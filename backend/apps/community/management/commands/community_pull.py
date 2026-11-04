"""
Descargar el feed del hub con credenciales pasadas por parámetro.

Lo usa scripts/dev/simulate_network.py para que la demo funcione sin editar el .env.
En operación normal esto lo hace la tarea community.sync.
"""
from django.core.management.base import BaseCommand, CommandError

from apps.community import services
from apps.community.models import CommunityIndicator


class Command(BaseCommand):
    help = "Descarga el feed del hub a la copia local y, si se pide, busca un dominio en ella."

    def add_arguments(self, parser):
        parser.add_argument("--hub-url", required=True)
        parser.add_argument("--api-key", required=True)
        parser.add_argument("--network-key", help="Clave de la red, para --check-domain")
        parser.add_argument("--check-domain", help="Dominio a buscar en la copia local")

    def handle(self, *args, **options):
        try:
            count = services.pull_feed(hub_url=options["hub_url"], api_key=options["api_key"])
        except services.HubError as exc:
            raise CommandError(exc.message)
        self.stdout.write(f"Indicadores en la copia local: {count}")

        domain = options.get("check_domain")
        if domain:
            hash_value = services.ioc_hash(services.normalize_domain(domain),
                                           options.get("network_key"))
            found = CommunityIndicator.objects.filter(ioc_hash=hash_value).first()
            if found is None:
                self.stdout.write(f"{domain}: sin reportes en el feed")
            else:
                self.stdout.write(f"{domain}: reportado por {found.company_count} empresas "
                                  f"(sectores {found.sectors}, regiones {found.regions})")
