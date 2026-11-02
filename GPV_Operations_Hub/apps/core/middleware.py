from django.shortcuts import redirect
from django.urls import reverse

from .logging_utils import new_op_id, reset_op_id, set_op_id


class OperationIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        op_id = new_op_id()
        request.op_id = op_id
        token = set_op_id(op_id)
        try:
            response = self.get_response(request)
        finally:
            reset_op_id(token)
        response["X-Operation-Id"] = op_id
        return response


class SecurityHeadersMiddleware:
    """Conservative CSP: every script/style is served locally."""

    CSP = (
        "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Content-Security-Policy", self.CSP)
        response.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response


class PasswordChangeRequiredMiddleware:
    EXEMPT = ("/cuenta/", "/static/", "/salir/", "/entrar/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and not request.path.startswith(self.EXEMPT):
            profile = getattr(user, "profile", None)
            if profile is not None and profile.must_change_password:
                return redirect(reverse("password_change"))
        return self.get_response(request)
