# MetaMender

**MetaMender** is a lightweight, AI-powered metadata enhancer for Jellyfin.
It enriches your media library by rewriting short or missing overviews for music items using your preferred language model — no servers, no Docker, no complexity.

---

## 🎯 What It Does

- Scans your Jellyfin library for albums and artists with poor or missing descriptions
- Uses your configured model to generate high-quality, streaming-style summaries
- Automatically applies changes through the Jellyfin API
- Keeps a full log of changes with before/after text and token usage
- Designed to be terminal-based and lightweight

---

## ⚙️ Configuration

1. Copy `config.template.json` and rename it to `config.json`.
2. Open `config.json` and fill in the required fields:
   - Jellyfin server URL
   - Jellyfin API key
   - Your Jellyfin user ID
   - API keys for the model provider you wish to use (OpenAI, Anthropic, Google)
3. (Optional) Specify a preferred model or item types to target and choose a `model_provider`.

> Note: `config.json` is excluded from the repo to keep your credentials secure.

---

### 📚 Model Provider Options

Set the `"model_provider"` field in your `config.json` to one of these values:

| `model_provider` | Description              | Required Config Keys                   | Example `"model"`       |
|------------------|-------------------------|----------------------------------------|-------------------------|
| `openai`         | OpenAI API (default)    | `openai_api_key`, `model`              | `"gpt-4o"`              |
| `anthropic`      | Anthropic Claude        | `anthropic_api_key`, `model`           | `"claude-3-haiku-20240307"` |
| `google`         | Google Gemini           | `google_api_key`, `model`              | `"gemini-pro"`          |
| `local`          | Ollama (local models)   | Ollama server running, `model`         | `"llama3"`, `"mistral"` |

#### Example configs:

**OpenAI**:
```json
{
  "model_provider": "openai",
  "openai_api_key": "sk-...",
  "model": "gpt-4o",
  ...
}
````

**Anthropic**:

```json
{
  "model_provider": "anthropic",
  "anthropic_api_key": "sk-ant-...",
  "model": "claude-3-haiku-20240307",
  ...
}
```

**Google**:

```json
{
  "model_provider": "google",
  "google_api_key": "AIza...",
  "model": "gemini-pro",
  ...
}
```

**Local (Ollama)**:

```json
{
  "model_provider": "local",
  "model": "llama3",
  ...
}
```

> For Ollama, ensure you have the model pulled and your local Ollama server is running (`ollama serve`).

---

### How to Choose

* **`openai`**: Use for ChatGPT models with an OpenAI API key.
* **`anthropic`**: Use for Claude models if you have access.
* **`google`**: Use for Gemini models with a Google API key.
* **`local`**: Use for running LLMs on your own machine via Ollama.

---

## 🧪 How to Run

1. Make sure Python 3.8+ is installed.
2. Install dependencies using the `requirements.txt` file.
3. Run the script: `metamender.py`

If everything is already well-described, the app will tell you — otherwise, it starts updating automatically.

---

## 🧾 Logs

Each run generates a timestamped log in the `logs/` folder. These logs show:

* Item names and types
* Original vs. generated overviews
* Token usage and estimated API cost
* Any skipped items with HTTP error codes

---

## ⚠️ Error Handling

If the API returns an error for an item, MetaMender logs a warning with
that item's ID and skips the update. These items are counted as "skipped" in the
final summary.

---

## 🛠️ Planned Features

* Support for TV shows, movies, books, and more
* Optional manual approval before applying changes
* Background auto-run support
* Clean web-based UI
* **AI-generated images for items missing artwork** (via OpenAI’s image model)
* Token tracking and usage analytics

---

## 🤝 Contributions & Feedback

MetaMender is built to be lightweight, hackable, and personal.
Suggestions, forks, and contributions are welcome.
