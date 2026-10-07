// Usuarios, roles y permisos. Se guardan en Vercel Blob PRIVADO (radicacion/usuarios.json)
// con la clave cifrada (scrypt). Si no hay usuarios, se crea admin / admin123.
import { get, put } from '@vercel/blob';
import { scryptSync, randomBytes, timingSafeEqual } from 'node:crypto';
import { verificar, leerCookie } from './_sesion.js';

const RUTA = 'radicacion/usuarios.json';

export const PERMISOS = {
  ver_reporte: 'Ver reporte de desviación',
  consultar_sie: 'Lanzar consultas al SIE',
  descargar_rips: 'Descargar RIPS (TXT / JSON)',
  descargar_reportes: 'Descargar reportes (Excel / CSV)',
  admin_usuarios: 'Administrar usuarios',
};
export const ROLES = {
  admin: { nombre: 'Administrador', permisos: Object.keys(PERMISOS) },
  analista: { nombre: 'Analista', permisos: ['ver_reporte', 'consultar_sie', 'descargar_rips', 'descargar_reportes'] },
  auditor: { nombre: 'Auditor RIPS', permisos: ['ver_reporte', 'descargar_rips'] },
  consulta: { nombre: 'Solo consulta', permisos: [] },
};

export function hash(clave) {
  const sal = randomBytes(16);
  return `scrypt$${sal.toString('hex')}$${scryptSync(String(clave), sal, 32).toString('hex')}`;
}
export function verificarClave(clave, guardado) {
  const [, sal, h] = String(guardado || '').split('$');
  if (!sal || !h) return false;
  const x = scryptSync(String(clave), Buffer.from(sal, 'hex'), 32);
  const y = Buffer.from(h, 'hex');
  return x.length === y.length && timingSafeEqual(x, y);
}

export async function guardarUsuarios(usuarios) {
  await put(RUTA, JSON.stringify(usuarios), {
    access: 'private', allowOverwrite: true, addRandomSuffix: false, contentType: 'application/json',
  });
}
export async function cargarUsuarios() {
  try {
    const r = await get(RUTA, { access: 'private', useCache: false });
    if (r && r.statusCode === 200) return JSON.parse(await new Response(r.stream).text());
  } catch (e) {
    if (e?.name !== 'BlobNotFoundError') throw e;
  }
  const inicial = {
    admin: {
      usuario: 'admin', nombre: 'Administrador', rol: 'admin', permisos: ROLES.admin.permisos,
      clave: hash('admin123'), activo: true, debeCambiar: true, creado: new Date().toISOString(),
    },
  };
  await guardarUsuarios(inicial);
  return inicial;
}

export const publico = (u) => ({
  usuario: u.usuario, nombre: u.nombre, rol: u.rol, permisos: u.permisos || [], activo: !!u.activo,
  debeCambiar: !!u.debeCambiar, creado: u.creado || null, ultimoIngreso: u.ultimoIngreso || null,
});

// Valida la sesión, que el usuario siga activo y (opcional) que tenga el permiso.
// Responde 401/403 y devuelve null si no; si sí, devuelve { yo, usuarios }.
export async function requiere(req, res, permiso) {
  const s = await verificar(leerCookie(req.headers.cookie));
  if (!s) { res.status(401).json({ error: 'Sesión vencida. Vuelve a ingresar.' }); return null; }
  const usuarios = await cargarUsuarios();
  const yo = usuarios[s.u];
  if (!yo || !yo.activo) { res.status(401).json({ error: 'Usuario inactivo.' }); return null; }
  if (permiso && !(yo.permisos || []).includes(permiso)) {
    res.status(403).json({ error: `No tienes permiso: ${PERMISOS[permiso] || permiso}.` });
    return null;
  }
  return { yo, usuarios };
}

export const normalizarUsuario = (u) => String(u || '').trim().toLowerCase().replace(/[^a-z0-9._-]/g, '').slice(0, 40);
