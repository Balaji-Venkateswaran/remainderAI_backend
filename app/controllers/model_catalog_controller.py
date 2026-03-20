import json
import os
import re
from typing import Any

from dotenv import load_dotenv
import requests

load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


class ModelCatalogController:
    @staticmethod
    def _extract_json_text(raw_text: str) -> str:
        cleaned = re.sub(r"```json|```", "", raw_text or "", flags=re.IGNORECASE).strip()
        if not cleaned:
            raise ValueError("Empty response")

        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or start >= end:
            raise ValueError("No JSON object found")

        return cleaned[start : end + 1]

    @staticmethod
    def _parse_json(raw_text: str) -> dict[str, Any]:
        payload = json.loads(ModelCatalogController._extract_json_text(raw_text))
        if not isinstance(payload, dict):
            raise ValueError("Model response must be a JSON object")
        return payload

    @staticmethod
    def _validate_models(parsed: dict[str, Any], provider: str) -> dict[str, Any]:
        models = parsed.get("models")
        if not isinstance(models, list) or not models:
            raise ValueError(f"Empty model list from {provider}")

        cleaned: list[dict[str, str]] = []
        for item in models:
            if not isinstance(item, dict):
                continue
            model_name = str(item.get("modelName", "")).strip()
            if not model_name:
                continue
            cleaned.append(
                {
                    "modelName": model_name,
                    "capacity": str(item.get("capacity", "")).strip(),
                    "type": str(item.get("type", "")).strip(),
                }
            )

        if not cleaned:
            raise ValueError(f"No valid models from {provider}")

        return {"models": cleaned}

    @staticmethod
    def _model_prompt(appliance_type: str, brand: str, region_hint: str) -> str:
        return f"""
You are an appliance catalog assistant.

List real, commonly sold models for:
Appliance Type: {appliance_type}
Brand: {brand}
Market preference: {region_hint}

Rules:
- Do not invent models
- Return 5 to 10 models when available
- Return JSON only

Format:
{{
  "models": [
    {{
      "modelName": "",
      "capacity": "",
      "type": ""
    }}
  ]
}}
"""

    @staticmethod
    def _get_models_llama3(appliance_type: str, brand: str) -> dict[str, Any]:
        payload = {
            "model": OLLAMA_MODEL,
            "prompt": ModelCatalogController._model_prompt(appliance_type, brand, "India"),
            "stream": False,
        }

        response = requests.post(OLLAMA_URL, json=payload, timeout=15)
        response.raise_for_status()

        raw = str(response.json().get("response", ""))
        parsed = ModelCatalogController._parse_json(raw)
        return ModelCatalogController._validate_models(parsed, provider="llama3")

    @staticmethod
    def _get_models_gemini(appliance_type: str, brand: str) -> dict[str, Any]:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise ValueError("Missing GEMINI_API_KEY")

        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(
            ModelCatalogController._model_prompt(appliance_type, brand, "India")
        )

        raw_text = getattr(response, "text", "") or ""
        parsed = ModelCatalogController._parse_json(raw_text)
        return ModelCatalogController._validate_models(parsed, provider="gemini")

    @staticmethod
    def get_models(appliance_type: str, brand: str):
        try:
            return ModelCatalogController._get_models_llama3(appliance_type, brand)
        except Exception:
            pass

        try:
            return ModelCatalogController._get_models_gemini(appliance_type, brand)
        except Exception as exc:
            return {"error": "Unable to fetch models from LLMs", "details": str(exc)}
