import React, { useState, useEffect, useRef } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  Info,
  CheckCircle,
  Bell,
} from 'lucide-react';

// ─── Tipos ────────────────────────────────────────────────────────────────────

type AlertItem = {
  id: string | number;
  type: 'critical' | 'warning' | 'info';
  category: string;
  title: string;
  unit: string;
  time: string;       // texto formateado para mostrar
  raw_time: string;   // ISO original para filtrar por fecha
  read: boolean;
};

// ─── Helper: normalizar ISO sin duplicar Z ────────────────────────────────────

function normalizeIso(raw: string): string {
  if (!raw) return new Date().toISOString();
  if (raw.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(raw)) return raw;
  return raw + 'Z';
}

// ─── Helper: formatear fecha ISO a texto legible ──────────────────────────────

function formatAlertTime(raw: string): string {
  if (!raw) return '';
  try {
    const d = new Date(raw);
    if (isNaN(d.getTime())) return raw;

    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffH = diffMs / 1000 / 3600;

    if (diffH < 1) return 'Hace unos minutos';
    if (diffH < 24) return `Hace ${Math.floor(diffH)} hora${Math.floor(diffH) > 1 ? 's' : ''}`;

    const yesterday = new Date(now);
    yesterday.setDate(now.getDate() - 1);
    if (d.toDateString() === yesterday.toDateString()) {
      return `Ayer, ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
    }

    return `${d.getDate()} ${d.toLocaleString('es', { month: 'short' })}, ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
  } catch {
    return raw;
  }
}

// ─── Helper: convertir alerta WS → AlertItem ─────────────────────────────────

function wsAlertToItem(msg: any): AlertItem {
  const raw_time = normalizeIso(msg.time || new Date().toISOString());
  return {
    id:       `fuel-${msg.vehicle_id || ''}-${msg.time || Date.now()}`,
    type:     'info',
    category: 'Combustible',
    title:    msg.title || 'Nuevo ticket de combustible',
    unit:     msg.unit || msg.vehicle_id || '',
    time:     formatAlertTime(raw_time),
    raw_time,
    read:     false,
  };
}

// ─── Componente principal ─────────────────────────────────────────────────────

const CATEGORIES = ['Todos', 'Rendimiento', 'Combustible', 'Operatividad', 'Báscula'];

export function Alerts() {
  const [filter, setFilter] = useState('Todos');
  const [fuelAlerts, setFuelAlerts] = useState<AlertItem[]>([]);
  const [readIds, setReadIds] = useState<Set<string | number>>(new Set());
  const wsRef = useRef<WebSocket | null>(null);

  // ── Conectar al canal /ws/alerts ──────────────────────────────────────────
  useEffect(() => {
    const socket = new WebSocket('wss://fleetops-space.com.mx/ws/alerts');

    socket.onopen = () => {};

    socket.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);

        // Estado inicial desde la DB
        if (msg.type === 'alerts_initial' && Array.isArray(msg.alerts)) {
          const items: AlertItem[] = msg.alerts.map((a: any) => {
            const raw_time = normalizeIso(a.raw_time || a.time || '');
            return { ...a, raw_time, time: formatAlertTime(raw_time) } as AlertItem;
          });
          setFuelAlerts(items);
          return;
        }

        // Nueva carga en tiempo real
        if (msg.type === 'new_fuel_alert') {
          const normalized = normalizeIso(msg.time || '');
          const diffHours = (Date.now() - new Date(normalized).getTime()) / 1000 / 3600;
          if (diffHours > 24) return;

          const item = wsAlertToItem(msg);
          setFuelAlerts((prev) => {
            if (prev.some((a) => a.id === item.id)) return prev;
            return [item, ...prev];
          });
        }
      } catch (e) {
        console.error('Error parseando WS alerts:', e);
      }
    };

    socket.onerror = (e) => console.error('🔥 WS alerts error:', e);
    socket.onclose = () => {};

    wsRef.current = socket;
    return () => socket.close();
  }, []);

  // ── Alertas con estado de leído aplicado ──────────────────────────────────
  const allAlerts: AlertItem[] = fuelAlerts.map((a) => ({
    ...a,
    read: readIds.has(a.id) ? true : a.read,
  }));

  const filteredAlerts = allAlerts.filter(
    (a) => filter === 'Todos' || a.category === filter,
  );

  const unreadCount = allAlerts.filter((a) => !a.read).length;

  const markAllRead = () => {
    setReadIds(new Set(allAlerts.map((a) => a.id)));
    setFuelAlerts((prev) => prev.map((a) => ({ ...a, read: true })));
  };

  const markOneRead = (id: string | number) => {
    setReadIds((prev) => new Set([...prev, id]));
    setFuelAlerts((prev) =>
      prev.map((a) => (a.id === id ? { ...a, read: true } : a)),
    );
  };

  return (
    <div className="p-8 max-w-[1000px] mx-auto animate-fade-in-up">
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-3">
            <Bell className="w-6 h-6 text-blue-500" />
            Centro de Alertas
            {unreadCount > 0 && (
              <span className="ml-1 px-2 py-0.5 rounded-full bg-blue-500 text-white text-xs font-bold">
                {unreadCount}
              </span>
            )}
          </h1>
          <p className="text-gray-500 mt-1">
            Monitoreo de eventos y notificaciones del sistema
          </p>
        </div>
        {unreadCount > 0 && (
          <button
            onClick={markAllRead}
            className="text-sm font-medium text-blue-600 hover:bg-blue-50 px-4 py-2 rounded-lg transition-colors"
          >
            Marcar todos como leídos
          </button>
        )}
      </div>

      {/* Filters */}
      <div className="flex gap-2 mb-8 overflow-x-auto pb-2">
        {CATEGORIES.map((cat) => (
          <button
            key={cat}
            onClick={() => setFilter(cat)}
            className={`px-4 py-2 rounded-full text-sm font-medium whitespace-nowrap transition-colors ${
              filter === cat
                ? 'bg-navy-500 text-white shadow-sm'
                : 'bg-white text-gray-600 border border-gray-200 hover:bg-gray-50'
            }`}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* Alert List */}
      <div className="space-y-4">
        {filteredAlerts.map((alert, index) => {
          const isCritical = alert.type === 'critical';
          const isWarning  = alert.type === 'warning';

          const borderColor = isCritical
            ? 'border-l-danger'
            : isWarning
            ? 'border-l-warning'
            : 'border-l-blue-500';

          const iconColor = isCritical
            ? 'text-danger'
            : isWarning
            ? 'text-warning'
            : 'text-blue-500';

          const bgClass = alert.read ? 'bg-white' : 'bg-blue-50/30';
          const Icon = isCritical ? AlertCircle : isWarning ? AlertTriangle : Info;

          return (
            <div
              key={alert.id}
              className={`rounded-xl p-5 shadow-sm border border-gray-100 border-l-4 ${borderColor} ${bgClass} flex flex-col sm:flex-row sm:items-center justify-between gap-4 transition-all hover:shadow-md animate-fade-in-up`}
              style={{ animationDelay: `${index * 50}ms` }}
            >
              <div className="flex items-start gap-4">
                <div className={`mt-1 ${iconColor}`}>
                  <Icon className="w-5 h-5" />
                </div>
                <div>
                  <div className="flex items-center gap-3 mb-1">
                    <span className="px-2 py-0.5 rounded bg-gray-100 text-gray-600 text-xs font-bold font-mono">
                      {alert.unit}
                    </span>
                    <span className="text-xs text-gray-400 font-medium">
                      {alert.time}
                    </span>
                    {!alert.read && (
                      <span className="w-2 h-2 rounded-full bg-blue-500" />
                    )}
                  </div>
                  <h3
                    className={`text-base ${
                      !alert.read
                        ? 'font-bold text-gray-900'
                        : 'font-medium text-gray-700'
                    }`}
                  >
                    {alert.title}
                  </h3>
                </div>
              </div>

              <div className="flex items-center gap-3 sm:ml-auto pl-9 sm:pl-0">
                <button className="text-sm font-medium text-blue-600 hover:text-blue-700 bg-white border border-gray-200 px-3 py-1.5 rounded-lg hover:bg-gray-50 transition-colors">
                  Ver Detalle
                </button>
                {!alert.read && (
                  <button
                    onClick={() => markOneRead(alert.id)}
                    className="text-gray-400 hover:text-gray-600 p-1.5 rounded-lg hover:bg-gray-100 transition-colors"
                    title="Marcar como leído"
                  >
                    <CheckCircle className="w-5 h-5" />
                  </button>
                )}
              </div>
            </div>
          );
        })}

        {filteredAlerts.length === 0 && (
          <div className="text-center py-16 bg-white rounded-xl border border-gray-100 border-dashed">
            <CheckCircle className="w-12 h-12 text-gray-300 mx-auto mb-3" />
            <p className="text-gray-500 font-medium">
              No hay alertas en las últimas 24 horas
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
