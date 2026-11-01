"""The checkout service charge. Stored in basis points (2% = 200) so all money stays in whole kobo."""
from apps.core.models import SiteSetting

KEY = "checkout-fees"
DEFAULT_BP = 200   # 2%
MAX_BP = 2000      # 20%: a guard against a typo like 200 instead of 2


def service_bp() -> int:
    stored = SiteSetting.objects.filter(key=KEY).values_list("value", flat=True).first() or {}
    try:
        bp = int(stored.get("service_bp", DEFAULT_BP))
    except (TypeError, ValueError):
        bp = DEFAULT_BP
    return min(max(bp, 0), MAX_BP)


def service_charge(goods_total: int, bp: int | None = None) -> int:
    """Charge on what the customer pays for the goods (after any promo discount), never on delivery.
    Rounded to the nearest kobo: N10,000 at 2% is N200."""
    bp = service_bp() if bp is None else bp
    return (max(goods_total, 0) * bp + 5_000) // 10_000


def percent_label(bp: int) -> str:
    return f"{bp / 100:g}%"
