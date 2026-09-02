"""Encrypted clipboard vault.

Three defects in the previous implementation are fixed here, and they are worth
naming because two of them meant the vault never actually protected anything:

1. **The preview column was stored in plaintext.** ``preview = content[:120]``
   went into SQLite unencrypted, and ``search()`` ran ``WHERE preview LIKE ?``
   against it. A copied password shorter than 120 characters was therefore stored
   in full, in the clear, in a world-readable file. Verified by reading the raw
   database bytes back.

2. **A repeating-key XOR "cipher" was used whenever ``cryptography`` was
   missing**, and announced itself in the log as a "lightweight XOR fallback".
   Home-grown obfuscation presented as encryption is worse than no encryption,
   because the user believes something. There is now no fallback: without
   ``cryptography`` the vault refuses to start and says so.

3. **The SQLite connection was created on one thread and used from another.**
   The clipboard watcher is a thread, so every real capture raised
   ``sqlite3.ProgrammingError`` — swallowed by the event bus into a log line. The
   vault has never worked in the running application.

Searching encrypted data without decrypting it is handled with a **blind index**:
each token is HMAC'd with a key derived from the master key and stored as a hash.
Equality search works; the tokens themselves are not recoverable from the index.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import re
import sqlite3
import threading
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from platformdirs import PlatformDirs

from ..config.schema import AppConfig
from .secrets import classify_secret
from .utils import ensure_directory

LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from cryptography.fernet import Fernet

#: ``cryptography`` is a hard requirement of the vault and a soft one of the
#: package, so it is imported defensively. The class is held in a plain
#: ``Optional[Any]`` rather than rebinding the imported name, which is what made
#: the previous version un-typeable ("cannot assign to a type").
FERNET_CLASS: Any | None
DECRYPT_ERRORS: tuple

try:  # pragma: no cover - presence depends on the host
    from cryptography.fernet import Fernet as _FernetClass
    from cryptography.fernet import InvalidToken as _InvalidTokenError

    FERNET_CLASS = _FernetClass
    DECRYPT_ERRORS = (_InvalidTokenError, ValueError, UnicodeDecodeError)
    HAVE_CRYPTOGRAPHY = True
except ImportError:  # pragma: no cover
    FERNET_CLASS = None
    DECRYPT_ERRORS = (ValueError, UnicodeDecodeError)
    HAVE_CRYPTOGRAPHY = False

#: Bumped when the on-disk format changes so old rows can be recognised.
SCHEMA_VERSION = 2

#: OWASP's current floor for PBKDF2-HMAC-SHA256. The previous value (390,000)
#: was the 2023 guidance.
PBKDF2_ITERATIONS = 600_000

_TOKEN_RE = re.compile(r"[A-Za-z0-9_./@-]{3,64}")


class VaultUnavailable(RuntimeError):
    """The vault cannot operate securely and therefore will not operate."""


@dataclass(frozen=True)
class VaultEntry:
    entry_id: int
    created_at: str
    entry_type: str
    content: str


class ClipboardVault:
    """Encrypted, searchable, single-user clipboard history.

    Every stored field is ciphertext. The only plaintext columns are the row id,
    a timestamp, a coarse type label ("url", "code", "text") and the blind index.
    """

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        # The vault normally lives in the per-user data directory. ``AEGIS_VAULT_DIR``
        # overrides that so the vault can be relocated (portable installs) and so the
        # test suite can point it at a tmp dir -- platformdirs does not honour XDG on
        # Windows/macOS, so without an explicit override every test would share the
        # real vault under %LOCALAPPDATA%.
        override = os.getenv("AEGIS_VAULT_DIR")
        data_dir = (
            Path(override)
            if override
            else Path(PlatformDirs(appname="Aegis", appauthor="Aegis").user_data_dir)
        )
        self.db_path = data_dir / "vault.sqlite"
        ensure_directory(self.db_path.parent)
        self._harden(self.db_path.parent, 0o700)
        self.salt_path = self.db_path.with_suffix(".salt")

        self._fernet: Fernet | None = None
        self._index_key: bytes | None = None
        self._connection: sqlite3.Connection | None = None
        # One connection, guarded. sqlite3 objects are not thread-safe, and the
        # clipboard watcher runs on its own thread.
        self._lock = threading.RLock()
        self._enabled = False
        self._unavailable_reason: str | None = None

        if self.config.clipboard_vault.enabled:
            try:
                self._initialize()
                self._enabled = True
            except VaultUnavailable as exc:
                self._unavailable_reason = str(exc)
                LOGGER.warning("Clipboard vault disabled: %s", exc)

    # -- lifecycle -----------------------------------------------------
    def _initialize(self) -> None:
        if not HAVE_CRYPTOGRAPHY:
            raise VaultUnavailable(
                "the 'cryptography' package is not installed. The vault stores "
                "clipboard history, which routinely contains passwords and tokens, "
                "so it will not run without vetted encryption. Install it with: "
                "pip install 'aegis-os-agent[vault]'"
            )

        passphrase = self._load_passphrase()
        if not passphrase:
            raise VaultUnavailable(
                "no passphrase is available. Set one in your OS keyring (service "
                "'aegis', username 'vault') or in the AEGIS_VAULT_PASSPHRASE "
                "environment variable"
            )

        salt = self._load_salt()
        master = hashlib.pbkdf2_hmac(
            "sha256", passphrase.encode("utf-8"), salt, PBKDF2_ITERATIONS, dklen=64
        )
        # Split the derived material: half encrypts, half keys the blind index.
        # Reusing one key for both would let an index entry confirm a guess about
        # the ciphertext.
        assert FERNET_CLASS is not None  # guarded by HAVE_CRYPTOGRAPHY above
        self._fernet = FERNET_CLASS(base64.urlsafe_b64encode(master[:32]))
        self._index_key = master[32:]

        self._connection = sqlite3.connect(
            self.db_path, check_same_thread=False, isolation_level=None
        )
        self._harden(self.db_path, 0o600)
        with self._lock:
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS entries (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at   TEXT NOT NULL,
                    entry_type   TEXT NOT NULL,
                    payload      BLOB NOT NULL,
                    blind_index  TEXT NOT NULL DEFAULT '',
                    schema_ver   INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS entries_created_at ON entries(created_at)"
            )
            self._migrate_legacy_rows()
        LOGGER.info("Clipboard vault ready (AES via Fernet, PBKDF2 %s)", f"{PBKDF2_ITERATIONS:,}")

    def _migrate_legacy_rows(self) -> None:
        """Bring a schema-v1 ``entries`` table up to the current shape.

        v1 stored the first 120 characters of every clipboard entry in the clear
        (the ``preview`` column) and had neither the ``blind_index`` nor the
        ``schema_ver`` column that :meth:`store` now writes. ``CREATE TABLE IF
        NOT EXISTS`` is a no-op against an existing v1 table, so those two columns
        must be added here or every ``store()`` on an upgraded vault raises
        ``sqlite3.OperationalError: no column named blind_index``.

        The leaked preview bytes cannot be un-leaked, but the column can stop
        being carried forward, so it is dropped. Existing v1 rows predate the
        encrypted blind index and so get its empty-string default; they are
        simply not matched by :meth:`search` -- acceptable, since the plaintext
        preview that v1 could search has just been removed.
        """
        assert self._connection is not None
        columns = {
            row[1] for row in self._connection.execute("PRAGMA table_info(entries)").fetchall()
        }
        if "preview" not in columns and {"blind_index", "schema_ver"} <= columns:
            return  # already current
        if "preview" in columns:
            LOGGER.warning(
                "Existing vault uses schema v1, which stored a plaintext preview of every "
                "entry. Removing that column now. Consider wiping the vault and rotating "
                "any credential you copied while it was in use."
            )
            self._connection.execute("ALTER TABLE entries DROP COLUMN preview")
        if "blind_index" not in columns:
            self._connection.execute(
                "ALTER TABLE entries ADD COLUMN blind_index TEXT NOT NULL DEFAULT ''"
            )
        if "schema_ver" not in columns:
            self._connection.execute(
                "ALTER TABLE entries ADD COLUMN schema_ver INTEGER NOT NULL DEFAULT 1"
            )

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    # -- key material --------------------------------------------------
    def _load_passphrase(self) -> str | None:
        env = os.getenv("AEGIS_VAULT_PASSPHRASE")
        if env:
            return env
        try:
            import keyring

            value = keyring.get_password("aegis", "vault")
            if value:
                return value
        except Exception as exc:  # pragma: no cover - depends on the host keyring
            LOGGER.debug("OS keyring unavailable: %s", exc)
        return None

    def _load_salt(self) -> bytes:
        if self.salt_path.exists():
            salt = self.salt_path.read_bytes()
            if len(salt) >= 16:
                return salt
            LOGGER.warning("Vault salt file was too short; generating a new one")
        salt = os.urandom(32)
        self.salt_path.write_bytes(salt)
        self._harden(self.salt_path, 0o600)
        return salt

    @staticmethod
    def _harden(path: Path, mode: int) -> None:
        try:
            path.chmod(mode)
        except OSError as exc:  # pragma: no cover - Windows and exotic filesystems
            LOGGER.debug("Could not set permissions on %s: %s", path, exc)

    # -- crypto --------------------------------------------------------
    def _encrypt(self, plaintext: str) -> bytes:
        assert self._fernet is not None
        return self._fernet.encrypt(plaintext.encode("utf-8"))

    def _decrypt(self, payload: bytes) -> str | None:
        assert self._fernet is not None
        try:
            return self._fernet.decrypt(payload).decode("utf-8")
        except DECRYPT_ERRORS:
            return None

    def _blind_index(self, content: str) -> str:
        """Searchable, non-reversible token index.

        Each distinct lowercased token becomes an HMAC prefix. Equality search
        works by hashing the query the same way; the index cannot be reversed
        into the original tokens without the key.
        """
        assert self._index_key is not None
        tokens = {match.group(0).lower() for match in _TOKEN_RE.finditer(content)}
        return " ".join(sorted(self._hash_token(token) for token in tokens))

    def _hash_token(self, token: str) -> str:
        assert self._index_key is not None
        return hmac.new(self._index_key, token.encode("utf-8"), hashlib.sha256).hexdigest()[:16]

    # -- public API ----------------------------------------------------
    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def unavailable_reason(self) -> str | None:
        return self._unavailable_reason

    @property
    def location(self) -> Path:
        return self.db_path

    def store(self, content: str, *, entry_type: str = "text") -> bool:
        """Encrypt and record *content*. Returns False when nothing was stored.

        Content that looks like a credential is **not stored at all**. Excluding
        it is a stronger guarantee than encrypting it, and it means a vault
        compromise cannot expose what was never written.
        """
        if not self._enabled or self._connection is None:
            return False
        if not content or not content.strip():
            return False

        verdict = classify_secret(content)
        if verdict:
            LOGGER.info(
                "Clipboard entry not stored: it %s. Nothing was written to disk.",
                verdict.reason,
            )
            return False

        payload = self._encrypt(content)
        index = self._blind_index(content)
        with self._lock:
            self._connection.execute(
                "INSERT INTO entries (created_at, entry_type, payload, blind_index, schema_ver)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    entry_type,
                    payload,
                    index,
                    SCHEMA_VERSION,
                ),
            )
            self._prune()
        return True

    def _prune(self) -> None:
        """Keep only the newest ``max_items`` rows.

        One statement with one bound parameter. The previous implementation
        selected every id to keep and then built a ``NOT IN (?, ?, … )`` clause
        with one placeholder per retained row — a thousand-placeholder query on
        every single clipboard change.
        """
        assert self._connection is not None
        self._connection.execute(
            "DELETE FROM entries WHERE id NOT IN ("
            "  SELECT id FROM entries ORDER BY id DESC LIMIT ?"
            ")",
            (self.config.clipboard_vault.max_items,),
        )

    def search(self, query: str, *, limit: int = 50) -> list[VaultEntry]:
        """Find entries containing every token in *query*."""
        if not self._enabled or self._connection is None or not query.strip():
            return []
        tokens = {m.group(0).lower() for m in _TOKEN_RE.finditer(query)}
        if not tokens:
            return []

        clauses = " AND ".join("blind_index LIKE ?" for _ in tokens)
        params: list[object] = [f"%{self._hash_token(t)}%" for t in sorted(tokens)]
        params.append(limit)
        with self._lock:
            rows = self._connection.execute(
                f"SELECT id, created_at, entry_type, payload FROM entries "
                f"WHERE {clauses} ORDER BY id DESC LIMIT ?",
                params,
            ).fetchall()
        return self._decrypt_rows(rows)

    def recent(self, limit: int = 20) -> list[VaultEntry]:
        if not self._enabled or self._connection is None:
            return []
        with self._lock:
            rows = self._connection.execute(
                "SELECT id, created_at, entry_type, payload FROM entries "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return self._decrypt_rows(rows)

    def _decrypt_rows(self, rows: Iterable[tuple]) -> list[VaultEntry]:
        out: list[VaultEntry] = []
        for entry_id, created_at, entry_type, payload in rows:
            content = self._decrypt(payload)
            if content is None:
                LOGGER.warning("Vault entry %s could not be decrypted; skipping", entry_id)
                continue
            out.append(VaultEntry(entry_id, created_at, entry_type, content))
        return out

    def count(self) -> int:
        if not self._enabled or self._connection is None:
            return 0
        with self._lock:
            return int(self._connection.execute("SELECT COUNT(*) FROM entries").fetchone()[0])

    def wipe(self) -> int:
        """Delete every entry. Returns how many were removed."""
        if self._connection is None:
            return 0
        with self._lock:
            removed = self.count()
            self._connection.execute("DELETE FROM entries")
            self._connection.execute("VACUUM")
        return removed

    def __enter__(self) -> ClipboardVault:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


__all__ = ["ClipboardVault", "VaultEntry", "VaultUnavailable", "HAVE_CRYPTOGRAPHY"]
