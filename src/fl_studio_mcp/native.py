"""Read-only inspector for observed FL26.1.5 events. Never rewrites FLP bytes."""
import hashlib
import json
import struct
import math
from pathlib import Path


def events(path):
    data = Path(path).read_bytes()
    if len(data) < 22:
        raise ValueError("truncated FLP header")
    if data[:4] != b"FLhd" or data[14:18] != b"FLdt":
        raise ValueError("unsupported FLP header")
    if struct.unpack_from("<I", data, 18)[0] != len(data) - 22:
        raise ValueError("FLdt length mismatch")
    ppq = struct.unpack_from("<H", data, 12)[0]
    pos, out = 22, []
    while pos < len(data):
        event = data[pos]
        pos += 1
        if event < 192:
            size = 1 if event < 64 else 2 if event < 128 else 3 if event == 172 else 4
        else:
            size, shift = 0, 0
            while True:
                if pos >= len(data):
                    raise ValueError("truncated variable event size")
                value = data[pos]
                pos += 1
                size |= (value & 127) << shift
                shift += 7
                if value < 128:
                    break
                if shift > 35:
                    raise ValueError("invalid event size")
        if pos + size > len(data):
            raise ValueError("truncated FLP event")
        out.append((event, data[pos:pos + size]))
        pos += size
    return data, ppq, out


def inspect(path):
    data, ppq, stream = events(path)
    result = {"path": str(Path(path).resolve()), "sha256": hashlib.sha256(data).hexdigest(),
              "ppq": ppq, "patterns": {}, "channels": {}, "playlist": [],
              "automation": [], "mixer_event_hashes": [], "plugin_state_hashes": []}
    pattern, channel = None, None
    for event, value in stream:
        if event == 213:
            result["plugin_state_hashes"].append(hashlib.sha256(value).hexdigest())
        if event == 156:
            result["bpm"] = int.from_bytes(value, "little") / 1000
        elif event == 65:
            pattern = int.from_bytes(value, "little")
            result["patterns"].setdefault(pattern, {"notes": []})
        elif event == 193 and pattern is not None:
            result["patterns"][pattern]["name"] = value.decode("utf-16le").rstrip("\0")
        elif event == 224:
            if len(value) % 24:
                raise ValueError("unexpected note-event stride")
            for start in range(0, len(value), 24):
                row = struct.unpack_from("<IHHIHHBBBBBBBB", value, start)
                result["patterns"][pattern]["notes"].append({
                    "channel": row[2], "pitch": row[4], "time_ticks": row[0],
                    "length_ticks": row[3], "velocity_raw": row[11],
                    "release_raw": row[8], "color": row[9], "pan_raw": row[10],
                    "mod_x_raw": row[12], "mod_y_raw": row[13],
                    "raw_record_hex": value[start:start + 24].hex()})
        elif event == 64:
            channel = int.from_bytes(value, "little")
            result["channels"].setdefault(channel, {})
        elif channel is not None and event in (21, 201, 203, 196, 213):
            target = result["channels"][channel]
            if event == 21:
                target["type_id"] = value[0]
            elif event == 213:
                target["plugin_state_sha256"] = hashlib.sha256(value).hexdigest()
            else:
                target[{201: "plugin", 203: "name", 196: "sample_path"}[event]] = value.decode("utf-16le").rstrip("\0")
        elif event == 234:
            count = struct.unpack_from("<I", value, 17)[0]
            points, position = [], 0.0
            for i in range(count):
                offset, level = struct.unpack_from("<dd", value, 21 + 24 * i)
                position += offset
                points.append({"position_beats": position, "value": level})
            result["automation"].append({"channel": channel, "points": points,
                                           "event_sha256": hashlib.sha256(value).hexdigest()})
        elif event == 233:
            if len(value) % 88:
                raise ValueError("unexpected FL26 playlist stride")
            for i in range(0, len(value), 88):
                base, item = struct.unpack_from("<HH", value, i + 4)
                reverse_track = struct.unpack_from("<H", value, i + 12)[0]
                start_offset, end_offset = struct.unpack_from("<ff", value, i + 24)
                start_bits, end_bits = struct.unpack_from("<II", value, i + 24)
                if item >= base:  # Pattern offsets are integer ticks; 0xFFFFFFFF = full source.
                    start_offset = None if start_bits == 0xFFFFFFFF else start_bits
                    end_offset = None if end_bits == 0xFFFFFFFF else end_bits
                result["playlist"].append({"clip_index": len(result["playlist"]),
                                          "position_ticks": struct.unpack_from("<I", value, i)[0],
                                          "length_ticks": struct.unpack_from("<I", value, i + 8)[0],
                                          "track": 500 - reverse_track,
                                          "source_kind": "pattern" if item >= base else "channel",
                                          "source_id": item - base if item >= base else item,
                                          "start_offset": start_offset if start_offset is not None and math.isfinite(start_offset) else None,
                                          "end_offset": end_offset if end_offset is not None and math.isfinite(end_offset) else None,
                                          "start_offset_bits": start_bits,
                                          "end_offset_bits": end_bits,
                                          "event_record_sha256": hashlib.sha256(value[i:i + 88]).hexdigest()})
        elif event in (225, 235, 236):
            result["mixer_event_hashes"].append({"event": event, "sha256": hashlib.sha256(value).hexdigest()})
    result["missing_sample_paths"] = [c["sample_path"] for c in result["channels"].values()
        if c.get("sample_path") and not Path(c["sample_path"]).is_file()]
    result["limitations"] = ["Observed FL26.1.5 event layout only; unknown events are preserved as opaque data, never rewritten",
        "Global BPM does not exclude tempo events inside Patterns; validate transport playback and actual render timing",
        "Plugin state hash does not prove preset identity or plugin availability", "No reliable unsaved-dirty-state detection"]
    return result


def verify_midi(flp_path, midi_path):
    import mido
    native = inspect(flp_path)
    midi = mido.MidiFile(midi_path)
    expected = []
    for channel, track in enumerate(midi.tracks[1:]):
        pos, active = 0, {}
        for msg in track:
            pos += msg.time
            if msg.type == "note_on" and msg.velocity:
                active.setdefault(msg.note, []).append((pos, msg.velocity))
            elif msg.type in ("note_off", "note_on"):
                start, velocity = active[msg.note].pop(0)
                expected.append((channel, msg.note, start, pos - start, velocity))
    actual = [(n["channel"], n["pitch"], n["time_ticks"], n["length_ticks"], n["velocity_raw"])
              for pattern in native["patterns"].values() for n in pattern["notes"]]
    if native["ppq"] != midi.ticks_per_beat:
        raise ValueError("PPQ adaptation required")
    if sorted(actual) != sorted(expected):
        raise AssertionError("native note fields differ from imported MIDI")
    return {"verified": True, "notes": len(actual), "fields": ["channel", "pitch", "start", "duration", "velocity"]}


