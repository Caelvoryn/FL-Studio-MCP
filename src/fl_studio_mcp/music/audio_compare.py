"""Measured, equal-duration file comparison. No DAW peak/name inference or listening."""
from __future__ import annotations

import hashlib
from pathlib import Path


def compare_files(reference, mix, reference_start=0.0, mix_start=0.0, duration=8.0):
    import librosa
    import numpy as np
    from scipy.signal import welch

    if not all(np.isfinite(x) for x in (reference_start, mix_start, duration)):
        raise ValueError("segment arguments must be finite")
    if min(reference_start, mix_start) < 0 or duration <= 0:
        raise ValueError("starts must be nonnegative and duration positive")
    sr = 44100
    count = int(round(duration * sr))
    if count < 2048:
        raise ValueError("segment too short")

    def profile(path, start):
        y, _ = librosa.load(path, sr=sr, mono=False, offset=start, duration=duration)
        y = np.atleast_2d(y).astype(np.float64)
        if y.shape[1] < count - 1:
            raise ValueError("requested segment extends beyond audio: %s" % path)
        if not np.isfinite(y).all():
            raise ValueError("non-finite audio samples")
        # Identical windows are compared. Decoder rounding of one sample is tolerated.
        y = y[:, :count - 1]
        rms = float(np.sqrt(np.mean(y ** 2)))
        peak = float(np.max(np.abs(y)))
        if rms < 1e-10:
            raise ValueError("silent segment cannot be level-matched: %s" % path)
        # RMS matching is deliberately labelled; it is not perceptual LUFS matching.
        gain = 10 ** (-20 / 20) / rms
        matched = y * gain
        freqs, power = welch(matched, fs=sr, nperseg=2048, axis=-1)
        power = power.mean(axis=0)
        edges = [(20, 120), (120, 500), (500, 4000), (4000, 16000)]
        energies = [float(power[(freqs >= a) & (freqs < b)].sum()) for a, b in edges]
        total = sum(energies)
        stereo = {"channels": int(y.shape[0]), "correlation": None, "side_mid_db": None}
        if y.shape[0] == 2:
            left, right = y
            mid, side = (left + right) / 2, (left - right) / 2
            if min(np.std(left), np.std(right)) > 1e-10:
                stereo["correlation"] = float(np.corrcoef(left, right)[0, 1])
            mid_rms, side_rms = np.sqrt(np.mean(mid ** 2)), np.sqrt(np.mean(side ** 2))
            if mid_rms > 0 and side_rms > 0:
                stereo["side_mid_db"] = float(20 * np.log10(side_rms / mid_rms))
        mono = matched.mean(axis=0)
        envelope = librosa.feature.rms(y=mono)[0]
        onset = librosa.onset.onset_detect(y=mono, sr=sr, units="time")
        return {"path": str(Path(path).resolve()),
                "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                "start_sec": start, "samples": int(y.shape[1]),
                "rms_dbfs": float(20 * np.log10(rms)),
                "sample_peak_dbfs": float(20 * np.log10(peak)),
                "crest_db": float(20 * np.log10(peak / rms)),
                "match_gain_db": float(20 * np.log10(gain)),
                "bands_pct": {"%d-%d" % e: 100 * v / total for e, v in zip(edges, energies)},
                "stereo": stereo, "onsets_sec": onset.tolist(),
                "rms_envelope_dbfs": (20 * np.log10(np.maximum(envelope, 1e-12))).tolist()}

    ref, own = profile(reference, reference_start), profile(mix, mix_start)
    return {"reference": ref, "mix": own, "sample_rate": sr,
            "duration_sec": (count - 1) / sr,
            "normalization": "RMS -20 dBFS in analysis only; NOT LUFS or perceptual loudness matching",
            "band_delta_pct": {k: own["bands_pct"][k] - ref["bands_pct"][k] for k in ref["bands_pct"]},
            "evidence": "decoded audio files", "listened": False,
            "limitations": "sample peak is not true peak; key/pitch and subjective musical quality not assessed; channel-mean downmix may cancel antiphase audio"}
