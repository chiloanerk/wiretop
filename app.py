"""The textual dashboard app: wires nettop plus the extra data sources into
the card grid, and owns the sort-cycle / quit / kill key bindings.
"""

import os
import signal
import time

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Label

from cards import (BreakdownCard, DestinationsCard, HistoryCard, InterfacesCard,
                   LatencyCard, StatusBar, ThroughputCard, TopProgramsCard)
from destinations import DestinationSource, group_by_app
from history import History, MAX_SPAN_SECONDS, history_view, period_start_for
from interfaces import InterfaceSource, wifi_interface_name
from latency import LatencySource
from netstats import SORT_MODES, Tracker, recent_speed_history
from nettop_source import NettopUnavailable
from procnames import ProcessNames
from wifi import WifiSignalSource

# Each source polls on its own cadence rather than sharing the 1s nettop
# tick — netstat is cheap, system_profiler is slow, ping/lsof are moderate.
NETTOP_INTERVAL = 1.0
INTERFACE_INTERVAL = 2.0
WIFI_INTERVAL = 8.0
LATENCY_INTERVAL = 3.0
DESTINATIONS_INTERVAL = 4.0
HISTORY_INTERVAL = 60.0

# How often the nettop-driven cards refresh, cycled with 'r'.
REFRESH_RATES = [1.0, 2.0, 5.0]


class InterfacesPolled(Message):
    def __init__(self, rates):
        self.rates = rates
        super().__init__()


class WifiPolled(Message):
    def __init__(self, signal):
        self.signal = signal
        super().__init__()


class LatencyPolled(Message):
    def __init__(self, rtt, history):
        self.rtt = rtt
        self.history = history
        super().__init__()


class DestinationsPolled(Message):
    def __init__(self, grouped):
        self.grouped = grouped
        super().__init__()


class KillConfirmScreen(ModalScreen):
    """Blocks until the user picks Cancel or Kill — a kill is never one key
    press away."""

    DEFAULT_CSS = """
    KillConfirmScreen {
        align: center middle;
    }
    #kill-dialog {
        width: auto;
        height: auto;
        border: round $error;
        padding: 1 2;
    }
    #kill-dialog Horizontal {
        width: auto;
        height: auto;
        margin-top: 1;
    }
    #kill-dialog Button {
        margin-right: 1;
    }
    """

    def __init__(self, app_name, pid_count):
        super().__init__()
        self._app_name = app_name
        self._pid_count = pid_count

    def compose(self) -> ComposeResult:
        with Vertical(id="kill-dialog"):
            yield Label(f"Kill {self._app_name} ({self._pid_count} processes)?")
            with Horizontal():
                yield Button("Cancel", id="cancel")
                yield Button("Kill", id="kill", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "kill")


class NetTopApp(App):
    """The dashboard. `source` is a NettopSource or ReplaySource."""

    # textual's built-in command palette (theme picker, etc.) isn't part of
    # this dashboard's design — it also has a known crash
    # (ScreenStackError) selecting a theme from it, so it's off entirely.
    ENABLE_COMMAND_PALETTE = False

    CSS = """
    Screen {
        layout: grid;
        grid-size: 3 3;
        grid-gutter: 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("s", "cycle_sort", "Sort"),
        Binding("k", "kill_selected", "Kill selected"),
        Binding("t", "cycle_theme", "Theme"),
        Binding("r", "cycle_refresh_rate", "Refresh rate"),
    ]

    def __init__(self, source, args):
        super().__init__()
        self._source = source
        self._args = args
        self.tracker = Tracker()
        self.names = ProcessNames()
        self.top = None
        self.problem = None
        self.sort_index = 0
        self._theme_names = sorted(self.available_themes)
        self._theme_index = self._theme_names.index(self.theme)
        self._rate_index = 0
        self._nettop_timer = None

        self._interface_source = InterfaceSource()
        self._wifi_name = wifi_interface_name()
        self._wifi_source = WifiSignalSource()
        self._latency_source = LatencySource()
        self._destination_source = DestinationSource()
        self._history = History()

    def compose(self) -> ComposeResult:
        yield Header()
        yield StatusBar(id="status-bar")
        yield TopProgramsCard(id="top-programs")
        yield ThroughputCard(id="throughput")
        yield BreakdownCard(id="breakdown")
        yield InterfacesCard(id="interfaces")
        yield LatencyCard(id="latency")
        yield DestinationsCard(id="destinations")
        yield HistoryCard(id="history")
        yield Footer()

    def on_mount(self) -> None:
        self._nettop_timer = self.set_interval(REFRESH_RATES[self._rate_index], self._tick_nettop)
        self.set_interval(INTERFACE_INTERVAL, self._tick_interfaces)
        self.set_interval(WIFI_INTERVAL, self._tick_wifi)
        self.set_interval(LATENCY_INTERVAL, self._tick_latency)
        self.set_interval(DESTINATIONS_INTERVAL, self._tick_destinations)
        self.set_interval(HISTORY_INTERVAL, self._tick_history)
        self.query_one(StatusBar).update_theme(self.theme)
        self.query_one(StatusBar).update_refresh_rate(REFRESH_RATES[self._rate_index])

    def on_unmount(self) -> None:
        self._source.close()
        self._history.close()

    # -- nettop-driven cards (Throughput, Top Programs, Breakdown, Past Hour, Vitals) --

    def _tick_nettop(self) -> None:
        try:
            samples = self._source.poll()
        except NettopUnavailable as stopped:
            self.problem = stopped
            self.exit()
            return
        for sample in samples:
            self.names.sync(sample.keys())
            self.tracker.add_sample(sample, self.names.get)
        if self.tracker.seconds >= self._args.warmup:
            # Re-picked every second so a program that turns heavy later can
            # still swap onto the list.
            self.top = self.tracker.pick_top(self._args.top)
        self._refresh_nettop_cards()

    def _refresh_nettop_cards(self) -> None:
        sort_by, sort_label = SORT_MODES[self.sort_index]
        rows = self.tracker.rows_for(self.top, sort_by=sort_by) if self.top else []
        self.query_one(TopProgramsCard).update_from(rows, sort_label)
        self.query_one(ThroughputCard).update_from(
            self.tracker.history,
            sum(app.speed_in for app in rows),
            sum(app.speed_out for app in rows),
        )
        self.query_one(BreakdownCard).update_from(rows)
        self.query_one(StatusBar).update_vitals(
            self.tracker.history, rows, self.tracker.seconds, self.tracker.seconds
        )

    # -- slower, independent data sources --
    #
    # Each of these shells out to a real command (netstat/system_profiler/
    # ping/lsof) and blocks until it returns. `system_profiler` alone takes
    # 3+ seconds on this machine — running any of them directly on the main
    # thread would freeze the whole UI (timers, charts, keyboard input) for
    # that long, since textual's event loop is single-threaded. `@work
    # (thread=True)` runs the blocking call on a background thread instead;
    # `exclusive=True` drops an overlapping call if a source is ever slower
    # than its own polling interval, rather than piling up worker threads.
    #
    # Results are handed back via `post_message` (thread-safe, fire-and-
    # forget), not `call_from_thread` — that method blocks the worker thread
    # until the main loop actually processes it, which deadlocks if you quit
    # while a poll is still in flight: the main loop wants the worker thread
    # to finish before it fully exits, while the worker thread is stuck
    # waiting on a main loop that's no longer being driven forward.
    # `post_message` just queues the update and returns immediately, so a
    # worker that's mid-poll when you quit finishes normally instead of
    # hanging the whole process.

    @work(thread=True, exclusive=True)
    def _tick_interfaces(self) -> None:
        rates = self._interface_source.poll()
        self.post_message(InterfacesPolled(rates))

    def on_interfaces_polled(self, message: InterfacesPolled) -> None:
        self.query_one(InterfacesCard).update_from(message.rates, self._wifi_name)

    @work(thread=True, exclusive=True)
    def _tick_wifi(self) -> None:
        self.post_message(WifiPolled(self._wifi_source.poll()))

    def on_wifi_polled(self, message: WifiPolled) -> None:
        self.query_one(StatusBar).update_wifi(message.signal)

    @work(thread=True, exclusive=True)
    def _tick_latency(self) -> None:
        rtt = self._latency_source.poll()
        self.post_message(LatencyPolled(rtt, list(self._latency_source.history)))

    def on_latency_polled(self, message: LatencyPolled) -> None:
        self.query_one(LatencyCard).update_from(message.rtt, message.history)

    @work(thread=True, exclusive=True)
    def _tick_destinations(self) -> None:
        connections = self._destination_source.poll()
        app_pids = {name: app.current_pids for name, app in self.tracker.apps.items()}
        grouped = group_by_app(connections, app_pids)
        resolved = self._destination_source.resolve_hosts(grouped)
        self.post_message(DestinationsPolled(resolved))

    def on_destinations_polled(self, message: DestinationsPolled) -> None:
        self.query_one(DestinationsCard).update_from(message.grouped)

    def _tick_history(self) -> None:
        now = time.time()
        recent_bytes = sum(recent_speed_history(self.tracker.history, int(HISTORY_INTERVAL)))
        self._history.record_period(period_start_for(now), recent_bytes)
        self._history.prune_older_than(now - MAX_SPAN_SECONDS)

        periods = self._history.periods_since(now - MAX_SPAN_SECONDS)
        values, span_seconds = history_view(periods, now)
        self.query_one(HistoryCard).update_from(values, span_seconds)

    # -- key bindings --

    def action_cycle_sort(self) -> None:
        self.sort_index = (self.sort_index + 1) % len(SORT_MODES)
        self._refresh_nettop_cards()

    def action_cycle_theme(self) -> None:
        self._theme_index = (self._theme_index + 1) % len(self._theme_names)
        theme_name = self._theme_names[self._theme_index]
        self.theme = theme_name
        self.query_one(StatusBar).update_theme(theme_name)

    def action_cycle_refresh_rate(self) -> None:
        self._rate_index = (self._rate_index + 1) % len(REFRESH_RATES)
        rate = REFRESH_RATES[self._rate_index]
        self._nettop_timer.stop()
        self._nettop_timer = self.set_interval(rate, self._tick_nettop)
        self.query_one(StatusBar).update_refresh_rate(rate)

    def action_kill_selected(self) -> None:
        name = self.query_one(TopProgramsCard).selected_app_name()
        app = self.tracker.apps.get(name) if name else None
        if not app or not app.current_pids:
            return
        pids = set(app.current_pids)

        def handle_confirmation(confirmed: bool) -> None:
            if not confirmed:
                return
            for pid in pids:
                try:
                    os.kill(pid, signal.SIGTERM)
                except OSError:
                    pass

        self.push_screen(KillConfirmScreen(name, len(pids)), handle_confirmation)
