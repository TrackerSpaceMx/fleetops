# FleetOps Backend — Tersa Mundi

Backend Python en tiempo real para el dashboard de gestión de flota **FleetOps**.  
Integra la API GPS de **Fulltrack2**, las reglas operativas del **Excel TECMED** y
las expone vía **WebSocket + REST (FastAPI)** al frontend React del repositorio
`TrackerSpaceMx/flops`.

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (flops)                         │
│  Dashboard  │  Flota  │  Combustible  │  Reportes  │  Báscula  │
└──────────────────────┬──────────────────────────────────────────┘
                       │  WebSocket + REST
┌──────────────────────▼──────────────────────────────────────────┐
│                   FleetOps Backend (Python)                      │
│                                                                  │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │  Scheduler  │  │ metrics_     │  │     state_store        │  │
│  │ (APScheduler│  │ engine.py    │  │  (memoria compartida)  │  │
│  │  asyncio)   │  │ Hoja1-5+     │  │                        │  │
│  │             │  │ Portada Excel│  │                        │  │
│  └──────┬──────┘  └──────┬───────┘  └───────────┬────────────┘  │
│         │                │                      │               │
│  ┌──────▼──────────────── ▼──────────────────────▼────────────┐  │
│  │                 WebSocket Manager                          │  │
│  │   canales: fleet / fuel / reports / alerts / all           │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │              Fulltrack2 API Client (httpx async)         │    │
│  │  /vehicles/all  │  /events/all  │  /consolidatedevents  │    │
│  └──────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
         ↑                                     ↑
   Sistema externo                       Fulltrack GPS
   (Báscula TECMED)                   ws.fulltrack2.com
```

---

## Requisitos

- Python **3.11+**
- pip

---

## Instalación

```bash
# 1. Clonar / copiar este directorio junto al repo del frontend
cd fleetops-backend

# 2. Crear entorno virtual
python3 -m venv .venv
source .venv/bin/activate          # Linux/macOS
# .venv\Scripts\activate           # Windows

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar variables de entorno
cp .env .env.local                 # editar si es necesario
```

El archivo `.env` ya viene con las credenciales de Fulltrack:

```env
FULLTRACK_BASE_URL=
FULLTRACK_APIKEY=
FULLTRACK_SECRETKEY=4
DIESEL_PRICE_PER_LITER=23.62
FLEET_POLL_INTERVAL=30
KM_POLL_INTERVAL=300
FRONTEND_ORIGIN=http://localhost:3000
```

---

## Ejecutar el servidor

```bash
# Modo desarrollo (con recarga automática)
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Modo producción
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
```

Abrir `http://localhost:8000/docs` para ver la documentación Swagger interactiva.

---

## Endpoints WebSocket

| Canal | URL | Uso |
|-------|-----|-----|
| Flota | `ws://localhost:8000/ws/fleet` | Dashboard + Gestión de Flota |
| Combustible | `ws://localhost:8000/ws/fuel` | Pestaña Combustible |
| Reportes | `ws://localhost:8000/ws/reports` | Generador de Reportes |
| Alertas | `ws://localhost:8000/ws/alerts` | Notificaciones |
| Todo | `ws://localhost:8000/ws/all` | Debug / todo en uno |

### Formato del mensaje `fleet_update`

```json
{
  "type": "fleet_update",
  "timestamp": "2026-04-05T19:34:55",
  "active_units": 6,
  "inactive_units": 2,
  "total_units": 8,
  "dashboard": {
    "periodo": "Abril 2026",
    "toneladas_mes": 13071.02,
    "promedio_hrs_rutas": 15.27,
    "promedio_km_rutas": 42.44,
    "consumo_combustible_lts": 55143.28,
    "consumo_combustible_importe": 1302484.20,
    "personal_operativo": 159
  },
  "units": [
    {
      "vehicle_id": "1213421",
      "eco": "TM-04",
      "placa": "ABC-1234",
      "status": "ACTIVO",
      "gps_date": "05/04/2026 19:30:10",
      "lat": 27.5023,
      "lng": -99.5075,
      "velocidad": 45,
      "km_hoy": 142,
      "toneladas": 452.3,
      "t_prod_hrs": 184,
      "t_no_prod_hrs": 24,
      "ton_por_t_prod": 2.45,
      "km_prod": 1245.42,
      "km_trasl": 1773.78,
      "km_disp": 754.8,
      "km_total": 3774,
      "km_por_litro": 2.026,
      "alerta_rendimiento": "normal",
      "diesel_lts": 1862.32,
      "diesel_importe": 43987.99,
      "total_lts": 1862.32,
      "total_importe": 43987.99,
      "precio_diesel": 23.62,
      "num_viajes": 90,
      "tons_prom_por_viaje": 6.11,
      "pct_carga": 58.0,
      "fuel_records": [],
      "litros_mes": 1862.32,
      "costo_mes": 43987.99
    }
  ]
}
```

---

## Endpoints REST

### Flota
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/fleet/vehicles` | Lista de vehículos |
| GET | `/api/fleet/status` | Estado GPS de la flota |
| GET | `/api/fleet/unit/{id}` | Detalle de unidad |
| GET | `/api/fleet/unit/{id}/km?date_from=&date_to=` | Km por rango de fechas |
| GET | `/api/fleet/routes` | Operatividad por ruta (Hoja 3) |
| POST | `/api/fleet/refresh` | Forzar actualización |

### Combustible
| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/api/fuel/load` | Registrar nueva carga |
| GET | `/api/fuel/records/{vehicle_id}` | Historial de cargas |
| GET | `/api/fuel/records` | Todos los registros |
| GET | `/api/fuel/report/hoja4` | Reporte Hoja 4 Excel |

### Reportes
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/reports/portada` | Resumen ejecutivo |
| GET | `/api/reports/operatividad` | Hoja 1 — Operatividad |
| GET | `/api/reports/km-rendimiento` | Hoja 2 — Km y rendimiento |
| GET | `/api/reports/por-ruta` | Hoja 3 — Por ruta |
| GET | `/api/reports/costo-combustible` | Hoja 4 — Costos |
| GET | `/api/reports/tonelaje` | Hoja 5 — Tonelaje |
| GET | `/api/reports/mensual` | Reporte mensual consolidado |
| GET | `/api/reports/comparativo` | Últimos 3 meses |

### Báscula (sistema externo)
| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/api/bascula/registro` | Un registro de pesaje |
| POST | `/api/bascula/batch` | Lote de registros |
| GET | `/api/bascula/registros` | Consultar registros |
| GET | `/api/bascula/resumen` | Resumen diario por unidad |

---

## Integración con el frontend (flops)

### 1. Copiar el cliente WebSocket

Copia `frontend-integration/fleetops-ws.js` dentro del proyecto React
(por ejemplo en `src/lib/fleetops-ws.js`).

### 2. Conectar en tu componente

```jsx
// src/app/dashboard/page.jsx (o donde corresponda)
import { useFleetOps, mapDashboardSummary, mapUnitToFlotaCard } from '@/lib/fleetops-ws';

export default function Dashboard() {
  const { data, connected } = useFleetOps('fleet', 'ws://localhost:8000');

  const summary = mapDashboardSummary(data);
  const units   = (data?.units ?? []).map(mapUnitToFlotaCard);

  return (
    <div>
      <span>{connected ? '🟢 LIVE' : '🔴 Desconectado'}</span>
      <p>Toneladas del mes: {summary.toneladas}</p>
      <p>Unidades activas: {summary.unidadesActivas}</p>
      {units.map(u => (
        <div key={u.id}>
          {u.eco} — {u.status} — {u.kmHoy} km hoy
        </div>
      ))}
    </div>
  );
}
```

### 3. Registrar carga de combustible

```js
// Desde la pestaña Combustible del frontend
await fetch('http://localhost:8000/api/fuel/load', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    vehicle_id:      '1213421',   // ras_vei_id de Fulltrack
    conductor:       'Juan Pérez',
    proveedor:       'Pemex',
    tipo:            'DIESEL',
    liters:          45.0,
    price_per_liter: 23.62,
    odometro_actual: 145877,
    tanque_lleno:    true,
  })
});
// El WS emitirá automáticamente 'fuel_update' a todos los clientes conectados
```

### 4. Enviar datos de báscula (sistema externo → backend)

```python
import httpx
httpx.post('http://backend:8000/api/bascula/registro', json={
    "folio": 1,
    "placa": "TM-04",
    "num_eco": "TM-04",
    "razon_social": "MUNICIPIO DE NUEVO LAREDO TAMAULIPAS",
    "fecha": "2026-04-05T10:33:53",
    "hora_entrada": "10:33:53",
    "hora_salida": "10:59:03",
    "turno": "Matutino",
    "peso_entrada": 13.87,
    "peso_salida": 10.03,
    "peso_neto": 3.84,
    "precio_ton": 0.0,
    "tipo_residuos": "DOMICILIARIO"
})
```

---

## Reglas del Excel implementadas

| Hoja Excel | Endpoint / función | Campos calculados |
|---|---|---|
| **Hoja 1** Operatividad promedio | `GET /api/reports/operatividad` | `t_prod_hrs`, `t_no_prod_hrs`, `ton_por_t_prod`, `km_prod`, `km_no_prod`, `ton_por_km_prod`, `pct_carga` |
| **Hoja 2** Km y rendimiento | `GET /api/reports/km-rendimiento` | `km_prod`, `km_trasl`, `km_disp`, `km_total`, `litros`, `km_por_litro` |
| **Hoja 3** Operatividad por ruta | `GET /api/reports/por-ruta` | Agregados por ruta de Hoja1+2 |
| **Hoja 4** Costo combustible | `GET /api/reports/costo-combustible` | `diesel_lts`, `diesel_importe`, `total_lts`, `total_importe` |
| **Hoja 5** Tonelaje comparativo | `GET /api/reports/tonelaje` | `tons`, `num_viajes`, `tons_prom_por_viaje`, `variacion_pct` |
| **Portada** Resumen ejecutivo | `GET /api/reports/portada` | `toneladas_mes`, `promedio_hrs`, `promedio_km`, `consumo_combustible` |
| **BASE DE DATOS** (báscula) | `POST /api/bascula/registro` | `peso_neto`, `turno`, `tipo_residuos`, `importe` |

### Factores de distribución (extraídos del Excel)

```
km_prod   = km_total × 0.33   (33% km productivos)
km_trasl  = km_total × 0.47   (47% km traslado)
km_disp   = km_total × 0.20   (20% km disposición)

t_prod    = horas × 0.58      (58% tiempo productivo)
t_noprod  = horas × 0.42      (42% tiempo no productivo)

rendimiento histórico:
  octubre:   1.58 km/lt
  noviembre: 1.68 km/lt
  diciembre: 1.80 km/lt
```

---

## Estructura de archivos

```
fleetops-backend/
├── main.py                          ← Entrada FastAPI + lifespan
├── requirements.txt
├── .env                             ← Credenciales Fulltrack
├── src/
│   ├── config/
│   │   └── settings.py              ← Todas las constantes y reglas Excel
│   ├── services/
│   │   ├── fulltrack_client.py      ← Cliente HTTP async para Fulltrack API
│   │   ├── state_store.py           ← Estado en memoria (thread-safe)
│   │   ├── metrics_engine.py        ← Motor de cálculo (Hoja1-5 + Portada)
│   │   └── fleet_service.py         ← Orquestador de actualización de flota
│   ├── websocket/
│   │   ├── ws_manager.py            ← Gestor de conexiones WS por canal
│   │   └── scheduler.py             ← Tareas periódicas (APScheduler asyncio)
│   └── routes/
│       ├── fleet_routes.py          ← REST: Flota y Dashboard
│       ├── fuel_routes.py           ← REST: Combustible
│       ├── report_routes.py         ← REST: Todas las hojas del Excel
│       ├── bascula_routes.py        ← REST: Recepción de datos de báscula
│       └── ws_routes.py             ← WebSocket endpoints
└── frontend-integration/
    └── fleetops-ws.js               ← Cliente WS + React hook + mappers
```
