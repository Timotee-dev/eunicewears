"""Owner-editable site content. Defaults live here; edits are stored in SiteSetting and merged over them."""
from .models import SiteSetting

T, LONG = 200, 20000
SCHEMA: dict[str, dict] = {
    "home": {"label": "Home page", "fields": [
        ("announcement", "Announcement bar (leave empty to hide)", T, False),
        ("headline", "Headline", 80, False), ("lede", "One short line under the headline", 160, True)]},
    "size-guide": {"label": "Size guide", "fields": [
        ("oversized", "Oversized fit: one size per line, e.g. M, 58, 74", 2000, True),
        ("regular", "Regular fit: one size per line", 2000, True),
        ("columns", "Column names, comma separated", T, False),
        ("note", "Note under the tables", 400, True)]},
    **{f"page-{slug}": {"label": title, "fields": [("title", "Page title", 80, False), ("body", "Page text", LONG, True)]}
       for slug, title in [("about", "About"), ("faq", "FAQ"), ("shipping", "Shipping"), ("returns", "Returns"),
                           ("privacy", "Privacy policy"), ("terms", "Terms")]},
}
DEFAULTS: dict[str, dict] = {
    "home": {
        "announcement": "", "headline": "Elevate your everyday.",
        "lede": "Plain round neck tees in oversized and regular fits.",
    },
    "size-guide": {"oversized": "", "regular": "", "columns": "Size, Chest (cm), Length (cm)", "note": ""},
    "page-about": {"title": "About Eunice Wears", "body": ""}, "page-faq": {"title": "Questions and answers", "body": ""},
    "page-shipping": {"title": "Shipping", "body": ""}, "page-returns": {"title": "Returns and refunds", "body": ""},
    "page-privacy": {"title": "Privacy policy", "body": ""}, "page-terms": {"title": "Terms and conditions", "body": ""},
}
PAGES = ["about", "faq", "shipping", "returns", "privacy", "terms"]


def get(key: str) -> dict:
    stored = SiteSetting.objects.filter(key=key).values_list("value", flat=True).first() or {}
    return {**DEFAULTS[key], **{k: v for k, v in stored.items() if k in DEFAULTS[key]}}


def get_all() -> dict[str, dict]:
    stored = dict(SiteSetting.objects.filter(key__in=SCHEMA).values_list("key", "value"))
    return {key: {**DEFAULTS[key], **{k: v for k, v in stored.get(key, {}).items() if k in DEFAULTS[key]}} for key in SCHEMA}


def clean(key: str, data: dict) -> dict:
    """Keep only known fields, as trimmed strings within their length limits."""
    return {name: str(data.get(name, "")).strip()[:limit] for name, _, limit, _ in SCHEMA[key]["fields"]}


def table_rows(text: str) -> list[list[str]]:
    return [[cell.strip() for cell in line.split(",")] for line in text.splitlines() if line.strip()]
