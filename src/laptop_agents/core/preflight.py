from dataclasses import dataclass
from typing import List, Tuple, Callable, Any, Dict


@dataclass
class PreflightResult:
    name: str
    passed: bool
    message: str


def check_api_connectivity() -> bool:
    # Placeholder for actual API ping
    return True


def check_position_match() -> bool:
    # Placeholder for local vs exchange recon
    return True


def check_min_equity() -> bool:
    return True


def check_daily_loss() -> bool:
    return True


def check_kill_switch() -> bool:
    import os

    val = os.environ.get("LA_KILL_SWITCH", "FALSE")
    return bool(val == "FALSE")


PREFLIGHT_GATES: List[Tuple[str, Callable[[], bool]]] = [
    ("api_connectivity", check_api_connectivity),
    ("position_reconciliation", check_position_match),
    ("min_equity", check_min_equity),
    ("daily_loss_ok", check_daily_loss),
    ("kill_switch_off", check_kill_switch),
]


def run_preflight(config: Dict[str, Any]) -> List[PreflightResult]:
    results = []
    for name, gate_func in PREFLIGHT_GATES:
        try:
            passed: bool = gate_func()
            results.append(
                PreflightResult(name, passed, "Passed" if passed else "Failed")
            )
        except Exception as e:
            results.append(PreflightResult(name, False, str(e)))
    return results


def all_gates_passed(results: List[PreflightResult]) -> bool:
    return all(r.passed for r in results)
