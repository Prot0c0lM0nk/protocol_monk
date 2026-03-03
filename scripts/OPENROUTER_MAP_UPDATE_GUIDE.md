# OpenRouter Map Update Guide

This guide shows how to update `protocol_monk/config/openrouter_models.json` using only the specific OpenRouter models you want.

The updater script:
- Fetches OpenRouter catalog data from `https://openrouter.ai/api/v1/models`
- Updates only the model IDs you request
- Preserves existing `user_overrides` for updated models
- Writes capability flags and pricing metadata when available

## File Paths

- Script: `protocol_monk/scripts/fetch_openrouter_model_config.py`
- Runtime map: `protocol_monk/config/openrouter_models.json`
- Example map: `protocol_monk/config/openrouter_models.example.json`

## Prerequisites

1. Activate the project environment:

```bash
source /opt/miniconda3/etc/profile.d/conda.sh
conda activate monk_env
```

2. Ensure your API key is set (recommended):

```bash
export OPENROUTER_API_KEY="your_key_here"
```

If no API key is set, the script still attempts the fetch, but authentication/rate limits may block it.

## Quick Start

Update two specific models and keep everything else in the file:

```bash
python -m protocol_monk.scripts.fetch_openrouter_model_config \
  --model z-ai/glm-5 \
  --model mistralai/ministral-14b-2512
```

## Recommended Workflow (Safe)

1. Preview changes without writing:

```bash
python -m protocol_monk.scripts.fetch_openrouter_model_config \
  --model z-ai/glm-5 \
  --model mistralai/ministral-14b-2512 \
  --dry-run
```

2. Apply changes:

```bash
python -m protocol_monk.scripts.fetch_openrouter_model_config \
  --model z-ai/glm-5 \
  --model mistralai/ministral-14b-2512
```

3. Validate map loads cleanly in app startup:

```bash
python -m pytest -q
```

## Update Modes

### `--write-mode merge` (default)

- Updates requested models
- Keeps all other existing models
- Keeps existing default model if still valid

Example:

```bash
python -m protocol_monk.scripts.fetch_openrouter_model_config \
  --model z-ai/glm-5 \
  --write-mode merge
```

### `--write-mode replace`

- Keeps only requested models
- Useful when you want a tightly curated map

Example:

```bash
python -m protocol_monk.scripts.fetch_openrouter_model_config \
  --model z-ai/glm-5 \
  --model qwen/qwen3.5-35b-a3b \
  --write-mode replace \
  --default-model z-ai/glm-5
```

## Useful Options

- `--model <id>`: Repeatable. Required.
- `--default-model <id>`: Force default model after update.
- `--output <path>`: Write map to a different file.
- `--base-url <url>`: Override API base URL.
- `--api-key <key>`: Override env API key.
- `--timeout <seconds>`: HTTP timeout.
- `--dry-run`: Build and validate output without writing.

## What Gets Updated Per Model

Each updated model entry includes:
- Required runtime fields:
  - `name`, `family`, `context_window`
  - `supports_tools`, `supports_thinking`
  - `parameters`, `user_overrides`
- Additional metadata:
  - `capabilities` (for example `completion`, `tools`, `thinking`, `vision`)
  - `supported_parameters`
  - `pricing` with:
    - `raw` values from OpenRouter
    - `usd_per_token` numeric values (when parseable)
    - `usd_per_million_tokens` computed values (when parseable)

`user_overrides` is preserved from your current map and copied into `parameters`.

## Troubleshooting

### "OpenRouter catalog did not contain requested model(s)"

- The model ID is incorrect or no longer listed.
- Re-check exact ID spelling (including provider prefix).

### HTTP/auth errors

- Confirm `OPENROUTER_API_KEY` is valid.
- Retry with a longer timeout:

```bash
python -m protocol_monk.scripts.fetch_openrouter_model_config \
  --model z-ai/glm-5 \
  --timeout 40
```

### "Requested default model is not present after update"

- Use a default that exists in the resulting model set.

## Practical Tip

Keep your map small and intentional:
- Add only the model IDs you actually use.
- Refresh those IDs periodically.
- Avoid bulk-fetching the full catalog unless you need it.
