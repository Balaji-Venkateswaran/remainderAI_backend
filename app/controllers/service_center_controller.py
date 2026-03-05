import json
import os
import re
from typing import Any

from dotenv import load_dotenv
from fastapi.responses import JSONResponse
import google.generativeai as genai
import requests

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

GEMINI_MODEL = "gemini-2.5-flash"


class ServiceCenterController:

    @staticmethod
    def _parse_json(raw_text: str) -> dict[str, Any]:
        cleaned = re.sub(r"```json|```", "", raw_text).strip()
        return json.loads(cleaned)

    @staticmethod
    def _query_overpass(
        tag_key: str,
        tag_value: str,
        user_lat: float,
        user_lon: float,
        radius_m: int
    ) -> list[dict[str, Any]]:
        overpass_url = "https://overpass-api.de/api/interpreter"
        query = f"""
        [out:json];
        (
          node["{tag_key}"="{tag_value}"](around:{radius_m},{user_lat},{user_lon});
          way["{tag_key}"="{tag_value}"](around:{radius_m},{user_lat},{user_lon});
        );
        out center;
        """

        res = requests.get(
            overpass_url,
            params={"data": query},
            timeout=15
        )
        if res.status_code != 200:
            return []
        return res.json().get("elements", [])

    @staticmethod
    async def find_service_centers(appliance_type: str, brand: str):
        try:
            user_lat = 11.0168
            user_lon = 76.9558

            appliance = appliance_type.lower()
            brand_lower = brand.lower()

            OSM_SHOP_MAP = {
                "washing machine": ["appliance", "electronics", "repair"],
                "refrigerator": ["appliance", "electronics", "repair"],
                "air conditioner": ["appliance", "electronics", "repair"],
                "television": ["electronics", "repair"],
                "microwave": ["electronics", "repair"],
                "dishwasher": ["appliance", "repair"],
                "water purifier": ["electronics", "repair"],
                "motorcycle": ["motorcycle", "repair", "car_repair"],
                "bike": ["motorcycle", "repair"]
            }

            shop_types = OSM_SHOP_MAP.get(
                appliance, ["repair", "electronics"]
            )

            overpass_url = "https://overpass-api.de/api/interpreter"
            centers = []

            for shop_type in shop_types:
                query = f"""
                [out:json];
                (
                  node["shop"="{shop_type}"](around:6000,{user_lat},{user_lon});
                  way["shop"="{shop_type}"](around:6000,{user_lat},{user_lon});
                );
                out center;
                """

                res = requests.get(
                    overpass_url,
                    params={"data": query},
                    timeout=15
                )

                if res.status_code != 200:
                    continue

                data = res.json()

                for el in data.get("elements", []):
                    tags = el.get("tags", {})
                    text_blob = " ".join(tags.values()).lower()

                    score = 0

                    if brand_lower and brand_lower in text_blob:
                        score += 3

                    if appliance in text_blob:
                        score += 2

                    if "repair" in text_blob or "service" in text_blob:
                        score += 1

                    if tags.get("shop") in ["electronics", "repair", "appliance"]:
                        score += 0.5

                    if score < 1:
                        continue

                    lat = el.get("lat") or el.get("center", {}).get("lat")
                    lon = el.get("lon") or el.get("center", {}).get("lon")

                    if not lat or not lon:
                        continue

                    centers.append({
                        "name": tags.get("name", "Service Center"),
                        "latitude": lat,
                        "longitude": lon,
                        "address": tags,
                        "mapUrl": (
                            f"https://www.openstreetmap.org/"
                            f"?mlat={lat}&mlon={lon}#map=17/{lat}/{lon}"
                        ),
                        "matchScore": score
                    })

            centers.sort(
                key=lambda x: x["matchScore"],
                reverse=True
            )

            return JSONResponse({
                "serviceCenters": centers[:10]
            })

        except Exception as e:
            return JSONResponse(
                {
                    "error": "Service center lookup failed",
                    "details": str(e)
                },
                status_code=500
            )

    @staticmethod
    async def find_local_services_llm(
        query: str,
        user_lat: float | None = None,
        user_lon: float | None = None,
        limit_per_category: int = 6,
        radius_m: int = 6000
    ):
        try:
            lat = user_lat if user_lat is not None else 11.0168
            lon = user_lon if user_lon is not None else 76.9558

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

            model = genai.GenerativeModel(GEMINI_MODEL)
            response = model.generate_content(prompt)
            parsed = ServiceCenterController._parse_json(response.text)
            categories = parsed.get("categories", [])

            if not categories:
                categories = [
                    {
                        "label": "groceries",
                        "osmTags": [
                            {"key": "shop", "value": "supermarket"},
                            {"key": "shop", "value": "convenience"},
                            {"key": "shop", "value": "greengrocer"}
                        ]
                    },
                    {
                        "label": "hardware",
                        "osmTags": [
                            {"key": "shop", "value": "hardware"},
                            {"key": "shop", "value": "doityourself"}
                        ]
                    },
                    {
                        "label": "pharmacy",
                        "osmTags": [
                            {"key": "amenity", "value": "pharmacy"}
                        ]
                    }
                ]

            results = []
            total_count = 0

            for category in categories:
                label = category.get("label", "service")
                tags = category.get("osmTags", [])
                seen = set()
                places = []

                for tag in tags:
                    key = tag.get("key")
                    value = tag.get("value")
                    if not key or not value:
                        continue

                    elements = ServiceCenterController._query_overpass(
                        key,
                        value,
                        lat,
                        lon,
                        radius_m
                    )

                    for el in elements:
                        osm_id = f"{el.get('type','')}_{el.get('id','')}"
                        if osm_id in seen:
                            continue
                        seen.add(osm_id)

                        tags_blob = el.get("tags", {})
                        lat = el.get("lat") or el.get("center", {}).get("lat")
                        lon = el.get("lon") or el.get("center", {}).get("lon")
                        if not lat or not lon:
                            continue

                        places.append({
                            "name": tags_blob.get("name", label.title()),
                            "latitude": lat,
                            "longitude": lon,
                            "address": tags_blob,
                            "mapUrl": (
                                f"https://www.openstreetmap.org/"
                                f"?mlat={lat}&mlon={lon}#map=17/{lat}/{lon}"
                            )
                        })

                    if len(places) >= limit_per_category:
                        break

                places = places[:limit_per_category]
                total_count += len(places)
                results.append({
                    "label": label,
                    "count": len(places),
                    "places": places
                })

            return JSONResponse({
                "query": query,
                "latitude": lat,
                "longitude": lon,
                "radiusMeters": radius_m,
                "categories": results,
                "total": total_count
            })

        except Exception as e:
            return JSONResponse(
                {
                    "error": "Local services lookup failed",
                    "details": str(e)
                },
                status_code=500
            )
