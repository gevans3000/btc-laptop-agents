from __future__ import annotations

import hashlib
import json

from laptop_agents.data.providers.bitunix_signing import build_query_string, sign_rest


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def test_query_string_ascii_sorted_concat():
    # docs example shows: id1uid200
    qs = build_query_string({"uid": 200, "id": 1})
    assert qs == "id1uid200"


def test_rest_signature_matches_reference_computation():
    nonce = "123456"
    timestamp_ms = 1724285700000
    api_key = "yourApiKey"
    secret_key = "yourSecretKey"
    query_params = build_query_string({"uid": 200, "id": 1})

    body_obj = {
        "uid": "2899",
        "arr": [{"id": 1, "name": "maple"}, {"id": 2, "name": "lily"}],
    }
    body = json.dumps(body_obj, separators=(",", ":"), ensure_ascii=False)

    # expected per docs: digest=sha256(nonce+timestamp+apiKey+queryParams+body); sign=sha256(digest+secretKey)
    digest = sha256_hex(nonce + str(timestamp_ms) + api_key + query_params + body)
    expected = sha256_hex(digest + secret_key)

    got = sign_rest(
        nonce=nonce,
        timestamp_ms=timestamp_ms,
        api_key=api_key,
        secret_key=secret_key,
        query_params=query_params,
        body=body,
    )
    assert got == expected
