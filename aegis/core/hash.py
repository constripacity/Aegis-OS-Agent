"""Hash helpers for streaming file integrity checks."""



import hashlib
from pathlib import Path

__all__ = ["sha256_file"]


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Return the SHA-256 digest of ``path`` without loading it entirely."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()

