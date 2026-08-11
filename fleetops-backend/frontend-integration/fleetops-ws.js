/**
 * fleetops-ws.js
 * ─────────────────────────────────────────────────────────────────────────────
 * Cliente WebSocket para conectar el frontend (React/Next.js de flops) 
 * con el backend Python de FleetOps.
 *
 * USO:
 *   import { FleetOpsWS } from './fleetops-ws';
 *
 *   const ws = new FleetOpsWS('ws://localhost:8000');
 *   ws.onFleetUpdate(payload => { ... actualizar estado React ... });
 *   ws.connect('fleet');
 * ─────────────────────────────────────────────────────────────────────────────
 */

const WS_CHANNELS = {
  fleet:   '/ws/fleet',    // Dashboard + Flota
  fuel:    '/ws/fuel',     // Combustible
  reports: '/ws/reports',  // Reportes
  alerts:  '/ws/alerts',   // Alertas
  all:     '/ws/all',      // Todo (debug)
};

export class FleetOpsWS {
  constructor(baseUrl = 'ws://localhost:8000') {
    this.baseUrl   = baseUrl.replace(/^http/, 'ws');
    this._sockets  = {};
    this._handlers = {
      fleet_update:    [],
      fuel_update:     [],
      reports_update:  [],
      alerta_rendimiento: [],
      connected:       [],
      error:           [],
    };
    this._reconnectDelay = 3000; // ms
  }

  // ── Conexión ──────────────────────────────────────────────────────────────

  connect(channel = 'fleet') {
    if (this._sockets[channel]?.readyState === WebSocket.OPEN) return;

    const url = `${this.baseUrl}${WS_CHANNELS[channel]}`;
    const ws  = new WebSocket(url);
    this._sockets[channel] = ws;

    ws.onopen = () => {
      console.log(`[FleetOps WS] Conectado al canal "${channel}"`);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this._dispatch(data);
      } catch (e) {
        console.error('[FleetOps WS] Error parseando mensaje:', e);
      }
    };

    ws.onerror = (err) => {
      console.error(`[FleetOps WS] Error en canal "${channel}":`, err);
      this._dispatch({ type: 'error', channel, error: err });
    };

    ws.onclose = () => {
      console.warn(`[FleetOps WS] Desconectado del canal "${channel}". Reconectando en ${this._reconnectDelay}ms...`);
      setTimeout(() => this.connect(channel), this._reconnectDelay);
    };
  }

  connectAll() {
    Object.keys(WS_CHANNELS).forEach(ch => this.connect(ch));
  }

  disconnect(channel) {
    if (this._sockets[channel]) {
      this._sockets[channel].onclose = null; // evitar reconexión
      this._sockets[channel].close();
      delete this._sockets[channel];
    }
  }

  disconnectAll() {
    Object.keys(this._sockets).forEach(ch => this.disconnect(ch));
  }

  // ── Solicitar refresh explícito al servidor ───────────────────────────────

  requestRefresh(channel = 'fleet') {
    const ws = this._sockets[channel];
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ action: 'refresh' }));
    }
  }

  // ── Handlers ──────────────────────────────────────────────────────────────

  /** Recibe actualizaciones completas de flota (Dashboard, pestaña Flota). */
  onFleetUpdate(fn) {
    this._handlers.fleet_update.push(fn);
    return this; // chainable
  }

  /** Recibe actualizaciones de combustible. */
  onFuelUpdate(fn) {
    this._handlers.fuel_update.push(fn);
    return this;
  }

  /** Recibe reportes actualizados. */
  onReportsUpdate(fn) {
    this._handlers.reports_update.push(fn);
    return this;
  }

  /** Recibe alertas de rendimiento bajo. */
  onAlert(fn) {
    this._handlers.alerta_rendimiento.push(fn);
    return this;
  }

  onConnected(fn) {
    this._handlers.connected.push(fn);
    return this;
  }

  onError(fn) {
    this._handlers.error.push(fn);
    return this;
  }

  // ── Dispatcher interno ────────────────────────────────────────────────────

  _dispatch(data) {
    const type = data.type || '';

    // fleet_update y fleet_initial ambos alimentan el mismo handler
    if (type === 'fleet_update' || type === 'fleet_initial' || type === 'all_initial') {
      this._handlers.fleet_update.forEach(fn => fn(data));
    }
    if (type === 'fuel_update' || type === 'fuel_initial') {
      this._handlers.fuel_update.forEach(fn => fn(data));
    }
    if (type === 'reports_update' || type === 'reports_initial') {
      this._handlers.reports_update.forEach(fn => fn(data));
    }
    if (type === 'alerta_rendimiento') {
      this._handlers.alerta_rendimiento.forEach(fn => fn(data));
    }
    if (type === 'connected') {
      this._handlers.connected.forEach(fn => fn(data));
    }
    if (type === 'error') {
      this._handlers.error.forEach(fn => fn(data));
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// React Hook — para usar directamente en componentes
// ─────────────────────────────────────────────────────────────────────────────

/**
 * useFleetOps(channel)
 * Hook de React que maneja la conexión WS y retorna el último estado recibido.
 *
 * Ejemplo:
 *   const { data, connected } = useFleetOps('fleet');
 *   // data.units → lista de unidades con GPS + métricas
 *   // data.dashboard → resumen ejecutivo
 */
export function useFleetOps(channel = 'fleet', baseUrl = 'ws://localhost:8000') {
  // (Requiere React importado en el proyecto)
  const { useState, useEffect, useRef } = window.React ?? require('react');

  const [data, setData]           = useState(null);
  const [connected, setConnected] = useState(false);
  const wsRef                     = useRef(null);

  useEffect(() => {
    const client = new FleetOpsWS(baseUrl);
    wsRef.current = client;

    client
      .onFleetUpdate(payload  => { setData(payload); setConnected(true); })
      .onFuelUpdate(payload   => { setData(payload); setConnected(true); })
      .onReportsUpdate(payload => { setData(payload); setConnected(true); })
      .onConnected(() => setConnected(true))
      .onError(() => setConnected(false));

    client.connect(channel);

    return () => client.disconnectAll();
  }, [channel, baseUrl]);

  const refresh = () => wsRef.current?.requestRefresh(channel);

  return { data, connected, refresh };
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers para mapear payload del backend → props del frontend (flops)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * mapUnitToFlotaCard(unit)
 * Convierte una unidad del payload WS al formato que espera
 * el componente de tarjeta de unidad en el frontend.
 */
export function mapUnitToFlotaCard(unit) {
  return {
    id:           unit.vehicle_id,
    eco:          unit.eco,
    placa:        unit.placa,
    descripcion:  unit.descripcion,
    status:       unit.status,           // 'ACTIVO' | 'INACTIVO' | 'SIN_GPS'
    gpsDate:      unit.gps_date,
    lat:          unit.lat,
    lng:          unit.lng,
    velocidad:    unit.velocidad,
    // Operatividad del día
    kmHoy:        unit.km_hoy ?? 0,
    horasHoy:     unit.t_prod_hrs ?? 0,
    tonsHoy:      unit.toneladas ?? 0,
    ltsHoy:       unit.diesel_lts ?? 0,
    // Rendimiento
    kmPorLitro:   unit.km_por_litro ?? 0,
    alertaNivel:  unit.alerta_rendimiento ?? 'normal',
    // Mensual
    kmMes:        unit.km_total ?? 0,
    tonsMes:      unit.toneladas ?? 0,
    ltsMes:       unit.total_lts ?? 0,
    costoMes:     unit.total_importe ?? 0,
  };
}

/**
 * mapDashboardSummary(payload)
 * Convierte el resumen del dashboard al formato de las tarjetas KPI.
 */
export function mapDashboardSummary(payload) {
  const d = payload?.dashboard ?? {};
  return {
    toneladas:         d.toneladas_mes     ?? 0,
    promedioHrs:       d.promedio_hrs_rutas ?? 0,
    promedioKm:        d.promedio_km_rutas  ?? 0,
    consumoCombustible: d.consumo_combustible_lts ?? 0,
    personalOperativo: d.personal_operativo ?? 159,
    unidadesActivas:   payload?.active_units  ?? 0,
    unidadesInactivas: payload?.inactive_units ?? 0,
    totalUnidades:     payload?.total_units   ?? 0,
    periodo:           d.periodo ?? '',
  };
}
