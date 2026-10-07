// Facturas duplicadas o sospechosas.
//   GET /api/duplicados          → resumen y pares (permiso ver_reporte)
//   GET /api/duplicados?excel=1  → Excel con detalle de servicios repetidos (datos de pacientes:
//                                  permiso descargar_rips)
import { worker } from './_auth.js';
import { requiere } from './_usuarios.js';

export const config = { maxDuration: 60 };

export default async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  const excel = req.query.excel === '1';
  if (!(await requiere(req, res, excel ? 'descargar_rips' : 'ver_reporte'))) return;
  try {
    const r = await worker(excel ? '/duplicados/excel' : '/duplicados', { signal: AbortSignal.timeout(55000) });
    if (!excel) {
      return res.status(r.status).setHeader('Content-Type', 'application/json; charset=utf-8').send(await r.text());
    }
    if (!r.ok) return res.status(r.status).json({ error: 'No se pudo generar el Excel' });
    res.setHeader('Content-Type', r.headers.get('content-type') || 'application/octet-stream');
    res.setHeader('Content-Disposition', r.headers.get('content-disposition') || 'attachment; filename="Facturas_duplicadas.xlsx"');
    return res.status(200).send(Buffer.from(await r.arrayBuffer()));
  } catch (e) {
    return res.status(502).json({ error: 'El servidor no respondió: ' + (e.message || e) });
  }
}
