import requests
import json
import re
import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3"

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
GEMINI_MODEL = "gemini-2.5-flash"


class ModelCatalogController:

    @staticmethod
    def _parse_json(raw_text: str):
        cleaned = re.sub(r"```json|```", "", raw_text).strip()
        return json.loads(cleaned)

    @staticmethod
    def _get_models_llama3(appliance_type: str, brand: str):
        prompt = f"""
List real and popular models for:

Appliance Type: {appliance_type}
Brand: {brand}

Rules:
- Do NOT invent models
- Use real product series
- Return 5–10 models
- JSON ONLY

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

        payload = {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False
        }

        response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=15
        )
        response.raise_for_status()

        raw = response.json().get("response", "")
        parsed = ModelCatalogController._parse_json(raw)

        if not parsed.get("models"):
            raise ValueError("Empty model list from llama3")

        return parsed

    @staticmethod
    def _get_models_gemini(appliance_type: str, brand: str):
        prompt = f"""
You are an appliance expert.

List real, commonly sold models for:
Appliance Type: {appliance_type}
Brand: {brand}

Rules:
- Do NOT hallucinate fake models
- Prefer Indian market models if possible
- JSON ONLY

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

        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(prompt)

        parsed = ModelCatalogController._parse_json(response.text)

        if not parsed.get("models"):
            raise ValueError("Empty model list from Gemini")

        return parsed

    @staticmethod
    def get_models(appliance_type: str, brand: str):
        try:
            return ModelCatalogController._get_models_llama3(
                appliance_type, brand
            )
        except Exception:
            pass

        try:
            return ModelCatalogController._get_models_gemini(
                appliance_type, brand
            )
        except Exception as e:
            return {
                "error": "Unable to fetch models from LLMs",
                "details": str(e)
            }
