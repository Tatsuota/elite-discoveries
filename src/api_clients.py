"""
External API hooks for Elite Discoveries.

Lets a user plug in their own credentials to pull their CMDR profile from
third-party services and overlay it on the journal-based discovery data:

  * Inara   — user's personal API key (Settings -> API keys on inara.cz).
              Mirrors how tools like EDMC talk to Inara.
  * EDSM    — user's API key (Settings -> API on edsm.net). Bonus provider;
              more discovery-relevant (ranks, credits, position).

Frontier's Companion API (the OAuth "login" Inara itself uses to import data)
lives in `frontier_oauth.py` — it needs a Frontier-issued client_id, so it is
opt-in and documented separately.

Standard library only (urllib). All calls are user-initiated.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

APP_NAME = "Elite Discoveries"
APP_VERSION = "1.1"
_TIMEOUT = 15


def _post_json(url: str, payload: dict, headers: dict | None = None) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


# --------------------------------------------------------------------------- #
#  Inara
# --------------------------------------------------------------------------- #
INARA_ENDPOINT = "https://inara.cz/inapi/v1/"


def inara_commander_profile(api_key: str, commander_name: str,
                            search_name: str | None = None) -> dict:
    """
    Fetch a commander's public Inara profile.

    Returns a normalised dict: {ok, source, error?, profile?}
    """
    if not api_key or not commander_name:
        return {"ok": False, "source": "inara", "error": "Missing Inara API key or CMDR name."}

    payload = {
        "header": {
            "appName": APP_NAME,
            "appVersion": APP_VERSION,
            "isBeingDeveloped": False,
            "APIkey": api_key.strip(),
            "commanderName": commander_name.strip(),
            "commanderFrontierID": "",
        },
        "events": [{
            "eventName": "getCommanderProfile",
            "eventTimestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "eventData": {"searchName": (search_name or commander_name).strip()},
        }],
    }

    try:
        resp = _post_json(INARA_ENDPOINT, payload)
    except urllib.error.HTTPError as e:
        return {"ok": False, "source": "inara", "error": f"HTTP {e.code} from Inara."}
    except urllib.error.URLError as e:
        return {"ok": False, "source": "inara", "error": f"Network error: {e.reason}"}
    except (ValueError, json.JSONDecodeError):
        return {"ok": False, "source": "inara", "error": "Invalid response from Inara."}

    header = resp.get("header", {})
    if header.get("eventStatus") != 200:
        return {"ok": False, "source": "inara",
                "error": header.get("eventStatusText") or "Inara authorisation failed."}

    events = resp.get("events", [])
    if not events:
        return {"ok": False, "source": "inara", "error": "No commander data returned."}

    ev = events[0]
    if ev.get("eventStatus") == 204:
        return {"ok": False, "source": "inara", "error": "Commander not found on Inara."}
    if ev.get("eventStatus") not in (200, 202):
        return {"ok": False, "source": "inara",
                "error": ev.get("eventStatusText") or "Inara returned an error."}

    return {"ok": True, "source": "inara", "profile": _normalise_inara(ev.get("eventData", {}))}


def _normalise_inara(d: dict) -> dict:
    ranks = []
    for r in d.get("commanderRanksPilot", []) or []:
        ranks.append({
            "name": r.get("rankName", "").title(),
            "value": r.get("rankValue"),
            "progress": r.get("rankProgress"),
        })
    sq = d.get("commanderSquadron") or {}
    ship = d.get("commanderMainShip") or {}
    return {
        "commanderName": d.get("commanderName"),
        "ranks": ranks,
        "allegiance": d.get("preferredAllegianceName"),
        "power": d.get("preferredPowerName"),
        "gameRole": d.get("preferredGameRole"),
        "squadron": sq.get("SquadronName"),
        "squadronRank": sq.get("SquadronMemberRank"),
        "squadronUrl": sq.get("inaraURL"),
        "mainShip": ship.get("shipType"),
        "mainShipName": ship.get("shipName"),
        "avatarUrl": d.get("avatarImageURL"),
        "profileUrl": d.get("inaraURL"),
    }


# --------------------------------------------------------------------------- #
#  EDSM  (bonus provider)
# --------------------------------------------------------------------------- #
def edsm_commander_profile(api_key: str, commander_name: str) -> dict:
    if not commander_name:
        return {"ok": False, "source": "edsm", "error": "Missing EDSM CMDR name."}

    base = "https://www.edsm.net/api-commander-v1"
    cmdr = commander_name.strip()
    key = (api_key or "").strip()
    q = lambda path, extra="": (
        f"{base}/{path}?commanderName={urllib.parse.quote(cmdr)}"
        + (f"&apiKey={urllib.parse.quote(key)}" if key else "")
        + extra
    )

    # get-ranks works for any public profile (no key needed) -> the primary call.
    try:
        ranks = _get_json(q("get-ranks"))
    except urllib.error.HTTPError as e:
        return {"ok": False, "source": "edsm", "error": f"HTTP {e.code} from EDSM."}
    except urllib.error.URLError as e:
        return {"ok": False, "source": "edsm", "error": f"Network error: {e.reason}"}
    except (ValueError, json.JSONDecodeError):
        return {"ok": False, "source": "edsm", "error": "Invalid response from EDSM."}

    msgnum = ranks.get("msgnum")
    if msgnum == 203:
        return {"ok": False, "source": "edsm",
                "error": "Commander not found on EDSM (profile must be public, or add an API key)."}
    if msgnum not in (100, None):
        return {"ok": False, "source": "edsm",
                "error": ranks.get("msg") or "EDSM returned an error."}

    rank_verbose = ranks.get("ranksVerbose", {}) or {}
    rank_prog = ranks.get("progress", {}) or {}
    norm_ranks = [{"name": k, "title": v, "progress": rank_prog.get(k)}
                  for k, v in rank_verbose.items()]

    # credits + position need the API key; treat them as best-effort enrichment.
    balance, system, coords = None, None, None
    if key:
        try:
            cr_hist = (_get_json(q("get-credits")).get("credits") or [])
            balance = cr_hist[0].get("balance") if cr_hist else None
        except Exception:
            pass
        try:
            pos = _get_json(q("get-position", "&showCoordinates=1"))
            system, coords = pos.get("system"), pos.get("coordinates")
        except Exception:
            pass

    return {"ok": True, "source": "edsm", "profile": {
        "commanderName": cmdr,
        "ranks": norm_ranks,
        "credits": balance,
        "system": system,
        "coords": coords,
        "profileUrl": f"https://www.edsm.net/en/user/profile/cmdr/{urllib.parse.quote(cmdr)}",
    }}


# --------------------------------------------------------------------------- #
#  Aggregator used by the server
# --------------------------------------------------------------------------- #
def fetch_commander(config: dict) -> dict:
    """Pull whatever providers are configured and merge into one payload."""
    out = {"providers": {}, "profile": {}}

    inara = config.get("inara") or {}
    if inara.get("apiKey") and inara.get("commander"):
        res = inara_commander_profile(inara["apiKey"], inara["commander"])
        out["providers"]["inara"] = {"ok": res["ok"], "error": res.get("error")}
        if res["ok"]:
            out["profile"].update({k: v for k, v in res["profile"].items() if v})

    edsm = config.get("edsm") or {}
    if edsm.get("commander"):
        res = edsm_commander_profile(edsm.get("apiKey", ""), edsm["commander"])
        out["providers"]["edsm"] = {"ok": res["ok"], "error": res.get("error")}
        if res["ok"]:
            # don't let EDSM clobber a richer Inara profile; only fill gaps
            for k, v in res["profile"].items():
                if v and not out["profile"].get(k):
                    out["profile"][k] = v
            if res["profile"].get("credits") is not None:
                out["profile"]["credits"] = res["profile"]["credits"]
            if res["profile"].get("system"):
                out["profile"]["system"] = res["profile"]["system"]

    out["ok"] = bool(out["profile"])
    if not out["providers"]:
        out["error"] = "No API providers configured."
    return out
