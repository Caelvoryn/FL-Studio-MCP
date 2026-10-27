"""Durable, deliberately bounded workflow primitives. No GUI success guesses."""
from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import shutil
import time
import uuid
from pathlib import Path


class WorkflowError(RuntimeError):
    def __init__(self, code, message, **details):
        super().__init__(message)
        self.code, self.details = code, details

    def result(self):
        return {"ok": False, "error": {"code": self.code, "message": str(self), **self.details}}


def state_dir():
    return Path(os.environ.get("FLSTUDIO_MCP_STATE_DIR", str(Path.home() / ".flstudio-mcp-system")))


def json_value(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(k): ("[REDACTED]" if any(s in str(k).lower() for s in ("password", "token", "secret", "api_key")) else json_value(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    return value


@contextlib.contextmanager
def trace_mutation(tool, inputs):
    """Crash leaves durable 'running' evidence; no automatic replay on restart."""
    request_id = uuid.uuid4().hex
    path = state_dir() / "requests" / (request_id + ".json")
    entry = {"schema": 1, "request_id": request_id, "tool": tool,
             "input": json_value(inputs), "status": "running", "started_unix": time.time()}
    atomic_json(path, entry)
    try:
        yield entry
        entry["status"] = "verified" if entry.get("output", {}).get("verified") else "unverified"
    except Exception as exc:
        entry.update(status="execution_unknown", error={"type": type(exc).__name__, "message": str(exc)})
        raise
    finally:
        entry["ended_unix"] = time.time()
        atomic_json(path, entry)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temp.open("x", encoding="utf8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


@contextlib.contextmanager
def mutation_lock(timeout=5.0):
    """OS byte lock releases on process death. All candidate mutations cooperate.

    Cannot lock an unrelated legacy server or a human editing FL. Never delete
    the lock file: unlinking permits a second inode and breaks mutual exclusion.
    """
    if not math.isfinite(timeout) or not 0 <= timeout <= 60:
        raise WorkflowError("INVALID_ARGUMENT", "Lock timeout must be finite, 0..60 seconds")
    folder = state_dir()
    folder.mkdir(parents=True, exist_ok=True)
    stream = (folder / "mutation.lock").open("a+b")
    stream.seek(0, 2)
    if stream.tell() == 0:
        stream.write(b"0")
        stream.flush()
    deadline = time.monotonic() + timeout
    while True:
        try:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except OSError:
            if time.monotonic() >= deadline:
                stream.close()
                raise WorkflowError("BUSY", "Another candidate automation owns the mutation lock")
            time.sleep(.05)
    try:
        yield
    finally:
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        stream.close()


def copy_exclusive(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_file():
        raise WorkflowError("FILE_NOT_FOUND", "Source does not exist", path=str(source))
    if source == destination:
        raise WorkflowError("OVERWRITE_REFUSED", "Source and destination must differ")
    destination.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with source.open("rb") as src, destination.open("xb") as dst:
            created = True
            shutil.copyfileobj(src, dst)
            dst.flush()
            os.fsync(dst.fileno())
        a, b = digest(source), digest(destination)
        if a != b:
            raise WorkflowError("COPY_MISMATCH", "Source changed during copy, or destination differs")
        return {"ok": True, "verified": True, "source": str(source),
                "destination": str(destination), "sha256": b, "bytes": destination.stat().st_size}
    except FileExistsError as exc:
        raise WorkflowError("OVERWRITE_REFUSED", "Destination already exists", path=str(destination)) from exc
    except Exception:
        if created:
            destination.unlink(missing_ok=True)  # only our incomplete newly created file
        raise


class Journal:
    """Persist intent BEFORE effects. An interrupted step is never auto-replayed."""
    def __init__(self, job_id):
        if not job_id or len(job_id) > 80 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in job_id):
            raise WorkflowError("INVALID_ARGUMENT", "job_id must contain 1..80 ASCII letters, digits, _ or -")
        self.path = state_dir() / "jobs" / (job_id + ".json")

    def load(self):
        if self.path.exists():
            return json.loads(self.path.read_text(encoding="utf8"))
        return {"schema": 1, "steps": {}}

    def step(self, name, inputs, action, verify):
        request_hash = hashlib.sha256(json.dumps(inputs, sort_keys=True, allow_nan=False).encode()).hexdigest()
        with mutation_lock():
            state = self.load()
            old = state["steps"].get(name)
            if old:
                if old["request_hash"] != request_hash:
                    raise WorkflowError("IDEMPOTENCY_CONFLICT", "Same step name with different inputs")
                if old["status"] == "verified":
                    if not verify(old["result"]):
                        raise WorkflowError("STALE_EVIDENCE", "Previously verified output no longer matches")
                    return {**old["result"], "replayed": False, "cached": True}
                raise WorkflowError("RECOVERY_REQUIRED", "Inspect interrupted/failed step before a new version", step=old)
            entry = {"status": "running", "request_hash": request_hash, "started_unix": time.time()}
            state["steps"][name] = entry
            atomic_json(self.path, state)
            try:
                result = action()
                if not verify(result):
                    raise WorkflowError("VERIFY_FAILED", "Independent postcondition failed")
                entry.update(status="verified", result=result, ended_unix=time.time())
                atomic_json(self.path, state)
                return result
            except Exception as exc:
                entry.update(status="failed", error={"type": type(exc).__name__, "message": str(exc)}, ended_unix=time.time())
                atomic_json(self.path, state)
                raise


def audio_integrity(path, minimum_seconds=.05, maximum_seconds=3600.0):
    """Read every actual PCM sample, rather than trusting a render notification."""
    import numpy as np
    import soundfile as sf
    if not all(math.isfinite(x) for x in (minimum_seconds, maximum_seconds)) or not 0 <= minimum_seconds <= maximum_seconds:
        raise WorkflowError("INVALID_ARGUMENT", "Invalid duration bounds")
    path = Path(path)
    if not path.is_file():
        raise WorkflowError("FILE_NOT_FOUND", "Audio does not exist", path=str(path))
    original_stat = path.stat()
    try:
        with sf.SoundFile(path) as stream:
            frames, rate, channels, subtype = len(stream), stream.samplerate, stream.channels, stream.subtype
            duration = frames / rate
            if not minimum_seconds <= duration <= maximum_seconds:
                raise WorkflowError("AUDIO_DURATION", "Audio duration outside expected range", duration_seconds=duration)
            peak, energy, count, clipped, nonzero, silent_frames = 0., 0., 0, 0, 0, 0
            for block in stream.blocks(blocksize=65536, dtype="float64", always_2d=True):
                if not np.isfinite(block).all():
                    raise WorkflowError("AUDIO_NONFINITE", "NaN or infinity in actual PCM")
                absolute = np.abs(block)
                peak = max(peak, float(absolute.max(initial=0)))
                energy += float(np.sum(block * block))
                count += block.size
                clipped += int(np.count_nonzero(absolute >= 1))
                nonzero += int(np.count_nonzero(absolute > 1e-6))
                silent_frames += int(np.count_nonzero(absolute.max(axis=1) < 1e-5))
    except WorkflowError:
        raise
    except Exception as exc:
        raise WorkflowError("AUDIO_DECODE", str(exc)) from exc
    if count == 0 or nonzero == 0:
        raise WorkflowError("AUDIO_SILENT", "Rendered audio is empty or effectively silent")
    sha256 = digest(path)
    final_stat = path.stat()
    if (original_stat.st_ino, original_stat.st_size, original_stat.st_mtime_ns) != (final_stat.st_ino, final_stat.st_size, final_stat.st_mtime_ns):
        raise WorkflowError("FILE_CHANGED", "Audio changed while it was being verified; wait for rendering to finish")
    return {"ok": clipped == 0, "verified": True, "sha256": sha256, "frames": frames,
            "sample_rate": rate, "channels": channels, "subtype": subtype, "duration_seconds": duration,
            "sample_peak_dbfs": 20 * math.log10(peak), "rms_dbfs": 10 * math.log10(energy / count),
            "clipped_samples": clipped, "silent_frame_fraction": silent_frames / frames,
            "subjective_listening": "not_performed", "true_peak": "not_measured", "lufs": "not_measured"}


def compare_audio(first, second):
    import numpy as np
    import soundfile as sf
    a_info, b_info = audio_integrity(first), audio_integrity(second)
    if (a_info["frames"], a_info["channels"], a_info["sample_rate"]) != (b_info["frames"], b_info["channels"], b_info["sample_rate"]):
        return {"ok": True, "classification": "format_or_duration_change", "first": a_info, "second": b_info}
    peak, error, count = 0., 0., 0
    with sf.SoundFile(first) as a, sf.SoundFile(second) as b:
        for x in a.blocks(blocksize=65536, dtype="float64", always_2d=True):
            y = b.read(len(x), dtype="float64", always_2d=True)
            delta = x - y
            peak = max(peak, float(np.abs(delta).max(initial=0)))
            error += float(np.sum(delta * delta))
            count += delta.size
    return {"ok": True, "classification": "exact_pcm" if peak == 0 else "numeric_difference",
            "max_absolute_difference": peak, "difference_rms": math.sqrt(error / count),
            "first": a_info, "second": b_info,
            "limitation": "Numeric difference alone cannot establish perceptual or musical structure change"}
