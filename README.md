# MetaMender

MetaMender is a lightweight metadata enhancer for Jellyfin. It scans media items
with missing or thin overviews, asks an AI provider to write short streaming-style
summaries, applies the updates through the Jellyfin API, and logs every change.

## What It Does

- Finds albums, artists, movies, series, episodes, books, or other configured item types
  with short overviews.
- Generates concise metadata with OpenAI, Anthropic, xAI/Grok, or an
  OpenAI-compatible provider.
- Automatically writes the improved overview back to Jellyfin.
- Keeps timestamped before/after logs in `logs/`.
- Tracks input and output token usage separately for better cost estimates.

## Requirements

- Python 3.10 or newer.
- A Jellyfin API key and user ID.
- An API key for the configured AI provider, unless you use a local provider
  that does not require one.

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

## Configuration

MetaMender requires `config.json`. The script reads its Jellyfin connection,
AI provider, API key, model, and target item types from that file.

1. Copy `config.template.json` to `config.json`.
2. Fill in these required values:
   - `jellyfin_url`
   - `jellyfin_api_key`
   - `user_id`
   - `ai_provider`
   - `ai_api_key` for hosted providers
3. Adjust optional settings as needed:
   - `library_id`
   - `item_types`
   - `ai_base_url`
   - `ai_model`
   - `ai_reasoning_effort`
   - `ai_max_output_tokens`
   - `ai_temperature`
   - `ai_input_cost_per_million`
   - `ai_output_cost_per_million`

`config.json` is ignored by Git so your local credentials stay out of commits.

The default model is `gpt-5.4-mini` with `ai_reasoning_effort` set to
`none`, which is a cost-conscious default for short metadata rewriting. Use
`gpt-5.4` when you want higher quality and are comfortable with higher cost.

## AI Providers

Set `ai_provider` to one of these values:

- `openai`: Uses OpenAI's Responses API. This is the default.
- `anthropic`: Uses Anthropic's Messages API.
- `xai` or `grok`: Uses xAI's Responses API with `https://api.x.ai/v1`.
- `openai_compatible`: Uses Chat Completions against your `ai_base_url`.
- `openrouter`: Uses Chat Completions with `https://openrouter.ai/api/v1`.
- `lmstudio`: Uses Chat Completions with `http://localhost:1234/v1`.
- `ollama`: Uses Chat Completions with `http://localhost:11434/v1`.

When `ai_model` is omitted, provider defaults are:

- `openai`: `gpt-5.4-mini`
- `anthropic`: `claude-haiku-4-5`
- `xai` or `grok`: `grok-4.20-reasoning`

Other OpenAI-compatible providers require `ai_model` because local/router model
names vary. Hosted providers also require `ai_api_key`; local providers such as
LM Studio and Ollama usually do not. `ai_reasoning_effort` only applies to the
OpenAI Responses API path. MetaMender omits it for Anthropic, xAI/Grok, and
compatible providers.

Example Anthropic config:

```json
"ai_provider": "anthropic",
"ai_api_key": "your-anthropic-key",
"ai_model": "claude-haiku-4-5"
```

Example Grok config:

```json
"ai_provider": "grok",
"ai_api_key": "your-xai-key",
"ai_model": "grok-4.20-reasoning"
```

## How to Run

```powershell
python .\metamender.py
```

If every configured item already has a usable overview, MetaMender exits without
making changes. Otherwise it updates matching items automatically.

## Logs

Each run creates a timestamped log in `logs/` with:

- Item names, types, and IDs.
- Original and generated overviews.
- Input and output token usage.
- Estimated cost when pricing is known or configured.
- Skipped items and HTTP errors.

## Notes

Provider pricing changes over time. MetaMender includes pricing for a few known
OpenAI models, but you can set `ai_input_cost_per_million` and
`ai_output_cost_per_million` in `config.json` when exact accounting matters.
