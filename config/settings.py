"""Environment loading and project paths."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

CONFIG_DIR = ROOT / "config"
ANSWERS_DIR = ROOT / "answers"
DATA_DIR = Path(os.getenv("DATA_DIR", ROOT / "data"))

TG_HOST = os.getenv("TG_HOST", "")
TG_GRAPHNAME = os.getenv("TG_GRAPHNAME", "")

# Env vars forwarded to the tigergraph-mcp subprocess.
TG_ENV_KEYS = (
    "TG_HOST", "TG_GRAPHNAME", "TG_TGCLOUD", "TG_SECRET", "TG_USERNAME",
    "TG_PASSWORD", "TG_API_TOKEN", "TG_JWT_TOKEN", "TG_RESTPP_PORT",
    "TG_GS_PORT", "TG_SSL_PORT", "TG_CERT_PATH",
)


def tg_env() -> dict[str, str]:
    return {k: os.environ[k] for k in TG_ENV_KEYS if os.getenv(k)}
