"""
Parse the in-game **Codex** from the Elite Dangerous journals.

Every Codex discovery is written to the journal as a `CodexEntry` event — locally,
no API or Frontier login required. We read those for ONE commander (the selected
one) and group them by category / sub-category / region, just like discoveries.

`CodexEntry` fields we use:
    EntryID, Name(_Localised), SubCategory(_Localised), Category(_Localised),
    Region(_Localised), System, SystemAddress, BodyID, Latitude, Longitude,
    IsNewEntry (true = first time this commander logged it).

The journal walk itself lives in `journal_parser`: entries are collected on the
same pass as the discoveries (see `Parser.codex_entries`) so the files are read
once per refresh. This module turns those entries into the grouped model.

Standard library only.
"""

from __future__ import annotations

from datetime import datetime, timezone

import journal_parser


def load_codex(journal_dir: str | None = None, commander: str | None = None) -> dict:
    """Standalone entry point (CLI / one-off use) — parses the journals itself.

    The server does NOT use this: it reads `Parser.codex_entries` from the
    discovery parse and calls `build_from_entries`, avoiding a second full read.
    """
    parser = journal_parser.Parser(journal_dir, commander)
    parser.parse()
    return build_from_entries(parser.codex_entries, commander)


def build_from_entries(entries: dict[int, dict], commander: str | None) -> dict:
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


if __name__ == "__main__":
    import sys
    cmdr = sys.argv[1] if len(sys.argv) > 1 else None
    d = load_codex(commander=cmdr)
    print(f"Commander: {d['commander']}")
    print(f"Codex entries: {d['totalEntries']}  (new: {d['newEntries']})")
    for c in d["categories"]:
        print(f"  {c['name']:32s} {c['count']:4d}  (new {c['newCount']})")
    print(f"Regions: {len(d['regions'])}")
