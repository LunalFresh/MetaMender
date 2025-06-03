#!/usr/bin/env python3
"""
MetaMender Phase-1 — fully automatic
• Rewrites missing/short overviews for MusicAlbum & MusicArtist (and any other
  ItemTypes you list in config.json)
• Applies them without prompts
• Shows a tqdm progress bar
• Writes a detailed run log to logs/MetaMender_YYYY-MM-DD_HH-MM-SS.txt
• Skips and logs items that return 404 / 403 / 410 instead of crashing
"""

import json, os, datetime, logging, textwrap
import requests, openai
from requests.exceptions import HTTPError
from tqdm import tqdm

# ── settings ────────────────────────────────────────────────────────────────
MIN_LEN       = 50
DEFAULT_MODEL = "gpt-4.1-mini"
EXTRA_FIELDS  = (
    "Overview,Artists,Album,Genres,ParentId,OriginalTitle,"
    "ProductionYear,SortName,PremiereDate"
)
LOG_DIR       = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

# ── Jellyfin helpers ─────────────────────────────────────────────────────────
def load_cfg(path="config.json"):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def jget(url, key, **params):
    params["api_key"] = key
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def jpost(url, key, payload):
    requests.post(url, params={"api_key": key},
                  json=payload, timeout=30).raise_for_status()

def safe_update_overview(base, key, uid, item_id, new_text):
    """Fetch full DTO via user path, patch Overview, POST back. Skip 4xx."""
    try:
        full = jget(f"{base}/Users/{uid}/Items/{item_id}", key)
    except HTTPError as e:
        if e.response.status_code in (404, 403, 410):
            logging.warning("‼️  skip %s – %s", item_id, e.response.reason)
            return False
        raise                      # unexpected error → propagate
    full["Overview"] = new_text
    jpost(f"{base}/Items/{item_id}", key, full)
    return True

def is_bad(txt):  # overview too short / missing
    return txt is None or len(txt.strip()) < MIN_LEN

# ── prompt + OpenAI ─────────────────────────────────────────────────────────
def prompt_for(it):
    typ    = it["Type"]
    title  = it.get("Name") or it.get("OriginalTitle") or "Untitled"
    year   = it.get("ProductionYear") or "Unknown"
    genres = ", ".join(it.get("Genres", [])) or "Various genres"
    old    = it.get("Overview") or "(none)"

    if typ == "MusicAlbum":
        artist = ", ".join(it.get("Artists", [])) or "Various Artists"
        return (
            f'Write a vibrant, Spotify-style album blurb (18-25 words) for '
            f'"{title}" ({year}) by {artist}. Summarize sound & theme, add one '
            f'concrete hook (hit track, chart feat.). Use max one vivid adjective '
            f'per phrase. Genres: {genres}. Current: {old}'
        )
    if typ == "MusicArtist":
        return (
            f'Write a concise artist bio (20-30 words) for {title}. Include origin, '
            f'style, and one standout milestone. Genres: {genres}. Current: {old}'
        )
    # fallback for any other types you include
    return (
        f'Rewrite this {typ.lower()} overview (25-40 words) in polished streaming style. '
        f'Title: {title}. Year: {year}. Current: {old}'
    )

def beautify(it, model):
    """Return rewritten overview text and token count or ``(None, 0)`` on error."""
    try:
        resp = openai.chat.completions.create(
            model=model,
            messages=[
                {"role": "system",
                 "content": "You craft concise, engaging overviews for media items."},
                {"role": "user", "content": prompt_for(it)}
            ],
            max_tokens=120,
            temperature=0.4,   # your preferred temp
        )
    except openai.OpenAIError as e:  # network, quota, etc.
        logging.warning("‼️  OpenAI error for ID %s – %s", it.get("Id"), e)
        return None, 0

    return resp.choices[0].message.content.strip(), resp.usage.total_tokens

# ── main ─────────────────────────────────────────────────────────────────────
def main():
    cfg  = load_cfg()
    base = cfg["jellyfin_url"].rstrip("/")
    key  = cfg["jellyfin_api_key"]
    uid  = cfg["user_id"]
    types= cfg.get("item_types") or ["MusicAlbum", "MusicArtist"]
    lib  = cfg.get("library_id")
    model= cfg.get("openai_model", DEFAULT_MODEL)

    # log file setup
    stamp    = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_path = os.path.join(LOG_DIR, f"MetaMender_{stamp}.txt")
    logging.basicConfig(filename=log_path,
                        level=logging.INFO,
                        format="%(asctime)s  %(message)s",
                        datefmt="%H:%M:%S")

    logging.info("▶️  MetaMender run — model %s — types %s",
                 model, ", ".join(types))

    openai.api_key = cfg["openai_api_key"]

    query = {"IncludeItemTypes": ",".join(types),
             "Recursive": "true",
             "Fields": EXTRA_FIELDS}
    if lib: query["ParentId"] = lib

    items = jget(f"{base}/Users/{uid}/Items", key, **query)["Items"]
    items   = [i for i in items if i["Type"] != "Audio"]      # ignore tracks
    targets = [i for i in items if is_bad(i.get("Overview"))]

    if not targets:
        print("Nothing to fix – library already polished! 🎉")
        return

    total_tokens = updated = skipped = 0
    for it in tqdm(targets, desc="Beautifying", unit="item"):
        new_txt, tok = beautify(it, model)
        if new_txt is None:           # OpenAI error
            skipped += 1
            continue
        total_tokens += tok

        if safe_update_overview(base, key, uid, it["Id"], new_txt):
            updated += 1
            logging.info(
                "\n%s | %s | ID %s\nOLD: %s\nNEW: %s\n",
                it["Type"], it["Name"], it["Id"],
                textwrap.shorten(it.get("Overview") or "(none)", 180),
                new_txt
            )
        else:
            skipped += 1

    cost = total_tokens * 0.00001   # adjust for your model’s pricing
    logging.info("✅ Done. Updated %d, skipped %d, tokens %d (≈$%.4f)",
                 updated, skipped, total_tokens, cost)

    print(f"\nFinished! ✅ {updated} items updated, {skipped} skipped.")
    print(f"Token usage: {total_tokens}  |  Approx cost: ${cost:.4f}")
    print(f"Detailed log saved to: {log_path}")

if __name__ == "__main__":
    main()
