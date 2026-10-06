// Descarga el Excel de una consulta desde el worker.
import { worker } from './_auth.js';

export default async function handler(req, res) {
  try {
    const r = await worker(`/consultas/${encodeURIComponent(req.query.id || '')}/excel`);
    if (!r.ok) return res.status(r.status).json({ error: 'Excel no disponible' });
    const buf = Buffer.from(await r.arrayBuffer());
    res.setHeader('Content-Type', r.headers.get('content-type') || 'application/octet-stream');
    res.setHeader('Content-Disposition', r.headers.get('content-disposition') || 'attachment; filename="radicacion.xlsx"');
    return res.status(200).send(buf);
  } catch (e) {
    return res.status(502).json({ error: String(e.message || e) });
  }
}
