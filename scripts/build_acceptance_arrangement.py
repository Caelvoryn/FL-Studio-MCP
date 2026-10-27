"""Original 40-bar / 75-second at 128 BPM test score. Does not control FL."""
import json
from pathlib import Path

import mido


def compose():
    tracks = [[] for _ in range(7)]
    def add(channel, pitch, bar, offset, duration, velocity):
        tracks[channel].append({"pitch": pitch, "time_bars": bar + offset,
                                "length_bars": duration, "velocity": velocity / 128})
    chords = [(57, 60, 64), (53, 57, 60), (60, 64, 67), (55, 59, 62)]
    roots = [33, 29, 36, 31]
    for bar in range(40):
        intro, build, drop, breakdown, outro = bar < 8, 8 <= bar < 16, 16 <= bar < 32, 24 <= bar < 28, bar >= 32
        chord = chords[(bar // 2) % 4]
        for pitch in chord:
            add(1, pitch, bar, 0, .92, 55 if intro or breakdown else 66)
        if bar >= 4 and not breakdown:
            for beat in range(4):
                if outro and bar >= 38 and beat > 1: continue
                add(2, roots[(bar // 2) % 4], bar, beat / 4 + .015, .15, 80 if drop else 66)
        if 4 <= bar < 38 and not breakdown:
            for beat in range(4):
                if build and bar == 15 and beat == 3: continue
                add(3, 60, bar, beat / 4, .06, 99 if drop else 78)
        if 8 <= bar < 38 and not breakdown:
            for beat in (1, 3): add(4, 60, bar, beat / 4, .06, 80)
        if 2 <= bar < 39:
            for eighth in range(8):
                if intro and eighth % 2 == 0: continue
                if breakdown and eighth not in (2, 6): continue
                add(5, 60, bar, eighth / 8 + (.008 if eighth % 2 else 0), .035,
                    44 + (eighth % 2) * 15 + (bar % 3) * 2)
        if bar in (7, 15, 23, 27, 31, 37):
            count = 16 if bar == 15 else 8
            for hit in range(count):
                add(6, 60, bar, .5 + hit / (2 * count), .02, 40 + int(40 * hit / count))
        if 6 <= bar < 36:
            # Question/answer contours, rests, and distinct every-four-bar endings.
            base = [69, 72, 76, 74] if (bar // 4) % 2 == 0 else [76, 74, 72, 67]
            offsets = [0, .1875, .5, .8125] if bar % 2 == 0 else [.125, .375, .625]
            if intro or breakdown: offsets = offsets[::2]
            if build and bar < 12: offsets = offsets[:2]
            for index, offset in enumerate(offsets):
                pitch = base[(index + bar % 4) % 4]
                if bar % 4 == 3 and index == len(offsets) - 1: pitch = 69
                add(0, pitch, bar, offset, .10 if drop else .15, 76 if drop else 62)
    return {"bpm": 128, "beats_per_bar": 4, "bars": 40, "duration_seconds": 75,
            "sections": [{"name": n, "start_bar": a, "end_bar_exclusive": b}
                         for n, a, b in [("Intro", 0, 8), ("Build-up", 8, 16), ("Drop A", 16, 24),
                                         ("Breakdown", 24, 28), ("Drop B", 28, 32), ("Outro", 32, 40)]],
            "tracks": [{"name": name, "channel": i, "notes": tracks[i]}
                       for i, name in enumerate(("Lead", "Pad", "Bass", "Kick", "Clap", "Hat", "Snare"))]}


def write(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    spec = compose()
    (output / "arrangement.json").write_text(json.dumps(spec, indent=2), encoding="utf8")
    midi = mido.MidiFile(type=1, ticks_per_beat=96)
    meta = mido.MidiTrack()
    midi.tracks.append(meta)
    meta.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(128)))
    for track in spec["tracks"]:
        target = mido.MidiTrack()
        midi.tracks.append(target)
        target.append(mido.MetaMessage("track_name", name=track["name"]))
        events = []
        for note in track["notes"]:
            start = round(note["time_bars"] * 384)
            end = start + round(note["length_bars"] * 384)
            velocity = round(note["velocity"] * 128)
            events += [(start, 1, note["pitch"], velocity), (end, 0, note["pitch"], 0)]
        previous = 0
        for tick, on, pitch, vel in sorted(events):
            target.append(mido.Message("note_on" if on else "note_off", channel=track["channel"],
                                       note=pitch, velocity=vel, time=tick - previous))
            previous = tick
    midi.save(output / "System_Demo_128.mid")
    return spec


if __name__ == "__main__":
    import sys
    result = write(sys.argv[1])
    print(json.dumps({"bars": result["bars"], "notes": sum(len(t["notes"]) for t in result["tracks"])}))
