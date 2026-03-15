# Protocol Monk

Protocol Monk is a local-first terminal assistant with a `protocol_monk` CLI entrypoint, interactive Rich or prompt-toolkit UIs, tool execution, and provider support for Ollama or OpenRouter.

## Quick Install And Run

Install from PyPI:

```bash
pipx install protocol-monk
```

Then run:

```bash
protocol_monk
```

If you want to install from a clone of this repo instead:

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

Published PyPI install path:

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
- The simplest current global setup is to export the key in your shell profile, for example `~/.zshrc`.
- Uses the packaged example model map by default.
- Set `OPENROUTER_MODELS_JSON_PATH` if you want to manage your own model map file.

Example shell setup:

```bash
export OPENROUTER_API_KEY="your_key_here"
export LLM_PROVIDER="openrouter"
```

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

The `protocol-monk` package is now published on PyPI.

Future releases can continue to use the GitHub Actions publish workflow through trusted publishing.

## Current Status And Limits

- Source install and `pipx` install are verified.
- PyPI install is now available with `pipx install protocol-monk`.
- `LICENSE` is included, but it is a demo/evaluation license rather than an open-source redistribution/modification grant.
- Runtime behavior still depends on local provider configuration and available models.
