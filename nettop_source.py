"""Reading per-process byte counts out of macOS's nettop, one sample a second."""

import os
import pty
import select
import shutil
import subprocess
import time

from netstats import parse_sample

NETTOP_COMMAND = [
    "nettop",
    "-P",                       # one line per process, no per-connection detail
    "-x",                       # plain byte counts instead of "1.2 MiB"
    "-n",                       # skip dns lookups
    "-d",                       # deltas: each sample is the traffic since the last
    "-s", "1",
    "-L", "0",                  # csv logging mode, keep going forever
    "-J", "bytes_in,bytes_out",
]


class NettopUnavailable(Exception):
    pass


def split_samples(lines):
    """Cut nettop's output into samples. It prints a header before each one."""
    samples = []
    rows = []
    for line in lines:
        line = line.strip()
        if line.startswith(","):
            if rows:
                samples.append(parse_sample(rows))
            rows = []
        elif line:
            rows.append(line)
    if rows:
        samples.append(parse_sample(rows))
    return samples


class NettopSource:
    """Live traffic from nettop.

    nettop block-buffers when its output is a pipe, which leaves the display
    frozen for half a minute and then jumps. Handing it a pty makes it think a
    person is watching, so it writes a line at a time.
    """

    def __init__(self):
        if shutil.which("nettop") is None:
            raise NettopUnavailable(
                "Could not find the 'nettop' command, which this program needs to "
                "watch network activity. It normally lives in /usr/bin."
            )
        self._master, writer = pty.openpty()
        try:
            self._process = subprocess.Popen(
                NETTOP_COMMAND,
                stdin=subprocess.DEVNULL,
                stdout=writer,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
        finally:
            os.close(writer)
        self._pending = b""
        self._rows = []
        self._had_first = False
        self._closed = False

    def fileno(self):
        return self._master

    def poll(self):
        """Any samples that have arrived. Never blocks."""
        ready, _, _ = select.select([self._master], [], [], 0)
        if not ready:
            return []
        try:
            chunk = os.read(self._master, 65536)
        except OSError:
            chunk = b""
        if not chunk:
            raise NettopUnavailable("The 'nettop' command stopped unexpectedly.")

        self._pending += chunk
        samples = []
        while b"\n" in self._pending:
            raw, _, self._pending = self._pending.partition(b"\n")
            line = raw.decode("utf-8", "replace").strip()
            if line.startswith(","):
                if self._rows:
                    samples.append(parse_sample(self._rows))
                self._rows = []
            elif line:
                self._rows.append(line)

        if samples and not self._had_first:
            self._had_first = True
            samples.pop(0)          # nettop's first sample is lifetime totals
        return samples

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
        os.close(self._master)


class ReplaySource:
    """Captured nettop output played back a sample a second, for checking the
    display without waiting on real traffic."""

    def __init__(self, path, clock=time.monotonic):
        with open(path) as handle:
            samples = split_samples(handle.read().splitlines())
        self._samples = samples[1:]     # the first is lifetime totals
        self._clock = clock
        self._due = clock()

    def fileno(self):
        return None

    def poll(self):
        if not self._samples or self._clock() < self._due:
            return []
        self._due += 1.0
        return [self._samples.pop(0)]

    def close(self):
        pass
