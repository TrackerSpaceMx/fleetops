import React, { useEffect, useState, useCallback } from 'react';
import { Scale, TrendingUp, TrendingDown, Truck, RefreshCw, Loader2 } from 'lucide-react';
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
} from 'recharts';
import { authFetch, API } from '../lib/auth';
import type { BasculaHoy, BasculaPorUnidad, TonelajeDiarioPoint, BascularRecord } from '../services/websocket';

async function fetchBasculaHoy(): Promise<BasculaHoy> {
  const r = await authFetch(`${API}/api/bascula/hoy`);
  if (!r.ok) throw new Error('Error GET /api/bascula/hoy');
  return r.json();
}
async function fetchBasculaAyer(): Promise<BasculaHoy> {
  const r = await authFetch(`${API}/api/bascula/ayer`);
  if (!r.ok) return { fecha: '', toneladas: 0, viajes: 0 };
  return r.json();
}
async function fetchTonelajeDiario(dias = 30): Promise<TonelajeDiarioPoint[]> {
  const r = await authFetch(`${API}/api/bascula/diario?dias=${dias}`);
  if (!r.ok) throw new Error('Error GET /api/bascula/diario');
  const data = await r.json();
  return (data.serie ?? []).map((p: any) => ({
    fecha: p.fecha,
    day: p.fecha ? p.fecha.slice(8, 10) : '',
    tons: p.toneladas,
    viajes: p.viajes,
  }));
}
async function fetchBasculaPorUnidad(): Promise<BasculaPorUnidad[]> {
  const r = await authFetch(`${API}/api/bascula/por-unidad`);
  if (!r.ok) throw new Error('Error GET /api/bascula/por-unidad');
  const data = await r.json();
  return data.unidades ?? [];
}
async function fetchBasculaActividad(limit = 60): Promise<BascularRecord[]> {
  const r = await authFetch(`${API}/api/bascula/actividad?limit=${limit}`);
  if (!r.ok) throw new Error('Error GET /api/bascula/actividad');
  const data = await r.json();
  return data.registros ?? [];
}
async function forceSync(): Promise<void> {
  await authFetch(`${API}/api/bascula/sync`);
}

function fmtNum(n: number, decimals = 2) {
  return (n ?? 0).toLocaleString('es-MX', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

export function Bascula() {
  const [hoy, setHoy] = useState<BasculaHoy | null>(null);
  const [ayer, setAyer] = useState<BasculaHoy | null>(null);
  const [diario, setDiario] = useState<TonelajeDiarioPoint[]>([]);
  const [porUnidad, setPorUnidad] = useState<BasculaPorUnidad[]>([]);
  const [actividad, setActividad] = useState<BascularRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadAll = useCallback(async () => {
    setError(null);
    try {
      const [h, a, d, u, act] = await Promise.all([
        fetchBasculaHoy(),
        fetchBasculaAyer(),
        fetchTonelajeDiario(30),
        fetchBasculaPorUnidad(),
        fetchBasculaActividad(60),
      ]);
      setHoy(h);
      setAyer(a);
      setDiario(d);
      setPorUnidad(u);
      setActividad(act);
    } catch (e: any) {
      setError(e.message || 'No se pudieron cargar los datos de báscula');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
    const interval = setInterval(loadAll, 60_000);
    return () => clearInterval(interval);
  }, [loadAll]);

  const handleSync = async () => {
    setSyncing(true);
    try {
      await forceSync();
      await loadAll();
    } finally {
      setSyncing(false);
    }
  };

  const variacion = ayer && ayer.toneladas > 0 && hoy
    ? ((hoy.toneladas - ayer.toneladas) / ayer.toneladas) * 100
    : null;

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center text-gray-400 gap-2">
        <Loader2 className="w-5 h-5 animate-spin" /> Cargando báscula…
      </div>
    );
  }

  return (
    <div className="p-8 space-y-6 animate-fade-in-up">
      {error && (
        <div className="bg-red-50 border border-red-100 text-danger text-sm rounded-lg px-4 py-3">
          {error}
        </div>
      )}

      {/* KPIs */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Toneladas hoy</span>
            <Scale className="w-5 h-5 text-blue-500" />
          </div>
          <p className="text-3xl font-bold text-gray-900">{fmtNum(hoy?.toneladas ?? 0)}</p>
          <p className="text-xs text-gray-400 mt-1">{hoy?.viajes ?? 0} viajes registrados</p>
        </div>

        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Toneladas ayer</span>
            <Scale className="w-5 h-5 text-gray-400" />
          </div>
          <p className="text-3xl font-bold text-gray-900">{fmtNum(ayer?.toneladas ?? 0)}</p>
          <p className="text-xs text-gray-400 mt-1">{ayer?.viajes ?? 0} viajes registrados</p>
        </div>

        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Variación vs ayer</span>
            {variacion !== null && variacion >= 0 ? (
              <TrendingUp className="w-5 h-5 text-success" />
            ) : (
              <TrendingDown className="w-5 h-5 text-danger" />
            )}
          </div>
          <p className={`text-3xl font-bold ${variacion !== null && variacion >= 0 ? 'text-success' : 'text-danger'}`}>
            {variacion !== null ? `${variacion >= 0 ? '+' : ''}${fmtNum(variacion, 1)}%` : '—'}
          </p>
          <button
            onClick={handleSync}
            disabled={syncing}
            className="text-xs mt-2 flex items-center gap-1.5 text-blue-500 hover:text-blue-600 font-medium disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${syncing ? 'animate-spin' : ''}`} />
            {syncing ? 'Sincronizando…' : 'Forzar sincronización'}
          </button>
        </div>
      </div>

      {/* Gráfico 30 días */}
      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6">
        <h3 className="text-sm font-bold text-gray-900 mb-4">Tonelaje diario — últimos 30 días</h3>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={diario}>
            <CartesianGrid strokeDasharray="3 3" stroke="#F0F4F8" vertical={false} />
            <XAxis dataKey="day" tick={{ fontSize: 11, fill: '#94A3B8' }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize: 11, fill: '#94A3B8' }} axisLine={false} tickLine={false} />
            <Tooltip
              contentStyle={{ borderRadius: 8, border: '1px solid #E2E8F0', fontSize: 12 }}
              formatter={(v: number) => [`${fmtNum(v)} ton`, 'Toneladas']}
            />
            <Bar dataKey="tons" fill="#0A7AFF" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Por unidad */}
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6">
          <h3 className="text-sm font-bold text-gray-900 mb-4">Toneladas por unidad — hoy</h3>
          <div className="space-y-3 max-h-80 overflow-y-auto pr-1">
            {porUnidad.length === 0 && (
              <p className="text-sm text-gray-400">Sin registros de báscula hoy todavía.</p>
            )}
            {porUnidad
              .sort((a, b) => b.toneladas - a.toneladas)
              .map((u) => {
                const max = Math.max(...porUnidad.map((x) => x.toneladas), 1);
                const pct = (u.toneladas / max) * 100;
                return (
                  <div key={u.num_eco}>
                    <div className="flex items-center justify-between text-xs mb-1">
                      <span className="font-semibold text-gray-700 flex items-center gap-1.5">
                        <Truck className="w-3.5 h-3.5 text-gray-400" /> {u.num_eco}
                      </span>
                      <span className="text-gray-500">{fmtNum(u.toneladas)} ton · {u.viajes} viajes</span>
                    </div>
                    <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                      <div className="h-full bg-blue-500 rounded-full" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                );
              })}
          </div>
        </div>

        {/* Actividad en vivo */}
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6">
          <h3 className="text-sm font-bold text-gray-900 mb-4">Actividad de báscula en vivo</h3>
          <div className="overflow-y-auto max-h-80">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-white">
                <tr className="text-gray-400 uppercase tracking-wide text-[10px] border-b border-gray-100">
                  <th className="text-left py-2 font-semibold">Unidad</th>
                  <th className="text-left py-2 font-semibold">Cliente</th>
                  <th className="text-right py-2 font-semibold">Neto (ton)</th>
                  <th className="text-right py-2 font-semibold">Hora</th>
                </tr>
              </thead>
              <tbody>
                {actividad.length === 0 && (
                  <tr><td colSpan={4} className="text-center text-gray-400 py-6">Sin actividad reciente.</td></tr>
                )}
                {actividad.map((r, i) => (
                  <tr key={`${r.folio}-${i}`} className="border-b border-gray-50 hover:bg-gray-50">
                    <td className="py-2 font-semibold text-gray-700">{r.num_eco || r.placa}</td>
                    <td className="py-2 text-gray-500 truncate max-w-[140px]">{r.tipo_cliente}</td>
                    <td className="py-2 text-right font-mono text-gray-700">{fmtNum(r.peso_neto)}</td>
                    <td className="py-2 text-right text-gray-400 font-mono">{r.hora_salida || r.hora_entrada}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
