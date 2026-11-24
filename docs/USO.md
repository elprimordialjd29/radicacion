# Uso

## Tablero (https://radicacion.vercel.app)

### Filtros
Año, Régimen, Tipo, Municipio y **Buscar** (prestador, contrato o NIT). Si escribes un número de
contrato completo, o lo eliges en las sugerencias, se muestra **solo ese contrato**; si eliges el
prestador, todos sus contratos. Meses: chips (varios a la vez) o rango **Desde / Hasta**.

### Pestañas del Tablero
| Pestaña | Qué muestra |
|---|---|
| Atenciones por mes (RIPS) | Contrato × **mes de atención** (fechas dentro del RIPS): usuarios RS/RC, descarga TXT/JSON por mes y **Unificado** |
| Pendientes | Contratos con meses vencidos sin RIPS |
| Radicaciones | Cada radicación: recepción, factura, fechas de atención, valor, fuente del periodo |
| Corridas | Historial de consultas al SIE |

Cada celda de Atenciones por mes lleva el nombre del mes arriba. ⏳ = aún en plazo, ✕ = sin RIPS,
— = fuera de vigencia.

### Descarga unificada de varios meses
1. Elige los meses (p. ej. Jul, Ago, Sep o Desde Marzo / Hasta Septiembre).
2. Debajo de cada contrato aparece **⬇ Unificado Jul–Sep** con **RS** y **RC**, cada uno **TXT** y **JSON**.
3. El archivo trae en cada sección (consultas, procedimientos, urgencias, medicamentos, otros
   servicios…) las líneas de **todos** esos meses; usuarios sin repetir; todas las facturas.
   Nombre: `RIPS_<contrato>_atenciones_2026-07_a_2026-09_RS_unificado.txt`. Si pasa de 4 MB baja en .zip.

### Consultar en el SIE
Meses de atención y contratos (filtrados o todos); el régimen es siempre **RS y RC**. La consulta
corre en el servidor (se puede cerrar la página). Si falla, se reintenta sola y se ve como
«reintento automático #N · correrá a las HH:MM». No hace falta lanzarla de nuevo.

### Reporte (permiso «Ver reporte»)
Resumen (valor contratado, radicado RS/RC, sin radicar vencido, radicado de más fuera del margen,
saldo de los contratos y si alcanza), facturas duplicadas, alertas, desviación por prestador o
contrato (ordenable por %, $ o ejecución; filtro de % mínimo), periodos sin radicar y tabla
detallada con saldo. Clic en una fila → detalle mes a mes con gráfica. Descargas en Excel y PDF.

### Frecuencia de uso (permiso «Ver reporte»)
Elige el **tipo de contrato** (o **TODOS (toda la EPS)**), los meses de atención arriba y la vista
**Departamento / Municipio / Contrato**. La última columna es el **Total**. Cada celda: veces que se
reportó y, debajo, pacientes distintos y % del grupo. El selector dice cómo se cuenta cada tipo:

| Tipo | Cómo se cuenta | Grupos |
|---|---|---|
| PMS, RCV | Matriz 3280 (frecuencia de uso, no evaluación): se busca el CUPS de cada actividad; cursos de vida por **edad**; el diagnóstico solo para las rutas **RCV y materna/prenatal**; cada registro cuenta en todos los programas que le apliquen, sin finalidad, sin valor único ni quitar duplicados. Al final, los códigos de PyM que reportan y la matriz no trae | Programas 3280 |
| MD, MDC, MD-RCV | Solo los **medicamentos** (unidades), como la Evaluación Asistencial | Medicamentos |
| ASE, ASB, EB, CMP, PAI | Igual que la Evaluación Cápita Asistencial (mapa CUPS → tipo de servicio; medicamentos y otros servicios por cantidad, sin quitar repetidos) | Tipos de servicio |
| DNT (o un tipo con catálogo cargado) | Catálogo de CUPS y diagnósticos por grupo | Grupos del catálogo |
| TODOS | Todos los códigos de todos los RIPS de la EPS | Tipo de servicio o archivo RIPS |

Solo se muestran las actividades con registros (no salen filas vacías); con «Contar en todos los
pacientes» aparecen también las que solo tienen registros fuera del grupo.
La primera vez de cada tipo se calcula en segundo plano (barra de avance); después abre al instante.
Usa el buscador para encontrar un CUPS o una actividad. ⬇ Excel: una fila por contrato y CUPS/actividad.

**Cargar el catálogo** (administrador): «⬆ Cargar CUPS y diagnósticos» → tipo de contrato y
**📄 Cargar desde Excel** (el archivo con las columnas ACTIVIDAD · DESCRIPCIÓN DEL CUPS · CUPS y, en la
misma hoja o en otra, CIE-10 · GRUPO), o pegar desde Excel: actividades (GRUPO · DESCRIPCIÓN · CUPS; el grupo puede estar en una celda combinada;
varios CUPS en una celda separados por coma o punto y coma) y diagnósticos (CIE-10 · GRUPO, con el
mismo nombre de grupo). Reemplaza el catálogo anterior de ese tipo.

### Servidor (solo administradores)
Memoria, disco, CPU, servicios, cola de consultas, almacenamiento y **Seguridad** (intentos sin
permiso, bloqueos, estado del correo de alertas).

## Bot por línea de comandos

```bash
cd bot
.venv/bin/python sie_bot.py septiembre                  # un mes
.venv/bin/python sie_bot.py agosto septiembre --anio 2026
.venv/bin/python sie_bot.py septiembre --solo PMS-XXXXX-2026-NN   # prueba con 1 contrato
.venv/bin/python sie_bot.py --todos                     # sin filtro de mes
```

| Opción | Qué hace |
|---|---|
| `--regimen RS,RC` | Regímenes a consultar (por defecto los dos) |
| `--tipo Capita` | Tipo Contrato (elige la opción que contiene "Capita", p. ej. "Capita RS") |
| `--contratos RUTA` | Excel o .txt de contratos (por defecto `SIE_CONTRATOS` del `.env`) |
| `--solo C1 C2` | Consultar solo esos contratos |
| `--incluir-fuera-vigencia` | Consulta también contratos que no estaban vigentes en el mes |
| `--sin-soportes` | No descarga soportes (no recomendado; el tablero ya no lo ofrece) |
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
