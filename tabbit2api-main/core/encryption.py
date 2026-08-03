import os
import base64
import hashlib
import logging
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger("tabbit2openai")

def get_master_key() -> bytes:
    """Get the 32-byte master key derived from environment variable."""
    key_str = os.environ.get("TABBIT_MASTER_KEY", "super-secret-master-key-12345678")
    # Ensure exactly 32 bytes for AES-256 by hashing the input string
    return hashlib.sha256(key_str.encode('utf-8')).digest()

def encrypt_token(plain_token: str) -> str:
    """Encrypt a plaintext token using AES-256-GCM."""
    if not plain_token:
        return ""
    try:
        key = get_master_key()
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, plain_token.encode('utf-8'), None)
        # Store nonce + ciphertext together
        return base64.b64encode(nonce + ciphertext).decode('utf-8')
    except Exception as e:
        logger.error(f"Failed to encrypt token: {e}")
        return ""

def decrypt_token(encrypted_token: str) -> str:
    """Decrypt an encrypted token using AES-256-GCM."""
    if not encrypted_token:
        return ""
    try:
        key = get_master_key()
        aesgcm = AESGCM(key)
        data = base64.b64decode(encrypted_token)
        nonce = data[:12]
        ciphertext = data[12:]
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode('utf-8')
    except Exception as e:
        logger.error(f"Failed to decrypt token: {e}")
        return ""
