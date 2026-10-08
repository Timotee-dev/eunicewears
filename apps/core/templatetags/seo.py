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


@register.filter
def prose(text: str) -> str:
    """Owner-written page text to HTML. Everything is escaped first; then "## " lines become headings,
    "- " lines become list items and blank lines separate paragraphs. No other markup is possible."""
    from django.utils.html import escape

    out, items = [], []

    def flush() -> None:
        if items:
            out.append("<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>")
            items.clear()

    for block in str(text).replace("\r\n", "\n").split("\n\n"):
        lines = [line.strip() for line in block.strip().split("\n") if line.strip()]
        if not lines:
            continue
        para = []
        for line in lines:
            if line.startswith("## "):
                flush()
                if para:
                    out.append("<p>" + "<br>".join(para) + "</p>")
                    para = []
                out.append(f"<h2>{escape(line[3:])}</h2>")
            elif line.startswith("- "):
                if para:
                    out.append("<p>" + "<br>".join(para) + "</p>")
                    para = []
                items.append(escape(line[2:]))
            else:
                flush()
                para.append(escape(line))
        if para:
            out.append("<p>" + "<br>".join(para) + "</p>")
    flush()
    return mark_safe("".join(out))
