import React, { useState, useEffect } from 'react';
import {
  Clock,
  Activity,
  Fuel,
  Scale,
  Eye,
  ChevronRight,
  ChevronDown,
  Plus,
  X,
  FileText,
  Loader2,
  RefreshCw,
} from 'lucide-react';
import { authFetch } from '../lib/auth';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend
} from 'recharts';
import { motion, AnimatePresence } from 'framer-motion';

const API = 'https://fleetops-space.com.mx';

// Paleta de colores para cada vehículo en la gráfica
const VEHICLE_COLORS = [
  '#0A7AFF', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6',
  '#06B6D4', '#F97316', '#EC4899', '#84CC16', '#6366F1',
];

// ── Helpers de tipo de residuo (báscula) ──────────────────────────────────────
function tipoColor(tipo: string) {
  if (!tipo) return 'bg-gray-100 text-gray-600';
  const t = tipo.toLowerCase();
  if (t.includes('domiciliario')) return 'bg-blue-50 text-blue-700';
  if (t.includes('particular'))   return 'bg-purple-50 text-purple-700';
  if (t.includes('industrial'))   return 'bg-orange-50 text-orange-700';
  if (t.includes('comercial'))    return 'bg-teal-50 text-teal-700';
  return 'bg-gray-100 text-gray-600';
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function formatFecha(raw: string) {
  try {
    return new Date(raw).toLocaleString('es-MX', {
      day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit'
    });
  } catch {
    return raw;
  }
}

// ── Modal ticket ──────────────────────────────────────────────────────────────
function TicketModal({ url, onClose }: { url: string; onClose: () => void }) {
  const isPdf = url.toLowerCase().endsWith('.pdf');
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm" onClick={onClose}>
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        className="bg-white rounded-xl shadow-xl max-w-2xl w-full overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-4 border-b border-gray-100 flex justify-between items-center">
          <h3 className="font-bold text-gray-900 flex items-center gap-2">
            <FileText className="w-4 h-4 text-blue-500" />
            Ticket de Combustible
          </h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="p-4 flex items-center justify-center min-h-[400px] bg-gray-50">
          {isPdf ? (
            <iframe src={url} className="w-full h-[500px] rounded" title="Ticket PDF" />
          ) : (
            <img src={url} alt="Ticket" className="max-h-[500px] object-contain rounded-lg shadow" />
          )}
        </div>
        <div className="p-4 bg-gray-50 border-t border-gray-100 flex justify-end">
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="px-4 py-2 text-sm font-medium text-blue-600 hover:text-blue-700"
          >
            Abrir en nueva pestaña ↗
          </a>
        </div>
      </motion.div>
    </div>
  );
}

// ── Tooltip personalizado para la gráfica multi-vehículo ─────────────────────
function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const now = new Date();
  const fecha = `${String(label).padStart(2, '0')}/${String(now.getMonth() + 1).padStart(2, '0')}/${now.getFullYear()}`;
  return (
    <div className="bg-white rounded-xl shadow-lg border border-gray-100 p-3 text-sm min-w-[180px]">
      <p className="font-bold text-gray-700 mb-2">📅 {fecha}</p>
      {payload.map((entry: any) => (
        entry.value > 0 && (
          <div key={entry.dataKey} className="flex items-center justify-between gap-4 py-0.5">
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full inline-block" style={{ backgroundColor: entry.color }} />
              <span className="text-gray-600 font-medium">{entry.dataKey}</span>
            </span>
            <span className="font-mono font-bold" style={{ color: entry.color }}>
              {entry.value} L
            </span>
          </div>
        )
      ))}
    </div>
  );
}

// ── Componente principal ──────────────────────────────────────────────────────
export function VehicleDetail({ vehicleId, onNavigate }: {
  vehicleId?: string;
  onNavigate?: (page: string, vehicleId?: string) => void;
}) {
  const [activeTab, setActiveTab] = useState('operatividad');

  // ── Combustible state ─────────────────────────────────────────────────────
  const [fuelRecords, setFuelRecords]         = useState<any[]>([]);
  const [fuelLoading, setFuelLoading]         = useState(false);
  const [fuelError, setFuelError]             = useState('');
  const [ticketUrl, setTicketUrl]             = useState<string | null>(null);
  const [ticketLoading, setTicketLoading]     = useState(false);
  const [vehicleEcoMap, setVehicleEcoMap]     = useState<Record<string, string>>({});
  const [allVehicles, setAllVehicles]         = useState<{ id: string; eco: string }[]>([]);
  const [rendVehicles, setRendVehicles]       = useState<string[]>([]);
  const MAX_REND_VEHICLES = 5;  const [fuelBusqueda, setFuelBusqueda]       = useState('');
  const [fuelPagina, setFuelPagina]           = useState(1);
  const FUEL_FILAS = 10;

  // ── Gráfica multi-vehículo ────────────────────────────────────────────────
  const [chartData, setChartData]             = useState<any[]>([]);
  const [chartVehicles, setChartVehicles]     = useState<string[]>([]);
  const [chartLoading, setChartLoading]       = useState(false);

  // ── Rendimiento histórico (últimos 3 meses) ───────────────────────────────
  const [rendimientoMeses, setRendimientoMeses]   = useState<any[]>([]);
  const [rendimientoLoading, setRendimientoLoading] = useState(false);

  // ── Báscula state ─────────────────────────────────────────────────────────
  const [basculaRecords, setBasculaRecords]   = useState<any[]>([]);
  const [basculaLoading, setBasculaLoading]   = useState(false);
  const [basculaTs, setBasculaTs]             = useState('');
  const [basculaTons, setBasculaTons]         = useState(0);
  const [basculaViajes, setBasculaViajes]     = useState(0);
  const [basculaBusqueda, setBasculaBusqueda] = useState('');
  const [basculaPagina, setBasculaPagina]     = useState(1);
  const BASCULA_FILAS = 10;
  const basculaPollingRef = React.useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Presigned URL para ticket ─────────────────────────────────────────────
  const openTicket = async (rawUrl: string) => {
    try {
      setTicketLoading(true);
      const key = rawUrl.split('.amazonaws.com/')[1];
      const res = await authFetch(`${API}/api/fuel/ticket-url?key=${encodeURIComponent(key)}`);
      if (!res.ok) throw new Error('no presigned');
      const data = await res.json();
      setTicketUrl(data.url);
    } catch {
      setTicketUrl(rawUrl);
    } finally {
      setTicketLoading(false);
    }
  };

//mapa de placas
  useEffect(() => {
    authFetch(`${API}/api/fleet/vehicles`)
      .then(r => r.json())
      .then((data: any) => {
        // El endpoint puede devolver el array directo o dentro de una propiedad
        const vehicles: any[] = Array.isArray(data) ? data : (data.vehicles ?? data.units ?? []);
        const map: Record<string, string> = {};
        const list: { id: string; eco: string }[] = [];
        vehicles.forEach((v: any) => {
          const id = String(v.ras_vei_id ?? v.vehicle_id ?? '');
          const eco = v.ras_vei_eco || v.ras_vei_placa || id;
          if (id) {
            map[id] = eco;
            list.push({ id, eco });
          }
        });
        setVehicleEcoMap(map);
        setAllVehicles(list.sort((a, b) => a.eco.localeCompare(b.eco, 'es', { numeric: true })));
      })
      .catch(() => {});
  }, []);

  // La unidad actual (de la URL) siempre empieza seleccionada en el comparador
  useEffect(() => {
    if (vehicleId) setRendVehicles([vehicleId]);
  }, [vehicleId]);

  // ── Cargar historial de combustible (pestaña Combustible) ─────────────────
  useEffect(() => {
    if (activeTab !== 'combustible') return;
    setFuelLoading(true);
    setFuelError('');

    const endpoint = vehicleId
      ? `${API}/api/fuel/records/${vehicleId}`
      : `${API}/api/fuel/records`;

    authFetch(endpoint)
      .then((r) => r.json())
      .then((data) => {
        if (data.records) {
          setFuelRecords(data.records);
        } else if (data.by_unit) {
          const all: any[] = [];
          Object.values(data.by_unit as Record<string, any>).forEach((u: any) => {
            all.push(...(u.records || []));
          });
          all.sort((a, b) => new Date(b.created_at ?? b.fecha).getTime() - new Date(a.created_at ?? a.fecha).getTime());
          setFuelRecords(all);
        }
      })
      .catch(() => setFuelError('No se pudo cargar el historial de cargas.'))
      .finally(() => setFuelLoading(false));
  }, [activeTab, vehicleId]);

  // ── Rendimiento histórico: últimos 3 meses, una o varias unidades ────────
  useEffect(() => {
    if (activeTab !== 'operatividad' || rendVehicles.length === 0) return;
    setRendimientoLoading(true);

    Promise.all(
      rendVehicles.map((vid) =>
        authFetch(`${API}/api/fleet/rendimiento-historico/${encodeURIComponent(vid)}`)
          .then(r => r.json())
          .then(data => {
            const eco = vehicleEcoMap[vid] || vid;
            const meses = data.meses ?? [];
            return meses.map((m: any) => ({ ...m, unidad: eco, unidadId: vid }));
          })
          .catch(() => [])
      )
    )
      .then((resultados) => setRendimientoMeses(resultados.flat()))
      .finally(() => setRendimientoLoading(false));
  }, [activeTab, rendVehicles, vehicleEcoMap]);

  // ── Gráfica multi-vehículo: todos los vehículos del mes actual ────────────
  useEffect(() => {
    if (activeTab !== 'operatividad') return;
    setChartLoading(true);

    authFetch(`${API}/api/fuel/records`)
      .then(r => r.json())
      .then(data => {
        const byUnit: Record<string, any> = data.by_unit || {};
        const now = new Date();
        const diasDelMes = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();

        // Construir estructura base: array de 31 días con { day, eco1: 0, eco2: 0, ... }
        const dias: Record<number, Record<string, number>> = {};
        for (let d = 1; d <= diasDelMes; d++) dias[d] = {};

        const ecos: string[] = [];

        Object.values(byUnit).forEach((unit: any) => {
          const eco: string = unit.eco || unit.vehicle_id;
          if (!ecos.includes(eco)) ecos.push(eco);

          (unit.records || []).forEach((r: any) => {
            const fecha = new Date(r.fecha ?? r.created_at);
            if (
              fecha.getMonth() === now.getMonth() &&
              fecha.getFullYear() === now.getFullYear()
            ) {
              const dia = fecha.getDate();
              dias[dia][eco] = Math.round(((dias[dia][eco] || 0) + (r.liters ?? 0)) * 100) / 100;
            }
          });
        });

        // Serializar a array para recharts: [{ day: 1, TM-01: 120, TM-02: 0, ... }]
        const chartRows = Object.entries(dias).map(([day, values]) => ({
          day: Number(day),
          ...ecos.reduce((acc, eco) => ({ ...acc, [eco]: values[eco] ?? 0 }), {}),
        }));

        setChartVehicles(ecos);
        setChartData(chartRows);
      })
      .catch(() => {})
      .finally(() => setChartLoading(false));
  }, [activeTab]);

  // ── Cargar y hacer polling de báscula (pestaña Báscula) ──────────────────
  const loadBascula = React.useCallback(async (showLoader = false) => {
    if (showLoader) setBasculaLoading(true);
    try {
      // Trae todos los registros de hoy y filtra por el eco de este vehículo
      const res = await authFetch(`${API}/api/bascula/actividad?limit=500`);
      if (!res.ok) throw new Error('Error al cargar báscula');
      const data = await res.json();
      const registros: any[] = data.registros ?? [];

      // Filtrar por el eco del vehículo actual (vehicleId puede ser num_eco)
      const filtrados = vehicleId
        ? registros.filter(r => {
            const ecoR = (r.num_eco || r.placa || '').replace('-', '').toUpperCase();
            const ecoV = vehicleId.replace('-', '').toUpperCase();
            return ecoR === ecoV;
          })
        : registros;

      setBasculaRecords(filtrados);
      setBasculaTons(parseFloat(filtrados.reduce((s: number, r: any) => s + (r.peso_neto ?? 0), 0).toFixed(3)));
      setBasculaViajes(filtrados.length);
      setBasculaTs(new Date().toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' }));
    } catch (e) {
      console.error('Error cargando báscula:', e);
    } finally {
      setBasculaLoading(false);
    }
  }, [vehicleId]);

  useEffect(() => {
    if (activeTab !== 'bascula') {
      // Limpiar polling si salimos de la pestaña
      if (basculaPollingRef.current) clearInterval(basculaPollingRef.current);
      return;
    }
    loadBascula(true);
    basculaPollingRef.current = setInterval(() => loadBascula(false), 60_000);
    return () => {
      if (basculaPollingRef.current) clearInterval(basculaPollingRef.current);
    };
  }, [activeTab, loadBascula]);

  const tabs = [
    { id: 'operatividad', label: 'Operatividad', icon: Activity },
    { id: 'combustible',  label: 'Combustible',  icon: Fuel     },
    { id: 'bascula',      label: 'Báscula',       icon: Scale    },
  ];

  return (
    <div className="p-8 max-w-[1400px] mx-auto animate-fade-in-up">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm text-gray-500 mb-6">
        <span>Inicio</span>
        <ChevronRight className="w-4 h-4" />
        <span>Flota</span>
        <ChevronRight className="w-4 h-4" />
        <span className="text-gray-900 font-medium">{vehicleId || 'TM-04'}</span>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-gray-200 mb-6">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-6 py-4 text-sm font-medium border-b-2 transition-colors relative ${isActive ? 'text-blue-600 border-blue-600' : 'text-gray-500 border-transparent hover:text-gray-700 hover:border-gray-300'}`}
            >
              <Icon className="w-4 h-4" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Tab Content */}
      <div className="min-h-[400px]">
        <AnimatePresence mode="wait">

          {/* ── OPERATIVIDAD ─────────────────────────────────────────────── */}
          {activeTab === 'operatividad' && (
            <motion.div key="operatividad" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.2 }} className="space-y-6">
              <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
                <div className="p-6 border-b border-gray-100 flex flex-wrap items-center justify-between gap-3">
                  <h3 className="text-lg font-bold text-gray-900">Rendimiento Mensual</h3>
                  <span className="text-xs text-gray-400 bg-gray-50 px-3 py-1 rounded-full border border-gray-100">
                    Últimos 3 meses
                  </span>
                </div>

                {/* Selector de unidades a comparar (máx. 5) */}
                <div className="px-6 py-4 border-b border-gray-100 flex flex-wrap items-center gap-2 bg-gray-50/50">
                  <span className="text-xs font-semibold text-gray-500 mr-1">Unidades:</span>
                  {rendVehicles.map((vid, idx) => (
                    <span
                      key={vid}
                      className="flex items-center gap-1.5 text-xs font-semibold pl-2.5 pr-1.5 py-1 rounded-full border"
                      style={{
                        color: VEHICLE_COLORS[idx % VEHICLE_COLORS.length],
                        borderColor: VEHICLE_COLORS[idx % VEHICLE_COLORS.length] + '55',
                        backgroundColor: VEHICLE_COLORS[idx % VEHICLE_COLORS.length] + '14',
                      }}
                    >
                      {vehicleEcoMap[vid] || vid}
                      {rendVehicles.length > 1 && (
                        <button
                          onClick={() => setRendVehicles(prev => prev.filter(v => v !== vid))}
                          className="hover:opacity-70"
                          title="Quitar"
                        >
                          <X className="w-3 h-3" />
                        </button>
                      )}
                    </span>
                  ))}

                  {rendVehicles.length < MAX_REND_VEHICLES && allVehicles.length > 0 && (
                    <div className="relative group">
                      <button className="flex items-center gap-1 text-xs font-semibold text-blue-600 border border-dashed border-blue-300 rounded-full pl-2 pr-2.5 py-1 hover:bg-blue-50 transition-colors">
                        <Plus className="w-3 h-3" /> Agregar unidad <ChevronDown className="w-3 h-3" />
                      </button>
                      <div className="absolute left-0 top-full mt-1 w-48 max-h-64 overflow-y-auto bg-white rounded-lg shadow-lg border border-gray-100 py-1 hidden group-hover:block z-20">
                        {allVehicles
                          .filter(v => !rendVehicles.includes(v.id))
                          .map(v => (
                            <button
                              key={v.id}
                              onClick={() => setRendVehicles(prev =>
                                prev.length < MAX_REND_VEHICLES ? [...prev, v.id] : prev
                              )}
                              className="w-full text-left px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
                            >
                              {v.eco}
                            </button>
                          ))}
                      </div>
                    </div>
                  )}
                  {rendVehicles.length >= MAX_REND_VEHICLES && (
                    <span className="text-[11px] text-gray-400">Máximo {MAX_REND_VEHICLES} unidades</span>
                  )}
                </div>

                <div className="overflow-x-auto">
                  {rendimientoLoading ? (
                    <div className="flex items-center justify-center py-16 gap-3 text-gray-400">
                      <Loader2 className="w-5 h-5 animate-spin" />
                      <span>Cargando métricas...</span>
                    </div>
                  ) : rendimientoMeses.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-16 text-gray-400">
                      <Activity className="w-10 h-10 mb-3 text-gray-200" />
                      <p className="font-medium text-gray-500">Sin datos históricos disponibles</p>
                      <p className="text-sm mt-1">Los datos aparecerán una vez que se procesen los KM del vehículo.</p>
                    </div>
                  ) : (
                    <table className="w-full text-left border-collapse">
                      <thead>
                        <tr className="bg-gray-50 text-gray-500 text-xs uppercase tracking-wider">
                          {rendVehicles.length > 1 && (
                            <th className="px-6 py-4 font-semibold">Unidad</th>
                          )}
                          <th className="px-6 py-4 font-semibold">Mes</th>
                          <th className="px-6 py-4 font-semibold text-right">Toneladas</th>
                          <th className="px-6 py-4 font-semibold text-right">KM Prod</th>
                          <th className="px-6 py-4 font-semibold text-right">KM Trasl</th>
                          <th className="px-6 py-4 font-semibold text-right">Total KM</th>
                          <th className="px-6 py-4 font-semibold text-right">Litros</th>
                          <th className="px-6 py-4 font-semibold text-right text-blue-600">Rendimiento</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100 text-sm font-mono">
                        {rendimientoMeses.map((row) => {
                          const rend = row.km_por_litro ?? 0;
                          const rendColor =
                            rend <= 0      ? 'text-gray-400'
                            : rend < 1.5   ? 'text-red-500'
                            : rend < 1.8   ? 'text-yellow-500'
                            : 'text-blue-600';
                          const colorIdx = rendVehicles.indexOf(row.unidadId);
                          return (
                            <tr key={`${row.unidadId}-${row.periodo}`} className="hover:bg-gray-50">
                              {rendVehicles.length > 1 && (
                                <td className="px-6 py-4 font-sans">
                                  <span
                                    className="inline-flex items-center gap-1.5 font-semibold"
                                    style={{ color: VEHICLE_COLORS[colorIdx % VEHICLE_COLORS.length] }}
                                  >
                                    <span
                                      className="w-2 h-2 rounded-full inline-block"
                                      style={{ backgroundColor: VEHICLE_COLORS[colorIdx % VEHICLE_COLORS.length] }}
                                    />
                                    {row.unidad}
                                  </span>
                                </td>
                              )}
                              <td className="px-6 py-4 font-sans font-medium text-gray-900 capitalize">
                                {row.periodo}
                              </td>
                              <td className="px-6 py-4 text-right">
                                {row.toneladas > 0
                                  ? `${Number(row.toneladas).toLocaleString('es-MX', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} t`
                                  : <span className="text-gray-300">—</span>
                                }
                              </td>
                              <td className="px-6 py-4 text-right">
                                {row.km_prod > 0
                                  ? Number(row.km_prod).toLocaleString('es-MX', { maximumFractionDigits: 0 })
                                  : <span className="text-gray-300">—</span>
                                }
                              </td>
                              <td className="px-6 py-4 text-right">
                                {row.km_trasl > 0
                                  ? Number(row.km_trasl).toLocaleString('es-MX', { maximumFractionDigits: 0 })
                                  : <span className="text-gray-300">—</span>
                                }
                              </td>
                              <td className="px-6 py-4 text-right font-bold text-gray-900">
                                {row.km_total > 0
                                  ? Number(row.km_total).toLocaleString('es-MX', { maximumFractionDigits: 0 })
                                  : <span className="text-gray-300 font-normal">—</span>
                                }
                              </td>
                              <td className="px-6 py-4 text-right text-gray-600">
                                {row.diesel_lts > 0
                                  ? `${Number(row.diesel_lts).toLocaleString('es-MX', { maximumFractionDigits: 0 })} L`
                                  : <span className="text-gray-300">—</span>
                                }
                              </td>
                              <td className={`px-6 py-4 text-right font-bold ${rendColor}`}>
                                {rend > 0 ? `${rend.toFixed(2)} km/lt` : <span className="text-gray-300 font-normal">—</span>}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>

              {/* ── GRÁFICA MULTI-VEHÍCULO ──────────────────────────────── */}
              <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
                <div className="flex items-center justify-between mb-6">
                  <h3 className="text-lg font-bold text-gray-900">
                    Evolución diaria de litros — Toda la flota
                  </h3>
                  <span className="text-xs text-gray-400 bg-gray-50 px-3 py-1 rounded-full border border-gray-100">
                    {new Date().toLocaleString('es-MX', { month: 'long', year: 'numeric' })}
                  </span>
                </div>

                {chartLoading ? (
                  <div className="h-[300px] flex items-center justify-center gap-3 text-gray-400">
                    <Loader2 className="w-5 h-5 animate-spin" />
                    <span>Cargando datos...</span>
                  </div>
                ) : chartData.length === 0 ? (
                  <div className="h-[300px] flex flex-col items-center justify-center text-gray-400">
                    <Fuel className="w-10 h-10 mb-3 text-gray-300" />
                    <p className="font-medium text-gray-500">Sin datos de combustible este mes</p>
                  </div>
                ) : (
                  <div className="h-[300px]">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={chartData}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                        <XAxis
                          dataKey="day"
                          tick={{ fontSize: 12, fill: '#6B7280' }}
                          axisLine={false}
                          tickLine={false}
                        />
                        <YAxis
                          tick={{ fontSize: 12, fill: '#6B7280' }}
                          axisLine={false}
                          tickLine={false}
                          unit=" L"
                        />
                        <Tooltip content={<CustomTooltip />} />
                        <Legend
                          wrapperStyle={{ fontSize: '12px', paddingTop: '16px' }}
                          iconType="circle"
                          iconSize={8}
                        />
                        {chartVehicles.map((eco, idx) => (
                          <Line
                            key={eco}
                            type="monotone"
                            dataKey={eco}
                            stroke={VEHICLE_COLORS[idx % VEHICLE_COLORS.length]}
                            strokeWidth={2}
                            dot={false}
                            activeDot={{ r: 5, strokeWidth: 2, stroke: '#fff' }}
                          />
                        ))}
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </div>
            </motion.div>
          )}

          {/* ── COMBUSTIBLE ──────────────────────────────────────────────── */}
          {activeTab === 'combustible' && (
            <motion.div key="combustible" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.2 }} className="space-y-6">

              <div className="flex justify-between items-center">
                <h3 className="text-lg font-bold text-gray-900">Historial de Cargas</h3>
                <button
                  onClick={() => onNavigate?.('nueva-carga')}
                  className="px-4 py-2 bg-blue-500 text-white rounded-lg font-medium text-sm hover:bg-blue-600 transition-colors"
                >
                  Nueva Carga
                </button>
              </div>

              <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
                {fuelLoading ? (
                  <div className="flex items-center justify-center py-20 gap-3 text-gray-400">
                    <Loader2 className="w-5 h-5 animate-spin" />
                    <span>Cargando registros...</span>
                  </div>
                ) : fuelError ? (
                  <div className="flex items-center justify-center py-20 text-red-400">
                    {fuelError}
                  </div>
                ) : fuelRecords.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-20 text-gray-400">
                    <Fuel className="w-10 h-10 mb-3 text-gray-300" />
                    <p className="font-medium text-gray-500">Sin registros de combustible</p>
                    <p className="text-sm mt-1">Las cargas registradas aparecerán aquí.</p>
                  </div>
                ) : (() => {
                  const q = fuelBusqueda.toLowerCase();
                  const filtrados = fuelRecords.filter(r =>
                    !q ||
                    (vehicleEcoMap[String(r.vehicle_id)] || r.vehicle_id || '').toLowerCase().includes(q) ||
                    (r.conductor   || '').toLowerCase().includes(q) ||
                    (r.proveedor   || '').toLowerCase().includes(q)
                  );
                  const totalPaginas = Math.max(1, Math.ceil(filtrados.length / FUEL_FILAS));
                  const paginaReal   = Math.min(fuelPagina, totalPaginas);
                  const filas        = filtrados.slice((paginaReal - 1) * FUEL_FILAS, paginaReal * FUEL_FILAS);

                  return (
                    <>
                      {/* Buscador */}
                      <div className="px-6 py-3 border-b border-gray-100 flex items-center gap-2">
                        <svg className="w-4 h-4 text-gray-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                        </svg>
                        <input
                          type="text"
                          placeholder="Buscar por unidad, operador o proveedor..."
                          value={fuelBusqueda}
                          onChange={e => { setFuelBusqueda(e.target.value); setFuelPagina(1); }}
                          className="w-full text-sm text-gray-700 placeholder-gray-400 bg-transparent outline-none"
                        />
                        {fuelBusqueda && (
                          <button
                            onClick={() => { setFuelBusqueda(''); setFuelPagina(1); }}
                            className="text-gray-400 hover:text-gray-600 text-xs shrink-0"
                          >
                            ✕ Limpiar
                          </button>
                        )}
                      </div>

                      <div className="overflow-x-auto">
                        <table className="w-full text-left border-collapse">
                          <thead>
                            <tr className="bg-gray-50 text-gray-500 text-xs uppercase tracking-wider">
                              <th className="px-6 py-4 font-semibold">Fecha</th>
                              <th className="px-6 py-4 font-semibold">Placa</th>
                              <th className="px-6 py-4 font-semibold text-right">Litros</th>
                              <th className="px-6 py-4 font-semibold text-right">Precio/Lt</th>
                              <th className="px-6 py-4 font-semibold text-right">Total</th>
                              <th className="px-6 py-4 font-semibold text-right">Odómetro</th>
                              <th className="px-6 py-4 font-semibold">Operador</th>
                              <th className="px-6 py-4 font-semibold text-center">Ticket</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-gray-100 text-sm">
                            {filas.length === 0 ? (
                              <tr>
                                <td colSpan={8} className="px-6 py-10 text-center text-gray-400 text-sm">
                                  Sin resultados para "{fuelBusqueda}"
                                </td>
                              </tr>
                            ) : filas.map((row, i) => {
                              const total = (row.liters ?? 0) * (row.price_per_liter ?? 0);
                              const hasTicket = !!row.foto_ticket_url;
                              return (
                                <tr key={row.id ?? i} className="hover:bg-gray-50">
                                  <td className="px-6 py-4 text-gray-600">{formatFecha(row.fecha ?? row.created_at)}</td>
                                  <td className="px-6 py-4">
                                    <span className="font-mono text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded">
                                      {vehicleEcoMap[String(row.vehicle_id)] || row.vehicle_id || '—'}
                                    </span>
                                  </td>
                                  <td className="px-6 py-4 text-right font-mono font-bold text-gray-900">{row.liters} L</td>
                                  <td className="px-6 py-4 text-right font-mono text-gray-500">${(row.price_per_liter ?? 0).toFixed(2)}</td>
                                  <td className="px-6 py-4 text-right font-mono font-bold text-blue-600">${total.toLocaleString('es-MX', { minimumFractionDigits: 2 })}</td>
                                  <td className="px-6 py-4 text-right font-mono text-gray-500">
                                    {row.odometro_actual ? `${Number(row.odometro_actual).toLocaleString('es-MX')} km` : '—'}
                                  </td>
                                  <td className="px-6 py-4 text-gray-600">{row.conductor || '—'}</td>
                                  <td className="px-6 py-4 text-center">
                                    {hasTicket ? (
                                      <button
                                        onClick={() => openTicket(row.foto_ticket_url)}
                                        className="text-blue-400 hover:text-blue-600 transition-colors inline-flex items-center justify-center"
                                        title="Ver ticket"
                                        disabled={ticketLoading}
                                      >
                                        {ticketLoading
                                          ? <Loader2 className="w-5 h-5 animate-spin" />
                                          : <Eye className="w-5 h-5" />
                                        }
                                      </button>
                                    ) : (
                                      <span className="text-gray-300 inline-flex items-center justify-center" title="Sin ticket">
                                        <Eye className="w-5 h-5" />
                                      </span>
                                    )}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                          <tfoot>
                            <tr className="bg-gray-50 border-t-2 border-gray-200">
                              <td colSpan={2} className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase">
                                {fuelBusqueda
                                  ? `${filtrados.length} resultado${filtrados.length !== 1 ? 's' : ''}`
                                  : `${fuelRecords.length} registro${fuelRecords.length !== 1 ? 's' : ''}`
                                }
                              </td>
                              <td className="px-6 py-3 font-mono font-bold text-gray-900 text-right">
                                {filtrados.reduce((s, r) => s + (r.liters ?? 0), 0).toLocaleString('es-MX', { maximumFractionDigits: 0 })} L
                              </td>
                              <td />
                              <td className="px-6 py-3 font-mono font-bold text-blue-600 text-right">
                                ${filtrados.reduce((s, r) => s + ((r.liters ?? 0) * (r.price_per_liter ?? 0)), 0).toLocaleString('es-MX', { minimumFractionDigits: 2 })}
                              </td>
                              <td colSpan={3} />
                            </tr>
                          </tfoot>
                        </table>
                      </div>

                      {/* Paginación */}
                      {totalPaginas > 1 && (
                        <div className="px-6 py-4 border-t border-gray-100 flex items-center justify-between">
                          <span className="text-xs text-gray-500">
                            Mostrando {(paginaReal - 1) * FUEL_FILAS + 1}–{Math.min(paginaReal * FUEL_FILAS, filtrados.length)} de {filtrados.length} registros
                          </span>
                          <div className="flex items-center gap-1">
                            <button
                              onClick={() => setFuelPagina(p => Math.max(1, p - 1))}
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
                                      onClick={() => setFuelPagina(p as number)}
                                      className={`w-8 h-8 text-xs font-medium rounded-md transition-colors ${
                                        paginaReal === p
                                          ? 'bg-blue-600 text-white'
                                          : 'border border-gray-200 text-gray-600 hover:bg-gray-50'
                                      }`}
                                    >{p}</button>
                              )
                            }
                            <button
                              onClick={() => setFuelPagina(p => Math.min(totalPaginas, p + 1))}
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
            </motion.div>
          )}

          {/* ── BÁSCULA ──────────────────────────────────────────────────── */}
          {activeTab === 'bascula' && (
            <motion.div key="bascula" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.2 }} className="space-y-6">

              {/* KPIs rápidos */}
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Toneladas Hoy</p>
                  <p className="text-2xl font-bold text-gray-900 font-mono tabular-nums">
                    {basculaTons.toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    <span className="text-base text-gray-400 font-sans ml-1">t</span>
                  </p>
                </div>
                <div className="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Viajes Hoy</p>
                  <p className="text-2xl font-bold text-gray-900 font-mono tabular-nums">
                    {basculaViajes}
                    <span className="text-base text-gray-400 font-sans ml-1">viajes</span>
                  </p>
                </div>
              </div>

              {/* Tabla */}
              <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">

                {/* Header */}
                <div className="p-6 border-b border-gray-100 flex items-center justify-between">
                  <div>
                    <h3 className="text-lg font-bold text-gray-900">Registros de Báscula</h3>
                    <p className="text-xs text-gray-400 mt-0.5">Solo registros del día actual</p>
                  </div>
                  <div className="flex items-center gap-3">
                    {basculaTs && (
                      <span className="text-xs text-gray-400 font-mono">Actualizado: {basculaTs}</span>
                    )}
                    <button
                      onClick={() => loadBascula(true)}
                      className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-blue-600 transition-colors"
                    >
                      <RefreshCw className={`w-4 h-4 ${basculaLoading ? 'animate-spin text-blue-500' : ''}`} />
                      {basculaLoading ? 'Actualizando...' : 'Actualizar'}
                    </button>
                  </div>
                </div>

                {/* Buscador */}
                <div className="px-6 py-3 border-b border-gray-100 flex items-center gap-2">
                  <svg className="w-4 h-4 text-gray-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                  <input
                    type="text"
                    placeholder="Buscar por folio, cliente o tipo de residuo..."
                    value={basculaBusqueda}
                    onChange={e => { setBasculaBusqueda(e.target.value); setBasculaPagina(1); }}
                    className="w-full text-sm text-gray-700 placeholder-gray-400 bg-transparent outline-none"
                  />
                  {basculaBusqueda && (
                    <button
                      onClick={() => { setBasculaBusqueda(''); setBasculaPagina(1); }}
                      className="text-gray-400 hover:text-gray-600 text-xs shrink-0"
                    >
                      ✕ Limpiar
                    </button>
                  )}
                </div>

                {basculaLoading && basculaRecords.length === 0 ? (
                  <div className="flex items-center justify-center py-20 gap-3 text-gray-400">
                    <Loader2 className="w-5 h-5 animate-spin" />
                    <span>Cargando registros de báscula...</span>
                  </div>
                ) : basculaRecords.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-20 text-gray-400">
                    <Scale className="w-10 h-10 mb-3 text-gray-200" />
                    <p className="font-medium text-gray-500">Sin registros de báscula hoy</p>
                    <p className="text-sm mt-1">Los registros aparecerán automáticamente cada minuto</p>
                  </div>
                ) : (() => {
                  const q = basculaBusqueda.toLowerCase();
                  const filtrados = basculaRecords.filter(r =>
                    !q ||
                    String(r.folio || '').toLowerCase().includes(q) ||
                    (r.tipo_cliente  || '').toLowerCase().includes(q) ||
                    (r.tipo_residuo  || '').toLowerCase().includes(q)
                  );
                  const totalPaginas = Math.max(1, Math.ceil(filtrados.length / BASCULA_FILAS));
                  const paginaReal   = Math.min(basculaPagina, totalPaginas);
                  const filas        = filtrados.slice((paginaReal - 1) * BASCULA_FILAS, paginaReal * BASCULA_FILAS);

                  return (
                    <>
                      <div className="overflow-x-auto">
                        <table className="w-full text-left border-collapse">
                          <thead>
                            <tr className="bg-gray-50 text-gray-500 text-xs uppercase tracking-wider">
                              <th className="px-6 py-4 font-semibold">Folio</th>
                              <th className="px-6 py-4 font-semibold">Entrada</th>
                              <th className="px-6 py-4 font-semibold">Salida</th>
                              <th className="px-6 py-4 font-semibold text-right">Entrada (kg)</th>
                              <th className="px-6 py-4 font-semibold text-right">Salida (kg)</th>
                              <th className="px-6 py-4 font-semibold text-right">Neto (t)</th>
                              <th className="px-6 py-4 font-semibold">Cliente</th>
                              <th className="px-6 py-4 font-semibold">Tipo Residuo</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-gray-100 text-sm">
                            {filas.length === 0 ? (
                              <tr>
                                <td colSpan={8} className="px-6 py-10 text-center text-gray-400 text-sm">
                                  Sin resultados para "{basculaBusqueda}"
                                </td>
                              </tr>
                            ) : filas.map((row, i) => (
                              <tr key={`${row.folio}-${i}`} className="hover:bg-gray-50 transition-colors">
                                <td className="px-6 py-4 font-mono text-gray-500">#{row.folio}</td>
                                <td className="px-6 py-4 font-mono text-gray-500">{row.hora_entrada || '—'}</td>
                                <td className="px-6 py-4 font-mono text-gray-500">{row.hora_salida || '—'}</td>
                                <td className="px-6 py-4 text-right font-mono text-gray-500">
                                  {(row.peso_entrada ?? 0).toLocaleString('es-MX')}
                                </td>
                                <td className="px-6 py-4 text-right font-mono text-gray-500">
                                  {(row.peso_salida ?? 0).toLocaleString('es-MX')}
                                </td>
                                <td className="px-6 py-4 text-right font-mono font-bold text-gray-900">
                                  {(row.peso_neto ?? 0).toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                </td>
                                <td className="px-6 py-4 text-gray-600">{row.tipo_cliente || '—'}</td>
                                <td className="px-6 py-4">
                                  <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${tipoColor(row.tipo_residuo)}`}>
                                    {row.tipo_residuo || 'N/D'}
                                  </span>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                          <tfoot>
                            <tr className="bg-gray-50 border-t-2 border-gray-200">
                              <td colSpan={5} className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase">
                                {basculaBusqueda
                                  ? `${filtrados.length} resultado${filtrados.length !== 1 ? 's' : ''} — Total día: ${basculaViajes} viajes`
                                  : `Total del día — ${basculaViajes} viajes`
                                }
                              </td>
                              <td className="px-6 py-3 font-mono font-bold text-gray-900 text-right">
                                {basculaBusqueda
                                  ? `${filtrados.reduce((s, r) => s + (r.peso_neto ?? 0), 0).toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} t`
                                  : `${basculaTons.toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} t`
                                }
                              </td>
                              <td colSpan={2} />
                            </tr>
                          </tfoot>
                        </table>
                      </div>

                      {/* Paginación */}
                      {totalPaginas > 1 && (
                        <div className="px-6 py-4 border-t border-gray-100 flex items-center justify-between">
                          <span className="text-xs text-gray-500">
                            Mostrando {(paginaReal - 1) * BASCULA_FILAS + 1}–{Math.min(paginaReal * BASCULA_FILAS, filtrados.length)} de {filtrados.length} registros
                          </span>
                          <div className="flex items-center gap-1">
                            <button
                              onClick={() => setBasculaPagina(p => Math.max(1, p - 1))}
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
                                      onClick={() => setBasculaPagina(p as number)}
                                      className={`w-8 h-8 text-xs font-medium rounded-md transition-colors ${
                                        paginaReal === p
                                          ? 'bg-blue-600 text-white'
                                          : 'border border-gray-200 text-gray-600 hover:bg-gray-50'
                                      }`}
                                    >{p}</button>
                              )
                            }
                            <button
                              onClick={() => setBasculaPagina(p => Math.min(totalPaginas, p + 1))}
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
            </motion.div>
          )}

        </AnimatePresence>
      </div>

      {/* Modal ticket */}
      <AnimatePresence>
        {ticketUrl && (
          <TicketModal url={ticketUrl} onClose={() => setTicketUrl(null)} />
        )}
      </AnimatePresence>
    </div>
  );
}
