"""Read existing Surge FXP XML metadata, never execute or modify preset data."""
from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path


def read_patch(path):
    path = Path(path)
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("preset exceeds 32 MiB safety limit")
    data = path.read_bytes()
    if data[:4] != b"CcnK" or data[8:12] != b"FPCh" or data[60:64] != b"sub3":
        raise ValueError("not a supported Surge FXP patch")
    start = data.find(b"<?xml", 64)
    end = data.find(b"</patch>", start)
    if start < 0 or end < 0 or end - start > 4 * 1024 * 1024:
        raise ValueError("missing or oversized Surge XML")
    xml = data[start:end + len(b"</patch>")]
    if b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
        raise ValueError("DTD/entity declarations are not permitted")
    root = ET.fromstring(xml)
    meta, params = root.find("meta"), root.find("parameters")
    if meta is None:
        raise ValueError("missing meta element")
    return {"plugin": "Surge XT", "path": str(path.resolve()),
            "sha256": hashlib.sha256(data).hexdigest(),
            "name": meta.get("name", path.stem), "category": meta.get("category", ""),
            "author": meta.get("author", ""), "comment": meta.get("comment", ""),
            "parameter_count": len(params) if params is not None else 0,
            "parameters": {p.tag: dict(p.attrib) for p in params} if params is not None else {},
            "metadata_source": "embedded Surge FXP XML", "listened": False}


def index(root):
    root = Path(root)
    if not root.is_dir():
        raise ValueError("Surge data directory does not exist")
    records, errors = [], []
    for path in sorted(root.rglob("*.fxp")):
        try:
            record = read_patch(path)
            record["relative_path"] = str(path.relative_to(root))
            records.append(record)
        except (ValueError, ET.ParseError, OSError) as exc:
            errors.append({"path": str(path), "error": str(exc)})
            records.append({"plugin": "Surge XT", "path": str(path.resolve()),
                            "name": path.stem, "category": str(path.parent.relative_to(root)),
                            "relative_path": str(path.relative_to(root)),
                            "metadata_source": "filesystem; XML parse failed",
                            "parse_error": str(exc), "listened": False})
    return {"root": str(root.resolve()), "records": records, "errors": errors,
            "count": len(records), "not_found_means": "no supported FXP in this root only; other resource locations may exist"}
