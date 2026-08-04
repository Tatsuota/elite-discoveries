"""
EDSM-backed discovery data source.

This replaces the local journal parser: instead of reading the game's Saved Games
folder, the first-discovery log is pulled entirely from the EDSM API for the
configured commander.

  * System list  -> api-logs-v1/get-logs  (needs the CMDR's API key; each log
                    entry has a `firstDiscover` flag — we keep the true ones).
  * Body detail  -> api-system-v1/bodies  (public; each body carries a
                    `discovery.commander`, so we mark the ones this CMDR found).

Body details load lazily per system (on expand) to stay within EDSM's rate limit
(~360 requests/hour). Pure formatting/colour helpers are reused from
journal_parser, but no journal files are ever read here.

Standard library only.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from journal_parser import star_color, planet_palette, estimate_body_value

_TIMEOUT = 25
_UA = "Elite Discoveries/2.0"

LOGS_URL = "https://www.edsm.net/api-logs-v1/get-logs"
BODIES_URL = "https://www.edsm.net/api-system-v1/bodies"


def _get_json(url: str, params: dict) -> dict:
    qs = urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
    req = urllib.request.Request(f"{url}?{qs}", headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


# --------------------------------------------------------------------------- #
#  System list  (api-logs-v1/get-logs)
# --------------------------------------------------------------------------- #
def get_first_discovered_systems(api_key: str, commander: str) -> dict:
    """
    Return every system this commander was the FIRST to discover, newest first.

    {ok, error?, commander, generatedAt, systems:[{address,name,firstDiscovered,
     discoveredAt}]}
    """
    if not api_key or not commander:
        return {"ok": False, "error": "Connect EDSM (API key + CMDR name) to load your discoveries.",
                "systems": []}

    seen: dict[str, dict] = {}
    end_dt = None
    try:
        for _ in range(40):  # paginate backwards; cap to avoid runaway
            data = _get_json(LOGS_URL, {
                "commanderName": commander, "apiKey": api_key, "endDateTime": end_dt,
            })
            msg = data.get("msgnum")
            if msg == 202:
                return {"ok": False, "error": "EDSM rejected the API key (missing/invalid).", "systems": []}
            if msg == 203:
                return {"ok": False, "error": "Commander not found on EDSM, or key doesn't match the CMDR.",
                        "systems": []}
            if msg not in (100, None):
                return {"ok": False, "error": data.get("msg") or "EDSM error.", "systems": []}

            logs = data.get("logs") or []
            if not logs:
                break

            oldest = None
            new_rows = 0
            for entry in logs:
                name = entry.get("system")
                date = entry.get("date")
                if not name:
                    continue
                if oldest is None or (date and date < oldest):
                    oldest = date
                cur = seen.get(name)
                if cur is None:
                    seen[name] = {
                        "address": entry.get("systemId64") or entry.get("systemId"),
                        "name": name,
                        "firstDiscovered": bool(entry.get("firstDiscover")),
                        "discoveredAt": date,
                    }
                    new_rows += 1
                else:
                    if entry.get("firstDiscover"):
                        cur["firstDiscovered"] = True
                    if date and (not cur["discoveredAt"] or date < cur["discoveredAt"]):
                        cur["discoveredAt"] = date  # earliest visit

            # advance the window; stop when we can't go further back
            if not oldest or oldest == end_dt:
                break
            end_dt = oldest
    except urllib.error.HTTPError as e:
        if e.code == 400:
            return {"ok": False, "error": "EDSM rejected the request (check API key / CMDR name).", "systems": []}
        return {"ok": False, "error": f"HTTP {e.code} from EDSM.", "systems": []}
    except urllib.error.URLError as e:
        return {"ok": False, "error": f"Network error reaching EDSM: {e.reason}", "systems": []}
    except (ValueError, json.JSONDecodeError):
        return {"ok": False, "error": "Invalid response from EDSM.", "systems": []}

    systems = [s for s in seen.values() if s["firstDiscovered"]]
    systems.sort(key=lambda s: (s["discoveredAt"] or ""), reverse=True)
    return {
        "ok": True,
        "commander": commander,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "source": "edsm",
        "systems": systems,
    }


# --------------------------------------------------------------------------- #
#  System detail  (api-system-v1/bodies)
# --------------------------------------------------------------------------- #
def get_system_detail(system_name: str, commander: str) -> dict:
    """Fetch + normalise the bodies of one system, marking this CMDR's finds."""
    try:
        data = _get_json(BODIES_URL, {"systemName": system_name})
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code} from EDSM."}
    except urllib.error.URLError as e:
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except (ValueError, json.JSONDecodeError):
        return {"ok": False, "error": "Invalid response from EDSM."}

    raw_bodies = data.get("bodies") or []
    cmdr = (commander or "").strip().lower()
    sysname = data.get("name") or system_name
    bodies = [_body(b, cmdr, sysname) for b in raw_bodies]
    bodies.sort(key=lambda b: (b["bodyId"] if b["bodyId"] is not None else 9999))

    fd = [b for b in bodies if b["firstDiscovered"]]
    stars = [b for b in bodies if b["type"] == "star"]
    main_star = min(stars, key=lambda b: (b["bodyId"] or 0)) if stars else None

    return {"ok": True, "system": {
        "name": data.get("name") or system_name,
        "address": data.get("id64"),
        "scannedCount": len(bodies),
        "bodyCount": len(bodies),
        "firstDiscoveredCount": len(fd),
        "firstMappedCount": 0,
        "firstFootfallCount": 0,
        "systemFirstDiscovered": bool(main_star and main_star["firstDiscovered"]),
        "estimatedValue": sum(b["estimatedValue"] for b in bodies),
        "mainStarColor": main_star["color"] if main_star else None,
        "flags": {
            "earthlike": any(b.get("planetClass") == "Earthlike body" for b in bodies),
            "waterWorld": any(b.get("planetClass") == "Water world" for b in bodies),
            "ammonia": any(b.get("planetClass") == "Ammonia world" for b in bodies),
            "terraformable": any(b.get("terraformable") for b in bodies),
            "bio": False,
        },
        "bodies": bodies,
    }}


# --------------------------------------------------------------------------- #
#  Normalisation: EDSM body  ->  the UI's body model
# --------------------------------------------------------------------------- #
_PLANET_CLASS = {
    "earth-like world": "Earthlike body",
    "water world": "Water world",
    "water giant": "Water giant",
    "ammonia world": "Ammonia world",
    "metal-rich body": "Metal rich body",
    "high metal content world": "High metal content body",
    "rocky body": "Rocky body",
    "rocky ice world": "Rocky ice body",
    "icy body": "Icy body",
    "class i gas giant": "Sudarsky class I gas giant",
    "class ii gas giant": "Sudarsky class II gas giant",
    "class iii gas giant": "Sudarsky class III gas giant",
    "class iv gas giant": "Sudarsky class IV gas giant",
    "class v gas giant": "Sudarsky class V gas giant",
    "helium-rich gas giant": "Helium rich gas giant",
    "helium gas giant": "Helium rich gas giant",
    "gas giant with water-based life": "Gas giant with water based life",
    "gas giant with ammonia-based life": "Gas giant with ammonia based life",
    "water giant with life": "Water giant",
}

_STAR_VALUE_K = {"D": 14057, "N": 22628, "H": 22628}


def _planet_class(sub_type: str) -> str:
    return _PLANET_CLASS.get((sub_type or "").strip().lower(), sub_type or "Rocky body")


def _star_type(body: dict) -> tuple[str, str | None]:
    """Return (starType letter, subclass) from EDSM star fields."""
    spec = body.get("spectralClass")
    if spec:
        letter = spec[0]
        subclass = spec[1:] or None
        return letter, subclass
    sub = (body.get("subType") or "").lower()
    if "neutron" in sub:
        return "N", None
    if "black hole" in sub:
        return "H", None
    if "white dwarf" in sub:
        return "D", None
    if "wolf-rayet" in sub:
        return "W", None
    if "t tauri" in sub:
        return "TTS", None
    first = (body.get("subType") or "?")[0]
    return (first if first.isalpha() else "?"), None


def _comp_list(comp: dict | None):
    if not comp:
        return None
    return [{"Name": k, "Percent": v} for k, v in comp.items()]


def _rings(body: dict):
    rings = (body.get("rings") or []) + (body.get("belts") or [])
    if not rings:
        return None
    return [{
        "name": r.get("name"),
        "class": (r.get("type") or ""),
        "massMT": r.get("mass"),
        "innerRad": r.get("innerRadius"),
        "outerRad": r.get("outerRadius"),
    } for r in rings]


def _body(b: dict, cmdr_lower: str, system_name: str = "") -> dict:
    btype_raw = (b.get("type") or "").lower()
    disc = b.get("discovery") or {}
    disc_cmdr = (disc.get("commander") or "").strip().lower()
    first_disc = bool(cmdr_lower and disc_cmdr == cmdr_lower)
    name = b.get("name", "")

    body = {
        "bodyId": b.get("bodyId"),
        "name": name,
        "shortName": _short(name, system_name),
        "timestamp": disc.get("date"),
        "distanceLS": b.get("distanceToArrival"),
        "wasDiscovered": not first_disc,
        "wasMapped": True,
        "firstDiscovered": first_disc,
        "firstMapped": False,        # EDSM doesn't expose mapping credit
        "firstFootfall": False,      # nor footfall
        "mappedByMe": False,
        "discoveredBy": disc.get("commander"),
        "orbitalPeriodDays": b.get("orbitalPeriod"),
        "rotationPeriodDays": b.get("rotationalPeriod"),
        "semiMajorAxisAU": b.get("semiMajorAxis"),
        "eccentricity": b.get("orbitalEccentricity"),
        "axialTilt": b.get("axialTilt"),
        "tidalLock": b.get("rotationalPeriodTidallyLocked"),
        "rings": _rings(b),
        "signals": None,
    }

    if btype_raw == "star":
        st, subclass = _star_type(b)
        radius_km = b.get("solarRadius") * 696340.0 if b.get("solarRadius") else None
        body.update({
            "type": "star",
            "starType": st,
            "subclass": subclass,
            "luminosity": b.get("luminosity"),
            "stellarMass": b.get("solarMasses"),
            "radiusKm": radius_km,
            "solarRadii": b.get("solarRadius"),
            "ageMY": b.get("age"),
            "surfaceTemperature": b.get("surfaceTemperature"),
            "absoluteMagnitude": b.get("absoluteMagnitude"),
            "color": star_color(st),
            "estimatedValue": _star_value(st, b.get("solarMasses"), first_disc),
        })
    elif btype_raw == "planet":
        pclass = _planet_class(b.get("subType"))
        tstate = (b.get("terraformingState") or "").strip()
        terraformable = "terraform" in tstate.lower() and "not" not in tstate.lower()
        radius_km = b.get("radius")
        pressure = b.get("surfacePressure")
        body.update({
            "type": "planet",
            "planetClass": pclass,
            "terraformState": tstate or None,
            "terraformable": terraformable,
            "atmosphere": b.get("atmosphereType") or None,
            "atmosphereType": b.get("atmosphereType") or None,
            "atmosphereComposition": _comp_list(b.get("atmosphereComposition")),
            "volcanism": (b.get("volcanismType") or "").strip() or None,
            "massEM": b.get("earthMasses"),
            "radiusKm": radius_km,
            "earthRadii": (radius_km / 6371.0) if radius_km else None,
            "gravityG": b.get("gravity"),
            "surfaceTemperature": b.get("surfaceTemperature"),
            # UI expects pascals (it divides by 101325); EDSM gives atmospheres.
            "surfacePressure": (pressure * 101325.0) if pressure is not None else None,
            "landable": b.get("isLandable"),
            "palette": planet_palette(pclass),
            "estimatedValue": estimate_body_value(
                pclass, b.get("earthMasses"), terraformable, first_disc, False, False),
        })
    else:
        body.update({"type": "cluster", "estimatedValue": 0})
    return body


def _short(name: str, system_name: str = "") -> str:
    """Strip the system-name prefix so e.g. 'Foo XY-Z 9 a' -> '9 a'."""
    if name and system_name and name.startswith(system_name):
        rest = name[len(system_name):].strip()
        return rest or name
    return name


def _star_value(star_type: str, mass, first_disc: bool) -> int:
    k = _STAR_VALUE_K.get((star_type or "")[:1], 1200)
    value = k + ((mass or 1.0) * k / 66.25)
    if first_disc:
        value *= 2.6
    return int(round(value))
