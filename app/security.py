"""Senhas (scrypt) e cookie de sessão assinado."""
import base64
import hashlib
import hmac
import json
import os
import time

from . import config


def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(h).decode()


def verify_password(pw: str, stored: str | None) -> bool:
    if not stored or not pw or not stored.startswith("scrypt$"):
        return False
    _, salt_b64, h_b64 = stored.split("$")
    h = hashlib.scrypt(pw.encode(), salt=base64.b64decode(salt_b64), n=2**14, r=8, p=1, dklen=32)
    return hmac.compare_digest(h, base64.b64decode(h_b64))


def password_version(stored: str | None) -> str:
    """Muda quando a senha muda → sessões antigas deixam de valer."""
    return hashlib.sha256((stored or "").encode()).hexdigest()[:12]


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sig(payload: str) -> str:
    return _b64(hmac.new(config.SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).digest())


def sign(data: dict, ttl_s: int) -> str:
    payload = _b64(json.dumps({**data, "exp": int(time.time()) + ttl_s}, separators=(",", ":")).encode())
    return payload + "." + _sig(payload)


def unsign(token: str | None) -> dict | None:
    if not token or "." not in token:
        return None
    payload, sig = token.rsplit(".", 1)
    if not hmac.compare_digest(sig, _sig(payload)):
        return None
    try:
        data = json.loads(_unb64(payload))
    except ValueError:
        return None
    if data.get("exp", 0) < time.time():
        return None
    return data
