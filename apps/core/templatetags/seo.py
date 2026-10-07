import json

from django import template
from django.core.serializers.json import DjangoJSONEncoder
from django.utils.safestring import mark_safe

register = template.Library()
_ESCAPES = {ord(">"): "\\u003E", ord("<"): "\\u003C", ord("&"): "\\u0026"}


@register.simple_tag
def jsonld(data) -> str:
    """Structured data block. <, > and & are escaped so product text can never close the tag."""
    body = json.dumps(data, cls=DjangoJSONEncoder).translate(_ESCAPES)
    return mark_safe(f'<script type="application/ld+json">{body}</script>')
