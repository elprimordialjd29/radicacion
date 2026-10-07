// Administración de usuarios (permiso admin_usuarios).
//   GET                       lista
//   POST   {usuario, nombre, clave, rol, permisos}      crear
//   PUT    {usuario, nombre?, rol?, permisos?, activo?, clave?}   editar / restablecer clave
//   DELETE ?usuario=X         eliminar
import { requiere, guardarUsuarios, publico, hash, normalizarUsuario, PERMISOS, ROLES } from './_usuarios.js';

const limpiarPermisos = (p) => [...new Set((p || []).filter((x) => x in PERMISOS))];
const admins = (us) => Object.values(us).filter((u) => u.activo && (u.permisos || []).includes('admin_usuarios'));

export default async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  const ctx = await requiere(req, res, 'admin_usuarios');
  if (!ctx) return;
  const { usuarios, yo } = ctx;
  const body = typeof req.body === 'string' ? JSON.parse(req.body || '{}') : (req.body || {});

  if (req.method === 'GET') {
    return res.status(200).json(Object.values(usuarios).map(publico).sort((a, b) => a.usuario.localeCompare(b.usuario)));
  }
  if (req.method === 'POST') {
    const id = normalizarUsuario(body.usuario);
    if (!id) return res.status(400).json({ error: 'Usuario inválido (letras, números, punto, guion).' });
    if (usuarios[id]) return res.status(409).json({ error: 'Ese usuario ya existe.' });
    if (String(body.clave || '').length < 8) return res.status(400).json({ error: 'La clave debe tener al menos 8 caracteres.' });
    const rol = body.rol in ROLES ? body.rol : 'consulta';
    usuarios[id] = {
      usuario: id, nombre: String(body.nombre || id).slice(0, 80), rol,
      permisos: limpiarPermisos(body.permisos ?? ROLES[rol].permisos), clave: hash(body.clave),
      activo: true, debeCambiar: true, creado: new Date().toISOString(), creadoPor: yo.usuario,
    };
    await guardarUsuarios(usuarios);
    return res.status(201).json(publico(usuarios[id]));
  }
  if (req.method === 'PUT') {
    const u = usuarios[normalizarUsuario(body.usuario)];
    if (!u) return res.status(404).json({ error: 'No existe ese usuario.' });
    const antes = { ...u };
    if (body.nombre !== undefined) u.nombre = String(body.nombre).slice(0, 80);
    if (body.rol !== undefined && body.rol in ROLES) u.rol = body.rol;
    if (body.permisos !== undefined) u.permisos = limpiarPermisos(body.permisos);
    if (body.activo !== undefined) u.activo = !!body.activo;
    if (body.clave) {
      if (String(body.clave).length < 8) return res.status(400).json({ error: 'La clave debe tener al menos 8 caracteres.' });
      u.clave = hash(body.clave); u.debeCambiar = true;
    }
    if (!admins(usuarios).length) { Object.assign(u, antes); return res.status(400).json({ error: 'Debe quedar al menos un administrador activo.' }); }
    await guardarUsuarios(usuarios);
    return res.status(200).json(publico(u));
  }
  if (req.method === 'DELETE') {
    const id = normalizarUsuario(req.query.usuario);
    if (!usuarios[id]) return res.status(404).json({ error: 'No existe ese usuario.' });
    if (id === yo.usuario) return res.status(400).json({ error: 'No puedes eliminar tu propio usuario.' });
    const resto = { ...usuarios }; delete resto[id];
    if (!admins(resto).length) return res.status(400).json({ error: 'Debe quedar al menos un administrador activo.' });
    await guardarUsuarios(resto);
    return res.status(200).json({ ok: true });
  }
  return res.status(405).json({ error: 'Método no permitido' });
}
