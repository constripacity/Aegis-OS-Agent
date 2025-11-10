# Demo media placeholders

Binary demo recordings are not tracked in git to keep pull requests lightweight. To record your own
palette walkthrough GIF:

1. Launch Aegis with `aegis run --no-clipboard-vault` in a dedicated desktop workspace.
2. Start a screen recorder (e.g., OBS, ScreenToGif, or macOS QuickTime) and capture an 8–10 second clip
   of the command palette flow: summon the palette with the hotkey, run “summarize clipboard”, then
   trigger “clean desktop”.
3. Export the recording as `demo.gif` (max 2 MB) and place it in this folder.
4. The file is gitignored to keep pull requests binary-free, but local clones and external hosts can
   embed it with `![Aegis demo](examples/media/demo.gif)` if desired.

The application remains fully functional without the GIF—these instructions simply help contributors
recreate the media after cloning the repository.
