"""Dashboard card widgets — one per panel. Each is a small, focused Container
that a formatting helper feeds; the actual number-crunching lives in
netstats.py/render.py/interfaces.py/wifi.py/latency.py/destinations.py, kept
pure and tested there.
"""

from rich.text import Text
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import DataTable, Sparkline, Static

from history import format_span
from interfaces import classify_interface
from netstats import (duration, format_megabytes, is_anomalous, mbps,
                      megabytes, recent_speed_history)
from render import (breakdown_bars, ticker_window, usage_levels, vitals_summary,
                    wifi_summary)

# Fg colors for the usage gradient, palest to most intense — same palette
# spirit as the old curses build, now as truecolor hex for `rich`.
GRADIENT_COLORS = ["#f2d675", "#e8a33d", "#d9701f", "#c23b22"]

THROUGHPUT_WINDOW_SECONDS = 120


class StretchingDataTable(DataTable):
    """A DataTable whose first column stretches to fill whatever width the
    widget actually has. DataTable's own columns are `auto_width` by
    default — sized purely from their content — so even though the widget's
    box correctly fills its container (`width: 1fr`), the columns inside it
    never do, leaving the table's real content stuck to the left with blank
    space on the right as the window grows."""

    def on_resize(self, event) -> None:
        self._stretch_first_column(event.size.width)

    def _stretch_first_column(self, available_width):
        columns = self.ordered_columns
        if not columns:
            return
        first, rest = columns[0], columns[1:]
        other_width = sum(column.get_render_width(self) for column in rest)
        first.auto_width = False
        first.width = max(10, available_width - other_width - 2 * self.cell_padding)
        self._require_update_dimensions = True
        self.refresh()


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
        self._theme_text = ""
        self._rate_text = ""

    def update_wifi(self, signal):
        self._wifi_text = wifi_summary(signal)
        self._render_line()

    def update_vitals(self, history, rows, seconds, elapsed):
        self._vitals_text = vitals_summary(history, rows, seconds, elapsed)
        self._render_line()

    def update_theme(self, theme_name):
        self._theme_text = f"Theme: {theme_name}"
        self._render_line()

    def update_refresh_rate(self, seconds):
        self._rate_text = f"Refresh: {seconds:g}s"
        self._render_line()

    def _render_line(self):
        parts = [self._wifi_text, self._vitals_text, self._theme_text, self._rate_text]
        self.update("   |   ".join(part for part in parts if part))


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


class TopProgramsCard(Card):
    """The per-program table. Selecting a row is what the kill action (`k`)
    acts on — see app.py. Placed first in the grid and spans the full row
    width, so it's one wide panel across the top with the other cards
    filling the remaining 3-column, 2-row grid below it."""

    DEFAULT_CSS = """
    TopProgramsCard {
        column-span: 3;
    }
    """

    COLUMNS = ["Program", "Busy", "Down (Mb/s)", "Up (Mb/s)", "Total (MB)",
               "Past Hr (MB)", "Sending"]

    def __init__(self, **kwargs):
        super().__init__("Top Programs", **kwargs)
        self._displayed_names = []
        self._last_sort_label = None

    def compose_body(self):
        yield StretchingDataTable(id="top-programs-table", cursor_type="row")

    def on_mount(self):
        table = self.query_one(DataTable)
        self._column_keys = table.add_columns(*self.COLUMNS)
        table._stretch_first_column(table.size.width)

    def update_from(self, rows, sort_label):
        self._title_widget().update(f"Top Programs — sorted by {sort_label}")
        table = self.query_one(DataTable)
        apps_by_name = {app.name: app for app in rows}
        levels_by_name = dict(zip(apps_by_name, usage_levels(rows)))

        sort_changed = sort_label != self._last_sort_label
        same_membership = (set(apps_by_name) == set(self._displayed_names)
                           and table.row_count == len(rows))

        if same_membership and not sort_changed:
            # Same tracked programs, same sort mode — keep the existing row
            # order fixed and just refresh values in place. Re-sorting the
            # live table on every tiny rank change (especially with dozens
            # of near-idle background processes at higher --top values) is
            # what caused the lag and the cursor jumping around while you
            # navigated: every reorder triggered a full rebuild plus a
            # scroll-to-cursor. Now that only happens on an actual roster
            # change or when you press 's'.
            for name in self._displayed_names:
                app = apps_by_name[name]
                values = self._row_values(app, levels_by_name[name])
                for column_key, value in zip(self._column_keys, values):
                    table.update_cell(name, column_key, value)
            return

        selected = self.selected_app_name()
        table.clear()
        for app in rows:
            table.add_row(*self._row_values(app, levels_by_name[app.name]), key=app.name)
        self._displayed_names = list(apps_by_name)
        self._last_sort_label = sort_label
        if selected in apps_by_name:
            table.move_cursor(row=self._displayed_names.index(selected))

    def _row_values(self, app, level):
        name = app.name
        if is_anomalous(app):
            name = f"⚠ {name}"
        style = GRADIENT_COLORS[level] if level is not None else None
        return (
            Text(name, style=style),
            "yes" if app.busy else "no",
            f"{mbps(app.speed_in):.2f}",
            f"{mbps(app.speed_out):.2f}",
            format_megabytes(app.total_bytes),
            format_megabytes(app.hour_bytes),
            duration(app.sending_seconds),
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


TICKER_INTERVAL_SECONDS = 0.3
TICKER_GAP = "     "  # the seam shown as a program's host list loops back to its start


class DestinationRow(Horizontal):
    """One program's destinations. The name stays put; the host list scrolls
    past on its own like a marquee, so a program with more hosts than fit on
    one line still gets to show all of them without you scrolling anything."""

    DEFAULT_CSS = """
    DestinationRow {
        height: 1;
    }
    DestinationRow > .destination-name {
        width: 20;
        text-style: bold;
    }
    DestinationRow > .destination-hosts {
        width: 1fr;
    }
    """

    def __init__(self, program_name, hosts, **kwargs):
        super().__init__(**kwargs)
        self.program_name = program_name
        self._hosts_text = ", ".join(hosts)
        self._offset = 0

    def compose(self):
        yield Static(self.program_name, classes="destination-name")
        yield Static(self._hosts_text, classes="destination-hosts")

    def on_mount(self):
        self.set_interval(TICKER_INTERVAL_SECONDS, self._advance_ticker)

    def update_hosts(self, hosts):
        self._hosts_text = ", ".join(hosts)

    def _advance_ticker(self):
        self._offset += 1
        hosts_widget = self.query_one(".destination-hosts", Static)
        width = hosts_widget.size.width or 1
        hosts_widget.update(ticker_window(self._hosts_text, width, self._offset, TICKER_GAP))


class DestinationsCard(Card):
    def __init__(self, **kwargs):
        super().__init__("Top Destinations", **kwargs)

    def compose_body(self):
        yield Static("No open connections among tracked programs.", id="destinations-empty")
        yield VerticalScroll(id="destinations-rows")

    def update_from(self, grouped):
        self.query_one("#destinations-empty", Static).display = not grouped
        container = self.query_one("#destinations-rows", VerticalScroll)
        rows_by_name = {row.program_name: row for row in container.query(DestinationRow)}

        for name, row in rows_by_name.items():
            if name not in grouped:
                row.remove()

        for name, hosts in grouped.items():
            row = rows_by_name.get(name)
            if row is None:
                container.mount(DestinationRow(name, hosts))
            else:
                row.update_hosts(hosts)


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
