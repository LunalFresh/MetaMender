# MetaMender

**MetaMender** is a lightweight, AI-powered metadata enhancer for Jellyfin.  
It enriches your media library by rewriting short or missing overviews for music items using OpenAI — no servers, no Docker, no complexity.

---

## 🎯 What It Does

- Scans your Jellyfin library for albums and artists with poor or missing descriptions
- Uses OpenAI to generate high-quality, streaming-style summaries
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
   - OpenAI API key
3. (Optional) Specify a preferred OpenAI model or item types to target.

> Note: `config.json` is excluded from the repo to keep your credentials secure.

---

## 🧪 How to Run

1. Make sure Python 3.8+ is installed.
2. Install dependencies using the `requirements.txt` file.
3. Run the script: `metamender.py`

If everything is already well-described, the app will tell you — otherwise, it starts updating automatically.

---

## 🧾 Logs

Each run generates a timestamped log in the `logs/` folder. These logs show:
- Item names and types
- Original vs. generated overviews
- Token usage and estimated API cost
- Any skipped items with HTTP error codes

---

## ⚠️ Error Handling

If the OpenAI API returns an error for an item, MetaMender logs a warning with
that item's ID and skips the update. These items are counted as "skipped" in the
final summary.

---

## 🛠️ Planned Features

- Support for TV shows, movies, books, and more
- Optional manual approval before applying changes
- Background auto-run support
- Clean web-based UI
- **AI-generated images for items missing artwork** (via OpenAI’s image model)
- Token tracking and usage analytics

---

## 🤝 Contributions & Feedback

MetaMender is built to be lightweight, hackable, and personal.  
Suggestions, forks, and contributions are welcome.