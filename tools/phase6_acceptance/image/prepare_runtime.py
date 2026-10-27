"""Copy only the local CPython runtime and its shared libraries into a clean root."""

import logging
from pathlib import Path
import shutil
import subprocess
import sys

logger = logging.getLogger(__name__)


def main() -> None:
    try:
        root = Path("/phase6-runtime")
        stdlib = (
            Path(sys.base_prefix)
            / "lib"
            / f"python{sys.version_info.major}.{sys.version_info.minor}"
        )
        target = root / str(stdlib).lstrip("/")
        shutil.copytree(
            stdlib,
            target,
            ignore=shutil.ignore_patterns(
                "site-packages",
                "__pycache__",
                "*.pyc",
                "test",
                "tests",
                "idlelib",
                "tkinter",
                "ensurepip",
            ),
        )
        binary = Path(sys.executable).resolve()
        binaries = [binary, *stdlib.glob("lib-dynload/*.so")]
        libraries = set()
        for item in binaries:
            result = subprocess.run(
                ["ldd", str(item)], check=True, capture_output=True, text=True
            )
            for line in result.stdout.splitlines():
                for word in line.split():
                    if word.startswith("/"):
                        libraries.add(Path(word))
        for item in [binary, *libraries]:
            destination = root / str(item).lstrip("/")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item.resolve(), destination)
        bindir = root / "usr/local/bin"
        (bindir / "python").symlink_to(binary.name)
        (bindir / "python3").symlink_to(binary.name)
        for directory in ("tmp", "work", "acceptance", "legacy", "etc"):
            (root / directory).mkdir(parents=True, exist_ok=True)
        (root / "tmp").chmod(0o1777)
        (root / "work").chmod(0o1777)
    except Exception:
        logger.exception("prepare_runtime failed")
        raise


if __name__ == "__main__":
    main()
