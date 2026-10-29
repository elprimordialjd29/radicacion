// Entrega los datos al dashboard. Protegido por middleware.js (clave).
import { leerServidor } from './_blob.js';

export default async function handler(req, res) {
  try {
    const texto = await leerServidor('/datos');
    if (!texto) return res.status(404).json({ error: 'Aún no hay datos' });
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    return res.status(200).send(texto);
  } catch (e) {
    return res.status(503).json({ error: 'Servidor de datos no disponible por un momento; intenta de nuevo. (' + String(e && e.message || e) + ')' });
  }
}
