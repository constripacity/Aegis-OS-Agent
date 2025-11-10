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

Use `pyinstaller --collect-binaries package` to include optional dependencies that fail to load. Inspect the build log for `missing` markers. When SmartScreen flags the unsigned executable, instruct testers to choose **More info → Run anyway** or right-click the file, select **Properties**, and tick **Unblock** before the first launch.

### Gatekeeper on macOS

Unsigned apps trigger "unverified developer" warnings. Inform testers to right-click (or hold `Ctrl` and click) the `.app`, select **Open**, and confirm. For persistent deployments, sign with `codesign --deep --force` once Developer ID certificates are available.

### AppImage compatibility

The distributed AppImage uses the PyInstaller one-file binary for portability. To integrate with a full AppImage toolchain, extract the binary, populate an AppDir layout, and run `appimagetool` to regenerate the bundle. Remember to make the result executable via `chmod +x` after download.

### High-DPI scaling

Tk-based UI inherits system scale. On Windows, set `QT_ENABLE_HIGHDPI_SCALING=1` or enable **Override high DPI scaling** in the executable properties if widgets appear blurry. On macOS, adjust the display scaling in **System Settings → Displays** for crisper rendering.

### Optional extras

OCR, vision-based renaming, global hotkeys, and the tray icon rely on optional dependencies listed in `requirements-optional.txt` (`pynput`, `pystray`, `pillow`, `pytesseract`). Install them as needed—the core agent remains lightweight without them.
