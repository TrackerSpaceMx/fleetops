import React, { useState, useEffect, useCallback } from 'react'
import jsPDF from 'jspdf'
import autoTable from 'jspdf-autotable'
import {
  FileText, Download, FileSpreadsheet, FileJson,
  BarChart3, Check, X, Loader2, AlertCircle,
  Truck, Scale, Fuel, ChevronDown, ChevronUp, RefreshCw,
  Calendar,
} from 'lucide-react'

const API_BASE = 'http://localhost:8000'
const EMPRESA  = 'Tersa Mundi S.A. de C.V.'
const SISTEMA  = 'FleetOps'

const BLUE_RGB:       [number, number, number] = [37,  99,  235]
const BLUE_LIGHT_RGB: [number, number, number] = [219, 234, 254]
const GRAY_RGB:       [number, number, number] = [107, 114, 128]
const BLACK_RGB:      [number, number, number] = [17,  24,  39]
const WHITE_RGB:      [number, number, number] = [255, 255, 255]

// ─── Catálogo ─────────────────────────────────────────────────────────────────
const REPORT_GROUPS = [
  {
    group: 'Flota — Hojas TECMED',
    icon: Truck,
    reports: [
      {
        id: 'costo-combustible', label: 'Combustible por Unidad',
        desc: 'Litros, importe y precio · filtrable por día o rango',
        endpoint: '/api/reports/costo-combustible', dataKey: 'unidades',
        chartKey: 'total_lts', supportsRange: true, supportsDetail: true,
        columns: ['eco','diesel_lts','diesel_importe','gasolina_lts','total_lts','total_importe','precio_diesel','cargas'],
        detailColumns: ['eco','fecha','hora','litros','precio_litro','importe','proveedor','conductor'],
        detailKey: 'detalle_cargas',
      },
      {
        id: 'km-rendimiento', label: 'Km y Rendimiento',
        desc: 'Km totales (Fulltrack) y km/litro · filtrable por rango',
        endpoint: '/api/reports/km-rendimiento', dataKey: 'unidades',
        chartKey: 'km_total', supportsRange: true, supportsDetail: false,
        columns: ['eco','km_total','litros','km_por_litro','alerta_rendimiento'],
        detailColumns: [], detailKey: null,
      },
      {
        id: 'operatividad', label: 'Operatividad por Unidad',
        desc: 'Toneladas (báscula) y % carga por unidad',
        endpoint: '/api/reports/operatividad', dataKey: 'unidades',
        chartKey: 'toneladas', supportsRange: false, supportsDetail: false,
        columns: ['eco','toneladas','num_viajes','pct_carga'],
        detailColumns: [], detailKey: null,
      },
      {
        id: 'tonelaje', label: 'Tonelaje por Unidad',
        desc: 'Toneladas y viajes · filtrable por día o rango',
        endpoint: '/api/reports/tonelaje', dataKey: 'unidades',
        chartKey: 'toneladas', supportsRange: true, supportsDetail: false,
        columns: ['eco','toneladas','num_viajes','tons_prom_por_viaje'],
        detailColumns: [], detailKey: null,
      },
      {
        id: 'comparativo', label: 'Comparativo 3 Meses',
        desc: 'Km, litros y km/lt de los últimos 3 meses',
        endpoint: '/api/reports/comparativo', dataKey: null,
        chartKey: 'km_total', supportsRange: false, supportsDetail: false,
        columns: ['periodo','km_total','litros','km_por_litro','toneladas'],
        detailColumns: [], detailKey: null,
      },
    ],
  },
  {
    group: 'Báscula',
    icon: Scale,
    reports: [
      {
        id: 'bascula-mensual', label: 'Tonelaje Mensual',
        desc: 'Toneladas y viajes por unidad en el mes',
        endpoint: '/api/bascula/mensual', dataKey: 'por_unidad',
        chartKey: 'toneladas', supportsRange: false, supportsDetail: false,
        columns: ['num_eco','toneladas','viajes','promedio_ton_viaje'],
        detailColumns: [], detailKey: null,
      },
      {
        id: 'bascula-actividad', label: 'Actividad con Fecha y Hora',
        desc: 'Cada pesaje con hora entrada/salida, peso neto y tipo cliente',
        endpoint: '/api/reports/actividad-bascula', dataKey: 'registros',
        chartKey: 'peso_neto', supportsRange: true, supportsDetail: false,
        columns: ['num_eco','fecha','hora_entrada','hora_salida','peso_neto','tipo_cliente','tipo_residuo'],
        detailColumns: [], detailKey: null,
      },
      {
        id: 'bascula-por-cliente', label: 'Por Tipo de Cliente',
        desc: 'Municipio, particulares y disposición con % del total',
        endpoint: '/api/bascula/por-cliente', dataKey: 'clientes',
        chartKey: 'toneladas', supportsRange: false, supportsDetail: false,
        columns: ['tipo_cliente','toneladas','viajes','pct_toneladas'],
        detailColumns: [], detailKey: null,
      },
      {
        id: 'bascula-turno', label: 'Por Turno',
        desc: 'Matutino, Vespertino y Nocturno',
        endpoint: '/api/bascula/turno-basculista', dataKey: 'por_dia',
        chartKey: 'toneladas', supportsRange: false, supportsDetail: false,
        columns: ['dia','turno','tipo_cliente','toneladas','viajes'],
        detailColumns: [], detailKey: null,
      },
    ],
  },
  {
    group: 'Combustible',
    icon: Fuel,
    reports: [
      {
        id: 'diesel-diario', label: 'Diesel Diario',
        desc: 'Litros e importe de diesel por día y vehículo',
        endpoint: '/api/bascula/diesel-diario', dataKey: 'unidades',
        chartKey: 'litros_mes', supportsRange: false, supportsDetail: false,
        columns: ['eco','litros_mes','km_mes','km_por_litro','toneladas_mes'],
        detailColumns: [], detailKey: null,
      },
    ],
  },
]

const ALL_REPORTS = REPORT_GROUPS.flatMap(g => g.reports)

const COLUMN_LABELS: Record<string, string> = {
  eco: 'No. Económico', num_eco: 'No. Económico',
  km_total: 'Km Total', km_por_litro: 'Km/Lt',
  alerta_rendimiento: 'Alerta',
  diesel_lts: 'Lts Diesel', diesel_importe: 'Importe Diesel',
  gasolina_lts: 'Lts Gasolina', total_lts: 'Total Litros',
  total_importe: 'Total Importe', precio_diesel: 'Precio/Lt',
  precio_litro: 'Precio/Lt', importe: 'Importe',
  toneladas: 'Toneladas', pct_carga: '% Carga',
  num_viajes: 'Viajes', viajes: 'Viajes', cargas: 'Cargas',
  tons_prom_por_viaje: 'Ton/Viaje', promedio_ton_viaje: 'Ton/Viaje Prom.',
  tipo_cliente: 'Tipo Cliente', pct_toneladas: '% del Total',
  tipo_residuo: 'Tipo Residuo',
  turno: 'Turno', dia: 'Día',
  fecha: 'Fecha', hora: 'Hora',
  hora_entrada: 'Hora Entrada', hora_salida: 'Hora Salida',
  peso_neto: 'Peso Neto (ton)', peso_entrada: 'Peso Entrada', peso_salida: 'Peso Salida',
  litros: 'Litros', litros_mes: 'Lts Mes', km_mes: 'Km Mes',
  toneladas_mes: 'Ton. Mes', periodo: 'Período',
  proveedor: 'Proveedor', conductor: 'Conductor',
}
const HIDDEN_COLS = new Set(['vehicle_id', 'folio', 'placa'])

function fmtVal(key: string, val: any): string {
  if (val == null || val === '') return '—'
  if (key.includes('importe') || key === 'precio_litro' || key === 'precio_diesel')
    return `$${parseFloat(val).toLocaleString('es-MX', { minimumFractionDigits: 2 })}`
  if (key.includes('pct') || key === 'variacion_pct') {
    const n = parseFloat(val)
    return `${(Math.abs(n) <= 1 ? n * 100 : n).toFixed(1)}%`
  }
  if (key === 'km_por_litro') return parseFloat(val).toFixed(3)
  if (key.startsWith('km_') || key === 'km_mes' || key === 'km_total')
    return Math.round(parseFloat(val)).toLocaleString('es-MX')
  if (key.includes('ton') || key === 'toneladas' || key === 'toneladas_mes' || key === 'peso_neto')
    return parseFloat(val).toLocaleString('es-MX', { minimumFractionDigits: 2 })
  if (key.includes('lts') || key === 'litros' || key === 'litros_mes')
    return parseFloat(val).toLocaleString('es-MX', { minimumFractionDigits: 1 })
  return String(val)
}

function alertColor(val: string) {
  const v = (val || '').toLowerCase()
  if (v === 'normal')  return 'text-green-600 bg-green-50 border-green-200'
  if (v === 'bajo')    return 'text-amber-600 bg-amber-50 border-amber-200'
  if (v === 'critico') return 'text-red-600 bg-red-50 border-red-200'
  return 'text-gray-400'
}

function getMonthOptions() {
  const now = new Date()
  return Array.from({ length: 6 }, (_, i) => {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
    const label = d.toLocaleDateString('es-MX', { month: 'long', year: 'numeric' })
    return { label: label.charAt(0).toUpperCase() + label.slice(1), year: d.getFullYear(), month: d.getMonth() + 1 }
  })
}

function todayStr() {
  return new Date().toISOString().slice(0, 10)
}

// ─── PDF helpers ──────────────────────────────────────────────────────────────
function drawPDFHeader(doc: jsPDF, title: string, period: string, count: number, W: number): number {
  const m = 14
  doc.setFillColor(...BLUE_RGB); doc.rect(0, 0, W, 18, 'F')
  doc.setFillColor(...WHITE_RGB); doc.roundedRect(m, 4, 10, 10, 1, 1, 'F')
  doc.setFontSize(6); doc.setTextColor(...BLUE_RGB); doc.text('TM', m + 1.8, 10.5)
  doc.setFontSize(9); doc.setFont('helvetica', 'bold'); doc.setTextColor(...WHITE_RGB)
  doc.text(EMPRESA, m + 13, 10.5)
  doc.setFontSize(8); doc.setFont('helvetica', 'normal')
  doc.text(title, W - m, 8, { align: 'right' })
  doc.setFontSize(7); doc.text(period, W - m, 13, { align: 'right' })
  doc.setDrawColor(...BLUE_RGB); doc.setLineWidth(0.4); doc.line(m, 22, W - m, 22)
  doc.setFontSize(7); doc.setTextColor(...GRAY_RGB)
  doc.text(`${count} registro${count !== 1 ? 's' : ''} · Generado por ${SISTEMA}`, m, 27)
  return 31
}

function drawPDFFooter(doc: jsPDF, W: number, page: number, total: number) {
  const H = doc.internal.pageSize.getHeight(); const m = 14; const y = H - 8
  doc.setDrawColor(...BLUE_LIGHT_RGB); doc.setLineWidth(0.3); doc.line(m, y - 2, W - m, y - 2)
  doc.setFontSize(6.5); doc.setTextColor(...GRAY_RGB)
  doc.text(EMPRESA, m, y)
  doc.text(`Página ${page} de ${total}  ·  ${SISTEMA}`, W - m, y, { align: 'right' })
}

function insertBarChart(doc: jsPDF, rows: any[], labelKey: string, valueKey: string, chartTitle: string, startY: number, W: number): number {
  const m = 14; const cW = W - 2 * m; const cH = 50
  const canvas = document.createElement('canvas')
  const S = 3; canvas.width = cW * S * 3.7795; canvas.height = cH * S * 3.7795
  const ctx = canvas.getContext('2d')!; ctx.scale(S, S)
  const pw = cW * 3.7795; const ph = cH * 3.7795
  ctx.fillStyle = '#EFF6FF'; ctx.fillRect(0, 0, pw, ph)
  const valid = rows.filter(r => r[valueKey] != null && !isNaN(parseFloat(r[valueKey])))
  if (!valid.length) return startY
  const vals = valid.map(r => parseFloat(r[valueKey]))
  const labels = valid.map(r => String(r[labelKey] ?? ''))
  const maxVal = Math.max(...vals, 1)
  const ba = { x: 38, y: 18, w: pw - 55, h: ph - 44 }
  const gap = ba.w / labels.length; const bw = Math.min(38, gap * 0.65)
  ctx.fillStyle = '#1E3A5F'; ctx.font = 'bold 10px Arial'; ctx.fillText(chartTitle, 6, 13)
  labels.forEach((label, i) => {
    const v = vals[i]; const bh = maxVal > 0 ? (v / maxVal) * ba.h : 0
    const x = ba.x + i * gap + gap / 2 - bw / 2; const y = ba.y + ba.h - bh
    ctx.fillStyle = `rgba(37,99,235,${0.6 + (i / labels.length) * 0.4})`
    ctx.beginPath(); ctx.roundRect(x, y, bw, bh, [3, 3, 0, 0]); ctx.fill()
    ctx.fillStyle = '#1E3A5F'; ctx.font = '8px Arial'; ctx.textAlign = 'center'
    const disp = v > 9999 ? `${(v/1000).toFixed(1)}k` : v.toFixed(v < 10 ? 2 : 0)
    ctx.fillText(disp, x + bw / 2, y - 3)
    ctx.fillStyle = '#6B7280'; ctx.font = '7px Arial'
    ctx.fillText(label.length > 6 ? label.slice(0, 5) + '…' : label, x + bw / 2, ba.y + ba.h + 12)
  })
  ctx.strokeStyle = '#DBEAFE'; ctx.lineWidth = 0.5
  ctx.beginPath(); ctx.moveTo(ba.x, ba.y); ctx.lineTo(ba.x, ba.y + ba.h); ctx.stroke()
  doc.addImage(canvas.toDataURL('image/png'), 'PNG', m, startY, cW, cH)
  return startY + cH + 4
}

function generateClientPDF(rows: any[], cols: string[], title: string, period: string, chartKey: string | null, withChart: boolean) {
  const doc = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4' })
  const W = doc.internal.pageSize.getWidth(); const m = 14
  const visCols = cols.filter(c => !HIDDEN_COLS.has(c))
  const heads = [visCols.map(k => COLUMN_LABELS[k] ?? k.replace(/_/g, ' '))]
  const body  = rows.map(row => visCols.map(k => fmtVal(k, row[k])))
  let startY = drawPDFHeader(doc, title, period, rows.length, W)
  const ecoKey = visCols.includes('eco') ? 'eco' : visCols.includes('num_eco') ? 'num_eco' : visCols.includes('tipo_cliente') ? 'tipo_cliente' : visCols[0]
  if (withChart && chartKey && rows.some(r => r[chartKey] != null))
    startY = insertBarChart(doc, rows, ecoKey, chartKey, `${COLUMN_LABELS[chartKey] ?? chartKey} por unidad`, startY, W) + 2
  const footRow = visCols.map((k, i) => {
    if (i === 0) return 'TOTAL'
    const sample = rows.find(r => r[k] != null)?.[k]
    if (sample != null && !isNaN(parseFloat(String(sample))))
      return fmtVal(k, rows.reduce((a, r) => a + (parseFloat(r[k]) || 0), 0))
    return ''
  })
  autoTable(doc, {
    head: heads, body, foot: [footRow], startY, margin: { left: m, right: m },
    styles: { fontSize: 8, cellPadding: 1.8, font: 'helvetica', textColor: BLACK_RGB },
    headStyles: { fillColor: BLUE_RGB, textColor: WHITE_RGB, fontStyle: 'bold', fontSize: 8.5 },
    alternateRowStyles: { fillColor: BLUE_LIGHT_RGB },
    footStyles: { fillColor: BLUE_LIGHT_RGB, textColor: BLUE_RGB, fontStyle: 'bold' },
    didDrawPage: () => {
      const p = (doc.internal as any).getCurrentPageInfo().pageNumber
      drawPDFFooter(doc, W, p, doc.getNumberOfPages())
    },
  })
  doc.save(`${title.replace(/\s+/g, '_')}_${period.replace(/\s+/g, '_')}.pdf`)
}

// ─── Componente ───────────────────────────────────────────────────────────────
export default function Reports() {
  const monthOptions = getMonthOptions()
  const [selectedPeriod, setSelectedPeriod] = useState(monthOptions[0])
  const [selectedId,     setSelectedId]     = useState('costo-combustible')
  const [format,         setFormat]         = useState('PDF')
  const [withChart,      setWithChart]      = useState(true)
  const [generating,     setGenerating]     = useState(false)
  const [previewData,    setPreviewData]    = useState<any[]>([])
  const [loadingPreview, setLoadingPreview] = useState(false)
  const [allVehicles,    setAllVehicles]    = useState<string[]>([])
  const [selectedUnits,  setSelectedUnits]  = useState<string[]>([])
  const [error,          setError]          = useState('')
  const [lastGenerated,  setLastGenerated]  = useState('')
  const [openGroups,     setOpenGroups]     = useState<Record<string,boolean>>(
    Object.fromEntries(REPORT_GROUPS.map(g => [g.group, true]))
  )
  // Filtro de fecha
  const [filterMode,  setFilterMode]  = useState<'month' | 'range' | 'day'>('month')
  const [dateFrom,    setDateFrom]    = useState(todayStr())
  const [dateTo,      setDateTo]      = useState(todayStr())
  const [showDetail,  setShowDetail]  = useState(false)

  const selectedReport = ALL_REPORTS.find(r => r.id === selectedId) ?? ALL_REPORTS[0]

  // Vehículos
  useEffect(() => {
    fetch(`${API_BASE}/api/fleet/vehicles`)
      .then(r => { if (!r.ok) throw new Error('404'); return r.json() })
      .then(data => {
        const ecos = (data.vehicles ?? [])
          .map((v: any) => v.ras_vei_eco || v.ras_vei_placa || String(v.ras_vei_id))
          .filter(Boolean).sort() as string[]
        if (ecos.length > 0) { setAllVehicles(ecos); setSelectedUnits(ecos) }
      }).catch(() => {})
  }, [])

  useEffect(() => {
    if (allVehicles.length > 0 || previewData.length === 0) return
    const sample = previewData[0] as any
    const ecoKey = sample?.eco ? 'eco' : sample?.num_eco ? 'num_eco' : null
    if (!ecoKey) { setAllVehicles(['TODAS']); setSelectedUnits(['TODAS']); return }
    const ecos = [...new Set(previewData.map((r: any) => r[ecoKey]).filter(Boolean))].sort() as string[]
    setAllVehicles(ecos); setSelectedUnits(ecos)
  }, [previewData, allVehicles.length])

  // Construir query params según filtro
  const buildParams = useCallback(() => {
    const params = new URLSearchParams()
    if (filterMode === 'month') {
      params.set('year',  String(selectedPeriod.year))
      params.set('month', String(selectedPeriod.month))
    } else if (filterMode === 'day') {
      params.set('date_from', dateFrom)
      params.set('date_to',   dateFrom)
    } else {
      params.set('date_from', dateFrom)
      params.set('date_to',   dateTo)
    }
    if (showDetail && selectedReport.supportsDetail) params.set('include_detail', 'true')
    return params.toString()
  }, [filterMode, selectedPeriod, dateFrom, dateTo, showDetail, selectedReport])

  const periodLabel = filterMode === 'month'
    ? selectedPeriod.label
    : filterMode === 'day'
    ? dateFrom
    : `${dateFrom} → ${dateTo}`

  // Preview
  const loadPreview = useCallback(async () => {
    if (!selectedReport) return
    setLoadingPreview(true); setError('')
    try {
      const url  = `${API_BASE}${selectedReport.endpoint}?${buildParams()}`
      const resp = await fetch(url)
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      let rows: any[] = []
      if (selectedReport.dataKey) {
        rows = data[selectedReport.dataKey] ?? []
      } else if (selectedId === 'comparativo') {
        rows = Object.values(data.comparativo ?? {}).map((v: any) => ({
          periodo: v.periodo, km_total: v.total_km, litros: v.total_litros,
          km_por_litro: v.km_por_litro, toneladas: v.total_toneladas,
        }))
      }
      const cols = (showDetail && selectedReport.supportsDetail && data[selectedReport.detailKey ?? '']?.length)
        ? selectedReport.detailColumns
        : selectedReport.columns
      if (showDetail && selectedReport.supportsDetail && data[selectedReport.detailKey ?? '']) {
        rows = data[selectedReport.detailKey!] ?? rows
      }
      rows = rows.map(r => Object.fromEntries(cols.map(k => [k, r[k] ?? null])))
      setPreviewData(rows)
    } catch (e: any) {
      setError('No se pudo cargar la vista previa: ' + e.message)
      setPreviewData([])
    } finally {
      setLoadingPreview(false)
    }
  }, [selectedId, buildParams, selectedReport, showDetail])

  useEffect(() => { loadPreview() }, [loadPreview])

  const toggleUnit  = (eco: string) =>
    setSelectedUnits(prev => prev.includes(eco) ? prev.filter(e => e !== eco) : [...prev, eco])
  const toggleGroup = (g: string) =>
    setOpenGroups(prev => ({ ...prev, [g]: !prev[g] }))

  const filteredData = (() => {
    if (!selectedUnits.length || selectedUnits.includes('TODAS')) return previewData
    const ecoKey = previewData[0]?.eco !== undefined ? 'eco' : 'num_eco'
    return previewData.filter(r => selectedUnits.includes(r[ecoKey]))
  })()

  const activeCols = (showDetail && selectedReport.supportsDetail && filteredData[0] && selectedReport.detailColumns.length > 0)
    ? selectedReport.detailColumns.filter(k => !HIDDEN_COLS.has(k))
    : selectedReport.columns.filter(k => !HIDDEN_COLS.has(k))

  const previewRows = filteredData.slice(0, 8)

  const handleGenerate = async () => {
    if (generating) return
    setGenerating(true); setError(''); setLastGenerated('')
    const { year, month } = selectedPeriod
    try {
      if (format === 'PDF') {
        const cols = activeCols
        generateClientPDF(filteredData, cols, selectedReport.label, periodLabel, selectedReport.chartKey ?? null, withChart)
        setLastGenerated(`${selectedReport.label} — ${periodLabel}.pdf`)
        return
      }
      const backendMap: Record<string, string> = {
        'bascula-por-cliente': 'bascula-mensual',
        'bascula-turno': 'bascula-turnos',
        'bascula-actividad': 'bascula-mensual',
        'diesel-diario': 'diesel-diario',
      }
      const reportId   = backendMap[selectedId] ?? selectedId
      const unitsParam = selectedUnits.filter(u => u !== 'TODAS').join(',')
      const ep         = format === 'Excel' ? 'excel' : 'csv'
      const url        = `${API_BASE}/api/export/${ep}?report=${reportId}&year=${year}&month=${month}${unitsParam ? `&units=${unitsParam}` : ''}`
      const resp = await fetch(url)
      if (!resp.ok) throw new Error((await resp.text()) || `HTTP ${resp.status}`)
      const blob = await resp.blob()
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `${selectedId}_${periodLabel.replace(/\s+/g,'_')}.${format === 'Excel' ? 'xlsx' : 'csv'}`
      a.click(); URL.revokeObjectURL(a.href)
      setLastGenerated(a.download)
    } catch (e: any) {
      setError('Error al generar: ' + e.message)
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div className="h-full flex flex-col bg-gray-50">

      {/* Topbar */}
      <div className="px-6 py-4 bg-white border-b border-gray-100 flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-gray-900 tracking-tight">Generador de Reportes</h1>
          <p className="text-sm text-gray-500 mt-0.5">{EMPRESA} · {SISTEMA}</p>
        </div>

        {/* Filtro de fecha */}
        <div className="flex items-center gap-2 flex-wrap">
          {/* Modo */}
          <div className="flex rounded-lg border border-gray-200 overflow-hidden text-xs font-bold">
            {([['month','Mes'],['day','Día'],['range','Rango']] as const).map(([mode, lbl]) => (
              <button key={mode} onClick={() => setFilterMode(mode)}
                className={`px-3 py-1.5 transition-colors ${filterMode === mode ? 'bg-blue-600 text-white' : 'bg-white text-gray-500 hover:bg-gray-50'}`}>
                {lbl}
              </button>
            ))}
          </div>

          {filterMode === 'month' && (
            <select value={`${selectedPeriod.year}-${selectedPeriod.month}`}
              onChange={e => { const o = monthOptions.find(o => `${o.year}-${o.month}` === e.target.value); if (o) setSelectedPeriod(o) }}
              className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 bg-white text-gray-700 font-medium focus:outline-none focus:ring-2 focus:ring-blue-200">
              {monthOptions.map(o => <option key={`${o.year}-${o.month}`} value={`${o.year}-${o.month}`}>{o.label}</option>)}
            </select>
          )}

          {filterMode === 'day' && (
            <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
              className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-200" />
          )}

          {filterMode === 'range' && (
            <div className="flex items-center gap-1">
              <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
                className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-200" />
              <span className="text-gray-400 text-xs">→</span>
              <input type="date" value={dateTo} min={dateFrom} onChange={e => setDateTo(e.target.value)}
                className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-200" />
            </div>
          )}

          <button onClick={loadPreview} className="p-2 rounded-lg border border-gray-200 bg-white text-gray-500 hover:bg-gray-50 transition-colors">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-hidden grid grid-cols-12 gap-0">

        {/* Catálogo */}
        <div className="col-span-3 bg-white border-r border-gray-100 overflow-y-auto">
          <div className="p-4">
            <p className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-3">Tipo de Reporte</p>
            {REPORT_GROUPS.map(g => {
              const Icon = g.icon
              return (
                <div key={g.group} className="mb-2">
                  <button onClick={() => toggleGroup(g.group)} className="w-full flex items-center justify-between px-2 py-1.5 rounded-lg hover:bg-gray-50 transition-colors">
                    <div className="flex items-center gap-2">
                      <Icon className="w-4 h-4 text-blue-500" />
                      <span className="text-xs font-bold text-gray-700">{g.group}</span>
                    </div>
                    {openGroups[g.group] ? <ChevronUp className="w-3.5 h-3.5 text-gray-400" /> : <ChevronDown className="w-3.5 h-3.5 text-gray-400" />}
                  </button>
                  {openGroups[g.group] && (
                    <div className="ml-2 mt-1 space-y-0.5">
                      {g.reports.map(r => (
                        <button key={r.id} onClick={() => { setSelectedId(r.id); setError(''); setPreviewData([]) }}
                          className={`w-full text-left px-3 py-2.5 rounded-lg border transition-colors ${selectedId === r.id ? 'bg-blue-50 border-blue-200' : 'bg-transparent border-transparent hover:bg-gray-50'}`}>
                          <div className="flex items-center gap-1.5">
                            <p className={`text-xs font-semibold ${selectedId === r.id ? 'text-blue-700' : 'text-gray-700'}`}>{r.label}</p>
                            {r.supportsRange && <Calendar className="w-3 h-3 text-blue-400 shrink-0" />}
                          </div>
                          <p className="text-xs text-gray-400 mt-0.5 leading-tight">{r.desc}</p>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>

        {/* Vista previa */}
        <div className="col-span-6 flex flex-col overflow-hidden">
          <div className="px-5 py-3 bg-white border-b border-gray-100 flex items-center justify-between">
            <div>
              <h2 className="font-bold text-gray-900 text-sm">{selectedReport.label}</h2>
              <p className="text-xs text-gray-400 mt-0.5 flex items-center gap-1">
                <Calendar className="w-3 h-3" />
                {periodLabel}
                {selectedReport.supportsRange && filterMode !== 'month' && (
                  <span className="ml-1 px-1.5 py-0.5 bg-blue-50 text-blue-600 rounded text-xs font-medium">Rango activo</span>
                )}
              </p>
            </div>
            {loadingPreview && <Loader2 className="w-4 h-4 animate-spin text-blue-400" />}
          </div>

          <div className="flex-1 overflow-auto p-4">
            {error && (
              <div className="flex items-start gap-2 text-sm text-red-600 bg-red-50 border border-red-100 rounded-xl p-3 mb-3">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />{error}
              </div>
            )}

            {/* Gráfica */}
            {!loadingPreview && filteredData.length > 0 && selectedReport.chartKey && (() => {
              const key  = selectedReport.chartKey
              const ecoK = filteredData[0]?.eco !== undefined ? 'eco' : filteredData[0]?.num_eco !== undefined ? 'num_eco' : filteredData[0]?.tipo_cliente !== undefined ? 'tipo_cliente' : activeCols[0]
              const vals = filteredData.map(r => parseFloat(r[key]) || 0)
              const max  = Math.max(...vals, 1)
              return (
                <div className="mb-4 bg-blue-50 rounded-xl border border-blue-100 p-3">
                  <p className="text-xs font-bold text-blue-800 mb-2">{COLUMN_LABELS[key] ?? key}</p>
                  <div className="flex items-end gap-1" style={{ height: 56 }}>
                    {filteredData.slice(0, 20).map((r, i) => (
                      <div key={i} className="flex-1 flex flex-col items-center gap-0.5" title={`${r[ecoK]}: ${fmtVal(key, r[key])}`}>
                        <div className="w-full rounded-t"
                          style={{ height: `${Math.max(3, (vals[i] / max) * 48)}px`, background: `rgba(37,99,235,${0.45 + (i / filteredData.length) * 0.55})` }} />
                        <span className="text-gray-400" style={{ fontSize: 7 }}>{String(r[ecoK] ?? '').slice(-5)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )
            })()}

            {loadingPreview ? (
              <div className="flex items-center justify-center h-32 text-gray-400 gap-2">
                <Loader2 className="w-5 h-5 animate-spin" /><span className="text-sm">Cargando datos...</span>
              </div>
            ) : previewRows.length === 0 ? (
              <div className="flex items-center justify-center h-32 text-gray-400 flex-col gap-2">
                <BarChart3 className="w-8 h-8 opacity-30" />
                <p className="text-sm">Sin datos para {periodLabel}</p>
              </div>
            ) : (
              <>
                <div className="overflow-x-auto rounded-xl border border-gray-100 shadow-sm">
                  <table className="w-full text-xs">
                    <thead>
                      <tr>
                        {activeCols.map(k => (
                          <th key={k} className="bg-blue-600 text-white font-bold px-3 py-2.5 text-left whitespace-nowrap first:rounded-tl-xl last:rounded-tr-xl">
                            {COLUMN_LABELS[k] ?? k.replace(/_/g,' ')}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {previewRows.map((row, ri) => (
                        <tr key={ri} className={ri % 2 === 0 ? 'bg-blue-50/40' : 'bg-white'}>
                          {activeCols.map(k => (
                            <td key={k} className="px-3 py-2 text-gray-700 whitespace-nowrap">
                              {k === 'alerta_rendimiento'
                                ? <span className={`px-2 py-0.5 rounded-full border text-xs font-bold ${alertColor(row[k])}`}>{row[k] ?? '—'}</span>
                                : fmtVal(k, row[k])}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {filteredData.length > 8 && (
                  <p className="text-xs text-gray-400 mt-2 text-center">
                    Mostrando 8 de {filteredData.length} registros — el archivo incluirá todos
                  </p>
                )}
              </>
            )}
          </div>
        </div>

        {/* Panel derecho */}
        <div className="col-span-3 bg-white border-l border-gray-100 flex flex-col overflow-y-auto">
          <div className="p-4 space-y-5 flex-1">

            {/* Filtro unidades */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-xs font-bold text-gray-700 uppercase tracking-wider">Unidades</label>
                <div className="flex gap-1">
                  <button onClick={() => setSelectedUnits(allVehicles)} className="text-xs text-blue-500 hover:text-blue-700 font-medium">Todas</button>
                  <span className="text-gray-300">·</span>
                  <button onClick={() => setSelectedUnits([])} className="text-xs text-gray-400 hover:text-gray-600 font-medium">Ninguna</button>
                </div>
              </div>
              {allVehicles.length === 0 ? (
                <p className="text-xs text-gray-400 py-2">Cargando unidades...</p>
              ) : (
                <div className="flex flex-wrap gap-1.5 max-h-36 overflow-y-auto">
                  {allVehicles.filter(e => e !== 'TODAS').map(eco => {
                    const active = selectedUnits.includes(eco)
                    return (
                      <button key={eco} onClick={() => toggleUnit(eco)}
                        className={`px-2.5 py-1 rounded-full border text-xs font-bold font-mono flex items-center gap-1 transition-colors ${active ? 'bg-blue-50 border-blue-200 text-blue-700' : 'bg-gray-50 border-gray-200 text-gray-400 hover:bg-gray-100'}`}>
                        {eco}{active && <X className="w-2.5 h-2.5" />}
                      </button>
                    )
                  })}
                </div>
              )}
              <p className="text-xs text-gray-400 mt-1.5">
                {selectedUnits.filter(u => u !== 'TODAS').length} de {allVehicles.filter(e => e !== 'TODAS').length} seleccionadas
              </p>
            </div>

            {/* Detalle por carga (solo combustible) */}
            {selectedReport.supportsDetail && (
              <label className="flex items-center gap-3 cursor-pointer">
                <div onClick={() => setShowDetail(v => !v)}
                  className={`w-5 h-5 rounded border flex items-center justify-center transition-colors cursor-pointer ${showDetail ? 'bg-blue-500 border-blue-500' : 'border-gray-300 bg-white hover:border-blue-400'}`}>
                  {showDetail && <Check className="w-3.5 h-3.5 text-white" />}
                </div>
                <div>
                  <span className="text-sm text-gray-700 font-medium block">Ver cargas individuales</span>
                  <span className="text-xs text-gray-400">Incluye fecha, hora y proveedor</span>
                </div>
              </label>
            )}

            {/* Formato */}
            <div>
              <label className="text-xs font-bold text-gray-700 uppercase tracking-wider block mb-2">Formato</label>
              <div className="grid grid-cols-3 gap-2">
                {[
                  { id: 'PDF',   icon: FileText,       desc: 'Con gráficas' },
                  { id: 'Excel', icon: FileSpreadsheet, desc: 'Nativo .xlsx' },
                  { id: 'CSV',   icon: FileJson,        desc: 'Datos planos' },
                ].map(f => {
                  const Icon = f.icon
                  return (
                    <button key={f.id} onClick={() => setFormat(f.id)}
                      className={`flex flex-col items-center justify-center p-3 rounded-xl border-2 transition-colors ${format === f.id ? 'border-blue-500 bg-blue-50' : 'border-gray-100 bg-white hover:border-gray-200'}`}>
                      <Icon className={`w-5 h-5 mb-0.5 ${format === f.id ? 'text-blue-500' : 'text-gray-400'}`} />
                      <span className={`text-xs font-bold ${format === f.id ? 'text-blue-700' : 'text-gray-600'}`}>{f.id}</span>
                      <span className="text-xs text-gray-400 mt-0.5">{f.desc}</span>
                    </button>
                  )
                })}
              </div>
            </div>

            {format === 'PDF' && (
              <label className="flex items-center gap-3 cursor-pointer">
                <div onClick={() => setWithChart(v => !v)}
                  className={`w-5 h-5 rounded border flex items-center justify-center transition-colors cursor-pointer ${withChart ? 'bg-blue-500 border-blue-500' : 'border-gray-300 bg-white hover:border-blue-400'}`}>
                  {withChart && <Check className="w-3.5 h-3.5 text-white" />}
                </div>
                <span className="text-sm text-gray-700 font-medium">Incluir gráfica de barras</span>
              </label>
            )}

            {error && (
              <div className="flex items-start gap-2 text-xs text-red-600 bg-red-50 border border-red-100 rounded-xl p-3">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />{error}
              </div>
            )}
            {lastGenerated && !error && (
              <div className="flex items-start gap-2 text-xs text-green-700 bg-green-50 border border-green-100 rounded-xl p-3">
                <Check className="w-4 h-4 shrink-0 mt-0.5" />Descargado: {lastGenerated}
              </div>
            )}
          </div>

          <div className="p-4 border-t border-gray-100 bg-gray-50">
            <button onClick={handleGenerate} disabled={generating}
              className="w-full py-3 rounded-xl bg-blue-600 text-white font-bold text-sm hover:bg-blue-700 active:bg-blue-800 transition-colors shadow-sm flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed">
              {generating ? <><Loader2 className="w-4 h-4 animate-spin" /> Generando...</> : <><Download className="w-4 h-4" /> Generar {format}</>}
            </button>
            <p className="text-center text-xs text-gray-400 mt-2">
              {periodLabel} · {filteredData.length} registro{filteredData.length !== 1 ? 's' : ''}
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
