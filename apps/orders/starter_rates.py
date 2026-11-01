"""Delivery set-up for Eunice Wears.

The rule the owner chose: inside Ondo town (the city of Ondo, in Ondo State) the store delivers for N1,500 paid at
checkout. Everywhere else, the rest of Ondo State included, the order travels by bus (waybill): checkout charges
nothing for delivery and the customer pays the driver or park when the parcel arrives. Pickup is free.

Everything here is safe to run on every deploy: it only adds what is missing, and the switch to the bus rule is
applied exactly once, so anything the owner edits afterwards in Dashboard > Settings is never overwritten."""
from apps.core.geo import NIGERIAN_STATES
from apps.core.models import SiteSetting

from .models import ShippingMethod

HOME_STATE = "Ondo"
HOME_TOWN = "Ondo"
HOME_FEE = 150_000  # kobo: N1,500 inside Ondo town, as the owner set it
BUS_NOTE = "Sent by bus. You pay the driver when it arrives."
POLICY_KEY, POLICY_VERSION = "delivery-policy", 3


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
        if True:  # Ondo town's own N1,500 rate is added by apply_bus_policy (v3)
            ShippingMethod.objects.create(name=f"Bus delivery to {_label(state)}", zone="other_states", state=state,
                                          fee=0, pay_on_delivery=True, estimate=BUS_NOTE)
        created += 1
    return created


def apply_bus_policy() -> int:
    """One-time switches, each applied once and never again (so later edits in Settings are kept).
    v2: every rate outside Ondo State becomes 'pay the driver'.
    v3: only Ondo town keeps a fee (N1,500); the rest of Ondo State also pays the driver."""
    marker = SiteSetting.objects.filter(key=POLICY_KEY).first()
    done = marker.value.get("version", 0) if marker else 0
    if done >= POLICY_VERSION:
        return 0
    changed = 0
    if done < 2:
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
    if done < 3:
        town = ShippingMethod.objects.filter(state=HOME_STATE).exclude(city="").first()
        if town is None:
            ShippingMethod.objects.create(name="Delivery within Ondo town", zone="other_states", state=HOME_STATE, city=HOME_TOWN,
                                          fee=HOME_FEE, estimate="1 to 2 working days")
        else:
            town.fee, town.pay_on_delivery, town.is_active = HOME_FEE, False, True
            town.save()
        changed += 1
        rest = ShippingMethod.objects.filter(state=HOME_STATE, city="").first()
        if rest is None:
            rest = ShippingMethod(zone="other_states", state=HOME_STATE)
        rest.name, rest.fee, rest.free_over, rest.pay_on_delivery, rest.estimate = \
            "Bus delivery within Ondo State (outside Ondo town)", 0, None, True, BUS_NOTE
        rest.save()
        changed += 1
        general = ShippingMethod.objects.filter(zone="other_states", state="").first()
        if general and general.name == "Bus delivery outside Ondo":
            general.name = "Bus delivery"
            general.save(update_fields=["name", "updated_at"])
    SiteSetting.objects.update_or_create(key=POLICY_KEY, defaults={"value": {"version": POLICY_VERSION}})
    return changed
