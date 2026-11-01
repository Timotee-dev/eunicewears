"""The checkout service charge. Stored in basis points (2% = 200) so all money stays in whole kobo."""
from apps.core.models import SiteSetting

KEY = "checkout-fees"
DEFAULT_BP = 200   # 2%
MAX_BP = 2000      # 20%: a guard against a typo like 200 instead of 2


def service_bp() -> int:
    stored = _settings()
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


# --- Paystack's commission, passed on to the customer -------------------------------------------
# Paystack (Nigeria, local): 1.5% + N100, the N100 waived under N2,500, capped at N2,000 per payment.
PAYSTACK_BP = 150
PAYSTACK_FLAT = 10_000        # N100 in kobo
PAYSTACK_FLAT_FROM = 250_000  # N2,500
PAYSTACK_CAP = 200_000        # N2,000


def _settings() -> dict:
    return SiteSetting.objects.filter(key=KEY).values_list("value", flat=True).first() or {}


def customer_pays_paystack() -> bool:
    return bool(_settings().get("pass_paystack", True))


def paystack_fee(amount: int) -> int:
    """What Paystack keeps from a payment of `amount` kobo (rounded up, so we never come out short)."""
    if amount <= 0:
        return 0
    fee = (amount * PAYSTACK_BP + 9_999) // 10_000 + (PAYSTACK_FLAT if amount >= PAYSTACK_FLAT_FROM else 0)
    return min(fee, PAYSTACK_CAP)


def processing_fee(amount: int, enabled: bool | None = None) -> int:
    """The extra the customer pays so that, after Paystack takes its cut, the store receives `amount` in full.
    Rounded up to a whole naira so the price reads cleanly."""
    enabled = customer_pays_paystack() if enabled is None else enabled
    if not enabled or amount <= 0:
        return 0
    candidates = [amount + PAYSTACK_CAP]
    for flat in (0, PAYSTACK_FLAT):
        candidates.append(-(-(amount + flat) * 10_000 // (10_000 - PAYSTACK_BP)))
    best = None
    for gross in candidates:
        gross = -(-gross // 100) * 100  # whole naira
        while gross - paystack_fee(gross) < amount:
            gross += 100
        best = gross if best is None else min(best, gross)
    return best - amount
