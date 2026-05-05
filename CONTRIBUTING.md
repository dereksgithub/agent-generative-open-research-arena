# Contributing to AGORA

AGORA is currently preparing for a first public alpha. Contributions should keep
the first researcher workflow stable: install, run an example scenario, inspect
outputs, and reproduce seeded heuristic runs.

## Local Setup

```bash
uv venv .venv --python 3.12
source .venv/bin/activate
uv pip install -e ".[dev]"
```

If `uv` is not available, use standard `venv` and `pip install -e ".[dev]"`.

For the spatial viewer:

```bash
cd viz/spatial
npm ci
npm run build
```

## Checks Before Opening a PR

Run the checks that match the release surface:

```bash
ruff check engine/
pytest engine/tests -q
uv build
```

If `uv` is not available, use `pip wheel . --no-deps -w /tmp/agora-build`
as a local packaging smoke test.

For spatial changes:

```bash
cd viz/spatial
npm ci
npm audit --audit-level=moderate
npm run build
```

## Change Guidelines

- Keep deterministic heuristic outputs stable unless the change intentionally
  updates simulation semantics.
- Update or add tests when changing scenario parsing, engine behavior, output
  contracts, LLM orchestration, or visualization server behavior.
- Keep public output formats backward-compatible where possible.
- Do not commit generated run outputs, local virtual environments, dependency
  folders, or editor/system artifacts.
- Document user-facing workflow changes in `README.md` and `docs/`.

## Release Notes

Add user-visible changes to `CHANGELOG.md` under `Unreleased`.
