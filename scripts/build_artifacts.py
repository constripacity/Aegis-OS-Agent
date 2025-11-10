"""Build platform-specific artifacts using PyInstaller."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
RELEASE = DIST / "release"


def os_pathsep() -> str:
    return ";" if sys.platform.startswith("win") else ":"


def run(cmd: List[str]) -> None:
    result = subprocess.run(cmd, cwd=ROOT, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"Command failed: {' '.join(cmd)}\n{result.stdout}\n{result.stderr}")


def ensure_clean() -> None:
    if RELEASE.exists():
        shutil.rmtree(RELEASE)
    RELEASE.mkdir(parents=True, exist_ok=True)


def build_windows() -> Path:
    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--clean",
            "--noconfirm",
            "--windowed",
            "--name",
            "AegisAgent",
            "--add-data",
            f"aegis/config/defaults.json{os_pathsep()}aegis/config",
            "aegis/main.py",
        ]
    )
    artifact = RELEASE / "AegisAgent.exe"
    built = DIST / "AegisAgent" / "AegisAgent.exe"
    shutil.copy2(built, artifact)
    return artifact


def build_macos() -> Path:
    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--clean",
            "--noconfirm",
            "--windowed",
            "--name",
            "AegisAgent",
            "--add-data",
            "aegis/config/defaults.json:aegis/config",
            "aegis/main.py",
        ]
    )
    app_dir = DIST / "AegisAgent.app"
    target = RELEASE / "AegisAgent-macOS.dmg"
    if shutil.which("hdiutil"):
        dmg_src = RELEASE / "AegisAgent"
        if dmg_src.exists():
            shutil.rmtree(dmg_src)
        shutil.copytree(app_dir, dmg_src)
        run(["hdiutil", "create", "-volname", "AegisAgent", "-srcfolder", str(dmg_src), str(target)])
        shutil.rmtree(dmg_src)
    else:
        archive = RELEASE / "AegisAgent-macOS"
        shutil.make_archive(
            str(archive),
            "zip",
            root_dir=app_dir.parent,
            base_dir=app_dir.name,
        )
        return archive.with_suffix(".zip")
    return target


def build_linux() -> Path:
    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--onefile",
            "--noconfirm",
            "--name",
            "AegisAgent",
            "--add-data",
            "aegis/config/defaults.json:aegis/config",
            "aegis/main.py",
        ]
    )
    binary = DIST / "AegisAgent"
    target = RELEASE / "AegisAgent.AppImage"
    shutil.copy2(binary, target)
    target.chmod(0o755)
    return target


def main() -> None:
    ensure_clean()
    if sys.platform.startswith("win"):
        build = build_windows()
    elif sys.platform == "darwin":
        build = build_macos()
    else:
        build = build_linux()
    print(f"Created artifact: {build}")


if __name__ == "__main__":
    main()
