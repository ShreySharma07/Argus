"""Loader for policy_matrix.yaml: action -> approval route."""

from functools import lru_cache

import yaml

from config.settings import CONFIG_DIR


@lru_cache
def policy() -> dict:
    with open(CONFIG_DIR / "policy_matrix.yaml") as f:
        return yaml.safe_load(f)


def route_for(action: str, exposure_usd: float = 0.0) -> str:
    """Approval route (`auto` | `L1` | `L2`) for an action under Policy §2."""
    spec = policy()["actions"].get(action)
    if spec is None:
        raise KeyError(f"Unknown policy action '{action}'")
    if "route_by_exposure" in spec:
        r = spec["route_by_exposure"]
        return r["at_or_below"] if exposure_usd <= r["limit_usd"] else r["above"]
    return spec["route"]


def is_executable(action: str, exposure_usd: float = 0.0) -> bool:
    return route_for(action, exposure_usd) in policy()["executable_routes"]


def threshold(name: str) -> float:
    return policy()["thresholds"][name]
