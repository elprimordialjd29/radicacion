"""
Convierte el "Archivo plano" de RIPS que descarga el SIE Dusakawi a JSON con la
estructura de la Resolución 2275 de 2023 (una factura → usuarios → servicios).

Formato del plano (secciones separadas por "∞---- ARCHIVO-XXX ----∞|"):
  USUARIOS        campos 2275 tal cual (11)
  FACTURAS        numDocumentoIdObligado, numFactura, tipoNota, numNota
  CONSULTAS, PROCEDIMIENTOS, URGENCIAS, MEDICAMENTOS, OTROS:
                  [numFactura, tipoDocUsuario, numDocUsuario] + campos 2275 del servicio
  (cada línea termina en ",|" → el último campo vacío se descarta)

El orden se verificó contra soportes reales (número y forma de cada campo).
URGENCIAS en el SIE no trae fechaInicioAtencion: se deja en null.
Secciones desconocidas (p. ej. RECIEN_NACIDOS) se incluyen en "seccionesSinMapear".
"""
import json
import re
import sys
from pathlib import Path

USUARIO = ["tipoDocumentoIdentificacion", "numDocumentoIdentificacion", "tipoUsuario", "fechaNacimiento",
           "codSexo", "codPaisResidencia", "codMunicipioResidencia", "codZonaTerritorialResidencia",
           "incapacidad", "consecutivo", "codPaisOrigen"]

# (nombre en JSON 2275, campos después del prefijo, índice del campo de texto libre que puede traer comas)
SERVICIOS = {
    "CONSULTAS": ("consultas", [
        "codPrestador", "fechaInicioAtencion", "numAutorizacion", "codConsulta",
        "modalidadGrupoServicioTecSal", "grupoServicios", "codServicio", "finalidadTecnologiaSalud",
        "causaMotivoAtencion", "codDiagnosticoPrincipal", "codDiagnosticoRelacionado1",
        "codDiagnosticoRelacionado2", "codDiagnosticoRelacionado3", "tipoDiagnosticoPrincipal",
        "tipoDocumentoIdentificacion", "numDocumentoIdentificacion", "vrServicio", "conceptoRecaudo",
        "valorPagoModerador", "numFEVPagoModerador", "consecutivo"], None),
    "PROCEDIMIENTOS": ("procedimientos", [
        "codPrestador", "fechaInicioAtencion", "idMIPRES", "numAutorizacion", "codProcedimiento",
        "viaIngresoServicioSalud", "modalidadGrupoServicioTecSal", "grupoServicios", "codServicio",
        "finalidadTecnologiaSalud", "tipoDocumentoIdentificacion", "numDocumentoIdentificacion",
        "codDiagnosticoPrincipal", "codDiagnosticoRelacionado", "codComplicacion", "vrServicio",
        "conceptoRecaudo", "valorPagoModerador", "numFEVPagoModerador", "consecutivo"], None),
    "URGENCIAS": ("urgencias", [
        "codPrestador", "causaMotivoAtencion", "codDiagnosticoPrincipal", "codDiagnosticoPrincipalE",
        "codDiagnosticoRelacionadoE1", "codDiagnosticoRelacionadoE2", "codDiagnosticoRelacionadoE3",
        "condicionDestinoUsuarioEgreso", "codDiagnosticoCausaMuerte", "fechaEgreso", "consecutivo"], None),
    "HOSPITALIZACION": ("hospitalizacion", [
        "codPrestador", "viaIngresoServicioSalud", "fechaInicioAtencion", "numAutorizacion",
        "causaMotivoAtencion", "codDiagnosticoPrincipal", "codDiagnosticoPrincipalE",
        "codDiagnosticoRelacionadoE1", "codDiagnosticoRelacionadoE2", "codDiagnosticoRelacionadoE3",
        "codComplicacion", "condicionDestinoUsuarioEgreso", "codDiagnosticoCausaMuerte", "fechaEgreso",
        "consecutivo"], None),
    "MEDICAMENTOS": ("medicamentos", [
        "codPrestador", "numAutorizacion", "idMIPRES", "fechaDispensAdmon", "codDiagnosticoPrincipal",
        "codDiagnosticoRelacionado", "tipoMedicamento", "codTecnologiaSalud", "nomTecnologiaSalud",
        "concentracionMedicamento", "unidadMedida", "formaFarmaceutica", "unidadMinDispensa",
        "cantidadMedicamento", "diasTratamiento", "tipoDocumentoIdentificacion",
        "numDocumentoIdentificacion", "vrUnitMedicamento", "vrServicio", "conceptoRecaudo",
        "valorPagoModerador", "numFEVPagoModerador", "consecutivo"], "nomTecnologiaSalud"),
    "OTROS": ("otrosServicios", [
        "codPrestador", "numAutorizacion", "idMIPRES", "fechaSuministroTecnologia", "tipoOS",
        "codTecnologiaSalud", "nomTecnologiaSalud", "cantidadOS", "tipoDocumentoIdentificacion",
        "numDocumentoIdentificacion", "vrUnitOS", "vrServicio", "conceptoRecaudo", "valorPagoModerador",
        "numFEVPagoModerador", "consecutivo"], "nomTecnologiaSalud"),
}
ORDEN_SERVICIOS = ["consultas", "procedimientos", "urgencias", "hospitalizacion", "recienNacidos",
                   "medicamentos", "otrosServicios"]
NUMERICOS = {"consecutivo", "vrServicio", "valorPagoModerador", "vrUnitMedicamento", "vrUnitOS",
             "cantidadMedicamento", "diasTratamiento", "cantidadOS", "concentracionMedicamento",
             "unidadMedida", "unidadMinDispensa"}


def _num(v):
    try:
        f = float(v)
        return int(f) if f.is_integer() else f
    except (TypeError, ValueError):
        return v


def _valor(campo, v):
    v = (v or "").strip()
    if v == "":
        return None
    return _num(v) if campo in NUMERICOS else v


def _campos(linea):
    linea = linea.strip()
    if linea.endswith("|"):
        linea = linea[:-1]
    partes = linea.split(",")
    if partes and partes[-1] == "":  # coma final antes de "|"
        partes = partes[:-1]
    return partes


def _ajustar(partes, n, campo_texto, nombres):
    """Si un texto libre trae comas, hay campos de más: se reúnen en ese campo."""
    if len(partes) <= n or not campo_texto:
        return (partes + [""] * n)[:n]
    i = nombres.index(campo_texto)
    extra = len(partes) - n
    return partes[:i] + [",".join(partes[i:i + extra + 1])] + partes[i + extra + 1:]


def leer_plano(texto):
    secciones, actual = {}, None
    for linea in texto.splitlines():
        m = re.search(r"ARCHIVO-([A-Za-z_]+)", linea)
        if m:
            actual = m.group(1).upper()
            secciones.setdefault(actual, [])
            continue
        s = linea.strip()
        if not actual or not s or s == "|" or set(s) <= set("*|") or "FACTURAS*" in s:
            continue
        secciones[actual].append(s)
    return secciones


def a_json(texto):
    """Devuelve una lista de objetos RIPS 2275 (uno por factura)."""
    sec = leer_plano(texto)
    usuarios = {}
    for l in sec.get("USUARIOS", []):
        u = {k: _valor(k, v) for k, v in zip(USUARIO, (_campos(l) + [""] * 11)[:11])}
        usuarios[(u["tipoDocumentoIdentificacion"], u["numDocumentoIdentificacion"])] = u

    facturas = {}
    for l in sec.get("FACTURAS", []):
        c = (_campos(l) + [""] * 4)[:4]
        facturas[c[1]] = {"numDocumentoIdObligado": c[0] or None, "numFactura": c[1] or None,
                          "tipoNota": c[2] or None, "numNota": c[3] or None}

    # servicios agrupados por factura → usuario
    por_factura = {}
    for clave, (nombre, campos, campo_texto) in SERVICIOS.items():
        n = 3 + len(campos)
        for l in sec.get(clave, []):
            partes = _ajustar(_campos(l), n, campo_texto, ["_f", "_t", "_d"] + campos)
            fac, tdoc, ndoc = partes[0], partes[1], partes[2]
            reg = {k: _valor(k, v) for k, v in zip(campos, partes[3:])}
            if clave == "URGENCIAS":
                reg = {"codPrestador": reg.pop("codPrestador"), "fechaInicioAtencion": None, **reg}
            por_factura.setdefault(fac, {}).setdefault((tdoc, ndoc), {}).setdefault(nombre, []).append(reg)

    salida = []
    for fac in list(facturas) or list(por_factura):
        obj = dict(facturas.get(fac) or {"numDocumentoIdObligado": None, "numFactura": fac,
                                          "tipoNota": None, "numNota": None})
        lista = []
        for (tdoc, ndoc), servs in por_factura.get(fac, {}).items():
            u = dict(usuarios.get((tdoc, ndoc)) or {"tipoDocumentoIdentificacion": tdoc,
                                                    "numDocumentoIdentificacion": ndoc})
            u["servicios"] = {k: servs[k] for k in ORDEN_SERVICIOS if k in servs}
            lista.append(u)
        obj["usuarios"] = lista
        salida.append(obj)

    sin_mapear = {k: v for k, v in sec.items() if k not in SERVICIOS and k not in ("USUARIOS", "FACTURAS")}
    if sin_mapear and salida:
        salida[0]["seccionesSinMapear"] = {k: [_campos(l) for l in v] for k, v in sin_mapear.items()}
    return salida


def leer_archivo(ruta):
    b = Path(ruta).read_bytes()
    for enc in ("utf-8", "latin-1"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("latin-1", "replace")


def convertir(ruta):
    """JSON (texto) de un archivo plano: objeto si hay una factura, lista si hay varias."""
    datos = a_json(leer_archivo(ruta))
    return json.dumps(datos[0] if len(datos) == 1 else datos, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    print(convertir(sys.argv[1]))
