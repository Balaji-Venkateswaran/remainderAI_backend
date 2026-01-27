from datetime import date
from dateutil.relativedelta import relativedelta
from app.controllers.gemini_service_interval_controller import (
    GeminiServiceIntervalController
)


def calculate_next_service_date_llm(
    appliance_type: str,
    base_date: date,
    brand: str | None = None,
    model: str | None = None
) -> dict:


    interval_data = GeminiServiceIntervalController.get_service_interval_months(
        appliance_type=appliance_type,
        brand=brand,
        model=model
    )

    interval_months = interval_data["intervalMonths"]
    reason = interval_data["reason"]

    next_date = base_date + relativedelta(months=interval_months)

    return {
        "intervalMonths": interval_months,
        "reason": reason,
        "nextServiceDate": next_date
    }
