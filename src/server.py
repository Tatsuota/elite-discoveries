"""
Local web server for the Elite Dangerous First Discoveries tracker.

Standard library only. Parses your journals on startup, caches the result in
memory, and serves a single-page web UI plus a tiny JSON API:

    GET  /                -> the web UI
    GET  /api/data        -> cached discoveries (fast)
    GET  /api/refresh     -> re-scan journals, then return fresh data
    GET  /api/config      -> stored API settings (keys masked)
    POST /api/config      -> save Inara / EDSM / Frontier credentials
    GET  /api/cmdr        -> CMDR profile pulled from the configured providers
    GET  /oauth/login     -> start Frontier Companion API login (needs client_id)
    GET  /oauth/callback  -> Frontier OAuth redirect target

Run:  python server.py        (opens your browser automatically)
"""

from __future__ import annotations

import json
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import api_clients
import codex_parser
import frontier_oauth
import journal_parser


def _bundle_dir() -> str:
    """Where read-only assets (web/) live. PyInstaller extracts to _MEIPASS."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _data_dir() -> str:
    """Writable, persistent dir for config.json (survives exe rebuilds)."""
    if getattr(sys, "frozen", False):
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        d = os.path.join(base, "EliteDiscoveries")
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            return os.path.dirname(sys.executable)
        return d
    return os.path.dirname(os.path.abspath(__file__))


HERE = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(_bundle_dir(), "web")
CONFIG_PATH = os.path.join(_data_dir(), "config.json")
HOST = "127.0.0.1"
PORT = int(os.environ.get("ED_PORT", "8765"))
ACTUAL_PORT = PORT  # set once the server binds (OAuth redirect must match)

_CACHE: dict[str, dict] = {}       # commander (lower) -> journal first-discovery model
_CODEX_CACHE: dict[str, dict] = {} # commander (lower) -> codex model
_LOC_INDEX: dict | None = None     # visited-system coords + current location
_LOCK = threading.Lock()
_OAUTH: dict[str, str] = {}        # state -> PKCE verifier
_FRONTIER_PROFILE: dict | None = None
_AUTHENTICATED = False             # whether an optional CMDR profile is connected

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}


def load_data(commander: str, force: bool = False) -> dict:
    """Read the local journals for ONE commander (the attached one)."""
    key = (commander or "").strip().lower()
    with _LOCK:
        if force or key not in _CACHE:
            print(f"Scanning journals for CMDR {commander}...")
            data = journal_parser.load(commander=commander)
            # Upgrade systems holding Codex "Anomalies" entries to the pink group.
            # (Parse the codex here directly — _LOCK is not re-entrant.)
            if force or key not in _CODEX_CACHE:
                _CODEX_CACHE[key] = codex_parser.load_codex(commander=commander)
            anomaly_addrs = {
                e.get("systemAddress")
                for cat in _CODEX_CACHE[key].get("categories", [])
                if "anomal" in (cat.get("name") or "").lower()
                for e in cat.get("entries", [])
            }
            for s in data["systems"]:
                if s["category"] == "other" and s["address"] in anomaly_addrs:
                    s["category"] = "anomaly"
            _CACHE[key] = data
            t = data["totals"]
            print(f"  -> {t['systemsFirstDiscovered']} systems, "
                  f"{t['bodiesFirstDiscovered']} bodies first-discovered.")
        return _CACHE[key]


def location_index(force: bool = False) -> dict:
    """Visited-system coordinates + current system, cached per session."""
    global _LOC_INDEX
    with _LOCK:
        if force or _LOC_INDEX is None:
            _LOC_INDEX = journal_parser.build_location_index()
        return _LOC_INDEX


def load_codex_data(commander: str, force: bool = False) -> dict:
    """Read the local journals' Codex entries for ONE commander."""
    key = (commander or "").strip().lower()
    with _LOCK:
        if force or key not in _CODEX_CACHE:
            print(f"Scanning Codex for CMDR {commander}...")
            _CODEX_CACHE[key] = codex_parser.load_codex(commander=commander)
            print(f"  -> {_CODEX_CACHE[key]['totalEntries']} codex entries.")
        return _CODEX_CACHE[key]


# --------------------------------------------------------------------------- #
#  API credential storage (config.json, local only)
# --------------------------------------------------------------------------- #
def load_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_config(cfg: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)


def masked_config() -> dict:
    """Never echo secrets back to the browser — just whether they're set."""
    cfg = load_config()
    inara = cfg.get("inara", {})
    edsm = cfg.get("edsm", {})
    frontier = cfg.get("frontier", {})
    return {
        "commander": cfg.get("commander", ""),
        "inara": {"commander": inara.get("commander", ""), "hasKey": bool(inara.get("apiKey"))},
        "edsm": {"commander": edsm.get("commander", ""), "hasKey": bool(edsm.get("apiKey"))},
        "frontier": {"hasClientId": bool(frontier.get("clientId")),
                     "connected": _FRONTIER_PROFILE is not None},
    }


def session_commander() -> str:
    if _FRONTIER_PROFILE and _FRONTIER_PROFILE.get("commanderName"):
        return _FRONTIER_PROFILE["commanderName"]
    cfg = load_config()
    return (cfg.get("inara", {}).get("commander")
            or cfg.get("edsm", {}).get("commander") or "")


def update_config(incoming: dict) -> None:
    """Merge submitted fields; a blank key field keeps the stored one."""
    cfg = load_config()
    if "commander" in incoming:               # locally selected commander
        cfg["commander"] = (incoming.get("commander") or "").strip()
    for provider in ("inara", "edsm", "frontier"):
        if provider not in incoming:
            continue
        section = cfg.setdefault(provider, {})
        for k, v in incoming[provider].items():
            if k in ("apiKey", "clientId") and v == "":
                continue  # don't wipe a stored secret with a blank submit
            section[k] = v
    save_config(cfg)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):  # quiet console
        pass

    def _send_json(self, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path):
        ext = os.path.splitext(path)[1].lower()
        try:
            with open(path, "rb") as fh:
                body = fh.read()
        except OSError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", _CONTENT_TYPES.get(ext, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location):
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()

    def _read_body_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    def do_POST(self):
        route = self.path.split("?", 1)[0]
        if route == "/api/config":
            update_config(self._read_body_json())
            self._send_json({"ok": True, "config": masked_config()})
            return
        self.send_error(404)

    def do_GET(self):
        parsed = urlparse(self.path)
        route = parsed.path

        if route == "/api/data":
            self._send_json(self._gated_data(force=False))
            return
        if route == "/api/refresh":
            self._send_json(self._gated_data(force=True))
            return
        if route == "/api/status":
            self._send_json({"authenticated": _AUTHENTICATED,
                             "commander": session_commander()})
            return
        if route == "/api/codex":
            cmdr = (load_config().get("commander") or "").strip()
            if not cmdr:
                self._send_json({"needsCommander": True})
            else:
                self._send_json(load_codex_data(cmdr, force="refresh" in parsed.query))
            return
        if route == "/api/commanders":
            self._send_json(journal_parser.list_commanders())
            return
        if route == "/api/locate":
            q = parse_qs(parsed.query)
            idx = location_index(force="refresh" in q)
            if q.get("current"):
                cur = idx["current"]
                hit = idx["coords"].get((cur or "").strip().lower()) if cur else None
                self._send_json({"ok": bool(hit), "name": cur, "pos": hit and hit["pos"],
                                 "error": None if hit else "No current location found in your journals."})
            else:
                name = (q.get("name") or [""])[0].strip()
                hit = idx["coords"].get(name.lower()) if name else None
                self._send_json({"ok": bool(hit), "name": hit["name"] if hit else name,
                                 "pos": hit and hit["pos"],
                                 "error": None if hit else
                                 "System not found in your flight logs (only visited systems have known coordinates)."})
            return
        if route == "/api/config":
            self._send_json(masked_config())
            return
        if route == "/api/cmdr":
            self._send_json(self._commander_payload())
            return
        if route == "/oauth/login":
            self._oauth_login()
            return
        if route == "/oauth/callback":
            self._oauth_callback(parse_qs(parsed.query))
            return

        # Static files (default to index.html).
        rel = "index.html" if route in ("/", "") else route.lstrip("/")
        target = os.path.normpath(os.path.join(WEB_DIR, rel))
        if not target.startswith(WEB_DIR):  # path-traversal guard
            self.send_error(403)
            return
        if not os.path.isfile(target):
            self.send_error(404)
            return
        self._send_file(target)

    # -- discovery data gate ------------------------------------------------ #
    def _gated_data(self, force: bool) -> dict:
        """Read the journals only once a commander has been selected, and only
        for that commander (the journal folder may hold several characters)."""
        cmdr = (load_config().get("commander") or "").strip()
        if not cmdr:
            return {"needsCommander": True}
        return load_data(cmdr, force=force)

    # -- commander profile (drives the gate) -------------------------------- #
    def _commander_payload(self) -> dict:
        global _AUTHENTICATED
        cfg = load_config()
        result = api_clients.fetch_commander(cfg)
        if _FRONTIER_PROFILE:
            # Frontier (live cAPI) data wins where present.
            result.setdefault("providers", {})["frontier"] = {"ok": True}
            for k, v in _FRONTIER_PROFILE.items():
                if v not in (None, ""):
                    result.setdefault("profile", {})[k] = v
            result["ok"] = True
        if result.get("ok"):
            _AUTHENTICATED = True   # unlock the discovery log for this session
        return result

    # -- Frontier OAuth ----------------------------------------------------- #
    def _oauth_login(self):
        client_id = (load_config().get("frontier", {}) or {}).get("clientId", "")
        if not client_id:
            self._redirect("/?frontier=noclientid")
            return
        flow = frontier_oauth.begin(client_id, HOST, ACTUAL_PORT)
        _OAUTH[flow["state"]] = flow["verifier"]
        self._redirect(flow["authUrl"])

    def _oauth_callback(self, params):
        global _FRONTIER_PROFILE, _AUTHENTICATED
        state = (params.get("state") or [""])[0]
        code = (params.get("code") or [""])[0]
        verifier = _OAUTH.pop(state, None)
        if not code or verifier is None:
            self._redirect("/?frontier=denied")
            return
        client_id = (load_config().get("frontier", {}) or {}).get("clientId", "")
        try:
            tok = frontier_oauth.exchange_code(client_id, code, verifier, HOST, ACTUAL_PORT)
            raw = frontier_oauth.fetch_profile(tok.get("access_token", ""))
            _FRONTIER_PROFILE = frontier_oauth.normalise_profile(raw)
            _AUTHENTICATED = True   # Frontier login unlocks the discovery log
            self._redirect("/?frontier=connected")
        except RuntimeError:
            self._redirect("/?frontier=error")


def _make_server() -> ThreadingHTTPServer:
    """Bind to PORT, or fall back to the next free port if it's taken."""
    for port in range(PORT, PORT + 20):
        try:
            return ThreadingHTTPServer((HOST, port), Handler)
        except OSError:
            continue
    # last resort: let the OS pick any free port
    return ThreadingHTTPServer((HOST, 0), Handler)


def serve_in_thread() -> tuple[ThreadingHTTPServer, int]:
    """Start the server on a daemon thread and return (server, port).

    Used by the standalone desktop client (desktop.py), which owns the window
    and shuts the server down when that window closes.
    """
    global ACTUAL_PORT
    srv = _make_server()
    ACTUAL_PORT = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, ACTUAL_PORT


def main():
    global ACTUAL_PORT
    # Discoveries are fetched from EDSM on demand (after a CMDR connects),
    # so there's nothing to warm up here.
    server = _make_server()
    ACTUAL_PORT = server.server_address[1]
    url = f"http://{HOST}:{ACTUAL_PORT}/"
    print(f"\nElite Discoveries running at {url}")
    print("Leave this window open. Press Ctrl+C to stop.\n")
    # The desktop client opens its own app window, so it sets ED_NO_BROWSER.
    if not os.environ.get("ED_NO_BROWSER"):
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.shutdown()


if __name__ == "__main__":
    main()
