# auth/ory_jwt.py

import os
import time
import requests
from functools import lru_cache
from jose import jwt, JWTError

JWKS_URI = os.getenv("JWKS_URI")
if not JWKS_URI:
    raise RuntimeError("JWKS_URI environment variable must be set")

ALGORITHMS = ["RS256"]


class JWKSClient:
    """
    Rough equivalent of `jwksRsa.expressJwtSecret` with:
      - in-memory cache
      - simple rate-limit on JWKS fetches
    """

    def __init__(self, jwks_uri: str, max_requests_per_minute: int = 5):
        self.jwks_uri = jwks_uri
        self.max_requests_per_minute = max_requests_per_minute

        self._jwks = None
        self._last_fetch_ts = 0.0
        self._requests_this_minute = 0
        self._window_start_ts = time.time()

    def _maybe_reset_rate_window(self) -> None:
        now = time.time()
        if now - self._window_start_ts >= 60:
            self._window_start_ts = now
            self._requests_this_minute = 0

    def _fetch_jwks(self) -> None:
        self._maybe_reset_rate_window()
        if self._requests_this_minute >= self.max_requests_per_minute:
            # Very simple rate limiting; in practice, you'd want logging here
            return

        resp = requests.get(self.jwks_uri, timeout=5)
        resp.raise_for_status()
        self._jwks = resp.json()
        self._last_fetch_ts = time.time()
        self._requests_this_minute += 1

    def _ensure_jwks(self) -> None:
        # Cache: re-fetch at most every 5 minutes (similar to `cache: true`)
        if self._jwks is None or (time.time() - self._last_fetch_ts) > 300:
            self._fetch_jwks()

    def get_key(self, kid: str):
        """
        Return the public key (as dict) for the given `kid`.
        """
        self._ensure_jwks()
        if not self._jwks or "keys" not in self._jwks:
            raise RuntimeError("JWKS not available")

        for key in self._jwks["keys"]:
            if key.get("kid") == kid:
                return key

        # If not found, try one more fresh fetch
        self._fetch_jwks()
        if not self._jwks or "keys" not in self._jwks:
            raise RuntimeError("JWKS not available after refresh")

        for key in self._jwks["keys"]:
            if key.get("kid") == kid:
                return key

        raise JWTError(f"No matching JWK found for kid={kid}")


jwks_client = JWKSClient(JWKS_URI)


def _jwk_to_public_key(jwk: dict):
    """
    python-jose can take the JWK dict directly, so this is just a pass-through.
    If you used another lib, you might need to convert.
    """
    return jwk


def decode_ory_jwt(token: str, audience: str | None = None) -> dict:
    """
    Python equivalent of your ORY JWT validation config.

    - Reads `kid` from the header
    - Fetches the correct JWK from JWKS
    - Validates using RS256
    """
    try:
        unverified_header = jwt.get_unverified_header(token)
    except JWTError as e:
        raise JWTError(f"Invalid token header: {e}")

    kid = unverified_header.get("kid")
    if not kid:
        raise JWTError("Token header missing 'kid'")

    jwk = jwks_client.get_key(kid)
    public_key = _jwk_to_public_key(jwk)

    options = {
        "verify_aud": audience is not None,
    }

    return jwt.decode(
        token,
        public_key,
        algorithms=ALGORITHMS,
        audience=audience,
        options=options,
    )
