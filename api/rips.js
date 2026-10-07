// Descarga del RIPS (TXT original del SIE o JSON Res. 2275) de un contrato/mes/régimen.
// Contiene datos de pacientes: solo pasa por aquí, detrás de la clave del dashboard.
import { worker } from './_auth.js';
import { requiere } from './_usuarios.js';

export const config = { maxDuration: 60 };

export default async function handler(req, res) {
  if (!(await requiere(req, res, 'descargar_rips'))) return;
  const { contrato = '', anio = '', mes = '', regimen = '', formato = 'txt', por = 'capita' } = req.query;
  const qs = new URLSearchParams({ contrato, anio, mes, regimen, formato, por });
  try {
    const r = await worker('/rips?' + qs.toString(), { signal: AbortSignal.timeout(55000) });
    if (!r.ok) {
      const t = await r.text();
      let msg = 'RIPS no disponible';
      try { msg = JSON.parse(t).detail || msg; } catch {}
      return res.status(r.status).send(msg);
    }
    const buf = Buffer.from(await r.arrayBuffer());
    res.setHeader('Content-Type', r.headers.get('content-type') || 'application/octet-stream');
    res.setHeader('Content-Disposition', r.headers.get('content-disposition') || 'attachment');
    res.setHeader('Cache-Control', 'no-store');
    return res.status(200).send(buf);
  } catch (e) {
    return res.status(502).send('El servidor de consultas no respondió: ' + (e.message || e));
  }
}
