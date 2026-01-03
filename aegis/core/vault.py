"""Encrypted clipboard vault storage with AES-Fernet support when available."""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

from platformdirs import PlatformDirs

from ..config.schema import AppConfig
from .classifiers import classify_text
from .utils import ensure_directory

LOGGER = logging.getLogger(__name__)


class ClipboardVault:
    """Store clipboard entries in an encrypted SQLite database."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        dirs = PlatformDirs(appname="Aegis", appauthor="Aegis")
        self.db_path = Path(dirs.user_data_dir) / "vault.sqlite"
        ensure_directory(self.db_path.parent)
        self.salt_path = self.db_path.with_suffix(".salt")
        self._fernet: Any | None = None
        self._xor_key: Optional[bytes] = None
        self._connection: sqlite3.Connection | None = None
        self._enabled = False
        if self.config.clipboard_vault.enabled:
            self._enabled = self._initialize()

    def _initialize(self) -> bool:
        key_material = self._derive_key()
        if not key_material:
            LOGGER.warning("Clipboard vault enabled but no passphrase provided; disabling vault")
            return False
        fernet_cls = self._load_fernet_class()
        if fernet_cls is not None:
            self._fernet = fernet_cls(base64.urlsafe_b64encode(key_material))
            LOGGER.info("Using AES-Fernet backend for clipboard vault")
        else:
            self._xor_key = key_material
            LOGGER.warning(
                "Clipboard vault is using XOR obfuscation (not strong encryption) because "
                "the 'cryptography' package is not installed. Install it with: pip install cryptography"
            )
        self._connection = sqlite3.connect(self.db_path)
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                entry_type TEXT NOT NULL,
                preview TEXT NOT NULL,
                payload BLOB NOT NULL
            )
            """
        )
        self._connection.commit()
        return True

    def _prune_entries(self) -> None:
        if not self._connection:
            return
        cursor = self._connection.execute(
            "SELECT id FROM entries ORDER BY id DESC LIMIT ?",
            (self.config.clipboard_vault.max_items,),
        )
        keep_ids = [row[0] for row in cursor.fetchall()]
        if not keep_ids:
            return
        placeholders = ",".join(["?"] * len(keep_ids))
        self._connection.execute(
            f"DELETE FROM entries WHERE id NOT IN ({placeholders})",
            keep_ids,
        )
        self._connection.commit()

    def _derive_key(self) -> bytes | None:
        passphrase = self._load_passphrase()
        if not passphrase:
            return None
        salt = self._load_salt()
        digest = hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, 390000, dklen=32)
        return digest

    def _load_passphrase(self) -> str | None:
        env = os.getenv("AEGIS_VAULT_PASSPHRASE")
        if env:
            return env
        try:
            import importlib

            keyring = importlib.import_module("keyring")
            value = keyring.get_password("aegis", "vault")
            if value:
                return value
        except Exception:  # pragma: no cover
            LOGGER.debug("Keyring not available")
        return None

    def _load_fernet_class(self) -> Any | None:
        try:
            import importlib

            module = importlib.import_module("cryptography.fernet")
            return getattr(module, "Fernet", None)
        except Exception:  # pragma: no cover - optional dependency
            LOGGER.debug("cryptography not available; using fallback")
            return None

    def _load_salt(self) -> bytes:
        if self.salt_path.exists():
            return self.salt_path.read_bytes()
        salt = os.urandom(16)
        self.salt_path.write_bytes(salt)
        return salt

    def _encrypt(self, plaintext: str) -> bytes:
        if self._fernet is not None:
            return self._fernet.encrypt(plaintext.encode("utf-8"))
        assert self._xor_key is not None
        data = plaintext.encode("utf-8")
        encrypted = bytes(b ^ self._xor_key[i % len(self._xor_key)] for i, b in enumerate(data))
        return base64.urlsafe_b64encode(encrypted)

    def _decrypt(self, payload: bytes) -> str:
        if self._fernet is not None:
            return self._fernet.decrypt(payload).decode("utf-8")
        assert self._xor_key is not None
        encrypted = base64.urlsafe_b64decode(payload)
        data = bytes(b ^ self._xor_key[i % len(self._xor_key)] for i, b in enumerate(encrypted))
        return data.decode("utf-8")

    def store(self, content: str) -> None:
        if not self._enabled or not (self._fernet or self._xor_key) or not self._connection:
            return
        classification = classify_text(content)
        preview = content[:120].replace("\n", " ")
        payload = self._encrypt(content)
        self._connection.execute(
            "INSERT INTO entries (created_at, entry_type, preview, payload) VALUES (?, ?, ?, ?)",
            (
                datetime.utcnow().isoformat(),
                classification.label,
                preview,
                payload,
            ),
        )
        self._connection.commit()
        self._prune_entries()

    def search(self, query: str) -> List[str]:
        if not self._enabled or not (self._fernet or self._xor_key) or not self._connection:
            return []
        cursor = self._connection.execute(
            "SELECT payload FROM entries WHERE preview LIKE ? ORDER BY id DESC LIMIT ?",
            (f"%{query}%", self.config.clipboard_vault.max_items),
        )
        results = []
        for (payload,) in cursor.fetchall():
            try:
                decrypted = self._decrypt(payload)
                results.append(decrypted)
            except Exception:  # pragma: no cover
                LOGGER.warning("Failed to decrypt vault entry")
        return results

    def wipe(self) -> None:
        if not self._connection:
            return
        self._connection.execute("DELETE FROM entries")
        self._connection.commit()

    def close(self) -> None:
        if self._connection:
            self._connection.close()
            self._connection = None

    def __del__(self) -> None:  # pragma: no cover
        try:
            self.close()
        except Exception:
            LOGGER.debug("Failed to close vault connection")

    @property
    def location(self) -> Path:
        return self.db_path

    @property
    def enabled(self) -> bool:
        return self._enabled


__all__ = ["ClipboardVault"]

