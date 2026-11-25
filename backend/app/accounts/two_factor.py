"""TOTP (authenticator-app) two-factor auth helpers.

Secrets are encrypted at rest with a Fernet key derived from the same
APP_SESSION_SECRET security.py already requires - no second secret to
provision or back up separately. The tradeoff: rotating APP_SESSION_SECRET
makes existing TOTP secrets undecryptable. That's acceptable here because
an admin "reset 2FA" (accounts.users.admin_reset_totp) is already the
recovery path for a lost authenticator, and covers this case too.
"""
import base64
import hashlib
import io
import os

import pyotp
import qrcode
from cryptography.fernet import Fernet, InvalidToken

ISSUER = "Revenue Console"


def _fernet():
    secret = os.environ.get("APP_SESSION_SECRET", "").encode()
    key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    return Fernet(key)


def generate_secret():
    return pyotp.random_base32()


def encrypt(secret):
    return _fernet().encrypt(secret.encode()).decode()


def decrypt(token):
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return None


def provisioning_qr_data_uri(secret, username):
    uri = pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name=ISSUER)
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def verify_code(secret, code):
    if not isinstance(code, str) or not code.strip():
        return False
    return pyotp.TOTP(secret).verify(code.strip(), valid_window=1)
