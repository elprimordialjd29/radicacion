// Entrega los datos al dashboard. Protegido por middleware.js (clave).
import { get } from '@vercel/blob';

export default async function handler(req, res) {
  try {
    const r = await get('radicacion/datos.json', { access: 'private', useCache: false });
    if (!r || r.statusCode !== 200) return res.status(404).json({ error: 'Aún no hay datos' });
    const texto = await new Response(r.stream).text();
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    return res.status(200).send(texto);
  } catch (e) {
    if (e && e.name === 'BlobNotFoundError') return res.status(404).json({ error: 'Aún no hay datos' });
    return res.status(500).json({ error: String(e && e.message || e) });
  }
}
