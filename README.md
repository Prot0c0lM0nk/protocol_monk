# Protocol Monk

Protocol Monk is currently a personal, source-first terminal tool with a Rich UI.

This is not a packaged product right now. There is no supported PyPI install, no app bundle, and no browser UI release. The stable path is running the tool locally from source.

## What This Repo Is

This GitHub repository is published from the `protocol_monk/` subtree of a larger local workspace. Treat it as a source mirror of the app package, not as a polished standalone distribution.

The main local workflow is:

```bash
source /opt/miniconda3/etc/profile.d/conda.sh
conda activate monk_env
cd /path/to/protocol_event_build
python -m protocol_monk.main
```

If you clone only this subtree repo, the simplest source layout is to clone it into a directory named `protocol_monk` and run from its parent directory so Python can import the package:

```bash
git clone https://github.com/Prot0c0lM0nk/protocol_monk.git protocol_monk
cd ..
python -m protocol_monk.main
```

## Current Runtime Contract

- Bootstrap config comes from `.env` in the larger workspace when present.
- The primary interface is the Rich terminal session started by `python -m protocol_monk.main`.
- Ollama and OpenRouter are intentionally separate and use different model-map contracts.

### Ollama

- Source of truth: live discovery from the Ollama API.
- Authoritative runtime map: `~/.protocol_monk/providers/ollama/models.json`
- Manual local context tuning is supported for downloaded models.
- If you lower a local model's `context_window`, refresh preserves it as `context_window_override` instead of snapping back to the discovered maximum.

### OpenRouter

- Source of truth: a curated tracked map in this repo.
- Authoritative map: `config/openrouter_models.json`
- This file is intentionally maintained as a small library of specific models, not a full catalog mirror.
- Update it with `scripts/fetch_openrouter_model_config.py` when the curated list changes.

## Requirements

- Python 3.14
- Ollama running at `http://localhost:11434` for local-model use
- `OPENROUTER_API_KEY` only when using the OpenRouter provider

## Updating The Curated OpenRouter Map

Example:

```bash
python -m protocol_monk.scripts.fetch_openrouter_model_config \
  --model openai/gpt-5.4 \
  --model anthropic/claude-sonnet-4.6 \
  --write-mode merge
```

See [scripts/OPENROUTER_MAP_UPDATE_GUIDE.md](scripts/OPENROUTER_MAP_UPDATE_GUIDE.md) for the current workflow.

## What This Repo Does Not Claim

- It is not a beginner-friendly packaged app.
- It is not currently distributed as a supported release artifact.
- It does not currently include the larger parent workspace's full test harness and repo-level scaffolding.
