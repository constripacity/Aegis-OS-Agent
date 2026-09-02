"""Command line entry point.

The command surface follows the safety model: `plan` shows what would change,
`apply` performs it after a confirmation, `history` lists what happened, and
`undo` reverses it. Nothing here moves a file without a plan first.
"""
from __future__ import annotations

import json
import logging
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import click

from .config.schema import AppConfig, config_dir, load_config, save_config
from .core.actions import ActionExecutor
from .core.bus import EventBus
from .core.intents import IntentRouter, describe
from .core.journal import ActionKind
from .core.notifier import Notifier
from .core.plan import Plan, PlannedAction
from .core.scheduler import SchedulerService
from .core.utils import human_size, open_path
from .reports.exporter import ReportExporter
from .watchers.clipboard import ClipboardWatcher
from .watchers.filesystem import DirectoryWatcher

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .ui.palette import CommandPalette
    from .ui.settings import SettingsWindow
    from .ui.system import HotkeyManager, TrayController


class UIUnavailable(RuntimeError):
    """The desktop UI cannot be loaded on this machine."""


def _load_ui():
    """Import the Tk-based UI lazily.

    Importing it at module scope meant the whole command line — `aegis plan`,
    `aegis undo`, `aegis history` — failed with ImportError on any machine
    without tkinter, including most Linux servers and minimal containers. The
    agent's headless surface must not depend on a GUI toolkit.
    """
    try:
        from .ui.palette import CommandPalette
        from .ui.settings import SettingsWindow
        from .ui.system import HotkeyManager, TrayController
    except ImportError as exc:  # pragma: no cover - depends on the host
        raise UIUnavailable(
            f"the desktop interface needs Python's tkinter, which is not available "
            f"here ({exc}).\n"
            "  Debian/Ubuntu:  sudo apt install python3-tk\n"
            "  Fedora:         sudo dnf install python3-tkinter\n"
            "  macOS/Windows:  reinstall Python from python.org\n"
            "Everything else works without it: try 'aegis plan' or 'aegis headless'."
        ) from exc
    return CommandPalette, SettingsWindow, HotkeyManager, TrayController


def _first_run_wizard():
    from .ui.first_run import FirstRunWizard

    return FirstRunWizard

LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")


class Application:
    """Runtime container for top-level services."""

    def __init__(self, config: AppConfig, use_ui: bool = True) -> None:
        self.config = config
        self._shutdown = threading.Event()
        self.bus = EventBus()
        self.notifier = Notifier()
        self.action_executor = ActionExecutor(self.bus, self.notifier, config)
        self.intent_router = IntentRouter(self.bus, self.action_executor, config)
        self.scheduler = SchedulerService(config, self.bus, self.action_executor)
        self.clipboard_watcher = ClipboardWatcher(
            bus=self.bus,
            config=config,
        )
        self.desktop_watcher: DirectoryWatcher | None = None
        self.downloads_watcher: DirectoryWatcher | None = None
        if config.watchers.desktop:
            self.desktop_watcher = DirectoryWatcher(
                root=Path(config.desktop_path).expanduser(),
                bus=self.bus,
                config=config,
                label="desktop",
            )
        if config.watchers.downloads:
            self.downloads_watcher = DirectoryWatcher(
                root=Path(config.downloads_path).expanduser(),
                bus=self.bus,
                config=config,
                label="downloads",
            )
        self.palette: CommandPalette | None = None
        self.settings_window: SettingsWindow | None = None
        self.tray: TrayController | None = None
        self.hotkey: HotkeyManager | None = None
        if use_ui:
            palette_cls, settings_cls, hotkey_cls, tray_cls = _load_ui()
            self.palette = palette_cls(self.bus, self.intent_router, config)
            self.settings_window = settings_cls(config, self._on_config_updated)
            self.tray = tray_cls(
                show_palette=self._show_palette,
                show_settings=self._show_settings,
                toggle_watchers=self._toggle_watchers,
                open_vault=self._open_vault,
                quit_app=self._quit,
            )
            self.hotkey = hotkey_cls(config.hotkey, self._show_palette)

    def wait(self) -> None:
        """Block until something asks the agent to stop.

        `aegis run` used to call `start()` and then fall straight into its
        `finally: app.stop()`, because every service here starts a background
        thread and returns immediately. The result was that the command started
        the watchers, the tray and the palette, tore all of them down again, and
        exited — so the agent had never actually run. This is the missing half.
        """
        try:
            while not self._shutdown.wait(1.0):
                pass
        except KeyboardInterrupt:  # pragma: no cover - interactive
            pass

    def request_shutdown(self) -> None:
        self._shutdown.set()

    def start(self, headless: bool = False) -> None:
        """Start all background services."""

        LOGGER.info("Starting Aegis services (headless=%s)", headless)
        self.scheduler.start()
        self.clipboard_watcher.start()
        if self.desktop_watcher:
            self.desktop_watcher.start()
        if self.downloads_watcher:
            self.downloads_watcher.start()
        if not headless and self.palette:
            self.palette.run()
        if not headless and self.hotkey:
            self.hotkey.start()
        if not headless and self.tray:
            self.tray.start()

    def stop(self) -> None:
        """Stop all services gracefully."""

        LOGGER.info("Stopping Aegis services")
        self.clipboard_watcher.stop()
        if self.desktop_watcher:
            self.desktop_watcher.stop()
        if self.downloads_watcher:
            self.downloads_watcher.stop()
        self.scheduler.stop()
        if self.tray:
            self.tray.stop()
        if self.hotkey:
            self.hotkey.stop()
        self.action_executor.vault.close()

    # UI callbacks ---------------------------------------------------------
    def _show_palette(self) -> None:
        if self.palette:
            self.palette.show()

    def _show_settings(self) -> None:
        if self.settings_window:
            self.settings_window.show()

    def _toggle_watchers(self) -> None:
        if self.action_executor.watchers_active():
            self.action_executor.pause_watchers(30)
        else:
            self.action_executor.resume_watchers()

    def _open_vault(self) -> None:
        vault = self.action_executor.vault
        if not vault.enabled:
            self.notifier.notify("Clipboard vault is disabled", level="warning")
            return
        location = vault.location
        if location.exists():
            open_path(location.parent)
        else:
            self.notifier.notify("Clipboard vault not initialized", level="warning")

    def _on_config_updated(self, config: AppConfig) -> None:
        self.config.hotkey = config.hotkey
        if self.hotkey:
            self.hotkey.update(config.hotkey)

    def _quit(self) -> None:
        # Signal rather than raising: this runs on the tray's own thread, where
        # a SystemExit would be swallowed and the main thread would keep waiting.
        self.request_shutdown()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _executor(config: AppConfig) -> tuple[EventBus, ActionExecutor, IntentRouter]:
    """Build the object graph needed for a one-shot command."""
    bus = EventBus()
    executor = ActionExecutor(bus, Notifier(), config)
    router = IntentRouter(bus, executor, config)
    return bus, executor, router


def _echo_plan(plan) -> None:
    click.echo(plan.render())
    if plan:
        click.echo("")
        click.echo("Apply it with:  aegis apply")


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(package_name="aegis-os-agent", prog_name="aegis")
@click.option("--config", "config_path", type=click.Path(path_type=Path), default=None,
              help="Use this configuration file instead of the default")
@click.option("--log-level", default="WARNING",
              type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]),
              help="How much to print")
@click.pass_context
def cli(ctx: click.Context, config_path: Path | None, log_level: str) -> None:
    """Aegis — a local-first agent for your own files and clipboard.

    Everything that changes a file shows you a plan first, records what it did,
    and can be undone.
    """
    logging.getLogger().setLevel(getattr(logging, log_level))
    target_path = config_path or config_dir() / "config.json"
    config_exists = target_path.exists()
    config = load_config(config_path)

    # The first-run wizard is interactive. Running it because someone typed
    # `aegis --help` on a fresh machine is hostile, so it only runs for
    # commands that actually need a configured agent, and only on a terminal.
    needs_config = ctx.invoked_subcommand in {"run", "headless", "palette", "setup"}
    if not config_exists and needs_config and sys.stdin.isatty():
        config = _first_run_wizard()(config, target_path).run()
    elif not config_exists and needs_config:
        click.echo(
            "No configuration found and this is not an interactive terminal. "
            f"Using defaults. Run 'aegis setup' to create {target_path}.",
            err=True,
        )
    ctx.obj = {"config": config, "config_path": target_path}


# -- planning ---------------------------------------------------------------
@cli.command()
@click.argument("folder", type=click.Choice(["downloads", "desktop"]), default="downloads")
@click.option("--recursive", is_flag=True, help="Also look in subfolders")
@click.option("--json", "as_json", is_flag=True, help="Emit the plan as JSON")
@click.pass_context
def plan(ctx: click.Context, folder: str, recursive: bool, as_json: bool) -> None:
    """Show what tidying FOLDER would change. Changes nothing."""
    config: AppConfig = ctx.obj["config"]
    _, executor, _ = _executor(config)
    built = executor.organizer.plan(
        executor._folder_path(folder), recursive=recursive, trigger=f"cli:plan:{folder}"
    )
    executor._last_plan = built
    _save_pending(config, built)
    if as_json:
        click.echo(json.dumps(built.to_dict(), indent=2))
    else:
        _echo_plan(built)
    executor.close()


@cli.command()
@click.option("--yes", is_flag=True, help="Do not ask for confirmation")
@click.pass_context
def apply(ctx: click.Context, yes: bool) -> None:
    """Apply the plan from the last `aegis plan`."""
    config: AppConfig = ctx.obj["config"]
    _, executor, _ = _executor(config)
    pending = _load_pending(config, executor)
    if pending is None or not pending:
        click.echo("There is no plan to apply. Run 'aegis plan' first.", err=True)
        executor.close()
        raise SystemExit(1)

    click.echo(pending.render(limit=10))
    if not yes and not click.confirm(f"\nApply these {len(pending)} change(s)?", default=False):
        click.echo("Nothing was changed.")
        executor.close()
        return

    executor._last_plan = pending
    report = executor.apply_last_plan()
    _clear_pending(config)
    if report is not None:
        click.echo(report.describe())
        if not report.ok:
            executor.close()
            raise SystemExit(1)
    executor.close()


@cli.command()
@click.argument("batch_id", required=False)
@click.option("--force", is_flag=True, help="Undo even if a file changed since it moved")
@click.pass_context
def undo(ctx: click.Context, batch_id: str | None, force: bool) -> None:
    """Reverse a batch of changes (default: the most recent)."""
    config: AppConfig = ctx.obj["config"]
    _, executor, _ = _executor(config)
    report = executor.undo(batch_id, force=force) if batch_id else executor.undo_last()
    if report is None:
        executor.close()
        raise SystemExit(1)
    click.echo(report.describe())
    executor.close()
    if not report.ok:
        raise SystemExit(1)


@cli.command()
@click.option("--limit", default=20, show_default=True, help="How many batches to show")
@click.pass_context
def history(ctx: click.Context, limit: int) -> None:
    """Show everything Aegis has changed, and what can still be undone."""
    config: AppConfig = ctx.obj["config"]
    _, executor, _ = _executor(config)
    lines = executor.history(limit=limit)
    if not lines:
        click.echo("Aegis has not changed anything yet.")
    else:
        for line in lines:
            click.echo(line)
        click.echo("")
        click.echo("Undo any of them with:  aegis undo <id>")
    executor.close()


# -- surveys ----------------------------------------------------------------
@cli.command(name="large")
@click.argument("folder", type=click.Choice(["downloads", "desktop"]), default="downloads")
@click.option("--limit", default=15, show_default=True)
@click.pass_context
def large(ctx: click.Context, folder: str, limit: int) -> None:
    """List the biggest files in FOLDER."""
    config: AppConfig = ctx.obj["config"]
    _, executor, _ = _executor(config)
    rows = executor.large_files(folder, limit=limit)
    if not rows:
        click.echo(f"Nothing found in your {folder} folder.")
    for path, size in rows:
        click.echo(f"{human_size(size):>10}  {path}")
    executor.close()


@cli.command(name="duplicates")
@click.argument("folder", type=click.Choice(["downloads", "desktop"]), default="downloads")
@click.pass_context
def duplicates(ctx: click.Context, folder: str) -> None:
    """Find files with identical contents. Deletes nothing."""
    config: AppConfig = ctx.obj["config"]
    _, executor, _ = _executor(config)
    groups = executor.find_duplicates(folder)
    if not groups:
        click.echo("No duplicates found.")
    for group in groups:
        size = group[0].stat().st_size
        wasted = human_size(size * (len(group) - 1))
        click.echo(f"\n{len(group)} copies of {human_size(size)} ({wasted} recoverable):")
        for path in group:
            click.echo(f"    {path}")
    if groups:
        click.echo("\nAegis does not delete anything. Remove the copies you do not want yourself.")
    executor.close()


# -- clipboard --------------------------------------------------------------
@cli.command(name="find")
@click.argument("query", nargs=-1, required=True)
@click.pass_context
def find(ctx: click.Context, query: tuple) -> None:
    """Search saved clipboard history for QUERY."""
    config: AppConfig = ctx.obj["config"]
    _, executor, _ = _executor(config)
    results = executor.search_vault(" ".join(query))
    for index, content in enumerate(results, start=1):
        preview = content.replace("\n", " ")[:200]
        click.echo(f"{index:2}. {preview}")
    if not results:
        click.echo("Nothing matched.")
    executor.close()


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show what Aegis is configured to do and whether the vault is working."""
    config: AppConfig = ctx.obj["config"]
    _, executor, _ = _executor(config)
    click.echo(f"Config file      {ctx.obj['config_path']}")
    click.echo(f"Desktop          {config.desktop_path}  (watch: {config.watchers.desktop})")
    click.echo(f"Downloads        {config.downloads_path}  (watch: {config.watchers.downloads})")
    click.echo(f"Archive          {config.archive_root}")
    click.echo(f"Quarantine       {config.quarantine_root}")
    click.echo(f"Action journal   {executor.journal.path}")
    click.echo(executor.vault_status())
    model = (
        f"on — {config.ollama_model} at {config.ollama_url}"
        if config.use_ollama
        else "off (using the built-in summariser)"
    )
    click.echo(f"Local model      {model}")
    batches = executor.journal.batches()
    click.echo(f"Changes recorded {len(batches)} batch(es)"
               + (f", most recent {batches[0].timestamp}" if batches else ""))
    executor.close()


@cli.command(name="do")
@click.argument("text", nargs=-1, required=True)
@click.option("--yes", is_flag=True, help="Do not ask before a destructive command")
@click.pass_context
def do(ctx: click.Context, text: tuple, yes: bool) -> None:
    """Run a command written the way you would say it.

    Anything that changes files still produces a plan you must apply.
    """
    config: AppConfig = ctx.obj["config"]
    _, executor, router = _executor(config)
    phrase = " ".join(text)
    intent = router.parse(phrase)
    if not intent.is_understood:
        click.echo(f"I don't understand {phrase!r}.", err=True)
        if intent.suggestions:
            click.echo(f"Did you mean: {', '.join(intent.suggestions)}?", err=True)
        click.echo("Run 'aegis do help' for the full list.", err=True)
        executor.close()
        raise SystemExit(1)

    # The palette asks before anything destructive; the CLI did not, so
    # `aegis do "wipe vault"` deleted the whole clipboard history without a
    # word. A confirmation that exists in one entry point and not the other is
    # not a confirmation.
    if intent.is_destructive and not yes:
        description = describe(intent.name)
        if not click.confirm(f"{description}. This cannot be undone. Continue?", default=False):
            click.echo("Nothing was changed.")
            executor.close()
            return

    result = router.dispatch(intent)
    if hasattr(result, "render"):
        _save_pending(config, result)
        _echo_plan(result)
    elif hasattr(result, "describe"):
        click.echo(result.describe())
    elif isinstance(result, list):
        for item in result:
            click.echo(item)
    elif result is not None:
        click.echo(result)
    executor.close()


# -- lifecycle --------------------------------------------------------------
@cli.command()
@click.pass_context
def setup(ctx: click.Context) -> None:
    """Create or update the configuration file."""
    config: AppConfig = ctx.obj["config"]
    path: Path = ctx.obj["config_path"]
    updated = _first_run_wizard()(config, path).run()
    save_config(updated, path)
    click.echo(f"Configuration written to {path}")


@cli.command()
@click.option("--use-ollama/--no-use-ollama", default=None, help="Override the local-model setting")
@click.option(
    "--no-clipboard-vault", is_flag=True, default=False,
    help="Do not record the clipboard",
)
@click.pass_context
def run(ctx: click.Context, use_ollama: bool | None, no_clipboard_vault: bool) -> None:
    """Start the agent with its window and tray icon."""
    config: AppConfig = ctx.obj["config"]
    if use_ollama is not None:
        config.use_ollama = use_ollama
    if no_clipboard_vault:
        config.clipboard_vault.enabled = False

    try:
        app = Application(config, use_ui=True)
    except UIUnavailable as exc:
        click.echo(f"error: {exc}", err=True)
        raise SystemExit(1) from None
    try:
        app.start(headless=False)
        click.echo("Aegis is running. Use the tray icon or press Ctrl-C to stop.")
        app.wait()
    except KeyboardInterrupt:  # pragma: no cover - interactive
        click.echo("\nStopping.")
    finally:
        app.stop()


@cli.command()
@click.pass_context
def headless(ctx: click.Context) -> None:
    """Start the agent with no window (for a login item or a service)."""
    config: AppConfig = ctx.obj["config"]
    app = Application(config, use_ui=False)
    try:
        app.start(headless=True)
        click.echo("Aegis is running with no window. Press Ctrl-C to stop.")
        app.wait()
    except KeyboardInterrupt:  # pragma: no cover - interactive
        click.echo("\nStopping.")
    finally:
        app.stop()


@cli.command()
@click.pass_context
def palette(ctx: click.Context) -> None:
    """Open the command palette on its own."""
    config: AppConfig = ctx.obj["config"]
    bus, executor, router = _executor(config)
    palette_cls, _, _, _ = _load_ui()
    palette_cls(bus, router, config).run()
    executor.close()


@cli.command()
@click.option("--html", "export_html", is_flag=True, help="Also write an HTML report")
@click.pass_context
def report(ctx: click.Context, export_html: bool) -> None:
    """Write a report of recent activity."""
    config: AppConfig = ctx.obj["config"]
    click.echo(ReportExporter(config).export_latest(include_html=export_html))


@cli.command(name="dump-config")
@click.option("--output", type=click.Path(path_type=Path), default=None)
@click.pass_context
def dump_config(ctx: click.Context, output: Path | None) -> None:
    """Print or save the effective configuration."""
    config: AppConfig = ctx.obj["config"]
    if output is None:
        click.echo(config.json(indent=2))
        return
    output.write_text(config.json(indent=2), encoding="utf-8")
    click.echo(f"Configuration written to {output}")


# -- pending-plan persistence ----------------------------------------------
# `aegis plan` and `aegis apply` are separate processes, so the plan has to
# survive between them. It is stored next to the journal, and re-validated on
# load: a plan whose sources have moved is refused rather than acted on.
def _pending_path(config: AppConfig) -> Path:
    return Path(config.reports_root).expanduser() / "pending-plan.json"


def _save_pending(config: AppConfig, built) -> None:
    path = _pending_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(built.to_dict(), indent=2), encoding="utf-8")


def _clear_pending(config: AppConfig) -> None:
    _pending_path(config).unlink(missing_ok=True)


def _load_pending(config: AppConfig, executor: ActionExecutor):
    path = _pending_path(config)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    restored = Plan(title=data.get("title", "Plan"), trigger=data.get("trigger", "cli"))
    for item in data.get("actions", []):
        source = Path(item["source"])
        if not source.exists():
            restored.skipped.append((source, "no longer there; skipped"))
            continue
        restored.actions.append(
            PlannedAction(
                kind=ActionKind(item.get("kind", "move")),
                source=source,
                destination=Path(item["destination"]),
                rule=item.get("rule", "saved plan"),
                reason=item.get("reason", ""),
                size=int(item.get("size", 0)),
                warnings=list(item.get("warnings", [])),
            )
        )
    return restored


if __name__ == "__main__":  # pragma: no cover
    cli()
