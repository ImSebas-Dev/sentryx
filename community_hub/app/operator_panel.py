"""
Panel mínimo del operador: una página sin dependencias externas.
Pinta los datos con textContent: el nombre del nodo lo escribe quien se registra,
sin autenticarse, y no debe poder inyectar HTML en este panel.
"""

PANEL_HTML = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sentryx Hub — Operador</title>
<style>
  :root { color-scheme: light dark; font-family: "Segoe UI", Roboto, sans-serif; }
  body { margin: 0 auto; padding: 16px; max-width: 960px; }
  h1 { font-size: 22px; margin: 0 0 12px; }
  .cards { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }
  .card { border: 1px solid #8884; border-radius: 8px; padding: 10px 14px; min-width: 110px; }
  .card b { display: block; font-size: 20px; }
  .wrap { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; font-size: 14px; }
  th, td { text-align: left; padding: 8px; border-bottom: 1px solid #8884; white-space: nowrap; }
  button { font: inherit; padding: 4px 10px; margin-right: 4px; cursor: pointer; }
  #err { color: #c50f1f; min-height: 20px; }
  .guide { border: 1px solid #8884; border-radius: 8px; padding: 10px 14px; margin-bottom: 12px; font-size: 14px; }
  .guide summary { font-weight: 600; cursor: pointer; }
  .guide ol { margin: 8px 0 0; padding-left: 20px; }
</style></head><body>
<h1>Red de alerta: panel del operador</h1>
<details class="guide" open>
  <summary>Cómo usar este panel</summary>
  <ol>
    <li>Las tarjetas resumen cuántos nodos, reportes e indicadores tiene la red.</li>
    <li>Busca en la tabla los nodos con estado «pending»: son empresas que pidieron entrar.</li>
    <li>Confirma con cada empresa, por un canal conocido, que la solicitud es suya. El nombre lo escribe quien se registra.</li>
    <li>Pulsa «Aprobar» para darle acceso. La empresa aún debe reclamar su clave.</li>
    <li>Pulsa «Suspender» si un nodo envía reportes falsos o abusa de la red.</li>
  </ol>
</details>
<div id="err" role="alert"></div>
<div class="cards" id="metrics"></div>
<div class="wrap"><table>
  <thead><tr><th>Nombre</th><th>Sector</th><th>Región</th><th>Estado</th><th>Reportes</th>
  <th>Reputación</th><th>Acciones</th></tr></thead>
  <tbody id="nodes"></tbody>
</table></div>
<script>
const $ = id => document.getElementById(id);
const headers = { "X-Operator-Action": "1" };

function card(label, value) {
  const el = document.createElement("div");
  el.className = "card";
  const b = document.createElement("b");
  b.textContent = value;
  el.append(b, label);
  return el;
}

function button(label, onClick) {
  const el = document.createElement("button");
  el.textContent = label;
  el.addEventListener("click", onClick);
  return el;
}

async function act(path) {
  const res = await fetch(path, { method: "POST", headers });
  if (!res.ok) $("err").textContent = "La acción falló (" + res.status + ").";
  load();
}

async function load() {
  const [m, nodes] = await Promise.all([
    fetch("/operator/metrics").then(r => r.json()),
    fetch("/operator/nodes").then(r => r.json()),
  ]);
  $("metrics").replaceChildren(
    card("nodos activos", m.nodes.active || 0),
    card("pendientes", m.nodes.pending || 0),
    card("suspendidos", m.nodes.suspended || 0),
    card("reportes", m.reports),
    card("indicadores", m.indicators),
    card("visibles en el feed", m.visible_indicators),
  );
  $("nodes").replaceChildren(...nodes.map(n => {
    const row = document.createElement("tr");
    [n.name, n.sector, n.region, n.status + (n.established ? " (establecido)" : ""),
     n.reports, n.reputation].forEach(value => {
      const td = document.createElement("td");
      td.textContent = value;
      row.append(td);
    });
    const actions = document.createElement("td");
    if (n.status !== "active") {
      actions.append(button("Aprobar", () => act("/operator/nodes/" + n.id + "/approve")));
    } else {
      actions.append(button("Suspender", () => act("/operator/nodes/" + n.id + "/suspend")));
    }
    row.append(actions);
    return row;
  }));
}
load();
</script></body></html>
"""
