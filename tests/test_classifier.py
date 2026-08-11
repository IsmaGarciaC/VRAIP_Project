"""Offline unit tests for the regex classification engine.

`classify_risk` is a pure function (Spanish bulletin text in, structured dict
out) with no DB / network / API dependency, so every test here runs fast and
fully offline. The synthetic bulletin fragments below are hand-built to match
the exact regex patterns in modules/classifier.py -- note that several of those
patterns are accent-sensitive (e.g. "explosió[nñ]", "podrían", "dióxido de
azufre"), so the accents in the sample text below are load-bearing.
"""

import pytest

from modules.classifier import classify_risk


# ---------------------------------------------------------------------------
# 1. Official alert level
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text, expected_level",
    [
        ("Nivel de Alerta: Roja", "Red Alert"),
        ("Nivel de Alerta - Naranja", "Orange Alert"),
        ("Nivel de Alerta SGR: Amarilla", "Yellow Alert"),
        ("Nivel de Alerta: Verde", "Green Alert"),
        # Blanca is treated as equivalent to Verde by project design decision.
        ("Nivel de Alerta: Blanca", "Green Alert"),
        # Masculine forms ("Nivel" is masculine, so some bulletins agree the
        # color word with it instead of with "Alerta") must match too.
        ("Nivel de Alerta: Rojo", "Red Alert"),
        ("Nivel de Alerta: Amarillo", "Yellow Alert"),
        ("Nivel de Alerta - SGR: Blanco", "Green Alert"),
    ],
)
def test_alert_level_detected(text, expected_level):
    result = classify_risk(text)
    assert result["alert_level"] == expected_level
    assert result["alert_level_detected"] is True


def test_alert_level_defaults_to_yellow_when_absent():
    # No "Nivel de Alerta" phrase -> engine defaults to Yellow but flags that
    # it was assigned, not actually detected.
    result = classify_risk("El volcán presenta actividad moderada.")
    assert result["alert_level"] == "Yellow Alert"
    assert result["alert_level_detected"] is False


# ---------------------------------------------------------------------------
# 2. Activity levels
# ---------------------------------------------------------------------------

def test_activity_levels_extracted():
    text = "Superficial: Alta\nInterna: Baja"
    result = classify_risk(text)
    assert result["surface_activity"] == "Alta"
    assert result["internal_activity"] == "Baja"


def test_activity_levels_not_specified_when_absent():
    result = classify_risk("Boletín sin datos de actividad.")
    assert result["surface_activity"] == "Not Specified"
    assert result["internal_activity"] == "Not Specified"


# ---------------------------------------------------------------------------
# 3. Physical phenomena flags
# ---------------------------------------------------------------------------

def test_ash_emissions_flag():
    assert classify_risk("Se observó emisión de ceniza.")["ash_emissions"] == 1
    assert classify_risk("Sin emisiones registradas.")["ash_emissions"] == 0


@pytest.mark.parametrize(
    "text",
    [
        "Presencia de gases volcánicos.",
        "Emisión de SO2 detectada.",
        # Accent required: the keyword is literally "dióxido de azufre".
        "Concentración de dióxido de azufre elevada.",
    ],
)
def test_gas_emissions_flag(text):
    assert classify_risk(text)["gas_emissions"] == 1


def test_gas_emissions_absent():
    assert classify_risk("Actividad sísmica leve.")["gas_emissions"] == 0


def test_incandescence_flag():
    assert classify_risk("Material incandescente en el cráter.")["incandescence"] == 1
    assert classify_risk("No se observó brillo nocturno.")["incandescence"] == 0


# ---------------------------------------------------------------------------
# 4. Lahar detection (positive + both negated branches)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text, expected",
    [
        # Positive report.
        ("Se reportaron lahares en el sector norte", 1),
        # Negation via "no se registraron ...".
        ("No se registraron lahares en las últimas 24 horas", 0),
        # Conditional/future phrasing via "podrían generar ..." (accent required).
        ("Podrían generar lahares en caso de lluvia", 0),
    ],
)
def test_lahar_detection(text, expected):
    assert classify_risk(text)["lahars_detected"] == expected


# ---------------------------------------------------------------------------
# 5. Explosions count
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text, expected",
    [
        # Accent required: the pattern is "explosió[nñ] ... (exp) ... <number>".
        ("Explosión (EXP) 12", 12),
        ("Explosión (EXP) | 3", 3),
        ("EXPLOSIÓN|(EXP)|45", 45),
    ],
)
def test_explosions_count_extracted(text, expected):
    assert classify_risk(text)["explosions_count"] == expected


def test_explosions_count_zero_when_absent():
    assert classify_risk("No se registró actividad sísmica relevante.")["explosions_count"] == 0


# ---------------------------------------------------------------------------
# 6. Maximum column height
# ---------------------------------------------------------------------------

def test_max_column_height_in_range():
    text = "Columna de emisión de 1500 metros sobre el cráter."
    assert classify_risk(text)["max_column_height_m"] == 1500


def test_max_column_height_ignores_value_without_unit():
    # A 4-digit year with no unit suffix must NOT be read as a column height:
    # the regex only accepts numbers followed by m / metros / m.s.n.c.
    text = "Boletín emitido en el año 2023 por el observatorio."
    assert classify_risk(text)["max_column_height_m"] == 0


def test_max_column_height_zero_when_absent():
    assert classify_risk("Sin columnas de emisión reportadas.")["max_column_height_m"] == 0
