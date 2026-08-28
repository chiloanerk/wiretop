# wiretop

A `mactop`-style dashboard for network usage on your Mac: a grid of live
cards — throughput graph, top programs, usage breakdown, interfaces, Wi-Fi
signal, latency, and more — instead of one scrolling table.

```
pipx install wiretop
wiretop
```

(or `uv tool install wiretop`). Not on PyPI yet — until then, install from
source:

```
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/wiretop
```

Press `q` to quit, `s` to cycle how the Top Programs card is sorted, `k` to
kill the selected program's processes (always asks for confirmation first).

Needs a real macOS terminal (`nettop`, `netstat`, `system_profiler`, `ping`,
`lsof`) — no `sudo`.

## Cards

| Card | Shows |
|---|---|
| **Live Throughput** | Aggregate down/up speed right now, and a sparkline of the last couple of minutes |
| **Top Programs** | Per-program table: busy, down/up speed, total used, past-hour used, sending time. Sortable with `s`; the heaviest rows get a color gradient; a program spiking well above its own average is marked ⚠ |
| **Usage Breakdown** | Each tracked program's share of the total, as a block-bar |
| **Past Hour** | The same throughput history, downsampled into 5-minute buckets over the last hour |
| **Interfaces** | Wi-Fi/Ethernet/VPN/Loopback totals and rates, from `netstat -ib` — separate from the per-process view |
| **Latency** | Round-trip time to `1.1.1.1`, with a recent-history sparkline |
| **Top Destinations** | Which remote hosts each tracked program currently has open connections to, from `lsof` |
| **History** | Usage over time, persisted locally; starts at whatever fine granularity you actually have (minutes) and widens its buckets as more accumulates, up to 7 days |

A status bar under the header (not a card) shows Wi-Fi signal and session
vitals — uptime, samples collected, busiest program, peak speed — at a
glance, without taking up a grid slot.

## How the per-program numbers work

1. Reads network activity from macOS's `nettop`.
2. Measures for 10 seconds to see how much data each program sends and
   receives, then picks the heaviest users so far (up to 30 with `--top`).
3. Then goes live, updating once a second. The list is re-checked every
   second, so a program that turns heavy later — a video that starts playing
   after the 10-second warmup, say — can still push its way onto the list, in
   place of whichever tracked program has used the least data overall.
4. Rows are ranked by total data used by default (rather than a raw
   second-to-second speed), so they only reorder when a program's total
   actually overtakes another's — no constant reshuffling. Press `s` to cycle
   sorting between Total Used, Past Hour, and Current Speed instead.

**Helper processes are grouped under their app.** Chrome runs a dozen helper
processes; they are added up into one "Google Chrome" row. Names come from
`ps` and are traced back to the enclosing `.app` bundle, because `nettop`
truncates names to 15 characters.

## Kill action

`k` on the selected Top Programs row always opens a confirm dialog naming the
program and how many processes it would affect; only explicitly choosing
"Kill" sends `SIGTERM` (never `SIGKILL`) to those processes. Cancelling, or
doing nothing, leaves everything untouched.

## Other data sources and their polling rates

Each source polls on its own cadence rather than sharing nettop's once-a-second
tick, since they have very different real-world costs:

| Source | Command | Interval |
|---|---|---|
| Interfaces | `netstat -ib` | 2s |
| Wi-Fi signal | `system_profiler SPAirPortDataType` (slow to invoke) | 8s |
| Latency | `ping -c 1 1.1.1.1` | 3s |
| Top destinations | `lsof -i -P -n` | 4s |
| History | (writes to local sqlite) | 60s |

`wdutil info` would be the more direct way to get Wi-Fi signal, but it
requires `sudo` unconditionally on macOS, so `system_profiler` is used
instead. `nettop -m route` was considered for destinations but only buckets
by gateway/subnet, not by remote host per program — `lsof` is used instead,
though it's a snapshot of open sockets, not a byte-volume ranking.

## Layout

| File | What is in it |
|---|---|
| `wiretop.py` | Entry point: argument parsing, builds the data source, runs the app |
| `app.py` | The textual `App`: the card grid, per-source polling timers, key bindings, the kill-confirm modal |
| `cards.py` | The card widgets |
| `nettop_source.py` | Running `nettop` under a pty; replaying a capture |
| `interfaces.py` | Per-interface totals from `netstat -ib`, and which interface is Wi-Fi |
| `wifi.py` | Wi-Fi signal from `system_profiler` |
| `latency.py` | Ping-based latency |
| `destinations.py` | Per-program remote hosts from `lsof` |
| `history.py` | Rolling period-log sqlite persistence and adaptive bucketing for the History card |
| `procnames.py` | Turning a pid into a program name |
| `netstats.py` | Parsing, adding up, ranking, formatting — no input or output |
| `render.py` | Pure formatting helpers the cards call into (gradients, bars, vitals text) |

Every source module splits a pure parser (unit-tested against captured real
command output, no subprocess/network in the test) from a thin class that
actually shells out — the same convention `netstats.py`/`render.py` already
used before this rewrite.

## Tests

```
.venv/bin/python -m unittest discover -s tests
```

`tests/test_app.py` drives the actual textual app headlessly
(`App.run_test()`); everything else is pure-function unit tests with no
terminal, network, or subprocess involved.

To check the per-program cards end to end without waiting for real traffic,
capture some output once and replay it:

```
nettop -P -x -n -d -s 1 -L 30 -J bytes_in,bytes_out > sample.txt
.venv/bin/wiretop --replay sample.txt --warmup 5
```
