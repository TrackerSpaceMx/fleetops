import React, { useEffect, useState, useCallback } from 'react';
import { toast } from 'sonner';
import {
  Users, UserPlus, ShieldCheck, ShieldOff, Loader2, X, KeyRound, ShieldAlert,
  Pencil, Trash2, RotateCcw,
} from 'lucide-react';
import { authFetch, API, useAuth } from '../lib/auth';

type Usuario = {
  id: string;
  username: string;
  nombre: string;
  rol: 'admin' | 'operador';
  activo: boolean | number;
  created_at: string;
  last_login_at: string | null;
};

export function Configuracion() {
  const { user } = useAuth();
  const [usuarios, setUsuarios] = useState<Usuario[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [form, setForm] = useState({ username: '', nombre: '', password: '', rol: 'operador' as 'admin' | 'operador' });

  // ── Edición ──────────────────────────────────────────────────────────────
  const [editingId, setEditingId]   = useState<string | null>(null);
  const [editForm, setEditForm]     = useState({ username: '', nombre: '' });
  const [savingEdit, setSavingEdit] = useState(false);

  // ── Reset de contraseña ──────────────────────────────────────────────────
  const [resetId, setResetId]           = useState<string | null>(null);
  const [resetPassword, setResetPassword] = useState('');
  const [savingReset, setSavingReset]   = useState(false);

  // ── Borrado ──────────────────────────────────────────────────────────────
  const [deleteTarget, setDeleteTarget] = useState<Usuario | null>(null);
  const [deleting, setDeleting]         = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const res = await authFetch(`${API}/api/auth/users`);
      if (!res.ok) {
        if (res.status === 403) throw new Error('Solo un administrador puede ver esta sección.');
        throw new Error('No se pudo cargar la lista de usuarios');
      }
      const data = await res.json();
      setUsuarios(data.usuarios ?? []);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (user?.rol !== 'admin') {
    return (
      <div className="p-8">
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-10 text-center max-w-md mx-auto">
          <ShieldAlert className="w-8 h-8 mx-auto mb-3 text-amber-500" />
          <h3 className="font-bold text-gray-900 mb-1">Acceso restringido</h3>
          <p className="text-sm text-gray-500">Solo los administradores pueden gestionar usuarios.</p>
        </div>
      </div>
    );
  }

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const res = await authFetch(`${API}/api/auth/users`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'No se pudo crear el usuario');
      toast.success(`Usuario "${form.username}" creado`);
      setForm({ username: '', nombre: '', password: '', rol: 'operador' });
      setShowForm(false);
      load();
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setSaving(false);
    }
  };

  const toggleActivo = async (u: Usuario) => {
    const activo = !u.activo;
    try {
      const res = await authFetch(`${API}/api/auth/users/${u.id}/estado?activo=${activo}`, { method: 'PATCH' });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || 'No se pudo actualizar el usuario');
      toast.success(activo ? `${u.username} reactivado` : `${u.username} desactivado`);
      load();
    } catch (e: any) {
      toast.error(e.message);
    }
  };

  const toggleRol = async (u: Usuario) => {
    const nuevoRol = u.rol === 'admin' ? 'operador' : 'admin';
    try {
      const res = await authFetch(`${API}/api/auth/users/${u.id}/rol`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rol: nuevoRol }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || 'No se pudo cambiar el rol');
      toast.success(`${u.username} ahora es ${nuevoRol}`);
      load();
    } catch (e: any) {
      toast.error(e.message);
    }
  };

  const startEdit = (u: Usuario) => {
    setEditingId(u.id);
    setEditForm({ username: u.username, nombre: u.nombre });
  };

  const saveEdit = async (id: string) => {
    setSavingEdit(true);
    try {
      const res = await authFetch(`${API}/api/auth/users/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editForm),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || 'No se pudo editar el usuario');
      toast.success('Usuario actualizado');
      setEditingId(null);
      load();
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setSavingEdit(false);
    }
  };

  const saveResetPassword = async () => {
    if (!resetId) return;
    if (resetPassword.length < 8) {
      toast.error('La contraseña debe tener al menos 8 caracteres');
      return;
    }
    setSavingReset(true);
    try {
      const res = await authFetch(`${API}/api/auth/users/${resetId}/password`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password_nueva: resetPassword }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || 'No se pudo restablecer la contraseña');
      toast.success('Contraseña actualizada');
      setResetId(null);
      setResetPassword('');
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setSavingReset(false);
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      const res = await authFetch(`${API}/api/auth/users/${deleteTarget.id}`, { method: 'DELETE' });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || 'No se pudo eliminar el usuario');
      toast.success(`${deleteTarget.username} eliminado`);
      setDeleteTarget(null);
      load();
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="p-8 space-y-6 animate-fade-in-up">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-gray-500 text-sm">
          <Users className="w-4 h-4" /> {usuarios.length} usuario{usuarios.length !== 1 ? 's' : ''} registrados
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="flex items-center gap-2 bg-blue-500 hover:bg-blue-600 text-white text-sm font-semibold px-4 py-2 rounded-lg shadow-sm transition-colors"
        >
          <UserPlus className="w-4 h-4" /> Nuevo usuario
        </button>
      </div>

      {showForm && (
        <form
          onSubmit={handleCreate}
          className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6 grid grid-cols-1 md:grid-cols-4 gap-4 items-end"
        >
          <div>
            <label className="block text-xs font-semibold text-gray-500 mb-1">Usuario</label>
            <input
              required
              value={form.username}
              onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))}
              className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/30"
              placeholder="j.perez"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-500 mb-1">Nombre completo</label>
            <input
              required
              value={form.nombre}
              onChange={(e) => setForm((f) => ({ ...f, nombre: e.target.value }))}
              className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/30"
              placeholder="Juan Pérez"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-500 mb-1">Contraseña temporal</label>
            <input
              required
              type="text"
              minLength={8}
              value={form.password}
              onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
              className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/30"
              placeholder="mínimo 8 caracteres"
            />
          </div>
          <div className="flex items-end gap-2">
            <div className="flex-1">
              <label className="block text-xs font-semibold text-gray-500 mb-1">Rol</label>
              <select
                value={form.rol}
                onChange={(e) => setForm((f) => ({ ...f, rol: e.target.value as any }))}
                className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/30"
              >
                <option value="operador">Operador</option>
                <option value="admin">Administrador</option>
              </select>
            </div>
            <button
              type="submit"
              disabled={saving}
              className="bg-navy-500 hover:bg-navy-600 text-white text-sm font-semibold px-4 py-2 rounded-lg disabled:opacity-60 shrink-0"
            >
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Crear'}
            </button>
            <button
              type="button"
              onClick={() => setShowForm(false)}
              className="text-gray-400 hover:text-gray-600 p-2"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </form>
      )}

      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center gap-2 text-gray-400 py-16">
            <Loader2 className="w-5 h-5 animate-spin" /> Cargando usuarios…
          </div>
        ) : error ? (
          <div className="text-danger text-sm p-6">{error}</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] font-semibold text-gray-400 uppercase tracking-wide border-b border-gray-100">
                <th className="px-6 py-3">Usuario</th>
                <th className="px-6 py-3">Rol</th>
                <th className="px-6 py-3">Estado</th>
                <th className="px-6 py-3">Último acceso</th>
                <th className="px-6 py-3 text-right">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {usuarios.map((u) => (
                <tr key={u.id} className="border-b border-gray-50 hover:bg-gray-50/60">
                  {editingId === u.id ? (
                    <td className="px-6 py-3" colSpan={1}>
                      <input
                        value={editForm.nombre}
                        onChange={(e) => setEditForm((f) => ({ ...f, nombre: e.target.value }))}
                        className="w-full px-2 py-1 rounded border border-gray-200 text-sm mb-1 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                        placeholder="Nombre completo"
                      />
                      <input
                        value={editForm.username}
                        onChange={(e) => setEditForm((f) => ({ ...f, username: e.target.value }))}
                        className="w-full px-2 py-1 rounded border border-gray-200 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                        placeholder="usuario"
                      />
                    </td>
                  ) : (
                    <td className="px-6 py-3">
                      <p className="font-semibold text-gray-900">{u.nombre}</p>
                      <p className="text-xs text-gray-400 flex items-center gap-1"><KeyRound className="w-3 h-3" /> {u.username}</p>
                    </td>
                  )}
                  <td className="px-6 py-3">
                    <span
                      className={`text-xs font-semibold px-2 py-1 rounded-full ${
                        u.rol === 'admin' ? 'bg-navy-500/10 text-navy-500' : 'bg-blue-500/10 text-blue-600'
                      }`}
                    >
                      {u.rol === 'admin' ? 'Administrador' : 'Operador'}
                    </span>
                  </td>
                  <td className="px-6 py-3">
                    <span
                      className={`text-xs font-semibold px-2 py-1 rounded-full ${
                        u.activo ? 'bg-emerald-500/10 text-emerald-600' : 'bg-gray-200 text-gray-500'
                      }`}
                    >
                      {u.activo ? 'Activo' : 'Desactivado'}
                    </span>
                  </td>
                  <td className="px-6 py-3 text-gray-400 text-xs">
                    {u.last_login_at ? new Date(u.last_login_at).toLocaleString('es-MX') : 'Nunca'}
                  </td>
                  <td className="px-6 py-3">
                    {editingId === u.id ? (
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => saveEdit(u.id)}
                          disabled={savingEdit}
                          className="text-xs font-semibold text-blue-600 hover:text-blue-700 disabled:opacity-50"
                        >
                          {savingEdit ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : 'Guardar'}
                        </button>
                        <button
                          onClick={() => setEditingId(null)}
                          className="text-xs font-medium text-gray-400 hover:text-gray-600"
                        >
                          Cancelar
                        </button>
                      </div>
                    ) : (
                      <div className="flex items-center justify-end gap-3">
                        <button
                          onClick={() => toggleRol(u)}
                          disabled={u.id === user?.id}
                          title="Cambiar rol"
                          className="text-xs font-medium text-gray-500 hover:text-navy-500 disabled:opacity-30 disabled:cursor-not-allowed"
                        >
                          {u.rol === 'admin' ? 'Hacer operador' : 'Hacer admin'}
                        </button>
                        <button
                          onClick={() => startEdit(u)}
                          title="Editar usuario"
                          className="text-gray-400 hover:text-blue-600"
                        >
                          <Pencil className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => { setResetId(u.id); setResetPassword(''); }}
                          title="Restablecer contraseña"
                          className="text-gray-400 hover:text-amber-600"
                        >
                          <RotateCcw className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => toggleActivo(u)}
                          disabled={u.id === user?.id}
                          title={u.activo ? 'Desactivar' : 'Reactivar'}
                          className="text-gray-400 hover:text-danger disabled:opacity-30 disabled:cursor-not-allowed"
                        >
                          {u.activo ? <ShieldOff className="w-4 h-4" /> : <ShieldCheck className="w-4 h-4 text-success" />}
                        </button>
                        <button
                          onClick={() => setDeleteTarget(u)}
                          disabled={u.id === user?.id}
                          title="Eliminar usuario"
                          className="text-gray-400 hover:text-red-600 disabled:opacity-30 disabled:cursor-not-allowed"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Modal: restablecer contraseña */}
      {resetId && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl p-6 w-full max-w-sm">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold text-gray-900">Restablecer contraseña</h3>
              <button onClick={() => setResetId(null)} className="text-gray-400 hover:text-gray-600">
                <X className="w-4 h-4" />
              </button>
            </div>
            <label className="block text-xs font-semibold text-gray-500 mb-1">Nueva contraseña</label>
            <input
              type="text"
              autoFocus
              minLength={8}
              value={resetPassword}
              onChange={(e) => setResetPassword(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm mb-4 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
              placeholder="mínimo 8 caracteres"
            />
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setResetId(null)}
                className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700"
              >
                Cancelar
              </button>
              <button
                onClick={saveResetPassword}
                disabled={savingReset}
                className="bg-blue-500 hover:bg-blue-600 text-white text-sm font-semibold px-4 py-2 rounded-lg disabled:opacity-60"
              >
                {savingReset ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Guardar'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal: confirmar borrado */}
      {deleteTarget && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl p-6 w-full max-w-sm">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 rounded-full bg-red-50 flex items-center justify-center shrink-0">
                <Trash2 className="w-5 h-5 text-red-600" />
              </div>
              <h3 className="font-bold text-gray-900">Eliminar usuario</h3>
            </div>
            <p className="text-sm text-gray-500 mb-6">
              ¿Seguro que quieres eliminar a <span className="font-semibold text-gray-700">{deleteTarget.nombre}</span> ({deleteTarget.username})? Esta acción no se puede deshacer.
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setDeleteTarget(null)}
                className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700"
              >
                Cancelar
              </button>
              <button
                onClick={confirmDelete}
                disabled={deleting}
                className="bg-red-600 hover:bg-red-700 text-white text-sm font-semibold px-4 py-2 rounded-lg disabled:opacity-60"
              >
                {deleting ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Eliminar'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
