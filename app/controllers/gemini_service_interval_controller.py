import os
import json
import re
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


class GeminiServiceIntervalController:

    @staticmethod
    def get_service_interval_months(
        appliance_type: str,
        brand: str | None = None,
        model: str | None = None
    ) -> dict:
        """
        Returns:
        {
          "intervalMonths": int,
          "reason": str
        }
        """

        prompt = f"""
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

        model_ai = genai.GenerativeModel("gemini-2.5-flash")
        response = model_ai.generate_content(prompt)

        raw = response.text.strip()
        cleaned = re.sub(r"```json|```", "", raw).strip()

        data = json.loads(cleaned)

        return {
            "intervalMonths": int(data["intervalMonths"]),
            "reason": data["reason"]
        }
