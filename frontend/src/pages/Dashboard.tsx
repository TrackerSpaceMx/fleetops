import React, { useEffect, useState, useRef, useCallback } from 'react';
import {
  ArrowUpRight, ArrowDownRight, Activity, Truck, Fuel, MapPin,
  AlertCircle, Clock, MoreVertical, Scale, RefreshCw,
} from 'lucide-react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, BarChart, Bar, Cell, ReferenceLine,
} from 'recharts';
import {
  connectFuelSocket,
  connectFleetSocket,
  fetchBasculaHoy,
  fetchBasculaAyer,
  fetchTonelajeDiario,
  fetchBasculaPorUnidad,
  fetchBasculaActividad,
  type FuelStats,
  type FleetStats,
  type BasculaHoy,
  type TonelajeDiarioPoint,
  type BasculaPorUnidad,
  type BascularRecord,
} from '@/services/websocket';
import { authFetch } from '../lib/auth';

const MESES_NOMBRE = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];

// Mini sparkline estático para el KPI de toneladas (se reemplaza con serie real)
const miniTrendData = Array.from({ length: 10 }, (_, i) => ({ value: 420 + i * 8 }));

// Colores por tipo de residuo
function tipoColor(tipo: string) {
  if (!tipo) return 'bg-gray-100 text-gray-600';
  const t = tipo.toLowerCase();
  if (t.includes('domiciliario')) return 'bg-blue-50 text-blue-700';
  if (t.includes('particular'))   return 'bg-purple-50 text-purple-700';
  if (t.includes('industrial'))   return 'bg-orange-50 text-orange-700';
  if (t.includes('comercial'))    return 'bg-teal-50 text-teal-700';
  return 'bg-gray-100 text-gray-600';
}

export function Dashboard() {

  // ── Estado báscula ────────────────────────────────────────────────────────
  const [basculaHoy, setBasculaHoy]           = useState<BasculaHoy>({ fecha: '', toneladas: 0, viajes: 0 });
  const [basculaAyer, setBasculaAyer]         = useState<number>(0);   // toneladas del día anterior
  const [tonsData, setTonsData]               = useState<TonelajeDiarioPoint[]>([]);
  const [tonsLoading, setTonsLoading]         = useState(true);
  const [porUnidad, setPorUnidad]             = useState<BasculaPorUnidad[]>([]);
  const [actividad, setActividad]             = useState<BascularRecord[]>([]);
  const [actividadTs, setActividadTs]         = useState<string>('');
  const [actividadLoading, setActividadLoading] = useState(false);
  const [busqueda, setBusqueda]               = useState<string>('');
  const [pagina, setPagina]                   = useState<number>(1);
  const FILAS_POR_PAGINA = 10;
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Estado combustible / flota ────────────────────────────────────────────
  const [fuelStats, setFuelStats] = useState<FuelStats>({
    total_liters: 0, total_cost: 0, recent_records: [], all_records: [],
  });
  const [fleetStats, setFleetStats] = useState<FleetStats>({
    active_units: 0, inactive_units: 0, total_units: 0, total_km_hoy: 0, units: [],
  });
  const [showAllFuel, setShowAllFuel]         = useState(false);
  const [comparativo, setComparativo]         = useState<any[]>([]);
  const [comparativoLoading, setComparativoLoading] = useState(true);
  const [consumoMode, setConsumoMode]         = useState<'litros' | 'costo'>('litros');

  // ── Datos derivados ───────────────────────────────────────────────────────
  const top3Units = [...fleetStats.units]
    .filter(u => u.diesel_lts > 0)
    .sort((a, b) => b.diesel_lts - a.diesel_lts)
    .slice(0, 3);

  const vehicleEcoMap = Object.fromEntries(
    fleetStats.units.map(u => [String((u as any).vehicle_id), u.eco])
  );

  const consumoTop3Data = top3Units.map(u => ({
    name:   u.eco,
    litros: Math.round(u.diesel_lts),
    costo:  Math.round(u.total_importe),
  }));

  // ── Carga báscula: inicial ────────────────────────────────────────────────
  const loadBascula = useCallback(async (showLoader = false) => {
    if (showLoader) setActividadLoading(true);
    try {
      // Calcular días del mes actual para pedir el rango completo mes a hoy

      const [hoy, ayer, serieData, unidades, act] = await Promise.all([
        fetchBasculaHoy(),
        fetchBasculaAyer(),
        fetchTonelajeDiario(30),   // siempre últimos 30 días
        fetchBasculaPorUnidad(),
        fetchBasculaActividad(500),
      ]);
      setBasculaHoy(hoy);
      setBasculaAyer(ayer.toneladas);             // dato real de ayer desde la DB
      setTonsData(serieData);
      setPorUnidad(unidades);
      setActividad(act);
      setPagina(1); // reset paginación al refrescar
      setActividadTs(new Date().toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' }));
    } catch (e) {
      console.error('Error cargando báscula:', e);
    } finally {
      setTonsLoading(false);
      setActividadLoading(false);
    }
  }, []);

  // ── Polling de actividad cada 1 min ──────────────────────────────────────
  const pollActividad = useCallback(async () => {
    try {
      const [act, hoy, unidades] = await Promise.all([
        fetchBasculaActividad(500),
        fetchBasculaHoy(),
        fetchBasculaPorUnidad(),
      ]);
      setActividad(act);
      setBasculaHoy(hoy);
      setPorUnidad(unidades);
      setPagina(1);
      setActividadTs(new Date().toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' }));
    } catch (e) {
      console.error('Error polling báscula:', e);
    }
  }, []);

  // ── Efectos ───────────────────────────────────────────────────────────────
  useEffect(() => {
    // Carga inicial
    loadBascula(true);

    // WebSockets
    const fuelSocket  = connectFuelSocket((data) => setFuelStats(data));
    const fleetSocket = connectFleetSocket(
      (data) => setFleetStats(data),
      // Cuando el scheduler emite bascula_update, refrescar sin esperar al intervalo
      (update) => {
        setBasculaHoy(prev => ({
          ...prev,
          toneladas: update.toneladas_hoy,
          viajes:    update.viajes_hoy,
        }));
        // También refresca actividad
        fetchBasculaActividad(500).then(setActividad).catch(() => {});
        fetchBasculaPorUnidad().then(setPorUnidad).catch(() => {});
        setActividadTs(new Date().toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' }));
      }
    );

    // Comparativo combustible últimos 3 meses
    const today = new Date();
    const meses: Array<{ year: number; month: number; label: string }> = [];
    for (let i = 2; i >= 0; i--) {
      const d = new Date(today.getFullYear(), today.getMonth() - i, 1);
      meses.push({ year: d.getFullYear(), month: d.getMonth() + 1, label: MESES_NOMBRE[d.getMonth()] });
    }
    Promise.all(
      meses.map(({ year, month }) =>
        authFetch(`https://fleetops-space.com.mx/api/reports/top3-consumo?year=${year}&month=${month}`)
          .then(r => r.json()).catch(() => ({ top3: [] }))
      )
    ).then(results => {
      const chartData = results.map((res, i) => ({
        periodo:  meses[i].label,
        year:     meses[i].year,
        month:    meses[i].month,
        unidades: (res.top3 ?? []).map((u: any) => ({
          name:   u.eco,
          litros: Math.round(u.litros_mes ?? 0),
          costo:  Math.round(u.costo_mes  ?? 0),
        })),
      }));
      setComparativo(chartData.filter(m => m.unidades.length > 0).length > 0 ? chartData : []);
      setComparativoLoading(false);
    }).catch(() => setComparativoLoading(false));

    // Polling cada 60 seg
    pollingRef.current = setInterval(pollActividad, 60_000);

    return () => {
      fuelSocket.close();
      fleetSocket.close();
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [loadBascula, pollActividad]);

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="p-8 space-y-6 max-w-[1600px] mx-auto">

      {/* ── HERO KPI ROW ──────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">

        {/* KPI 1 — Toneladas Hoy (BÁSCULA REAL) */}
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100 animate-fade-in-up" style={{ animationDelay: '0ms' }}>
          <div className="flex justify-between items-start mb-4">
            <div>
              <p className="text-sm font-semibold text-gray-500 uppercase tracking-wider">Toneladas Hoy</p>
              {tonsLoading ? (
                <div className="flex items-center gap-2 mt-2">
                  <div className="w-5 h-5 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
                  <span className="text-gray-400 text-sm">Cargando...</span>
                </div>
              ) : (
                <h3 className="text-3xl font-bold text-gray-900 font-mono mt-1 tabular-nums">
                  {basculaHoy.toneladas.toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}{' '}
                  <span className="text-lg text-gray-400 font-sans">t</span>
                </h3>
              )}
            </div>
            <div className="w-10 h-10 rounded-full bg-blue-50 flex items-center justify-center">
              <Scale className="w-5 h-5 text-blue-500" />
            </div>
          </div>
          <div className="flex items-center justify-between">
            <div className="text-sm text-gray-500">
              <span className="font-semibold text-gray-700">{basculaHoy.viajes}</span> viajes hoy
            </div>
            {!tonsLoading && basculaAyer > 0 && (() => {
              const diff = basculaHoy.toneladas - basculaAyer;
              const pct  = basculaAyer > 0 ? ((diff / basculaAyer) * 100).toFixed(1) : '0';
              const sube = diff >= 0;
              return (
                <div className={`flex items-center gap-1 text-xs font-semibold px-2 py-1 rounded-md ${sube ? 'text-emerald-600 bg-emerald-50' : 'text-red-500 bg-red-50'}`}>
                  {sube ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                  {sube ? '+' : ''}{pct}% vs ayer
                </div>
              );
            })()}
          </div>
        </div>

        {/* KPI 2 — Combustible (live) */}
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100 animate-fade-in-up" style={{ animationDelay: '100ms' }}>
          <div className="flex justify-between items-start mb-4">
            <div>
              <p className="text-sm font-semibold text-gray-500 uppercase tracking-wider">Combustible</p>
              <h3 className="text-3xl font-bold text-gray-900 font-mono mt-1 tabular-nums">
                {(fuelStats.total_liters ?? 0).toLocaleString('es-MX', { maximumFractionDigits: 0 })}{' '}
                <span className="text-lg text-gray-400 font-sans">L</span>
              </h3>
            </div>
            <div className="w-10 h-10 rounded-full bg-warning/10 flex items-center justify-center">
              <Fuel className="w-5 h-5 text-warning" />
            </div>
          </div>
          <div className="flex items-center justify-between">
            <div className="text-sm text-gray-500 font-mono">
              Costo:{' '}
              <span className="font-semibold text-gray-900">
                {(fuelStats.total_cost ?? 0).toLocaleString('es-MX', { style: 'currency', currency: 'MXN' })}
              </span>
            </div>
            <div className="relative w-8 h-8">
              <svg className="w-full h-full transform -rotate-90" viewBox="0 0 36 36">
                <path className="text-gray-100" strokeWidth="4" stroke="currentColor" fill="none"
                  d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
                <path className="text-warning" strokeWidth="4" strokeDasharray="60, 100" stroke="currentColor" fill="none"
                  d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
              </svg>
            </div>
          </div>
        </div>

        {/* KPI 3 — Flota Activa (live) */}
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100 animate-fade-in-up" style={{ animationDelay: '200ms' }}>
          <div className="flex justify-between items-start mb-4">
            <div>
              <p className="text-sm font-semibold text-gray-500 uppercase tracking-wider">Flota Activa</p>
              <h3 className="text-3xl font-bold text-gray-900 font-mono mt-1 tabular-nums">
                {fleetStats.active_units}
                <span className="text-lg text-gray-400 font-sans">/{fleetStats.total_units}</span>
              </h3>
            </div>
            <div className="w-10 h-10 rounded-full bg-success/10 flex items-center justify-center">
              <Truck className="w-5 h-5 text-success" />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-danger/10 text-danger text-xs font-bold">
              <AlertCircle className="w-3 h-3" /> {fleetStats.inactive_units} Offline
            </span>
            <span className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-warning/10 text-warning text-xs font-bold">
              <Clock className="w-3 h-3" /> 1 Taller
            </span>
          </div>
        </div>

        {/* KPI 4 — KM Recorridos (live) */}
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100 animate-fade-in-up" style={{ animationDelay: '300ms' }}>
          <div className="flex justify-between items-start mb-4">
            <div>
              <p className="text-sm font-semibold text-gray-500 uppercase tracking-wider">KM Recorridos</p>
              <h3 className="text-3xl font-bold text-gray-900 font-mono mt-1 tabular-nums">
                {(fleetStats.total_km_hoy ?? 0).toLocaleString('es-MX')}{' '}
                <span className="text-lg text-gray-400 font-sans">km</span>
              </h3>
            </div>
            <div className="w-10 h-10 rounded-full bg-blue-50 flex items-center justify-center">
              <MapPin className="w-5 h-5 text-blue-500" />
            </div>
          </div>
          <div className="flex items-center gap-1 text-gray-400 text-sm">
            <span>Total flota hoy</span>
          </div>
        </div>

      </div>

      {/* ── SECOND ROW ────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">

        {/* Rendimiento por Unidad */}
        <div className="lg:col-span-5 bg-white rounded-xl p-6 shadow-sm border border-gray-100 flex flex-col">
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-lg font-bold text-gray-900">Rendimiento por Unidad</h3>
            <span className="text-xs font-medium text-gray-500 bg-gray-100 px-2 py-1 rounded">KM / LT</span>
          </div>
          <div className="flex-1 min-h-[300px]">
            {fleetStats.units.length === 0 ? (
              <div className="flex items-center justify-center h-full text-gray-400 text-sm">Esperando datos...</div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={fleetStats.units} layout="vertical" margin={{ top: 0, right: 20, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={true} vertical={false} stroke="#E5E7EB" />
                  <XAxis type="number" domain={[0, 'auto']} tick={{ fontSize: 12, fill: '#6B7280' }} />
                  <YAxis dataKey="eco" type="category" tick={{ fontSize: 11, fill: '#374151', fontWeight: 600 }} width={55} />
                  <Tooltip
                    cursor={{ fill: '#F3F4F6' }}
                    contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)' }}
                    formatter={(value: number) => [`${value.toFixed(2)} km/lt`, 'Rendimiento']}
                  />
                  <ReferenceLine x={1.5} stroke="#EF4444" strokeDasharray="3 3" />
                  <Bar dataKey="km_por_litro" radius={[0, 4, 4, 0]} barSize={14}>
                    {fleetStats.units.map((entry, index) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={entry.km_por_litro >= 1.8 ? '#10B981' : entry.km_por_litro >= 1.5 ? '#F59E0B' : '#EF4444'}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Tonelaje Diario — últimos 30 días (BÁSCULA REAL) */}
        <div className="lg:col-span-7 bg-white rounded-xl p-6 shadow-sm border border-gray-100 flex flex-col">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h3 className="text-lg font-bold text-gray-900">Tonelaje Diario</h3>
              <p className="text-sm text-gray-500">Últimos 30 días</p>
            </div>
            <div className="flex items-center gap-4 text-sm">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-blue-500"></div>
                <span className="text-gray-600">Real</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-4 h-0.5 bg-gray-400 border-dashed border-t-2"></div>
                <span className="text-gray-600">Meta (450t)</span>
              </div>
            </div>
          </div>
          <div className="flex-1 min-h-[300px]">
            {tonsLoading ? (
              <div className="flex items-center justify-center h-full text-gray-400 text-sm gap-2">
                <div className="w-5 h-5 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
                Cargando datos de báscula...
              </div>
            ) : tonsData.length === 0 ? (
              <div className="flex items-center justify-center h-full text-gray-400 text-sm">
                Sin datos de báscula aún
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={tonsData} margin={{ top: 10, right: 0, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="colorTons" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor="#0A7AFF" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#0A7AFF" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                  <XAxis dataKey="day" tick={{ fontSize: 12, fill: '#6B7280' }} tickLine={false} axisLine={false} />
                  <YAxis tick={{ fontSize: 12, fill: '#6B7280' }} tickLine={false} axisLine={false} />
                  <Tooltip
                    contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)', padding: '10px 14px' }}
                    labelStyle={{ fontWeight: 'bold', color: '#111827', marginBottom: '4px' }}
                    formatter={(value: number, _name: string, props: any) => {
                      const viajes = props?.payload?.viajes ?? '';
                      return [
                        <span key="v">
                          <span style={{ fontSize: '18px', fontWeight: 700, fontFamily: 'monospace' }}>
                            {value.toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} t
                          </span>
                          {viajes ? <span style={{ display: 'block', fontSize: '12px', color: '#6B7280', marginTop: '2px' }}>{viajes} viajes</span> : null}
                        </span>,
                        ''
                      ];
                    }}
                    labelFormatter={(label, payload) => {
                      const fecha = payload?.[0]?.payload?.fecha ?? '';
                      if (fecha) {
                        const d = new Date(fecha + 'T12:00:00');
                        return d.toLocaleDateString('es-MX', { weekday: 'short', day: 'numeric', month: 'short' });
                      }
                      return `Día ${label}`;
                    }}
                  />
                  <ReferenceLine y={450} stroke="#9CA3AF" strokeDasharray="5 5" />
                  <Area type="monotone" dataKey="tons" stroke="#0A7AFF" strokeWidth={3} fillOpacity={1} fill="url(#colorTons)" />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

      </div>

      {/* ── THIRD ROW ─────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* Estado de la Flota — carga por unidad hoy (BÁSCULA REAL) */}
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-bold text-gray-900">Estado de la Flota</h3>
            <button className="text-sm text-blue-500 font-medium hover:text-blue-600">Ver mapa</button>
          </div>

          {porUnidad.length > 0 ? (
            /* Vista con datos de báscula: grid de unidades con toneladas */
            <div className="grid grid-cols-5 gap-2">
              {fleetStats.units.length > 0
                ? /* Usar datos de flota + enriquecer con báscula */
                  fleetStats.units.map((unit) => {
                    const basData = porUnidad.find(
                      p => p.num_eco.replace('-','').toUpperCase() === unit.eco.replace('-','').toUpperCase()
                    );
                    const tons = basData?.toneladas ?? unit.toneladas_hoy ?? 0;
                    const statusColor =
                      unit.status === 'ACTIVO'   ? 'bg-success' :
                      unit.status === 'INACTIVO'  ? 'bg-warning' : 'bg-danger';
                    return (
                      <div
                        key={unit.vehicle_id}
                        className="aspect-square rounded-lg border border-gray-200 flex flex-col items-center justify-center p-1 hover:border-blue-500 hover:shadow-md transition-all cursor-pointer group relative"
                        title={`${unit.eco} — ${tons.toFixed(1)}t cargadas hoy`}
                      >
                        <div className={`absolute top-1 right-1 w-2 h-2 rounded-full ${statusColor}`} />
                        <span className="text-xs font-bold text-gray-700 group-hover:text-blue-600">{unit.eco}</span>
                        <span className="text-[10px] text-gray-400 font-mono mt-0.5">
                          {tons > 0 ? `${tons.toFixed(1)}t` : '—'}
                        </span>
                      </div>
                    );
                  })
                : /* Si aún no hay datos de flota, mostrar solo báscula */
                  porUnidad.map((u) => (
                    <div
                      key={u.num_eco}
                      className="aspect-square rounded-lg border border-gray-200 flex flex-col items-center justify-center p-1 hover:border-blue-500 hover:shadow-md transition-all cursor-pointer group"
                    >
                      <span className="text-xs font-bold text-gray-700 group-hover:text-blue-600">{u.num_eco}</span>
                      <span className="text-[10px] text-gray-400 font-mono mt-0.5">{u.toneladas.toFixed(1)}t</span>
                    </div>
                  ))
              }
            </div>
          ) : (
            /* Sin datos de báscula todavía: fallback con estatus GPS */
            <div className="grid grid-cols-5 gap-2">
              {fleetStats.units.map((unit) => {
                const statusColor =
                  unit.status === 'ACTIVO'   ? 'bg-success' :
                  unit.status === 'INACTIVO'  ? 'bg-warning' : 'bg-danger';
                return (
                  <div
                    key={unit.vehicle_id}
                    className="aspect-square rounded-lg border border-gray-200 flex flex-col items-center justify-center p-1 hover:border-blue-500 hover:shadow-md transition-all cursor-pointer group relative"
                  >
                    <div className={`absolute top-1 right-1 w-2 h-2 rounded-full ${statusColor}`} />
                    <span className="text-xs font-bold text-gray-700 group-hover:text-blue-600">{unit.eco}</span>
                    <span className="text-[10px] text-gray-400 font-mono mt-0.5">—</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Consumo Top 3 */}
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-lg font-bold text-gray-900">Consumo (Top 3)</h3>
            <div className="bg-gray-100 p-1 rounded-lg flex text-xs font-medium">
              <button
                onClick={() => setConsumoMode('litros')}
                className={`px-3 py-1 rounded-md transition-colors ${consumoMode === 'litros' ? 'bg-white shadow-sm text-gray-900' : 'text-gray-500 hover:text-gray-900'}`}
              >
                Litros
              </button>
              <button
                onClick={() => setConsumoMode('costo')}
                className={`px-3 py-1 rounded-md transition-colors ${consumoMode === 'costo' ? 'bg-white shadow-sm text-gray-900' : 'text-gray-500 hover:text-gray-900'}`}
              >
                $ MXN
              </button>
            </div>
          </div>
          <div className="h-[250px] flex gap-2">
            {comparativoLoading ? (
              <div className="flex items-center justify-center w-full text-gray-400 text-sm">
                <div className="flex flex-col items-center gap-2">
                  <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
                  <span>Cargando histórico...</span>
                </div>
              </div>
            ) : comparativo.length === 0 ? (
              <div className="flex items-center justify-center w-full text-gray-400 text-sm flex-col gap-2">
                <Fuel className="w-8 h-8 text-gray-300" />
                <span>Registra el primer abastecimiento para ver datos aquí</span>
              </div>
            ) : (
              comparativo.map((mes) => (
                <div key={mes.periodo} className="flex-1 flex flex-col">
                  <p className="text-xs font-semibold text-gray-500 text-center mb-1">{mes.periodo}</p>
                  {mes.unidades.length === 0 ? (
                    <div className="flex-1 flex items-center justify-center text-gray-300 text-xs border border-dashed border-gray-200 rounded-lg">
                      Sin datos
                    </div>
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={mes.unidades} margin={{ top: 0, right: 4, left: -28, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                        <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#6B7280' }} axisLine={false} tickLine={false} />
                        <YAxis tick={{ fontSize: 10, fill: '#6B7280' }} axisLine={false} tickLine={false} />
                        <Tooltip
                          cursor={{ fill: '#F3F4F6' }}
                          contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)' }}
                          formatter={(v: number) =>
                            consumoMode === 'litros'
                              ? [`${v.toLocaleString('es-MX')} L`, 'Litros']
                              : [v.toLocaleString('es-MX', { style: 'currency', currency: 'MXN' }), 'Costo']
                          }
                        />
                        <Bar dataKey={consumoMode === 'litros' ? 'litros' : 'costo'} radius={[4, 4, 0, 0]}>
                          {mes.unidades.map((_: any, i: number) => (
                            <Cell key={i} fill={['#1A2B5E', '#0A7AFF', '#93C5FD'][i]} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </div>
              ))
            )}
          </div>
        </div>

        {/* Últimas Cargas de Combustible */}
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100 flex flex-col">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-bold text-gray-900">Últimas Cargas</h3>
            <button className="text-gray-400 hover:text-gray-600"><MoreVertical className="w-5 h-5" /></button>
          </div>
          <div className="flex-1 space-y-4">
            {(showAllFuel ? fuelStats.all_records : fuelStats.recent_records).map((fuel, i) => (
              <div key={fuel.id ?? i} className="flex items-center justify-between p-3 rounded-lg hover:bg-gray-50 transition-colors border border-transparent hover:border-gray-100">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-blue-50 flex items-center justify-center">
                    <Fuel className="w-5 h-5 text-blue-500" />
                  </div>
                  <div>
                    <p className="text-sm font-bold text-gray-900">
                      {vehicleEcoMap[String(fuel.vehicle_id)]
                        ? <>{vehicleEcoMap[String(fuel.vehicle_id)]} <span className="text-gray-400 font-normal text-xs font-mono">#{fuel.vehicle_id}</span></>
                        : fuel.vehicle_id
                      }
                      <span className="text-gray-400 font-normal mx-1">•</span>{' '}
                      <span className="text-gray-500 font-normal">{fuel.conductor}</span>
                    </p>
                    <p className="text-xs text-gray-500 mt-0.5">
                      {new Date(fuel.created_at + 'Z').toLocaleString('es-MX', {
                        day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'
                      })}
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-sm font-bold text-gray-900 font-mono">{fuel.liters} L</p>
                  <p className="text-xs text-gray-500 font-mono mt-0.5">
                    {(fuel.liters * fuel.price_per_liter).toLocaleString('es-MX', { style: 'currency', currency: 'MXN' })}
                  </p>
                </div>
              </div>
            ))}
          </div>
          <button
            onClick={() => setShowAllFuel(!showAllFuel)}
            className="w-full mt-4 py-2 text-sm font-medium text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
          >
            {showAllFuel
              ? 'Ver menos'
              : `Ver historial completo (${fuelStats.all_records?.length ?? 0} registros)`}
          </button>
        </div>

      </div>

      {/* ── BOTTOM ROW — Actividad de Báscula EN VIVO ─────────────────────── */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="p-6 border-b border-gray-100 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h3 className="text-lg font-bold text-gray-900">Actividad de Báscula</h3>
            <span className="px-2.5 py-0.5 rounded-full bg-success/10 text-success text-xs font-bold animate-pulse">EN VIVO</span>
            {actividadTs && (
              <span className="text-xs text-gray-400 font-mono">
                Actualizado: {actividadTs}
              </span>
            )}
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => loadBascula(true)}
              className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-blue-600 transition-colors"
              title="Actualizar ahora"
            >
              <RefreshCw className={`w-4 h-4 ${actividadLoading ? 'animate-spin text-blue-500' : ''}`} />
              {actividadLoading ? 'Actualizando...' : 'Actualizar'}
            </button>
            <button className="text-sm text-blue-500 font-medium hover:text-blue-600">Exportar CSV</button>
          </div>
        </div>

        {/* Búsqueda */}
        <div className="px-6 py-3 border-b border-gray-100 flex items-center gap-2">
          <svg className="w-4 h-4 text-gray-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="text"
            placeholder="Buscar por unidad, cliente o tipo de residuo..."
            value={busqueda}
            onChange={e => { setBusqueda(e.target.value); setPagina(1); }}
            className="w-full text-sm text-gray-700 placeholder-gray-400 bg-transparent outline-none"
          />
          {busqueda && (
            <button onClick={() => { setBusqueda(''); setPagina(1); }} className="text-gray-400 hover:text-gray-600 text-xs shrink-0">✕ Limpiar</button>
          )}
        </div>

        {actividad.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-gray-400">
            <Scale className="w-10 h-10 text-gray-200 mb-3" />
            <p className="text-sm font-medium">Sin registros de báscula hoy</p>
            <p className="text-xs mt-1">Los registros aparecerán automáticamente cada minuto</p>
          </div>
        ) : (() => {
          const q = busqueda.toLowerCase();
          const filtrados = actividad.filter(r =>
            !q ||
            (r.num_eco || r.placa || '').toLowerCase().includes(q) ||
            (r.tipo_cliente || '').toLowerCase().includes(q) ||
            (r.tipo_residuo || '').toLowerCase().includes(q)
          );
          const totalPaginas = Math.max(1, Math.ceil(filtrados.length / FILAS_POR_PAGINA));
          const paginaReal   = Math.min(pagina, totalPaginas);
          const filas        = filtrados.slice((paginaReal - 1) * FILAS_POR_PAGINA, paginaReal * FILAS_POR_PAGINA);

          return (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-gray-50 text-gray-500 text-xs uppercase tracking-wider">
                      <th className="px-6 py-4 font-semibold">Folio</th>
                      <th className="px-6 py-4 font-semibold">Unidad</th>
                      <th className="px-6 py-4 font-semibold">Cliente</th>
                      <th className="px-6 py-4 font-semibold">Entrada</th>
                      <th className="px-6 py-4 font-semibold">Salida</th>
                      <th className="px-6 py-4 font-semibold text-right">Peso Neto</th>
                      <th className="px-6 py-4 font-semibold">Tipo Residuo</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 text-sm">
                    {filas.length === 0 ? (
                      <tr>
                        <td colSpan={7} className="px-6 py-10 text-center text-gray-400 text-sm">
                          Sin resultados para "{busqueda}"
                        </td>
                      </tr>
                    ) : filas.map((event, i) => (
                      <tr key={`${event.folio}-${i}`} className="hover:bg-gray-50 transition-colors group">
                        <td className="px-6 py-4 font-mono text-gray-500">#{event.folio}</td>
                        <td className="px-6 py-4 font-bold text-gray-900">{event.num_eco || event.placa}</td>
                        <td className="px-6 py-4 text-gray-600">{event.tipo_cliente || '—'}</td>
                        <td className="px-6 py-4 font-mono text-gray-500">{event.hora_entrada}</td>
                        <td className="px-6 py-4 font-mono text-gray-500">{event.hora_salida}</td>
                        <td className="px-6 py-4 font-mono font-bold text-gray-900 text-right">
                          {event.peso_neto.toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} t
                        </td>
                        <td className="px-6 py-4">
                          <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${tipoColor(event.tipo_residuo)}`}>
                            {event.tipo_residuo || 'N/D'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr className="bg-gray-50 border-t-2 border-gray-200">
                      <td colSpan={5} className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase">
                        {busqueda
                          ? `${filtrados.length} resultado${filtrados.length !== 1 ? 's' : ''} — Total día: ${basculaHoy.viajes} viajes`
                          : `Total del día — ${basculaHoy.viajes} viajes`
                        }
                      </td>
                      <td className="px-6 py-3 font-mono font-bold text-gray-900 text-right">
                        {busqueda
                          ? `${filtrados.reduce((s, r) => s + (r.peso_neto || 0), 0).toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} t`
                          : `${basculaHoy.toneladas.toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} t`
                        }
                      </td>
                      <td />
                    </tr>
                  </tfoot>
                </table>
              </div>

              {/* Paginación */}
              {totalPaginas > 1 && (
                <div className="px-6 py-4 border-t border-gray-100 flex items-center justify-between">
                  <span className="text-xs text-gray-500">
                    Mostrando {(paginaReal - 1) * FILAS_POR_PAGINA + 1}–{Math.min(paginaReal * FILAS_POR_PAGINA, filtrados.length)} de {filtrados.length} registros
                  </span>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => setPagina(p => Math.max(1, p - 1))}
                      disabled={paginaReal === 1}
                      className="px-3 py-1.5 text-xs font-medium rounded-md border border-gray-200 text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                    >
                      ← Anterior
                    </button>
                    {Array.from({ length: totalPaginas }, (_, i) => i + 1)
                      .filter(p => p === 1 || p === totalPaginas || Math.abs(p - paginaReal) <= 1)
                      .reduce<(number | '...')[]>((acc, p, idx, arr) => {
                        if (idx > 0 && (p as number) - (arr[idx - 1] as number) > 1) acc.push('...');
                        acc.push(p);
                        return acc;
                      }, [])
                      .map((p, idx) =>
                        p === '...'
                          ? <span key={`dots-${idx}`} className="px-2 text-gray-400 text-xs">…</span>
                          : <button
                              key={p}
                              onClick={() => setPagina(p as number)}
                              className={`w-8 h-8 text-xs font-medium rounded-md transition-colors ${
                                paginaReal === p
                                  ? 'bg-blue-600 text-white'
                                  : 'border border-gray-200 text-gray-600 hover:bg-gray-50'
                              }`}
                            >{p}</button>
                      )
                    }
                    <button
                      onClick={() => setPagina(p => Math.min(totalPaginas, p + 1))}
                      disabled={paginaReal === totalPaginas}
                      className="px-3 py-1.5 text-xs font-medium rounded-md border border-gray-200 text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                    >
                      Siguiente →
                    </button>
                  </div>
                </div>
              )}
            </>
          );
        })()}
      </div>

    </div>
  );
}
