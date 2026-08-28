"""Which remote hosts each program is currently talking to, from macOS's
`lsof -i -P -n`.

This is a snapshot of open sockets, not a byte-volume ranking — `lsof` has no
traffic-volume column. The parsing here is pure; only DestinationSource
shells out.
"""

import subprocess


def parse_lsof_connections(text):
    """Turn `lsof -i -P -n` output into {pid: [remote_host, ...]}, one entry
    per established outbound connection. Listening sockets ("*:port") and
    anything without a remote address are skipped."""
    connections = {}
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 9 or not fields[1].isdigit():
            continue
        pid = int(fields[1])
        address = fields[8]
        if "->" not in address:
            continue
        _, _, remote = address.partition("->")
        remote_host, _, _ = remote.rpartition(":")
        if remote_host:
            connections.setdefault(pid, []).append(remote_host)
    return connections


def group_by_app(connections, app_pids):
    """`connections` from parse_lsof_connections; `app_pids` is
    {app_name: {pid, ...}} (e.g. from Tracker.apps[name].current_pids).
    Returns {app_name: [remote_host, ...]}, sorted and de-duplicated, for
    only the apps currently talking to somewhere."""
    grouped = {}
    for name, pids in app_pids.items():
        hosts = set()
        for pid in pids:
            hosts.update(connections.get(pid, []))
        if hosts:
            grouped[name] = sorted(hosts)
    return grouped


class DestinationSource:
    """Polls `lsof -i -P -n` on its own timer (too heavy to run every
    second)."""

    def __init__(self, run=None):
        self._run = run or self._run_lsof

    @staticmethod
    def _run_lsof():
        result = subprocess.run(["lsof", "-i", "-P", "-n"], capture_output=True, text=True)
        return result.stdout

    def poll(self):
        """{pid: [remote_host, ...]} — see parse_lsof_connections."""
        return parse_lsof_connections(self._run())
