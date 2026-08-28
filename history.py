"""Longer-term usage history, persisted locally so trends survive between
runs — and so the History card can show a sensible graph well before a full
7 days of data exists.

Storage is a rolling log of small fixed-width periods (bytes moved in just
that period, not a cumulative total), so restarting wiretop mid-day doesn't
lose or double-count anything. Display resamples that log into wider buckets
as more history accumulates — see `history_view()`.
"""

import sqlite3
from pathlib import Path

DEFAULT_PATH = Path.home() / ".wiretop" / "history.db"

RECORD_PERIOD_SECONDS = 5 * 60  # how finely usage is logged
MAX_SPAN_SECONDS = 7 * 24 * 3600  # how far back the graph ever looks

# Bucket widths the display can grow into, smallest first. The graph always
# shows close to TARGET_BARS bars, widening the buckets as the recorded span
# grows, rather than a fixed number of mostly-empty day-wide bars from the
# start.
BUCKET_LADDER_SECONDS = [
    RECORD_PERIOD_SECONDS,  # 5 min
    15 * 60,
    60 * 60,
    2 * 60 * 60,
    6 * 60 * 60,
    12 * 60 * 60,
    24 * 60 * 60,
]
TARGET_BARS = 12


def period_start_for(timestamp, period_seconds=RECORD_PERIOD_SECONDS):
    """The start of the period `timestamp` falls into."""
    return int(timestamp // period_seconds) * period_seconds


def choose_bucket_seconds(span_seconds, ladder=BUCKET_LADDER_SECONDS, target_bars=TARGET_BARS):
    """The smallest bucket width that keeps the bar count near `target_bars`
    for a span this wide; the ladder's widest step once the span outgrows
    even that."""
    for bucket in ladder:
        if bucket <= 0:
            continue
        if -(-span_seconds // bucket) <= target_bars:  # ceil division
            return bucket
    return ladder[-1]


def resample_periods(periods, now, bucket_seconds, num_buckets):
    """`periods`: [(period_start, total_bytes), ...]. Groups them into
    `num_buckets` consecutive `bucket_seconds`-wide buckets ending at `now`,
    oldest first. Buckets with nothing recorded are 0."""
    start = now - bucket_seconds * num_buckets
    buckets = [0] * num_buckets
    for period_start, total in periods:
        if period_start < start or period_start >= now:
            continue
        index = int((period_start - start) // bucket_seconds)
        if 0 <= index < num_buckets:
            buckets[index] += total
    return buckets


def history_view(periods, now, target_bars=TARGET_BARS,
                  ladder=BUCKET_LADDER_SECONDS, max_span=MAX_SPAN_SECONDS):
    """The values to graph and the span they cover, given an ascending list
    of (period_start, total_bytes) rows: (bucketed_values, span_seconds).
    Empty history gives ([], 0)."""
    if not periods:
        return [], 0
    span = min(now - periods[0][0], max_span)
    bucket_seconds = choose_bucket_seconds(span, ladder, target_bars)
    num_buckets = max(1, int(-(-span // bucket_seconds)))  # ceil division
    values = resample_periods(periods, now, bucket_seconds, num_buckets)
    return values, num_buckets * bucket_seconds


def format_span(seconds):
    """A short "-Nm"/"-Nh"/"-Nd" label for how far back a graph reaches."""
    if seconds <= 0:
        return "now"
    if seconds < 3600:
        return f"-{seconds // 60}m"
    if seconds < 86400:
        return f"-{seconds // 3600}h"
    return f"-{seconds // 86400}d"


class History:
    """The sqlite-backed period log. `record_period` adds to a period's
    total rather than overwriting it, so repeated calls within the same
    period accumulate correctly."""

    def __init__(self, path=DEFAULT_PATH):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self._path)
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS periods (period_start INTEGER PRIMARY KEY, total_bytes INTEGER)"
        )
        self._connection.commit()

    def record_period(self, period_start, bytes_moved):
        self._connection.execute(
            "INSERT INTO periods (period_start, total_bytes) VALUES (?, ?) "
            "ON CONFLICT(period_start) DO UPDATE SET total_bytes = total_bytes + excluded.total_bytes",
            (period_start, bytes_moved),
        )
        self._connection.commit()

    def prune_older_than(self, cutoff):
        self._connection.execute("DELETE FROM periods WHERE period_start < ?", (cutoff,))
        self._connection.commit()

    def periods_since(self, cutoff):
        """[(period_start, total_bytes), ...], oldest first."""
        rows = self._connection.execute(
            "SELECT period_start, total_bytes FROM periods WHERE period_start >= ? ORDER BY period_start",
            (cutoff,),
        ).fetchall()
        return rows

    def close(self):
        self._connection.close()
