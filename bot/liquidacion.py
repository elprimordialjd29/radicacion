#!/usr/bin/env python3
"""
SIE Dusakawi — Liquidación LMA (prefacturas de cápita)

Flujo:
  1. Inicia sesión en el SIE igual que sie_bot.py (usuario y clave del .env)
  2. Abre Gestión de Sistema Financiero > Ordenes de Pago > Prefactura
  3. Para cada contrato del listado: Número Contrato → Buscar → lee TODAS las páginas
  4. Cada prefactura que aparece se descarga UNA vez por corrida con el ícono de la impresora
     (Excel «estadistica.xlsx»: una fila por contrato con TOTAL, AFILIADOS y los conceptos).
     Se vuelven a bajar en cada corrida para tener siempre los valores que hoy tiene el SIE.
  5. Guarda todo en worker_datos/liquidacion.db. La pestaña «Liquidación LMA» toma por contrato,
     mes y régimen la ÚLTIMA prefactura que lo trae (consecutivo más alto).
Solo consulta y descarga: no cambia nada en el SIE.

Uso:
  python liquidacion.py --oculto
  python liquidacion.py --solo PMS-44001-2026-30 ASE-47001-2026-37
"""
import argparse
import getpass
import os
import re
import sys
from datetime import datetime

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

import liquidacion_datos as LD
import sie_bot as S

PREF_URL = f"{S.BASE_URL}/pages/sistema_financiero/prefactura/prefactura.xhtml"
MENU_URL = f"{S.BASE_URL}/sistema_financiero.xhtml?URL_ANTERIOR=sistema_financiero"
TABLA = "[id='dtMtto']"
# columnas de la tabla de prefacturas: 4 de íconos (editar, contabilizar, reverso, impresora) y luego
# Consecutivo Prefactura, Descripción, Fecha Inicial, Fecha Final
LEER_JS = r"""
() => {
  const dt = document.querySelector("[id='dtMtto']");
  if (!dt) return null;
  const rows = [...dt.querySelectorAll('tbody > tr')].filter(tr => !tr.classList.contains('ui-datatable-empty-message'))
     .map(tr => [...tr.children].slice(4).map(td => td.innerText.replace(/\s+/g, ' ').trim()));
  const nx = dt.querySelector('.ui-paginator-next');
  return {rows, next: !!nx && !nx.classList.contains('ui-state-disabled')};
}
"""


def ahora():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def abrir_prefactura(page):
    S.log("Abriendo Prefactura…")
    S.ir(page, PREF_URL)
    S.esperar_ajax(page)
    if page.locator(f"xpath={S.xp_label('Número Contrato')}").count() == 0:
        # Plan B: entrar por el menú como lo haría una persona
        S.log("  entrando por el menú Gestión de Sistema Financiero…")
        S.ir(page, MENU_URL)
        S.esperar_ajax(page)
        page.get_by_text("Ordenes de Pago", exact=True).first.click()
        S.esperar_ajax(page)
        page.get_by_text("Prefactura", exact=True).first.click()
        page.wait_for_load_state("domcontentloaded")
        S.esperar_ajax(page)
    S.campo_texto(page, "Número Contrato").wait_for(state="visible", timeout=30000)
    S.log("Prefactura lista ✔")


def descargar(page, i, consecutivo):
    """Clic en la impresora de la fila i (verificando que sea la prefactura pedida) y guarda el Excel."""
    fila = page.locator(f"{TABLA} tbody > tr").nth(i)
    texto = fila.locator("td").nth(4).inner_text(timeout=10000).strip()
    if texto != str(consecutivo):
        raise RuntimeError(f"la fila {i + 1} ya no es la prefactura {consecutivo} (dice {texto})")
    boton = fila.locator("button:has(.fa-print), a:has(.fa-print)").first
    with page.expect_download(timeout=180000) as dl:
        boton.click()
    d = dl.value
    LD.CARPETA.mkdir(parents=True, exist_ok=True)
    tmp = LD.CARPETA / f"{consecutivo}.parcial"
    d.save_as(str(tmp))
    destino = LD.CARPETA / f"{consecutivo}.xlsx"
    tmp.replace(destino)
    S.esperar_ajax(page)
    return destino


def buscar(page, contrato, al_ver, quiere_bajar, al_bajar):
    """Busca el contrato y recorre todas las páginas. Devuelve [(consecutivo, descripción, f. inicial, f. final)].
    Cada fila pasa por `al_ver(...)`; la prefactura que `quiere_bajar(k)` aprueba se descarga y se entrega a
    `al_bajar(k, ruta | None, error)`."""
    campo = S.campo_texto(page, "Número Contrato")
    campo.fill("")
    campo.fill(contrato)
    # OJO: la barra superior tiene otro botón "buscar" (cmdGeneralSearch); el de la página es #cmdBuscar
    page.locator("#cmdBuscar").click()
    S.esperar_ajax(page)
    page.wait_for_timeout(500)
    # PrimeFaces conserva la página del paginador entre búsquedas: volver siempre a la primera
    primero = page.locator(f"{TABLA} .ui-paginator-first")
    if primero.count() and "ui-state-disabled" not in (primero.first.get_attribute("class") or ""):
        primero.first.click()
        S.esperar_ajax(page)
        page.wait_for_timeout(400)
    filas = []
    for _ in range(200):   # páginas
        t = page.evaluate(LEER_JS)
        if t is None:
            raise RuntimeError("no apareció la tabla de prefacturas")
        for i, r in enumerate(t["rows"]):
            if not r or not r[0].isdigit():
                continue
            k = int(r[0])
            fila = (k, r[1] if len(r) > 1 else "", r[2] if len(r) > 2 else "", r[3] if len(r) > 3 else "")
            filas.append(fila)
            al_ver(*fila)
            if quiere_bajar(k):
                try:
                    al_bajar(k, descargar(page, i, k), "")
                except Exception as e:
                    al_bajar(k, None, str(e).splitlines()[0][:160])
        if not t["next"]:
            break
        page.locator(f"{TABLA} .ui-paginator-next").first.click()
        S.esperar_ajax(page)
        page.wait_for_timeout(400)
    return filas


def main():
    load_dotenv(S.BASE / ".env")
    ap = argparse.ArgumentParser(description="Liquidación LMA: prefacturas de cápita del SIE Dusakawi")
    ap.add_argument("--anio", type=int, default=int(os.getenv("SIE_ANIO", datetime.now().year)))
    ap.add_argument("--contratos", default=os.getenv("SIE_CONTRATOS", str(S.BASE / "contratos.xlsx")))
    ap.add_argument("--solo", nargs="*", help="consultar solo estos contratos")
    ap.add_argument("--oculto", action="store_true", help="navegador sin ventana")
    a = ap.parse_args()

    contratos, _meta = S.cargar_contratos(a.contratos)
    todos = list(contratos)
    if a.solo:
        contratos = [c for c in contratos if c in a.solo] or a.solo
    if not contratos:
        sys.exit("El listado de contratos está vacío.")
    usuario = os.getenv("SIE_USUARIO") or input("Usuario SIE: ").strip()
    clave = os.getenv("SIE_CLAVE")
    if not clave:
        if not sys.stdin.isatty():
            sys.exit("ERROR: falta SIE_CLAVE en bot/.env (modo servidor)")
        clave = getpass.getpass("Clave SIE: ")

    S.log(f"Liquidación LMA {a.anio}: {len(contratos)} contratos (se consultan {len(contratos)}) · "
          "régimen subsidiado y contributivo · Prefactura del SIE")
    con = LD.abrir()
    inicio = ahora()
    bajadas, intentos, err_desc = set(), {}, {}   # prefacturas descargadas en ESTA corrida
    vistos, listados, errores = set(), {}, {}

    def al_ver(k, desc, fi, ff):
        LD.registrar(con, k, desc, fi, ff, ahora())
        vistos.add(k)

    def quiere_bajar(k):
        return k not in bajadas and intentos.get(k, 0) < 2

    def al_bajar(k, ruta, error):
        intentos[k] = intentos.get(k, 0) + 1
        if ruta is None:
            err_desc[k] = error
            S.log(f"    prefactura {k}: no se pudo descargar ({error})")
            return
        try:
            conceptos, filas, av = LD.leer_excel(ruta)
            LD.guardar_excel(con, k, conceptos, filas, ahora())
            con.commit()
            bajadas.add(k)
            err_desc.pop(k, None)
            for x in av:
                err_desc.setdefault(f"{k} (aviso)", x)
        except Exception as e:
            err_desc[k] = "Excel ilegible: " + str(e).splitlines()[0][:120]
            S.log(f"    prefactura {k}: {err_desc[k]}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=a.oculto, slow_mo=0 if a.oculto else 60)
        page = browser.new_page(viewport={"width": 1500, "height": 950}, accept_downloads=True)
        page.set_default_timeout(30000)
        page.set_default_navigation_timeout(90000)
        try:
            S.iniciar_sesion(page, usuario, clave, a.anio)
            abrir_prefactura(page)
            for n, c in enumerate(contratos, 1):
                for intento in (1, 2):
                    try:
                        if "login" in page.url:      # la sesión se venció en medio de la corrida
                            S.iniciar_sesion(page, usuario, clave, a.anio)
                            abrir_prefactura(page)
                        antes = len(bajadas)
                        filas = buscar(page, c, al_ver, quiere_bajar, al_bajar)
                        LD.guardar_busqueda(con, c, [f[0] for f in filas], ahora())
                        con.commit()
                        listados[c] = [f[0] for f in filas]
                        nuevas = len(bajadas) - antes
                        S.log(f"[{n}/{len(contratos)}] {c}: {len(filas)} prefacturas"
                              + (f" · {nuevas} descargadas" if nuevas else ""))
                        errores.pop(c, None)
                        break
                    except Exception as e:
                        errores[c] = str(e).splitlines()[0][:150]
                        S.log(f"[{n}/{len(contratos)}] {c}: error ({errores[c]})")
                        S.evidencia(page, f"liq_error_{re.sub(r'[^A-Za-z0-9-]', '_', c)}")
                        if intento == 1:
                            try:
                                abrir_prefactura(page)   # recargar la página y reintentar
                            except Exception:
                                pass
        finally:
            browser.close()

    # prefacturas vistas que no se pudieron descargar: quedan con lo de la última descarga buena
    for k in sorted(vistos - bajadas):
        errores.setdefault(f"Prefactura {k}", "no se pudo descargar: " + str(err_desc.get(k, "sin detalle")))
    completa = not a.solo and not errores and len(listados) == len(todos)
    if completa:
        LD.marcar_vigentes(con, vistos)
    avisos = LD.validar(con, listados, bajadas, todos)
    avisos += [f"Prefactura {k.split()[0]}: {v}" for k, v in err_desc.items() if str(k).endswith("(aviso)")]
    fin = ahora()
    LD.registrar_corrida(con, inicio, fin, len(contratos), len(listados), len(vistos), len(bajadas), errores, avisos, completa)
    con.commit()
    con.close()

    print("\n" + "=" * 60)
    print(f" Contratos consultados   : {len(listados)}/{len(contratos)}")
    print(f" Prefacturas encontradas : {len(vistos)}")
    print(f" Prefacturas descargadas : {len(bajadas)}")
    print(f" Errores                 : {len(errores)}")
    print(f" Avisos para revisar     : {len(avisos)}")
    for k, v in list(errores.items())[:15]:
        print(f"   ✕ {k}: {v}")
    print("=" * 60)
    if not listados:
        sys.exit(1)   # no se pudo consultar nada: el worker la reintenta sola


if __name__ == "__main__":
    main()
