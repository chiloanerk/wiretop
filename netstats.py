"""Working out who used the network, from nettop's numbers.

Everything here is pure: no processes, no network, no terminal.
"""

from collections import deque

HOUR_SECONDS = 3600

# What rows_for() can sort by, in the order pressing the sort key cycles
# through, each paired with the label shown on screen for it.
SORT_MODES = [
    ("total", "Total Used"),
    ("hour", "Past Hour"),
    ("speed", "Current Speed"),
]


def parse_sample(rows):
    """Turn nettop CSV rows into {pid: (name, bytes_in, bytes_out)}.

    A row looks like "Google Chrome H.35165,10520,7229,". The process name can
    itself contain dots, so the pid is split off the end rather than the front.
    """
    sample = {}
    for row in rows:
        fields = row.strip().split(",")
        if len(fields) < 3:
            continue
        name, _, pid = fields[0].rpartition(".")
        if not name or not pid.isdigit():
            continue
        try:
            bytes_in = int(fields[1])
            bytes_out = int(fields[2])
        except ValueError:
            continue
        sample[int(pid)] = (name, bytes_in, bytes_out)
    return sample


class AppStats:
    """Running totals for one program."""

    def __init__(self, name):
        self.name = name
        self.total_in = 0
        self.total_out = 0
        self.sending_seconds = 0
        self.speed_in = 0
        self.speed_out = 0
        self.current_pids = set()
        self._recent_seconds = deque(maxlen=HOUR_SECONDS)
        self.hour_bytes = 0

    @property
    def total_bytes(self):
        return self.total_in + self.total_out

    @property
    def speed_bytes(self):
        return self.speed_in + self.speed_out

    @property
    def busy(self):
        return self.speed_bytes > 0

    @property
    def average_speed(self):
        """This app's own average bytes/second over its trailing hour."""
        if not self._recent_seconds:
            return 0
        return self.hour_bytes / len(self._recent_seconds)

    def record_second(self):
        """Fold the current second's speed into the trailing hour of usage."""
        if len(self._recent_seconds) == self._recent_seconds.maxlen:
            self.hour_bytes -= self._recent_seconds[0]
        self._recent_seconds.append(self.speed_bytes)
        self.hour_bytes += self.speed_bytes


class Tracker:
    """Adds up one-second deltas, grouped by program."""

    def __init__(self):
        self.apps = {}
        self.seconds = 0
        self.history = deque(maxlen=HOUR_SECONDS)  # aggregate bytes/second, all apps

    def add_sample(self, sample, name_for_pid):
        """Fold in one second of traffic. `sample` comes from parse_sample."""
        self.seconds += 1

        moved = {}
        moved_pids = {}
        for pid, (nettop_name, bytes_in, bytes_out) in sample.items():
            name = name_for_pid(pid, nettop_name)
            seen_in, seen_out = moved.get(name, (0, 0))
            moved[name] = (seen_in + bytes_in, seen_out + bytes_out)
            moved_pids.setdefault(name, set()).add(pid)

        for app in self.apps.values():
            app.speed_in = 0
            app.speed_out = 0
            app.current_pids = set()

        for name, (bytes_in, bytes_out) in moved.items():
            app = self.apps.get(name)
            if app is None:
                app = AppStats(name)
                self.apps[name] = app
            app.total_in += bytes_in
            app.total_out += bytes_out
            app.speed_in = bytes_in
            app.speed_out = bytes_out
            app.current_pids = moved_pids[name]
            if bytes_in + bytes_out > 0:
                app.sending_seconds += 1

        total_speed = 0
        for app in self.apps.values():
            app.record_second()
            total_speed += app.speed_bytes
        self.history.append(total_speed)

    def pick_top(self, count):
        """The programs that averaged the most data per second so far.

        Every program is averaged over the same number of seconds, so ranking
        by the total gives the same order as ranking by the average.
        """
        ranked = sorted(self.apps.values(), key=lambda app: (-app.total_bytes, app.name))
        return [app.name for app in ranked[:count]]

    def rows_for(self, names, sort_by="total"):
        """Stats for the chosen programs, ranked by `sort_by` (one of the keys
        in SORT_MODES).

        Sorting by a running total (total used, or the past hour) instead of
        the current speed keeps rows from reshuffling every second, since a
        running total rarely swaps rank second to second the way speed does.
        """
        rows = [self.apps[name] for name in names if name in self.apps]
        if sort_by == "speed":
            rows.sort(key=lambda app: (-app.speed_bytes, -app.total_bytes, app.name))
        elif sort_by == "hour":
            rows.sort(key=lambda app: (-app.hour_bytes, app.name))
        else:
            rows.sort(key=lambda app: (-app.total_bytes, app.name))
        return rows


def recent_speed_history(history, seconds):
    """The most recent `seconds` of aggregate per-second speed, oldest first.
    Shorter than `seconds` if the session itself is younger than that."""
    return list(history)[-seconds:]


ANOMALY_MULTIPLIER = 3.0


def is_anomalous(app, multiplier=ANOMALY_MULTIPLIER):
    """True if `app` is moving data well above its own trailing-hour average
    right now — catches a program spiking, not just one that's globally big."""
    return app.average_speed > 0 and app.speed_bytes > app.average_speed * multiplier


def mbps(bytes_in_one_second):
    return bytes_in_one_second * 8 / 1_000_000


def megabytes(byte_count):
    return byte_count / 1_000_000


def format_megabytes(byte_count):
    """Megabytes, with enough decimals that small amounts are still readable.

    A program that used 10 KB should not look identical to one that used none.
    """
    total = megabytes(byte_count)
    if total >= 100:
        return f"{total:.1f}"
    if total >= 1:
        return f"{total:.2f}"
    return f"{total:.3f}"


def duration(seconds):
    """23:45 under an hour, 1:23:45 once past it."""
    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
