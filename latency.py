"""Round-trip latency to a reference host, from macOS's `ping`.

The parsing here is pure; only LatencySource shells out.
"""

import re
import subprocess
from collections import deque

REFERENCE_HOST = "1.1.1.1"
HISTORY_LENGTH = 60

ROUND_TRIP = re.compile(r"=\s*[\d.]+/([\d.]+)/[\d.]+/[\d.]+\s*ms")


def parse_ping_summary(text):
    """The average round-trip time in ms from `ping`'s summary line, or None
    if every packet was lost (no summary line, or 100% loss)."""
    match = ROUND_TRIP.search(text)
    if not match:
        return None
    return float(match.group(1))


class LatencySource:
    """Pings a reference host on its own timer, keeping a small rolling
    history of recent round-trip times for a sparkline."""

    def __init__(self, host=REFERENCE_HOST, run=None, history_length=HISTORY_LENGTH):
        self._host = host
        self._run = run or self._run_ping
        self.history = deque(maxlen=history_length)

    def _run_ping(self):
        # -t is ping's own exit timeout, not TTL, on macOS. subprocess's own
        # timeout is a backstop in case ping itself ever doesn't honor it.
        result = subprocess.run(["ping", "-c", "1", "-t", "2", self._host],
                                 capture_output=True, text=True, timeout=5)
        return result.stdout

    def poll(self):
        """This poll's round-trip time in ms (or None if unreachable), also
        appended to `self.history` when reachable. Never blocks for more
        than a few seconds even if `ping` itself hangs."""
        try:
            rtt = parse_ping_summary(self._run())
        except (OSError, subprocess.TimeoutExpired):
            rtt = None
        if rtt is not None:
            self.history.append(rtt)
        return rtt
