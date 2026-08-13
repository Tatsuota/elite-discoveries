"""
Elite Dangerous journal parser - extracts FIRST DISCOVERIES from local journals.

The game writes append-only JSON-lines journals to:
    %USERPROFILE%\\Saved Games\\Frontier Developments\\Elite Dangerous\\Journal*.log

Each `Scan` event carries the flags that tell us whether *you* were the first
commander to touch a body:
    WasDiscovered : false  -> you are the first to DISCOVER it
    WasMapped     : false  -> nobody had MAPPED it (do an SAA scan = first mapper)
    WasFootfalled : false  -> nobody had walked on it (first footfall)

This module reads every journal, deduplicates bodies across files/sessions
(keeping the earliest scan, which holds the true "was it already known" state),
and returns a structured model the web UI renders.

Standard library only - no pip installs required.
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from glob import glob


# --------------------------------------------------------------------------- #
#  Locating the journals
# --------------------------------------------------------------------------- #
def default_journal_dir() -> str:
    """Return the standard Elite Dangerous journal directory for this machine."""
    env = os.environ.get("ED_JOURNAL_DIR")
    if env:
        return env
    profile = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    return os.path.join(
        profile, "Saved Games", "Frontier Developments", "Elite Dangerous"
    )


def journal_files(journal_dir: str) -> list[str]:
    """All Journal*.log files, sorted chronologically (filename = timestamp)."""
    files = glob(os.path.join(journal_dir, "Journal.*.log"))
    return sorted(files)


# --------------------------------------------------------------------------- #
#  Star / planet classification helpers
# --------------------------------------------------------------------------- #

# Star spectral classes -> display colour (rough black-body colour).
STAR_COLORS = {
    "O": "#9bb0ff", "B": "#aabfff", "A": "#cad7ff", "F": "#f8f7ff",
    "G": "#fff4ea", "K": "#ffd2a1", "M": "#ffcc6f",
    "L": "#ff8a52", "T": "#c75d4f", "Y": "#7a3b3b",
    # Giants / exotic
    "TTS": "#ffd2a1", "AeBe": "#cad7ff",
    "W": "#9bb0ff", "WN": "#9bb0ff", "WC": "#9bb0ff", "WO": "#9bb0ff",
    "C": "#ff6b3d", "CN": "#ff6b3d", "CJ": "#ff6b3d", "MS": "#ffcc6f", "S": "#ffb46f",
    "D": "#dfe9ff", "DA": "#dfe9ff", "DB": "#dfe9ff", "DC": "#dfe9ff",
    "DAB": "#dfe9ff", "DAO": "#dfe9ff", "DAZ": "#dfe9ff", "DAV": "#dfe9ff",
    "N": "#e9f7ff",            # neutron star
    "H": "#1a1030",            # black hole
    "SupermassiveBlackHole": "#1a1030",
}

# Planet class -> a palette {base, accent} the UI uses to draw the portrait.
PLANET_PALETTES = {
    "Metal rich body":            {"base": "#7c5a3a", "accent": "#c9a26b"},
    "High metal content body":    {"base": "#6b5240", "accent": "#a98c66"},
    "Rocky body":                 {"base": "#6e655c", "accent": "#9c9088"},
    "Rocky ice body":             {"base": "#8a8f96", "accent": "#c4cdd6"},
    "Icy body":                   {"base": "#9fb6c9", "accent": "#e6f2fb"},
    "Earthlike body":             {"base": "#2f7d4f", "accent": "#4fb6d6"},
    "Water world":                {"base": "#1f5fa6", "accent": "#5fd0e6"},
    "Water giant":                {"base": "#17486f", "accent": "#3aa6c4"},
    "Ammonia world":              {"base": "#8a6a2f", "accent": "#d8b25a"},
    "Sudarsky class I gas giant":   {"base": "#9a7b5a", "accent": "#d8c0a0"},
    "Sudarsky class II gas giant":  {"base": "#c08a4a", "accent": "#f0d28a"},
    "Sudarsky class III gas giant": {"base": "#7d96b8", "accent": "#cfe0f2"},
    "Sudarsky class IV gas giant":  {"base": "#5a4a5a", "accent": "#9a7aa0"},
    "Sudarsky class V gas giant":   {"base": "#7a3030", "accent": "#c06050"},
    "Helium rich gas giant":        {"base": "#b0a070", "accent": "#e8dca0"},
    "Helium gas giant":             {"base": "#b0a070", "accent": "#e8dca0"},
    "Gas giant with water based life":   {"base": "#5a8a6a", "accent": "#a0d8b0"},
    "Gas giant with ammonia based life": {"base": "#8a7a4a", "accent": "#d8c080"},
}
PLANET_PALETTE_DEFAULT = {"base": "#6e655c", "accent": "#9c9088"}


def planet_palette(planet_class: str) -> dict:
    return PLANET_PALETTES.get(planet_class, PLANET_PALETTE_DEFAULT)


def star_color(star_type: str) -> str:
    if not star_type:
        return "#ffd2a1"
    if star_type in STAR_COLORS:
        return STAR_COLORS[star_type]
    # Match leading letter for white-dwarf / wolf-rayet sub-variants.
    return STAR_COLORS.get(star_type[0], "#ffd2a1")


# Scan-value estimation used to live here. Credit values were removed from the
# UI, so the tables and helpers were deleted rather than computed on every parse.


# --------------------------------------------------------------------------- #
#  The model
# --------------------------------------------------------------------------- #
def _short_name(body_name: str, system_name: str) -> str:
    if body_name and system_name and body_name.startswith(system_name):
        rest = body_name[len(system_name):].strip()
        return rest if rest else body_name
    return body_name


def _classify(event: dict) -> str:
    if "StarType" in event:
        return "star"
    if "PlanetClass" in event:
        return "planet"
    name = event.get("BodyName", "")
    if "Belt Cluster" in name:
        return "cluster"
    if name.endswith("Ring") or " Ring" in name:
        return "ring"
    return "other"


class Parser:
    def __init__(self, journal_dir: str | None = None, commander: str | None = None):
        self.journal_dir = journal_dir or default_journal_dir()
        # When set, ONLY this commander's scans are read (the journal folder can
        # hold several Elite Dangerous characters; we read exactly one).
        self.commander_input = (commander or "").strip() or None
        self.commander_filter = (commander or "").strip().lower() or None
        self.commander = None
        self._active = None                       # commander currently logged in
        self.commanders: set[str] = set()         # all commanders seen
        self.systems: dict[int, dict] = {}        # SystemAddress -> system
        self._bodies: dict[tuple, dict] = {}      # (sysaddr, bodyId) -> body
        self._saa: dict[tuple, dict] = {}         # mapped bodies (you scanned them)
        self._signals: dict[tuple, dict] = {}     # bio/geo/material signals
        self._disembarked: set[tuple] = set()     # bodies we actually walked on
        self._footfall_seen: dict[tuple, tuple] = {}   # key -> (ts, wasFootfalled)
        self.journal_count = 0

    def _active_ok(self) -> bool:
        """True if the logged-in commander matches the filter (or no filter)."""
        if not self.commander_filter:
            return True
        return (self._active or "").strip().lower() == self.commander_filter

    # -- system bookkeeping ------------------------------------------------- #
    def _system(self, address, name) -> dict:
        sys = self.systems.get(address)
        if sys is None:
            sys = {
                "address": address, "name": name, "pos": None,
                "bodyCount": None, "allegiance": None, "economy": None,
                "security": None, "population": None,
                "bodies": {},  # bodyId -> body (filled at finalize)
            }
            self.systems[address] = sys
        elif name and not sys.get("name"):
            sys["name"] = name
        return sys

    # -- main parse loop ---------------------------------------------------- #
    def parse(self) -> dict:
        files = journal_files(self.journal_dir)
        self.journal_count = len(files)
        for path in files:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        if '"event":"' not in line:
                            continue
                        # cheap prefilter before json.loads
                        if not any(k in line for k in (
                            "Scan", "FSDJump", "Location", "CarrierJump",
                            "SAASignalsFound", "FSSBodySignals", "Commander",
                            "LoadGame", "Disembark",
                        )):
                            continue
                        try:
                            e = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        self._handle(e)
            except OSError:
                continue
        return self.build()

    def _handle(self, e: dict):
        ev = e.get("event")

        if ev in ("Commander", "LoadGame"):
            name = e.get("Name") or e.get("Commander")
            if name:
                self._active = name
                self.commanders.add(name)
                if not self.commander_filter:
                    self.commander = name
            return

        # Everything below is data for whoever is currently logged in — skip it
        # unless it belongs to the commander we're reading.
        if not self._active_ok():
            return

        if ev in ("FSDJump", "Location", "CarrierJump"):
            addr = e.get("SystemAddress")
            if addr is None:
                return
            sys = self._system(addr, e.get("StarSystem"))
            if e.get("StarPos"):
                sys["pos"] = e["StarPos"]
            for src, dst in (
                ("SystemAllegiance", "allegiance"),
                ("SystemEconomy_Localised", "economy"),
                ("SystemSecurity_Localised", "security"),
                ("Population", "population"),
            ):
                if e.get(src) not in (None, ""):
                    sys[dst] = e[src]
            return

        if ev == "FSSDiscoveryScan":
            addr = e.get("SystemAddress")
            if addr is None:
                return
            sys = self._system(addr, e.get("SystemName"))
            sys["bodyCount"] = e.get("BodyCount")
            return

        if ev == "Disembark":
            # Getting out on foot is what earns a first footfall — a planet
            # surface only (not a station/ship interior).
            if e.get("OnPlanet"):
                addr, bid = e.get("SystemAddress"), e.get("BodyID")
                if addr is not None and bid is not None:
                    self._disembarked.add((addr, bid))
            return

        if ev == "SAAScanComplete":
            addr, bid = e.get("SystemAddress"), e.get("BodyID")
            if addr is not None and bid is not None:
                self._saa[(addr, bid)] = {
                    "probesUsed": e.get("ProbesUsed"),
                    "efficiencyTarget": e.get("EfficiencyTarget"),
                }
            return

        if ev in ("SAASignalsFound", "FSSBodySignals"):
            addr, bid = e.get("SystemAddress"), e.get("BodyID")
            if addr is None or bid is None:
                return
            slot = self._signals.setdefault((addr, bid), {"bio": 0, "geo": 0, "other": []})
            for s in e.get("Signals", []) or []:
                stype = s.get("Type_Localised") or s.get("Type", "")
                count = s.get("Count", 0)
                if "Biological" in str(s.get("Type", "")) or stype == "Biological":
                    slot["bio"] = max(slot["bio"], count)
                elif "Geological" in str(s.get("Type", "")) or stype == "Geological":
                    slot["geo"] = max(slot["geo"], count)
                else:
                    slot["other"].append({"name": stype, "count": count})
            for g in e.get("Genuses", []) or []:
                gname = g.get("Genus_Localised") or g.get("Genus", "")
                slot.setdefault("genuses", [])
                if gname and gname not in slot["genuses"]:
                    slot["genuses"].append(gname)
            return

        if ev == "Scan":
            self._handle_scan(e)

    def _handle_scan(self, e: dict):
        addr = e.get("SystemAddress")
        bid = e.get("BodyID")
        if addr is None or bid is None:
            return
        key = (addr, bid)
        self._system(addr, e.get("StarSystem"))

        # `WasFootfalled` is Odyssey-only and absent from most FSS/auto scans, so
        # the earliest scan we keep below often doesn't carry it. Remember the
        # earliest scan that DOES report it — that's the state before we landed.
        if "WasFootfalled" in e:
            ts = e.get("timestamp", "")
            prev = self._footfall_seen.get(key)
            if prev is None or ts < prev[0]:
                self._footfall_seen[key] = (ts, bool(e["WasFootfalled"]))

        # Keep the EARLIEST scan: it holds the true "already known?" state.
        # A later re-scan of a system you discovered would read WasDiscovered=true.
        if key in self._bodies:
            existing = self._bodies[key]
            if e.get("timestamp", "") >= existing.get("timestamp", ""):
                return
        self._bodies[key] = e

    # -- finalize ----------------------------------------------------------- #
    def build(self) -> dict:
        # Attach bodies to their systems.
        for (addr, bid), e in self._bodies.items():
            sys = self.systems.get(addr)
            if sys is None:
                sys = self._system(addr, e.get("StarSystem"))
            sys["bodies"][bid] = self._make_body(addr, bid, e)

        out_systems = []
        totals = {
            "systemsFirstDiscovered": 0, "bodiesFirstDiscovered": 0,
            "bodiesFirstMapped": 0, "firstFootfalls": 0,
            "earthlikes": 0, "waterWorlds": 0, "ammoniaWorlds": 0,
            "terraformable": 0,
        }

        # Counted across ALL systems, not just the ones we list: footfalls
        # usually happen in already-discovered systems. Not displayed yet (the
        # journals confirm only a fraction of real landings) but kept truthful.
        totals["firstFootfalls"] = sum(
            1 for s in self.systems.values() for b in s["bodies"].values()
            if b.get("firstFootfall"))

        for sys in self.systems.values():
            bodies = sorted(sys["bodies"].values(), key=lambda b: (b["bodyId"]))
            if not bodies:
                continue

            stars = [b for b in bodies if b["type"] == "star"]
            main_star = min(stars, key=lambda b: b["bodyId"]) if stars else None
            system_first = bool(main_star and not main_star["wasDiscovered"])
            if not system_first and stars:
                system_first = any(not s["wasDiscovered"] for s in stars)

            fd_bodies = [b for b in bodies if b["firstDiscovered"]]
            fm_bodies = [b for b in bodies if b["firstMapped"]]
            ff_bodies = [b for b in bodies if b["firstFootfall"]]

            # Surface systems holding a "first" we actually display. First maps
            # often happen in already-discovered systems, so keying this on
            # first-discoveries alone hid them (and zeroed their totals).
            # `ff_bodies` is deliberately NOT included: the footfall stat is
            # hidden pending a better signal, so a footfall-only system would
            # otherwise be listed with nothing to show for it.
            if not (system_first or fd_bodies or fm_bodies):
                continue

            disc_times = [b["timestamp"] for b in (fd_bodies or fm_bodies or ff_bodies)
                          if b.get("timestamp")]

            classes = {b.get("planetClass") for b in bodies}
            has_elw = "Earthlike body" in classes
            has_ww = "Water world" in classes
            has_aw = "Ammonia world" in classes
            has_terraform = any(b.get("terraformable") for b in bodies)
            has_bio = any((b.get("signals") or {}).get("bio") for b in bodies)

            # Codex-style category (water/ammonia include "-based life" gas giants).
            water_life = has_ww or "Gas giant with water based life" in classes
            ammonia_life = has_aw or "Gas giant with ammonia based life" in classes
            if has_elw:
                category = "elw"
            elif water_life and ammonia_life:
                category = "waterAmmonia"
            elif ammonia_life:
                category = "ammonia"
            elif water_life:
                category = "water"
            else:
                category = "other"   # server upgrades to "anomaly" via the Codex

            out_systems.append({
                "address": sys["address"],
                "name": sys["name"] or "Unknown System",
                "pos": sys["pos"],
                "allegiance": sys.get("allegiance"),
                "economy": sys.get("economy"),
                "security": sys.get("security"),
                "population": sys.get("population"),
                "bodyCount": sys.get("bodyCount"),
                "scannedCount": len(bodies),
                "systemFirstDiscovered": system_first,
                "firstDiscoveredCount": len(fd_bodies),
                "firstMappedCount": len(fm_bodies),
                "firstFootfallCount": len(ff_bodies),
                "discoveredAt": min(disc_times) if disc_times else None,
                "category": category,
                "flags": {
                    "earthlike": has_elw, "waterWorld": has_ww,
                    "ammonia": has_aw, "terraformable": has_terraform,
                    "bio": has_bio,
                },
                "bodies": bodies,
            })

            if system_first:
                totals["systemsFirstDiscovered"] += 1
            totals["bodiesFirstDiscovered"] += len(fd_bodies)
            totals["bodiesFirstMapped"] += len(fm_bodies)
            totals["earthlikes"] += sum(1 for b in fd_bodies if b.get("planetClass") == "Earthlike body")
            totals["waterWorlds"] += sum(1 for b in fd_bodies if b.get("planetClass") == "Water world")
            totals["ammoniaWorlds"] += sum(1 for b in fd_bodies if b.get("planetClass") == "Ammonia world")
            totals["terraformable"] += sum(1 for b in fd_bodies if b.get("terraformable"))

        # Newest discoveries first.
        out_systems.sort(key=lambda s: (s["discoveredAt"] or ""), reverse=True)

        # Report the commander we read, plus any others present in the journals
        # (so the UI can note that other characters were skipped).
        if self.commander_filter:
            self.commander = next(
                (c for c in self.commanders
                 if c.strip().lower() == self.commander_filter), None)
        others = sorted(c for c in self.commanders
                        if not self.commander
                        or c.strip().lower() != self.commander.strip().lower())
        return {
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "commander": self.commander,
            "commanderFilter": self.commander_input,
            "commanders": sorted(self.commanders),
            "otherCommanders": others,
            "journalDir": self.journal_dir,
            "journalCount": self.journal_count,
            "totals": totals,
            "systems": out_systems,
        }

    # -- per-body transform ------------------------------------------------- #
    def _make_body(self, addr, bid, e: dict) -> dict:
        sysname = e.get("StarSystem", "")
        btype = _classify(e)
        was_disc = bool(e.get("WasDiscovered", True))
        was_mapped = bool(e.get("WasMapped", True))
        was_foot = bool(e.get("WasFootfalled", True))
        mapped_by_me = (addr, bid) in self._saa
        saa = self._saa.get((addr, bid))
        sig = self._signals.get((addr, bid))

        planet_class = e.get("PlanetClass") or None
        terraform = (e.get("TerraformState") or "").strip()
        terraformable = terraform in ("Terraformable", "Terraforming", "Terraformed")

        first_disc = not was_disc
        first_mapped = mapped_by_me and not was_mapped
        # A first footfall requires that we ACTUALLY disembarked on the body and
        # that nobody had walked there when we scanned it. `WasFootfalled: false`
        # on its own only means "un-footfalled at scan time" — an opportunity,
        # not an achievement. The field is Odyssey-only, so `is False` keeps a
        # missing field (older journals) from counting either way.
        walked_here = (addr, bid) in self._disembarked
        seen = self._footfall_seen.get((addr, bid))
        first_foot = walked_here and seen is not None and seen[1] is False

        radius_m = e.get("Radius")
        body = {
            "bodyId": bid,
            "name": e.get("BodyName", ""),
            "shortName": _short_name(e.get("BodyName", ""), sysname),
            "type": btype,
            "timestamp": e.get("timestamp"),
            "distanceLS": e.get("DistanceFromArrivalLS"),
            "wasDiscovered": was_disc,
            "wasMapped": was_mapped,
            "firstDiscovered": first_disc,
            "firstMapped": first_mapped,
            "firstFootfall": bool(first_foot),
            "mappedByMe": mapped_by_me,
            "probesUsed": saa.get("probesUsed") if saa else None,
            "efficiencyTarget": saa.get("efficiencyTarget") if saa else None,
            # orbital
            "orbitalPeriodDays": _sec_to_days(e.get("OrbitalPeriod")),
            "rotationPeriodDays": _sec_to_days(e.get("RotationPeriod")),
            "semiMajorAxisAU": _m_to_au(e.get("SemiMajorAxis")),
            "eccentricity": e.get("Eccentricity"),
            "axialTilt": _rad_to_deg(e.get("AxialTilt")),
            "tidalLock": e.get("TidalLock"),
            "rings": _rings(e.get("Rings")),
            "signals": sig,
        }

        if btype == "star":
            body.update({
                "starType": e.get("StarType"),
                "subclass": e.get("Subclass"),
                "luminosity": e.get("Luminosity"),
                "stellarMass": e.get("StellarMass"),
                "radiusKm": (radius_m / 1000.0) if radius_m else None,
                "solarRadii": (radius_m / 6.957e8) if radius_m else None,
                "ageMY": e.get("Age_MY"),
                "surfaceTemperature": e.get("SurfaceTemperature"),
                "absoluteMagnitude": e.get("AbsoluteMagnitude"),
                "color": star_color(e.get("StarType")),
            })
        elif btype == "planet":
            body.update({
                "planetClass": planet_class,
                "terraformState": terraform or None,
                "terraformable": terraformable,
                "atmosphere": e.get("Atmosphere") or None,
                "atmosphereType": e.get("AtmosphereType") or None,
                "atmosphereComposition": e.get("AtmosphereComposition") or None,
                "volcanism": (e.get("Volcanism") or "").strip() or None,
                "massEM": e.get("MassEM"),
                "radiusKm": (radius_m / 1000.0) if radius_m else None,
                "earthRadii": (radius_m / 6.371e6) if radius_m else None,
                "gravityG": _gravity_g(e.get("SurfaceGravity")),
                "surfaceTemperature": e.get("SurfaceTemperature"),
                "surfacePressure": e.get("SurfacePressure"),
                "landable": e.get("Landable"),
                "composition": e.get("Composition") or None,
                "palette": planet_palette(planet_class),
            })
        return body


# --------------------------------------------------------------------------- #
#  Small unit conversions
# --------------------------------------------------------------------------- #
def _sec_to_days(s):
    return round(s / 86400.0, 3) if isinstance(s, (int, float)) and s else None


def _m_to_au(m):
    return round(m / 1.495978707e11, 4) if isinstance(m, (int, float)) and m else None


def _rad_to_deg(r):
    return round(math.degrees(r), 2) if isinstance(r, (int, float)) else None


def _gravity_g(surface_gravity):
    # Journal SurfaceGravity is in m/s^2 (actually already in m/s^2 * 0.1? no, m/s^2).
    if not isinstance(surface_gravity, (int, float)):
        return None
    return round(surface_gravity / 9.80665, 3)


def _rings(rings):
    if not rings:
        return None
    out = []
    for r in rings:
        out.append({
            "name": r.get("Name"),
            "class": (r.get("RingClass", "") or "").replace("eRingClass_", ""),
            "massMT": r.get("MassMT"),
            "innerRad": r.get("InnerRad"),
            "outerRad": r.get("OuterRad"),
        })
    return out



# --------------------------------------------------------------------------- #
#  Convenience entry point
# --------------------------------------------------------------------------- #
def load(journal_dir: str | None = None, commander: str | None = None) -> dict:
    return Parser(journal_dir, commander).parse()


def build_location_index(journal_dir: str | None = None) -> dict:
    """Coordinates of every system ever visited + the CURRENT system.

    Scans FSDJump / Location / CarrierJump events (they carry `StarPos`).
    Journals are processed chronologically, so the last event seen is the
    commander's current location. Commander-agnostic: coordinates are universal.
    """
    coords: dict[str, dict] = {}
    current: str | None = None
    for path in journal_files(journal_dir or default_journal_dir()):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if ('"event":"FSDJump"' not in line
                            and '"event":"Location"' not in line
                            and '"event":"CarrierJump"' not in line):
                        continue
                    try:
                        e = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    name = e.get("StarSystem")
                    pos = e.get("StarPos")
                    if not name:
                        continue
                    if pos:
                        coords[name.strip().lower()] = {"name": name, "pos": pos}
                    current = name
        except OSError:
            continue
    return {"coords": coords, "current": current}


def list_commanders(journal_dir: str | None = None) -> list[str]:
    """Distinct commander names present in the journals (cheap scan)."""
    names: set[str] = set()
    for path in journal_files(journal_dir or default_journal_dir()):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if '"event":"Commander"' not in line and '"event":"LoadGame"' not in line:
                        continue
                    try:
                        e = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if e.get("event") in ("Commander", "LoadGame"):
                        n = e.get("Name") or e.get("Commander")
                        if n:
                            names.add(n)
        except OSError:
            continue
    return sorted(names)


if __name__ == "__main__":
    import sys
    cmdr = sys.argv[2] if len(sys.argv) > 2 else None
    data = load(sys.argv[1] if len(sys.argv) > 1 else None, cmdr)
    t = data["totals"]
    print(f"Commanders in journals: {data['commanders']}")
    print(f"Reading commander: {data['commander']}")
    print(f"Journals : {data['journalCount']}")
    print(f"Systems first-discovered: {t['systemsFirstDiscovered']}")
    print(f"Bodies  first-discovered: {t['bodiesFirstDiscovered']}")
    print(f"Bodies  first-mapped    : {t['bodiesFirstMapped']}")
    print(f"Earthlikes / Water / Ammonia: "
          f"{t['earthlikes']} / {t['waterWorlds']} / {t['ammoniaWorlds']}")
