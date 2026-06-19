import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any

try:
    from jose import JWTError, jwt
except ModuleNotFoundError:
    class JWTError(Exception):
        """Fallback JWT error used when python-jose is unavailable."""

    def _b64encode(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    def _b64decode(data: str) -> bytes:
        padding = "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode((data + padding).encode("ascii"))

    def _json_default(value: Any) -> Any:
        if isinstance(value, datetime):
            return int(value.timestamp())
        raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")

    class _FallbackJWT:
        def encode(self, claims: dict[str, Any], key: str, algorithm: str = "HS256") -> str:
            if algorithm != "HS256":
                raise JWTError(f"Unsupported JWT algorithm without python-jose: {algorithm}")
            header = {"alg": algorithm, "typ": "JWT"}
            header_b64 = _b64encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
            payload_b64 = _b64encode(
                json.dumps(claims, default=_json_default, separators=(",", ":")).encode("utf-8")
            )
            signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
            signature = hmac.new(key.encode("utf-8"), signing_input, hashlib.sha256).digest()
            return f"{header_b64}.{payload_b64}.{_b64encode(signature)}"

        def decode(self, token: str, key: str, algorithms: list[str] | None = None) -> dict[str, Any]:
            allowed = algorithms or ["HS256"]
            try:
                header_b64, payload_b64, signature_b64 = token.split(".")
                header = json.loads(_b64decode(header_b64))
                if header.get("alg") not in allowed or header.get("alg") != "HS256":
                    raise JWTError("Unsupported JWT algorithm")
                signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
                expected = hmac.new(key.encode("utf-8"), signing_input, hashlib.sha256).digest()
                if not hmac.compare_digest(_b64decode(signature_b64), expected):
                    raise JWTError("Invalid JWT signature")
                payload = json.loads(_b64decode(payload_b64))
            except Exception as exc:
                if isinstance(exc, JWTError):
                    raise
                raise JWTError("Invalid JWT token") from exc

            exp = payload.get("exp")
            if exp is not None and datetime.now(timezone.utc).timestamp() > float(exp):
                raise JWTError("JWT token has expired")
            return payload

    jwt = _FallbackJWT()
