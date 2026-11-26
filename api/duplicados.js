// Análisis sobre los RIPS (una sola función por el límite de 12 del plan Hobby):
//   GET /api/duplicados               → facturas duplicadas: resumen y pares (permiso ver_reporte)
//   GET /api/duplicados?excel=1       → Excel con detalle de servicios repetidos (datos de pacientes:
//                                        permiso descargar_rips)
//   GET /api/frecuencia?tipo&anio&meses&regimen&modalidad → frecuencia de uso de CUPS y diagnósticos (ver_reporte)
//   GET /api/frecuencia-cursos?tipo&anio&meses&regimen → hoja de curso de vida y oportunidad (ver_reporte)
//   GET /api/frecuencia-catalogo      → catálogos de CUPS/diagnósticos por tipo de contrato (ver_reporte)
//   PUT /api/frecuencia-catalogo?tipo=DNT {actividades, diagnosticos} → cargar catálogo (admin_usuarios)
//   GET  /api/liquidacion?anio        → liquidación LMA por contrato, régimen y mes (ver_reporte)
//   POST /api/liquidacion {anio, contratos} → actualizar desde el SIE: pone en cola el bot de prefacturas (consultar_sie)
// (vercel.json reescribe /api/frecuencia, /api/frecuencia-catalogo y /api/liquidacion hacia aquí con ?accion=…)
import { worker } from './_auth.js';
import { requiere } from './_usuarios.js';

export const config = { maxDuration: 60 };

const json = (res, r, t) => res.status(r.status).setHeader('Content-Type', 'application/json; charset=utf-8').send(t);

async function frecuencia(req, res) {
  if (!(await requiere(req, res, 'ver_reporte'))) return;
  const { tipo = '', anio = '', meses = '', regimen = '', modalidad = '' } = req.query;
  const r = await worker('/frecuencia?' + new URLSearchParams({ tipo, anio, meses, regimen, modalidad }), { signal: AbortSignal.timeout(55000) });
  return json(res, r, await r.text());
}

// hoja de curso de vida y oportunidad del Excel de frecuencia
async function cursos(req, res) {
  if (!(await requiere(req, res, 'ver_reporte'))) return;
  const { tipo = '', anio = '', meses = '', regimen = '' } = req.query;
  const r = await worker('/frecuencia/cursos?' + new URLSearchParams({ tipo, anio, meses, regimen }), { signal: AbortSignal.timeout(55000) });
  return json(res, r, await r.text());
}

async function catalogo(req, res) {
  if (req.method === 'PUT') {
    const ctx = await requiere(req, res, 'admin_usuarios');
    if (!ctx) return;
    const body = typeof req.body === 'string' ? JSON.parse(req.body || '{}') : (req.body || {});
    const tipo = String(req.query.tipo || '').replace(/[^A-Za-z]/g, '').slice(0, 6);
    const r = await worker(`/frecuencia/catalogo/${tipo}`, {
      method: 'PUT', body: JSON.stringify({ actividades: body.actividades || '', diagnosticos: body.diagnosticos || '', usuario: ctx.yo.usuario }),
    });
    return json(res, r, await r.text());
  }
  if (!(await requiere(req, res, 'ver_reporte'))) return;
  const r = await worker('/frecuencia/catalogo');
  return json(res, r, await r.text());
}

// liquidación LMA: prefacturas de cápita del SIE (la última por contrato, mes y régimen)
async function liquidacion(req, res) {
  if (req.method === 'POST') {
    const ctx = await requiere(req, res, 'consultar_sie');
    if (!ctx) return;
    const body = typeof req.body === 'string' ? JSON.parse(req.body || '{}') : (req.body || {});
    const contratos = Array.isArray(body.contratos) ? body.contratos.map(String).slice(0, 1000) : [];
    const r = await worker('/liquidacion/actualizar', {
      method: 'POST', body: JSON.stringify({ anio: +body.anio || new Date().getFullYear(), contratos, usuario: ctx.yo.usuario }),
    });
    return json(res, r, await r.text());
  }
  if (!(await requiere(req, res, 'ver_reporte'))) return;
  const anio = String(req.query.anio || new Date().getFullYear()).replace(/\D/g, '').slice(0, 4);
  const r = await worker('/liquidacion?' + new URLSearchParams({ anio }), { signal: AbortSignal.timeout(55000) });
  return json(res, r, await r.text());
}

export default async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  try {
    if (req.query.accion === 'frecuencia') return await frecuencia(req, res);
    if (req.query.accion === 'catalogo') return await catalogo(req, res);
    if (req.query.accion === 'cursos') return await cursos(req, res);
    if (req.query.accion === 'liquidacion') return await liquidacion(req, res);
    const excel = req.query.excel === '1';
    if (!(await requiere(req, res, excel ? 'descargar_rips' : 'ver_reporte'))) return;
    const r = await worker(excel ? '/duplicados/excel' : '/duplicados', { signal: AbortSignal.timeout(55000) });
    if (!excel) return json(res, r, await r.text());
    if (!r.ok) return res.status(r.status).json({ error: 'No se pudo generar el Excel' });
    res.setHeader('Content-Type', r.headers.get('content-type') || 'application/octet-stream');
    res.setHeader('Content-Disposition', r.headers.get('content-disposition') || 'attachment; filename="Facturas_duplicadas.xlsx"');
    return res.status(200).send(Buffer.from(await r.arrayBuffer()));
  } catch (e) {
    return res.status(502).json({ error: 'El servidor no respondió: ' + (e.message || e) });
  }
}
