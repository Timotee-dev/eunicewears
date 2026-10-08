from django.conf import settings

from . import content as site_content


def site(request) -> dict:
    return {"SITE_NAME": settings.SITE_NAME, "SITE_URL": settings.SITE_URL}


def content(request) -> dict:
    if request.path.startswith(("/api/", "/dashboard/")):
        return {}
    home = site_content.get("home")
    return {"home_content": home, "announcement": home["announcement"], "social_links": site_content.social_links(),
            "canonical_url": settings.SITE_URL + request.path}
