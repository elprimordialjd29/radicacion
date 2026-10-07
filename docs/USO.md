# Uso del bot

```bash
cd bot
.venv/bin/python sie_bot.py septiembre                  # un mes
.venv/bin/python sie_bot.py agosto septiembre --anio 2026
.venv/bin/python sie_bot.py septiembre --solo PMS-XXXXX-2026-NN   # prueba con 1 contrato
.venv/bin/python sie_bot.py --todos                     # sin filtro de mes
```

| Opción | Qué hace |
|---|---|
| `--regimen RS` | Tipo Régimen en el SIE (RS por defecto; RC para contributivo) |
| `--tipo Capita` | Tipo Contrato (elige la opción que contiene "Capita", p. ej. "Capita RS") |
| `--contratos RUTA` | Excel o .txt de contratos (por defecto `SIE_CONTRATOS` del `.env`) |
| `--solo C1 C2` | Consultar solo esos contratos |
| `--incluir-fuera-vigencia` | Consulta también contratos que no estaban vigentes en el mes |
| `--sin-soportes` | No descarga soportes; el mes sale de la Fecha Recepción (más rápido) |
| `--por-recepcion` | Filtra por Fecha Recepción aunque se descarguen soportes |
| `--oculto` | Navegador sin ventana |
| `--no-publicar` | No sube nada al dashboard |

## Cómo se decide el periodo (mes de cápita) — modelo VENCIDO

La cápita se radica vencida: **la radicación de cada mes trae el RIPS de las atenciones del
mes anterior** (la de abril trae las de marzo) y **la cápita del primer mes va con el RIPS en
cero**. Por eso:

- Mes de cápita = mes de las atenciones del soporte (ARCHIVO-CONSULTAS) **+ 1**.
- Soporte en cero (solo encabezado de factura) = **primer mes de vigencia** del contrato
  (fuente `INICIAL`); si ese mes ya está ocupado, el mes anterior al primer periodo confirmado,
  y si no, el siguiente libre (fuente `ESTIMADO`).

### Detalle del cálculo de fechas

Se usa el mismo procedimiento que se hace a mano:

1. En cada fila de Consulta Recepción se descarga el **soporte RIPS** (el ícono de la
   hoja, al lado del ojo).
2. Dentro del archivo se buscan las fechas de la sección `ARCHIVO-CONSULTAS`
   (p. ej. `2026-04-21` → **abril 2026**).
3. Si hay fechas de varios meses, gana el mes con más registros y se marca como
   "varios meses".
4. Si no hay consultas, se usan las fechas de las otras secciones (nunca las de FACTURAS).
5. Sin fechas o con error en la descarga → hoja **"Revisar (sin periodo)"**.

Los soportes quedan en `bot/descargas/soportes/<contrato>/` y no se vuelven a descargar.

## Vigencia

Un contrato **no se consulta** para meses anteriores a su INICIO ni posteriores a su
FIN, según el Excel de contratos. Aparece como **FUERA DE VIGENCIA**, no como pendiente.

## Excel generado (`bot/descargas/`)

| Hoja | Contenido |
|---|---|
| Resumen | Contrato × mes: radicados, valor y estado |
| Detalle | Todos los registros del periodo, con fechas de atención |
| Novedades | Lo radicado o cambiado desde la corrida anterior |
| Pendientes | Contratos vigentes sin radicación |
| Revisar (sin periodo) | Soportes sin fecha o con error |

## Si algo falla

El bot guarda una captura y el HTML en `bot/logs/`. Con eso se ajustan los
selectores si el SIE cambia su pantalla.
