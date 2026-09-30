import json
from pathlib import Path

HUB_DIR = Path.home() / ".agenthub"
CONFIG_PATH = HUB_DIR / "config.json"
AGENTS_DIR = HUB_DIR / "agents"
INSTALLED_PATH = HUB_DIR / "installed.json"
DEFAULT_MARKET = str(HUB_DIR / "market")


def ensure_dirs():
    HUB_DIR.mkdir(parents=True, exist_ok=True)
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)


def _atomic_write(path, text):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def load_config():
    if CONFIG_PATH.is_file():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_config(cfg):
    ensure_dirs()
    _atomic_write(CONFIG_PATH, json.dumps(cfg, ensure_ascii=False, indent=2))


def load_installed():
    if INSTALLED_PATH.is_file():
        try:
            return json.loads(INSTALLED_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_installed(data):
    ensure_dirs()
    _atomic_write(INSTALLED_PATH, json.dumps(data, ensure_ascii=False, indent=2))
