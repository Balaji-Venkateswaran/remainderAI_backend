import base64
import io
import json
import os
import re
from typing import Any

from dotenv import load_dotenv
from fastapi import File, UploadFile
from fastapi.responses import JSONResponse
from PIL import Image, UnidentifiedImageError
import requests

load_dotenv()

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "llava:latest")
OLLAMA_TIMEOUT_SECONDS = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "240"))


class DetectController:
    @staticmethod
    def _prepare_image(image_bytes: bytes) -> tuple[Image.Image, bytes]:
        pil_image = Image.open(io.BytesIO(image_bytes))
        pil_image.load()
        if pil_image.mode not in ("RGB", "L"):
            pil_image = pil_image.convert("RGB")
        elif pil_image.mode == "L":
            pil_image = pil_image.convert("RGB")

        # Keep uploads small enough for local vision inference to respond.
        pil_image.thumbnail((1024, 1024))

        output = io.BytesIO()
        pil_image.save(output, format="JPEG", quality=85, optimize=True)
        return pil_image, output.getvalue()

    @staticmethod
    def _empty_detection(confidence: float = 0.0) -> dict[str, Any]:
        return {
            "applianceType": "",
            "brand": "",
            "model": "",
            "detectedText": "",
            "confidence": confidence,
        }

    @staticmethod
    def _extract_json(raw_text: str) -> dict[str, Any]:
        cleaned = re.sub(r"```json|```", "", raw_text or "", flags=re.IGNORECASE).strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or start >= end:
            raise ValueError("Model response did not contain valid JSON")

        payload = json.loads(cleaned[start : end + 1])
        if not isinstance(payload, dict):
            raise ValueError("Model response JSON must be an object")
        return payload

    @staticmethod
    def _prompt() -> str:
        return """
You are a vision AI.

Analyze the uploaded appliance image and identify:
- applianceType (Washing Machine, Refrigerator, Air Conditioner, TV, Microwave, etc.)
- brand (company name if visible)
- detectedText (short text visible on the product such as logo, badge, label, or model plate)

Rules:
- Return ONLY valid JSON
- No markdown
- If a field is unknown, use an empty string
- confidence must be a number between 0.0 and 1.0
- Look carefully for logos, printed brand names, stickers, control panel labels, and door badges
- If you can read a likely brand name in the image text, put that value in both `brand` and `detectedText`
- Prefer common appliance brands over generic words like inverter, frost free, digital, smart, or direct cool
- Do not guess a brand unless some visible text or logo supports it

{
  "applianceType": "",
  "brand": "",
  "detectedText": "",
  "confidence": 0.0
}
"""

    @staticmethod
    def _generate_with_gemini(pil_image: Image.Image) -> dict[str, Any]:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise ValueError("Missing GEMINI_API_KEY")

        try:
            import google.generativeai as genai
        except ImportError as exc:
            raise RuntimeError("Missing google-generativeai package") from exc

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content([DetectController._prompt(), pil_image])

        raw = (getattr(response, "text", "") or "").strip()
        if not raw:
            raise ValueError("Gemini returned an empty response")
        return DetectController._extract_json(raw)

    @staticmethod
    def _generate_with_ollama(image_bytes: bytes) -> dict[str, Any]:
        payload = {
            "model": OLLAMA_VISION_MODEL,
            "prompt": DetectController._prompt(),
            "images": [base64.b64encode(image_bytes).decode("utf-8")],
            "stream": False,
        }
        response = requests.post(
            f"{OLLAMA_BASE_URL.rstrip('/')}/api/generate",
            json=payload,
            timeout=(10, OLLAMA_TIMEOUT_SECONDS),
        )
        response.raise_for_status()

        raw = str(response.json().get("response", "")).strip()
        if not raw:
            raise ValueError("Ollama returned an empty response")
        return DetectController._extract_json(raw)

    @staticmethod
    async def detect_appliance(image: UploadFile = File(...)):
        try:
            img_bytes = await image.read()
            pil_image, prepared_bytes = DetectController._prepare_image(img_bytes)

            provider_errors: list[str] = []

            try:
                result = DetectController._generate_with_gemini(pil_image)
                provider_used = "gemini"
            except Exception as gemini_exc:
                provider_errors.append(f"gemini: {gemini_exc}")
                result = DetectController._generate_with_ollama(prepared_bytes)
                provider_used = "ollama"

            confidence = result.get("confidence", 0.8)
            try:
                confidence = float(confidence)
            except (TypeError, ValueError):
                confidence = 0.8

            confidence = max(0.0, min(1.0, confidence))

            payload = DetectController._empty_detection(confidence=confidence)
            payload["applianceType"] = str(result.get("applianceType", "")).strip()
            payload["brand"] = str(result.get("brand", "")).strip()
            payload["detectedText"] = str(result.get("detectedText", "")).strip()
            if not payload["brand"] and payload["detectedText"]:
                text_lower = payload["detectedText"].strip().lower()
                known_brands = {
                    "samsung",
                    "lg",
                    "whirlpool",
                    "godrej",
                    "haier",
                    "panasonic",
                    "sony",
                    "bosch",
                    "ifb",
                    "voltas",
                    "daikin",
                    "hitachi",
                }
                if text_lower in known_brands:
                    payload["brand"] = payload["detectedText"].strip()
            payload["provider"] = provider_used

            if provider_errors:
                payload["warning"] = "; ".join(provider_errors)

            return JSONResponse(payload)

        except UnidentifiedImageError:
            return JSONResponse({"error": "Unsupported or invalid image"}, status_code=400)
        except requests.RequestException as exc:
            return JSONResponse(
                {
                    "error": f"Ollama detection failed: {exc}",
                    "detection": DetectController._empty_detection(),
                },
                status_code=503,
            )
        except (RuntimeError, ValueError) as exc:
            return JSONResponse(
                {
                    "error": str(exc),
                    "detection": DetectController._empty_detection(),
                },
                status_code=503,
            )
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)
