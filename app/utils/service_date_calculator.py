from datetime import date

from dateutil.relativedelta import relativedelta

from app.controllers.gemini_service_interval_controller import GeminiServiceIntervalController


def calculate_next_service_date_llm(
    appliance_type: str,
    base_date: date,
    brand: str | None = None,
    model: str | None = None,
) -> dict:
    interval_data = GeminiServiceIntervalController.get_service_interval_months(
        appliance_type=appliance_type,
        brand=brand,
        model=model,
    )

    interval_months = int(interval_data.get("intervalMonths", 6))
    interval_months = min(24, max(1, interval_months))
    reason = str(interval_data.get("reason", "Industry-standard interval"))

    next_date = base_date + relativedelta(months=interval_months)

    return {
        "intervalMonths": interval_months,
        "reason": reason,
        "nextServiceDate": next_date,
    }
