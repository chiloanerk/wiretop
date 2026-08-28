"""Dashboard card widgets — one per panel. Each is a small, focused Container
that a formatting helper feeds; the actual number-crunching lives in
netstats.py/render.py/interfaces.py/wifi.py/latency.py/destinations.py, kept
pure and tested there.
"""

from rich.text import Text
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Sparkline, Static

from history import format_span
from interfaces import classify_interface
from netstats import (bucketed_history, duration, format_megabytes,
                      is_anomalous, mbps, megabytes, recent_speed_history)
from render import breakdown_bars, usage_levels, vitals_summary, wifi_summary

# Fg colors for the usage gradient, palest to most intense — same palette
# spirit as the old curses build, now as truecolor hex for `rich`.
GRADIENT_COLORS = ["#f2d675", "#e8a33d", "#d9701f", "#c23b22"]

THROUGHPUT_WINDOW_SECONDS = 120
PAST_HOUR_BUCKET_SECONDS = 300  # 5 minutes
PAST_HOUR_BUCKETS = 12


class Card(Vertical):
    """A titled panel; subclasses fill in `compose_body()`."""

    DEFAULT_CSS = """
    Card {
        border: round $accent;
        padding: 0 1;
        height: 100%;
    }
    Card > .card-title {
        text-style: bold;
    }
    """

    def __init__(self, title, **kwargs):
        super().__init__(**kwargs)
        self._title = title

    def compose(self):
        yield Static(self._title, classes="card-title")
        yield from self.compose_body()

    def compose_body(self):
        return ()


class StatusBar(Static):
    """A single always-visible line under the header: Wi-Fi signal and
    session vitals. Too small/glanceable to earn their own bordered cards."""

    DEFAULT_CSS = """
    StatusBar {
        dock: top;
        height: 1;
        background: $panel;
        color: $text-muted;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__("", **kwargs)
        self._wifi_text = wifi_summary(None)
        self._vitals_text = ""

    def update_wifi(self, signal):
        self._wifi_text = wifi_summary(signal)
        self._render_line()

    def update_vitals(self, history, rows, seconds, elapsed):
        self._vitals_text = vitals_summary(history, rows, seconds, elapsed)
        self._render_line()

    def _render_line(self):
        self.update(f"{self._wifi_text}   |   {self._vitals_text}")


class Graph(Vertical):
    """A Sparkline that fills the space it's given, with a y-axis max label
    above it and an x-axis time range below it (Sparkline itself has neither,
    and defaults to a 1-row height that ignores its container's size)."""

    DEFAULT_CSS = """
    Graph {
        height: 1fr;
    }
    Graph > Sparkline {
        height: 1fr;
    }
    Graph > .graph-axis {
        color: $text-muted;
        height: 1;
    }
    Graph > .graph-x-row > Static {
        width: 1fr;
    }
    Graph > .graph-x-row > .graph-x-right {
        text-align: right;
    }
    """

    def __init__(self, x_left, x_right, unit="", **kwargs):
        super().__init__(**kwargs)
        self._x_left = x_left
        self._x_right = x_right
        self._unit = unit

    def compose(self):
        yield Static("0" + self._unit, classes="graph-axis", id=f"{self.id}-ymax")
        yield Sparkline([], id=f"{self.id}-spark")
        with Horizontal(classes="graph-axis graph-x-row"):
            yield Static(self._x_left, classes="graph-x-left")
            yield Static(self._x_right, classes="graph-x-right")

    def update_data(self, values):
        values = list(values) or [0]
        self.query_one(f"#{self.id}-spark", Sparkline).data = values
        self.query_one(f"#{self.id}-ymax", Static).update(f"{max(values):.1f}{self._unit}")

    def update_x_left(self, text):
        self.query_one(".graph-x-left", Static).update(text)


class ThroughputCard(Card):
    def __init__(self, **kwargs):
        super().__init__("Live Throughput", **kwargs)

    def compose_body(self):
        yield Static("", id="throughput-stats")
        yield Graph("-2m", "now", unit=" Mb/s", id="throughput-graph")

    def update_from(self, history, current_in, current_out):
        self.query_one("#throughput-stats", Static).update(
            f"↓ {mbps(current_in):.2f} Mb/s   ↑ {mbps(current_out):.2f} Mb/s"
        )
        window = recent_speed_history(history, THROUGHPUT_WINDOW_SECONDS)
        self.query_one("#throughput-graph", Graph).update_data([mbps(v) for v in window])


class PastHourCard(Card):
    def __init__(self, **kwargs):
        super().__init__("Past Hour", **kwargs)

    def compose_body(self):
        yield Graph("-1h", "now", unit=" MB", id="past-hour-graph")

    def update_from(self, history):
        buckets = bucketed_history(history, PAST_HOUR_BUCKET_SECONDS, PAST_HOUR_BUCKETS)
        self.query_one("#past-hour-graph", Graph).update_data(
            [megabytes(total) for total in buckets]
        )


class TopProgramsCard(Card):
    """The per-program table. Selecting a row is what the kill action (`k`)
    acts on — see app.py."""

    COLUMNS = ["Program", "Busy", "Down (Mb/s)", "Up (Mb/s)", "Total (MB)",
               "Past Hr (MB)", "Sending"]

    def __init__(self, **kwargs):
        super().__init__("Top Programs", **kwargs)

    def compose_body(self):
        yield DataTable(id="top-programs-table", cursor_type="row")

    def on_mount(self):
        self.query_one(DataTable).add_columns(*self.COLUMNS)

    def update_from(self, rows, sort_label):
        self._title_widget().update(f"Top Programs — sorted by {sort_label}")
        table = self.query_one(DataTable)
        table.clear()
        for app, level in zip(rows, usage_levels(rows)):
            name = app.name
            if is_anomalous(app):
                name = f"⚠ {name}"
            style = GRADIENT_COLORS[level] if level is not None else None
            table.add_row(
                Text(name, style=style),
                "yes" if app.busy else "no",
                f"{mbps(app.speed_in):.2f}",
                f"{mbps(app.speed_out):.2f}",
                format_megabytes(app.total_bytes),
                format_megabytes(app.hour_bytes),
                duration(app.sending_seconds),
                key=app.name,
            )

    def _title_widget(self):
        return self.query_one(".card-title", Static)

    def selected_app_name(self):
        """The name of the currently-selected row, or None if the table's
        empty."""
        table = self.query_one(DataTable)
        if table.row_count == 0:
            return None
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        return row_key.value


class BreakdownCard(Card):
    def __init__(self, **kwargs):
        super().__init__("Usage Breakdown", **kwargs)

    def compose_body(self):
        yield Static("", id="breakdown-text")

    def update_from(self, rows):
        text = "\n".join(breakdown_bars(rows)) or "No usage yet."
        self.query_one("#breakdown-text", Static).update(text)


class InterfacesCard(Card):
    COLUMNS = ["Interface", "Kind", "Down (Mb/s)", "Up (Mb/s)", "Total (MB)"]

    def __init__(self, **kwargs):
        super().__init__("Interfaces", **kwargs)

    def compose_body(self):
        yield DataTable(id="interfaces-table")

    def on_mount(self):
        self.query_one(DataTable).add_columns(*self.COLUMNS)

    def update_from(self, rates, wifi_name):
        table = self.query_one(DataTable)
        table.clear()
        for name, (bytes_in, bytes_out, rate_in, rate_out) in sorted(rates.items()):
            if bytes_in == 0 and bytes_out == 0:
                continue  # skip interfaces that have never carried traffic
            kind = classify_interface(name, wifi_name)
            table.add_row(name, kind, f"{mbps(rate_in):.2f}", f"{mbps(rate_out):.2f}",
                          format_megabytes(bytes_in + bytes_out))


class LatencyCard(Card):
    def __init__(self, **kwargs):
        super().__init__("Latency", **kwargs)

    def compose_body(self):
        yield Static("", id="latency-text")
        yield Graph("older", "now", unit=" ms", id="latency-graph")

    def update_from(self, rtt, history):
        text = f"{rtt:.1f} ms" if rtt is not None else "Unreachable"
        self.query_one("#latency-text", Static).update(text)
        self.query_one("#latency-graph", Graph).update_data(history)


class DestinationsCard(Card):
    def __init__(self, **kwargs):
        super().__init__("Top Destinations", **kwargs)

    def compose_body(self):
        yield Static("", id="destinations-text")

    def update_from(self, grouped):
        if not grouped:
            text = "No open connections among tracked programs."
        else:
            lines = []
            for name, hosts in grouped.items():
                lines.append(f"{name}: {', '.join(hosts[:3])}")
            text = "\n".join(lines)
        self.query_one("#destinations-text", Static).update(text)


class HistoryCard(Card):
    """Grows from a few minutes of bars up to 7 days, widening its buckets
    as more history accumulates — see history.py's history_view()."""

    def __init__(self, **kwargs):
        super().__init__("History", **kwargs)

    def compose_body(self):
        yield Graph("", "now", unit=" MB", id="history-graph")

    def update_from(self, values, span_seconds):
        graph = self.query_one("#history-graph", Graph)
        graph.update_data([megabytes(total) for total in values])
        graph.update_x_left(format_span(span_seconds))
