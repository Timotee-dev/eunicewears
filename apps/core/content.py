"""Owner-editable site content. Defaults live here; edits are stored in SiteSetting and merged over them."""
from . import page_text
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
    "social": {"label": "Social and contact links", "fields": [
        ("tiktok", "TikTok username or link (e.g. @eunicewears)", T, False),
        ("instagram", "Instagram username or link", T, False),
        ("whatsapp", "WhatsApp number with country code (e.g. 2348012345678)", 20, False),
        ("email", "Contact email shown to customers", T, False)]},
    **{f"page-{slug}": {"label": title, "fields": [("title", "Page title", 80, False), ("body", "Page text", LONG, True)]}
       for slug, title in [("about", "About"), ("faq", "FAQ"), ("shipping", "Shipping"), ("returns", "Returns"),
                           ("privacy", "Privacy policy"), ("terms", "Terms")]},
}
DEFAULTS: dict[str, dict] = {
    "home": {
        "announcement": "", "headline": "Elevate your everyday.",
        "lede": "Plain round neck tees in oversized and regular fits.",
    },
    "size-guide": {
        "oversized": "S, 56, 70\nM, 59, 72\nL, 62, 74\nXL, 65, 76\nXXL, 68, 78",
        "regular": "S, 49, 68\nM, 52, 70\nL, 55, 72\nXL, 58, 74\nXXL, 61, 76",
        "columns": "Size, Chest width (cm), Length (cm)",
        "note": "Measured with the tee laid flat: chest is straight across from armpit to armpit, length is from the top of the shoulder to the hem. Allow 1 to 2 cm either way.",
    },
    "social": {"tiktok": "", "instagram": "", "whatsapp": "", "email": ""},
    "page-about": {"title": "About Eunice Wears", "body": page_text.ABOUT},
    "page-faq": {"title": "Questions and answers", "body": page_text.FAQ},
    "page-shipping": {"title": "Shipping and delivery", "body": page_text.SHIPPING},
    "page-returns": {"title": "Returns and refunds", "body": page_text.RETURNS},
    "page-privacy": {"title": "Privacy policy", "body": page_text.PRIVACY},
    "page-terms": {"title": "Terms and conditions", "body": page_text.TERMS},
}
PAGES = ["about", "faq", "shipping", "returns", "privacy", "terms"]


def _merge(key: str, stored: dict) -> dict:
    """Saved text wins over the starter text. A page saved with an empty title or body falls back to the starter
    text, so an information page is never blank; other fields (like the announcement bar) may be left empty."""
    keep_empty = not key.startswith("page-")
    if key == "size-guide" and not (str(stored.get("oversized", "")).strip() or str(stored.get("regular", "")).strip()):
        return dict(DEFAULTS[key])  # no measurements saved yet: show the starter chart
    return {**DEFAULTS[key], **{k: v for k, v in stored.items() if k in DEFAULTS[key] and (keep_empty or str(v).strip())}}


def get(key: str) -> dict:
    return _merge(key, SiteSetting.objects.filter(key=key).values_list("value", flat=True).first() or {})


def get_all() -> dict[str, dict]:
    stored = dict(SiteSetting.objects.filter(key__in=SCHEMA).values_list("key", "value"))
    return {key: _merge(key, stored.get(key, {})) for key in SCHEMA}


def clean(key: str, data: dict) -> dict:
    """Keep only known fields, as trimmed strings within their length limits."""
    return {name: str(data.get(name, "")).strip()[:limit] for name, _, limit, _ in SCHEMA[key]["fields"]}


def table_rows(text: str) -> list[list[str]]:
    return [[cell.strip() for cell in line.split(",")] for line in text.splitlines() if line.strip()]


def social_links() -> list[dict]:
    """Links for the footer, built from whatever the owner filled in under Content > Social and contact links."""
    import re

    value, links = get("social"), []

    def profile(raw: str, base: str, at: bool) -> str:
        raw = raw.strip()
        if raw.lower().startswith(("http://", "https://")):
            return raw if raw.lower().startswith("https://") else ""
        handle = re.sub(r"[^A-Za-z0-9._]", "", raw.lstrip("@"))
        return f"{base}{'@' if at else ''}{handle}" if handle else ""

    if url := profile(value["tiktok"], "https://www.tiktok.com/", True):
        links.append({"name": "TikTok", "icon": "i-tiktok", "url": url})
    if url := profile(value["instagram"], "https://www.instagram.com/", False):
        links.append({"name": "Instagram", "icon": "i-instagram", "url": url})
    if digits := re.sub(r"\D", "", value["whatsapp"]):
        links.append({"name": "WhatsApp", "icon": "i-whatsapp", "url": f"https://wa.me/{digits}"})
    if "@" in value["email"] and " " not in value["email"].strip():
        links.append({"name": "Email", "icon": "i-mail", "url": f"mailto:{value['email'].strip()}"})
    return links
