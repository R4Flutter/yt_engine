import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def fix_console() -> None:
    """Windows console is cp1252; titles contain emoji. Reconfigure to UTF-8."""
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def load_settings() -> dict:
    with open(ROOT / "config" / "settings.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_seeds() -> list[dict]:
    with open(ROOT / "config" / "seeds.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)["channels"]


def resolve_path(rel: str) -> Path:
    p = Path(rel).expanduser()
    return p if p.is_absolute() else ROOT / p


def api_key(settings: dict) -> str:
    s = settings["api"]
    env = os.environ.get(s["key_env"], "").strip()
    if env:
        return env
    dotenv = ROOT / ".env"
    if dotenv.exists():
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                if k.strip() == s["key_env"]:
                    return v.strip().strip('"').strip("'")
    return s.get("key", "").strip()