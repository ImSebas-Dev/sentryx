#!/usr/bin/env python3
"""
Sentryx — Simulación de la Red de alerta para la demo. Solo usa la librería estándar.

Requisitos: el hub corriendo y COMMUNITY_HUB_OPERATOR_KEY definida.

    docker compose --profile hub up -d
    python scripts/dev/simulate_network.py --operator-key <clave> --local

Qué hace:
  1. Registra y aprueba 3 nodos ficticios en el hub.
  2. Los 3 reportan un dominio compartido; solo uno reporta un dominio único.
  3. Muestra que el feed trae el compartido, no el único, y ningún dato de los nodos.
  4. Con --local, descarga el feed al backend y comprueba que el nodo local recibe el aviso.

Los nodos se aprueban como "establecidos" a propósito: un nodo nuevo cuenta como medio
reporte durante 7 días, así que 3 nodos recién creados sumarían 1,5 y nunca llegarían a K=2.
"""
import argparse
import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import date

SHARED_DOMAIN = "pagos-falsos-demo.example"
UNIQUE_DOMAIN = "solo-un-reporte-demo.example"
NODES = [("Transportes Demo A", "H", "Cundinamarca"),
         ("Transportes Demo B", "H", "Cundinamarca"),
         ("Comercio Demo C", "G", "Bogotá D.C.")]


def request(method, url, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, {"detail": exc.read().decode(errors="replace")}


def ioc_hash(value, key):
    return hmac.new(key.encode(), value.encode(), hashlib.sha256).hexdigest()


def create_node(hub, operator_headers, name, sector, region):
    status, reg = request("POST", f"{hub}/nodes/register",
                          {"name": f"{name} {int(time.time())}", "sector": sector, "region": region})
    if status != 201:
        sys.exit(f"No se pudo registrar el nodo: {status} {reg}")
    status, result = request(
        "POST", f"{hub}/operator/nodes/{reg['node_id']}/approve?established=true",
        headers=operator_headers)
    if status != 200:
        sys.exit(f"No se pudo aprobar: {status} {result}. ¿La clave de operador es correcta?")
    status, claim = request("POST", f"{hub}/nodes/claim", {
        "node_id": reg["node_id"], "registration_token": reg["registration_token"]})
    if status != 200:
        sys.exit(f"No se pudo reclamar la key: {status} {claim}")
    return {"X-Node-Key": claim["node_api_key"]}


def report(hub, headers, domain, sector, region, network_key):
    status, result = request("POST", f"{hub}/indicators", {"indicators": [{
        "ioc_type": "domain", "ioc_hash": ioc_hash(domain, network_key),
        "phishing_type": "bec", "mitre_technique": "T1566.002", "severity": "HIGH",
        "sector": sector, "region": region, "observed_on": date.today().isoformat(),
    }]}, headers)
    if status != 200:
        sys.exit(f"No se pudo reportar: {status} {result}")


def main():
    # La consola de Windows usa cp1252 y fallaría al imprimir algunos caracteres
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--hub", default=os.environ.get("HUB_URL", "http://localhost:8100"))
    parser.add_argument("--operator-key", default=os.environ.get("COMMUNITY_HUB_OPERATOR_KEY", ""))
    parser.add_argument("--network-key", default=os.environ.get("COMMUNITY_NETWORK_KEY", "clave-demo-de-la-red"))
    parser.add_argument("--local", action="store_true",
                        help="Descarga el feed al backend con docker compose")
    args = parser.parse_args()
    if not args.operator_key:
        sys.exit("Falta --operator-key (o COMMUNITY_HUB_OPERATOR_KEY).")

    status, _ = request("GET", f"{args.hub}/health")
    if status != 200:
        sys.exit(f"El hub no responde en {args.hub}. Levántalo con: docker compose --profile hub up -d")

    credentials = base64.b64encode(f"operator:{args.operator_key}".encode()).decode()
    operator_headers = {"Authorization": f"Basic {credentials}", "X-Operator-Action": "1"}

    print("1. Registrando y aprobando 3 nodos ficticios...")
    keys = [create_node(args.hub, operator_headers, *node) for node in NODES]

    print("2. Enviando indicadores: un dominio compartido y uno único...")
    for node_headers, (_, sector, region) in zip(keys, NODES):
        report(args.hub, node_headers, SHARED_DOMAIN, sector, region, args.network_key)
    report(args.hub, keys[0], UNIQUE_DOMAIN, NODES[0][1], NODES[0][2], args.network_key)

    print("3. Consultando el feed...")
    _, feed = request("GET", f"{args.hub}/feed", headers=keys[1])
    items = {item["ioc_hash"]: item for item in feed.get("indicators", [])}
    shared = items.get(ioc_hash(SHARED_DOMAIN, args.network_key))
    unique = items.get(ioc_hash(UNIQUE_DOMAIN, args.network_key))
    if not shared or unique:
        sys.exit(f"Resultado inesperado. Compartido: {shared}. Único: {unique}.")
    print(f"   OK {SHARED_DOMAIN}: visible, reportado por {shared['company_count']} empresas")
    print(f"     sectores {shared['sectors']}, regiones {shared['regions']}")
    print(f"   OK {UNIQUE_DOMAIN}: NO aparece, tiene menos de K reportes")
    print(f"   OK Campos del feed: {sorted(shared)} (ninguno identifica a un nodo)")

    print("4. Nodo local...")
    local_key = create_node(args.hub, operator_headers, "Nodo local demo", "H", "Cundinamarca")["X-Node-Key"]
    if args.local:
        result = subprocess.run(
            ["docker", "compose", "exec", "-T", "backend", "python", "manage.py", "community_pull",
             "--hub-url", "http://community_hub:8100", "--api-key", local_key,
             "--network-key", args.network_key, "--check-domain", SHARED_DOMAIN],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        lines = [ln for ln in result.stdout.splitlines() if ln and not ln.startswith("[")]
        print("   " + "\n   ".join(lines) if lines else result.stderr)
        if result.returncode != 0:
            sys.exit(result.returncode)
        print(f"   OK El backend ya tiene el aviso de {SHARED_DOMAIN} en su copia local")
    print("\nPara verlo en la interfaz, agrega al .env, reinicia el backend y activa la red:")
    print("   COMMUNITY_HUB_URL=http://community_hub:8100")
    print(f"   COMMUNITY_NODE_API_KEY={local_key}")
    print(f"   COMMUNITY_NETWORK_KEY={args.network_key}")
    print(f"Luego analiza un correo de pagos@{SHARED_DOMAIN}.")


if __name__ == "__main__":
    main()
