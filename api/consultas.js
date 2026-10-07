// Puente dashboard → worker del servidor (consultas al SIE).
//   GET  /api/consultas               lista
//   GET  /api/consultas?id=X          detalle (con log)
//   POST /api/consultas               nueva {anio, meses, contratos, catalogo}
//   POST /api/consultas?id=X&accion=cancelar
import { worker } from './_auth.js';
import { requiere } from './_usuarios.js';

export default async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  try {
    const { id, accion } = req.query;
    // ver la lista: cualquier usuario; lanzar o cancelar: permiso consultar_sie
    const ctx = await requiere(req, res, req.method === 'GET' ? null : 'consultar_sie');
    if (!ctx) return;
    let r;
    if (req.method === 'GET') {
      r = await worker(id ? `/consultas/${encodeURIComponent(id)}` : '/consultas?limit=15');
    } else if (req.method === 'POST' && id && accion === 'cancelar') {
      r = await worker(`/consultas/${encodeURIComponent(id)}/cancelar`, { method: 'POST' });
    } else if (req.method === 'POST') {
      const body = typeof req.body === 'string' ? JSON.parse(req.body) : (req.body || {});
      body.usuario = ctx.yo.usuario;
      r = await worker('/consultas', { method: 'POST', body: JSON.stringify(body) });
    } else {
      return res.status(405).json({ error: 'Método no permitido' });
    }
    const texto = await r.text();
    res.status(r.status).setHeader('Content-Type', 'application/json; charset=utf-8');
    return res.send(texto);
  } catch (e) {
    return res.status(502).json({ error: 'El servidor de consultas no respondió: ' + (e.message || e) });
  }
}
