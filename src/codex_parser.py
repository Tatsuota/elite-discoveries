"""
Parse the in-game **Codex** from the Elite Dangerous journals.

Every Codex discovery is written to the journal as a `CodexEntry` event — locally,
no API or Frontier login required. We read those for ONE commander (the selected
one) and group them by category / sub-category / region, just like discoveries.

`CodexEntry` fields we use:
    EntryID, Name(_Localised), SubCategory(_Localised), Category(_Localised),
    Region(_Localised), System, SystemAddress, BodyID, Latitude, Longitude,
    IsNewEntry (true = first time this commander logged it).

Standard library only. Reuses `journal_parser` only for the file-listing helpers.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from journal_parser import journal_files, default_journal_dir


def load_codex(journal_dir: str | None = None, commander: str | None = None) -> dict:
    cf = (commander or "").strip().lower() or None
    active = None
    entries: dict[int, dict] = {}   # EntryID -> earliest record

    for path in journal_files(journal_dir or default_journal_dir()):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if '"event":"' not in line:
                        continue
                    if not any(k in line for k in ("CodexEntry", "Commander", "LoadGame")):
                        continue
                    try:
                        e = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ev = e.get("event")
                    if ev in ("Commander", "LoadGame"):
                        n = e.get("Name") or e.get("Commander")
                        if n:
                            active = n
                        continue
                    if ev != "CodexEntry":
                        continue
                    # only the selected commander's codex
                    if cf and (active or "").strip().lower() != cf:
                        continue
                    eid = e.get("EntryID")
                    if eid is None:
                        continue

                    rec = {
                        "entryId": eid,
                        "name": e.get("Name_Localised") or _tidy(e.get("Name")),
                        "subCategory": e.get("SubCategory_Localised") or _tidy(e.get("SubCategory")),
                        "category": e.get("Category_Localised") or _tidy(e.get("Category")),
                        "region": e.get("Region_Localised") or _tidy(e.get("Region")),
                        "system": e.get("System"),
                        "systemAddress": e.get("SystemAddress"),
                        "bodyId": e.get("BodyID"),
                        "lat": e.get("Latitude"),
                        "lon": e.get("Longitude"),
                        "isNew": bool(e.get("IsNewEntry")),
                        "timestamp": e.get("timestamp"),
                    }
                    prev = entries.get(eid)
                    if prev is None:
                        entries[eid] = rec
                    else:
                        # keep the earliest sighting, but remember if it was ever new
                        ever_new = prev["isNew"] or rec["isNew"]
                        if (rec["timestamp"] or "") < (prev["timestamp"] or ""):
                            entries[eid] = rec
                        entries[eid]["isNew"] = ever_new
        except OSError:
            continue

    return _build(entries, commander)


def _build(entries: dict[int, dict], commander: str | None) -> dict:
    cats: dict[str, dict] = {}
    regions: dict[str, int] = {}
    new_total = 0

    for e in entries.values():
        if e["isNew"]:
            new_total += 1
        if e.get("region"):
            regions[e["region"]] = regions.get(e["region"], 0) + 1

        cname = e["category"] or "Unknown"
        cat = cats.setdefault(cname, {"name": cname, "count": 0, "newCount": 0,
                                      "subCategories": {}, "entries": []})
        cat["count"] += 1
        if e["isNew"]:
            cat["newCount"] += 1
        cat["entries"].append(e)
        sname = e["subCategory"] or "Other"
        cat["subCategories"][sname] = cat["subCategories"].get(sname, 0) + 1

    categories = []
    for cat in cats.values():
        cat["entries"].sort(key=lambda x: (x["timestamp"] or ""), reverse=True)
        cat["subCategories"] = [
            {"name": k, "count": v}
            for k, v in sorted(cat["subCategories"].items(), key=lambda kv: -kv[1])
        ]
        categories.append(cat)
    categories.sort(key=lambda c: -c["count"])

    region_list = [{"name": k, "count": v}
                   for k, v in sorted(regions.items(), key=lambda kv: -kv[1])]

    return {
        "ok": True,
        "commander": commander,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "totalEntries": len(entries),
        "newEntries": new_total,
        "categories": categories,
        "regions": region_list,
    }


def _tidy(token: str | None) -> str | None:
    """Turn a raw `$Codex_..._Name;` token into something readable as a fallback."""
    if not token:
        return token
    s = token.strip().strip("$;")
    for p in ("Codex_Ent_", "Codex_SubCategory_", "Codex_Category_", "Codex_RegionName_"):
        if s.startswith(p):
            s = s[len(p):]
    return s.replace("_", " ").strip() or token


if __name__ == "__main__":
    import sys
    cmdr = sys.argv[1] if len(sys.argv) > 1 else None
    d = load_codex(commander=cmdr)
    print(f"Commander: {d['commander']}")
    print(f"Codex entries: {d['totalEntries']}  (new: {d['newEntries']})")
    for c in d["categories"]:
        print(f"  {c['name']:32s} {c['count']:4d}  (new {c['newCount']})")
    print(f"Regions: {len(d['regions'])}")
