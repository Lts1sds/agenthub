import json
import shutil
import urllib.request
import zipfile
from pathlib import Path

from .config import DEFAULT_MARKET, HUB_DIR
from .spec import load_spec, spec_from_dict


class MarketSource:
    def list_agents(self):
        raise NotImplementedError

    def get_package(self, name):
        raise NotImplementedError


class LocalMarket(MarketSource):
    def __init__(self, path):
        self.path = Path(path).expanduser()

    def list_agents(self):
        if not self.path.is_dir():
            return []
        out = []
        for child in sorted(self.path.iterdir()):
            if child.is_dir() and (child / "agent.yaml").is_file():
                try:
                    out.append(load_spec(child))
                except Exception:
                    continue
        return out

    def get_package(self, name):
        cand = self.path / name
        if not (cand / "agent.yaml").is_file():
            raise FileNotFoundError("agent '%s' not found in market %s" % (name, self.path))
        return cand


class RemoteMarket(MarketSource):
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")

    def list_agents(self):
        data = _get_json(self.base_url + "/api/agents")
        out = []
        for item in data.get("agents", []):
            try:
                out.append(spec_from_dict(item))
            except Exception:
                continue
        return out

    def get_package(self, name):
        cache = HUB_DIR / "cache"
        cache.mkdir(parents=True, exist_ok=True)
        zip_path = cache / (name + ".zip")
        pkg_dir = cache / name
        if pkg_dir.exists():
            shutil.rmtree(pkg_dir)
        _download(self.base_url + "/api/download/" + name, zip_path)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(pkg_dir)
        if not (pkg_dir / "agent.yaml").is_file():
            raise FileNotFoundError("downloaded package '%s' is invalid" % name)
        return pkg_dir


def _get_json(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def _download(url, dest):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as f:
        shutil.copyfileobj(resp, f)


def resolve_market(cfg):
    ref = cfg.get("market") or DEFAULT_MARKET
    if ref.startswith(("http://", "https://")):
        return RemoteMarket(ref)
    return LocalMarket(ref)
