import json
import os
import re
from typing import Any

from dotenv import load_dotenv

load_dotenv()

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


class GeminiServiceIntervalController:
    @staticmethod
    def _prompt(appliance_type: str, brand: str | None, model: str | None) -> str:
        return f"""
You are a home appliance service expert.

Given the appliance details, suggest the STANDARD service interval in MONTHS.

Return ONLY valid JSON.
No markdown. No explanation text outside JSON.

JSON format:
{{
  "intervalMonths": number,
  "reason": ""
}}

Rules:
- intervalMonths must be between 1 and 24
- Use industry best practices
- Be conservative (avoid too frequent service)
- Appliance Type: {appliance_type}
- Brand: {brand or "Unknown"}
- Model: {model or "Unknown"}
"""

    @staticmethod
    def _extract_json(raw_text: str) -> dict[str, Any]:
        cleaned = re.sub(r"```json|```", "", raw_text or "", flags=re.IGNORECASE).strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or start >= end:
            raise ValueError("Model response did not contain valid JSON")

        payload = json.loads(cleaned[start : end + 1])
        if not isinstance(payload, dict):
            raise ValueError("Model response must be a JSON object")
        return payload

    @staticmethod
    def get_service_interval_months(
        appliance_type: str,
        brand: str | None = None,
        model: str | None = None,
    ) -> dict:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            return {
                "intervalMonths": 6,
                "reason": "Defaulted because Gemini API key is not configured.",
            }

        try:
            import google.generativeai as genai

            genai.configure(api_key=api_key)
            model_ai = genai.GenerativeModel(GEMINI_MODEL)
            response = model_ai.generate_content(
                GeminiServiceIntervalController._prompt(appliance_type, brand, model)
            )
            raw_text = (getattr(response, "text", "") or "").strip()
            data = GeminiServiceIntervalController._extract_json(raw_text)

            interval = int(data.get("intervalMonths", 6))
            interval = min(24, max(1, interval))
            reason = str(data.get("reason", "Industry-standard interval"))

            return {"intervalMonths": interval, "reason": reason}

        except Exception:
            return {
                "intervalMonths": 6,
                "reason": "Defaulted due to model response/parsing failure.",
            }
