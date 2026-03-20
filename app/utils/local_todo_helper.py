import json
import logging
import os
import re
from typing import Any

from dotenv import load_dotenv
import requests

load_dotenv()

logger = logging.getLogger(__name__)

_LOCAL_CATEGORY_CACHE: dict[str, str] = {}
_LOCAL_CATEGORY_MODEL = os.getenv("LOCAL_CATEGORY_MODEL", "gemini-2.5-flash")
_OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3:latest")
_MAX_NOTES_LENGTH = 2000
_LOCAL_CATEGORY_MODE = os.getenv("LOCAL_CATEGORY_MODE", "llm_first").strip().lower()

_ALLOWED_CATEGORIES = ("Groceries", "Hardware", "Electronics", "Shopping")


def build_group_line(title: str, notes: str | None) -> str:
    title_text = (title or "").strip()
    notes_text = (notes or "").strip()
    return f"- {title_text}: {notes_text}" if notes_text else f"- {title_text}"


def append_unique_line(existing_notes: str | None, line: str) -> str:
    current = (existing_notes or "").strip()
    clean_line = line.strip()
    if not current:
        return clean_line

    lines = [value.strip() for value in current.splitlines() if value.strip()]
    if clean_line in lines:
        return current

    return f"{current}\n{clean_line}"


def fallback_local_category_title(text: str) -> str:
    normalized = (text or "").lower()

    if re.search(
        r"\b(tomato|onion|chilly|chili|apple|banana|potato|pumpkin|vegetable|fruit|milk|rice|grocery|groceries|cauliflower|califlower)\b",
        normalized,
    ):
        return "Groceries"

    if re.search(
        r"\b(screw|screwdriver|bolt|nut|hardware|tool|tools|tubelight|tube light|electrical|light|bulb|led|lamp|switch|pipe|pvc|plumbing)\b",
        normalized,
    ):
        return "Hardware"

    if re.search(
        r"\b(pendrive|pen drive|usb|mobile|phone|computer|laptop|electronics)\b",
        normalized,
    ):
        return "Electronics"

    return "Shopping"


def try_parse_json_notes(notes: str | None) -> Any:
    if not notes:
        return None
    try:
        return json.loads(notes)
    except json.JSONDecodeError:
        return None


def extract_note_lines(notes: str | None) -> list[str]:
    if not notes:
        return []

    parsed = try_parse_json_notes(notes)
    if isinstance(parsed, dict):
        return []

    items: list[str] = []
    for line in notes.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        items.append(stripped.replace("- ", "", 1).strip())
    return items


def safe_notes(notes: str | None) -> str:
    text = notes or ""
    if len(text) <= _MAX_NOTES_LENGTH:
        return text
    return f"{text[:_MAX_NOTES_LENGTH - 3]}..."


def _parse_category(raw: str) -> str | None:
    text = (raw or "").strip().lower()
    if not text:
        return None

    if "grocer" in text or text == "groceries":
        return "Groceries"
    if "hard" in text or text == "hardware":
        return "Hardware"
    if "elect" in text or text == "electronics":
        return "Electronics"
    if "shop" in text or text == "shopping":
        return "Shopping"

    return None


def _build_classifier_prompt(text: str) -> str:
    return f"""
You are a strict shopping item classifier.

Item: "{text}"

Allowed categories:
- groceries
- hardware
- electronics
- shopping

Examples:
- "need to buy tomato" -> groceries
- "need to buy screw" -> hardware
- "need to buy pendrive" -> electronics
- "need to buy gift wrap" -> shopping

Return ONLY one lowercase word from the allowed categories.
"""


def _classify_with_gemini(prompt: str) -> str | None:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(_LOCAL_CATEGORY_MODEL)
        response = model.generate_content(prompt)
        raw = (getattr(response, "text", "") or "").strip()
        return _parse_category(raw)
    except Exception as exc:  # pragma: no cover - network/provider behavior
        logger.debug("Gemini classification failed: %s", exc)
        return None


def _classify_with_ollama(prompt: str) -> str | None:
    url = f"{_OLLAMA_BASE_URL.rstrip('/')}/api/generate"
    payload = {"model": _OLLAMA_MODEL, "prompt": prompt, "stream": False}

    try:
        res = requests.post(url, json=payload, timeout=5)
        if res.status_code != 200:
            return None
        data = res.json()
        raw = str(data.get("response", "")).strip()
        return _parse_category(raw)
    except (requests.RequestException, ValueError) as exc:
        logger.debug("Ollama classification failed: %s", exc)
        return None


def _classify_with_llms(prompt: str) -> str | None:
    gemini_category = _classify_with_gemini(prompt)
    if gemini_category:
        return gemini_category

    return _classify_with_ollama(prompt)


def local_category_title(text: str) -> str:
    normalized = (text or "").strip().lower()
    if not normalized:
        return "Shopping"

    cached = _LOCAL_CATEGORY_CACHE.get(normalized)
    if cached in _ALLOWED_CATEGORIES:
        return cached

    prompt = _build_classifier_prompt(text)
    fallback_category = fallback_local_category_title(text)

    if _LOCAL_CATEGORY_MODE == "regex_first":
        if fallback_category != "Shopping":
            _LOCAL_CATEGORY_CACHE[normalized] = fallback_category
            return fallback_category
        llm_category = _classify_with_llms(prompt)
        result = llm_category or "Shopping"
        _LOCAL_CATEGORY_CACHE[normalized] = result
        return result

    if _LOCAL_CATEGORY_MODE in {"llm_first", "llm_only"}:
        llm_category = _classify_with_llms(prompt)
        if llm_category:
            _LOCAL_CATEGORY_CACHE[normalized] = llm_category
            return llm_category

    if _LOCAL_CATEGORY_MODE != "llm_only" and fallback_category != "Shopping":
        _LOCAL_CATEGORY_CACHE[normalized] = fallback_category
        return fallback_category

    _LOCAL_CATEGORY_CACHE[normalized] = "Shopping"
    return "Shopping"
