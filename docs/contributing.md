# Contributor documentation

This guide is for people changing or maintaining sonicprobe. For installation, configuration and everyday use, start with the [user documentation](https://github.com/decryptus/sonicprobe/blob/master/README.md).

## Tests and release

```sh
python -m pip install -e . mock
python .github/scripts/check-test-collection.py --runner unittest tests
python -m unittest discover -s tests -v
python -m pip install build twine
python -m build
python -m twine check --strict dist/*
```

CI tests core workers, helpers, SQL and local server behavior on the configured
interpreter matrix. PyPI publishing is gated by these tests and artifact validation.
Update `VERSION`, `RELEASE` and `setup.yml` together. Merging to master creates a
new `vX.Y.Z` tag and publishes via Trusted Publishing (`decryptus/sonicprobe`,
workflow `pypi.yml`, environment `pypi`). Existing tags are never overwritten. A GitHub release with versioned notes and
distributions is created after successful PyPI publication.

License: GPL-3.0-or-later; original module copyrights remain in the source.

See the [September 2026 code and architecture review](https://github.com/decryptus/sonicprobe/blob/master/docs/REVIEW.md) (French).

See the [XYS schema guide](https://github.com/decryptus/sonicprobe/blob/master/docs/xys.md) for configuration validation, extensions,
modifier semantics and compatibility notes for the proposed validator cleanup.

## Documentation rules

Keep user instructions and contributor material separate. The repository [engineering requirements](https://github.com/decryptus/sonicprobe/blob/master/AGENTS.md) define the review and validation rules. Preserve user-facing compatibility, security and recovery guidance when moving internal explanations.
