import html
import io
import json
import os
import sqlite3
import sys
import tempfile
import time
import uuid
import zipfile
from pathlib import Path

from flask import Flask, Response, abort, jsonify, request

sys.path.insert(0, str(Path(__file__).parent))
from agenthub.spec import SpecError, load_manifest, load_spec, spec_from_dict

DATA_DIR = Path(os.environ.get("AGENTHUB_SERVER_DATA", Path(__file__).parent / "data"))
DB_PATH = DATA_DIR / "market.db"
PKG_DIR = DATA_DIR / "packages"
UPLOAD_TOKEN = os.environ.get("AGENTHUB_UPLOAD_TOKEN", "dev-token")
PUBLIC_URL = os.environ.get("AGENTHUB_PUBLIC_URL", "http://127.0.0.1:18766").rstrip("/")
PORT = int(os.environ.get("AGENTHUB_PORT", "18766"))

app = Flask(__name__)


def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PKG_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute(
        """CREATE TABLE IF NOT EXISTS agents (
            name TEXT PRIMARY KEY,
            version TEXT NOT NULL,
            spec TEXT NOT NULL,
            downloads INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        )"""
    )
    con.commit()
    return con


def _safe_extract(zf, dest):
    dest = Path(dest).resolve()
    for member in zf.namelist():
        target = (dest / member).resolve()
        if target != dest and not str(target).startswith(str(dest) + os.sep):
            raise SpecError("invalid zip member path: %s" % member)
    zf.extractall(dest)


@app.get("/api/agents")
def api_list():
    con = init_db()
    rows = con.execute("SELECT spec, downloads FROM agents ORDER BY downloads DESC, updated_at DESC").fetchall()
    con.close()
    agents = []
    for spec_text, downloads in rows:
        d = json.loads(spec_text)
        d["downloads"] = downloads
        agents.append(d)
    return jsonify({"agents": agents})


@app.get("/api/agents/<name>")
def api_detail(name):
    con = init_db()
    row = con.execute(
        "SELECT version, spec, downloads, updated_at FROM agents WHERE name = ?", (name,)
    ).fetchone()
    con.close()
    if row is None:
        abort(404)
    d = json.loads(row[1])
    d["downloads"] = row[2]
    d["updated_at"] = row[3]
    return jsonify(d)


@app.put("/api/agents/<name>")
def api_upload(name):
    auth = request.headers.get("Authorization", "")
    if auth != "Bearer " + UPLOAD_TOKEN:
        return jsonify({"error": "invalid upload token"}), 401
    body = request.get_data()
    if not body:
        return jsonify({"error": "empty body, expected a zip package"}), 400
    try:
        zf = zipfile.ZipFile(io.BytesIO(body))
    except zipfile.BadZipFile:
        return jsonify({"error": "body is not a valid zip"}), 400
    with tempfile.TemporaryDirectory() as td:
        dest = Path(td)
        try:
            _safe_extract(zf, dest)
            spec = load_spec(dest)
            manifest = load_manifest(dest)
        except SpecError as e:
            return jsonify({"error": str(e)}), 400
        if spec.name != name:
            return jsonify({"error": "package name mismatch: agent.yaml says %r" % spec.name}), 400
    PKG_DIR.mkdir(parents=True, exist_ok=True)
    tmp_pkg = PKG_DIR / (name + ".zip." + uuid.uuid4().hex + ".tmp")
    tmp_pkg.write_bytes(body)
    os.replace(tmp_pkg, PKG_DIR / (name + ".zip"))
    con = init_db()
    con.execute(
        """INSERT INTO agents (name, version, spec, downloads, updated_at)
           VALUES (?, ?, ?, 0, ?)
           ON CONFLICT(name) DO UPDATE SET
             version=excluded.version, spec=excluded.spec, updated_at=excluded.updated_at""",
        (name, spec.version, json.dumps(manifest, ensure_ascii=False), time.strftime("%Y-%m-%d %H:%M:%S")),
    )
    con.commit()
    con.close()
    return jsonify({"ok": True, "url": PUBLIC_URL + "/api/agents/" + name})


@app.get("/api/download/<name>")
def api_download(name):
    pkg = PKG_DIR / (name + ".zip")
    if not pkg.is_file():
        abort(404)
    con = init_db()
    con.execute("UPDATE agents SET downloads = downloads + 1 WHERE name = ?", (name,))
    con.commit()
    con.close()
    return Response(
        pkg.read_bytes(),
        mimetype="application/zip",
        headers={"Content-Disposition": "attachment; filename=%s.zip" % name},
    )


def _require_agent(name):
    con = init_db()
    row = con.execute("SELECT 1 FROM agents WHERE name = ?", (name,)).fetchone()
    con.close()
    if row is None:
        abort(404)


@app.get("/install/<name>.bat")
def install_bat(name):
    _require_agent(name)
    content = "\r\n".join(
        [
            "@echo off",
            "chcp 65001 >nul",
            "echo === AgentHub one-click install: %s ===" % name,
            "python --version >nul 2>&1",
            "if errorlevel 1 (",
            "  echo [ERROR] Python not found. Install Python 3.9+ from https://www.python.org/downloads/ first.",
            "  pause",
            "  exit /b 1",
            ")",
            "pip install --quiet agenthub-cli",
            "agenthub market set %s" % PUBLIC_URL,
            "agenthub install %s" % name,
            "echo.",
            "echo === %s installed! ===" % name,
            "pause",
        ]
    )
    return Response(
        content,
        mimetype="text/plain",
        headers={"Content-Disposition": "attachment; filename=%s.bat" % name},
    )


@app.get("/install/<name>.sh")
def install_sh(name):
    _require_agent(name)
    content = "\n".join(
        [
            "#!/usr/bin/env bash",
            "set -e",
            "echo '=== AgentHub one-click install: %s ==='" % name,
            "command -v python3 >/dev/null || { echo '[ERROR] python3 is required'; exit 1; }",
            "pip install --quiet agenthub-cli",
            "agenthub market set %s" % PUBLIC_URL,
            "agenthub install %s" % name,
            "echo '=== %s installed! ==='" % name,
        ]
    )
    return Response(
        content,
        mimetype="text/plain",
        headers={"Content-Disposition": "attachment; filename=%s.sh" % name},
    )


PAGE_HEAD = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>AgentHub 市场</title>
<style>
body { font-family: system-ui, "Segoe UI", sans-serif; background: #0f1117; color: #e6e6e6; max-width: 960px; margin: 0 auto; padding: 32px 20px; }
h1 { font-size: 28px; }
.sub { color: #9aa0ae; margin-bottom: 32px; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.card { background: #171a23; border: 1px solid #262b38; border-radius: 10px; padding: 18px; }
.card h2 { margin: 0 0 6px; font-size: 18px; }
.meta { color: #9aa0ae; font-size: 13px; margin-bottom: 10px; }
.desc { font-size: 14px; line-height: 1.5; margin-bottom: 14px; }
pre { background: #0b0d12; border: 1px solid #262b38; border-radius: 6px; padding: 10px; font-size: 12px; overflow-x: auto; }
.btns { display: flex; gap: 10px; margin-top: 10px; flex-wrap: wrap; }
.btns a { display: inline-block; padding: 8px 14px; border-radius: 6px; font-size: 14px; text-decoration: none; }
.primary { background: #3b82f6; color: #fff; }
.ghost { border: 1px solid #3b82f6; color: #3b82f6; }
.tag { display: inline-block; background: #262b38; border-radius: 4px; padding: 2px 8px; font-size: 12px; margin-right: 6px; }
</style>
</head>
<body>
<h1>AgentHub 市场</h1>
<p class="sub">一键安装 agent，LLM 调用自动经中转站计费</p>
<div class="grid">
"""

PAGE_TAIL = "\n</div>\n</body>\n</html>\n"


def _card(d, downloads):
    name = html.escape(str(d.get("name", "")))
    desc = html.escape(str(d.get("description", "")))
    version = html.escape(str(d.get("version", "")))
    author = html.escape(str(d.get("author", "")))
    atype = html.escape(str(d.get("type", "")))
    models = html.escape(", ".join(d.get("models") or []))
    usage = (
        "agenthub run %s [args...]" % name
        if d.get("type") == "program"
        else "open comagic / claude-code and invoke the skill"
    )
    return """
<div class="card">
  <h2>%(name)s <span class="tag">%(atype)s</span></h2>
  <div class="meta">v%(version)s · by %(author)s · %(models)s · %(downloads)d downloads</div>
  <div class="desc">%(desc)s</div>
  <pre>agenthub market set %(url)s
agenthub install %(name)s

# usage
%(usage)s</pre>
  <div class="btns">
    <a class="primary" href="/install/%(name)s.bat">Windows 一键安装 (.bat)</a>
    <a class="ghost" href="/install/%(name)s.sh">Mac/Linux (.sh)</a>
  </div>
</div>""" % {
        "name": name,
        "atype": atype,
        "version": version,
        "author": author,
        "models": models,
        "downloads": downloads,
        "desc": desc,
        "url": html.escape(PUBLIC_URL),
        "usage": html.escape(usage),
    }


@app.get("/")
def index():
    con = init_db()
    rows = con.execute("SELECT spec, downloads FROM agents ORDER BY downloads DESC, updated_at DESC").fetchall()
    con.close()
    cards = []
    for spec_text, downloads in rows:
        cards.append(_card(json.loads(spec_text), downloads))
    body = "\n".join(cards)
    if not body:
        body = '<div class="card"><div class="desc">市场还是空的。创作者上传第一个 agent：<pre>agenthub push ./my-agent --token YOUR_TOKEN</pre></div></div>'
    return PAGE_HEAD + body + PAGE_TAIL


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=PORT)
