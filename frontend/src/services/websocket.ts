export type FuelRecord = {
  id: string;
  vehicle_id: string;
  conductor: string;
  proveedor: string;
  liters: number;
  price_per_liter: number;
  fecha: string;
  created_at: string;
};

export type FleetUnit = {
  vehicle_id: string;
  eco: string;
  km_por_litro: number;
  diesel_lts: number;
  total_importe: number;
  // báscula
  toneladas_hoy: number;
  status: string;
};

export type FuelStats = {
  total_liters: number;
  total_cost: number;
  recent_records: FuelRecord[];
  all_records: FuelRecord[];
};

export type FleetStats = {
  active_units: number;
  inactive_units: number;
  total_units: number;
  total_km_hoy: number;
  units: FleetUnit[];
};

// ── Tipos de báscula ──────────────────────────────────────────────────────────

export type BascularRecord = {
  folio: number | string;
  placa: string;
  num_eco: string;
  fecha: string;
  hora_entrada: string;
  hora_salida: string;
  peso_entrada: number;
  peso_salida: number;
  peso_neto: number;
  tipo_cliente: string;
  tipo_residuo: string;
};

export type TonelajeDiarioPoint = {
  fecha: string;    // "2026-05-14"
  day: string;      // "14" (para el eje X del gráfico)
  tons: number;
  viajes: number;
};

export type BasculaHoy = {
  fecha: string;
  toneladas: number;
  viajes: number;
};

export type BasculaPorUnidad = {
  num_eco: string;
  toneladas: number;
  viajes: number;
};

// ── WebSocket: combustible ────────────────────────────────────────────────────

export const connectFuelSocket = (onMessage: (data: FuelStats) => void): WebSocket => {
  const socket = new WebSocket('ws://localhost:8000/ws/fuel');
  socket.onopen = () => console.log('🟢 WebSocket conectado (fuel)');
  socket.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === 'connected') return;
      if (data.type === 'fuel_initial' || data.type === 'fuel_update') {
        const records: FuelRecord[] = data.records ?? [];
        const sorted = [...records].sort(
          (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        );
        const todayStr = new Date().toDateString();
        const todayRecords = records.filter(r => {
          const fecha = r.fecha || r.created_at;
          return fecha ? new Date(fecha).toDateString() === todayStr : false;
        });
        const total_liters = todayRecords.reduce((sum, r) => sum + (r.liters ?? 0), 0);
        const total_cost   = todayRecords.reduce((sum, r) => sum + ((r.liters ?? 0) * (r.price_per_liter ?? 0)), 0);
        onMessage({
          total_liters,
          total_cost,
          recent_records: sorted.slice(0, 5),
          all_records: sorted,
        });
      }
    } catch (error) {
      console.error('❌ Error parseando WS (fuel):', error);
    }
  };
  socket.onerror = (e) => console.error('🔥 WS error (fuel):', e);
  socket.onclose = () => console.log('🔴 WebSocket cerrado (fuel)');
  return socket;
};

// ── WebSocket: flota ──────────────────────────────────────────────────────────

export const connectFleetSocket = (
  onMessage: (data: FleetStats) => void,
  // Callback opcional: cuando llega un bascula_update por WS de alertas
  onBasculaUpdate?: (data: { toneladas_hoy: number; viajes_hoy: number }) => void,
): WebSocket => {
  const socket = new WebSocket('ws://localhost:8000/ws/fleet');
  socket.onopen = () => console.log('🟢 WebSocket conectado (fleet)');
  socket.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === 'connected') return;

      // Evento de actualización de báscula emitido por el scheduler
      if (data.type === 'bascula_update' && onBasculaUpdate) {
        onBasculaUpdate({
          toneladas_hoy: data.toneladas_hoy ?? 0,
          viajes_hoy:    data.viajes_hoy   ?? 0,
        });
        return;
      }

      if (data.type === 'fleet_update' || data.type === 'fleet_initial' || data.type === 'all_initial') {
        const units: FleetUnit[] = (data.units ?? [])
          .filter((u: any) => u.diesel_lts > 0 || u.km_por_litro > 0 || u.toneladas > 0)
          .map((u: any) => ({
            vehicle_id:    String(u.vehicle_id ?? ''),
            eco:           u.eco,
            km_por_litro:  u.km_por_litro  ?? 0,
            diesel_lts:    u.diesel_lts    ?? 0,
            total_importe: u.total_importe ?? 0,
            toneladas_hoy: u.toneladas     ?? 0,   // ← viene de state_store, actualizado por báscula
            status:        u.status        ?? 'SIN_GPS',
          }))
          .sort((a: FleetUnit, b: FleetUnit) => b.km_por_litro - a.km_por_litro);

        const total_km_hoy = (data.units ?? []).reduce(
          (sum: number, u: any) => sum + (parseFloat(u.km_hoy) || 0), 0
        );
        onMessage({
          active_units:   data.active_units   ?? 0,
          inactive_units: data.inactive_units ?? 0,
          total_units:    data.total_units    ?? 0,
          total_km_hoy:   Math.round(total_km_hoy),
          units,
        });
      }
    } catch (error) {
      console.error('❌ Error parseando WS (fleet):', error);
    }
  };
  socket.onerror = (e) => console.error('🔥 WS error (fleet):', e);
  socket.onclose = () => console.log('🔴 WebSocket cerrado (fleet)');
  return socket;
};

// ── REST helpers: báscula ─────────────────────────────────────────────────────

const API = 'http://localhost:8000';

export async function fetchBasculaHoy(): Promise<BasculaHoy> {
  const r = await fetch(`${API}/api/bascula/hoy`);
  if (!r.ok) throw new Error('Error GET /api/bascula/hoy');
  return r.json();
}

export async function fetchBasculaAyer(): Promise<BasculaHoy> {
  const r = await fetch(`${API}/api/bascula/ayer`);
  if (!r.ok) return { fecha: '', toneladas: 0, viajes: 0 }; // sin datos de ayer → no romper
  return r.json();
}

export async function fetchTonelajeDiario(dias = 30): Promise<TonelajeDiarioPoint[]> {
  const r = await fetch(`${API}/api/bascula/diario?dias=${dias}`);
  if (!r.ok) throw new Error('Error GET /api/bascula/diario');
  const data = await r.json();
  // Mapear para el gráfico: fecha ISO → número de día
  return (data.serie ?? []).map((p: any) => ({
    fecha:  p.fecha,
    day:    p.fecha ? p.fecha.slice(8, 10) : '',   // "14"
    tons:   p.toneladas,
    viajes: p.viajes,
  }));
}

export async function fetchBasculaPorUnidad(fecha?: string): Promise<BasculaPorUnidad[]> {
  const url = fecha
    ? `${API}/api/bascula/por-unidad?target_date=${fecha}`
    : `${API}/api/bascula/por-unidad`;
  const r = await fetch(url);
  if (!r.ok) throw new Error('Error GET /api/bascula/por-unidad');
  const data = await r.json();
  return data.unidades ?? [];
}

export async function fetchBasculaActividad(limit = 50): Promise<BascularRecord[]> {
  const r = await fetch(`${API}/api/bascula/actividad?limit=${limit}`);
  if (!r.ok) throw new Error('Error GET /api/bascula/actividad');
  const data = await r.json();
  return data.registros ?? [];
}