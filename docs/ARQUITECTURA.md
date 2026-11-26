# Arquitectura

## Componentes
| Ruta | Rol |
|---|---|
| `bot/sie_bot.py` | Automatización Playwright del SIE: consulta, descarga de soportes, periodo, Excel, publicación |
| `bot/rips_json.py` | Plano del SIE → JSON Res. 2275 (`convertir`) y unión de varios meses (`unir_planos`) |
| `bot/duplicados.py` | Análisis de facturas duplicadas (proceso aparte) |
| `bot/liquidacion.py` | Playwright: Prefactura del SIE (Gestión de Sistema Financiero), descarga con la impresora |
| `bot/liquidacion_datos.py` | Liquidación LMA sin Playwright: lee el Excel, guarda en `worker_datos/liquidacion.db`, arma el JSON (siempre la última prefactura) |
| `bot/historial.db` | SQLite: `registros`, `consultas`, `corridas`, `migraciones` (no versionado) |
| `bot/descargas/soportes/<contrato>/` | Soportes RIPS tal como los entrega el SIE (no versionados) |
| `worker/app.py` | API FastAPI del VPS: cola de consultas, RIPS, datos, usuarios, monitor, duplicados, seguridad |
| `worker/seguridad.py` | Registro de intentos, bloqueos y alertas por correo |
| `api/*.js` | Funciones de Vercel (puente hacia el worker con `WORKER_TOKEN`) |
| `middleware.js` | Exige sesión válida (cookie HMAC) en todo menos login y endpoints con token |
| `index.html`, `login.html` | Tablero y pantalla de ingreso (HTML + JS, sin build) |

## Flujo en el SIE
1. `login.xhtml`: Usuario, Clave y Año Trabajo → Ingresar (hasta 90 s, 3 intentos; si el SIE
   muestra un aviso, p. ej. «usuario inactivo», se copia al error).
2. `pages/audit/reception_consulta_support_rips/reception_consulta_support_rips.xhtml`
   (si falla, por el menú Gestión de Cuentas Médicas → Consulta Recepción).
3. Filtros: Tipo Régimen (RS y RC, siempre los dos), Tipo Contrato = Capita RS / Capita RC,
   Estado = Radicado, Cantidad = 5000, Número Contrato Prestador. Botón `#cmdBuscar`
   (no `cmdGeneralSearch`, que es la búsqueda global).
4. Se lee la tabla (con paginación) y en cada fila se descarga el soporte RIPS
   (`button[title*="soporte de Rips"]`). Si ya existe, no se vuelve a descargar.

Los campos se ubican por el texto de su etiqueta, no por los ids `j_idt…` de PrimeFaces.

## Reglas de negocio
- **Mes de atención** = mes con más fechas en `ARCHIVO-CONSULTAS` del RIPS (si no hay
  consultas, las demás secciones de servicios; nunca USUARIOS ni FACTURAS).
- **Modelo vencido**: mes de cápita = mes de atención + 1. La cápita del primer mes de vigencia
  va con el RIPS en cero (`INICIAL · Cápita inicial`).
- **Tope mensual** = VALOR CONTRATO ÷ meses de vigencia (RS + RC juntos).
- **Desviación** = solo lo radicado por encima del tope + margen aceptable (±10 % por defecto,
  por variación UPC × usuarios). Lo no radicado es saldo, no desviación. > 50 % = atípico.
- **Saldo del contrato** = valor − todo lo radicado; se compara con lo que costarían al tope
  los meses que aún no tienen factura («¿alcanza?»).
- Meses **en plazo** (configurable 1–3 meses) no cuentan como pendientes.
- Radicaciones que dejan de figurar como Radicado en el SIE se marcan **NO VIGENTE** y se excluyen.

## Descarga de RIPS (`GET /rips` del worker)
| Parámetros | Entrega |
|---|---|
| `contrato, anio, mes, regimen, formato, por=capita` | Soportes de la cápita de ese mes |
| `… por=atencion` | Soportes con atenciones de ese mes (excluye los RIPS en cero) |
| `contrato, anio, regimen, formato, meses=7,8,9` | **Unificado**: un solo plano con todas las secciones de esos meses |

TXT = archivo original del SIE (Latin-1, CRLF). JSON = conversión Res. 2275. Más de 4 MB → .zip
(límite de respuesta de Vercel).

## Formato de `dashboard.json`
```json
{
  "generado": "ISO", "version": 1,
  "contratos": [{"contrato","prestador","nit","municipio","inicio","fin","estado_contrato","valor_contrato"}],
  "registros": [{"contrato","recepcion","ips","fecha_recepcion","estado","radicacion","valor","regimen",
                 "periodo_anio","periodo_mes","fecha_min","fecha_max","fuente","primera_vez",
                 "factura","n_usuarios","n_servicios","meses_rips"}],
  "consultas": [{"contrato","anio","mes","regimen","fecha","resultado"}],
  "corridas":  [{"fecha","meses","contratos","radicados","pendientes","errores","novedades"}],
  "ultima": {"fecha","anio","meses","radicados","pendientes","fuera_vigencia","errores","novedades"},
  "no_vigentes": [...]
}
```
No contiene identificaciones de pacientes (solo conteos de usuarios y servicios).
