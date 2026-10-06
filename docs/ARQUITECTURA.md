# Arquitectura

## Componentes
| Ruta | Rol |
|---|---|
| `bot/sie_bot.py` | Automatización Playwright del SIE + procesamiento + publicación |
| `bot/historial.db` | SQLite local: `registros`, `consultas` y `corridas` (no versionado) |
| `api/subir.js` | Recibe el JSON del bot y lo guarda en Vercel Blob (privado) |
| `api/datos.js` | Entrega el JSON al dashboard |
| `middleware.js` | Basic Auth con `DASHBOARD_CLAVE` |
| `index.html` | Dashboard (HTML + JS, sin dependencias) |

## Flujo en el SIE
1. `login.xhtml`: Usuario, Clave y Año Trabajo → Ingresar.
2. `pages/audit/reception_consulta_support_rips/reception_consulta_support_rips.xhtml`
   (si falla, se entra por el menú Gestión de Cuentas Médicas → Consulta Recepción).
3. Filtros: Tipo Régimen, Tipo Contrato = Capita, Estado = Radicado, Cantidad = 5000,
   Número Contrato Prestador.
4. Buscar → se lee la tabla (con paginación) y en cada fila se descarga el soporte
   RIPS (columna 4 de íconos).

Los campos se ubican por el texto de su etiqueta, no por los ids `j_idt…` de
PrimeFaces, que cambian.

## Estados en el dashboard (contrato × mes)
| Estado | Regla |
|---|---|
| ✓ Radicado | Hay al menos un registro con periodo de atención en ese mes |
| ✕ Sin radicar | Se consultó ese mes, el contrato estaba vigente y no hay registros |
| ! Error | La consulta de ese contrato falló |
| ? No consultado | Vigente, pero ese mes aún no se ha corrido |
| — Fuera de vigencia | El mes está fuera de INICIO–FIN del contrato |

## Formato del JSON publicado
```json
{
  "generado": "ISO", "version": 1,
  "contratos": [{"contrato","prestador","nit","municipio","inicio","fin","estado_contrato","valor_contrato"}],
  "registros": [{"contrato","recepcion","ips","fecha_recepcion","estado","radicacion","valor",
                 "periodo_anio","periodo_mes","fecha_min","fecha_max","fuente","regimen","primera_vez"}],
  "consultas": [{"contrato","anio","mes","fecha","resultado"}],
  "corridas":  [{"fecha","meses","contratos","radicados","pendientes","errores","novedades"}],
  "ultima": {"fecha","anio","meses","radicados","pendientes","fuera_vigencia","errores","novedades"}
}
```
No contiene identificaciones de pacientes.
