#!/usr/bin/env python3
"""
MetaMender updates missing or short Jellyfin overviews with concise AI-written
metadata and logs every before/after change.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from openai import OpenAI, OpenAIError
from openai.types.chat import ChatCompletion
from openai.types.responses import Response
from requests import Session
from requests.exceptions import HTTPError, RequestException
from tqdm import tqdm

try:
    import anthropic
    from anthropic import AnthropicError
except ImportError:
    anthropic = None

    class AnthropicError(Exception):
        pass


MIN_LEN = 50
DEFAULT_MODEL = "gpt-5.4-mini"
DEFAULT_MODELS = {
    "openai": DEFAULT_MODEL,
    "anthropic": "claude-haiku-4-5",
    "xai": "grok-4.20-reasoning",
    "grok": "grok-4.20-reasoning",
}
DEFAULT_REASONING_EFFORT = "none"
DEFAULT_MAX_OUTPUT_TOKENS = 120
DEFAULT_TEMPERATURE = 0.4
REQUEST_TIMEOUT_SECONDS = 30
EXTRA_FIELDS = (
    "Overview,Artists,Album,Genres,ParentId,OriginalTitle,"
    "ProductionYear,SortName,PremiereDate"
)
LOG_DIR = Path("logs")
OPENAI_PROVIDER = "openai"
ANTHROPIC_PROVIDER = "anthropic"
XAI_PROVIDERS = {"xai", "grok"}
RESPONSES_API_PROVIDERS = {OPENAI_PROVIDER, *XAI_PROVIDERS}
COMPATIBLE_PROVIDERS = {
    "openai_compatible",
    "openrouter",
    "lmstudio",
    "ollama",
}
PROVIDER_BASE_URLS = {
    "xai": "https://api.x.ai/v1",
    "grok": "https://api.x.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "lmstudio": "http://localhost:1234/v1",
    "ollama": "http://localhost:11434/v1",
}
PROVIDERS_REQUIRING_API_KEY = {
    ANTHROPIC_PROVIDER,
    OPENAI_PROVIDER,
    "openrouter",
    "xai",
    "grok",
}

# Prices are USD per 1M tokens for known defaults. OpenAI pricing can change, so
# prefer config overrides for strict accounting.
KNOWN_MODEL_PRICING = {
    "gpt-5.4": (2.50, 15.00),
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.4-nano": (0.20, 1.25),
}


@dataclass(frozen=True)
class Config:
    jellyfin_url: str
    jellyfin_api_key: str
    user_id: str
    library_id: str | None
    item_types: list[str]
    ai_provider: str
    ai_api_key: str | None
    ai_base_url: str | None
    ai_model: str
    ai_reasoning_effort: str | None
    ai_max_output_tokens: int
    ai_temperature: float | None
    ai_input_cost_per_million: float | None
    ai_output_cost_per_million: float | None


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError as exc:
        raise SystemExit(
            f"Missing {path}. Copy config.template.json to config.json and fill it in."
        ) from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc


def clean_config_value(value: Any) -> Any:
    if isinstance(value, str) and value.startswith("your-"):
        return None
    return value


def config_value(
    cfg: dict[str, Any],
    key: str,
    *,
    required: bool = True,
    default: Any = None,
) -> Any:
    value = clean_config_value(cfg.get(key, default))
    if required and value in (None, ""):
        raise SystemExit(f"Missing required setting in config.json: {key}")
    return value


def first_config_value(
    cfg: dict[str, Any],
    keys: list[str],
    *,
    required: bool = True,
    default: Any = None,
) -> Any:
    for key in keys:
        value = clean_config_value(cfg.get(key))
        if value not in (None, ""):
            return value

    if required and default in (None, ""):
        joined_keys = ", ".join(keys)
        raise SystemExit(f"Missing required setting in config.json: one of {joined_keys}")
    return default


def load_cfg(path: str = "config.json") -> Config:
    raw = load_json(Path(path))
    item_types = raw.get("item_types") or ["MusicAlbum", "MusicArtist"]
    supported_providers = {
        ANTHROPIC_PROVIDER,
        OPENAI_PROVIDER,
        *COMPATIBLE_PROVIDERS,
        *XAI_PROVIDERS,
    }
    ai_provider = str(
        first_config_value(
            raw,
            ["ai_provider", "model_provider"],
            required=False,
            default=OPENAI_PROVIDER,
        )
    ).lower()

    if ai_provider not in supported_providers:
        providers = ", ".join(sorted(supported_providers))
        raise SystemExit(f"Unsupported ai_provider {ai_provider!r}. Use one of: {providers}")

    provider_base_url = PROVIDER_BASE_URLS.get(ai_provider)
    api_key_required = ai_provider in PROVIDERS_REQUIRING_API_KEY
    provider_default_model = DEFAULT_MODELS.get(ai_provider)

    return Config(
        jellyfin_url=str(
            config_value(raw, "jellyfin_url", default="http://localhost:8096")
        ).rstrip("/"),
        jellyfin_api_key=str(config_value(raw, "jellyfin_api_key")),
        user_id=str(config_value(raw, "user_id")),
        library_id=config_value(raw, "library_id", required=False),
        item_types=[str(item_type) for item_type in item_types],
        ai_provider=ai_provider,
        ai_api_key=first_config_value(
            raw,
            ["ai_api_key", "openai_api_key"],
            required=api_key_required,
        ),
        ai_base_url=first_config_value(
            raw,
            ["ai_base_url", "openai_base_url"],
            required=ai_provider == "openai_compatible" and provider_base_url is None,
            default=provider_base_url,
        ),
        ai_model=str(first_config_value(
            raw,
            ["ai_model", "openai_model"],
            required=provider_default_model is None,
            default=provider_default_model,
        )),
        ai_reasoning_effort=first_config_value(
            raw,
            ["ai_reasoning_effort", "openai_reasoning_effort"],
            required=False,
            default=DEFAULT_REASONING_EFFORT,
        ),
        ai_max_output_tokens=int(
            first_config_value(
                raw,
                ["ai_max_output_tokens", "openai_max_output_tokens"],
                required=False,
                default=DEFAULT_MAX_OUTPUT_TOKENS,
            )
        ),
        ai_temperature=optional_float(
            first_config_value(
                raw,
                ["ai_temperature", "openai_temperature"],
                required=False,
                default=DEFAULT_TEMPERATURE,
            )
        ),
        ai_input_cost_per_million=optional_float(
            first_config_value(
                raw,
                ["ai_input_cost_per_million", "openai_input_cost_per_million"],
                required=False,
            )
        ),
        ai_output_cost_per_million=optional_float(
            first_config_value(
                raw,
                ["ai_output_cost_per_million", "openai_output_cost_per_million"],
                required=False,
            )
        ),
    )


def optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def build_ai_client(cfg: Config) -> Any:
    if cfg.ai_provider == ANTHROPIC_PROVIDER:
        return build_anthropic_client(cfg)

    kwargs: dict[str, Any] = {"api_key": cfg.ai_api_key or "not-needed"}
    if cfg.ai_base_url:
        kwargs["base_url"] = cfg.ai_base_url
    return OpenAI(**kwargs)


def build_anthropic_client(cfg: Config) -> Any:
    if anthropic is None:
        raise RuntimeError(
            "Anthropic provider requires the anthropic package. "
            "Run: python -m pip install -r requirements.txt"
        )

    kwargs: dict[str, Any] = {"api_key": cfg.ai_api_key}
    if cfg.ai_base_url:
        kwargs["base_url"] = cfg.ai_base_url
    return anthropic.Anthropic(**kwargs)


def jget(session: Session, url: str, api_key: str, **params: Any) -> dict[str, Any]:
    params["api_key"] = api_key
    response = session.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def jpost(session: Session, url: str, api_key: str, payload: dict[str, Any]) -> None:
    response = session.post(
        url,
        params={"api_key": api_key},
        json=payload,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()


def safe_update_overview(
    session: Session,
    base_url: str,
    api_key: str,
    user_id: str,
    item_id: str,
    new_text: str,
) -> bool:
    """Fetch the full Jellyfin DTO, patch Overview, then post it back."""
    try:
        full = jget(session, f"{base_url}/Users/{user_id}/Items/{item_id}", api_key)
    except HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status in (403, 404, 410):
            logging.warning("Skipping %s because Jellyfin returned %s", item_id, status)
            return False
        raise

    full["Overview"] = new_text
    jpost(session, f"{base_url}/Items/{item_id}", api_key, full)
    return True


def is_bad(text: str | None) -> bool:
    return text is None or len(text.strip()) < MIN_LEN


def prompt_for(item: dict[str, Any]) -> str:
    item_type = item["Type"]
    title = item.get("Name") or item.get("OriginalTitle") or "Untitled"
    year = item.get("ProductionYear") or "Unknown"
    genres = ", ".join(item.get("Genres", [])) or "Various genres"
    old_overview = item.get("Overview") or "(none)"

    if item_type == "MusicAlbum":
        artist = ", ".join(item.get("Artists", [])) or "Various Artists"
        return (
            f'Write a vibrant, Spotify-style album blurb (18-25 words) for "{title}" '
            f"({year}) by {artist}. Summarize sound and theme, add one concrete hook "
            f"(hit track or chart feat). Use max one vivid adjective per phrase. "
            f"Genres: {genres}. Current: {old_overview}"
        )

    if item_type == "MusicArtist":
        return (
            f"Write a concise artist bio (20-30 words) for {title}. Include origin, "
            f"style, and one standout milestone. Genres: {genres}. Current: {old_overview}"
        )

    return (
        f"Rewrite this {item_type.lower()} overview (25-40 words) in polished streaming "
        f"style. Title: {title}. Year: {year}. Current: {old_overview}"
    )


def beautify(client: Any, item: dict[str, Any], cfg: Config) -> tuple[str, TokenUsage]:
    if cfg.ai_provider == ANTHROPIC_PROVIDER:
        return beautify_with_anthropic(client, item, cfg)
    if cfg.ai_provider in RESPONSES_API_PROVIDERS:
        return beautify_with_responses(client, item, cfg)
    return beautify_with_chat_completions(client, item, cfg)


def beautify_with_responses(
    client: OpenAI,
    item: dict[str, Any],
    cfg: Config,
) -> tuple[str, TokenUsage]:
    request: dict[str, Any] = {
        "model": cfg.ai_model,
        "input": [
            {
                "role": "system",
                "content": "You craft concise, engaging overviews for media items.",
            },
            {"role": "user", "content": prompt_for(item)},
        ],
        "max_output_tokens": cfg.ai_max_output_tokens,
    }

    if cfg.ai_provider == OPENAI_PROVIDER:
        request["store"] = False
    if cfg.ai_provider == OPENAI_PROVIDER and cfg.ai_reasoning_effort:
        request["reasoning"] = {"effort": cfg.ai_reasoning_effort}
    if cfg.ai_temperature is not None:
        request["temperature"] = cfg.ai_temperature

    response = client.responses.create(**request)
    text = response.output_text.strip()
    usage = response_token_usage(response)
    if not text:
        raise RuntimeError(
            f"{cfg.ai_provider} returned an empty overview for item {item.get('Id')}"
        )
    return text, usage


def beautify_with_anthropic(
    client: Any,
    item: dict[str, Any],
    cfg: Config,
) -> tuple[str, TokenUsage]:
    request: dict[str, Any] = {
        "model": cfg.ai_model,
        "system": "You craft concise, engaging overviews for media items.",
        "messages": [{"role": "user", "content": prompt_for(item)}],
        "max_tokens": cfg.ai_max_output_tokens,
    }
    if cfg.ai_temperature is not None:
        request["temperature"] = cfg.ai_temperature

    response = client.messages.create(**request)
    text = anthropic_text(response)
    usage = anthropic_token_usage(response)
    if not text:
        raise RuntimeError(f"Anthropic returned an empty overview for item {item.get('Id')}")
    return text, usage


def beautify_with_chat_completions(
    client: OpenAI,
    item: dict[str, Any],
    cfg: Config,
) -> tuple[str, TokenUsage]:
    request: dict[str, Any] = {
        "model": cfg.ai_model,
        "messages": [
            {
                "role": "system",
                "content": "You craft concise, engaging overviews for media items.",
            },
            {"role": "user", "content": prompt_for(item)},
        ],
        "max_tokens": cfg.ai_max_output_tokens,
    }
    if cfg.ai_temperature is not None:
        request["temperature"] = cfg.ai_temperature

    response = client.chat.completions.create(**request)
    text = (response.choices[0].message.content or "").strip()
    usage = chat_token_usage(response)
    if not text:
        raise RuntimeError(
            f"{cfg.ai_provider} returned an empty overview for item {item.get('Id')}"
        )
    return text, usage


def anthropic_text(response: Any) -> str:
    parts: list[str] = []
    for block in getattr(response, "content", []):
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text", "")))
    return "\n".join(part.strip() for part in parts if part.strip()).strip()


def response_token_usage(response: Response) -> TokenUsage:
    usage = response.usage
    if usage is None:
        return TokenUsage()

    return TokenUsage(
        input_tokens=usage.input_tokens or 0,
        output_tokens=usage.output_tokens or 0,
    )


def anthropic_token_usage(response: Any) -> TokenUsage:
    usage = getattr(response, "usage", None)
    if usage is None:
        return TokenUsage()

    return TokenUsage(
        input_tokens=getattr(usage, "input_tokens", 0) or 0,
        output_tokens=getattr(usage, "output_tokens", 0) or 0,
    )


def chat_token_usage(response: ChatCompletion) -> TokenUsage:
    usage = response.usage
    if usage is None:
        return TokenUsage()

    return TokenUsage(
        input_tokens=usage.prompt_tokens or 0,
        output_tokens=usage.completion_tokens or 0,
    )


def estimate_cost(cfg: Config, usage: TokenUsage) -> float | None:
    pricing = known_pricing_for(cfg.ai_provider, cfg.ai_model)
    input_rate = cfg.ai_input_cost_per_million
    output_rate = cfg.ai_output_cost_per_million

    if input_rate is None and pricing is not None:
        input_rate = pricing[0]
    if output_rate is None and pricing is not None:
        output_rate = pricing[1]
    if input_rate is None or output_rate is None:
        return None

    return (
        usage.input_tokens * input_rate / 1_000_000
        + usage.output_tokens * output_rate / 1_000_000
    )


def known_pricing_for(provider: str, model: str) -> tuple[float, float] | None:
    if provider != OPENAI_PROVIDER:
        return None

    if model in KNOWN_MODEL_PRICING:
        return KNOWN_MODEL_PRICING[model]

    # Snapshot model ids usually start with the base model name.
    for base_model, pricing in sorted(
        KNOWN_MODEL_PRICING.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        if model.startswith(f"{base_model}-"):
            return pricing
    return None


def setup_logging() -> Path:
    LOG_DIR.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_path = LOG_DIR / f"MetaMender_{stamp}.txt"
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format="%(asctime)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    return log_path


def find_targets(session: Session, cfg: Config) -> list[dict[str, Any]]:
    query: dict[str, Any] = {
        "IncludeItemTypes": ",".join(cfg.item_types),
        "Recursive": "true",
        "Fields": EXTRA_FIELDS,
    }
    if cfg.library_id:
        query["ParentId"] = cfg.library_id

    result = jget(
        session,
        f"{cfg.jellyfin_url}/Users/{cfg.user_id}/Items",
        cfg.jellyfin_api_key,
        **query,
    )
    items = [item for item in result["Items"] if item["Type"] != "Audio"]
    return [item for item in items if is_bad(item.get("Overview"))]


def main() -> None:
    cfg = load_cfg()
    log_path = setup_logging()

    logging.info(
        "MetaMender run - model %s - reasoning %s - types %s",
        cfg.ai_model,
        cfg.ai_reasoning_effort or "default",
        ", ".join(cfg.item_types),
    )

    with requests.Session() as session:
        try:
            targets = find_targets(session, cfg)
        except RequestException as exc:
            raise SystemExit(f"Could not read Jellyfin items: {exc}") from exc

        if not targets:
            print("Nothing to fix - library already has usable overviews.")
            return

        ai_client = build_ai_client(cfg)
        usage = TokenUsage()
        updated = skipped = 0
        for item in tqdm(targets, desc="Beautifying", unit="item"):
            try:
                new_text, item_usage = beautify(ai_client, item, cfg)
                usage.input_tokens += item_usage.input_tokens
                usage.output_tokens += item_usage.output_tokens

                if safe_update_overview(
                    session,
                    cfg.jellyfin_url,
                    cfg.jellyfin_api_key,
                    cfg.user_id,
                    item["Id"],
                    new_text,
                ):
                    updated += 1
                    logging.info(
                        "\n%s | %s | ID %s\nOLD: %s\nNEW: %s\n",
                        item["Type"],
                        item["Name"],
                        item["Id"],
                        textwrap.shorten(item.get("Overview") or "(none)", 180),
                        new_text,
                    )
                else:
                    skipped += 1
            except (AnthropicError, OpenAIError, RequestException, RuntimeError) as exc:
                skipped += 1
                logging.exception("Skipped %s because of an error: %s", item.get("Id"), exc)

    cost = estimate_cost(cfg, usage)
    if cost is None:
        cost_text = "unknown; set per-million rates in config for this model"
    else:
        cost_text = f"${cost:.4f}"

    logging.info(
        "Done. Updated %d, skipped %d, input tokens %d, output tokens %d, cost %s",
        updated,
        skipped,
        usage.input_tokens,
        usage.output_tokens,
        cost_text,
    )

    print(f"\nFinished. {updated} items updated, {skipped} skipped.")
    print(
        f"Token usage: {usage.total_tokens} "
        f"({usage.input_tokens} input, {usage.output_tokens} output) | Approx cost: {cost_text}"
    )
    print(f"Detailed log saved to: {log_path}")


if __name__ == "__main__":
    main()
