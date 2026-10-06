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

## Cómo se decide el periodo (mes)

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
