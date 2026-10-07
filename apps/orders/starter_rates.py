"""Starter delivery rates: Lagos, a fee for every other state, a general fallback and pickup.
The amounts are PLACEHOLDERS so checkout works from day one. The owner replaces them in Dashboard > Settings.
Safe to run repeatedly: it only adds what is missing and never changes or re-creates a rate the owner has touched."""
from apps.core.geo import NIGERIAN_STATES

from .models import ShippingMethod

REGIONS = [
    (350_000, "2 to 3 working days", ["Ogun", "Oyo", "Osun", "Ondo", "Ekiti"]),
    (450_000, "3 to 4 working days", ["Edo", "Delta", "Bayelsa", "Rivers", "Akwa Ibom", "Cross River",
                                      "Abia", "Anambra", "Ebonyi", "Enugu", "Imo"]),
    (500_000, "3 to 5 working days", ["Kwara", "Kogi", "Benue", "Niger", "Nasarawa", "Plateau", "FCT (Abuja)"]),
    (600_000, "4 to 6 working days", ["Kaduna", "Kano", "Katsina", "Kebbi", "Jigawa", "Sokoto", "Zamfara"]),
    (650_000, "4 to 7 working days", ["Adamawa", "Bauchi", "Borno", "Gombe", "Taraba", "Yobe"]),
]
GENERAL = [
    ("Lagos delivery", "lagos", 250_000, "1 to 2 working days"),
    ("Delivery outside Lagos", "other_states", 500_000, "3 to 5 working days"),
    ("Pickup", "pickup", 0, "Ready within 24 hours"),
]


def ensure_starter_rates() -> int:
    created = 0
    for name, zone, fee, estimate in GENERAL:
        if not ShippingMethod.objects.filter(zone=zone, state="").exists():
            ShippingMethod.objects.create(name=name, zone=zone, fee=fee, estimate=estimate)
            created += 1
    covered = set(ShippingMethod.objects.exclude(state="").values_list("state", flat=True))
    for fee, estimate, states in REGIONS:
        for state in states:
            assert state in NIGERIAN_STATES, state
            if state not in covered:
                label = "Abuja (FCT)" if state.startswith("FCT") else state
                ShippingMethod.objects.create(name=f"Delivery to {label}", zone="other_states", state=state, fee=fee, estimate=estimate)
                created += 1
    return created
