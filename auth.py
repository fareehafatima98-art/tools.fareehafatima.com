"""
Auth helpers for the tools portal.

Single shared password with HMAC-signed cookies (no accounts). Routes that
need protection call check_auth(request) to validate the cookie; redirects to
/login if absent or invalid.
"""
import hmac, hashlib, os, time
from typing import Optional

SECRET = os.environ.get("TOOLS_SECRET", "PLEASE_SET_TOOLS_SECRET_IN_VERCEL_ENV")
PASSWORD = os.environ.get("TOOLS_PASSWORD", "")
COOKIE_NAME = "tools_auth"
COOKIE_MAX_AGE = 30 * 24 * 3600  # 30 days

def verify_password(password: str) -> bool:
    """Check if the submitted password matches TOOLS_PASSWORD."""
    if not PASSWORD:
        return False
    # compare as bytes: compare_digest rejects str with non-ASCII characters
    return hmac.compare_digest(password.encode("utf-8"), PASSWORD.encode("utf-8"))

def sign_cookie_value(expiry: int) -> str:
    """Create an HMAC-signed cookie value: expiry|signature"""
    msg = str(expiry).encode("utf-8")
    sig = hmac.new(SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return f"{expiry}|{sig}"

def verify_cookie_value(value: str) -> bool:
    """Verify the cookie's signature and check it hasn't expired."""
    try:
        expiry_str, sig = value.split("|", 1)
        expiry = int(expiry_str)

        # Check expiry
        if time.time() > expiry:
            return False

        # Verify signature
        expected_sig = hmac.new(SECRET.encode("utf-8"),
                               expiry_str.encode("utf-8"),
                               hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected_sig)
    except (ValueError, AttributeError):
        return False

def is_authenticated(cookies: dict) -> bool:
    """Check if the request has a valid auth cookie."""
    cookie_val = cookies.get(COOKIE_NAME)
    if not cookie_val:
        return False
    return verify_cookie_value(cookie_val)

def make_auth_cookie() -> tuple[str, str]:
    """Return (cookie_name, cookie_value) for setting after login."""
    expiry = int(time.time() + COOKIE_MAX_AGE)
    value = sign_cookie_value(expiry)
    return (COOKIE_NAME, value)
