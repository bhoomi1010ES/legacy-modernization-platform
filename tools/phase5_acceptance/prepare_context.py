"""Prepare a bounded, redacted source context for the pinned Go/Fiber image."""
import asyncio
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT / "repo_workspaces" / "job_f7755169-0ecd-49ed-b1ca-80bab89e9711"
BUILD = Path(__file__).resolve().parent / "generated_context"
sys.path.insert(0, str(ROOT / "backend"))
from app.services.phase6_workspace import file_snapshot, git


async def main():
    if BUILD.exists():
        raise RuntimeError("Refusing to overwrite a prior characterization build context")
    if not WORKSPACE.is_dir():
        raise RuntimeError("The Go/Fiber job workspace is not available")
    source_commit = await git(WORKSPACE, "rev-parse", "HEAD")
    if await git(WORKSPACE, "status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError("Tracked source changes must be committed before the image can bind to a candidate revision")
    files = await file_snapshot(WORKSPACE, exclude_paths={"bin/main"})
    tracked = set(filter(None, (await git(WORKSPACE, "ls-files", "-z")).split("\x00")))
    if "bin/main" not in tracked:
        raise RuntimeError("The expected tracked Go executable is missing")
    excluded_path = WORKSPACE / "bin" / "main"
    if excluded_path.is_symlink() or getattr(excluded_path, "is_junction", lambda: False)() or not excluded_path.is_file() or WORKSPACE.resolve() not in excluded_path.resolve().parents:
        raise RuntimeError("The excluded Go executable is not a safe regular file in the job workspace")
    excluded_bytes = excluded_path.read_bytes()
    if len(excluded_bytes) <= 8 * 1048576:
        raise RuntimeError("The expected oversized tracked executable did not match the reviewed exclusion policy")
    excluded = [{"path": "bin/main", "size_bytes": len(excluded_bytes),
                 "sha256": hashlib.sha256(excluded_bytes).hexdigest(),
                 "reason": "Tracked prebuilt executable is excluded; the pinned Go/Fiber image builds the application from the bound source snapshot."}]
    hashes = {}
    content = {}
    total = 0
    for name, value in files.items():
        if isinstance(value, dict):
            import base64
            raw = base64.b64decode(value["data"], validate=True)
            if hashlib.sha256(raw).hexdigest() != value["sha256"]:
                raise RuntimeError("Snapshot binary hash mismatch")
        else:
            raw = value.encode("utf-8")
        total += len(raw)
        hashes[name] = hashlib.sha256(raw).hexdigest()
        content[name] = raw
    if total > 8 * 1048576:
        raise RuntimeError("Source-only workspace still exceeds the controller adapter limit")
    ordered_hashes = json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()
    manifest = {"source_commit": source_commit, "snapshot_sha256": hashlib.sha256(ordered_hashes).hexdigest(),
                "files": hashes, "excluded_files": excluded}
    BUILD.mkdir(parents=True)
    try:
        for name, raw in content.items():
            target = BUILD.joinpath(*Path(name).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        image = Path(__file__).resolve().parent / "image"
        shutil.copyfile(image / "adapter.py", BUILD / "adapter.py")
        shutil.copyfile(image / "Dockerfile", BUILD / "Dockerfile")
        (BUILD / ".dockerignore").write_text("", encoding="utf-8")
        (BUILD / "source-manifest.json").write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")))
    except Exception:
        shutil.rmtree(BUILD)
        raise
    print(json.dumps({"source_commit": source_commit, "source_files": len(files), "source_bytes": total,
                      "source_snapshot_sha256": manifest["snapshot_sha256"], "excluded": excluded,
                      "context": str(BUILD)}))


if __name__ == "__main__":
    asyncio.run(main())
