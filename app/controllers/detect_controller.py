from fastapi import UploadFile, File
from fastapi.responses import JSONResponse
from PIL import Image
import io
import json
import re
import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

class DetectController:

    @staticmethod
    async def detect_appliance(image: UploadFile = File(...)):
        try:
            img_bytes = await image.read()
            pil_img = Image.open(io.BytesIO(img_bytes))

            prompt = """
You are a vision AI.

From the image, identify:
- applianceType (Washing Machine, Refrigerator, Air Conditioner, TV, Microwave, etc.)
- brand (company name if visible)

Return ONLY valid JSON.

{
  "applianceType": "",
  "brand": "",
  "confidence": 0.0
}
"""

            model = genai.GenerativeModel("gemini-2.5-flash")
            response = model.generate_content([prompt, pil_img])

            raw = response.text.strip()
            cleaned = re.sub(r"```json|```", "", raw).strip()
            result = json.loads(cleaned)

            return JSONResponse({
                "applianceType": result.get("applianceType", ""),
                "brand": result.get("brand", ""),
                "model": "",
                "detectedText": "",
                "confidence": result.get("confidence", 0.8)
            })

        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
