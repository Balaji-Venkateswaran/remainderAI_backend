import json
import os
import re
from typing import Any

from dotenv import load_dotenv
from fastapi.responses import JSONResponse
import requests

load_dotenv()

GEMINI_MODEL = "gemini-2.5-flash"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
DEFAULT_LAT = 11.0168
DEFAULT_LON = 76.9558


class ServiceCenterController:
    @staticmethod
    def _parse_json(raw_text: str) -> dict[str, Any]:
        cleaned = re.sub(r"```json|```", "", raw_text).strip()
        return json.loads(cleaned)

    @staticmethod
    def _sanitize_categories(raw_categories: Any) -> list[dict[str, Any]]:
        if not isinstance(raw_categories, list):
            return []

        cleaned: list[dict[str, Any]] = []
        seen_labels: set[str] = set()

        for item in raw_categories:
            if not isinstance(item, dict):
                continue

            label = str(item.get("label", "")).strip().lower()
            if not label or label in seen_labels:
                continue

            tags = item.get("osmTags", [])
            if not isinstance(tags, list):
                continue

            normalized_tags: list[dict[str, str]] = []
            seen_pairs: set[tuple[str, str]] = set()

            for tag in tags:
                if not isinstance(tag, dict):
                    continue
                key = str(tag.get("key", "")).strip().lower()
                value = str(tag.get("value", "")).strip().lower()
                if not key or not value:
                    continue
                pair = (key, value)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                normalized_tags.append({"key": key, "value": value})

            if not normalized_tags:
                continue

            seen_labels.add(label)
            cleaned.append({"label": label, "osmTags": normalized_tags})

        return cleaned

    @staticmethod
    def _query_overpass(
        tag_key: str,
        tag_value: str,
        user_lat: float,
        user_lon: float,
        radius_m: int,
    ) -> list[dict[str, Any]]:
        query = f"""
[out:json];
(
  node["{tag_key}"="{tag_value}"](around:{radius_m},{user_lat},{user_lon});
  way["{tag_key}"="{tag_value}"](around:{radius_m},{user_lat},{user_lon});
);
out center;
"""

        try:
            res = requests.get(OVERPASS_URL, params={"data": query}, timeout=15)
            if res.status_code != 200:
                return []
            return res.json().get("elements", [])
        except (requests.RequestException, ValueError):
            return []

    @staticmethod
    def _map_url(lat: float, lon: float) -> str:
        return f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=17/{lat}/{lon}"

    @staticmethod
    def _fallback_categories() -> list[dict[str, Any]]:
        return [
            {
                "label": "groceries",
                "osmTags": [
                    {"key": "shop", "value": "supermarket"},
                    {"key": "shop", "value": "convenience"},
                    {"key": "shop", "value": "greengrocer"},
                ],
            },
            {
                "label": "hardware",
                "osmTags": [
                    {"key": "shop", "value": "hardware"},
                    {"key": "shop", "value": "doityourself"},
                ],
            },
            {
                "label": "electronics",
                "osmTags": [
                    {"key": "shop", "value": "electronics"},
                    {"key": "shop", "value": "mobile_phone"},
                    {"key": "shop", "value": "computer"},
                ],
            },
            {
                "label": "pharmacy",
                "osmTags": [{"key": "amenity", "value": "pharmacy"}],
            },
        ]

    @staticmethod
    def _load_categories_from_gemini(query: str) -> list[dict[str, Any]]:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            return []

        prompt = f"""
You are a local services planner.

User request: "{query}"

Return ONLY valid JSON. No markdown.

Format:
{{
  "categories": [
    {{
      "label": "",
      "priority": "primary|related",
      "osmTags": [
        {{"key": "shop", "value": ""}}
      ]
    }}
  ]
}}

Rules:
- Use OpenStreetMap tag keys like shop, amenity, office, tourism, leisure
- Include 1 primary category that best matches the user request
- Include 2 to 5 related categories
- 1 to 4 osmTags per category
- Keep labels short (1 to 3 words)
"""

        try:
            import google.generativeai as genai

            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(GEMINI_MODEL)
            response = model.generate_content(prompt)
            raw_text = getattr(response, "text", "") or ""
            if not raw_text.strip():
                return []
            parsed = ServiceCenterController._parse_json(raw_text)
            return ServiceCenterController._sanitize_categories(parsed.get("categories", []))
        except Exception:
            return []

    @staticmethod
    async def find_service_centers(appliance_type: str, brand: str):
        try:
            user_lat = DEFAULT_LAT
            user_lon = DEFAULT_LON
            appliance = appliance_type.lower()
            brand_lower = brand.lower()

            osm_shop_map = {
                "washing machine": ["appliance", "electronics", "repair"],
                "refrigerator": ["appliance", "electronics", "repair"],
                "air conditioner": ["appliance", "electronics", "repair"],
                "television": ["electronics", "repair"],
                "microwave": ["electronics", "repair"],
                "dishwasher": ["appliance", "repair"],
                "water purifier": ["electronics", "repair"],
                "motorcycle": ["motorcycle", "repair", "car_repair"],
                "bike": ["motorcycle", "repair"],
            }
            shop_types = osm_shop_map.get(appliance, ["repair", "electronics"])

            centers: list[dict[str, Any]] = []

            for shop_type in shop_types:
                elements = ServiceCenterController._query_overpass(
                    tag_key="shop",
                    tag_value=shop_type,
                    user_lat=user_lat,
                    user_lon=user_lon,
                    radius_m=6000,
                )

                for element in elements:
                    tags = element.get("tags", {})
                    text_blob = " ".join(str(value) for value in tags.values()).lower()

                    score = 0.0
                    if brand_lower and brand_lower in text_blob:
                        score += 3.0
                    if appliance and appliance in text_blob:
                        score += 2.0
                    if "repair" in text_blob or "service" in text_blob:
                        score += 1.0
                    if tags.get("shop") in {"electronics", "repair", "appliance"}:
                        score += 0.5
                    if score < 1:
                        continue

                    lat = element.get("lat") or element.get("center", {}).get("lat")
                    lon = element.get("lon") or element.get("center", {}).get("lon")
                    if lat is None or lon is None:
                        continue

                    centers.append(
                        {
                            "name": tags.get("name", "Service Center"),
                            "latitude": lat,
                            "longitude": lon,
                            "address": tags,
                            "mapUrl": ServiceCenterController._map_url(lat, lon),
                            "matchScore": score,
                        }
                    )

            centers.sort(key=lambda item: item["matchScore"], reverse=True)
            return JSONResponse({"serviceCenters": centers[:10]})

        except Exception as exc:
            return JSONResponse(
                {"error": "Service center lookup failed", "details": str(exc)},
                status_code=500,
            )

    @staticmethod
    async def find_local_services_llm(
        query: str,
        user_lat: float | None = None,
        user_lon: float | None = None,
        limit_per_category: int = 6,
        radius_m: int = 6000,
    ):
        try:
            query_lat = user_lat if user_lat is not None else DEFAULT_LAT
            query_lon = user_lon if user_lon is not None else DEFAULT_LON

            categories = ServiceCenterController._load_categories_from_gemini(query)
            if not categories:
                categories = ServiceCenterController._fallback_categories()

            results: list[dict[str, Any]] = []
            total_count = 0

            for category in categories:
                label = str(category.get("label", "service"))
                tags = category.get("osmTags", [])
                if not isinstance(tags, list):
                    tags = []

                seen: set[str] = set()
                places: list[dict[str, Any]] = []

                for tag in tags:
                    key = tag.get("key")
                    value = tag.get("value")
                    if not key or not value:
                        continue

                    elements = ServiceCenterController._query_overpass(
                        tag_key=key,
                        tag_value=value,
                        user_lat=query_lat,
                        user_lon=query_lon,
                        radius_m=radius_m,
                    )

                    for element in elements:
                        osm_id = f"{element.get('type', '')}_{element.get('id', '')}"
                        if osm_id in seen:
                            continue
                        seen.add(osm_id)

                        tags_blob = element.get("tags", {})
                        place_lat = element.get("lat") or element.get("center", {}).get("lat")
                        place_lon = element.get("lon") or element.get("center", {}).get("lon")
                        if place_lat is None or place_lon is None:
                            continue

                        places.append(
                            {
                                "name": tags_blob.get("name", label.title()),
                                "latitude": place_lat,
                                "longitude": place_lon,
                                "address": tags_blob,
                                "mapUrl": ServiceCenterController._map_url(place_lat, place_lon),
                            }
                        )

                    if len(places) >= limit_per_category:
                        break

                places = places[:limit_per_category]
                total_count += len(places)
                results.append({"label": label, "count": len(places), "places": places})

            return JSONResponse(
                {
                    "query": query,
                    "latitude": query_lat,
                    "longitude": query_lon,
                    "radiusMeters": radius_m,
                    "categories": results,
                    "total": total_count,
                }
            )

        except Exception as exc:
            return JSONResponse(
                {"error": "Local services lookup failed", "details": str(exc)},
                status_code=500,
            )
