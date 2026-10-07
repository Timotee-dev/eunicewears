from django import template

register = template.Library()


@register.filter
def naira(kobo) -> str:
    """Integer kobo -> '₦12,000' (shows kobo only when there are any)."""
    try:
        kobo = int(kobo)
    except (TypeError, ValueError):
        return ""
    whole, part = divmod(kobo, 100)
    return f"\u20a6{whole:,}" + (f".{part:02d}" if part else "")
