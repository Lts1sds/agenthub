import argparse
import io
import json
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from . import __version__, config
from .installer import install as do_install
from .installer import uninstall as do_uninstall
from .market import resolve_market
from .runner import run as do_run
from .spec import SpecError, load_spec, load_manifest


def main(argv=None):
    parser = argparse.ArgumentParser(prog="agenthub", description="AgentHub - agent marketplace CLI")
    parser.add_argument("--version", action="version", version="agenthub %s" % __version__)
    sub = parser.add_subparsers(dest="command")

    p_login = sub.add_parser("login", help="save hub credentials (relay base_url + api_key)")
    p_login.add_argument("--base-url", required=True)
    p_login.add_argument("--api-key", required=True)
    p_login.add_argument("--upload-token", help="creator upload token for the market server")

    sub.add_parser("whoami", help="show current config")

    p_market = sub.add_parser("market", help="market source management")
    market_sub = p_market.add_subparsers(dest="market_command")
    p_set = market_sub.add_parser("set", help="set market directory (or remote URL)")
    p_set.add_argument("value")
    market_sub.add_parser("show", help="show current market")

    sub.add_parser("list", help="list agents in the market")

    p_info = sub.add_parser("info", help="show agent details")
    p_info.add_argument("name")

    p_install = sub.add_parser("install", help="install an agent")
    p_install.add_argument("name")
    p_install.add_argument("--force", action="store_true")

    sub.add_parser("installed", help="list installed agents")

    p_uninstall = sub.add_parser("uninstall", help="remove an installed agent")
    p_uninstall.add_argument("name")

    p_run = sub.add_parser("run", help="run a program-type agent")
    p_run.add_argument("name")
    p_run.add_argument("args", nargs=argparse.REMAINDER)

    p_push = sub.add_parser("push", help="upload an agent package to the remote market")
    p_push.add_argument("dir")
    p_push.add_argument("--token", help="upload token (or saved via login --upload-token)")

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    try:
        return dispatch(args)
    except (RuntimeError, SpecError, FileNotFoundError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 1


def dispatch(args):
    cfg = config.load_config()
    if args.command == "login":
        cfg["base_url"] = args.base_url.rstrip("/")
        cfg["api_key"] = args.api_key
        if args.upload_token:
            cfg["upload_token"] = args.upload_token
        config.save_config(cfg)
        print("credentials saved.")
        return 0
    if args.command == "whoami":
        if not cfg:
            print("not logged in. run: agenthub login --base-url URL --api-key KEY")
            return 0
        key = cfg.get("api_key", "")
        masked = (key[:4] + "..." + key[-4:]) if len(key) > 8 else "***"
        print("base_url : %s" % cfg.get("base_url", ""))
        print("api_key  : %s" % masked)
        print("market   : %s" % (cfg.get("market") or config.DEFAULT_MARKET))
        return 0
    if args.command == "market":
        if args.market_command == "set":
            cfg["market"] = args.value
            config.save_config(cfg)
            print("market set to: %s" % args.value)
            return 0
        print(cfg.get("market") or config.DEFAULT_MARKET)
        return 0
    if args.command == "list":
        agents = resolve_market(cfg).list_agents()
        if not agents:
            print("no agents in market. put agent packages there, or run:")
            print("  agenthub market set <path>")
            print("current market: %s" % (cfg.get("market") or config.DEFAULT_MARKET))
            return 0
        for a in agents:
            print("%-20s %-8s %-12s %s" % (a.name, a.version, a.type, a.description))
        return 0
    if args.command == "info":
        path = resolve_market(cfg).get_package(args.name)
        spec = load_spec(path)
        print("name        : %s" % spec.name)
        print("version     : %s" % spec.version)
        print("author      : %s" % spec.author)
        print("type        : %s" % spec.type)
        print("description : %s" % spec.description)
        if spec.models:
            print("models      : %s" % ", ".join(spec.models))
        if spec.type == "prompt-pack":
            print("targets     : %s" % ", ".join(spec.targets))
        else:
            print("runtime     : %s" % spec.runtime_kind)
            print("entry       : %s" % spec.entry)
        return 0
    if args.command == "install":
        spec, record = do_install(args.name, cfg, force=args.force)
        print("installed %s v%s (%s)" % (spec.name, spec.version, spec.type))
        if spec.type == "prompt-pack":
            for inj in record["injected"]:
                print("  skill -> %-11s %s" % (inj["target"], inj["path"]))
            print("open your agent runtime and invoke the skill: %s" % spec.name)
        else:
            print("run it with: agenthub run %s [args...]" % spec.name)
        return 0
    if args.command == "uninstall":
        record = do_uninstall(args.name)
        print("removed %s (was v%s)" % (args.name, record.get("version", "")))
        return 0
    if args.command == "installed":
        data = config.load_installed()
        if not data:
            print("nothing installed.")
            return 0
        for name, rec in data.items():
            print("%-20s v%-8s %s" % (name, rec.get("version", ""), rec.get("type", "")))
        return 0
    if args.command == "run":
        return do_run(args.name, args.args, cfg)
    if args.command == "push":
        return do_push(args.dir, cfg, args.token)
    return 1


def do_push(package_dir, cfg, token):
    market = cfg.get("market") or config.DEFAULT_MARKET
    if not market.startswith(("http://", "https://")):
        raise RuntimeError("push requires a remote market (run: agenthub market set http://...)")
    package_dir = Path(package_dir).resolve()
    spec = load_spec(package_dir)
    token = token or cfg.get("upload_token", "")
    if not token:
        raise RuntimeError("upload token required (--token, or login --upload-token)")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(package_dir.rglob("*")):
            if not p.is_file():
                continue
            parts = set(p.parts)
            if ".venv" in parts or "__pycache__" in parts:
                continue
            zf.write(p, str(p.relative_to(package_dir)))
    req = urllib.request.Request(
        market.rstrip("/") + "/api/agents/" + spec.name,
        data=buf.getvalue(),
        method="PUT",
        headers={"Content-Type": "application/zip", "Authorization": "Bearer " + token},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode()).get("error", "")
        except Exception:
            detail = e.reason
        raise RuntimeError("push failed (HTTP %d): %s" % (e.code, detail))
    print("pushed %s v%s -> %s" % (spec.name, spec.version, result.get("url", market)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
