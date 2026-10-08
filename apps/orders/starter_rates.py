"""Delivery set-up for Eunice Wears.

The rule the owner chose: inside Ondo State the store delivers for a fee paid at checkout. Everywhere else the
order travels by bus (waybill): checkout charges nothing for delivery and the customer pays the driver or park
when the parcel arrives. Pickup is free.

Everything here is safe to run on every deploy: it only adds what is missing, and the switch to the bus rule is
applied exactly once, so anything the owner edits afterwards in Dashboard > Settings is never overwritten."""
from apps.core.geo import NIGERIAN_STATES
from apps.core.models import SiteSetting

from .models import ShippingMethod

HOME_STATE = "Ondo"
HOME_FEE = 150_000  # kobo. PLACEHOLDER: the owner sets the real Ondo fee in Settings.
BUS_NOTE = "Sent by bus. You pay the driver when it arrives."
POLICY_KEY, POLICY_VERSION = "delivery-policy", 2


def _label(state: str) -> str:
    return "Abuja (FCT)" if state.startswith("FCT") else state


def ensure_starter_rates() -> int:
    created = 0
    general = [
        dict(name="Bus delivery within Lagos", zone="lagos", fee=0, pay_on_delivery=True, estimate=BUS_NOTE),
        dict(name="Bus delivery outside Ondo", zone="other_states", fee=0, pay_on_delivery=True, estimate=BUS_NOTE),
        dict(name="Pickup", zone="pickup", fee=0, estimate="Ready within 24 hours"),
    ]
    for rate in general:
        if not ShippingMethod.objects.filter(zone=rate["zone"], state="").exists():
            ShippingMethod.objects.create(**rate)
            created += 1
    covered = set(ShippingMethod.objects.exclude(state="").values_list("state", flat=True))
    for state in NIGERIAN_STATES:
        if state in covered or state == "Lagos":
            continue
        if state == HOME_STATE:
            ShippingMethod.objects.create(name="Delivery within Ondo State", zone="other_states", state=state,
                                          fee=HOME_FEE, estimate="1 to 2 working days")
        else:
            ShippingMethod.objects.create(name=f"Bus delivery to {_label(state)}", zone="other_states", state=state,
                                          fee=0, pay_on_delivery=True, estimate=BUS_NOTE)
        created += 1
    return created


def apply_bus_policy() -> int:
    """One-time: turn every delivery rate outside Ondo into 'pay the driver'. Returns how many rates changed."""
    marker = SiteSetting.objects.filter(key=POLICY_KEY).first()
    if marker and marker.value.get("version", 0) >= POLICY_VERSION:
        return 0
    changed = 0
    for rate in ShippingMethod.objects.exclude(zone="pickup").exclude(state=HOME_STATE):
        if rate.pay_on_delivery and rate.fee == 0:
            continue
        rate.fee, rate.free_over, rate.pay_on_delivery, rate.estimate = 0, None, True, BUS_NOTE
        if rate.state:
            rate.name = f"Bus delivery to {_label(rate.state)}"
        elif rate.zone == "lagos":
            rate.name = "Bus delivery within Lagos"
        elif rate.zone == "other_states":
            rate.name = "Bus delivery outside Ondo"
        rate.save()
        changed += 1
    home = ShippingMethod.objects.filter(state=HOME_STATE).first()
    if home and home.name.startswith("Delivery to"):
        home.name = "Delivery within Ondo State"
        home.save(update_fields=["name", "updated_at"])
    SiteSetting.objects.update_or_create(key=POLICY_KEY, defaults={"value": {"version": POLICY_VERSION}})
    return changed
