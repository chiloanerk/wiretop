"""Pure formatting helpers for the dashboard's cards.

Nothing here touches textual or a terminal, so it's all checked with plain
string/data comparisons.
"""

from netstats import duration, mbps

# Fraction of the tracked rows that count as "high usage" and get a color
# gradient; the rest stay plain. Rows must already be sorted by total_bytes.
HIGHLIGHT_FRACTION = 0.35
GRADIENT_STEPS = 4


def usage_levels(rows, fraction=HIGHLIGHT_FRACTION, steps=GRADIENT_STEPS):
    """None for plain rows; 0 (lightest) .. steps-1 (most intense) for the
    heaviest `fraction` of rows, scaled by rank within that group."""
    highlighted = max(1, round(len(rows) * fraction)) if rows else 0
    levels = []
    for rank in range(len(rows)):
        if rank >= highlighted:
            levels.append(None)
            continue
        step = (steps - 1) - rank * (steps - 1) // max(1, highlighted - 1)
        levels.append(step)
    return levels


def breakdown_bars(rows, bar_width=20, name_width=16):
    """One text line per row: name, a block-bar of its share of total bytes
    among `rows`, and the percentage."""
    total = sum(app.total_bytes for app in rows)
    lines = []
    for app in rows:
        share = app.total_bytes / total if total else 0
        filled = round(share * bar_width)
        bar = "█" * filled + "░" * (bar_width - filled)
        lines.append(f"{app.name[:name_width]:<{name_width}} {bar} {share * 100:4.1f}%")
    return lines


def vitals_summary(history, rows, seconds, elapsed):
    """One line: uptime, samples, busiest program, peak speed over the
    session — for the status bar, not a card of its own."""
    peak = max(history) if history else 0
    busiest = rows[0].name if rows else "-"
    return (f"Up {duration(elapsed)}   Samples {seconds}   "
            f"Busiest {busiest}   Peak {mbps(peak):.2f} Mb/s")


def wifi_summary(signal):
    """One line: signal strength and channel — for the status bar."""
    if signal is None:
        return "Wi-Fi: not connected"
    parts = []
    if "signal_dbm" in signal:
        parts.append(f"{signal['signal_dbm']} dBm")
    if "channel" in signal:
        parts.append(f"ch{signal['channel']} ({signal.get('band', '?')})")
    return "Wi-Fi: " + (" ".join(parts) if parts else "connected")


def ticker_window(text, width, offset, gap="     "):
    """A `width`-wide slice of `text`, scrolling continuously from `offset`
    — a marquee effect for text too long to fit on one line. `gap` is the
    seam shown as the text loops back to its start. Returns `text` unchanged
    if it already fits."""
    if not text or width <= 0:
        return ""
    loop = text + gap
    if len(loop) <= width:
        return text
    repeats = width // len(loop) + 2
    extended = loop * repeats
    offset %= len(loop)
    return extended[offset:offset + width]
