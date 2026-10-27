from pathlib import Path

import pytest
from fl_studio_mcp.music.surge_library import index, read_patch


def patch_file(path, xml):
    data = bytearray(92)
    data[:4] = b"CcnK"
    data[8:12] = b"FPCh"
    data[60:64] = b"sub3"
    path.write_bytes(bytes(data) + xml)


def test_reads_embedded_metadata(tmp_path):
    p = tmp_path / "filename.fxp"
    patch_file(p, b'<?xml version="1.0"?><patch><meta name="Real Name" category="Bass" author="Test"/><parameters><volume value="0.4"/></parameters></patch>')
    r = read_patch(p)
    assert r["name"] == "Real Name" and r["category"] == "Bass"
    assert r["parameters"]["volume"]["value"] == "0.4"
    assert not r["listened"] and Path(r["path"]).is_file()


def test_bad_xml_preserves_disk_entry(tmp_path):
    p = tmp_path / "broken.fxp"
    patch_file(p, b'<?xml version="1.0"?><patch><meta name="bad\xb5"/></patch>')
    r = index(tmp_path)
    assert len(r["records"]) == 1 and len(r["errors"]) == 1
    assert r["records"][0]["metadata_source"].startswith("filesystem")


def test_entity_declaration_rejected(tmp_path):
    p = tmp_path / "entity.fxp"
    patch_file(p, b'<?xml version="1.0"?><!DOCTYPE patch [<!ENTITY x "boom">]><patch><meta/></patch>')
    with pytest.raises(ValueError, match="DTD/entity"):
        read_patch(p)
