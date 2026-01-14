from fastapi.responses import JSONResponse
import requests


class ServiceCenterController:

    @staticmethod
    async def find_service_centers(appliance_type: str, brand: str):
        try:
            # 📍 Hardcoded user location (Coimbatore)
            user_lat = 11.0168
            user_lon = 76.9558

            appliance = appliance_type.lower()
            brand_lower = brand.lower()

            # ✅ Reliable rule-based mapping for OpenStreetMap
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

                    # 🔍 Scoring logic instead of strict filtering
                    score = 0

                    if brand_lower and brand_lower in text_blob:
                        score += 3

                    if appliance in text_blob:
                        score += 2

                    if "repair" in text_blob or "service" in text_blob:
                        score += 1

                    if tags.get("shop") in ["electronics", "repair", "appliance"]:
                        score += 0.5

                    # ❌ Reject weak matches
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

            # 🔽 Sort by relevance
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
