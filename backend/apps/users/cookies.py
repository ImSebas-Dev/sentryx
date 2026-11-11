"""
Sentryx v2 — Refresh token del panel web en una cookie HttpOnly.

El panel web se identifica con la cabecera X-Sentryx-Client: web. Para esas
peticiones el refresh token no viaja en el cuerpo de la respuesta (donde el
JavaScript, y por tanto un XSS, podría leerlo): va en una cookie HttpOnly,
SameSite=Strict, limitada a /api/v1/auth/. El access token, de vida corta, lo
guarda el panel solo en memoria.

La extensión del navegador no envía la cabecera y sigue recibiendo el par en el
cuerpo, como antes.
"""
from django.conf import settings


def is_web_client(request) -> bool:
    request = getattr(request, "_request", request)
    return request.META.get(settings.AUTH_WEB_CLIENT_HEADER, "").lower() == "web"


def set_refresh_cookie(response, refresh: str):
    response.set_cookie(
        settings.AUTH_REFRESH_COOKIE_NAME, refresh,
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        path=settings.AUTH_REFRESH_COOKIE_PATH,
        secure=settings.AUTH_REFRESH_COOKIE_SECURE,
        httponly=True,
        samesite="Strict",
    )
    return response


def clear_refresh_cookie(response):
    response.delete_cookie(settings.AUTH_REFRESH_COOKIE_NAME,
                           path=settings.AUTH_REFRESH_COOKIE_PATH, samesite="Strict")
    return response


def refresh_from_cookie(request) -> str:
    request = getattr(request, "_request", request)
    return request.COOKIES.get(settings.AUTH_REFRESH_COOKIE_NAME, "")


def token_response(request, body: dict, status=200):
    """
    Respuesta con el par JWT. Para el panel web mueve el refresh a la cookie.
    Usar en todo endpoint que entregue tokens (login, 2FA, refresh).
    """
    from rest_framework.response import Response

    body = dict(body)
    refresh = body.get("refresh")
    if refresh and is_web_client(request):
        body.pop("refresh")
        response = Response(body, status=status)
        return set_refresh_cookie(response, refresh)
    return Response(body, status=status)
