"""Read plugin/preset names from disk -- like plugin_library, for PRESETS.

Sources (read-only directory listings; never file contents):
  * FL Presets:  <FL Studio*>/Presets/Plugin presets/<Plugin>/*.fst  (per-plugin)
                 + Channel presets/ + Mixer presets/
  * Serum:       <Documents>/Xfer/Serum 2 Presets/**/*.serumpreset

FL still can't LOAD a preset via the API -- this is suggestion-only (the user
loads the named preset; then Claude tweaks params via the existing plugin tools).
"""
from __future__ import annotations

import os
import re
from pathlib import Path

_ENV_FL = "FLSTUDIO_MCP_PRESETS"
_ENV_SERUM = "FLSTUDIO_MCP_SERUM_PRESETS"

# Small synonym map so a description like "vintage bass" matches Serum-style
# short names ("BA ...", "Analog ..."). Rough -- Claude refines the final pick.
_SYN = {
    "bass": ("bass", "ba ", "808", "sub"),
    "lead": ("lead", "ld ", "ld_"),
    "pluck": ("pluck", "plk"),
    "pad": ("pad", "pd "),
    "keys": ("keys", "key", "piano", "ky "),
    "arp": ("arp", "seq", "sequence"),
    "chord": ("chord", "chd", "stab"),
    "vintage": ("vintage", "vint", "retro", "analog", "analogue", "classic", "old"),
    "warm": ("warm", "soft", "mellow", "smooth"),
    "bright": ("bright", "air", "crisp", "shiny"),
    "hard": ("hard", "aggress", "dist", "grit", "growl", "dirty"),
    "vocal": ("vocal", "vox", "voice", "choir", "formant"),
    "fx": ("fx", "riser", "sweep", "impact", "noise"),
}


def _fl_studio_dirs():
    from .resource_paths import fl_user_dirs
    yield from fl_user_dirs()


def fl_preset_roots():
    env = os.environ.get(_ENV_FL)
    if env:
        return [env] if Path(env).is_dir() else []
    from .resource_paths import fl_install_dirs
    roots = [fl / "Presets" for fl in _fl_studio_dirs()]
    roots += [fl / "Data" / "Patches" for fl in fl_install_dirs()]
    return [str(p) for p in dict.fromkeys(roots) if p.is_dir()]


def find_fl_presets():
    roots = fl_preset_roots()
    return roots[0] if roots else None


def find_serum_presets():
    env = os.environ.get(_ENV_SERUM)
    if env:
        return env if os.path.isdir(env) else None
    from .resource_paths import documents_dirs
    for doc in documents_dirs():
        for name in ("Serum 2 Presets", "Serum2 Presets", "Serum Presets"):
            p = doc / "Xfer" / name
            if p.is_dir():
                return str(p)
    return None


def _names(folder, ext):
    out = set()
    if folder and os.path.isdir(folder):
        for _r, _d, files in os.walk(folder):
            for f in files:
                if f.lower().endswith(ext):
                    out.add(os.path.splitext(f)[0])
    return sorted(out, key=str.lower)


def preset_records(presets_root):
    """Keep file identity, type and nested category; duplicate names are valid."""
    pp = Path(presets_root) / "Plugin presets" if presets_root else None
    if pp is None or not pp.is_dir():
        return []
    records = []
    for p in sorted(pp.rglob("*")):
        if not p.is_file() or p.suffix.lower() != ".fst":
            continue
        parts = p.relative_to(pp).parts
        typed = parts[0].lower() in ("generators", "effects")
        pos = 1 if typed else 0
        if len(parts) <= pos + 1:
            continue
        records.append({"plugin": parts[pos], "name": p.stem,
                        "kind": parts[0] if typed else "unknown",
                        "category": "/".join(parts[pos + 1:-1]),
                        "path": str(p.resolve()), "metadata_source": "filesystem"})
    return records


def plugin_presets(presets_root):
    out = {}
    for row in preset_records(presets_root):
        out.setdefault(row["plugin"], set()).add(row["name"])
    return {key: sorted(names, key=str.lower) for key, names in out.items()}


def serum_presets():
    return _names(find_serum_presets(), ".serumpreset")


def surge_catalog_records():
    """Explicit local index; keep only files still present. Never infer a timbre."""
    import json
    catalog = os.environ.get("FLSTUDIO_MCP_SURGE_CATALOG")
    if not catalog:
        return []
    path = Path(catalog)
    if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("Surge catalog missing or exceeds 16 MiB")
    records = json.loads(path.read_text(encoding="utf8")).get("records", [])
    return [{k: v for k, v in row.items() if k != "parameters"}
            for row in records if row.get("plugin") == "Surge XT"
            and Path(row["path"]).is_file() and Path(row["path"]).suffix.lower() == ".fxp"]


def list_presets(plugin_filter=None):
    """Categorized preset names. No filter -> a SUMMARY (per-plugin counts +
    serum/channel/mixer counts). With plugin_filter -> that plugin's full list."""
    fl, serum_dir = find_fl_presets(), find_serum_presets()
    surge = surge_catalog_records()
    if not fl and not serum_dir and not surge:
        return {"found": False,
                "error": "no preset folders found; set %s / %s." % (_ENV_FL, _ENV_SERUM)}
    records = [row for root in fl_preset_roots() for row in preset_records(root)]
    records.extend(surge)
    groups = {}
    for row in records:
        groups.setdefault(row["plugin"], set()).add(row["name"])
    pp = {k: sorted(v, key=str.lower) for k, v in groups.items()}
    serum = serum_presets()

    if plugin_filter:
        f = plugin_filter.lower()
        out = {k: v for k, v in pp.items() if f in k.lower()}
        if "serum" in f and serum:
            out["Serum 2 (Xfer)"] = serum
        return {"found": True, "filter": plugin_filter,
                "fl_presets_path": fl, "serum_path": serum_dir,
                "presets": out, "count": sum(len(v) for v in out.values()),
                "records": [r for r in records if f in r["plugin"].lower()]}

    summary = {"found": True, "fl_presets_path": fl, "serum_path": serum_dir,
               "fl_presets_roots": fl_preset_roots(),
               "file_count": len(records),
               "plugins_with_presets": {k: len(v) for k, v in pp.items()},
               "serum_preset_count": len(serum)}
    for sub, key in (("Channel presets", "channel_presets"), ("Mixer presets", "mixer_presets")):
        names = _names(os.path.join(fl, sub), ".fst") if fl else []
        if names:
            summary[key] = {"count": len(names), "sample": names[:12]}
    return summary


def _expand(tok):
    out = {tok}
    for key, syns in _SYN.items():
        if tok == key or tok in syns:
            out.add(key)
            out.update(syns)
    return out


def score_presets(names, description, top=15):
    """Rough name match: how many (synonym-expanded) description tokens appear in
    each preset name. Returns the top matches (name-only -- can't hear sound)."""
    toks = [w for w in re.split(r"[^a-z0-9]+", (description or "").lower()) if w]
    expanded = [_expand(t) for t in toks]
    scored = []
    for nm in names:
        low = nm.lower()
        s = sum(1 for syn_set in expanded if any(syn in low for syn in syn_set))
        if s:
            scored.append((s, nm))
    scored.sort(key=lambda x: (-x[0], x[1].lower()))
    return [nm for _s, nm in scored[:top]]
