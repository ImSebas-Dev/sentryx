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


def scope_to_user(queryset, user, owner_field="owner"):
    """
    Filtra un queryset por el dueño de cada registro según quién consulta:
      - superusuario de la plataforma: todo;
      - admin de una empresa: los registros de los usuarios de SU empresa;
      - admin sin empresa o cualquier otro rol: solo los suyos.
    Úsala en toda vista que liste datos de usuarios: antes el admin de una
    empresa veía las alertas, incidentes y auditoría de todas las demás.
    """
    if getattr(user, "is_superuser", False):
        return queryset
    organization = org_of(user)
    if getattr(user, "is_admin", False) and organization:
        return queryset.filter(**{f"{owner_field}__organization": organization})
    return queryset.filter(**{owner_field: user})
