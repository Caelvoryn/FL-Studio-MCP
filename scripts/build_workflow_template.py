"""Original MIDI test arrangement, not a validated native FLP or finished song."""
import argparse
import json
import random
from pathlib import Path

import mido
from fl_studio_mcp.music.midi_export import write_midi


def build(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    midi_path = output / "Editable_Workflow_Template.mid"
    spec_path = output / "arrangement.json"
    if midi_path.exists() or spec_path.exists():
        raise FileExistsError("choose a new version directory; original files are preserved")
    rng = random.Random(20261026)
    tracks = [{"name": name, "channel": ch, "notes": []} for name, ch in
              [("Lead", 0), ("Chords", 1), ("Bass", 2), ("Kick", 9),
               ("Clap", 9), ("Hat", 9), ("Transition", 9)]]

    def note(track, pitch, start, length, velocity):
        tracks[track]["notes"].append({"pitch": pitch, "start_bars": round(max(0, start), 6),
                                       "length_bars": length, "velocity": velocity})

    sections = [("Intro", 0, 8), ("Build", 8, 16), ("Drop A", 16, 32),
                ("Breakdown", 32, 40), ("Build 2", 40, 48), ("Drop B", 48, 60),
                ("Outro", 60, 64)]
    progression = [(57, 60, 64), (53, 57, 60), (60, 64, 67), (55, 59, 62)]
    motif = [(0, 76, .125), (.1875, 79, .0625), (.375, 81, .1875), (.75, 79, .125)]
    for bar in range(64):
        section = next(name for name, start, end in sections if start <= bar < end)
        chord = progression[(bar // 2) % 4]
        for p in chord:
            note(1, p, bar + .005, .85 if "Drop" in section else 1.75, .58 + rng.random() * .1)
        if bar >= 8 and section != "Breakdown":
            for beat in range(4):
                note(3, 36, bar + beat / 4, .04, .88 + rng.random() * .08)
                note(2, chord[0] - 24, bar + beat / 4 + .125, .10, .7 + rng.random() * .1)
            for step in range(8):
                swing = .012 if step % 2 else 0
                note(5, 42, bar + step / 8 + swing + rng.uniform(-.003, .003), .025,
                     .45 + (.18 if step % 2 else 0) + rng.random() * .1)
            for beat in (1, 3):
                note(4, 39, bar + beat / 4 + .002, .04, .76 + rng.random() * .1)
        if "Drop" in section or section == "Breakdown":
            for start, pitch, length in motif:
                if bar % 4 == 3 and start == .75:
                    pitch, length = 74, .1875
                if section == "Drop B" and bar % 2:
                    pitch -= 12
                note(0, pitch, bar + start + rng.uniform(-.002, .002), length,
                     .78 if start == 0 else .64 + rng.random() * .12)
        if bar in (15, 31, 47, 59):
            for step in range(8):
                note(6, 38, bar + .5 + step / 16, .025, .35 + step * .07)
    plan = {"status": "MIDI template; FL import/instruments/routing/export/listening unverified",
            "bpm": 120, "meter": "4/4", "key": "A minor", "seed": 20261026,
            "sections": sections, "tracks": tracks,
            "native_flp_requirements": ["one editable Piano Roll per musical part", "assign installed instruments and verified presets",
                                        "dedicated mixer routes", "native effects/automation", "save as new FLP and reopen for verification"],
            "feedback": {"listened": False, "file_sha256": None, "time_range": None,
                         "listener": None, "issue": None, "priority": None, "target_change": None}}
    write_midi(tracks, 120, str(midi_path))
    loaded = mido.MidiFile(midi_path)
    counts = [sum(msg.type == "note_on" and msg.velocity > 0 for msg in t) for t in loaded.tracks[1:]]
    assert counts == [len(t["notes"]) for t in tracks]
    readback = []
    for spec, midi_track in zip(tracks, loaded.tracks[1:]):
        tick, active, actual = 0, {}, []
        for msg in midi_track:
            tick += msg.time
            if msg.type == "note_on" and msg.velocity > 0:
                active.setdefault((msg.channel, msg.note), []).append((tick, msg.velocity))
            elif msg.type in ("note_on", "note_off"):
                start, velocity = active[(msg.channel, msg.note)].pop(0)
                actual.append((msg.note, start, tick - start, velocity, msg.channel))
        assert all(not pending for pending in active.values())
        expected = [(n["pitch"], round(n["start_bars"] * 1920),
                     round(n["length_bars"] * 1920), round(n["velocity"] * 127), spec["channel"])
                    for n in spec["notes"]]
        assert sorted(actual) == sorted(expected), spec["name"]
        readback.append({"track": spec["name"], "notes_verified": len(actual),
                         "fields": ["pitch", "start_ticks", "duration_ticks", "velocity", "channel"]})
    plan["midi_readback"] = {"type": loaded.type, "tracks_including_tempo": len(loaded.tracks),
                             "note_counts": counts, "verified": True, "detail": readback}
    spec_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps({"midi": str(midi_path), "readback": plan["midi_readback"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", help="new song/version directory")
    build(parser.parse_args().output)
