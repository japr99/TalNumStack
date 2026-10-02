"""
Utilidades para el sistema de medidas de TalNumStack.
Permite trabajar con diferentes unidades en la UI manteniendo el formato interno en mm.
"""

from lang import t

# Unidades de medida
UNIT_MM = "mm"
UNIT_CM = "cm"
UNIT_INCHES = "pulgadas"
UNIT_PICAS = "picas"

# Factores de conversión (Todo a milímetros)
MM_PER_CM = 10.0
MM_PER_INCH = 25.4
MM_PER_PICA = 4.233  # 1 pica = 1/6 inch


def convert_to_mm(value, from_unit):
    """
    Convierte un valor de cualquier unidad a milímetros

    Args:
        value: Valor numérico a convertir
        from_unit: Unidad de origen (UNIT_MM, UNIT_CM, UNIT_INCHES, UNIT_PICAS)

    Returns:
        Valor convertido a milímetros (float)
    """
    try:
        val = float(value)
    except (ValueError, TypeError):
        return 0.0

    if from_unit == UNIT_MM:
        return val
    elif from_unit == UNIT_CM:
        return val * MM_PER_CM
    elif from_unit == UNIT_INCHES:
        return val * MM_PER_INCH
    elif from_unit == UNIT_PICAS:
        return val * MM_PER_PICA
    return val


def convert_from_mm(value_mm, to_unit):
    """
    Convierte un valor de milímetros a cualquier unidad

    Args:
        value_mm: Valor en milímetros
        to_unit: Unidad de destino (UNIT_MM, UNIT_CM, UNIT_INCHES, UNIT_PICAS)

    Returns:
        Valor convertido a la unidad especificada (float)
    """
    try:
        val_mm = float(value_mm)
    except (ValueError, TypeError):
        return 0.0

    if to_unit == UNIT_MM:
        return val_mm
    elif to_unit == UNIT_CM:
        return val_mm / MM_PER_CM
    elif to_unit == UNIT_INCHES:
        return val_mm / MM_PER_INCH
    elif to_unit == UNIT_PICAS:
        return val_mm / MM_PER_PICA
    return val_mm


def get_unit_label(unit, t_func=None):
    """
    Devuelve la etiqueta legible para una unidad.
    Se traduce automáticamente usando lang.t si no se proporciona t_func.
    """
    labels = {
        UNIT_MM: "mm",
        UNIT_CM: "cm",
        UNIT_INCHES: "pulgadas",
        UNIT_PICAS: "picas",
    }
    label = labels.get(unit, unit)

    # Si es mm o cm, no solemos traducirlos (aunque t() lo permitiría)
    if unit in [UNIT_MM, UNIT_CM]:
        return label

    func = t_func if t_func else t
    return func(label)


# Abreviaturas fijas para usar en etiquetas de campos (no se traducen,
# son estándares internacionales: mm, cm, in, pc).
_UNIT_ABBR = {
    UNIT_MM: "mm",
    UNIT_CM: "cm",
    UNIT_INCHES: "in",
    UNIT_PICAS: "pc",
}


def get_unit_abbr(unit):
    """
    Devuelve la abreviatura corta e invariable para una unidad.
    Usar en etiquetas de campos (label=) para evitar textos largos
    que se parten en dos líneas según el idioma.
      mm → mm  |  cm → cm  |  pulgadas → in  |  picas → pc
    """
    return _UNIT_ABBR.get(unit, unit or "mm")


def get_units_list():
    """Devuelve la lista de unidades disponibles."""
    return [UNIT_MM, UNIT_CM, UNIT_INCHES, UNIT_PICAS]
