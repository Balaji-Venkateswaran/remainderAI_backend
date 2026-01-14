import os

import google.generativeai as genai


genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


def generate_event_notes(title: str, description: str | None) -> str:
    prompt = f"""
You are summarizing a calendar event for a reminder app.
Write a concise, helpful note based on the event title and description.
Return plain text only.

Title: {title}
Description: {description or "N/A"}
"""

    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception:
        return description or ""
