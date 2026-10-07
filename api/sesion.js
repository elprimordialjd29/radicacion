// Quién soy y qué puedo hacer (la interfaz oculta lo que no está permitido).
import { requiere, publico, PERMISOS, ROLES } from './_usuarios.js';

export default async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  const ctx = await requiere(req, res);
  if (!ctx) return;
  return res.status(200).json({ usuario: publico(ctx.yo), permisos: PERMISOS, roles: ROLES });
}
