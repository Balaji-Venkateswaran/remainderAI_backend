import os

from dotenv import load_dotenv

load_dotenv()

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def generate_event_notes(title: str, description: str | None) -> str:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return description or ""

    prompt = f"""
You are summarizing a calendar event for a reminder app.
Write a concise, helpful note based on the event title and description.
Return plain text only.

Title: {title}
Description: {description or "N/A"}
"""

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(prompt)
        text = (getattr(response, "text", "") or "").strip()
        return text or (description or "")
    except Exception:
        return description or ""
