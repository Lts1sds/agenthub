import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import config
from .market import resolve_market
from .spec import SpecError, load_spec


def install(name, cfg, force=False):
    installed = config.load_installed()
    if name in installed and not force:
        raise RuntimeError("'%s' already installed (use --force to reinstall)" % name)
    market = resolve_market(cfg)
    src = market.get_package(name)
    spec = load_spec(src)
    dest = config.AGENTS_DIR / name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    record = {
        "version": spec.version,
        "type": spec.type,
        "path": str(dest),
        "installed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "injected": [],
    }
    if spec.type == "prompt-pack":
        record["injected"] = _inject_skills(spec, dest)
    else:
        _setup_program(spec, dest)
        record["entry"] = spec.entry
        record["launcher"] = str(_write_launcher(spec))
    installed[name] = record
    config.save_installed(installed)
    return spec, record


def _write_launcher(spec):
    path = config.HUB_DIR / ("run-%s.bat" % spec.name if sys.platform == "win32" else "run-%s.sh" % spec.name)
    if sys.platform == "win32":
        path.write_text("@echo off\r\nagenthub run %s %%*\r\n" % spec.name, encoding="utf-8")
    else:
        path.write_text("#!/usr/bin/env bash\nagenthub run %s \"$@\"\n" % spec.name, encoding="utf-8")
        path.chmod(0o755)
    return path


def _skill_targets():
    return {
        "comagic": Path.home() / ".config" / "comagic" / "skills",
        "claude-code": Path.home() / ".claude" / "skills",
    }


def _inject_skills(spec, dest):
    injected = []
    skills_dir = dest / "skills"
    for target in spec.targets:
        base = _skill_targets()[target]
        base.mkdir(parents=True, exist_ok=True)
        for skill in sorted(skills_dir.iterdir()):
            if not skill.is_dir():
                continue
            out = base / skill.name
            if out.exists():
                shutil.rmtree(out)
            shutil.copytree(skill, out)
            injected.append({"target": target, "skill": skill.name, "path": str(out)})
    return injected


def _setup_program(spec, dest):
    if spec.runtime_kind != "python-cli":
        raise SpecError("runtime '%s' is not supported yet" % spec.runtime_kind)
    req = dest / spec.deps
    has_deps = req.is_file() and req.read_text(encoding="utf-8").strip()
    if not has_deps:
        return
    venv_dir = dest / ".venv"
    if venv_dir.exists():
        shutil.rmtree(venv_dir)
    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
    if sys.platform == "win32":
        pip = venv_dir / "Scripts" / "pip.exe"
    else:
        pip = venv_dir / "bin" / "pip"
    subprocess.run([str(pip), "install", "-r", str(req)], check=True)


def uninstall(name):
    installed = config.load_installed()
    record = installed.pop(name, None)
    if record is None:
        raise RuntimeError("'%s' is not installed" % name)
    for inj in record.get("injected", []):
        p = Path(inj["path"])
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
    launcher = record.get("launcher")
    if launcher and Path(launcher).is_file():
        Path(launcher).unlink()
    path = Path(record["path"])
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    config.save_installed(installed)
    return record
