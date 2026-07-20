"""
pdf_routes.py — Módulo de exportación a PDF (ReportLab).

Genera tres tipos de PDF:
  1. /api/pdf/mensual        → Reporte mensual completo (Portada + 5 hojas TECMED)
  2. /api/pdf/bascula        → Actividad de báscula mensual + resumen por unidad
  3. /api/pdf/ejecutivo      → Sólo portada con KPIs clave (1 página)

Todos usan encabezado/pie corporativo de Tersa Mundi.
Orientación: Landscape A4 (297 × 210 mm).
"""

import io
import logging
from datetime import date as _date
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from reportlab.lib          import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles   import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units    import mm
from reportlab.platypus     import (
    BaseDocTemplate, Frame, KeepTogether, PageBreak,
    PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pdf", tags=["PDF"])

# ── Colores corporativos ──────────────────────────────────────────────────────
C_BLUE       = colors.HexColor("#2563EB")
C_BLUE_DARK  = colors.HexColor("#1E3A5F")
C_BLUE_LIGHT = colors.HexColor("#EFF6FF")
C_BLUE_MID   = colors.HexColor("#DBEAFE")
C_WHITE      = colors.white
C_GRAY       = colors.HexColor("#6B7280")
C_GRAY_LIGHT = colors.HexColor("#F9FAFB")
C_GREEN      = colors.HexColor("#16A34A")
C_AMBER      = colors.HexColor("#D97706")
C_RED        = colors.HexColor("#DC2626")
C_BLACK      = colors.HexColor("#111827")

EMPRESA = "Tersa Mundi S.A. de C.V."
SISTEMA = "FleetOps"

PAGE_W, PAGE_H = landscape(A4)
MARGIN = 14 * mm

# ── Nombres de meses ──────────────────────────────────────────────────────────
MESES = {
    1:"Enero",2:"Febrero",3:"Marzo",4:"Abril",5:"Mayo",6:"Junio",
    7:"Julio",8:"Agosto",9:"Septiembre",10:"Octubre",11:"Noviembre",12:"Diciembre",
}

LABELS = {
    "eco":                 "No. Económico",
    "km_total":            "Km Total",
    "km_prod":             "Km Productivo",
    "km_trasl":            "Km Traslado",
    "km_disp":             "Km Disposición",
    "km_no_prod":          "Km No Productivo",
    "km_por_litro":        "Km/Lt",
    "alerta_rendimiento":  "Alerta",
    "diesel_lts":          "Lts Diesel",
    "diesel_importe":      "Importe Diesel",
    "gasolina_lts":        "Lts Gasolina",
    "total_lts":           "Total Litros",
    "total_importe":       "Total Importe",
    "precio_diesel":       "Precio/Lt",
    "toneladas":           "Toneladas",
    "num_viajes":          "Viajes",
    "tons_prom_por_viaje": "Ton/Viaje",
    "tons_ticket":         "Ton Ticket",
    "variacion_pct":       "Variación %",
    "t_prod_hrs":          "T.Prod (hrs)",
    "t_no_prod_hrs":       "T.No Prod (hrs)",
    "ton_por_t_prod":      "Ton/Hr.Prod",
    "ton_por_km_prod":     "Ton/Km.Prod",
    "pct_carga":           "% Carga",
    "litros":              "Litros",
    "num_eco":             "No. Económico",
    "tipo_cliente":        "Tipo Cliente",
    "promedio_ton_viaje":  "Ton/Viaje Prom.",
    "viajes":              "Viajes",
    "turno":               "Turno",
    "dia":                 "Día",
}

HIDDEN = {"vehicle_id"}


# ── Estilos de párrafo ────────────────────────────────────────────────────────

def _styles():
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=14, textColor=C_WHITE, spaceAfter=0),
        "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=11, textColor=C_BLUE_DARK, spaceAfter=4*mm),
        "h3": ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=9,  textColor=C_BLUE_DARK, spaceAfter=2*mm),
        "sub": ParagraphStyle("sub", fontName="Helvetica", fontSize=8, textColor=C_GRAY, spaceAfter=6*mm),
        "kpi_val": ParagraphStyle("kpi_val", fontName="Helvetica-Bold", fontSize=18, textColor=C_BLUE, alignment=1),
        "kpi_lab": ParagraphStyle("kpi_lab", fontName="Helvetica",      fontSize=7,  textColor=C_GRAY, alignment=1),
        "cell":   ParagraphStyle("cell",  fontName="Helvetica", fontSize=7.5, textColor=C_BLACK),
        "note":   ParagraphStyle("note",  fontName="Helvetica-Oblique", fontSize=7, textColor=C_GRAY),
    }


# ── Encabezado / pie de página ────────────────────────────────────────────────

def _make_page_template(title: str, period: str) -> PageTemplate:
    """Crea el PageTemplate con encabezado azul y pie gris."""
    frame = Frame(
        MARGIN, MARGIN,
        PAGE_W - 2*MARGIN,
        PAGE_H - 2*MARGIN - 18*mm,   # deja espacio para encabezado
        id="main",
        topPadding=4*mm,
    )

    def _on_page(canvas, doc):
        canvas.saveState()

        # Barra azul superior
        canvas.setFillColor(C_BLUE)
        canvas.rect(0, PAGE_H - 18*mm, PAGE_W, 18*mm, fill=1, stroke=0)

        # Logo TM
        canvas.setFillColor(C_WHITE)
        canvas.roundRect(MARGIN, PAGE_H - 14*mm, 10*mm, 10*mm, 1*mm, fill=1, stroke=0)
        canvas.setFillColor(C_BLUE)
        canvas.setFont("Helvetica-Bold", 7)
        canvas.drawCentredString(MARGIN + 5*mm, PAGE_H - 9*mm, "TM")

        # Empresa
        canvas.setFont("Helvetica-Bold", 9)
        canvas.setFillColor(C_WHITE)
        canvas.drawString(MARGIN + 13*mm, PAGE_H - 8.5*mm, EMPRESA)

        # Título del reporte (derecha)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 7*mm, title)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(C_BLUE_MID)
        canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 12*mm, period)

        # Línea separadora
        canvas.setStrokeColor(C_BLUE_LIGHT)
        canvas.setLineWidth(0.4)
        canvas.line(MARGIN, PAGE_H - 19*mm, PAGE_W - MARGIN, PAGE_H - 19*mm)

        # Pie de página
        canvas.setFont("Helvetica", 6.5)
        canvas.setFillColor(C_GRAY)
        canvas.line(MARGIN, 10*mm, PAGE_W - MARGIN, 10*mm)
        canvas.drawString(MARGIN, 7*mm, EMPRESA)
        canvas.drawRightString(
            PAGE_W - MARGIN, 7*mm,
            f"Página {doc.page}  ·  {SISTEMA}  ·  {_date.today().strftime('%d/%m/%Y')}"
        )

        canvas.restoreState()

    return PageTemplate(id="main", frames=[frame], onPage=_on_page)


# ── Tabla de datos ────────────────────────────────────────────────────────────

def _make_table(rows: list[dict], keys: list[str] | None = None, col_widths=None) -> Table:
    """
    Construye una Table de ReportLab desde una lista de dicts.
    Aplica colores alternados, cabecera azul y fila de totales.
    """
    if not rows:
        return Table([["Sin datos"]])

    if keys is None:
        keys = [k for k in rows[0].keys() if k not in HIDDEN]

    heads = [LABELS.get(k, k.replace("_", " ").title()) for k in keys]

    ST = _styles()

    def _fmt(key: str, val) -> str:
        if val is None:
            return "—"
        if key in ("diesel_importe", "total_importe", "precio_diesel"):
            return f"${float(val):,.2f}"
        if key in ("pct_carga", "variacion_pct", "pct_toneladas"):
            try:
                return f"{float(val)*100:.1f}%" if float(val) <= 1 else f"{float(val):.1f}%"
            except Exception:
                return str(val)
        if key in ("km_por_litro", "tons_prom_por_viaje", "promedio_ton_viaje"):
            try:
                return f"{float(val):.3f}"
            except Exception:
                return str(val)
        if key in ("km_total", "km_prod", "km_trasl", "km_disp", "km_no_prod", "km_mes"):
            try:
                return f"{int(float(val)):,}"
            except Exception:
                return str(val)
        if key in ("toneladas", "litros", "diesel_lts", "gasolina_lts", "total_lts", "litros_mes"):
            try:
                return f"{float(val):,.2f}"
            except Exception:
                return str(val)
        return str(val)

    def _alert_para(val):
        v = str(val or "").lower()
        color = C_GREEN if v == "normal" else (C_AMBER if v == "bajo" else (C_RED if v == "critico" else C_GRAY))
        s = ParagraphStyle("a", fontName="Helvetica-Bold", fontSize=7, textColor=color, alignment=1)
        return Paragraph(str(val or ""), s)

    # Encabezados
    data = [[Paragraph(h, ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=7.5,
                                          textColor=C_WHITE, alignment=1))
             for h in heads]]

    # Filas
    for row in rows:
        r = []
        for key in keys:
            val = row.get(key)
            if key == "alerta_rendimiento":
                r.append(_alert_para(val))
            else:
                fval = _fmt(key, val)
                align = 0 if key in ("eco", "num_eco", "tipo_cliente", "turno", "dia") else 1
                s = ParagraphStyle("td", fontName="Helvetica", fontSize=7.5,
                                   textColor=C_BLACK, alignment=align)
                r.append(Paragraph(fval, s))
        data.append(r)

    # Fila de totales
    total_row = [Paragraph("TOTAL", ParagraphStyle("tot", fontName="Helvetica-Bold",
                                                    fontSize=7.5, textColor=C_BLUE_DARK))]
    for key in keys[1:]:
        samples = [row.get(key) for row in rows if row.get(key) is not None]
        if samples and all(isinstance(s, (int, float)) for s in samples):
            total = sum(float(s) for s in samples)
            total_row.append(Paragraph(_fmt(key, total),
                                       ParagraphStyle("tot", fontName="Helvetica-Bold",
                                                      fontSize=7.5, textColor=C_BLUE_DARK, alignment=1)))
        else:
            total_row.append(Paragraph("", ParagraphStyle("tot")))
    data.append(total_row)

    n_rows = len(data)
    n_cols = len(keys)

    # Anchos automáticos si no se pasan
    if col_widths is None:
        avail = PAGE_W - 2*MARGIN
        col_widths = [avail / n_cols] * n_cols

    ts = TableStyle([
        # Encabezado
        ("BACKGROUND",  (0, 0),           (-1, 0),           C_BLUE),
        ("TEXTCOLOR",   (0, 0),           (-1, 0),           C_WHITE),
        ("FONTNAME",    (0, 0),           (-1, 0),           "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0),           (-1, 0),           7.5),
        ("ROWBACKGROUND", (0, 0),         (-1, 0),           C_BLUE),
        ("ROWHEIGHT",   (0, 0),           (0, 0),            8*mm),
        # Filas alternadas
        *[("BACKGROUND", (0, i), (-1, i), C_BLUE_LIGHT if i % 2 == 0 else C_WHITE)
          for i in range(1, n_rows - 1)],
        # Fila de totales
        ("BACKGROUND",  (0, -1),          (-1, -1),          C_BLUE_MID),
        ("FONTNAME",    (0, -1),          (-1, -1),          "Helvetica-Bold"),
        # Bordes
        ("GRID",        (0, 0),           (-1, -1),          0.3, colors.HexColor("#D1D5DB")),
        ("LINEBELOW",   (0, 0),           (-1, 0),           1,   C_BLUE),
        ("ROWHEIGHT",   (0, 1),           (-1, -1),          7*mm),
        ("VALIGN",      (0, 0),           (-1, -1),          "MIDDLE"),
        ("TOPPADDING",  (0, 0),           (-1, -1),          1.5*mm),
        ("BOTTOMPADDING",(0, 0),          (-1, -1),          1.5*mm),
        ("LEFTPADDING", (0, 0),           (-1, -1),          2*mm),
        ("RIGHTPADDING",(0, 0),           (-1, -1),          2*mm),
    ])

    tbl = Table(data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(ts)
    return tbl


# ── KPI Box (para portada y reporte ejecutivo) ────────────────────────────────

def _kpi_table(kpis: list[tuple[str, str]]) -> Table:
    """
    kpis = [(valor_str, etiqueta), ...]
    Genera una fila de tarjetas KPI con fondo azul claro.
    """
    ST = _styles()
    n  = len(kpis)
    cell_w = (PAGE_W - 2*MARGIN) / n

    data = [[
        Table(
            [[Paragraph(val,   ST["kpi_val"])],
             [Paragraph(label, ST["kpi_lab"])]],
            colWidths=[cell_w - 4*mm],
            style=TableStyle([
                ("ALIGN",       (0, 0), (-1, -1), "CENTER"),
                ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING",  (0, 0), (-1, -1), 3*mm),
                ("BOTTOMPADDING",(0,0), (-1, -1), 3*mm),
            ])
        )
        for val, label in kpis
    ]]

    outer_style = TableStyle([
        ("BACKGROUND",  (0, 0), (-1, -1), C_BLUE_LIGHT),
        ("BOX",         (0, 0), (-1, -1), 0.5, C_BLUE_MID),
        ("INNERGRID",   (0, 0), (-1, -1), 0.5, C_BLUE_MID),
        ("ROWHEIGHT",   (0, 0), (-1, -1), 20*mm),
        ("LEFTPADDING", (0, 0), (-1, -1), 2*mm),
        ("RIGHTPADDING",(0, 0), (-1, -1), 2*mm),
    ])
    tbl = Table(data, colWidths=[cell_w]*n)
    tbl.setStyle(outer_style)
    return tbl


# ── Builder principal ─────────────────────────────────────────────────────────

def _build_pdf(
    sections: list,          # lista de (section_title, rows, keys_or_None)
    pdf_title: str,
    period: str,
    portada_data: dict = None,   # datos para la portada ejecutiva
) -> bytes:
    buf  = io.BytesIO()
    ST   = _styles()

    doc = BaseDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN + 18*mm,
        bottomMargin=MARGIN + 8*mm,
    )
    doc.addPageTemplates([_make_page_template(pdf_title, period)])

    story = []

    # ── Portada ejecutiva (si se pasa) ────────────────────────────────────────
    if portada_data:
        story.append(Paragraph(EMPRESA, ST["h1"]))
        story.append(Spacer(1, 2*mm))
        story.append(Paragraph(pdf_title, ST["h2"]))
        story.append(Paragraph(period, ST["sub"]))
        story.append(Spacer(1, 4*mm))

        kpis_raw = [
            (f'{portada_data.get("total_unidades", 0)}',       "Unidades"),
            (f'{portada_data.get("activas", 0)}',              "Activas hoy"),
            (f'{portada_data.get("total_km", 0):,.0f}',        "Km Totales"),
            (f'{portada_data.get("total_toneladas", 0):,.1f}', "Toneladas"),
            (f'{portada_data.get("total_litros", 0):,.1f}',    "Lts Diesel"),
            (f'{portada_data.get("km_por_litro", 0):.3f}',     "Km/Litro"),
        ]
        story.append(_kpi_table(kpis_raw))
        story.append(Spacer(1, 6*mm))

        # Totales financieros
        fin_rows = [
            {"concepto": "Total Litros",  "valor": f'{portada_data.get("total_litros", 0):,.2f}'},
            {"concepto": "Total Importe", "valor": f'${portada_data.get("total_importe", 0):,.2f}'},
            {"concepto": "Precio Prom./Lt", "valor": f'${portada_data.get("precio_promedio", 0):,.4f}'},
            {"concepto": "Km/Litro Flota", "valor": f'{portada_data.get("km_por_litro", 0):.3f}'},
        ]
        avail = PAGE_W - 2*MARGIN
        fin_tbl = _make_table(
            fin_rows, keys=["concepto", "valor"],
            col_widths=[avail * 0.6, avail * 0.4],
        )
        story.append(fin_tbl)
        story.append(PageBreak())

    # ── Secciones de datos ────────────────────────────────────────────────────
    for sec_title, rows, keys in sections:
        if not rows:
            continue
        story.append(Paragraph(sec_title, ST["h2"]))
        story.append(Paragraph(
            f"{len(rows)} unidades  ·  {period}",
            ST["sub"],
        ))
        story.append(Spacer(1, 2*mm))
        tbl = _make_table(rows, keys=keys)
        story.append(KeepTogether([tbl]))
        story.append(Spacer(1, 4*mm))
        story.append(PageBreak())

    doc.build(story)
    buf.seek(0)
    return buf.read()


# ── Helpers de datos ──────────────────────────────────────────────────────────

def _period_label(year: int, month: int) -> str:
    return f"{MESES.get(month, str(month))} de {year}"


async def _load_metrics(year: int, month: int) -> list[dict]:
    from src.routes.report_routes import _get_all_unit_metrics
    return _get_all_unit_metrics(year, month)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/mensual")
async def pdf_mensual(
    year:  int = Query(default=None),
    month: int = Query(default=None),
):
    """
    PDF completo del reporte mensual TECMED.
    Contiene: portada ejecutiva + Hoja 1 (Operatividad) + Hoja 2 (Km/Rendimiento)
              + Hoja 4 (Combustible) + Hoja 5 (Tonelaje).

    GET /api/pdf/mensual?year=2026&month=5
    """
    today  = _date.today()
    y = year  or today.year
    m = month or today.month
    period = _period_label(y, m)

    metrics = await _load_metrics(y, m)
    if not metrics:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Sin métricas para el período indicado.")

    # Portada
    from src.services.metrics_engine import calcular_portada
    portada = calcular_portada(metrics, y, m)

    # Secciones
    hoja1_rows = [
        {k: met.get(k) for k in ("eco","toneladas","t_prod_hrs","t_no_prod_hrs",
                                  "ton_por_t_prod","km_prod","km_no_prod","ton_por_km_prod","pct_carga")}
        for met in metrics
    ]
    hoja2_rows = [
        {k: met.get(k) for k in ("eco","km_prod","km_trasl","km_disp","km_total",
                                  "diesel_lts","km_por_litro","alerta_rendimiento")}
        for met in metrics
    ]
    hoja4_rows = [
        {k: met.get(k) for k in ("eco","diesel_lts","diesel_importe","gasolina_lts",
                                  "total_lts","total_importe","precio_diesel")}
        for met in metrics
    ]
    hoja5_rows = [
        {k: met.get(k) for k in ("eco","toneladas","num_viajes","tons_prom_por_viaje",
                                  "tons_ticket","variacion_pct")}
        for met in metrics
    ]

    sections = [
        ("Hoja 1 — Operatividad por Unidad",            hoja1_rows, None),
        ("Hoja 2 — Kilómetros y Rendimiento",           hoja2_rows, None),
        ("Hoja 4 — Consumo y Costo de Combustible",     hoja4_rows, None),
        ("Hoja 5 — Tonelaje por Unidad",                hoja5_rows, None),
    ]

    pdf_bytes = _build_pdf(
        sections=sections,
        pdf_title=f"Reporte Mensual — {period}",
        period=period,
        portada_data=portada,
    )

    filename = f"reporte_mensual_{y}-{m:02d}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/bascula")
async def pdf_bascula(
    year:  int = Query(default=None),
    month: int = Query(default=None),
):
    """
    PDF de báscula: resumen mensual por unidad + desglose por tipo de cliente
    + reporte por turno.

    GET /api/pdf/bascula?year=2026&month=5
    """
    from src.database import db_service

    today  = _date.today()
    y = year  or today.year
    m = month or today.month
    period = _period_label(y, m)

    por_unidad_raw = await db_service.get_bascula_monthly_by_eco(y, m)
    por_tipo_raw   = await db_service.get_bascula_monthly_by_tipo_cliente(y, m)
    turnos_raw     = await db_service.get_bascula_by_turno(y, m)

    if not por_unidad_raw:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Sin registros de báscula para el período indicado.")

    from collections import defaultdict

    # Consolidar por eco
    eco_agg: dict[str, dict] = defaultdict(lambda: {"toneladas": 0.0, "viajes": 0})
    for row in por_unidad_raw:
        eco = row["num_eco"]
        eco_agg[eco]["toneladas"] += row["toneladas"]
        eco_agg[eco]["viajes"]    += row["viajes"]
    unidad_rows = [
        {
            "num_eco":            eco,
            "toneladas":          round(d["toneladas"], 3),
            "viajes":             d["viajes"],
            "promedio_ton_viaje": round(d["toneladas"] / d["viajes"], 3) if d["viajes"] else 0,
        }
        for eco, d in sorted(eco_agg.items(), key=lambda x: -x[1]["toneladas"])
    ]

    # Consolidar por tipo_cliente
    tc_agg: dict[str, dict] = defaultdict(lambda: {"toneladas": 0.0, "viajes": 0})
    for row in por_tipo_raw:
        tc = row["tipo_cliente"] or "SIN TIPO"
        tc_agg[tc]["toneladas"] += row["toneladas"]
        tc_agg[tc]["viajes"]    += row["viajes"]
    tipo_rows = [
        {"tipo_cliente": tc, "toneladas": round(d["toneladas"], 3), "viajes": d["viajes"]}
        for tc, d in sorted(tc_agg.items(), key=lambda x: -x[1]["toneladas"])
    ]

    # Turno: aplanar
    turno_rows = [
        {
            "dia":          r["dia"],
            "turno":        r["turno"],
            "tipo_cliente": r["tipo_cliente"],
            "toneladas":    r["toneladas"],
            "viajes":       r["viajes"],
        }
        for r in turnos_raw
    ]

    # Totales para portada
    total_tons   = round(sum(r["toneladas"] for r in unidad_rows), 3)
    total_viajes = sum(r["viajes"] for r in unidad_rows)
    portada_data = {
        "total_unidades":  len(unidad_rows),
        "activas":         len([r for r in unidad_rows if r["viajes"] > 0]),
        "total_km":        0,
        "total_toneladas": total_tons,
        "total_litros":    0,
        "km_por_litro":    0,
        "total_importe":   0,
        "precio_promedio": 0,
    }

    sections = [
        ("Tonelaje por Unidad",                unidad_rows, None),
        ("Tonelaje por Tipo de Cliente",        tipo_rows,   None),
        ("Detalle por Turno",                   turno_rows,  None),
    ]

    pdf_bytes = _build_pdf(
        sections=sections,
        pdf_title=f"Reporte Báscula — {period}",
        period=period,
        portada_data=portada_data,
    )

    filename = f"reporte_bascula_{y}-{m:02d}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/ejecutivo")
async def pdf_ejecutivo(
    year:  int = Query(default=None),
    month: int = Query(default=None),
):
    """
    PDF ejecutivo de 1-2 páginas: sólo KPIs de portada + tabla comparativa
    de los últimos 3 meses. Ideal para directivos.

    GET /api/pdf/ejecutivo?year=2026&month=5
    """
    today = _date.today()
    y = year  or today.year
    m = month or today.month
    period = _period_label(y, m)

    from src.services.metrics_engine import calcular_portada
    from src.routes.report_routes import _get_all_unit_metrics

    # Datos del mes actual
    metrics = _get_all_unit_metrics(y, m)
    portada = calcular_portada(metrics, y, m) if metrics else {}

    # Comparativo 3 meses
    comp_rows = []
    for i in range(3):
        mo = m - i
        yr = y
        if mo <= 0:
            mo += 12
            yr -= 1
        mets_i = _get_all_unit_metrics(yr, mo)
        if mets_i:
            p = calcular_portada(mets_i, yr, mo)
            comp_rows.append({
                "periodo":      p.get("periodo", ""),
                "total_km":     p.get("total_km", 0),
                "total_litros": p.get("total_litros", 0),
                "km_por_litro": p.get("km_por_litro", 0),
                "toneladas":    p.get("total_toneladas", 0),
                "importe":      p.get("total_importe", 0),
            })

    sections = [
        ("Comparativo Últimos 3 Meses", comp_rows, None),
    ]

    pdf_bytes = _build_pdf(
        sections=sections,
        pdf_title=f"Reporte Ejecutivo — {period}",
        period=period,
        portada_data=portada if portada else None,
    )

    filename = f"reporte_ejecutivo_{y}-{m:02d}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )