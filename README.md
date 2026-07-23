# Elite Discoveries

A first-discovery tracker for **Elite Dangerous** — log and manage your
first-discovery explorations, including SAA (surface area analysis) data,
atmospheric compositions, biological scans, and more.

*Built with [Claude Code](https://claude.com/claude-code).*

## Download

- **[Elite-Discoveries.exe](Elite%20Discoveries.exe)** — Windows standalone app (14 MB)
  No install, no Python required. Just download and run.

## Running

1. Download `Elite Discoveries.exe`
2. Double-click to launch — opens in a browser window
3. Select your commander from the drop-down (or add a new one)
4. Start exploring!

## Features

- Log first discoveries with EDSM / Inara integration
- Track SAA mappings and probe efficiency data
- View atmospheric / biological / geological / thargoid signal data
- Search and filter discoveries
- Export discovery data
- Multi-commander support (local profiles)
- Runs fully offline; data stored locally

## Build from source

Requires Python 3.10+.

```bash
cd src
pip install -r requirements.txt
python server.py
```

The server runs on `http://localhost:8765` — open that URL in your browser.

## Configuration

Create a `config.json` in the `src/` directory:

```json
{
  "commander": "Your Commander Name"
}
```

The app will store your first-discovery data locally. To sync with EDSM or Inara,
you'll need to configure your API keys in the Settings panel within the app.

## Tech

Python (Flask + Jinja2) server • HTML/CSS/JavaScript frontend • PyInstaller packaging

---

For issues, questions, or contributions, open an [issue](../../issues) or submit a PR.
