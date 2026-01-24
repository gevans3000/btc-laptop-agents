"""Signing and utility functions for Bitunix API."""

from __future__ import annotations
import hashlib
import json
import time
from typing import Any, Dict, Optional


def _now_ms() -> int:
    """Get current timestamp in milliseconds."""
    return int(time.time() * 1000)


def _sha256_hex(s: str) -> str:
    """Compute SHA256 hex digest of a string."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _minified_json(obj: Any) -> str:
    """Return JSON string with no spaces between separators."""
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def build_query_string(params: Optional[Dict[str, Any]]) -> str:
    """
    Bitunix-specific query string: sort params by ASCII key,
    then concat key+value with NO separators.
    """
    if not params:
        return ""
    items = sorted(params.items(), key=lambda kv: kv[0])
    return "".join([str(k) + str(v) for k, v in items])


def sign_rest(
    *,
    nonce: str,
    timestamp_ms: int,
    api_key: str,
    secret_key: str,
    query_params: str,
    body: str,
) -> str:
    """
    Compute Bitunix REST signature.
    digest = sha256(nonce + timestamp + apiKey + queryParams + body)
    sign = sha256(digest + secretKey)
    """
    digest = _sha256_hex(nonce + str(timestamp_ms) + api_key + query_params + body)
    return _sha256_hex(digest + secret_key)


def sign_ws(
    *, nonce: str, timestamp_ms: int, api_key: str, secret_key: str, params_string: str
) -> str:
    """
    Compute Bitunix WebSocket signature.
    digest = sha256(nonce + timestamp + apiKey + params)
    sign = sha256(digest + secretKey)
    """
    digest = _sha256_hex(nonce + str(timestamp_ms) + api_key + params_string)
    return _sha256_hex(digest + secret_key)
