import os

from cryptography.fernet import Fernet

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        key = os.environ.get("ENCRYPTION_KEY")
        if not key:
            # Pydantic-settings loads .env.local into Settings fields but doesn't
            # set real env vars.  Fall back to reading the file directly.
            try:
                from insightxpert.config import Settings
                key = Settings().encryption_key or None
            except Exception:
                key = None
        if not key:
            raise RuntimeError(
                "ENCRYPTION_KEY not set. Set a 32-byte base64-encoded key "
                "(e.g., export ENCRYPTION_KEY=$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'))"
            )
        if isinstance(key, str):
            key = key.encode()
        _fernet = Fernet(key)
    return _fernet


def encrypt_credentials(value: str) -> str:
    """Encrypt a plaintext value using Fernet symmetric encryption."""
    f = _get_fernet()
    return f.encrypt(value.encode()).decode()


def decrypt_credentials(encrypted_value: str) -> str:
    """Decrypt a Fernet-encrypted value."""
    f = _get_fernet()
    return f.decrypt(encrypted_value.encode()).decode()
