"""Profile-based configuration loader with merge precedence."""

from pathlib import Path
from typing import Any, Dict, Optional
import os
import yaml

PROFILES_DIR = Path(__file__).parent.parent.parent.parent / "config" / "profiles"


def load_profile(
    profile_name: str, cli_overrides: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Load config with precedence: base < profile < env < CLI."""
    # 1. Load base
    base_path = PROFILES_DIR / "base.yaml"
    config = _load_yaml(base_path) if base_path.exists() else {}

    # 2. Load profile (handles _extends)
    profile_path = PROFILES_DIR / f"{profile_name}.yaml"
    if profile_path.exists():
        profile = _load_yaml(profile_path)
        if "_extends" in profile:
            # Note: For now we just support extending base.yaml
            # In a more complex system, this would be recursive
            del profile["_extends"]
        config = _deep_merge(config, profile)

    # 3. Apply env overrides (LA_* prefix)
    config = _apply_env_overrides(config)

    # 4. Apply CLI overrides
    if cli_overrides:
        config = _deep_merge(config, cli_overrides)

    return config


def _load_yaml(path: Path) -> Dict[str, Any]:
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _apply_env_overrides(config: Dict[str, Any]) -> Dict[str, Any]:
    """Apply environment overrides with LA_ prefix."""
    for key, value in os.environ.items():
        if key.startswith("LA_"):
            parts = key[3:].lower().split("_")
            _update_config_nested(config, parts, _parse_value(value))
    return config


def _update_config_nested(d: Dict[str, Any], parts: list[str], value: Any) -> bool:
    """Recursively update config by trying to match parts against existing keys."""
    if not parts:
        return False

    # Try all combinations of joining parts to match an existing key
    for i in range(1, len(parts) + 1):
        key = "_".join(parts[:i])
        if key in d:
            if i == len(parts):
                d[key] = value
                return True
            elif isinstance(d[key], dict):
                if _update_config_nested(d[key], parts[i:], value):
                    return True

    # Fallback to creating new structure if no match found
    current = d
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value
    return True


def _set_nested(d: Dict[str, Any], keys: list[str], value: Any) -> None:
    """Legacy helper, now replaced by _update_config_nested but kept for reference if needed."""
    for key in keys[:-1]:
        d = d.setdefault(key, {})
    d[keys[-1]] = value


def _parse_value(v: str) -> Any:
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    try:
        if "." in v:
            return float(v)
        return int(v)
    except ValueError:
        return v
