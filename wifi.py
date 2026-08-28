"""Wi-Fi signal strength, from macOS's `system_profiler SPAirPortDataType`.

The parsing here is pure; only WifiSignalSource shells out. `wdutil info`
would be the more direct tool but needs sudo unconditionally on macOS, so
this uses system_profiler instead — slower to invoke, hence its own slow
poll cadence rather than once a second.
"""

import re
import subprocess

CHANNEL = re.compile(r"(\d+)\s*\((\d+GHz)")
SIGNAL_NOISE = re.compile(r"(-?\d+)\s*dBm\s*/\s*(-?\d+)\s*dBm")


def parse_wifi_signal(text):
    """The current network's signal info from `system_profiler
    SPAirPortDataType` output, or None if not connected. Only the first
    "Current Network Information:" block is used (the active radio) — a
    second, empty one can appear for other Wi-Fi-capable radios."""
    lines = text.splitlines()
    in_block = False
    header_indent = None
    fields = {}
    for line in lines:
        stripped = line.strip()
        if not in_block:
            if stripped == "Current Network Information:":
                in_block = True
                header_indent = len(line) - len(line.lstrip(" "))
            continue
        if not stripped:
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent <= header_indent:
            break
        key, sep, value = stripped.partition(":")
        if not sep or not value.strip():
            continue  # e.g. the SSID line itself, which has no value
        fields[key.strip()] = value.strip()

    result = {}
    if "PHY Mode" in fields:
        result["phy_mode"] = fields["PHY Mode"]
    channel_match = CHANNEL.match(fields.get("Channel", ""))
    if channel_match:
        result["channel"] = int(channel_match.group(1))
        result["band"] = channel_match.group(2)
    signal_match = SIGNAL_NOISE.match(fields.get("Signal / Noise", ""))
    if signal_match:
        result["signal_dbm"] = int(signal_match.group(1))
        result["noise_dbm"] = int(signal_match.group(2))
    return result or None


class WifiSignalSource:
    """Polls system_profiler for the current Wi-Fi signal, on its own timer
    (it's too slow to invoke every second)."""

    def __init__(self, run=None):
        self._run = run or self._run_system_profiler

    @staticmethod
    def _run_system_profiler():
        result = subprocess.run(["system_profiler", "SPAirPortDataType"],
                                 capture_output=True, text=True, timeout=10)
        return result.stdout

    def poll(self):
        """The current signal dict (see parse_wifi_signal), or None."""
        try:
            return parse_wifi_signal(self._run())
        except (OSError, subprocess.TimeoutExpired):
            return None
