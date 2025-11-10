"""CLI entry point for Aegis OS Agent."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import click

from .config.schema import AppConfig, load_config
from .core.bus import EventBus
from .core.scheduler import SchedulerService
from .core.actions import ActionExecutor
from .core.intents import IntentRouter
from .core.notifier import Notifier
from .watchers.clipboard import ClipboardWatcher
from .watchers.filesystem import DirectoryWatcher
from .ui.palette import CommandPalette
from .ui.settings import SettingsWindow
from .reports.exporter import ReportExporter

LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class Application:
    """Runtime container for top-level services."""

    def __init__(self, config: AppConfig, use_ui: bool = True) -> None:
        self.config = config
        self.bus = EventBus()
        self.notifier = Notifier()
        self.action_executor = ActionExecutor(self.bus, self.notifier, config)
        self.intent_router = IntentRouter(self.bus, self.action_executor, config)
        self.scheduler = SchedulerService(config, self.bus, self.action_executor)
        self.clipboard_watcher = ClipboardWatcher(
            bus=self.bus,
            config=config,
        )
        self.desktop_watcher: Optional[DirectoryWatcher] = None
        self.downloads_watcher: Optional[DirectoryWatcher] = None
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
        self.palette: Optional[CommandPalette] = CommandPalette(self.bus, self.intent_router, config) if use_ui else None
        self.settings_window: Optional[SettingsWindow] = SettingsWindow(config, self.intent_router) if use_ui else None

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

    def stop(self) -> None:
        """Stop all services gracefully."""

        LOGGER.info("Stopping Aegis services")
        self.clipboard_watcher.stop()
        if self.desktop_watcher:
            self.desktop_watcher.stop()
        if self.downloads_watcher:
            self.downloads_watcher.stop()
        self.scheduler.stop()


@click.group()
@click.option("--config", "config_path", type=click.Path(path_type=Path), default=None)
@click.option("--log-level", default="INFO", type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]))
@click.pass_context
def cli(ctx: click.Context, config_path: Optional[Path], log_level: str) -> None:
    """Entry point for the Aegis CLI."""

    logging.getLogger().setLevel(getattr(logging, log_level))
    config = load_config(config_path)
    ctx.obj = {
        "config": config,
    }


@cli.command()
@click.option("--use-ollama/--no-use-ollama", default=None, help="Override Ollama usage flag")
@click.option("--no-clipboard-vault", is_flag=True, default=False)
@click.pass_context
def run(ctx: click.Context, use_ollama: Optional[bool], no_clipboard_vault: bool) -> None:
    """Start the agent with UI components."""

    config: AppConfig = ctx.obj["config"]
    if use_ollama is not None:
        config.use_ollama = use_ollama
    if no_clipboard_vault:
        config.clipboard_vault.enabled = False

    app = Application(config, use_ui=True)
    try:
        app.start(headless=False)
    except KeyboardInterrupt:  # pragma: no cover - manual exit
        LOGGER.info("Interrupted by user")
    finally:
        app.stop()


@cli.command()
@click.pass_context
def headless(ctx: click.Context) -> None:
    """Run the agent without UI components."""

    config: AppConfig = ctx.obj["config"]
    app = Application(config, use_ui=False)
    try:
        app.start(headless=True)
    except KeyboardInterrupt:  # pragma: no cover
        LOGGER.info("Interrupted by user")
    finally:
        app.stop()


@cli.command()
@click.pass_context
def palette(ctx: click.Context) -> None:
    """Launch only the command palette."""

    config: AppConfig = ctx.obj["config"]
    bus = EventBus()
    notifier = Notifier()
    executor = ActionExecutor(bus, notifier, config)
    router = IntentRouter(bus, executor, config)
    palette = CommandPalette(bus, router, config)
    palette.run()


@cli.command()
@click.option("--html", "export_html", is_flag=True, help="Export an HTML report in addition to JSON")
@click.pass_context
def report(ctx: click.Context, export_html: bool) -> None:
    """Generate the latest activity report."""

    config: AppConfig = ctx.obj["config"]
    exporter = ReportExporter(config)
    summary = exporter.export_latest(include_html=export_html)
    click.echo(summary)


@cli.command()
@click.option("--output", type=click.Path(path_type=Path), default=None)
@click.pass_context
def dump_config(ctx: click.Context, output: Optional[Path]) -> None:
    """Write the current configuration to disk."""

    config: AppConfig = ctx.obj["config"]
    path = output or Path("aegis-config.json")
    path.write_text(config.json(indent=2), encoding="utf-8")
    click.echo(f"Configuration written to {path}")


if __name__ == "__main__":  # pragma: no cover
    cli()

