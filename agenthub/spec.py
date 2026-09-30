import re
from dataclasses import dataclass, field
from pathlib import Path

from .miniyaml import loads

VALID_TYPES = ("prompt-pack", "program")
VALID_TARGETS = ("comagic", "claude-code")
VALID_RUNTIMES = ("python-cli", "mcp", "node")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+([\-+][0-9A-Za-z.-]+)?$")


class SpecError(Exception):
    pass


@dataclass
class AgentSpec:
    name: str
    version: str
    author: str = ""
    description: str = ""
    type: str = "prompt-pack"
    models: list = field(default_factory=list)
    targets: list = field(default_factory=list)
    runtime_kind: str = ""
    entry: str = ""
    deps: str = "requirements.txt"


def load_manifest(package_dir):
    manifest = Path(package_dir) / "agent.yaml"
    if not manifest.is_file():
        raise SpecError("missing agent.yaml in %s" % package_dir)
    try:
        return loads(manifest.read_text(encoding="utf-8"))
    except ValueError as e:
        raise SpecError("agent.yaml parse error: %s" % e)


def load_spec(package_dir):
    return spec_from_dict(load_manifest(package_dir), Path(package_dir))


def spec_from_dict(data, package_dir=None):
    if not isinstance(data, dict):
        raise SpecError("agent.yaml must be a mapping")
    name = data.get("name")
    if not name or not NAME_RE.match(str(name)):
        raise SpecError("invalid or missing 'name' (lowercase letters, digits, hyphens)")
    version = str(data.get("version", ""))
    if not VERSION_RE.match(version):
        raise SpecError("invalid or missing 'version' (expected x.y.z)")
    atype = data.get("type", "prompt-pack")
    if atype not in VALID_TYPES:
        raise SpecError("'type' must be one of %s" % (VALID_TYPES,))
    spec = AgentSpec(
        name=str(name),
        version=version,
        author=str(data.get("author", "")),
        description=str(data.get("description", "")),
        type=atype,
        models=[str(m) for m in (data.get("models") or [])],
    )
    if atype == "prompt-pack":
        install = data.get("install") or {}
        if not isinstance(install, dict):
            raise SpecError("'install' must be a mapping")
        targets = install.get("targets") or []
        if isinstance(targets, str):
            targets = [targets]
        if not targets:
            raise SpecError("prompt-pack requires install.targets")
        bad = [t for t in targets if t not in VALID_TARGETS]
        if bad:
            raise SpecError("unknown targets %s, valid: %s" % (bad, VALID_TARGETS))
        spec.targets = targets
        if package_dir is not None and not (package_dir / "skills").is_dir():
            raise SpecError("prompt-pack requires a skills/ directory")
    else:
        runtime = data.get("runtime") or {}
        if not isinstance(runtime, dict):
            raise SpecError("program requires a 'runtime' section")
        kind = runtime.get("kind", "")
        if kind not in VALID_RUNTIMES:
            raise SpecError("runtime.kind must be one of %s" % (VALID_RUNTIMES,))
        entry = runtime.get("entry", "")
        if not entry:
            raise SpecError("program requires runtime.entry")
        if package_dir is not None and not (package_dir / entry).is_file():
            raise SpecError("runtime.entry not found in package: %s" % entry)
        spec.runtime_kind = kind
        spec.entry = entry
        spec.deps = runtime.get("deps", "requirements.txt")
    return spec
