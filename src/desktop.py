"""
Elite Discoveries — desktop application.

Runs the local API server in the background and shows the app in a real,
self-contained window. When you close the window, the server shuts down too.

Windowing strategy (first that works wins):
  1. A native OS window via pywebview / Edge WebView2 — a true application
     window with its own taskbar entry, no browser involved.
  2. A Chromium "app-mode" window (Chrome/Edge/Brave/Opera/Vivaldi).
  3. Your default browser.

Run:  pythonw desktop.py   (no console)   or   python desktop.py   (with console)
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import subprocess
import urllib.request

# The server must NOT open the default browser — this client owns the window.
os.environ.setdefault("ED_NO_BROWSER", "1")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import server  # noqa: E402  (after sys.path tweak)

WINDOW_SIZE = "1180,840"


# --------------------------------------------------------------------------- #
#  Native application window (pywebview / Edge WebView2)
# --------------------------------------------------------------------------- #
def run_native_window(url: str) -> bool:
    """Open a real OS window. Returns True if it ran (and has now closed),
    False if pywebview / a backend isn't available so we should fall back."""
    try:
        import webview
    except Exception:
        return False
    try:
        webview.create_window(
            "Elite Discoveries", url,
            width=1200, height=840, min_size=(900, 620),
            background_color="#262624",
        )
        webview.start()          # blocks until the window is closed
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------- #
#  Find a Chromium browser (fallback app-mode windows)
# --------------------------------------------------------------------------- #
def _candidate_paths() -> dict[str, list[str]]:
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pfx86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    lad = os.environ.get("LOCALAPPDATA", "")
    return {
        "Chrome": [rf"{pf}\Google\Chrome\Application\chrome.exe",
                   rf"{pfx86}\Google\Chrome\Application\chrome.exe",
                   rf"{lad}\Google\Chrome\Application\chrome.exe"],
        "MSEdge": [rf"{pfx86}\Microsoft\Edge\Application\msedge.exe",
                   rf"{pf}\Microsoft\Edge\Application\msedge.exe"],
        "Brave":  [rf"{pf}\BraveSoftware\Brave-Browser\Application\brave.exe",
                   rf"{pfx86}\BraveSoftware\Brave-Browser\Application\brave.exe"],
        "Opera":  [rf"{lad}\Programs\Opera\opera.exe"],
        "Vivaldi": [rf"{lad}\Vivaldi\Application\vivaldi.exe"],
    }


def _default_browser_progid() -> str:
    try:
        import winreg
        key = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            return winreg.QueryValueEx(k, "ProgId")[0] or ""
    except OSError:
        return ""


def find_browser() -> str | None:
    cands = _candidate_paths()
    progid = _default_browser_progid()
    # Prefer the user's default browser if it's Chromium-based.
    for name, paths in cands.items():
        if name.lower() in progid.lower():
            for p in paths:
                if os.path.isfile(p):
                    return p
    # Otherwise the first Chromium browser we can find.
    for paths in cands.values():
        for p in paths:
            if os.path.isfile(p):
                return p
    return None


# --------------------------------------------------------------------------- #
#  Wait for the server to accept connections
# --------------------------------------------------------------------------- #
def _wait_until_up(url: str, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except OSError:
            time.sleep(0.15)
    return False


# --------------------------------------------------------------------------- #
def main() -> None:
    srv, port = server.serve_in_thread()
    url = f"http://127.0.0.1:{port}/"
    _wait_until_up(url)

    # Headless mode (used to verify a packaged build): run the server, no window.
    if os.environ.get("ED_NO_WINDOW"):
        print(f"Elite Discoveries serving at {url} (headless).")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        srv.shutdown()
        return

    # 1) A real native application window (unless explicitly disabled).
    if not os.environ.get("ED_NO_NATIVE") and run_native_window(url):
        srv.shutdown()
        return

    # 2) Chromium app-mode window.
    browser = find_browser()
    if browser:
        # A dedicated profile dir makes this its own browser instance, so the
        # process stays in the foreground and `wait()` returns on window close.
        profile = os.path.join(tempfile.gettempdir(), "EliteDiscoveriesApp")
        try:
            proc = subprocess.Popen([
                browser,
                f"--app={url}",
                f"--user-data-dir={profile}",
                f"--window-size={WINDOW_SIZE}",
                "--no-first-run",
                "--no-default-browser-check",
            ])
            proc.wait()           # block until the app window is closed
        except OSError:
            browser = None        # fall through to the default-browser path

    # 3) Default browser.
    if not browser:
        import webbrowser
        webbrowser.open(url)
        print(f"Elite Discoveries running at {url}\nClose this window to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass

    srv.shutdown()


if __name__ == "__main__":
    main()
