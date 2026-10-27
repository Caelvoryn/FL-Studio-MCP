import asyncio
import json

import numpy as np
import pytest
import soundfile as sf
from fastmcp import Client, FastMCP
from fl_studio_mcp.music.audio_compare import compare_files
from fl_studio_mcp.tools import audio, mix_doctor


@pytest.fixture
def tone(tmp_path):
    sr = 22050
    t = np.arange(sr * 2) / sr
    p = tmp_path / "tone.wav"
    sf.write(p, 0.2 * np.sin(2 * np.pi * 440 * t), sr, subtype="FLOAT")
    return p


def test_mono_pitch_is_a4(tone):
    result = audio.audio_extract_melody(tone, bpm=120, engine="pyin")
    assert result["engine"] == "pyin" and result["kept_count"] > 0
    assert all(abs(n["midi"] - 69) <= 1 for n in result["notes"])
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("bpm", [0, -1, float("nan"), float("inf")])
def test_invalid_bpm(tone, bpm):
    with pytest.raises(ValueError, match="bpm"):
        audio.audio_extract_melody(tone, bpm=bpm)


def test_silence_has_no_key():
    assert audio.estimate_key(np.zeros(12))["key"] is None


def test_actual_audio_comparison_ignores_gain_and_keeps_stereo(tone, tmp_path):
    y, sr = sf.read(tone)
    right = tmp_path / "gain.wav"
    sf.write(right, y * 0.5, sr, subtype="FLOAT")
    r = compare_files(tone, right, duration=1)
    assert max(abs(x) for x in r["band_delta_pct"].values()) < 0.001
    assert r["reference"]["samples"] == r["mix"]["samples"]
    assert abs((r["mix"]["rms_dbfs"] - r["reference"]["rms_dbfs"]) + 6.0206) < 0.01
    assert r["listened"] is False
    json.dumps(r, allow_nan=False)


def test_short_or_missing_segment_rejected(tone):
    with pytest.raises(ValueError, match="beyond"):
        compare_files(tone, tone, duration=10)


def test_silent_comparison_rejected(tone, tmp_path):
    p = tmp_path / "silent.wav"
    sf.write(p, np.zeros(44100), 22050)
    with pytest.raises(ValueError, match="silent"):
        compare_files(tone, p, duration=1)


def test_reference_tool_requires_real_mix():
    async def run():
        mcp = FastMCP("compare")
        mix_doctor.register(mcp)
        async with Client(mcp) as client:
            r = await client.call_tool("fl_reference_match", {"reference_audio_path": "reference.wav"})
            assert r.data["code"] == "actual_mix_required"
            assert r.data["ok"] is False
    asyncio.run(run())


def test_dependency_error_is_actionable():
    r = audio.analysis_error(ModuleNotFoundError("librosa"))
    assert r["code"] == "audio_dependency_missing" and r["remediation"]
