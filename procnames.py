"""Turning a pid into the name of a program a person would recognise.

nettop truncates names to 15 characters ("Google Chrome H"), and a single app
can run a dozen helper processes, so names come from ps and are folded back to
the app they belong to.
"""

import re
import subprocess

BUNDLE = re.compile(r"/([^/]+)\.app/")


def app_name(path):
    """The program name a person would use for this executable path.

    "/Applications/Google Chrome.app/.../Google Chrome Helper" -> "Google Chrome"
    """
    bundle = BUNDLE.search(path)
    if bundle:
        return bundle.group(1)
    name = path.rsplit("/", 1)[-1]
    if name.startswith("-"):
        name = name[1:]
    return name


def read_process_table():
    """{pid: executable path} for everything running right now."""
    result = subprocess.run(["ps", "-axo", "pid=,comm="], capture_output=True, text=True)
    table = {}
    for line in result.stdout.splitlines():
        pid, _, path = line.strip().partition(" ")
        path = path.strip()
        if pid.isdigit() and path:
            table[int(pid)] = path
    return table


class ProcessNames:
    """Remembers pid -> program name so ps runs at most once per new pid."""

    def __init__(self, read_table=read_process_table):
        self._read_table = read_table
        self._names = {}
        self._unknown = set()

    def sync(self, pids):
        """Look up any pids not seen before, in a single ps call."""
        fresh = [pid for pid in pids if pid not in self._names and pid not in self._unknown]
        if not fresh:
            return
        for pid, path in self._read_table().items():
            self._names[pid] = app_name(path)
        for pid in fresh:
            if pid not in self._names:
                self._unknown.add(pid)

    def get(self, pid, fallback):
        """The program name, or nettop's truncated one if the process has gone."""
        return self._names.get(pid, fallback)
