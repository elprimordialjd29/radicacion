# Changelog

## 0.8.0 — 2026-10-07
- **Modelo de cápita vencido**: mes de cápita = mes de las atenciones del RIPS + 1; el soporte
  en cero es la cápita del primer mes de vigencia (`INICIAL`). Migración única del historial.
- Detalle: valores y % encima de cada barra, explicación mes a mes, sin columna RIPS
  redundante; recepciones muestran el mes de las atenciones.

## 0.7.1 — 2026-10-07
- **Facturas duplicadas**: análisis de radicaciones vigentes con los soportes RIPS (mismo
  número de factura, mismo contrato+régimen+periodo, servicios idénticos ≥80 %), con usuarios
  en común, servicios idénticos y diferencia de valor; sección en el Reporte y Excel con el
  detalle de servicios repetidos. Corre en un proceso aparte (≈60 MB) y se precalcula al
  terminar cada consulta.

## 0.7.0 — 2026-10-07
- **Validación**: auditoría contra el SIE (todos los estados) — las facturas anuladas no se
  suman; si una radicación deja de figurar como Radicado se marca NO VIGENTE y se excluye.
- Alertas: posible factura duplicada (mismo mes y régimen, valores ±0,5 %), cifra atípica,
  fuera del margen y contratos que superan su valor total.
- Meses **en plazo** de radicación (configurable 1–3 meses) no cuentan como pendientes ni
  como esperado exigible.
- Reporte rediseñado (cabecera, parámetros, alertas, tablas) y detalle con gráfica mensual
  (RS/RC vs tope y franja del margen).
- **Descargas**: Excel del reporte (Resumen, Por prestador, Por contrato, Detalle mensual,
  Alertas, Sin radicar) y del detalle; impresión / PDF.
- **Monitoreo del servidor** (solo administradores): memoria, disco, CPU, servicios,
  cola de consultas, programación y almacenamiento de la app.

## 0.6.0 — 2026-10-06
- **Usuarios y roles**: pantalla de ingreso propia (sin la ventana del navegador), sesión
  firmada en cookie HttpOnly por 12 h. Usuario inicial `admin` (se pide cambiar la clave).
- Permisos por usuario: ver reporte, lanzar consultas al SIE, descargar RIPS, descargar
  reportes (Excel/CSV) y administrar usuarios; roles base Administrador, Analista,
  Auditor RIPS y Solo consulta. Se validan en el servidor (API) y se ocultan en la interfaz.
- Usuarios en Vercel Blob privado con clave cifrada (scrypt). Cambiar mi clave, crear,
  editar, desactivar, restablecer clave y eliminar usuarios.
- Reporte: desviación = radicado por encima del tope + margen aceptable (±5–20 %).

## 0.5.0 — 2026-10-06
- **Pestaña Reporte**:
  1. Prestadores con más periodos sin radicar (meses, contratos y valor esperado en riesgo).
  2. Valor contrato vs radicado: esperado = VALOR CONTRATO ÷ meses de vigencia × meses
     vigentes elegidos; desviación en $ y % de ejecución con barra (meta 100%),
     agrupable por prestador o contrato y ordenable. Exporta a CSV.
- Dashboard: varios meses a la vez (chips + Desde/Hasta), gráfica que sigue la selección
  con animación, pendientes agrupados por contrato, descarga RIPS separada por régimen.
- Consultas programadas a las 12:00 m y 12:00 a. m. (hora Colombia).

## 0.4.1 — 2026-10-06
- Reparación: 644 radicaciones tenían el mes por fecha de recepción (consulta rápida);
  se recalcularon desde los soportes (288 consultas RS+RC sin errores).
- **Periodo estimado (≈)**: 233 radicaciones reales tienen el soporte RIPS del SIE vacío
  (solo encabezado de factura). Se les asigna el mes siguiente al último periodo
  confirmado del mismo contrato y régimen; se reemplaza si luego llega un soporte con fechas.
- `--solo-publicar`: recalcula estimados y republica sin consultar el SIE.

## 0.4.0 — 2026-10-06
- **Descarga de RIPS por mes**: botones TXT (archivo plano original del SIE) y JSON
  (estructura Res. 2275: factura → usuarios → servicios) en cada mes radicado y en
  cada radicación. Si hay varias radicaciones, se entregan en un .zip.
- `bot/rips_json.py`: convertidor plano → JSON 2275 (consultas, procedimientos,
  urgencias, hospitalización, medicamentos y otros servicios), verificado contra
  soportes reales.
- **Régimen Subsidiado y Contributivo**: el bot consulta Capita RS y Capita RC en la
  misma sesión; filtro de régimen en el dashboard y elección de régimen al consultar.
- El periodo ya no puede tomar fechas de USUARIOS (fechas de nacimiento) como respaldo.

## 0.3.1 — 2026-10-06
- Corrección: el bot hacía clic en el buscador general de la barra superior
  (`cmdGeneralSearch`) en lugar del Buscar del formulario (`#cmdBuscar`), y leía
  los registros por defecto de 2022.
- El soporte RIPS se descarga con el botón "descargar el soporte de Rips" de cada fila.
- Probado en el VPS con ASB-20001-2026-36: 6 radicaciones; periodo de marzo de 2026
  según 1.546 consultas del soporte.

## 0.3.0 — 2026-10-06
- **100% web**: las consultas al SIE se lanzan desde el dashboard y corren en el VPS
  (`worker/app.py`, FastAPI + cola, una consulta a la vez) con avance en vivo,
  cancelar y descarga del Excel.
- API `/api/consultas` y `/api/excel` en Vercel (puente con token al worker).
- Usuarios con nombre (`DASHBOARD_USUARIOS`); cada consulta registra quién la lanzó.
- Dashboard: botón Buscar, mes "Todos" y sugerencias por prestador.
- Bot en modo servidor: lee los contratos en JSON, no pide nada por teclado y no usa
  funciones de macOS.
- Archivos de despliegue en `deploy/` y guía en `docs/SERVIDOR.md`.

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
