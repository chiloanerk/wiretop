#!/usr/bin/env python3
"""Shows which programs on this Mac are using the most network data, as a
multi-card dashboard.

Measures for ten seconds, picks the heaviest users, then updates in place.
Press 's' to cycle how the list is sorted, 'k' to kill the selected program
(with a confirmation step), 'q' to quit.
"""

import argparse
import locale
import sys

from app import NetTopApp
from nettop_source import NettopSource, NettopUnavailable, ReplaySource

MAX_TOP = 20


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warmup", type=int, default=10,
                        help="seconds to measure before choosing the top programs")
    parser.add_argument("--top", type=int, default=20,
                        help=f"how many programs to follow (max {MAX_TOP})")
    parser.add_argument("--replay", metavar="FILE",
                        help="play back captured nettop output instead of watching live")
    args = parser.parse_args(argv)
    args.top = min(args.top, MAX_TOP)
    return args


def main(argv=None):
    args = parse_args(argv)
    locale.setlocale(locale.LC_ALL, "")

    try:
        source = ReplaySource(args.replay) if args.replay else NettopSource()
    except NettopUnavailable as unavailable:
        print(unavailable, file=sys.stderr)
        return 1
    except OSError as unreadable:
        print(f"Could not read {args.replay}: {unreadable}", file=sys.stderr)
        return 1

    app = NetTopApp(source, args)
    try:
        app.run()
    except KeyboardInterrupt:
        return 0

    if app.problem is not None:
        print(f"\n{app.problem}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
