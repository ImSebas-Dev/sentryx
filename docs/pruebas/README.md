# Prueba del sistema con 100 correos

Prueba de punta a punta de Sentryx v2 con 100 correos en contexto colombiano
(40 legítimos y 60 de phishing en 7 tipos), enviados por la API real.

| Archivo | Contenido |
| --- | --- |
| `corpus_legitimos.py` | 40 correos legítimos (banca, DIAN, servicios públicos, comercio, correo interno) |
| `corpus_phishing.py` | 60 correos de phishing reconstruidos a partir de campañas documentadas en Colombia |
| `ejecutar_prueba.py` | Envía los 100 correos a `POST /api/v1/alerts/analyze/` y calcula métricas |
| `verificar_funcional.py` | Revisa alertas, campañas, seudonimización, auditoría, informes y aislamiento |
| `resultados.json` | Respuesta de la API para cada correo |
| `metricas.json` | Matriz de confusión, métricas por tipo y latencias |
| `verificacion_funcional.json` | Resultado de las verificaciones funcionales |
| `anexo_resultados.md` | Tabla de los 100 correos con su resultado |

Resultado del 12 de octubre de 2026 (commit con modelos `*_v1` sin reentrenar):
exactitud 94 %, precisión 98,2 %, exhaustividad 91,7 %, F1 0,948; tipo correcto
en 20 de 60 correos de phishing.

## Repetir la prueba

Usar un usuario analista dedicado (`prueba.sistema@sentryx.local`, ver el
script) para que las alertas no se mezclen con las de otros usuarios.

```bash
docker cp docs/pruebas sentryx_backend:/tmp/
docker compose exec -u root backend chown -R appuser /tmp/pruebas
docker compose exec backend python /tmp/pruebas/ejecutar_prueba.py
docker compose exec -T backend sh -c "python manage.py shell < /tmp/pruebas/verificar_funcional.py"
docker cp sentryx_backend:/tmp/pruebas/resultados.json docs/pruebas/
docker cp sentryx_backend:/tmp/pruebas/metricas.json docs/pruebas/
```

No usar estos correos para entrenar: si entran al dataset, la prueba deja de
medir generalización.

## Fuentes de las modalidades de phishing

- [La DIAN advirtió sobre engaños por correo electrónico (Infobae, 2024)](https://www.infobae.com/colombia/2024/09/29/la-dian-advirtio-sobre-enganos-por-medio-de-correos-electronicos-conozca-como-identificar-mensajes-fraudulentos/)
- [Alertan por correos con falsas citaciones judiciales y multas (El Colombiano)](https://www.elcolombiano.com/tecnologia/alertan-correos-falsas-citaciones-judiciales-multas-fraude-victima-NG39598072)
- [Campaña de phishing con Bre-B y llaves digitales (DPL News, 2025)](https://dplnews.com/?p=282871)
- [Suplantación de Bancolombia (Colombia.com con ESET)](https://www.colombia.com/tecnologia/internet/sdi/152466/bancolombia-nueva-estafa-esta-afectando-a-miles-de-clientes)
