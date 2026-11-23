from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


class DomainError(Exception):
    """Business-rule failure rendered as {"code", "detail"}."""

    def __init__(self, code, detail, status=400):
        super().__init__(detail)
        self.code, self.detail, self.status = code, detail, status


def exception_handler(exc, context):
    if isinstance(exc, DomainError):
        return Response({"code": exc.code, "detail": exc.detail}, status=exc.status)
    return drf_exception_handler(exc, context)
