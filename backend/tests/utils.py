"""Utilidades compartidas por las pruebas del backend."""
from django.contrib.auth import get_user_model

User = get_user_model()


def make_user(email, role="analyst", password="SecurePass123!", **extra):
    """
    Crear un usuario que ya puede iniciar sesión (correo verificado y cuenta
    aprobada). Usar siempre este helper: un usuario sin aprobar recibe 403 en
    el login y las pruebas fallarían por un motivo distinto al que prueban.
    """
    username = extra.pop("username", email.split("@")[0])
    fields = {"is_email_verified": True, "is_approved": True, "accepted_terms": True}
    fields.update(extra)
    user = User.objects.create_user(
        username=username, email=email, password=password, role=role, **fields,
    )
    return user
