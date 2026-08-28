"""Per-network-interface totals, from macOS's `netstat -ib`.

The parsing here is pure (no subprocess); only InterfaceSource shells out.
"""

import re
import subprocess

LINK_ROW = re.compile(r"<Link#\d+>")


def parse_netstat_ib(text):
    """Turn `netstat -ib` output into {interface: (bytes_in, bytes_out)}.

    Each interface appears multiple times (once per address family); only the
    "<Link#N>" row has real totals, so the rest are skipped. The Address
    column is sometimes blank, so fields are counted from the right rather
    than by a fixed position.
    """
    totals = {}
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 10:
            continue
        name, network = fields[0], fields[2]
        if not LINK_ROW.match(network):
            continue
        trailing = fields[-7:]  # Ipkts Ierrs Ibytes Opkts Oerrs Obytes Coll
        try:
            bytes_in = int(trailing[2])
            bytes_out = int(trailing[5])
        except ValueError:
            continue
        totals[name.rstrip("*")] = (bytes_in, bytes_out)
    return totals


INTERFACE_LINE = re.compile(r"^\s+(en\d+):\s*$")


def parse_wifi_interface_name(text):
    """Find the Wi-Fi interface's name (e.g. "en0") in
    `system_profiler SPAirPortDataType` output, from its "Interfaces:"
    section — not guessed from naming convention."""
    lines = text.splitlines()
    in_interfaces = False
    for line in lines:
        if line.strip() == "Interfaces:":
            in_interfaces = True
            continue
        if not in_interfaces:
            continue
        match = INTERFACE_LINE.match(line)
        if match:
            return match.group(1)
        if line.strip().endswith(":") and not line.startswith((" " * 8, "\t")):
            break  # left the Interfaces: block
    return None


def wifi_interface_name():
    """The real Wi-Fi interface name on this Mac, or None if it can't be
    determined (e.g. no Wi-Fi hardware)."""
    try:
        result = subprocess.run(["system_profiler", "SPAirPortDataType"],
                                 capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return parse_wifi_interface_name(result.stdout)


def classify_interface(name, wifi_name):
    """A short human label for an interface: Wi-Fi, Ethernet, VPN, Loopback,
    or Other. Best-effort — only the Wi-Fi name is actually confirmed."""
    if wifi_name and name == wifi_name:
        return "Wi-Fi"
    if name.startswith("utun"):
        return "VPN"
    if name == "lo0":
        return "Loopback"
    if name.startswith("en"):
        return "Ethernet"
    return "Other"


class InterfaceSource:
    """Polls `netstat -ib` and turns cumulative counters into rates."""

    def __init__(self, run=None):
        self._run = run or self._run_netstat
        self._previous = {}

    @staticmethod
    def _run_netstat():
        try:
            result = subprocess.run(["netstat", "-ib"], capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            return ""
        return result.stdout

    def poll(self):
        """{interface: (bytes_in, bytes_out, rate_in, rate_out)} — totals and
        this poll's rate, in bytes/second-since-last-poll. Never blocks for
        more than a few seconds even if `netstat` itself hangs."""
        current = parse_netstat_ib(self._run())
        rates = {}
        for name, (bytes_in, bytes_out) in current.items():
            prev = self._previous.get(name)
            if prev is None:
                rate_in = rate_out = 0
            else:
                rate_in = max(0, bytes_in - prev[0])
                rate_out = max(0, bytes_out - prev[1])
            rates[name] = (bytes_in, bytes_out, rate_in, rate_out)
        self._previous = current
        return rates
