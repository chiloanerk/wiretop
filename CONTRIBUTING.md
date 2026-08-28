# Contributing

## Branching strategy

`wiretop` uses **trunk-based development**: `main` is always the source of
truth and should always be in a releasable state. No `develop` branch, no
long-lived `release/*` branches — those add process overhead this project
doesn't need at its current size, and fight against everything else here
being kept boring and simple.

### Day-to-day work

- Branch off `main` for anything more than a one-line fix:
  `feature/<short-name>`, `fix/<short-name>`, `chore/<short-name>` (docs,
  packaging, CI-only changes).
- Keep branches short-lived — hours to a few days, not weeks. If a branch is
  living long enough to drift from `main`, it's a sign the change should be
  split smaller.
- Merge back into `main` once tests pass
  (`.venv/bin/python -m unittest discover -s tests`). Delete the branch
  after merging.
- Trivial fixes (a typo, a one-line correction) can go straight to `main`
  without a branch — use judgement, don't force ceremony onto small changes.

### Releasing

Releases are cut from `main` at whatever commit is ready — there's no
separate release branch. The process (see also `CHANGELOG.md`):

1. Add a `## [x.y.z] - YYYY-MM-DD` entry to `CHANGELOG.md`.
2. Bump `version` in `pyproject.toml` to match.
3. Commit and push to `main`.
4. Tag and push the tag:
   ```
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```
5. The `publish.yml` GitHub Actions workflow builds and publishes to PyPI
   automatically via Trusted Publishing — no manual `twine upload` needed.
6. Create a GitHub Release for the tag with notes matching the changelog
   entry (`gh release create vX.Y.Z --notes "..."`, or via GitHub's UI).

### Hotfixes

If a bug needs an urgent patch and `main` has since moved on with unrelated
in-progress work: branch `fix/<short-name>` from `main` (not from the old
tag — there's no supported older version line to patch separately), fix,
merge, then release a new patch version through the normal process above.
This project doesn't currently support maintaining multiple version lines
in parallel; if that ever becomes necessary, revisit this document.

### Branch protection (recommended, not yet configured)

Once there's more than one contributor, turn on branch protection for
`main`: require the test suite to pass before merging, require at least one
review. Not urgent for a solo-maintained project, but worth doing before
opening the project up to outside contributions.
