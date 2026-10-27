"""Export only reviewed source files; NEVER copy the development Git history."""
import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path


def prepare(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists():
        raise FileExistsError("New destination required; no release artifacts will be overwritten")
    files = []
    for directory in ("src", "fl_controller", "tests"):
        files += [p for p in (source / directory).rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix not in (".pyc", ".pyo")]
    for name in ("pyproject.toml", "LICENSE", "README.md", "requirements-system-tested.txt", "codex-mcp.example.toml",
                 "docs/实施前审计.md", "docs/inherited_tools.json", "docs/tool_catalog.json", "docs/CAPABILITIES.md",
                 "docs/WORKFLOW.md", "docs/TEST_RESULTS.md", "docs/ARCHITECTURE_CURRENT.md",
                 "docs/UI12_ACCEPTANCE.md", "docs/UI_PROFILES.md", "docs/DEV2_ACCEPTANCE.md", "docs/DEPENDENCIES.json", "docs/SECURITY_REVIEW.md", "docs/DEV2_GAPS.md"):
        files.append(source / name)
    for name in ("run_server.py", "diagnose.py", "build_acceptance_arrangement.py", "build_workflow_template.py",
                 "verify_mcp_local.py", "Start-Bridge.ps1", "Stop-Bridge.ps1", "prepare_public_release.py"):
        files.append(source / "scripts" / name)
    secret = re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{24,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
    private_path = re.compile(r"(?:[A-Za-z]:[\\/]Users[\\/](?!Public[\\/]|YOUR[\\/])[^\\/\s]+|[A-Za-z]:[\\/](?:WpSystem|文档|音乐)[\\/])")
    manifest = []
    for path in sorted(set(files)):
        if not path.is_file():
            raise FileNotFoundError(path.relative_to(source))
        data = path.read_bytes()
        text = data.decode("utf8")
        # The scanner's own regex is code, not an actual credential.
        if path.name != "prepare_public_release.py" and (secret.search(text) or private_path.search(text)):
            raise ValueError("Potential secret or personal path in " + str(path.relative_to(source)))
        manifest.append({"path": path.relative_to(source).as_posix(), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
    destination.mkdir(parents=True)
    for item in manifest:
        target = destination / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / item["path"], target)
    (destination / ".gitignore").write_text(".venv/\n__pycache__/\n*.py[cod]\n.pytest_cache/\n*.log\n.env*\nstate/\nbackups/\n*.flp\n*.wav\n*.mp3\n*.fst\n*.fxp\n*.egg-info/\n", encoding="utf8")
    (destination / "PUBLIC_MANIFEST.json").write_text(json.dumps({"schema": 1, "files": manifest,
        "excluded": ["development_git_history", "runtime_configuration", "personal_paths", "logs", "backups", "FLP/WAV", "commercial_presets"]}, indent=2), encoding="utf8")
    return {"files": len(manifest), "published": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("destination")
    args = parser.parse_args()
    print(json.dumps(prepare(Path(__file__).resolve().parents[1], args.destination)))
