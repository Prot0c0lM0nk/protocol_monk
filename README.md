# Protocol Monk

Protocol Monk is a local-first terminal assistant with a `protocol_monk` CLI entrypoint, interactive Rich or prompt-toolkit UIs, tool execution, and provider support for Ollama or OpenRouter.

## Quick Install And Run

Install from a clone of this repo:

```bash
python -m pip install .
```

First run:

```bash
protocol_monk
```

If you want explicit local overrides, copy the example environment file first:

```bash
cp .env.example .env
```

## `pipx`

For an isolated CLI install:

```bash
pipx install .
```

After the first PyPI release, the intended end-user command is:

```bash
pipx install protocol-monk
```

## Provider Requirements

### Ollama

- Default provider path.
- Requires a reachable Ollama server, defaulting to `http://localhost:11434`.
- Requires at least one installed model that Ollama can serve.
- Model discovery cache is written to `./.protocol_monk/models.json`.

### OpenRouter

- Requires `OPENROUTER_API_KEY`.
- Uses the packaged example model map by default.
- Set `OPENROUTER_MODELS_JSON_PATH` if you want to manage your own model map file.

## Dev Setup

For reproducible contributor setup:

```bash
conda env create -f environment.yml
conda activate monk_env
python -m pip install -e .[dev]
```

Build and verify release artifacts:

```bash
python -m build
python -m twine check dist/*
```

## PyPI Publishing

This repo includes `.github/workflows/package-release.yml`.

Before the first PyPI release:

1. Create the `protocol-monk` project on PyPI.
2. Configure PyPI trusted publishing for this repository and workflow.
3. Push a version tag such as `v0.1.0`, or trigger the workflow manually.

## Current Status And Limits

- Source install and `pipx` install are verified.
- A PyPI publish workflow is prepared, but no release has been published yet.
- `LICENSE` is included, but it is a demo/evaluation license rather than an open-source redistribution/modification grant.
- Runtime behavior still depends on local provider configuration and available models.
