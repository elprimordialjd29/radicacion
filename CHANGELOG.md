# Changelog

## 0.14.3 — 2026-11-24
- Frecuencia de uso: el **periodo** del Excel (fila «Periodo», nombre del archivo) y de la pantalla es el de
  los meses de atención que **sí tienen RIPS radicados**, no «todos los meses»: p. ej. «marzo a septiembre de
  2026 (meses de atención con RIPS radicados)»; si hay huecos, «marzo a mayo y julio de 2026». El servidor
  devuelve `meses_datos` en `/frecuencia`.

## 0.14.2 — 2026-11-24
- Excel de frecuencia **solo con la cantidad de actividades** (frecuencia de uso): se quitan «Pacientes con
  este servicio» / «Pacientes del programa» (base del %), «Pacientes que lo recibieron» y el %, que no se
  entendían. Queda: ubicación · contrato · prestador · modalidad · programa o tipo de servicio · actividad ·
  CUPS · **Veces** (Unidades en medicamentos). La fila «Cómo leer» del encabezado lo explica. DNT no cambia.

## 0.14.1 — 2026-11-24
- **Excel de frecuencia con la modalidad en cada fila**: con «Todas las modalidades», cada actividad de cada
  contrato sale en una fila por modalidad (Intramural, Extramural jornada de salud, unidad móvil,
  domiciliaria, Telemedicina…) con sus veces, pacientes y %; lo que el RIPS no trae con modalidad
  (medicamentos y otros servicios) va en la fila «Sin modalidad (medicamentos y otros servicios)». La suma
  de las filas da el total de la pantalla (PMS: 3.080.197).
- Columna más clara: «Pacientes con este servicio» ahora es **«Pacientes atendidos en el tipo de
  servicio»** (pacientes distintos con cualquier servicio de ese tipo: la base del %, por eso se repite en
  los códigos del mismo tipo); en 3280, «Pacientes del programa». El % lleva el mismo nombre de su base y
  el encabezado del Excel trae una fila «Cómo leer» que explica cada columna.

## 0.14.0 — 2026-11-24
- **Modalidad de realización** en la frecuencia de uso (PMS, RCV, asistenciales y TODOS), del campo
  `modalidadGrupoServicioTecSal` de consultas y procedimientos, siempre con su **descripción**:
  Intramural, Extramural unidad móvil, Extramural domiciliaria, Extramural jornada de salud,
  Telemedicina interactiva, no interactiva, telexperticia y telemonitoreo.
  - Debajo de cada actividad, en gris, cuántas veces se hizo en cada modalidad (total).
  - Selector «Todas las modalidades / …» para ver solo una; el Excel trae la columna «Modalidad» y el
    nombre del archivo la incluye. Medicamentos y otros servicios no traen modalidad en el RIPS.
- TODOS: el grupo aparte ahora se llama **«CUPS SIN CLASIFICAR · Consultas / Procedimientos / Otros
  servicios»** y sus nombres salen de la **tabla oficial CUPS de SISPRO** (CUPSRips, consultada el
  2026-11-24; `worker/config/cups_nombres_web.json`, 379 CUPS). Los 24 códigos que no existen en esa
  tabla (p. ej. 123456, 039145, 089020) dicen «Código que no existe en la tabla CUPS (SISPRO)».
  Los clasificados siguen con los nombres de las matrices.

## 0.13.3 — 2026-11-24
- **Frecuencia de uso TODOS (toda la EPS) clasificada solo con las matrices** (sin buscar afuera): cada
  código va a su **tipo de servicio de la Evaluación Asistencial** (asistencias, especialidades,
  complementarias —laboratorio, imágenes—, cada vacuna PAI, TAB, urgencias, hospitalización,
  medicamentos), si no a su **área de la matriz 3280** (cursos de vida, materna, RCV, demanda inducida
  y salud mental) y si no al **catálogo cargado** (DNT…), con el nombre que trae esa matriz. Lo que no
  está en ninguna queda **aparte**, al final: «FUERA DE LAS MATRICES · Consultas / Procedimientos /
  Otros servicios».
- Nombres sin hueco: «Sin nombre en las matrices», «Medicamento sin nombre en el RIPS» y los registros de
  urgencias y hospitalización con su nombre.

## 0.13.2 — 2026-11-24
- Frecuencia de uso asistencial (ASE, ASB, EB, CMP, PAI), medicamentos y TODOS: **las descripciones ya no
  salen en blanco**. El RIPS no trae el nombre de consultas ni procedimientos; ahora se toma del nuevo
  `worker/config/cups_nombres.json` (439 CUPS con su nombre oficial, sacados de los archivos de la EPS
  «VALORES POR SERVICIO Y CUPS» y «CAPITA DE RECUPERACION DE LA SALUD»; vacunas PAI y traslados por su
  tipo de servicio). Orden: nombre oficial del CUPS → nombre que trae el RIPS → descripción 3280 → «Sin
  nombre en el catálogo de CUPS». Ej.: 890101 «ATENCION (VISITA) DOMICILIARIA, POR MEDICINA GENERAL»,
  890401 «INTERCONSULTA POR MEDICINA GENERAL», 890301 «CONSULTA DE CONTROL O DE SEGUIMIENTO POR MEDICINA
  GENERAL». La matriz 3280 no cambia.

## 0.13.1 — 2026-11-24
- **Frecuencia de uso: que crucen todas las actividades.** La copia de la matriz 3280 traía CUPS que
  ningún prestador reporta (glicemia 903901/904332, colesterol 903902…, citología 910101…, 59
  actividades). Se corrigen en `worker/config/res3280_correcciones.json` con las fórmulas del Excel de
  la matriz y los códigos que sí vienen en los RIPS de la EPS (verificados con conteos: % embarazadas,
  % RCV, sexo y edad). La copia del evaluador no se toca. De 389 actividades por programa solo quedan
  sin registros en toda la EPS las de especialistas que no se reportan en cápita (cardiología,
  endocrinología, nefrología, oftalmología, ecocardiograma).
- Variantes de código unidas: `*PYM02RIA-37`, `PYM02R`, `PYM02RIAS`, `PYMRIA04` → PYMxxRIA (asesorías
  VIH, preservativos, mama, próstata); `*DI0001-1` → DI0001-1; `9062491` → 906249.
- **Demanda inducida completa**: cada curso de vida con sus 6 subcódigos (DI0001-1…6, …, DI0006-1…6) y
  el código sin subcódigo; DI0007, DI0008, DI0009 (incl. educación familiar DI0009-1) y DI00011 con
  todos los subcódigos que reportan. Salud mental con I11412 (estilos de vida saludable) y los PM
  (PM00011, PM00012, PM00013, PM0009). PyM con autoexamen de mama (PYM05RIA) y solicitud de mamografía
  (PYM07RIA); RCV con relación proteinuria/creatinuria (PYM00RIA).
- Grupo final **«OTROS CÓDIGOS DE PyM REPORTADOS (no están en la matriz 3280)»**: los DI/PM/PYM/I1 que
  vienen en los RIPS y no tienen actividad, para que no se pierda ninguno.
- **Agrupación (reglas del usuario: es frecuencia de uso, no evaluación)**: cursos de vida solo por
  **edad** (antes Z108 metía al paciente en jóvenes, adultez y vejez a la vez); el diagnóstico solo arma
  las rutas **RCV y materna/prenatal**; cada registro cuenta en todos los programas que le apliquen,
  **sin finalidad, sin valor único y sin quitar duplicados**. DM + HTA = pacientes con las dos. IVE
  (O04), parto (O60–O84, Z37, Z38, P) y posparto (Z39, O85–O92, Z38, P) por su propio diagnóstico, para
  que no repitan a todas las embarazadas.
- **Contratos de medicamentos (MD, MDC, MD-RCV): solo medicamentos**, en unidades.
- Medicamentos de la forma asistencial: se cuentan también los repetidos (mismo paciente, código y
  fecha).
- **Sin filas vacías**: en pantalla y en Excel solo salen las actividades con registros en lo que se
  está viendo (DNT sigue igual).
- El tipo «MD» ya no incluye los contratos «MD-RCV» (mismo tipo que en pantalla).

## 0.13.0 — 2026-11-24
- **Frecuencia de uso para todos los tipos de contrato** y opción **TODOS (toda la EPS)**. Cada tipo se
  cuenta como en su aplicación:
  - **PMS y RCV (incl. MD-RCV): matriz 3280**, versión sencilla pedida por el usuario: los 25 programas
    y 156 actividades de `res3280_cups.json` (copia del evaluador 3280); cada registro con un CUPS de la
    actividad (o el nombre del medicamento) cuenta en los pacientes del programa —curso de vida por edad a
    la última atención del mes y rutas por diagnóstico (embarazo, DM, HTA…)—, **sin finalidad ni valor
    único**. Opción «Contar en todos los pacientes».
  - **ASE, ASB, EB, MD, MDC, CMP, PAI: Evaluación Cápita Asistencial**: el mismo mapa CUPS → tipo de
    servicio (`asistencial_cups.json`, copia de la app) y las mismas reglas de lectura del TXT
    (medicamentos y otros servicios por cantidad, urgencias, traslados).
  - **DNT**: su catálogo de CUPS y diagnósticos (sin cambios).
  - **TODOS**: todos los códigos reportados en los RIPS de la EPS, por tipo de servicio o, si no está en
    el mapa, por el archivo RIPS.
- Cálculo **en segundo plano** (proceso aparte) con barra de avance; cada RIPS se resume una vez y cada
  contrato queda en caché (`worker_datos/frecuencia_cache/`). Al terminar cada consulta al SIE y al
  arrancar el worker se precalcula lo que cambió.
- Pantalla: selector con el tipo y su forma de contar, buscador de CUPS/actividad, columnas según el
  tipo (programa, tipo de servicio, archivo RIPS). Excel en formato lista para todos los tipos.
- Departamento también para contratos con prefijo doble (MD-RCV).

## 0.12.11 — 2026-11-24
- Excel de frecuencia de uso: vuelve el **bloque de datos del reporte arriba de cada hoja** (título,
  periodo, régimen, margen, plazo, corte de datos, generado por y fuente), como en la primera versión;
  la tabla empieza en la fila 10 con sus filtros y queda fija al desplazarse.

## 0.12.10 — 2026-11-24
- Excel de frecuencia de uso: solo filas de contratos (sin filas «TOTAL / TODOS LOS PRESTADORES»).
  Cada niño se cuenta dentro de su contrato, así que la suma de los contratos da el total
  (verificado: 55 de 55 CUPS y diagnósticos cuadran). En pantalla se mantiene la columna Total.

## 0.12.9 — 2026-11-24
- Excel de frecuencia de uso sin columnas repetidas: un solo juego de cifras (Veces, Niños que lo
  recibieron, % del grupo), el mismo de la pantalla; si está marcado «Contar en todos los pacientes»
  el Excel trae esas cifras (y lo dice en el nombre del archivo). Se quitaron «Veces (todos)» y
  «Pacientes (todos)», que repetían lo mismo en cada grupo. Columnas ordenadas: ubicación · contrato ·
  prestador · grupo · DX · niños en el grupo · actividad · CUPS · cifras.

## 0.12.8 — 2026-11-24
- Excel de frecuencia de uso simplificado: solo hojas **Frecuencia CUPS** y **Diagnósticos**; sin columna
  «Nivel» ni filas de municipio/departamento (se filtran por sus columnas); una fila por contrato y al
  final las filas del **TOTAL** en negrilla. Se quitaron las hojas Resumen e Info.

## 0.12.7 — 2026-11-24
- Excel de frecuencia de uso: **encabezado fijo** (la fila 1 queda visible al desplazarse), en negrilla
  con fondo azul y filtros; los nombres de los **prestadores** también en las filas de municipio,
  departamento y total. Se genera con ExcelJS (cdnjs, se carga solo al descargar).

## 0.12.6 — 2026-11-24
- Excel de frecuencia de uso rehecho en **formato lista**: una fila por contrato × CUPS (y por
  municipio, departamento y total, con la columna Nivel), columnas fijas (departamento, municipio,
  contrato, prestador, grupo, actividad, CUPS, DX, niños del grupo, veces, niños, % del grupo, veces y
  pacientes en todos), encabezado en la fila 1 con **filtros**. Hojas: Frecuencia CUPS, Diagnósticos,
  Resumen e Info (datos del reporte y cómo leerlo).

## 0.12.5 — 2026-11-24
- Frecuencia de uso: la columna **Total** pasa al final; cada columna de contrato muestra número de
  contrato, prestador, **municipio y departamento** (y la de municipio, su departamento). El Excel
  también deja el total al final y agrega municipio y departamento en la hoja Resumen.

## 0.12.4 — 2026-11-23
- Frecuencia de uso: si se busca un prestador o contrato, se muestra **solo su valor** (sin la columna
  del total de todos los contratos) y las tarjetas de arriba son de lo buscado; sin búsqueda se ve el
  total y la columna por departamento, municipio o contrato.

## 0.12.3 — 2026-11-20
- Frecuencia de uso más clara: columna **DX que corresponde** al lado de cada CUPS (diagnósticos de su
  grupo); cabecera de cada grupo con «niños en este grupo», sus diagnósticos y color por severidad
  (riesgo, moderada, severa); cada celda muestra veces, niños y **% del grupo** con barra; recuadro
  «Cómo leer»; columna total resaltada de forma uniforme. El Excel incluye la columna DX.

## 0.12.2 — 2026-11-20
- Frecuencia de uso: **cargar el catálogo desde un archivo Excel** (.xlsx/.xls/.csv) en «⬆ Cargar CUPS
  y diagnósticos». Se lee en el navegador: busca la fila de encabezado con ACTIVIDAD (o GRUPO) ·
  DESCRIPCIÓN DEL CUPS · CUPS (aunque haya títulos arriba o columnas de más), rellena los grupos de
  celdas combinadas y toma los diagnósticos (CIE-10 · GRUPO) de cualquier hoja. Llena los campos
  para revisarlos antes de guardar.

## 0.12.1 — 2026-11-20
- **Por grupo** (p. ej. riesgo de desnutrición, aguda moderada, aguda severa): el catálogo se pega con
  tres columnas GRUPO · DESCRIPCIÓN · CUPS (celdas combinadas de Excel se rellenan hacia abajo) y los
  diagnósticos con su grupo; cada CUPS de un grupo se cuenta en los pacientes con diagnóstico de ese
  grupo (la clasificación es por mes: si en un mes un paciente tiene varios grupos, queda en el más severo). Opción «Contar en
  todos los pacientes».

## 0.12.0 — 2026-11-20
- **Frecuencia de uso** (nueva pestaña, permiso «Ver reporte»): cuántas veces se reportó cada CUPS
  en los RIPS (consultas, procedimientos, medicamentos y otros servicios) y cuántos pacientes
  distintos, por **total del tipo de contrato** (p. ej. todos los DNT), **departamento**,
  **municipio** y **contrato**. - Tabla de **diagnósticos** (CIE-10, principal o relacionados) agrupados (riesgo, aguda moderada,
  aguda severa…): pacientes y atenciones.
- **Catálogo por tipo de contrato** (DNT, PMS, ASE…): el administrador pega desde Excel las
  columnas DESCRIPCIÓN · CUPS (varios CUPS por celda) y CIE-10 · GRUPO. Actividades sin código se
  listan aparte. Excel con hojas CUPS, Diagnósticos y Resumen.
- Usa los meses de atención y el régimen elegidos arriba; la búsqueda de prestador/contrato limita
  las columnas. Cada RIPS se lee una sola vez y queda en caché (`worker_datos/frecuencia_cache/`).
  Departamento = código DIVIPOLA del número de contrato (20 Cesar, 44 La Guajira, 47 Magdalena…).

## 0.11.0 — 2026-11-17
- **Descarga RIPS unificada**: al elegir varios meses (p. ej. Jul–Sep o Mar–Sep) aparece, debajo
  de cada contrato, «⬇ Unificado» con TXT y JSON por régimen. Un solo archivo con las
  atenciones de todos esos meses: cada sección (consultas, procedimientos, urgencias,
  medicamentos, otros servicios…) trae las líneas de todos los meses; usuarios sin repetir;
  todas las facturas. Mismo formato y codificación del SIE (unir un solo mes da el archivo
  original byte por byte). Solo descarga: los soportes guardados no se modifican.
  Más de 4 MB → se entrega en .zip. (`rips_json.unir_planos`, worker `/rips?meses=`.)
- **Reintentos automáticos**: si una consulta al SIE falla se vuelve a poner en cola sola
  (5, 10, 20, 30 min y luego cada hora; hasta 10 intentos); se omite si otra igual ya terminó
  bien. Correo de aviso si el SIE no deja iniciar sesión o si se agotan los intentos.
- **SIE lento**: páginas con 90 s de espera y 3 intentos; el clic en «Ingresar» ya no espera
  la navegación (causaba «Locator.click: Timeout 30000ms»); el ingreso se reintenta 3 veces.
  El error muestra el aviso del SIE (p. ej. «El usuario ingresado se encuentra inactivo»).
- **Régimen fijo**: las consultas siempre incluyen RS y RC (tablero y servidor).
- Atenciones por mes: el nombre del mes aparece dentro de cada celda; buscar un número de
  contrato exacto (o elegirlo en las sugerencias) muestra solo ese contrato.

## 0.10.0 — 2026-10-29
- **Datos y usuarios en el servidor**: Vercel Blob (plan Hobby) se suspendió por exceder la
  cuota de operaciones. Ahora el tablero lee los datos (`bot/descargas/dashboard.json`) y los
  usuarios (`bot/worker_datos/usuarios.json`) del worker del VPS; ya no se usa Blob.
- **Seguridad**: bloqueo de 15 min tras 5 claves erradas del mismo usuario o 10 desde la
  misma IP; registro de intentos sin permiso (clave errada, token inválido en la API o
  directo al servidor, permiso negado, admin desde IP nueva) en Servidor → Seguridad;
  alertas por correo (`deploy/configurar_alertas.py`); las sesiones se cierran al cambiar la
  clave, desactivar el usuario o cambiar sus permisos; cabeceras CSP, HSTS, nosniff,
  Referrer-Policy y Permissions-Policy.
- Lecturas tolerantes a fallas pasajeras (reintentos y última copia buena) en Vercel y en el
  tablero («Reconectando…» en vez de error).
- Roles nuevos: «Descarga RIPS (solo tablero)» y «Reporte (ver y descargar)».
- `api/rips-ext` (evaluador externo) entrega por defecto el RIPS por **mes de atención**
  (antes daba la cápita inicial en cero para el primer mes).
- Atenciones por mes: solo las columnas de los meses filtrados, contratos con RIPS primero y
  aviso corto cuando un mes elegido aún está en plazo.
- Se retiró el modo «rápido» (sin soportes): siempre se descargan los soportes RIPS.

## 0.9.0 — 2026-10-15
- **Resumen del reporte**: valor contratado, radicado (RS/RC), sin radicar vencido, radicado de
  más fuera del margen (facturas y contratos por régimen) y **saldo de los contratos** con
  «¿alcanza para los meses que faltan?»; barra con meses radicados, vencidos, en plazo y por
  venir. Saldo también por prestador, por contrato, en el detalle y en los Excel.
- Desviación por prestador/contrato: columnas ordenables (Desv. %, Desviación $, Ejecución),
  ranking, barra por %, filtro de % mínimo; la relación de contratos en Excel respeta el orden.
- Tablero por **mes de atención** (gráfica e indicadores coinciden con la tabla RIPS); meses en
  plazo muestran el % parcial recibido.
- Horas con zona horaria (sin duraciones negativas); el worker cierra siempre las conexiones
  SQLite (una fuga agotaba los 1024 archivos y dejaba el tablero con error).

## 0.8.1 — 2026-10-07
- **Validación factura (SIE) vs RIPS** en cada radicación: número de factura del RIPS, valor de
  la factura, fechas de las atenciones, usuarios y servicios; ✓ si las atenciones son del mes
  anterior a la cápita, ⚠ si son de otro mes, de varios meses o si el RIPS viene en cero fuera
  del primer mes. También en el Excel (columnas «Facturas vs RIPS» y «Validación»).
- `bot/completar_rips.py`: completa esos datos en el historial desde los soportes ya descargados.

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
