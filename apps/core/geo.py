"""Nigeria's 36 states and the Federal Capital Territory, as customers choose them at checkout."""
NIGERIAN_STATES = [
    "Abia", "Adamawa", "Akwa Ibom", "Anambra", "Bauchi", "Bayelsa", "Benue", "Borno", "Cross River", "Delta",
    "Ebonyi", "Edo", "Ekiti", "Enugu", "FCT (Abuja)", "Gombe", "Imo", "Jigawa", "Kaduna", "Kano", "Katsina",
    "Kebbi", "Kogi", "Kwara", "Lagos", "Nasarawa", "Niger", "Ogun", "Ondo", "Osun", "Oyo", "Plateau", "Rivers",
    "Sokoto", "Taraba", "Yobe", "Zamfara",
]
_ALIASES = {"abuja": "FCT (Abuja)", "fct": "FCT (Abuja)", "federal capital territory": "FCT (Abuja)"}
_BY_KEY = {name.lower(): name for name in NIGERIAN_STATES}


def canonical_state(value: str) -> str | None:
    """'lagos state' -> 'Lagos', 'abuja' -> 'FCT (Abuja)'. None if it is not a Nigerian state."""
    key = " ".join(value.strip().lower().split())
    if key.endswith(" state"):
        key = key[:-6]
    return _BY_KEY.get(key) or _ALIASES.get(key)
