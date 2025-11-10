# Aegis Demo Walkthrough

This walkthrough shows a typical Aegis session without network access.

1. **Start the agent**
   ```bash
   aegis run --no-clipboard-vault
   ```
   The tray icon appears and the clipboard/desktop watchers begin polling.

2. **Copy an article snippet**
   - Copy a few paragraphs from a document.
   - Aegis detects the clipboard change and posts a notification that a summary is ready.
   - Opening the command palette and typing `summarize clipboard` shows the TL;DR in the toast area.

3. **Drop files on the Desktop**
   - Save `invoice.pdf` and `photo.png` to the Desktop.
   - Run `clean desktop` from the palette.
   - The files move into `~/Aegis/Archive/<YYYY-MM>/` with safe renames.

4. **Search clipboard history** (optional)
   - Enable the vault in Settings and set the environment variable:
     ```bash
     export AEGIS_VAULT_PASSPHRASE="demo-passphrase"
     ```
   - Copy a URL and run `find invoice` from the palette to see vault matches.

5. **Generate a report**
   ```bash
   aegis report --html
   ```
   A JSON and HTML report appear under `~/Aegis/Reports/` summarizing the actions.

6. **Headless mode**
   ```bash
   aegis headless --use-ollama
   ```
   The watchers run without UI, relying on Ollama if available for intent parsing and summaries.

