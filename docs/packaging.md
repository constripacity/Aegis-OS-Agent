# Packaging

Aegis is a Python application first. `pip install aegis-os-agent` (or
`pip install -e .` from a clone) is the supported path and the one the tests
cover. Everything below is about producing a binary for people who do not have
Python, which is a convenience, not the primary distribution channel.

> **Status.** The PyInstaller build in `scripts/build_artifacts.py` has not been
> run as part of this revision — the environment the work was done in had no
> network access, so PyInstaller could not be installed. The script is
> unchanged and previously produced artifacts, but treat a first build after
> checkout as unverified until CI publishes one. `.github/workflows/release.yml`
> runs it on tags for all three platforms; a green run there is the real proof.

## Building locally

```bash
python -m pip install -r requirements.txt
python -m pip install pyinstaller
python scripts/build_artifacts.py
```

The script detects the host OS and writes to `dist/release/`:

| Platform | Artifact | Notes |
| --- | --- | --- |
| Windows | `AegisAgent.exe` | Windowed build, no console |
| macOS | `AegisAgent.dmg`, or `.zip` when `hdiutil` is missing | Wraps `AegisAgent.app` |
| Linux | `AegisAgent.AppImage` | A PyInstaller one-file binary under an AppImage name |

You can only build for the platform you are on. PyInstaller does not
cross-compile, which is why the release workflow uses a three-OS matrix.

The Linux artifact is named `.AppImage` for familiarity but is not produced by
`appimagetool`; it is a self-extracting PyInstaller binary. If you need a real
AppImage, run `appimagetool` against the extracted bundle and replace the file.

## Signing

**Released binaries are not signed.** No Apple Developer ID and no Windows
code-signing certificate exists for this project, so:

- macOS shows *"cannot be opened because it is from an unidentified developer"*.
  Right-click the app, choose **Open**, and confirm. There is no way around this
  short of a paid certificate, and this project does not have one.
- Windows SmartScreen shows *"Windows protected your PC"*. Choose **More info**
  then **Run anyway**.

If you have certificates and want signed builds for your own distribution:

```bash
# macOS
codesign --force --options runtime --sign "Developer ID Application: NAME (TEAMID)" dist/release/AegisAgent.app
xcrun notarytool submit dist/release/AegisAgent.dmg --keychain-profile PROFILE --wait

# Windows
signtool sign /a /fd sha256 /tr http://timestamp.digicert.com /td sha256 dist\release\AegisAgent.exe

# Linux
gpg --detach-sign --armor dist/release/AegisAgent.AppImage
```

Do not add these to the release workflow without the corresponding secrets;
a signing step that silently no-ops is worse than no signing step, because the
release notes then claim something untrue.

## Verifying a download

Every release publishes `SHA256SUMS.txt`. Check it before running anything:

```bash
shasum -a 256 -c SHA256SUMS.txt --ignore-missing   # macOS / Linux
certutil -hashfile AegisAgent.exe SHA256           # Windows, compare by eye
```

## Manual PyInstaller invocation

For debugging build problems:

```bash
pyinstaller --clean --noconfirm --windowed --name AegisAgent \
  --add-data "aegis/config/defaults.json:aegis/config" \
  aegis/main.py
```

Use `;` instead of `:` in `--add-data` on Windows.

## Known build issues

**`tkinter` missing from the bundle.** The desktop UI needs Tk, which ships
with python.org builds but not with every distro package. On Debian and Ubuntu,
`sudo apt install python3-tk` before building. Without it the binary builds and
the CLI works, but `aegis run` and `aegis palette` exit with a message saying
the UI is unavailable — which is the intended behaviour, not a crash.

**Optional desktop extras.** Clipboard access, the tray icon, the global
hotkey, and notifications come from the `desktop` extra
(`pip install -e ".[desktop]"`), declared in `pyproject.toml`. There is no
`requirements-optional.txt`; extras live in `pyproject.toml` and nowhere else.
Install them before building if you want a binary with the tray icon.
