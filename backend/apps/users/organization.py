"""
Sentryx v2 — Separación de datos por empresa.

ShieldUser.organization es texto libre y puede venir vacío (registro sin empresa,
usuarios sembrados por setup.sh). Usa siempre estas funciones para comparar
organizaciones: dos usuarios sin empresa NO pertenecen a la misma organización.
"""


def org_of(user) -> str:
    return (getattr(user, "organization", "") or "").strip()


def same_org(user_a, user_b) -> bool:
    org_a = org_of(user_a)
    return bool(org_a) and org_a == org_of(user_b)


def users_of_org(organization: str):
    """Usuarios activos que pueden iniciar sesión en la organización."""
    from django.contrib.auth import get_user_model
    if not organization:
        return get_user_model().objects.none()
    return get_user_model().objects.filter(
        organization=organization, is_active=True, is_email_verified=True,
    )
