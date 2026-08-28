# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.1] - 2026-08-28

### Changed
- Version bump only, to unblock the first automated release through the new
  GitHub Actions + PyPI Trusted Publishing pipeline. No functional changes
  from 0.1.0.

## [0.1.0] - 2026-08-28

Initial release.

### Added
- A `mactop`-style multi-card network dashboard for macOS, built on `textual`.
- Cards: Live Throughput, Top Programs, Usage Breakdown, Interfaces, Latency,
  Top Destinations, History.
- A status bar showing Wi-Fi signal and session vitals.
- Sort cycling (`s`), color theme cycling (`t`), refresh-rate cycling (`r`).
- Kill action (`k`) for the selected program, with a mandatory confirm step.
- Best-effort reverse-DNS for Top Destinations, cached, with an automatic
  scrolling ticker for destination lists too long to fit on one line.
- History card that grows its bucket granularity from minutes up to 7 days
  as data actually accumulates, instead of one lonely bar on day one.
- Packaged for PyPI — installable via `pipx`, `uv tool`, or `pip`.

[0.1.1]: https://github.com/chiloanerk/wiretop/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/chiloanerk/wiretop/releases/tag/v0.1.0
