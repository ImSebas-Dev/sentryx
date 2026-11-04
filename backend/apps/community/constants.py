"""Listas de la Red de alerta. Mantén SECTORS y DEPARTMENTS iguales a community_hub/app/schemas.py."""

# Secciones de la Clasificación Industrial Internacional Uniforme (CIIU Rev. 4)
SECTORS = [
    ("A", "Agricultura, ganadería, silvicultura y pesca"),
    ("B", "Explotación de minas y canteras"),
    ("C", "Industrias manufactureras"),
    ("D", "Suministro de electricidad, gas y vapor"),
    ("E", "Agua, alcantarillado y gestión de desechos"),
    ("F", "Construcción"),
    ("G", "Comercio y reparación de vehículos"),
    ("H", "Transporte y almacenamiento"),
    ("I", "Alojamiento y servicios de comida"),
    ("J", "Información y comunicaciones"),
    ("K", "Actividades financieras y de seguros"),
    ("L", "Actividades inmobiliarias"),
    ("M", "Actividades profesionales, científicas y técnicas"),
    ("N", "Servicios administrativos y de apoyo"),
    ("O", "Administración pública y defensa"),
    ("P", "Educación"),
    ("Q", "Salud humana y asistencia social"),
    ("R", "Actividades artísticas y de entretenimiento"),
    ("S", "Otras actividades de servicios"),
    ("T", "Actividades de los hogares como empleadores"),
    ("U", "Organizaciones extraterritoriales"),
]

# Los 32 departamentos y Bogotá D.C.
DEPARTMENTS = [
    "Amazonas", "Antioquia", "Arauca", "Atlántico", "Bogotá D.C.", "Bolívar", "Boyacá", "Caldas",
    "Caquetá", "Casanare", "Cauca", "Cesar", "Chocó", "Córdoba", "Cundinamarca", "Guainía",
    "Guaviare", "Huila", "La Guajira", "Magdalena", "Meta", "Nariño", "Norte de Santander",
    "Putumayo", "Quindío", "Risaralda", "San Andrés y Providencia", "Santander", "Sucre",
    "Tolima", "Valle del Cauca", "Vaupés", "Vichada",
]

# Sube la versión si cambias el texto: quien aceptó el anterior no aceptó este.
CONSENT_VERSION = "1"
CONSENT_TEXT = """Al activar la Red de alerta, tu empresa comparte con las demás empresas de la red \
avisos sobre campañas de phishing.

Qué se comparte, por cada indicador de una alerta con puntaje de 70 o más, o resuelta por un analista:
- Una huella (HMAC-SHA256) del dominio o de la URL, que no permite leer el valor original sin la clave de la red.
- El tipo de phishing, la técnica MITRE y la severidad.
- El sector CIIU y el departamento que elijas aquí.
- La fecha en que se observó, sin la hora.

Qué nunca se comparte: el cuerpo o el asunto de los correos, los remitentes, los destinatarios, \
el nombre de tu empresa ni los usuarios.

Otras empresas solo ven un indicador cuando varias lo reportaron, y nunca saben quiénes fueron. \
El operador de la red sí conoce el nombre que se registró para cada nodo, pero no el contenido de tus correos.

Puedes desactivar la red cuando quieras: dejaremos de enviar datos y pediremos borrar tus aportes."""

# Nunca compartas ni marques estos dominios: los usan millones de personas. Un phishing
# enviado desde Gmail haría que cualquier correo de Gmail pareciera una campaña.
EXCLUDED_DOMAINS = {
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "msn.com",
    "yahoo.com", "yahoo.es", "icloud.com", "me.com", "aol.com", "protonmail.com", "proton.me",
    "zoho.com", "gmx.com", "mail.com", "google.com", "microsoft.com", "office.com",
    "office365.com", "sharepoint.com", "dropbox.com", "facebook.com", "linkedin.com",
    "whatsapp.com", "instagram.com", "youtube.com", "amazon.com",
}

# Quita estos parámetros antes de calcular la huella de una URL
TRACKING_PARAMS = {
    "gclid", "fbclid", "msclkid", "mc_cid", "mc_eid", "igshid", "yclid", "_hsenc", "_hsmi",
    "mkt_tok", "ref", "ref_src",
}
TRACKING_PREFIXES = ("utm_",)
