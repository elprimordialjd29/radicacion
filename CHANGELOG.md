# Changelog

## 0.2.0 — 2026-10-06
- Repositorio con control de cambios, documentación y despliegue en Vercel.
- Dashboard: cumplimiento por mes, matriz contrato × mes, pendientes, radicaciones,
  historial de corridas, exportación CSV, modo oscuro.
- API `/api/subir` (token) y `/api/datos`, con Vercel Blob privado y acceso con clave.
- Bot: lee el Excel CONTRATOS_CAPITADOS (prestador, NIT, municipio, vigencia).
- Bot: omite los meses fuera de vigencia del contrato.
- Bot: el historial guarda el periodo, las fechas de atención y la fuente.
- Bot: opciones `--solo`, `--incluir-fuera-vigencia` y `--no-publicar`.
- Corrección: la columna IPS ya no se confunde con "Recepción RIPS".

## 0.1.0 — 2026-10-06
- Bot Playwright: login, Consulta Recepción, filtros Cápita/Radicado por contrato.
- Periodo tomado del soporte RIPS (`ARCHIVO-CONSULTAS`).
- Excel con Resumen, Detalle, Novedades, Pendientes y Revisar.
- Historial SQLite y notificación de macOS.
