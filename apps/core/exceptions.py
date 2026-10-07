"""Every API error has one shape: {"error": {"code", "message", "fields"}}."""
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler


def _first_message(detail) -> str:
    if isinstance(detail, dict):
        return _first_message(next(iter(detail.values())))
    if isinstance(detail, list):
        return _first_message(detail[0]) if detail else ""
    return str(detail)


def api_exception_handler(exc, context) -> Response | None:
    response = exception_handler(exc, context)
    if response is None:
        return None  # unhandled -> Django's 500 handling, no stack trace leaks
    fields = None
    if isinstance(exc, exceptions.ValidationError):
        code = "validation_error"
        if isinstance(exc.detail, dict):
            fields = {k: [str(m) for m in (v if isinstance(v, list) else [v])] for k, v in exc.detail.items()}
            message = "Check the highlighted fields and try again."
            if set(fields) == {"non_field_errors"}:
                message = fields.pop("non_field_errors")[0]
                fields = None
        else:
            message = _first_message(exc.detail)
    else:
        codes = exc.get_codes() if hasattr(exc, "get_codes") else "error"
        code = codes if isinstance(codes, str) else "error"
        message = _first_message(getattr(exc, "detail", "Something went wrong."))
    response.data = {"error": {"code": code, "message": message, "fields": fields}}
    return response
