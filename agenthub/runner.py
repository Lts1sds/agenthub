import os
import subprocess
import sys
from pathlib import Path

from . import config


def run(name, args, cfg):
    installed = config.load_installed()
    record = installed.get(name)
    if record is None:
        raise RuntimeError("'%s' is not installed" % name)
    if record.get("type") != "program":
        raise RuntimeError(
            "'%s' is a %s; prompt-packs are used inside your agent runtime" % (name, record.get("type"))
        )
    pkg = Path(record["path"])
    entry = pkg / record.get("entry", "")
    if not entry.is_file():
        raise RuntimeError("entry file missing: %s" % entry)
    venv = pkg / ".venv"
    if venv.is_dir():
        if sys.platform == "win32":
            python = venv / "Scripts" / "python.exe"
        else:
            python = venv / "bin" / "python"
    else:
        python = sys.executable
    env = os.environ.copy()
    if cfg.get("base_url"):
        env["AGENTHUB_BASE_URL"] = cfg["base_url"]
    if cfg.get("api_key"):
        env["AGENTHUB_API_KEY"] = cfg["api_key"]
    proc = subprocess.run([str(python), str(entry), *args], cwd=str(pkg), env=env)
    return proc.returncode
