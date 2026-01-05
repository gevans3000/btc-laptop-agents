from __future__ import annotations

import argparse
import base64
import binascii
import json
import shutil
import subprocess
import sys
import time
import gzip
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]

def _now_tag() -> str:
    return time.strftime("%Y%m%d-%H%M%S")

def _safe_rel_path(p: str) -> Path:
    if not p or p.strip() == "":
        raise ValueError("Empty path in patch spec")
    pp = Path(p)
    if pp.is_absolute():
        raise ValueError(f"Absolute paths not allowed: {p}")
    norm = (REPO_ROOT / pp).resolve()
    if REPO_ROOT not in norm.parents and norm != REPO_ROOT:
        raise ValueError(f"Path escapes repo: {p}")
    return norm

def _run(cmd: List[str]) -> Tuple[int, str]:
    p = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode, out

def _looks_like_json(s: str) -> bool:
    ss = s.strip()
    return ss.startswith("{") and ss.endswith("}")

def _decode_payload(s: str) -> Dict[str, Any]:
    s = (s or "").strip()

    if not s:
        raise ValueError("No payload provided. Paste the payload string I send you.")

    if "PASTE_PAYLOAD_HERE" in s or (s.startswith("<") and s.endswith(">")):
        raise ValueError("You pasted the placeholder. Replace it with the actual payload I send you.")

    # Allow raw JSON payload (handy for tiny patches)
    if _looks_like_json(s):
        try:
            return json.loads(s)
        except json.JSONDecodeError as e:
            raise ValueError(f"Raw JSON payload is invalid: {e}") from e

    # Otherwise: base64 (optionally gzipped)
    try:
        raw = base64.b64decode(s.encode("utf-8"), validate=True)
    except (binascii.Error, ValueError) as e:
        raise ValueError(
            "Payload is not valid base64. Make sure you pasted the full payload I sent (no quotes removed)."
        ) from e

    # Try gzip
    try:
        raw = gzip.decompress(raw)
    except Exception:
        pass

    try:
        txt = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError(
            "Decoded bytes are not UTF-8 JSON. This usually means the payload was truncated or not the one I sent."
        ) from e

    try:
        return json.loads(txt)
    except json.JSONDecodeError as e:
        raise ValueError(f"Decoded payload is not JSON: {e}") from e

def _backup(paths: List[Path], backup_dir: Path) -> Dict[str, str]:
    backup_dir.mkdir(parents=True, exist_ok=True)
    mapping: Dict[str, str] = {}
    for p in paths:
        rel = str(p.relative_to(REPO_ROOT))
        if p.exists():
            dst = backup_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dst)
            mapping[rel] = str(dst)
    return mapping

def _restore(mapping: Dict[str, str]) -> None:
    for rel, backup_path in mapping.items():
        src = Path(backup_path)
        dst = REPO_ROOT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

def _apply_writes(writes: List[Dict[str, Any]]) -> List[Path]:
    touched: List[Path] = []
    for w in writes:
        path = w["path"]
        content = w.get("content", "")
        p = _safe_rel_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8", newline="\n")
        touched.append(p)
    return touched

def _apply_deletes(deletes: List[str]) -> List[Path]:
    removed: List[Path] = []
    for d in deletes:
        p = _safe_rel_path(d)
        if p.exists():
            p.unlink()
            removed.append(p)
    return removed

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--b64", help="Patch payload as base64 (optionally gzipped before base64). Or raw JSON for tiny patches.")
    ap.add_argument("--stdin", action="store_true", help="Read payload from stdin (best for very long payloads).")
    ap.add_argument("--no-tests", action="store_true", help="Skip pytest (still runs compileall).")
    args = ap.parse_args()

    payload_str = sys.stdin.read().strip() if args.stdin else (args.b64 or "").strip()

    try:
        payload = _decode_payload(payload_str)
    except Exception as e:
        print(f"SAFE_APPLY INPUT ERROR: {e}", file=sys.stderr)
        return 2

    writes = payload.get("writes") or []
    deletes = payload.get("deletes") or []
    if not isinstance(writes, list) or not isinstance(deletes, list):
        print("Invalid payload shape. Expected {writes:[...], deletes:[...]}", file=sys.stderr)
        return 2

    touched_paths: List[Path] = []
    for w in writes:
        touched_paths.append(_safe_rel_path(w["path"]))
    for d in deletes:
        touched_paths.append(_safe_rel_path(d))

    tag = _now_tag()
    backup_dir = REPO_ROOT / ".patch_backups" / tag
    mapping = _backup(touched_paths, backup_dir)

    pre_existing = {str(p.relative_to(REPO_ROOT)) for p in touched_paths if p.exists()}

    try:
        _apply_deletes(deletes)
        _apply_writes(writes)

        rc, out = _run([sys.executable, "-m", "compileall", "src"])
        if rc != 0:
            raise RuntimeError("compileall failed:\n" + out)

        if not args.no_tests:
            rc, out = _run([sys.executable, "-m", "pytest", "-q"])
            if rc != 0:
                raise RuntimeError("pytest failed:\n" + out)

        print(f"SAFE_APPLY OK (backup in {backup_dir})")
        return 0

    except Exception as e:
        print("SAFE_APPLY FAILED — rolling back.", file=sys.stderr)
        print(str(e), file=sys.stderr)
        _restore(mapping)

        for p in touched_paths:
            rel = str(p.relative_to(REPO_ROOT))
            if rel not in pre_existing and p.exists():
                try:
                    p.unlink()
                except Exception:
                    pass

        print("Rollback complete.", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
