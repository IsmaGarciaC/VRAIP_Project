"""VRAIP dashboard -- read-only Streamlit view over data/vraip.db.

Two views (main panel + per-volcano detail) built strictly on the read-only helpers in
database.db. This module never opens sqlite3 directly and never writes: no INSERT,
UPDATE or DELETE happens anywhere in the dashboard.

Data caveats surfaced deliberately in the UI (they are properties of the pipeline, not
bugs to work around here):
  * bulletins.published_at is the INGESTION timestamp, not the bulletin's own stated
    publication date -- every date axis and label says "ingesta" for that reason.
  * bulletins.source_url is the portal entry point, not a per-document permalink.
  * some ai_alerts rows hold the interpreter's pre-written fallback text instead of live
    Gemini output; the dashboard shows whatever is stored and does not try to tell them
    apart.
  * a volcano may have zero ingested bulletins (currently Tungurahua); every view has to
    degrade to "Sin datos disponibles" rather than raise.

Citizen-facing text is in Spanish per the Chapter 3 non-functional requirement; code
comments are in English.
"""

import os
import re

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from database.db import get_dashboard_dataframe, get_volcanoes_dataframe

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSS_PATH = os.path.join(BASE_DIR, "style.css")

# --------------------------------------------------------------------------------------
# Alert-level vocabulary
# --------------------------------------------------------------------------------------
# classifier.py stores English labels ("Yellow Alert", ...). The dashboard shows Spanish.
#
# Colors are the reserved status palette (good / warning / serious / critical) and are
# mode-invariant. A green/yellow/orange/red scale cannot be made colorblind-safe -- red
# vs green measures deltaE 4.1 under deuteranopia -- and the hues are fixed by the IGEPN
# alert convention, so hue is never the only encoding: the level name is always printed
# (badge, legend entry, hover text, y-axis tick) and a distinct glyph plus an escalating
# marker size ride along as secondary channels.
LEVEL_UNKNOWN = "sin-datos"

ALERT_LEVELS = {
    "green":  {"key": "verde",    "label": "Alerta Verde",    "color": "#0ca30c", "ordinal": 1, "glyph": "●", "size": 12},
    "yellow": {"key": "amarilla", "label": "Alerta Amarilla", "color": "#fab219", "ordinal": 2, "glyph": "▲", "size": 15},
    "orange": {"key": "naranja",  "label": "Alerta Naranja",  "color": "#ec835a", "ordinal": 3, "glyph": "◆", "size": 18},
    "red":    {"key": "roja",     "label": "Alerta Roja",     "color": "#d03b3b", "ordinal": 4, "glyph": "■", "size": 21},
}

NO_DATA = {
    "key": LEVEL_UNKNOWN,
    "label": "Sin datos",
    "color": "#898781",
    "ordinal": None,
    "glyph": "○",
    "size": 10,
}

# Fixed display order: escalating severity, "Sin datos" last.
LEVEL_ORDER = [ALERT_LEVELS[k]["label"] for k in ("green", "yellow", "orange", "red")] + [NO_DATA["label"]]

# Chart chrome, one step off the surface in each mode (recessive grid and axes).
CHROME = {
    "light": {"surface": "#ffffff", "text": "#0b0b0b", "secondary": "#52514e",
              "muted": "#898781", "grid": "#e1e0d9", "axis": "#c3c2b7",
              "land": "#f0efec", "ocean": "#e7edf3"},
    "dark":  {"surface": "#0e1117", "text": "#ffffff", "secondary": "#c3c2b7",
              "muted": "#898781", "grid": "#2c2c2a", "axis": "#383835",
              "land": "#22262c", "ocean": "#161b22"},
}


def level_info(alert_level):
    """Maps a stored alert_level string onto its display vocabulary.

    Falls back to the "Sin datos" entry for None/NaN/unrecognised values so a missing
    classification can never raise.
    """
    if alert_level is None or (isinstance(alert_level, float) and pd.isna(alert_level)):
        return NO_DATA
    text = str(alert_level).strip().lower()
    for keyword, info in ALERT_LEVELS.items():
        if keyword in text:
            return info
    return NO_DATA


# --------------------------------------------------------------------------------------
# Data access (read-only, cached)
# --------------------------------------------------------------------------------------
@st.cache_data(ttl=300, show_spinner="Cargando datos del pipeline...")
def load_data():
    """Reads the pipeline join and the volcano roster, adding display-only columns."""
    bulletins = get_dashboard_dataframe()
    volcanoes = get_volcanoes_dataframe()

    # Parse the ingestion timestamp once; unparseable values become NaT rather than
    # breaking the sort or the time axis.
    bulletins["fecha_ingesta"] = pd.to_datetime(bulletins["published_at"], errors="coerce")

    levels = bulletins["alert_level"].apply(level_info)
    bulletins["nivel_label"] = [lv["label"] for lv in levels]
    bulletins["nivel_ordinal"] = [lv["ordinal"] for lv in levels]
    bulletins["nivel_color"] = [lv["color"] for lv in levels]

    # Newest first; bulletin_id breaks ties between rows ingested in the same second.
    bulletins = bulletins.sort_values(
        ["fecha_ingesta", "bulletin_id"], ascending=False, na_position="last"
    ).reset_index(drop=True)

    return bulletins, volcanoes


def latest_by_volcano(bulletins, volcanoes):
    """One row per monitored volcano: its most recent bulletin, or empty fields if none.

    Left-joins from the volcano roster so a volcano with zero ingested bulletins
    (currently Tungurahua) still appears, with nivel_label "Sin datos".
    """
    if bulletins.empty:
        latest = bulletins
    else:
        latest = bulletins.drop_duplicates(subset="volcano_id", keep="first")

    merged = volcanoes.merge(
        latest.drop(columns=["volcano_name", "latitude", "longitude", "igepn_code"],
                    errors="ignore"),
        on="volcano_id",
        how="left",
    )
    merged["nivel_label"] = merged["nivel_label"].fillna(NO_DATA["label"])
    merged["tiene_datos"] = merged["bulletin_id"].notna()
    return merged


# --------------------------------------------------------------------------------------
# Text helpers
# --------------------------------------------------------------------------------------
def clean_text(value):
    """Returns a stripped string for any cell value; empty string for None/NaN."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def one_line_summary(explanation, limit=150):
    """First sentence of the stored AI explanation, truncated -- never re-generated.

    The stored text may be Spanish (live Gemini) or English (fallback template); it is
    shown exactly as stored, only shortened.
    """
    text = re.sub(r"\s+", " ", clean_text(explanation))
    if not text:
        return "Sin resumen disponible."

    match = re.search(r"(.+?[.!?])(\s|$)", text)
    sentence = match.group(1) if match else text
    if len(sentence) <= limit:
        return sentence

    cut = sentence[:limit].rsplit(" ", 1)[0]
    return f"{cut.rstrip(',.;:')}..."


def parse_recommendations(recommendations):
    """Splits the stored recommendations field into a list of bullet strings.

    The interpreter writes one "- ..." item per line, sometimes indented. If no bullet
    markers survive parsing, the whole field is returned as a single item so nothing
    stored is ever dropped.
    """
    text = clean_text(recommendations)
    if not text:
        return []

    items = []
    for line in text.splitlines():
        item = re.sub(r"^\s*(?:[-*•–—]|\d+[.)])\s*", "", line).strip()
        if item:
            items.append(item)
    return items or [text]


def format_date(value, with_time=True):
    """Formats an ingestion timestamp for display; 'Sin datos' when missing."""
    if value is None or pd.isna(value):
        return "Sin datos"
    stamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(stamp):
        return clean_text(value) or "Sin datos"
    return stamp.strftime("%d/%m/%Y %H:%M" if with_time else "%d/%m/%Y")


def badge_html(alert_level, large=False):
    """Inline badge: colored chip + glyph + the level name spelled out."""
    info = level_info(alert_level)
    size_class = " vraip-badge--grande" if large else ""
    return (
        f'<span class="vraip-badge vraip-badge--{info["key"]}{size_class}">'
        f'{info["glyph"]} {info["label"]}</span>'
    )


# --------------------------------------------------------------------------------------
# Charts
# --------------------------------------------------------------------------------------
def chart_chrome():
    """Chart palette for the viewer's current theme, defaulting to light."""
    mode = "light"
    try:
        theme = getattr(st.context, "theme", None)
        if theme is not None and getattr(theme, "type", None) == "dark":
            mode = "dark"
    except Exception:
        # No script context (e.g. the figure is built outside a Streamlit run).
        pass
    return CHROME[mode]


def build_map(status):
    """Map of Ecuador with one marker per monitored volcano.

    Uses a plotly geo trace rather than a tile map: it needs neither a Mapbox token nor
    a tile server, so it renders identically offline (this project demos offline).
    Volcanoes with no bulletins are drawn in the neutral "Sin datos" color instead of
    being dropped, so the map always shows the full monitored set.
    """
    chrome = chart_chrome()
    fig = go.Figure()

    # One trace per level so the legend spells out every level present.
    for label in LEVEL_ORDER:
        subset = status[status["nivel_label"] == label]
        if subset.empty:
            continue
        info = next(
            (i for i in list(ALERT_LEVELS.values()) + [NO_DATA] if i["label"] == label), NO_DATA
        )
        fig.add_trace(
            go.Scattergeo(
                lat=subset["latitude"],
                lon=subset["longitude"],
                text=subset["volcano_name"],
                # Labels sit beside the markers, not above them: the volcanoes are
                # close together in latitude, so a "top center" label would collide
                # with the marker of the volcano to the north.
                textposition="middle right",
                textfont=dict(color=chrome["secondary"], size=12),
                mode="markers+text",
                name=label,
                marker=dict(
                    size=info["size"],
                    color=info["color"],
                    # 2px surface ring keeps overlapping markers legible.
                    line=dict(color=chrome["surface"], width=2),
                ),
                customdata=subset[["nivel_label", "resumen"]].to_numpy(),
                hovertemplate=(
                    "<b>%{text}</b><br>%{customdata[0]}<br>%{customdata[1]}<extra></extra>"
                ),
            )
        )

    # The window is deliberately wider in longitude than the country itself: a geo
    # subplot preserves geographic aspect, so a near-square window leaves large dead
    # margins in a wide Streamlit container.
    fig.update_geos(
        resolution=50,
        showcountries=True, countrycolor=chrome["axis"],
        showsubunits=True, subunitcolor=chrome["grid"],
        showland=True, landcolor=chrome["land"],
        showocean=True, oceancolor=chrome["ocean"],
        showlakes=False, showframe=False, coastlinecolor=chrome["axis"],
        lataxis_range=[-5.4, 1.9],
        lonaxis_range=[-85.0, -72.0],
        bgcolor="rgba(0,0,0,0)",
    )
    fig.update_layout(
        height=480,
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(
            orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0,
            font=dict(color=chrome["secondary"]), title_text="",
        ),
        hoverlabel=dict(font_size=13),
    )
    return fig


def build_history_chart(history):
    """Alert-level history for one volcano, as a step line over ingestion dates.

    Levels are plotted on an ordinal scale (Verde=1 ... Roja=4) but the y-axis is
    labelled with the level names, never the numbers. The line is drawn as steps
    ("hv") because an alert level holds until it is changed -- a straight interpolation
    would imply intermediate levels that were never issued.
    """
    chrome = chart_chrome()
    plotted = history.dropna(subset=["nivel_ordinal", "fecha_ingesta"]).sort_values("fecha_ingesta")

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=plotted["fecha_ingesta"],
            y=plotted["nivel_ordinal"],
            mode="lines+markers",
            line=dict(color=chrome["muted"], width=2, shape="hv"),
            marker=dict(
                size=10,
                color=plotted["nivel_color"],
                line=dict(color=chrome["surface"], width=2),
            ),
            customdata=plotted[["nivel_label"]].to_numpy(),
            hovertemplate="%{x|%d/%m/%Y %H:%M}<br><b>%{customdata[0]}</b><extra></extra>",
            showlegend=False,  # single series: the title already names it
        )
    )
    fig.update_layout(
        height=340,
        # Margins leave room for the tick labels; automargin below grows them if the
        # date labels need more.
        margin=dict(l=20, r=20, t=20, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=chrome["secondary"]),
        hovermode="x unified",
    )
    fig.update_xaxes(
        title_text="Fecha de ingesta",  # ingestion date, not the bulletin's own date
        title_font=dict(color=chrome["secondary"]),
        showgrid=False, automargin=True,
        linecolor=chrome["axis"], linewidth=1, ticks="outside", tickcolor=chrome["axis"],
        tickfont=dict(color=chrome["muted"]), tickformat="%d/%m/%y",
    )
    fig.update_yaxes(
        title_text="Nivel de alerta",
        title_font=dict(color=chrome["secondary"]),
        range=[0.5, 4.5],
        tickmode="array",
        tickvals=[info["ordinal"] for info in ALERT_LEVELS.values()],
        # Level names, never the ordinal numbers.
        ticktext=[info["label"].replace("Alerta ", "") for info in ALERT_LEVELS.values()],
        showgrid=True, gridcolor=chrome["grid"], gridwidth=1, automargin=True,
        zeroline=False, linecolor=chrome["axis"], linewidth=1,
        tickfont=dict(color=chrome["muted"]),
    )
    return fig


# --------------------------------------------------------------------------------------
# Views
# --------------------------------------------------------------------------------------
def render_main(bulletins, status):
    """Main panel: summary metrics, national map, per-volcano status cards."""
    st.title("VRAIP - Panel de Riesgo Volcanico")
    st.caption(
        "Monitoreo de la actividad volcanica del Ecuador a partir de los boletines del IGEPN. "
        "El estado mostrado corresponde al ultimo boletin procesado por el pipeline."
    )

    # --- Summary metrics -------------------------------------------------------------
    top_left, top_right = st.columns(2)
    top_left.metric("Volcanes monitoreados", len(status))

    latest_date = bulletins["fecha_ingesta"].max() if not bulletins.empty else None
    top_right.metric(
        "Ultimo boletin procesado",
        format_date(latest_date),
        help="Fecha de ingesta del boletin mas reciente almacenado en la base de datos.",
    )

    counts = status["nivel_label"].value_counts()
    level_columns = st.columns(4)
    for column, info in zip(level_columns, ALERT_LEVELS.values()):
        column.metric(
            info["label"],
            int(counts.get(info["label"], 0)),
            help=f"Volcanes cuyo ultimo boletin fue clasificado como {info['label']}.",
        )

    sin_datos = int(counts.get(NO_DATA["label"], 0))
    if sin_datos:
        st.caption(
            f"{sin_datos} volcan(es) sin boletines ingeridos; se muestran como "
            f"\"{NO_DATA['label']}\" en el mapa y en las tarjetas."
        )

    st.divider()

    # --- Map --------------------------------------------------------------------------
    st.subheader("Mapa de estado actual")
    st.plotly_chart(build_map(status), width="stretch", theme=None)

    # Table-view twin of the map: every value on it is readable without color.
    with st.expander("Ver datos del mapa"):
        st.dataframe(
            pd.DataFrame({
                "Volcan": status["volcano_name"],
                "Nivel de alerta": status["nivel_label"],
                "Ultimo boletin": status["fecha_ingesta"].apply(format_date),
                "Latitud": status["latitude"],
                "Longitud": status["longitude"],
            }),
            hide_index=True,
            width="stretch",
        )

    st.divider()

    # --- Status cards -----------------------------------------------------------------
    st.subheader("Estado por volcan")
    cards = st.columns(2)
    for position, (_, row) in enumerate(status.iterrows()):
        with cards[position % 2]:
            with st.container(border=True):
                st.markdown(
                    f'<p class="vraip-card-title">{row["volcano_name"]}</p>'
                    f'{badge_html(row.get("alert_level"))}',
                    unsafe_allow_html=True,
                )
                if row["tiene_datos"]:
                    st.markdown(
                        f'<p class="vraip-card-meta">Ultimo boletin: '
                        f'{format_date(row["fecha_ingesta"])}</p>'
                        f'<p class="vraip-card-summary">'
                        f'{one_line_summary(row.get("explanation"))}</p>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        '<p class="vraip-card-meta">Ultimo boletin: Sin datos</p>'
                        '<p class="vraip-card-summary">Sin datos disponibles: este volcan '
                        'aun no tiene boletines procesados.</p>',
                        unsafe_allow_html=True,
                    )


def render_detail(bulletins, status, volcano_name):
    """Detail view for one volcano: AI alert, recommendations, history, source."""
    st.title(f"Detalle - {volcano_name}")

    history = bulletins[bulletins["volcano_name"] == volcano_name]
    if history.empty:
        st.info(
            f"Sin datos disponibles: aun no se han procesado boletines para {volcano_name}. "
            "El volcan permanece en la lista de monitoreo y aparecera aqui en cuanto el "
            "pipeline ingiera su primer boletin."
        )
        return

    newest = history.iloc[0]

    # --- Alert level + stored AI explanation ------------------------------------------
    st.markdown(badge_html(newest.get("alert_level"), large=True), unsafe_allow_html=True)
    if not newest.get("alert_level_detected", 1):
        st.caption(
            "Nivel asignado por defecto: el boletin no declaraba explicitamente un nivel "
            "de alerta."
        )

    st.subheader("Explicacion")
    explanation = clean_text(newest.get("explanation"))
    st.write(explanation or "Sin explicacion disponible para este boletin.")

    # --- Recommendations ---------------------------------------------------------------
    st.subheader("Recomendaciones preventivas")
    recommendations = parse_recommendations(newest.get("recommendations"))
    if recommendations:
        st.markdown("\n".join(f"- {item}" for item in recommendations))
    else:
        st.write("Sin recomendaciones disponibles para este boletin.")

    st.divider()

    # --- Alert-level history ------------------------------------------------------------
    st.subheader(f"Historial de nivel de alerta - {volcano_name}")
    st.caption(
        f"{len(history)} boletin(es) procesado(s). El eje horizontal usa la fecha de "
        "ingesta al sistema, no la fecha de publicacion declarada en el boletin."
    )
    st.plotly_chart(build_history_chart(history), width="stretch", theme=None)

    # Table-view twin of the history chart.
    with st.expander("Ver datos del historial"):
        st.dataframe(
            pd.DataFrame({
                "Fecha de ingesta": history["fecha_ingesta"].apply(format_date),
                "Nivel de alerta": history["nivel_label"],
                "Archivo": history["pdf_filename"],
            }),
            hide_index=True,
            width="stretch",
        )

    st.divider()

    # --- Source reference ----------------------------------------------------------------
    st.subheader("Fuente")
    source_url = clean_text(newest.get("source_url")) or "No registrada"
    source_line = (
        f'<a href="{source_url}" target="_blank">{source_url}</a>'
        if source_url.startswith("http")
        else source_url
    )
    st.markdown(
        f'<div class="vraip-source">'
        f'<b>Boletin:</b> {format_date(newest["fecha_ingesta"])} (fecha de ingesta)<br>'
        f'<b>Archivo:</b> {clean_text(newest.get("pdf_filename")) or "No registrado"}<br>'
        f'<b>Origen:</b> {source_line}'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "El enlace corresponde al portal de busqueda de informes del IGEPN, no al "
        "documento especifico."
    )


# --------------------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------------------
def load_css():
    """Injects style.css if present; the dashboard renders fine without it."""
    try:
        with open(CSS_PATH, encoding="utf-8") as handle:
            st.markdown(f"<style>{handle.read()}</style>", unsafe_allow_html=True)
    except OSError:
        pass


def main():
    st.set_page_config(page_title="VRAIP - Riesgo Volcanico", page_icon="🌋", layout="wide")
    load_css()

    bulletins, volcanoes = load_data()
    status = latest_by_volcano(bulletins, volcanoes)
    # Hover summaries are built here so the map trace can read them off one column.
    status["resumen"] = [
        one_line_summary(row["explanation"], limit=90) if row["tiene_datos"]
        else "Sin datos disponibles."
        for _, row in status.iterrows()
    ]

    with st.sidebar:
        st.header("VRAIP")
        view = st.radio("Vista", ["Panel principal", "Detalle por volcan"])
        volcano_name = st.selectbox("Volcan", volcanoes["volcano_name"].tolist())

        st.divider()
        last_run = bulletins["fecha_ingesta"].max() if not bulletins.empty else None
        st.caption("Ultima ejecucion del pipeline")
        st.write(format_date(last_run))
        st.caption(f"{len(bulletins)} boletines procesados | {len(volcanoes)} volcanes")

        if st.button("Actualizar datos", width="stretch"):
            st.cache_data.clear()
            st.rerun()

    if view == "Panel principal":
        render_main(bulletins, status)
    else:
        render_detail(bulletins, status, volcano_name)


main()
