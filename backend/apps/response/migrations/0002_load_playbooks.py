"""
Cargar los 4 playbooks de la respuesta guiada, en español claro y sin teléfonos:
los números de emergencia los completa cada empresa en sus contactos.
"""
from django.db import migrations

PLAYBOOKS = [
    {
        "key": "password",
        "title": "Escribí mi contraseña en un enlace",
        "description": "Alguien pudo quedarse con tu contraseña. Cámbiala antes de que la use.",
        "severity": "HIGH",
        "steps": [
            {"id": "cambiar-clave", "critical": True,
             "title": "Cambia la contraseña desde otro dispositivo",
             "detail": "Usa otro celular o computador, y entra escribiendo la dirección a mano. "
                       "No uses el enlace del correo. Si usas esa clave en otros servicios, "
                       "cámbiala también allí."},
            {"id": "cerrar-sesiones", "critical": True,
             "title": "Cierra las sesiones abiertas",
             "detail": "En la seguridad de tu cuenta elige «Cerrar sesión en todos los dispositivos»."},
            {"id": "activar-2fa", "critical": True,
             "title": "Activa la verificación en dos pasos",
             "detail": "Así la contraseña sola ya no alcanza para entrar a tu cuenta."},
            {"id": "revisar-reenvio", "critical": False,
             "title": "Revisa las reglas de reenvío del correo",
             "detail": "Los atacantes crean reglas que copian tus correos a otra dirección. "
                       "Borra las que no reconozcas."},
            {"id": "avisar-admin", "critical": False,
             "title": "Avisa al administrador",
             "detail": "Cuéntale qué cuenta se afectó y a qué hora escribiste la contraseña. "
                       "Sentryx ya le envió un aviso."},
        ],
    },
    {
        "key": "attachment",
        "title": "Abrí un archivo adjunto",
        "description": "El archivo pudo instalar algo en tu equipo. Aísla el equipo primero.",
        "severity": "CRITICAL",
        "steps": [
            {"id": "desconectar-red", "critical": True,
             "title": "Desconecta el equipo de la red",
             "detail": "Quita el cable de red y apaga el wifi. Así evitas que se propague a otros "
                       "equipos o que saque información."},
            {"id": "no-apagar", "critical": True,
             "title": "No apagues el equipo",
             "detail": "Déjalo encendido y sin usarlo: apagarlo puede borrar evidencia que sirve "
                       "para saber qué pasó."},
            {"id": "avisar-admin", "critical": True,
             "title": "Avisa al administrador",
             "detail": "Dile qué equipo es, qué archivo abriste y a qué hora."},
            {"id": "escanear", "critical": False,
             "title": "Escanea con el antivirus",
             "detail": "Hazlo cuando el administrador lo indique, con el equipo todavía aislado."},
        ],
    },
    {
        "key": "payment",
        "title": "Hice un pago o transferencia",
        "description": "Cada minuto cuenta: el banco solo puede intentar frenarla si avisas ya.",
        "severity": "CRITICAL",
        "steps": [
            {"id": "llamar-banco", "critical": True,
             "title": "Llama de inmediato a la línea de fraude de tu banco",
             "detail": "Pide que intenten congelar o reversar la transferencia. Usa el número de "
                       "tus contactos de emergencia o el que aparece detrás de tu tarjeta, nunca "
                       "uno que venga en el correo. Anota el número de radicado."},
            {"id": "guardar-comprobantes", "critical": True,
             "title": "Guarda los comprobantes",
             "detail": "Conserva el comprobante de pago y el correo original. No los borres."},
            {"id": "avisar-gerencia", "critical": True,
             "title": "Avisa a gerencia",
             "detail": "Cuéntales el valor, la cuenta de destino y la hora del pago."},
        ],
    },
    {
        "key": "data",
        "title": "Compartí datos de la empresa o de clientes",
        "description": "Identifica qué salió para decidir a quién hay que avisar.",
        "severity": "HIGH",
        "steps": [
            {"id": "identificar-datos", "critical": True,
             "title": "Identifica qué datos compartiste",
             "detail": "Anota qué información era, de cuántas personas y a quién se la enviaste. "
                       "No copies aquí los datos: describe solo de qué tipo eran."},
            {"id": "avisar-responsable", "critical": True,
             "title": "Avisa al responsable del tratamiento de datos",
             "detail": "Es quien debe decidir los siguientes pasos en la empresa. Si no sabes "
                       "quién es, avisa a gerencia."},
            {"id": "evaluar-sic", "critical": False,
             "title": "Evalúa el reporte a la SIC",
             "detail": "Si hay datos personales de clientes o empleados, el responsable debe "
                       "evaluar si corresponde reportar el incidente ante la Superintendencia de "
                       "Industria y Comercio. Verifica los plazos vigentes con tu asesor legal."},
        ],
    },
]


def load(apps, schema_editor):
    Playbook = apps.get_model("response", "Playbook")
    for data in PLAYBOOKS:
        Playbook.objects.update_or_create(key=data["key"], defaults=data)


def unload(apps, schema_editor):
    apps.get_model("response", "Playbook").objects.filter(
        key__in=[p["key"] for p in PLAYBOOKS]).delete()


class Migration(migrations.Migration):

    dependencies = [("response", "0001_initial")]

    operations = [migrations.RunPython(load, unload)]
