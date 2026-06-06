# Contributing to autoria-mcp

Thanks for your interest! This is a small, focused project — contributions that
fix bugs, improve docs, or sharpen the existing tool surface are very welcome.

## Development setup

The project uses [uv](https://docs.astral.sh/uv/). Python 3.11+ is required.

```sh
git clone https://github.com/yevhen-kalyna/autoria-mcp
cd autoria-mcp
uv sync                 # create the venv and install deps (incl. the dev group)
pre-commit install      # enable the git hooks (ruff + format on commit)
```

You do **not** need an AUTO.RIA API key to develop or run the test suite — the
tests are fully offline (see below).

## Quality gates

These four checks must pass; CI runs them on Python 3.11 and 3.12, and they mirror
what `pre-commit` enforces locally:

```sh
uv run ruff check .            # lint
uv run ruff format --check .   # formatting
uv run mypy src                # strict type check
uv run pytest                  # tests
```

`ruff` is configured for both linting and formatting (line length 100); `mypy` runs
in `--strict` mode. Run `uv run ruff format .` to auto-fix formatting.

## Tests must not hit the network

Quota on the AUTO.RIA free tier is scarce, and the test suite must stay
deterministic. **No test may make a live API call.** HTTP is mocked with
[`respx`](https://lundberg.github.io/respx/) against recorded fixtures under
`tests/fixtures/`. If you add behaviour that touches a new endpoint, record a
representative response as a fixture and mock it — never call the real API from a
test. Scrub any `api_key` / `user_id` from captured payloads before committing.

## Pull requests

- Branch off `main`; PRs are **squash-merged**.
- Use [Conventional Commits](https://www.conventionalcommits.org/) for the PR title
  (e.g. `fix(search): …`, `docs(readme): …`) — it becomes the squash commit message.
- Keep changes focused; update `README.md` / `CHANGELOG.md` when behaviour or the
  tool surface changes.
- Make sure all four quality gates above are green before requesting review.

## Releasing (maintainers)

Publishing uses GitHub Actions + OIDC Trusted Publishing (no tokens). The publish
steps **cannot be validated locally** — `uv build` / `twine check` never exercise
them — so always rehearse on TestPyPI before tagging.

1. **Bump the version** in `pyproject.toml` and move `CHANGELOG.md`'s `Unreleased`
   entries under a dated release heading. The git tag must match this version.
2. **Dry-run to TestPyPI**: Actions → *Release* → **Run workflow**
   (`workflow_dispatch`). This builds, runs `twine check`, and publishes to
   TestPyPI (ungated). Treat this as a required gate, not a one-off.
3. **Smoke-test the published TestPyPI artifact** in a clean environment — this
   installs the *uploaded* wheel, not your local source. Run it **outside** the
   repo so the local project doesn't shadow it; dependencies resolve from PyPI
   (TestPyPI doesn't carry them), while `--index` pulls `autoria-mcp` from TestPyPI:

   ```sh
   uv run --isolated --no-project \
     --index https://test.pypi.org/simple/ \
     --with autoria-mcp \
     autoria-mcp --version
   ```

4. **Release**: push the tag — `git tag vX.Y.Z && git push origin vX.Y.Z`. The
   tag run publishes to PyPI via the reviewer-gated `pypi` environment; approve the
   pending `publish-pypi` job in the Actions UI.

First-time setup (once per index): add the GitHub Trusted Publisher on PyPI and
TestPyPI (repo `yevhen-kalyna/autoria-mcp`, workflow `release.yml`, environments
`pypi` / `testpypi`), and create those two environments in repo settings (add a
required reviewer to `pypi`).

## Reporting security issues

Please do **not** open a public issue for vulnerabilities — see
[`SECURITY.md`](SECURITY.md).
