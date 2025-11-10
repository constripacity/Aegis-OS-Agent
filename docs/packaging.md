# Packaging and Release Guide

This document describes how the Aegis OS Agent builds offline desktop bundles.

## Quick build recap

1. Install dependencies:

```bash
python -m pip install -r requirements.txt
python -m pip install -r requirements-optional.txt
python -m pip install pyinstaller
```

2. Build using the helper script (detects your OS automatically):

```bash
python scripts/build_artifacts.py
```

3. Resulting bundles are stored in `dist/release/`:

- **Windows** – `AegisAgent.exe` signed optionally via SignTool (`/a` flag) after the build.
- **macOS** – `AegisAgent.app` wrapped as a `.dmg` (or `.zip` if `hdiutil` is unavailable). Sign via `codesign --deep --force` when certificates are present.
- **Linux** – `AegisAgent.AppImage` (PyInstaller one-file binary renamed for AppImage tooling). Optional signing supported via `gpg --detach-sign`.

4. Upload bundles to GitHub Releases. The release workflow (`.github/workflows/release.yml`) runs automatically for tags and posts artifacts together with SHA-256 sums.

## Manual PyInstaller invocation

If you need to customise options or debug, invoke PyInstaller directly:

```bash
pyinstaller --clean --noconfirm --name AegisAgent \
  --add-data "aegis/config/defaults.json:aegis/config" \
  aegis/main.py
```

This produces a platform-native bundle in `dist/`.

## Common troubleshooting

### Missing DLLs on Windows

Use `pyinstaller --collect-binaries package` to include optional dependencies that fail to load. Inspect the build log for `missing` markers.

### Gatekeeper blocks on macOS

Unsigned apps trigger "unverified developer" warnings. Inform testers to right-click the `.app`, select **Open**, and confirm. Provide signed builds when certificates become available.

### AppImage compatibility

The distributed AppImage is generated from a PyInstaller one-file binary for simplicity. To integrate with a full AppImage toolchain, run `appimagetool` against the extracted one-file bundle and replace the uploaded artifact.

### High-DPI scaling

Tk-based UI inherits system scale. On Windows, enable high DPI awareness by setting the `QT_ENABLE_HIGHDPI_SCALING=1` environment variable before launching if you observe blurry widgets.

### Optional extras

OCR, vision-based renaming, and tray integrations rely on optional dependencies listed in `requirements-optional.txt`. Install them when you need those features; the core agent remains lightweight without them.
