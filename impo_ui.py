import json
from types import SimpleNamespace
import flet as ft
import copy
import os
import threading
import asyncio
import fitz  # PyMuPDF
import base64
import time
import builtins

# # Silenciar prints de depuración en este módulo por defecto.
# # Para activar, cambiar _PRINT_DEBUG = True durante desarrollo.
_PRINT_DEBUG = False
if not _PRINT_DEBUG:

    def _no_print(*args, **kwargs):
        return None

    print = _no_print

DEBUG_IMPO_UI = False

if not DEBUG_IMPO_UI:

    def _no_print(*args, **kwargs):
        return None

    print = _no_print

# Control específico para prints del STAMP tras recalcular imposición.
# Poner a True para habilitar prints detallados del stamp y añadir más prints
# relevantes dentro del bloque protegido.
DEBUG_STAMP = False

# Flag para silenciar los prints dentro de actualizar_checkboxes_desde_estado
# Poner a True para habilitar prints de diagnóstico de checkboxes
DEBUG_CHECKBOXES = False
# Nota: si necesita imprimir un STAMP completo para depuración, incluya
# un `if DEBUG_STAMP:` alrededor del `print(...)` en el punto de carga
# concreto. No imprimir automáticamente al importar el módulo.


from pdf_manipulator import contar_paginas_pdf, leer_cajas_por_pagina  # leer_cajas_pdf


from grafico import grafico_datos, generar_ordenamiento_pdf_montaje
from color_design import *

# Importar funciones para obtener PDF ordenado temporal
from pdf_ordenado_ui import (
    obtener_pdf_ordenado_temp,
    guardar_pdf_ordenado_temp,
    obtener_ruta_pdf_original,
    obtener_ordenamiento_calculado,
    # limpiar_pdf_ordenado_temp,  # eliminado porque ya no se usa
    # limpiar_ordenamiento_calculado,  # eliminado porque ya no se usa
    obtener_total_pliegos_indice,
    esta_pliego_cacheado,
    marcar_pliego_cacheado,
    obtener_paginas_del_pliego,
    extraer_imagenes_pliego,
    obtener_ruta_imagen,
    copiar_pdf_a_temporal,
)

from fritz_json_export import (
    generar_impo_export_data,
    guardar_impo_export_data,
    imprimir_impo_export_data,
)

# internacionalización
from lang import t


# Helper seguro para parsear floats desde cadenas (acepta coma o punto).
# Definido a nivel de módulo para que todas las funciones lo puedan usar.
def _safe_float_from_str(s):
    """Convierte una cadena numérica a float.
    - Acepta separador decimal coma o punto.
    - Devuelve None si la conversión falla o la entrada es None/vacía.
    """
    try:
        if s is None:
            return None
        s2 = str(s).strip()
        if s2 == "":
            return None
        s2 = s2.replace(",", ".")
        return float(s2)
    except Exception:
        return None


# Pending unit change (if preferences change before UI created)
_pending_unit_change = None


def update_units_in_impo(unit_code):
    """Global entrypoint other modules can call to request unit change in impo UI.
    If the in-function `update_units` exists it will be called immediately; otherwise
    the requested unit is stored and applied when the impo UI is created.
    """
    global _pending_unit_change
    try:
        fn = globals().get("update_units")
        if callable(fn):
            try:
                fn(unit_code)
                return True
            except Exception:
                pass
        # store for later
        _pending_unit_change = unit_code
        try:
            # also keep in state dict if available
            _estado_impo_ui["unit"] = unit_code
        except Exception:
            pass
        return False
    except Exception:
        _pending_unit_change = unit_code
        return False


# Utilities for unit conversion and preference
try:
    from utils.unit_utils import (
        convert_to_mm,
        convert_from_mm,
        get_unit_label,
        get_unit_abbr,
        get_units_list,
    )
except Exception:
    # provide minimal fallbacks to keep editor/static checks satisfied
    def convert_to_mm(value, from_unit):
        try:
            return float(value)
        except Exception:
            return 0.0

    def convert_from_mm(value_mm, to_unit):
        try:
            return float(value_mm)
        except Exception:
            return 0.0

    def get_unit_label(unit_code, t_func=None):
        return unit_code or "mm"

    def get_unit_abbr(unit):
        abbr = {"mm": "mm", "cm": "cm", "pulgadas": "in", "picas": "pc"}
        return abbr.get(unit, unit or "mm")


try:
    from talnum_preferences import get_preference

    _initial_unit_pref = get_preference("unit", "mm") or "mm"
    print(f"[INIT] 🔧 Unidad cargada desde preferencias: {_initial_unit_pref}")
except Exception:
    _initial_unit_pref = "mm"
    print("[INIT] 🔧 Usando unidad por defecto: mm")


# Variable global para guardar ruta del PDF ordenado cargado
_pdf_ordenado_actual = None

# Flag global para saber si el trabajo fue modificado (para el stamp y la UI)
TRABAJO_MODIFICADO_DEFAULT = False

from impo_stack import (
    actualizar_capa_cruces,
    actualizar_capa_trazado,
    actualizar_capa_fondo,
    actualizar_capa_marca_texto,
    crear_capa_marca_texto,
    centrar_grupo_trazado_en_pliego,
    crear_capa_cruces,
    crear_capa_marcas_corte_exteriores,
    crear_capa_marcas_medianales_internas,
    crear_capa_lineas_corte,
    crear_grupo_trazado_centrado,
    crear_trazado_con_rows_from_widgets,
    calcular_offsets_celdas,
)


def _es_dorso_val(v):
    try:
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            s = v.strip().lower()
            return s.startswith("d") or "dorso" in s
    except Exception:
        pass
    return False


def calcular_datos_medianales_para_json(
    longitud_cruz_mm,
    longitud_marcas_exteriores_mm,
    offset_cruz_mm,
    tamano_usuario_w,
    tamano_usuario_h,
    calles_h,
    calles_v,
    longitud_brazo_max_mm=None,
    offset_seguridad_mm=None,
):
    """
    Calcula los datos de marcas medianales para el JSON (sin UI).
    Replica la lógica de crear_capa_marcas_medianales_internas.
    """
    GROSOR_CRUZ_PT = 0.5
    PT_TO_MM = 25.4 / 72.0

    h_offsets_mm = []
    v_offsets_mm = []
    lineas_medianales = []

    if len(calles_h) == 0 or len(calles_v) == 0:
        return {}

    margen_inicial = longitud_marcas_exteriores_mm + offset_cruz_mm
    # Determinar longitud efectiva del brazo: usar el valor máximo proporcionado
    # por la UI (`longitud_brazo_max_mm`) si está definido; en caso contrario
    # usar la mitad de la longitud de la cruz (comportamiento histórico).
    if longitud_brazo_max_mm is not None:
        try:
            longitud_brazo_mm = min(
                float(longitud_brazo_max_mm), float(longitud_cruz_mm) / 2.0
            )
        except Exception:
            longitud_brazo_mm = float(longitud_cruz_mm) / 2.0
    else:
        longitud_brazo_mm = float(longitud_cruz_mm) / 2.0

    # Calcular Offsets
    h_offsets_mm.append(margen_inicial + tamano_usuario_h)
    v_offsets_mm.append(margen_inicial + tamano_usuario_w)

    for i in range(1, len(calles_h)):
        offset_anterior_h = h_offsets_mm[-1]
        calle_anterior_h = calles_h[i - 1]
        h_offsets_mm.append(offset_anterior_h + tamano_usuario_h + calle_anterior_h)

    for j in range(1, len(calles_v)):
        offset_anterior_v = v_offsets_mm[-1]
        calle_anterior_v = calles_v[j - 1]
        v_offsets_mm.append(offset_anterior_v + tamano_usuario_w + calle_anterior_v)

    # Generar Líneas
    for i, y_mm in enumerate(h_offsets_mm):
        calle_h_size = calles_h[i] if i < len(calles_h) else 0.0

        for j, x_mm in enumerate(v_offsets_mm):
            calle_v_size = calles_v[j] if j < len(calles_v) else 0.0

            longitud_h = (
                min(longitud_brazo_mm, calle_v_size / 2) if calle_v_size > 0 else 0
            )
            longitud_v = (
                min(longitud_brazo_mm, calle_h_size / 2) if calle_h_size > 0 else 0
            )

            if DEBUG_IMPO_UI:
                print(
                    f"[MARCA MED] H{i}∩V{j}: calle_v={calle_v_size:.1f}mm, calle_h={calle_h_size:.1f}mm → longitud_h={longitud_h:.1f}mm, longitud_v={longitud_v:.1f}mm"
                )

            if longitud_h <= 0 and longitud_v <= 0:
                continue

            center_x = calle_v_size / 2 if calle_v_size > 0 else 0
            center_y = calle_h_size / 2 if calle_h_size > 0 else 0

            cruz_x = x_mm + center_x
            cruz_y = y_mm + center_y

            interseccion_id = f"H{i}∩V{j}"

            if longitud_h > 0:
                # Brazo izquierdo
                lineas_medianales.append(
                    {
                        "tipo": "horizontal",
                        "brazo": "izquierdo",
                        "x_mm": cruz_x - longitud_h,
                        "y_mm": cruz_y,
                        "width_mm": longitud_h,
                        "height_mm": GROSOR_CRUZ_PT * PT_TO_MM,
                        "interseccion": interseccion_id,
                    }
                )
                # Brazo derecho
                lineas_medianales.append(
                    {
                        "tipo": "horizontal",
                        "brazo": "derecho",
                        "x_mm": cruz_x,  # empieza en el centro
                        "y_mm": cruz_y,
                        "width_mm": longitud_h,
                        "height_mm": GROSOR_CRUZ_PT * PT_TO_MM,
                        "interseccion": interseccion_id,
                    }
                )

            if longitud_v > 0:
                # Brazo arriba
                lineas_medianales.append(
                    {
                        "tipo": "vertical",
                        "brazo": "arriba",
                        "x_mm": cruz_x,
                        "y_mm": cruz_y - longitud_v,
                        "width_mm": GROSOR_CRUZ_PT * PT_TO_MM,
                        "height_mm": longitud_v,
                        "interseccion": interseccion_id,
                    }
                )
                # Brazo abajo
                lineas_medianales.append(
                    {
                        "tipo": "vertical",
                        "brazo": "abajo",
                        "x_mm": cruz_x,
                        "y_mm": cruz_y,  # empieza en el centro
                        "width_mm": GROSOR_CRUZ_PT * PT_TO_MM,
                        "height_mm": longitud_v,
                        "interseccion": interseccion_id,
                    }
                )

    return {
        "h_offsets_mm": h_offsets_mm,
        "v_offsets_mm": v_offsets_mm,
        "calles_h": calles_h,
        "calles_v": calles_v,
        "offset_seguridad_mm": (
            offset_seguridad_mm if offset_seguridad_mm is not None else 1.0
        ),
        "longitud_brazo_max_mm": (
            longitud_brazo_max_mm if longitud_brazo_max_mm is not None else 5.0
        ),
        "num_cruces": len(lineas_medianales) // 4,  # Aprox
        "num_lineas": len(lineas_medianales),
        "lineas_medianales": lineas_medianales,
        "grosor_pt": GROSOR_CRUZ_PT,
        "grosor_mm": GROSOR_CRUZ_PT * PT_TO_MM,
    }


# Constantes de conversión
MM_TO_PT = 72.0 / 25.4
PT_TO_MM = 25.4 / 72.0

# Variable para controlar si estamos cargando datos (evitar recálculos)
_CARGANDO_DATOS = False

# Variables persistentes para el PDF cargado y ordenamiento
_archivo_seleccionado = {"ruta": "", "nombre": "", "paginas": 0}
_ordenamiento_calculado = {"ordenamiento": None, "paginas_requeridas": 0}
_pdf_ordenado_actual = None  # Ruta al PDF ordenado temporal

# ════════════════════════════════════════════════════════════════════════════════
# ESTADO COMPLETO DE LA UI DE IMPOSICIÓN (persistente entre sesiones)
# ════════════════════════════════════════════════════════════════════════════════
_estado_impo_ui = {
    # Indica si hay una imposición creada (True) o no (False)
    "impo_creada": False,
    # Boxes PDF (siempre presentes aunque sean None)
    "mediabox": None,
    "cropbox": None,
    "bleedbox": None,
    # Datos de cálculo (fase1/2/3) - para detectar cambios
    "cantidad": "",
    "can_hojas_tal": "",
    "hojas_x_pliego": "",
    "comienzo_numeracion": "",
    "horizontal": "",
    "vertical": "",
    "orientacion": "Izquierda",
    # PDF y ordenamiento
    "pdf_stamp": None,
    "pdf_ruta": "",
    "pdf_nombre": "",
    "pdf_paginas": 0,
    "ordenamiento_paginas_requeridas": 0,
    # Grid y calles
    "grid_cols": 1,
    "grid_rows": 1,
    "calles_list": [],
    # Tamaños
    "tamano_usuario_w": 0.0,
    "tamano_usuario_h": 0.0,
    "sangre": 0.0,
    "pliego_ancho": None,
    "pliego_alto": None,
    "pliego_congelado": False,
    # Offsets
    "offset_img_x": 0.0,
    "offset_img_y": 0.0,
    "offset_trazado_x": 0.0,
    "offset_trazado_y": 0.0,
    # Dropdowns
    "dropdown_copias": "1",
    "dropdown_doble_cara": "cara",
    "dropdown_rotacion": "0°",
    "dropdown_tipo_corte": None,
    # Checkboxes
    "checkbox_cruces": False,
    "checkbox_lineas_corte": False,
    "checkbox_marcas_texto": False,
    "checkbox_linea_exterior": True,
    "checkbox_xerox": False,
    # Estado de navegación de pliegos
    "pliego_index": 0,
    "pliego_actual_texto": "1",
    "total_pliegos": 0,
    # Zoom
    "zoom_level": 0.96,
    "auto_zoom": True,
    # Marcas de texto (configuración completa)
    "marca_texto_contenido": "NumStack - Imposición",
    "marca_texto_pos_sup_izq": True,
    "marca_texto_pos_sup_der": False,
    "marca_texto_pos_inf_izq": False,
    "marca_texto_pos_inf_der": False,
    "marca_texto_pos_centro_sup": False,
    "marca_texto_pos_centro_inf": False,
    "marca_texto_pos_centro_lat_izq": False,
    "marca_texto_pos_centro_lat_der": False,
    "marca_texto_rotacion": 0,
    "marca_texto_familia": "Arial",
    "marca_texto_tipo": "Regular",
    "marca_texto_cuerpo": 10,
    "marca_texto_color": "#000000",
    "marca_texto_offset_h_mm": 0.0,
    "marca_texto_offset_v_mm": 0.0,
    # Configuración de cruces
    "longitud_cruz_mm": 10.0,
    "grosor_cruz_pt": 0.5,
    "offset_cruz_mm": 5.0,
    "auto_sangre_offset_cruz": False,
    "offset_seguridad_mm": 1.0,
    "longitud_brazo_max_mm": 5.0,
    # Estado de UI/controles
    "controles_visibles": False,
    "boton_crear_disabled": True,
    "navegacion_visible": False,
    # Timestamp de última modificación
    "ultima_modificacion": None,
}

TAMANO_USUARIO_W = 210  # mm
TAMANO_USUARIO_H = 297  # mm

SANGRE = 0  # mm

GRID_COLS = 1
GRID_ROWS = 1


def limpiar_estado_imposicion():
    global _estado_impo_ui, _archivo_seleccionado, _pdf_ordenado_actual, _ordenamiento_calculado, _pdf_stamp, _PDF_VALIDATED
    # Preservar 'ultima_modificacion' si existe
    ultima_modificacion_actual = _estado_impo_ui.get("ultima_modificacion", None)
    # Preservar claves de preferencias de aplicación para evitar que
    # la limpieza borre valores visuales/control usados por la UI.
    # Estas claves provienen de las preferencias de la aplicación
    # y no forman parte del estado de un trabajo.
    pref_keys = ["unit", "language", "theme", "tema", "theme_mode", "tema_flet"]
    preserved_prefs = {
        k: _estado_impo_ui.get(k) for k in pref_keys if k in _estado_impo_ui
    }
    _estado_impo_ui = {
        # Boxes PDF (siempre presentes aunque sean None)
        "mediabox": None,
        "cropbox": None,
        "bleedbox": None,
        "cantidad": "",
        "can_hojas_tal": "",
        "hojas_x_pliego": "",
        "comienzo_numeracion": "",
        "horizontal": "",
        "vertical": "",
        "orientacion": "Izquierda",
        "pdf_stamp": None,
        "pdf_ruta": "",
        "pdf_nombre": "",
        "pdf_paginas": 0,
        "ordenamiento_paginas_requeridas": 0,
        "grid_cols": 1,
        "grid_rows": 1,
        "calles_list": [],
        "tamano_usuario_w": 0.0,
        "tamano_usuario_h": 0.0,
        "sangre": 0.0,
        "pliego_ancho": None,
        "pliego_alto": None,
        "pliego_congelado": False,
        "offset_img_x": 0.0,
        "offset_img_y": 0.0,
        "offset_trazado_x": 0.0,
        "offset_trazado_y": 0.0,
        "dropdown_copias": "1",
        "dropdown_doble_cara": "cara",
        "dropdown_rotacion": "0°",
        "dropdown_tipo_corte": None,
        "checkbox_cruces": False,
        "checkbox_lineas_corte": False,
        "checkbox_marcas_texto": False,
        "checkbox_linea_exterior": True,
        "checkbox_xerox": False,
        "pliego_index": 0,
        "pliego_actual_texto": "1",
        "total_pliegos": 0,
        "zoom_level": 0.96,
        "auto_zoom": True,
        "marca_texto_contenido": "NumStack - Imposición",
        "marca_texto_pos_sup_izq": True,
        "marca_texto_pos_sup_der": False,
        "marca_texto_pos_inf_izq": False,
        "marca_texto_pos_inf_der": False,
        "marca_texto_pos_centro_sup": False,
        "marca_texto_pos_centro_inf": False,
        "marca_texto_pos_centro_lat_izq": False,
        "marca_texto_pos_centro_lat_der": False,
        "marca_texto_rotacion": 0,
        "marca_texto_familia": "Arial",
        "marca_texto_tipo": "Regular",
        "marca_texto_cuerpo": 10,
        "marca_texto_color": "#000000",
        "marca_texto_offset_h_mm": 0.0,
        "marca_texto_offset_v_mm": 0.0,
        "longitud_cruz_mm": 10.0,
        "grosor_cruz_pt": 0.5,
        "offset_cruz_mm": 5.0,
        "auto_sangre_offset_cruz": False,
        "offset_seguridad_mm": 1.0,
        "longitud_brazo_max_mm": 5.0,
        "controles_visibles": False,
        "boton_crear_disabled": True,
        "navegacion_visible": False,
        "ultima_modificacion": ultima_modificacion_actual,
        "trabajo_modificado": TRABAJO_MODIFICADO_DEFAULT,
    }
    # Reaplicar las preferencias preservadas (si existían)
    try:
        if preserved_prefs:
            _estado_impo_ui.update(preserved_prefs)
    except Exception:
        pass
    # Limpiar archivo seleccionado y PDF actual
    _archivo_seleccionado = {"ruta": "", "nombre": "", "paginas": 0}
    _pdf_ordenado_actual = None

    # Asegurar limpieza de globals relacionados con el PDF/stamp/ordenamiento
    try:
        _pdf_stamp = None
    except Exception:
        pass

    try:
        _PDF_VALIDATED = False
    except Exception:
        pass

    try:
        if isinstance(_ordenamiento_calculado, dict):
            _ordenamiento_calculado.clear()
            _ordenamiento_calculado.update(
                {"ordenamiento": None, "paginas_requeridas": 0}
            )
    except Exception:
        pass

    # Intentar limpiar la sesión temporal de pdf_ordenado_ui para eliminar caches en disco
    try:
        from pdf_ordenado_ui import limpiar_temp_sesion

        limpiar_temp_sesion()
    except Exception:
        pass

    # Asegurar que las globals que usan el trazado reflejen el estado limpio
    try:
        TAMANO_USUARIO_W = _estado_impo_ui.get("tamano_usuario_w", 210.0)
        TAMANO_USUARIO_H = _estado_impo_ui.get("tamano_usuario_h", 100.0)
        SANGRE = _estado_impo_ui.get("sangre", 0.0)
    except Exception:
        try:
            TAMANO_USUARIO_W = 210.0
            TAMANO_USUARIO_H = 100.0
            SANGRE = 0.0
        except Exception:
            pass

    # Actualizar textfields visibles si existen
    try:
        tf_sangre = globals().get("textfield_sangre")
        if tf_sangre:
            try:
                tf_sangre.value = f"{SANGRE:.2f}"
                try:
                    tf_sangre.update()
                except Exception:
                    pass
            except Exception:
                pass
    except Exception:
        pass

    try:
        tf_tam_w = globals().get("textfield_tamano_usuario_w")
        if tf_tam_w:
            try:
                tf_tam_w.value = f"{TAMANO_USUARIO_W:.2f}"
                try:
                    tf_tam_w.update()
                except Exception:
                    pass
            except Exception:
                pass
    except Exception:
        pass

    try:
        tf_tam_h = globals().get("textfield_tamano_usuario_h")
        if tf_tam_h:
            try:
                tf_tam_h.value = f"{TAMANO_USUARIO_H:.2f}"
                try:
                    tf_tam_h.update()
                except Exception:
                    pass
            except Exception:
                pass
    except Exception:
        pass


# Generar `CALLES_L` (lista de calles usada en tiempo de ejecución) automáticamente según el grid:
n_h = max(0, GRID_ROWS - 1)
n_v = max(0, GRID_COLS - 1)
CALLES_L = []  # Valor inicial: vacío, la auto-generación llenará con 0s por defecto

# Escala de visualización
ESCALA_VISUAL = 1  # píxeles por mm
# Zoom compartido
zoom_level = {"value": 0.96}
ZOOM_LEVEL_INICIAL = zoom_level["value"]

# Zoom final calculado
zoom_final = {"value": 1}

AUTO_ZOOM = True

# Velocidad del arrastre con raton: speed = zoom * PAN_MULTIPLICADOR.
# 1.0 = el contenido va pegado al raton (1:1 en pantalla, igual que PageNumber).
# Subir a 1.5/2.0 si se quiere recorrer el pliego con menos arrastre.
# 26-sep-2026: usuario lo quiere mas rapido -> 3.0 (a zoom alto el contenido
# se adelanta al cursor; si resbala, usar PAN_VELOCIDAD_MAX).
PAN_MULTIPLICADOR = 3.0

# Offsets globales de la imagen del pdf aplicados por el usuario (mm)
USER_OFFSET_IMAGEN_X_MM = 0.0
USER_OFFSET_IMAGEN_Y_MM = 0.0

# Variable global que representa el tamaño del pliego final activo (mm)
TAMANO_TRAZADO = {"w_mm": None, "h_mm": None}
TAMANO_TRAZADO_CRUCES = {"w_mm": None, "h_mm": None}
TAMANO_FINAL_PLIEGO = {"w_mm": None, "h_mm": None}

# Últimos tamaños calculados por `actualizar_trazado` - usados para recalcular zoom sin rehacer todo
LAST_GRUPO_W_MM = None
LAST_GRUPO_H_MM = None
LAST_TAMANO_TOTAL_W_MM = None
LAST_TAMANO_TOTAL_H_MM = None

# Offsets globales del trazado aplicados por el usuario (mm)
USER_OFFSET_TRAZADO_X_MM = 0.0
USER_OFFSET_TRAZADO_Y_MM = 0.0

# Bandera para suspender temporalmente la marcación de 'modificado'
# Usada durante operaciones de carga/limpieza para evitar que handlers
# de `on_change` marquen el proyecto como modificado mientras aplicamos
# valores programáticamente.
_SUSPEND_MARK_MODIFIED = False

# Flag para indicar si TAMANO_FINAL_PLIEGO fue congelado manualmente por el usuario
PLIEGO_CONGELADO = False

# Parámetros de cruces y marcas
LONGITUD_CRUZ_MM = 10.0
GROSOR_CRUZ_PT = 0.5
OFFSET_CRUZ_MM = 5.0
AUTO_SANGRE_OFFSET_CRUZ = False  # Si True, usar sangre como offset de cruces
OFFSET_CRUZ_PREF = 0.0

# ✨ NUEVOS: Parámetros para marcas medianales internas
OFFSET_SEGURIDAD_MM = 1.0  # Margen de seguridad adicional cuando sangre = 0
LONGITUD_BRAZO_MAX_MM = 5.0  # Longitud total de cada línea de cruz medianal (usuario especifica total, se usa la mitad para cada brazo desde el centro)

# Parámetros de marcas de texto (ejecución)
MARCA_TEXTO_CONTENIDO = "NumStack - Imposición"
MARCA_TEXTO_POS_SUP_IZQ = True
MARCA_TEXTO_POS_SUP_DER = False
MARCA_TEXTO_POS_INF_IZQ = False
MARCA_TEXTO_POS_INF_DER = False
MARCA_TEXTO_POS_CENTRO_SUP = False
MARCA_TEXTO_POS_CENTRO_INF = False
MARCA_TEXTO_POS_CENTRO_LAT_IZQ = False
MARCA_TEXTO_POS_CENTRO_LAT_DER = False
MARCA_TEXTO_ROTACION = 0
MARCA_TEXTO_FAMILIA = "Arial"
MARCA_TEXTO_TIPO = "Regular"
MARCA_TEXTO_CUERPO = 12
MARCA_TEXTO_COLOR = ft.Colors.BLACK
MARCA_TEXTO_OFFSET_H_MM = 0.0
MARCA_TEXTO_OFFSET_V_MM = 0.0

# Checkboxes de opciones de imposición
checkbox_cruces: ft.Checkbox | None = None
checkbox_lineas_corte: ft.Checkbox | None = None
checkbox_marcas_texto: ft.Checkbox | None = None
checkbox_linea_exterior: ft.Checkbox | None = None

# Botón de tamaño auto/manual de pliego
boton_auto_manual_pliego: ft.Button | None = None

# Referencia a función mark_modified (se asigna desde crear_ventana_ordenar_imposicion)
_mark_modified_callback = None

# Bandera que indica que el PDF (temporal/ordenado) ha sido validado
# Sólo cuando esta bandera es True se permite que `guardar_estado_impo_ui`
# actualice los campos relacionados con el PDF (pdf_stamp, pdf_ruta, pdf_nombre, pdf_paginas, boxes).
_PDF_VALIDATED = False

# ════════════════════════════════════════════════════════════════════════════════
# FUNCIONES DE PERSISTENCIA DE ESTADO
# ════════════════════════════════════════════════════════════════════════════════
# Variables globales para PREFERENCIAS de exportación (se restauran con el estado)
_PREF_COPIAS = "1"
_PREF_XEROX = False
_PREF_NOMBRE_PERSONALIZADO = False
_PREF_FILENAME = "imposicion_output.pdf"


def guardar_estado_impo_ui():
    """
    Captura TODO el estado actual de la UI de imposición y lo guarda en _estado_impo_ui.
    Esto incluye: PDF, grid, tamaños, offsets, dropdowns, checkboxes, zoom, marcas, etc.
    """
    import time

    global _estado_impo_ui, _archivo_seleccionado, _ordenamiento_calculado, _pdf_ordenado_actual
    global GRID_COLS, GRID_ROWS, CALLES_L
    global TAMANO_USUARIO_W, TAMANO_USUARIO_H, SANGRE
    global TAMANO_FINAL_PLIEGO, PLIEGO_CONGELADO
    global USER_OFFSET_IMAGEN_X_MM, USER_OFFSET_IMAGEN_Y_MM
    global USER_OFFSET_TRAZADO_X_MM, USER_OFFSET_TRAZADO_Y_MM
    global zoom_level, AUTO_ZOOM
    global MARCA_TEXTO_CONTENIDO, MARCA_TEXTO_POS_SUP_IZQ, MARCA_TEXTO_POS_SUP_DER
    # Globales de prefs de exportación
    global _PREF_COPIAS, _PREF_XEROX, _PREF_NOMBRE_PERSONALIZADO, _PREF_FILENAME
    global MARCA_TEXTO_POS_INF_IZQ, MARCA_TEXTO_POS_INF_DER
    global MARCA_TEXTO_POS_CENTRO_SUP, MARCA_TEXTO_POS_CENTRO_INF
    global MARCA_TEXTO_POS_CENTRO_LAT_IZQ, MARCA_TEXTO_POS_CENTRO_LAT_DER
    global MARCA_TEXTO_ROTACION, MARCA_TEXTO_FAMILIA, MARCA_TEXTO_TIPO
    global MARCA_TEXTO_CUERPO, MARCA_TEXTO_COLOR
    global MARCA_TEXTO_OFFSET_H_MM, MARCA_TEXTO_OFFSET_V_MM
    global LONGITUD_CRUZ_MM, GROSOR_CRUZ_PT, OFFSET_CRUZ_MM
    global AUTO_SANGRE_OFFSET_CRUZ, OFFSET_SEGURIDAD_MM, LONGITUD_BRAZO_MAX_MM
    global checkbox_cruces, checkbox_lineas_corte, checkbox_marcas_texto, checkbox_linea_exterior
    global dropdown_doble_cara  # ✅ Included global access

    # Globales de preferencias de exportación (last used)
    global _PREF_COPIAS, _PREF_XEROX, _PREF_NOMBRE_PERSONALIZADO, _PREF_FILENAME

    # Protección: evitar persistir un estado incompleto antes de que la UI esté lista.
    # Condiciones para permitir guardar:
    # - Existe el dict global `_estado_impo_ui` y contiene al menos las claves mínimas esperadas,
    # - O bien `_PDF_VALIDATED` es True (hay metadata PDF válida),
    # - En caso contrario, salir sin persistir.
    try:
        if not isinstance(globals().get("_estado_impo_ui", None), dict):
            # Nada que guardar aún
            return
        # Heurística: si el estado solo tiene defaults vacíos y no hay PDF validado, evitar sobrescribir
        estado_tmp = globals().get("_estado_impo_ui") or {}
        minimal_keys = [
            "pdf_nombre",
            "tamano_usuario_w",
            "tamano_usuario_h",
            "dropdown_doble_cara",
        ]
        has_meaningful = any(
            estado_tmp.get(k) not in (None, "", 0, 0.0) for k in minimal_keys
        )
        if not has_meaningful and not globals().get("_PDF_VALIDATED", False):
            # Evitar persistir un estado vacío o por defecto
            return

    except Exception:
        # Si falla la comprobación, continuar con la rutina normal (defensivo)
        pass

    try:
        # Generar stamp del PDF si existe
        pdf_stamp = None
        if _pdf_ordenado_actual and os.path.exists(_pdf_ordenado_actual):
            try:
                stat = os.stat(_pdf_ordenado_actual)
                pdf_stamp = f"{stat.st_size}_{stat.st_mtime}"
            except:
                pass

        # Capturar estado completo
        # NOTA: NO guardar rutas temporales (pdf_ruta, pdf_ordenado_ruta)
        # Solo metadata persistible (nombre_archivo, páginas, ruta_original)
        # Normalizar nombre del PDF a persistir (eliminar sufijos temporales y extensión)
        _nombre_persistible = _archivo_seleccionado.get(
            "nombre_archivo", _archivo_seleccionado.get("nombre", "")
        )
        try:
            # Eliminar extensión .pdf primero
            if _nombre_persistible.lower().endswith(".pdf"):
                _nombre_persistible = _nombre_persistible[:-4]
            # Eliminar sufijos temporales
            if _nombre_persistible.endswith("_ordenado_temp"):
                _nombre_persistible = _nombre_persistible[: -len("_ordenado_temp")]
            elif _nombre_persistible.endswith("_temp"):
                _nombre_persistible = _nombre_persistible[: -len("_temp")]
            elif _nombre_persistible.endswith("_ordenado"):
                _nombre_persistible = _nombre_persistible[: -len("_ordenado")]
            # Volver a añadir .pdf para el campo nombre_archivo
            _nombre_persistible = _nombre_persistible + ".pdf"
        except Exception:
            pass

        # Construir metadata del archivo seleccionad0 para persistir dentro del estado
        archivo_sel_for_estado = {
            "nombre_archivo": _nombre_persistible,
            "ruta_original": _archivo_seleccionado.get("ruta_original", ""),
            "num_paginas": _archivo_seleccionado.get(
                "paginas", _archivo_seleccionado.get("num_paginas", 0)
            ),
        }
        # Incluir boxes (MediaBox/TrimBox/BleedBox) si están disponibles (serializables a JSON)
        try:
            boxes = _archivo_seleccionado.get("boxes_by_page")
            if boxes and isinstance(boxes, dict) and 0 in boxes:
                p0 = boxes[0]

                def _box_to_list(b):
                    if not b:
                        return None
                    return [float(x) for x in b]

                archivo_sel_for_estado["mediabox"] = _box_to_list(p0.get("mediabox"))
                archivo_sel_for_estado["trimbox"] = _box_to_list(p0.get("trimbox"))
                archivo_sel_for_estado["bleedbox"] = _box_to_list(p0.get("bleedbox"))
            else:
                archivo_sel_for_estado["mediabox"] = None
                archivo_sel_for_estado["trimbox"] = None
                archivo_sel_for_estado["bleedbox"] = None
        except Exception:
            archivo_sel_for_estado["mediabox"] = None
            archivo_sel_for_estado["trimbox"] = None
            archivo_sel_for_estado["bleedbox"] = None

        # Actualizar el estado no-PDF primero
        _estado_impo_ui.update(
            {
                "ordenamiento": _ordenamiento_calculado.get("ordenamiento"),
                "ordenamiento_paginas_requeridas": _ordenamiento_calculado.get(
                    "paginas_requeridas", 0
                ),
                # Grid y calles
                "grid_cols": GRID_COLS,
                "grid_rows": GRID_ROWS,
                "calles_list": list(CALLES_L) if CALLES_L else [],
                # Tamaños
                "tamano_usuario_w": TAMANO_USUARIO_W,
                "tamano_usuario_h": TAMANO_USUARIO_H,
                "sangre": SANGRE,
                "pliego_ancho": TAMANO_FINAL_PLIEGO.get("w_mm"),
                "pliego_alto": TAMANO_FINAL_PLIEGO.get("h_mm"),
                "pliego_congelado": PLIEGO_CONGELADO,
                # Offsets
                "offset_img_x": USER_OFFSET_IMAGEN_X_MM,
                "offset_img_y": USER_OFFSET_IMAGEN_Y_MM,
                "offset_trazado_x": USER_OFFSET_TRAZADO_X_MM,
                "offset_trazado_y": USER_OFFSET_TRAZADO_Y_MM,
                # Preferencias de Exportación PDF (last used)
                "export_copies": globals().get("_PREF_COPIAS", "1"),
                "export_xerox": globals().get("_PREF_XEROX", False),
                "export_custom_name": globals().get(
                    "_PREF_NOMBRE_PERSONALIZADO", False
                ),
                "export_filename": globals().get(
                    "_PREF_FILENAME", "imposicion_output.pdf"
                ),
                # Dropdowns persistentes
                "dropdown_doble_cara": (
                    dropdown_doble_cara.value if dropdown_doble_cara else "cara"
                ),
                # Zoom
                "zoom_level": zoom_level.get("value", 0.96),
                "auto_zoom": AUTO_ZOOM,
                # Marcas de texto
                "marca_texto_contenido": MARCA_TEXTO_CONTENIDO,
                "marca_texto_pos_sup_izq": MARCA_TEXTO_POS_SUP_IZQ,
                "marca_texto_pos_sup_der": MARCA_TEXTO_POS_SUP_DER,
                "marca_texto_pos_inf_izq": MARCA_TEXTO_POS_INF_IZQ,
                "marca_texto_pos_inf_der": MARCA_TEXTO_POS_INF_DER,
                "marca_texto_pos_centro_sup": MARCA_TEXTO_POS_CENTRO_SUP,
                "marca_texto_pos_centro_inf": MARCA_TEXTO_POS_CENTRO_INF,
                "marca_texto_pos_centro_lat_izq": MARCA_TEXTO_POS_CENTRO_LAT_IZQ,
                "marca_texto_pos_centro_lat_der": MARCA_TEXTO_POS_CENTRO_LAT_DER,
                "marca_texto_rotacion": MARCA_TEXTO_ROTACION,
                "marca_texto_familia": MARCA_TEXTO_FAMILIA,
                "marca_texto_tipo": MARCA_TEXTO_TIPO,
                "marca_texto_cuerpo": MARCA_TEXTO_CUERPO,
                "marca_texto_color": (
                    str(MARCA_TEXTO_COLOR) if MARCA_TEXTO_COLOR else "#000000"
                ),
                "marca_texto_offset_h_mm": MARCA_TEXTO_OFFSET_H_MM,
                "marca_texto_offset_v_mm": MARCA_TEXTO_OFFSET_V_MM,
                # Configuración de cruces
                "longitud_cruz_mm": LONGITUD_CRUZ_MM,
                "grosor_cruz_pt": GROSOR_CRUZ_PT,
                "offset_cruz_mm": OFFSET_CRUZ_MM,
                "auto_sangre_offset_cruz": AUTO_SANGRE_OFFSET_CRUZ,
                "offset_seguridad_mm": OFFSET_SEGURIDAD_MM,
                "longitud_brazo_max_mm": LONGITUD_BRAZO_MAX_MM,
                # Boxes principales para el stamp limpio (valores por defecto por ahora)
                "mediabox": None,
                "cropbox": None,
                "bleedbox": None,
            }
        )

        # Sólo persistir metadata del PDF (nombre, ruta, páginas, boxes, stamp)
        # si el PDF ha sido validado explícitamente por el flujo de carga/validación.
        try:
            if globals().get("_PDF_VALIDATED", False):
                _estado_impo_ui.update(
                    {
                        "pdf_stamp": pdf_stamp,
                        "pdf_nombre_archivo": _nombre_persistible,
                        "pdf_paginas": _archivo_seleccionado.get(
                            "paginas", _archivo_seleccionado.get("num_paginas", 0)
                        ),
                        "pdf_ruta_original": _archivo_seleccionado.get(
                            "ruta_original", ""
                        ),
                        "archivo_seleccionado": archivo_sel_for_estado,
                        "mediabox": archivo_sel_for_estado.get("mediabox"),
                        "cropbox": archivo_sel_for_estado.get("trimbox")
                        or archivo_sel_for_estado.get("cropbox"),
                        "bleedbox": archivo_sel_for_estado.get("bleedbox"),
                    }
                )
        except Exception:
            pass

        # Asegurar que los campos críticos provenientes de la UI de `app.py`
        # estén presentes en el stamp persistido (aunque sean vacíos).
        # Estos campos suelen actualizarse desde `app.print_and_save_stamp()`
        # pero aquí garantizamos su existencia para persistencia consistente.
        try:
            for _k in (
                "cantidad",
                "can_hojas_tal",
                "hojas_x_pliego",
                "comienzo_numeracion",
                "horizontal",
                "vertical",
                "orientacion",
            ):
                _estado_impo_ui.setdefault(_k, "")
        except Exception:
            pass

        # Timestamp - solo actualizar si no había timestamp previo (nuevo estado)
        # Si ya había timestamp, mantenerlo para evitar falsos positivos de "modificado"
        if (
            "ultima_modificacion" not in _estado_impo_ui
            or _estado_impo_ui["ultima_modificacion"] is None
        ):
            _estado_impo_ui["ultima_modificacion"] = time.time()

        # Capturar valores de checkboxes con claves del archivo .tns (consistente con generar_imposicion)
        if checkbox_cruces is not None:
            _estado_impo_ui["CHECK_BOX_CRUCES_Y_MARCAS"] = checkbox_cruces.value
        if checkbox_lineas_corte is not None:
            _estado_impo_ui["CHECK_BOX_LINEAS_DE_CORTE"] = checkbox_lineas_corte.value
        if checkbox_marcas_texto is not None:
            _estado_impo_ui["CHECK_BOX_MARCAS_DE_TEXTO"] = checkbox_marcas_texto.value
        if checkbox_linea_exterior is not None:
            _estado_impo_ui["CHECK_BOX_LINEA_EXTERIOR"] = checkbox_linea_exterior.value

        # Trace: mostrar exactamente qué claves relacionadas con checkboxes se escribieron
        try:
            print(
                f"[TRACE WRITE] checkboxes guardadas: CRUCES={_estado_impo_ui.get('CHECK_BOX_CRUCES_Y_MARCAS')} | LINEAS={_estado_impo_ui.get('CHECK_BOX_LINEAS_DE_CORTE')} | MARCAS={_estado_impo_ui.get('CHECK_BOX_MARCAS_DE_TEXTO')} | EXTERIOR={_estado_impo_ui.get('CHECK_BOX_LINEA_EXTERIOR')}"
            )
            # También mostrar variantes en minúsculas que usamos para merge/compatibilidad
            print(
                f"[TRACE WRITE] variantes lowercase: checkbox_cruces={_estado_impo_ui.get('checkbox_cruces')} | checkbox_lineas_corte={_estado_impo_ui.get('checkbox_lineas_corte')} | checkbox_marcas_texto={_estado_impo_ui.get('checkbox_marcas_texto')} | checkbox_linea_exterior={_estado_impo_ui.get('checkbox_linea_exterior')}"
            )
        except Exception:
            pass
        # Sincronizar variantes lowercase para evitar claves inconsistentes
        try:
            _estado_impo_ui["checkbox_cruces"] = bool(
                _estado_impo_ui.get(
                    "CHECK_BOX_CRUCES_Y_MARCAS",
                    _estado_impo_ui.get("checkbox_cruces", False),
                )
            )
            _estado_impo_ui["checkbox_lineas_corte"] = bool(
                _estado_impo_ui.get(
                    "CHECK_BOX_LINEAS_DE_CORTE",
                    _estado_impo_ui.get("checkbox_lineas_corte", False),
                )
            )
            _estado_impo_ui["checkbox_marcas_texto"] = bool(
                _estado_impo_ui.get(
                    "CHECK_BOX_MARCAS_DE_TEXTO",
                    _estado_impo_ui.get("checkbox_marcas_texto", False),
                )
            )
            _estado_impo_ui["checkbox_linea_exterior"] = bool(
                _estado_impo_ui.get(
                    "CHECK_BOX_LINEA_EXTERIOR",
                    _estado_impo_ui.get("checkbox_linea_exterior", True),
                )
            )
            print(
                f"[SYNC WRITE] lowercase sincronizadas: checkbox_cruces={_estado_impo_ui['checkbox_cruces']} | checkbox_linea_exterior={_estado_impo_ui['checkbox_linea_exterior']}"
            )
        except Exception:
            pass
        # Asegurar consistencia: escribir también las claves MAYÚSCULAS espejo desde las lowercase canónicas
        try:
            _estado_impo_ui["CHECK_BOX_CRUCES_Y_MARCAS"] = bool(
                _estado_impo_ui.get("checkbox_cruces", False)
            )
            _estado_impo_ui["CHECK_BOX_LINEAS_DE_CORTE"] = bool(
                _estado_impo_ui.get("checkbox_lineas_corte", False)
            )
            _estado_impo_ui["CHECK_BOX_MARCAS_DE_TEXTO"] = bool(
                _estado_impo_ui.get("checkbox_marcas_texto", False)
            )
            _estado_impo_ui["CHECK_BOX_LINEA_EXTERIOR"] = bool(
                _estado_impo_ui.get("checkbox_linea_exterior", True)
            )
            print(
                f"[SYNC WRITE] uppercase sincronizadas desde lowercase: CHECK_BOX_LINEA_EXTERIOR={_estado_impo_ui['CHECK_BOX_LINEA_EXTERIOR']}"
            )
        except Exception:
            pass
        try:
            # También sincronizar variantes legacy MAYÚSCULAS para evitar inconsistencias
            legacy_map = {
                "CHECK_BOX_CRUCES": _estado_impo_ui.get("checkbox_cruces", False),
                "CHECK_BOX_CRUCES_Y_MARCAS": _estado_impo_ui.get(
                    "checkbox_cruces", False
                ),
                "CHECK_BOX_LINEAS_CORTE": _estado_impo_ui.get(
                    "checkbox_lineas_corte", False
                ),
                "CHECK_BOX_LINEAS_DE_CORTE": _estado_impo_ui.get(
                    "checkbox_lineas_corte", False
                ),
                "CHECK_BOX_MARCAS_TEXTO": _estado_impo_ui.get(
                    "checkbox_marcas_texto", False
                ),
                "CHECK_BOX_MARCAS_DE_TEXTO": _estado_impo_ui.get(
                    "checkbox_marcas_texto", False
                ),
                "CHECK_BOX_LINEA_EXTERIOR": _estado_impo_ui.get(
                    "checkbox_linea_exterior", True
                ),
            }
            for k, v in legacy_map.items():
                _estado_impo_ui[k] = bool(v)
            print(
                f"[SYNC WRITE] legacy uppercase keys synced: { {k: _estado_impo_ui[k] for k in legacy_map} }"
            )
        except Exception:
            pass

        # CRÍTICO: Guardar dropdown_doble_cara si existe
        if dropdown_doble_cara is not None:
            _estado_impo_ui["dropdown_doble_cara"] = dropdown_doble_cara.value

        # Log simplificado - mostrar solo datos PERSISTIBLES (NO temporales)
        nombre_persistible = _archivo_seleccionado.get("nombre_archivo", "")
        ruta_original = _archivo_seleccionado.get("ruta_original", "")
        print(f"[GUARDAR ESTADO] ✅ Estado guardado")
        if nombre_persistible:
            print(f"[GUARDAR ESTADO]   PDF original: {nombre_persistible}")
        if ruta_original:
            print(f"[GUARDAR ESTADO]   Ruta original: {ruta_original}")
        print(
            f"[GUARDAR ESTADO]   Grid: {GRID_COLS}x{GRID_ROWS}, Tamaño: {TAMANO_USUARIO_W:.2f}x{TAMANO_USUARIO_H:.2f}mm"
        )
        print(
            f"[GUARDAR ESTADO] 🔍 STAMP COMPLETO dropdown_doble_cara: {_estado_impo_ui.get('dropdown_doble_cara', 'NO EXISTE')}"
        )
        # Notificar callback de sincronización (por ejemplo app.py) si existe
        try:
            import builtins

            cb = getattr(builtins, "_on_trabajo_modificado_change", None)
            print(
                f"[GUARDAR ESTADO] notificando callback trabajo_modificado={_estado_impo_ui.get('trabajo_modificado', None)} callback_exists={callable(cb)}"
            )
            if callable(cb):
                try:
                    cb()
                except Exception:
                    pass
        except Exception:
            pass

        # Además, si la UI de imposición está abierta, forzar su propia actualización
        try:
            upd = globals().get("_impo_update_project_state_ui", None)
            if callable(upd):
                try:
                    upd()
                except Exception:
                    pass
        except Exception:
            pass
        # Forzar update de la página de imposición si está expuesta globalmente
        try:
            import builtins

            p = getattr(builtins, "_impo_page", None)
            if p is not None:
                try:
                    p.update()
                except Exception:
                    pass
        except Exception:
            pass

        return True

    except Exception as ex:
        print(f"[GUARDAR ESTADO] ❌ Error guardando estado: {ex}")
        import traceback

        traceback.print_exc()
        return False


def restaurar_estado_impo_ui():
    """
    Restaura TODO el estado de la UI desde _estado_impo_ui a las variables globales.
    Debe llamarse ANTES de crear los controles de la UI.
    """
    global _archivo_seleccionado, _ordenamiento_calculado, _pdf_ordenado_actual
    global GRID_COLS, GRID_ROWS, CALLES_L
    global TAMANO_USUARIO_W, TAMANO_USUARIO_H, SANGRE
    global TAMANO_FINAL_PLIEGO, PLIEGO_CONGELADO
    global USER_OFFSET_IMAGEN_X_MM, USER_OFFSET_IMAGEN_Y_MM
    global USER_OFFSET_TRAZADO_X_MM, USER_OFFSET_TRAZADO_Y_MM
    global zoom_level, AUTO_ZOOM
    global MARCA_TEXTO_CONTENIDO, MARCA_TEXTO_POS_SUP_IZQ, MARCA_TEXTO_POS_SUP_DER
    global MARCA_TEXTO_POS_INF_IZQ, MARCA_TEXTO_POS_INF_DER
    global MARCA_TEXTO_POS_CENTRO_SUP, MARCA_TEXTO_POS_CENTRO_INF
    global MARCA_TEXTO_POS_CENTRO_LAT_IZQ, MARCA_TEXTO_POS_CENTRO_LAT_DER
    global MARCA_TEXTO_ROTACION, MARCA_TEXTO_FAMILIA, MARCA_TEXTO_TIPO
    global MARCA_TEXTO_CUERPO, MARCA_TEXTO_COLOR
    global MARCA_TEXTO_OFFSET_H_MM, MARCA_TEXTO_OFFSET_V_MM
    global LONGITUD_CRUZ_MM, GROSOR_CRUZ_PT, OFFSET_CRUZ_MM
    global AUTO_SANGRE_OFFSET_CRUZ, OFFSET_SEGURIDAD_MM, LONGITUD_BRAZO_MAX_MM
    global _PREF_COPIAS, _PREF_XEROX, _PREF_NOMBRE_PERSONALIZADO, _PREF_FILENAME

    try:
        if not _estado_impo_ui:
            pass  # Continue to init globals if not set

        estado = _estado_impo_ui if _estado_impo_ui else {}

        # Init prefs if not exist
        if "_PREF_COPIAS" not in globals():
            _PREF_COPIAS = "1"
        if "_PREF_XEROX" not in globals():
            _PREF_XEROX = False
        if "_PREF_NOMBRE_PERSONALIZADO" not in globals():
            _PREF_NOMBRE_PERSONALIZADO = False
        if "_PREF_FILENAME" not in globals():
            _PREF_FILENAME = "imposicion_output.pdf"

        # Recuperar preferencias de exportación
        if estado:
            _PREF_COPIAS = estado.get("export_copies", "1")
            _PREF_XEROX = estado.get("export_xerox", False)
            _PREF_NOMBRE_PERSONALIZADO = estado.get("export_custom_name", False)
            if _PREF_NOMBRE_PERSONALIZADO:
                _PREF_FILENAME = estado.get("export_filename", "imposicion_output.pdf")

        # Restaurar PDF y ordenamiento - NO restaurar rutas temporales
        _archivo_seleccionado["ruta"] = ""  # La ruta temporal se regenera
        # Preferir la estructura anidada 'archivo_seleccionado' si existe
        archivo_guardado = estado.get("archivo_seleccionado") if estado else None
        if archivo_guardado:
            _archivo_seleccionado["ruta_original"] = archivo_guardado.get(
                "ruta_original", estado.get("pdf_ruta_original", "")
            )
            _archivo_seleccionado["nombre"] = archivo_guardado.get(
                "nombre_archivo", estado.get("pdf_nombre_archivo", "")
            )
            _archivo_seleccionado["nombre_archivo"] = archivo_guardado.get(
                "nombre_archivo", estado.get("pdf_nombre_archivo", "")
            )
            _archivo_seleccionado["paginas"] = archivo_guardado.get(
                "num_paginas", estado.get("pdf_paginas", 0)
            )
            # Restaurar boxes mínima (page 0) si estaban guardadas
            try:
                mb = archivo_guardado.get("mediabox")
                tb = archivo_guardado.get("trimbox")
                bb = archivo_guardado.get("bleedbox")
                if mb or tb or bb:
                    _archivo_seleccionado["boxes_by_page"] = {
                        0: {"mediabox": mb, "trimbox": tb, "bleedbox": bb}
                    }
            except Exception:
                pass
        else:
            _archivo_seleccionado["ruta_original"] = estado.get("pdf_ruta_original", "")
            _archivo_seleccionado["nombre"] = estado.get("pdf_nombre_archivo", "")
            _archivo_seleccionado["nombre_archivo"] = estado.get(
                "pdf_nombre_archivo", ""
            )
            _archivo_seleccionado["paginas"] = estado.get("pdf_paginas", 0)
        _pdf_ordenado_actual = None  # No restaurar ruta temporal
        # NOTA: ordenamiento_calculado NO se restaura - se regenera llamando a recalcular_ordenamiento()

        # Grid y calles
        GRID_COLS = estado.get("grid_cols", 1)
        GRID_ROWS = estado.get("grid_rows", 1)
        CALLES_L = list(estado.get("calles_list", []))

        # Tamaños
        TAMANO_USUARIO_W = estado.get("tamano_usuario_w", 210.0)
        TAMANO_USUARIO_H = estado.get("tamano_usuario_h", 100.0)
        SANGRE = estado.get("sangre", 3.0)
        TAMANO_FINAL_PLIEGO["w_mm"] = estado.get("pliego_ancho")
        TAMANO_FINAL_PLIEGO["h_mm"] = estado.get("pliego_alto")
        PLIEGO_CONGELADO = estado.get("pliego_congelado", False)

        # Offsets
        USER_OFFSET_IMAGEN_X_MM = estado.get("offset_img_x", 0.0)
        USER_OFFSET_IMAGEN_Y_MM = estado.get("offset_img_y", 0.0)
        USER_OFFSET_TRAZADO_X_MM = estado.get("offset_trazado_x", 0.0)
        USER_OFFSET_TRAZADO_Y_MM = estado.get("offset_trazado_y", 0.0)

        # Zoom
        # Siempre usar valores por defecto para el zoom, ignorando el estado guardado
        zoom_level["value"] = 0.96
        AUTO_ZOOM = True

        # Marcas de texto
        MARCA_TEXTO_CONTENIDO = estado.get(
            "marca_texto_contenido", "NumStack - Imposición"
        )
        MARCA_TEXTO_POS_SUP_IZQ = estado.get("marca_texto_pos_sup_izq", True)
        MARCA_TEXTO_POS_SUP_DER = estado.get("marca_texto_pos_sup_der", False)
        MARCA_TEXTO_POS_INF_IZQ = estado.get("marca_texto_pos_inf_izq", False)
        MARCA_TEXTO_POS_INF_DER = estado.get("marca_texto_pos_inf_der", False)
        MARCA_TEXTO_POS_CENTRO_SUP = estado.get("marca_texto_pos_centro_sup", False)
        MARCA_TEXTO_POS_CENTRO_INF = estado.get("marca_texto_pos_centro_inf", False)
        MARCA_TEXTO_POS_CENTRO_LAT_IZQ = estado.get(
            "marca_texto_pos_centro_lat_izq", False
        )
        MARCA_TEXTO_POS_CENTRO_LAT_DER = estado.get(
            "marca_texto_pos_centro_lat_der", False
        )
        MARCA_TEXTO_ROTACION = estado.get("marca_texto_rotacion", 0)
        MARCA_TEXTO_FAMILIA = estado.get("marca_texto_familia", "Arial")
        MARCA_TEXTO_TIPO = estado.get("marca_texto_tipo", "Regular")
        MARCA_TEXTO_CUERPO = estado.get("marca_texto_cuerpo", 12)
        MARCA_TEXTO_COLOR = estado.get("marca_texto_color", ft.Colors.BLACK)
        MARCA_TEXTO_OFFSET_H_MM = estado.get("marca_texto_offset_h_mm", 0.0)
        MARCA_TEXTO_OFFSET_V_MM = estado.get("marca_texto_offset_v_mm", 0.0)

        # Configuración de cruces
        LONGITUD_CRUZ_MM = estado.get("longitud_cruz_mm", 10.0)
        GROSOR_CRUZ_PT = estado.get("grosor_cruz_pt", 0.5)
        OFFSET_CRUZ_MM = estado.get("offset_cruz_mm", 5.0)
        AUTO_SANGRE_OFFSET_CRUZ = estado.get("auto_sangre_offset_cruz", False)
        OFFSET_SEGURIDAD_MM = estado.get("offset_seguridad_mm", 1.0)
        LONGITUD_BRAZO_MAX_MM = estado.get("longitud_brazo_max_mm", 5.0)

        # print(f"[RESTAURAR ESTADO] ✅ Estado restaurado - PDF: {_archivo_seleccionado.get('nombre', 'Sin PDF')}")
        # print(f"[RESTAURAR ESTADO]   Grid: {GRID_COLS}x{GRID_ROWS}, Tamaño: {TAMANO_USUARIO_W}x{TAMANO_USUARIO_H}mm")
        # print(f"[RESTAURAR ESTADO]   🔍 CALLES_L global después de restaurar: {CALLES_L}")
        return True

    except Exception as ex:
        print(f"[RESTAURAR ESTADO] ❌ Error restaurando estado: {ex}")
        import traceback

        traceback.print_exc()
        return False


def actualizar_controles_desde_estado(
    textfield_ancho,
    textfield_alto,
    textfield_sangre,
    textfield_grid_cols,
    textfield_grid_rows,
    textfield_tamano_usuario_w,
    textfield_tamano_usuario_h,
    textfield_offset_img_x,
    textfield_offset_img_y,
    textfield_offset_trazado_x,
    textfield_offset_trazado_y,
    dropdown_copias,
    dropdown_doble_cara,
    dropdown_rotacion,
    checkbox_cruces,
    checkbox_lineas_corte,
    checkbox_marcas_texto,
    checkbox_linea_exterior,
):
    """
    Actualiza los valores de todos los controles de UI desde _estado_impo_ui.
    Debe llamarse DESPUÉS de crear los controles pero ANTES de mostrar la ventana.
    """
    try:
        estado = _estado_impo_ui
        # Determinar unidad actual para mostrar (fallback a preferencia inicial)
        try:
            unit = estado.get("unit") or _initial_unit_pref or "mm"
        except Exception:
            unit = _initial_unit_pref if "_initial_unit_pref" in globals() else "mm"

        # TextFields de tamaño de pliego (convertir desde mm a la unidad seleccionada)
        try:
            if textfield_ancho and estado.get("pliego_ancho") is not None:
                try:
                    textfield_ancho.value = (
                        f"{convert_from_mm(float(estado['pliego_ancho']), unit):.2f}"
                    )
                except Exception:
                    textfield_ancho.value = f"{estado['pliego_ancho']:.2f}"
        except Exception:
            pass
        try:
            if textfield_alto and estado.get("pliego_alto") is not None:
                try:
                    textfield_alto.value = (
                        f"{convert_from_mm(float(estado['pliego_alto']), unit):.2f}"
                    )
                except Exception:
                    textfield_alto.value = f"{estado['pliego_alto']:.2f}"
        except Exception:
            pass

        # TextFields de configuración (sangre convertido)
        if textfield_sangre:
            try:
                sang = estado.get("sangre", 3.0)
                textfield_sangre.value = f"{convert_from_mm(float(sang), unit):.2f}"
            except Exception:
                try:
                    textfield_sangre.value = f"{estado.get('sangre', 3.0):.2f}"
                except Exception:
                    pass
        if textfield_grid_cols:
            textfield_grid_cols.value = str(estado.get("grid_cols", 1))
        if textfield_grid_rows:
            textfield_grid_rows.value = str(estado.get("grid_rows", 1))
        if textfield_tamano_usuario_w:
            try:
                tw = estado.get("tamano_usuario_w", 210.0)
                textfield_tamano_usuario_w.value = (
                    f"{convert_from_mm(float(tw), unit):.2f}"
                )
            except Exception:
                textfield_tamano_usuario_w.value = (
                    f"{estado.get('tamano_usuario_w', 210.0):.2f}"
                )
            textfield_tamano_usuario_w.visible = True
            try:
                textfield_tamano_usuario_w.update()
            except:
                pass
        if textfield_tamano_usuario_h:
            try:
                th = estado.get("tamano_usuario_h", 100.0)
                textfield_tamano_usuario_h.value = (
                    f"{convert_from_mm(float(th), unit):.2f}"
                )
            except Exception:
                textfield_tamano_usuario_h.value = (
                    f"{estado.get('tamano_usuario_h', 100.0):.2f}"
                )
            textfield_tamano_usuario_h.visible = True
            try:
                textfield_tamano_usuario_h.update()
            except:
                pass

        # TextFields de offsets
        try:
            if textfield_offset_img_x:
                ox = estado.get("offset_img_x", 0.0)
                textfield_offset_img_x.value = f"{convert_from_mm(float(ox), unit):.2f}"
        except Exception:
            try:
                textfield_offset_img_x.value = f"{estado.get('offset_img_x', 0.0):.2f}"
            except Exception:
                pass
        try:
            if textfield_offset_img_y:
                oy = estado.get("offset_img_y", 0.0)
                textfield_offset_img_y.value = f"{convert_from_mm(float(oy), unit):.2f}"
        except Exception:
            try:
                textfield_offset_img_y.value = f"{estado.get('offset_img_y', 0.0):.2f}"
            except Exception:
                pass
        try:
            if textfield_offset_trazado_x:
                tx = estado.get("offset_trazado_x", 0.0)
                textfield_offset_trazado_x.value = (
                    f"{convert_from_mm(float(tx), unit):.2f}"
                )
        except Exception:
            try:
                textfield_offset_trazado_x.value = (
                    f"{estado.get('offset_trazado_x', 0.0):.2f}"
                )
            except Exception:
                pass
        try:
            if textfield_offset_trazado_y:
                ty = estado.get("offset_trazado_y", 0.0)
                textfield_offset_trazado_y.value = (
                    f"{convert_from_mm(float(ty), unit):.2f}"
                )
        except Exception:
            try:
                textfield_offset_trazado_y.value = (
                    f"{estado.get('offset_trazado_y', 0.0):.2f}"
                )
            except Exception:
                pass

        # Dropdowns
        if dropdown_copias:
            dropdown_copias.value = estado.get("dropdown_copias", "1")
        if dropdown_doble_cara:
            dropdown_doble_cara.value = estado.get("dropdown_doble_cara", "cara")
        if dropdown_rotacion:
            dropdown_rotacion.value = estado.get("dropdown_rotacion", "0°")

        # Checkboxes: manejar variantes históricas y elegir TRUE si cualquiera indica True
        try:
            # Cruces
            if checkbox_cruces:
                keys_tried = [
                    "CHECK_BOX_CRUCES",
                    "CHECK_BOX_CRUCES_Y_MARCAS",
                    "checkbox_cruces",
                ]
                val = any(bool(estado.get(k, False)) for k in keys_tried)
                checkbox_cruces.value = val
                print(
                    f"[TRACE READ] checkbox_cruces asignado desde claves {keys_tried} => {val}"
                )
        except Exception:
            pass
        try:
            # Lineas de corte
            if checkbox_lineas_corte:
                keys_tried = [
                    "CHECK_BOX_LINEAS_CORTE",
                    "CHECK_BOX_LINEAS_DE_CORTE",
                    "checkbox_lineas_corte",
                ]
                val = any(bool(estado.get(k, False)) for k in keys_tried)
                checkbox_lineas_corte.value = val
                print(
                    f"[TRACE READ] checkbox_lineas_corte asignado desde claves {keys_tried} => {val}"
                )
        except Exception:
            pass
        try:
            # Marcas de texto
            if checkbox_marcas_texto:
                keys_tried = [
                    "CHECK_BOX_MARCAS_TEXTO",
                    "CHECK_BOX_MARCAS_DE_TEXTO",
                    "checkbox_marcas_texto",
                ]
                val = any(bool(estado.get(k, False)) for k in keys_tried)
                checkbox_marcas_texto.value = val
                print(
                    f"[TRACE READ] checkbox_marcas_texto asignado desde claves {keys_tried} => {val}"
                )
        except Exception:
            pass
        try:
            # Linea exterior
            if checkbox_linea_exterior:
                keys_tried = ["CHECK_BOX_LINEA_EXTERIOR", "checkbox_linea_exterior"]
                # Default True historically for linea_exterior if absent
                val = (
                    any(bool(estado.get(k, False)) for k in keys_tried)
                    if any(k in estado for k in keys_tried)
                    else estado.get("checkbox_linea_exterior", True)
                )
                checkbox_linea_exterior.value = val
                print(
                    f"[TRACE READ] checkbox_linea_exterior asignado desde claves {keys_tried} => {val}"
                )
        except Exception:
            pass

        # print("[ACTUALIZAR CONTROLES] ✅ Controles actualizados desde estado")
        # print(f"[ACTUALIZAR CONTROLES]   Tamaño usuario: {estado.get('tamano_usuario_w', 210.0):.2f} x {estado.get('tamano_usuario_h', 100.0):.2f} mm")
        return True

    except Exception as ex:
        print(f"[ACTUALIZAR CONTROLES] ❌ Error: {ex}")
        import traceback

        traceback.print_exc()
        return False


# funcion para cambiar y eliminar
def dimensiones_mediabox_celdas_impo(
    tamano_usuario_w,
    tamano_usuario_h,
    sangre,
    calles,
    grid_cols,
    grid_rows,
    mediabox_w,
    mediabox_h,
):

    # ✅ DECLARAR GLOBALES AL INICIO
    global GRID_COLS, GRID_ROWS, TAMANO_TRAZADO

    """
    Calcula las dimensiones de todas las celdas del grid y las devuelve en un dict.
    Las claves son 'row_col: {row},{col}'.
    """
    resultados = {}

    # Preparar listas de calles horizontales y verticales UNA VEZ
    # ✅ CORREGIDO: n_v son calles entre COLUMNAS, n_h son calles entre FILAS
    n_v = max(0, grid_cols - 1)  # calles verticales (entre columnas)
    n_h = max(0, grid_rows - 1)  # calles horizontales (entre filas)
    vert_calles = []  # calles verticales (entre columnas)
    horiz_calles = []  # calles horizontales (entre filas)

    if isinstance(calles, (list, tuple)):
        if len(calles) >= n_v + n_h:
            # ORDEN V-FIRST: primero verticales, luego horizontales
            vert_calles = [float(x) for x in calles[:n_v]]
            horiz_calles = [float(x) for x in calles[n_v : n_v + n_h]]
        else:
            fallback = float(calles[0]) if len(calles) > 0 else float(sangre)
            vert_calles = [fallback] * n_v
            horiz_calles = [fallback] * n_h
    else:
        val = float(calles)
        vert_calles = [val] * n_v
        horiz_calles = [val] * n_h

    # funciones de acceso a calles (ahora usan las listas calculadas)
    # ✅ CORREGIDO: usar las listas correctas según la semántica

    def calle_h_derecha(col_idx):
        # Calle a la DERECHA de la columna col_idx (entre columnas) → usar vert_calles
        if col_idx < len(vert_calles):
            return float(vert_calles[col_idx])
        return 0.0

    def calle_h_izquierda(col_idx):
        # Calle a la IZQUIERDA de la columna col_idx (entre columnas) → usar vert_calles
        if col_idx - 1 >= 0 and (col_idx - 1) < len(vert_calles):
            return float(vert_calles[col_idx - 1])
        return 0.0

    def calle_v_abajo(row_idx):
        # Calle ABAJO de la fila row_idx (entre filas) → usar horiz_calles
        if row_idx < len(horiz_calles):
            return float(horiz_calles[row_idx])
        return 0.0

    def calle_v_arriba(row_idx):
        # Calle ARRIBA de la fila row_idx (entre filas) → usar horiz_calles
        if row_idx - 1 >= 0 and (row_idx - 1) < len(horiz_calles):
            return float(horiz_calles[row_idx - 1])
        return 0.0

    # if DEBUG_IMPO_UI:
    #     print("\n" + "="*80)
    #     print("📊 DEPURACIÓN - DIMENSIONES DE CELDAS INICIALES:")
    #     print("="*80)

    # iterar celdas para construir metadatos por celda (pero NO acumular tamano_total aquí)

    for row in range(grid_rows):
        for col in range(grid_cols):
            # --- Lógica original de una celda ---

            sangre_pdf_w = (mediabox_w - tamano_usuario_w) / 2.0
            sangre_pdf_h = (mediabox_h - tamano_usuario_h) / 2.0

            sangre_izq_deseada = (
                min(float(sangre), calle_h_izquierda(col) / 2.0)
                if col > 0
                else float(sangre)
            )
            sangre_der_deseada = (
                min(float(sangre), calle_h_derecha(col) / 2.0)
                if col < grid_cols - 1
                else float(sangre)
            )
            sangre_sup_deseada = (
                min(float(sangre), calle_v_arriba(row) / 2.0)
                if row > 0
                else float(sangre)
            )
            sangre_inf_deseada = (
                min(float(sangre), calle_v_abajo(row) / 2.0)
                if row < grid_rows - 1
                else float(sangre)
            )

            if row == 0:
                sangre_sup_deseada = float(sangre)
            if row == grid_rows - 1:
                sangre_inf_deseada = float(sangre)
            if col == 0:
                sangre_izq_deseada = float(sangre)
            if col == grid_cols - 1:
                sangre_der_deseada = float(sangre)

            celda_w = tamano_usuario_w + sangre_izq_deseada + sangre_der_deseada
            celda_h = tamano_usuario_h + sangre_sup_deseada + sangre_inf_deseada

            calle_margen_w = 0.0
            calle_margen_h = 0.0
            if col < grid_cols - 1:
                right_call = calle_h_derecha(col)
                # La calle SIEMPRE determina el espaciador: calle / 2
                # Sin importar si sangre es mayor o menor
                calle_margen_w = max(0.0, right_call / 2.0)
            if row < grid_rows - 1:
                down_call = calle_v_abajo(row)
                # Lo mismo para vertical: la calle define el espaciador
                calle_margen_h = max(0.0, down_call / 2.0)

            # Offset automático: varía por celda según sangre ajustada por calles
            # Este es el offset que centra la imagen en la celda
            offset_imagen_x_left = sangre_izq_deseada - sangre_pdf_w
            offset_imagen_y_top = sangre_sup_deseada - sangre_pdf_h

            # No acumulamos el tamaño total por celda (evita duplicar sangres)

            resultados[f"row_col: {row},{col}"] = {
                "celda_w": celda_w,
                "celda_h": celda_h,
                "calle_margen_w": calle_margen_w,
                "calle_margen_h": calle_margen_h,
                "calle": calles,
                "sangre_izq_deseada": sangre_izq_deseada,
                "sangre_der_deseada": sangre_der_deseada,
                "sangre_sup_deseada": sangre_sup_deseada,
                "sangre_inf_deseada": sangre_inf_deseada,
                "offset_imagen_x_left": offset_imagen_x_left,
                "offset_imagen_y_top": offset_imagen_y_top,
            }

            # DEBUG: Print cell dimensions (DESACTIVADO)
            # print(f"row_col: {row},{col}: celda_w={celda_w:.2f}, celda_h={celda_h:.2f}, "
            #       f"calle_margen_w={calle_margen_w:.2f}, calle_margen_h={calle_margen_h:.2f}, "
            #       f"calle={calles}, "
            #       f"sangre_izq={sangre_izq_deseada:.2f}, sangre_der={sangre_der_deseada:.2f}, "
            #       f"sangre_sup={sangre_sup_deseada:.2f}, sangre_inf={sangre_inf_deseada:.2f}, "
            #       f"offset_imagen_UI_x={offset_imagen_x_left:.2f}, offset_imagen_UI_y={offset_imagen_y_top:.2f}, "
            #       f"offset_imagen_FRITZ_x={offset_imagen_fritz_x_left:.2f}, offset_imagen_FRITZ_y={offset_imagen_fritz_y_top:.2f}")

    # Calcular tamaño total final SUMANDO el tamaño sin sangre, sus calles y su sangre x 2
    # ✅ CORREGIDO: ancho usa vert_calles (entre columnas), alto usa horiz_calles (entre filas)
    tamano_total_w = (GRID_COLS * tamano_usuario_w) + sum(vert_calles) + (sangre * 2)
    tamano_total_h = (GRID_ROWS * tamano_usuario_h) + sum(horiz_calles) + (sangre * 2)

    resultados["tamano_total_w"] = round(tamano_total_w, 6)
    resultados["tamano_total_h"] = round(tamano_total_h, 6)
    resultados["sangre_mm"] = float(
        sangre
    )  # ✅ Guardar sangre para usar en marcas medianales

    # print(
    #     f"\n[CALC] Tamaño total del grid: {tamano_total_w:.2f} × {tamano_total_h:.2f} mm\n"
    # )

    TAMANO_TRAZADO = {"w_mm": tamano_total_w, "h_mm": tamano_total_h}

    return resultados


def compute_border_px(
    grosor_mm=None, grosor_pt=None, escala=ESCALA_VISUAL, viewer_zoom=None
):
    """Calcula el grosor en píxeles para bordes y líneas, compensando por el zoom del viewer."""
    # Priorizar mm si se proporciona, si no usar pt->mm
    try:
        if grosor_mm is not None:
            px = float(grosor_mm) * float(escala)
        elif grosor_pt is not None:
            # convertir pt -> mm -> px
            mm = float(grosor_pt) * PT_TO_MM
            px = mm * float(escala)
        else:
            px = 1.0
    except Exception:
        px = 1.0

    # Compensación por zoom del viewer para mantener el grosor visual constante
    try:
        if viewer_zoom and viewer_zoom > 0:
            compensated = px / float(viewer_zoom)
        else:
            compensated = px
    except Exception:
        compensated = px

    return float(compensated)


def compute_common_thicknesses(escala=ESCALA_VISUAL, viewer_zoom=None):
    """Devuelve un dict con grosores en px (compensados) para los mm usados frecuentemente."""
    if viewer_zoom is None:
        viewer_zoom = (
            zoom_final.get("value") if isinstance(zoom_final, dict) else zoom_final
        )

    return {
        "m0_15": compute_border_px(
            grosor_mm=0.15, escala=escala, viewer_zoom=viewer_zoom
        ),
        "m0_2": compute_border_px(
            grosor_mm=0.2, escala=escala, viewer_zoom=viewer_zoom
        ),
        "m0_25": compute_border_px(
            grosor_mm=0.25, escala=escala, viewer_zoom=viewer_zoom
        ),
    }


def build_calles_list(calle_value, grid_cols, grid_rows):
    """
    Construye la lista de calles en orden V-first: [V1, V2, ..., H1, H2, ...].
    Es decir, primero las calles verticales (entre columnas) y luego las
    horizontales (entre filas).

    - V = vertical (separación entre columnas)
    - H = horizontal (separación entre filas)

    Si se pasa un único valor numérico se replica para todas las calles
    (verticales + horizontales). La función asegura que la lista resultante
    tenga exactamente el número esperado de valores (trunca o repite el
    último valor si es necesario).
    """
    global CALLES_L

    # Número de calles horizontales = filas - 1 (separaciones H entre filas)
    n_h = max(0, grid_rows - 1)
    # Número de calles verticales = columnas - 1 (separaciones V entre columnas)
    n_v = max(0, grid_cols - 1)
    total_calles = n_h + n_v

    if isinstance(calle_value, (list, tuple)):
        # Si ya es una lista, usarla directamente
        calle_list = [float(x) for x in calle_value]
    else:
        # Si es un número, replicar para todas las calles
        calle_float = float(calle_value)
        calle_list = [calle_float] * total_calles

    # Asegurar que tiene el tamaño correcto
    while len(calle_list) < total_calles:
        calle_list.append(calle_list[-1] if calle_list else 0.0)

    # Truncar si es más largo
    calle_list = calle_list[:total_calles]

    # Guardar en global
    CALLES_L = calle_list

    return calle_list


def imprimir_analisis_dim_celds(dim_celds, titulo="ANÁLISIS DE dim_celds"):
    """
    Imprime el contenido de dim_celds de forma estructurada y legible.
    Organizado por capas, mostrando todos los offsets necesarios para inversión DORSO.
    """
    if not dim_celds:
        print(f"\n{'='*80}\n{titulo}\n{'='*80}")
        print("⚠️ dim_celds está vacío o es None")
        return

    if not DEBUG_IMPO_UI:
        return

    print(f"\n{'='*80}")
    print(f"{titulo}")
    print(f"{'='*80}\n")

    # ============================================================================
    # DIMENSIONES GENERALES DEL PLIEGO
    # ============================================================================
    print("📐 DIMENSIONES GENERALES DEL PLIEGO:")
    print("-" * 80)
    if "tamano_total_w" in dim_celds:
        print(f"  • Ancho total: {dim_celds['tamano_total_w']:.2f} mm")
    if "tamano_total_h" in dim_celds:
        print(f"  • Alto total: {dim_celds['tamano_total_h']:.2f} mm")
    if "grid_cols" in dim_celds:
        print(f"  • Columnas: {dim_celds['grid_cols']}")
    if "grid_rows" in dim_celds:
        print(f"  • Filas: {dim_celds['grid_rows']}")
    print()

    # ============================================================================
    # INFORMACIÓN DE CAPAS (LAYERS)
    # ============================================================================
    if "capas" in dim_celds and isinstance(dim_celds["capas"], dict):
        print("🎨 INFORMACIÓN DE CAPAS (LAYERS):")
        print("-" * 80)
        for capa_nombre, capa_data in sorted(dim_celds["capas"].items()):
            print(f"\n  📍 {capa_nombre.upper()}:")
            if isinstance(capa_data, dict):
                for key, value in sorted(capa_data.items()):
                    if isinstance(value, (int, float)):
                        print(f"      {key}: {value:.2f} mm")
                    else:
                        print(f"      {key}: {value}")
        print()

    # ============================================================================
    # OFFSETS DE CELDAS (CRÍTICO PARA INVERSIÓN DORSO)
    # ============================================================================
    if "offsets_celdas" in dim_celds:
        print("📍 OFFSETS DE CELDAS (Para inversión DORSO):")
        print("-" * 80)
        offsets = dim_celds["offsets_celdas"]
        if isinstance(offsets, list):
            for i, offset_data in enumerate(offsets):
                if isinstance(offset_data, dict):
                    row = offset_data.get("row", "?")
                    col = offset_data.get("col", "?")
                    x = offset_data.get("x_mm", 0)
                    y = offset_data.get("y_mm", 0)
                    w = offset_data.get("w_mm", 0)
                    h = offset_data.get("h_mm", 0)
                    print(
                        f"  Celda [{row},{col}]: x={x:.2f}mm, y={y:.2f}mm, w={w:.2f}mm, h={h:.2f}mm"
                    )
        print()

    # ============================================================================
    # INFORMACIÓN DE GRID (offsets_grid_info)
    # ============================================================================
    if "offsets_grid_info" in dim_celds:
        print("🔲 INFORMACIÓN DE GRID:")
        print("-" * 80)
        grid_info = dim_celds["offsets_grid_info"]
        if isinstance(grid_info, dict):
            for key, value in sorted(grid_info.items()):
                if key in ["left_edges", "top_edges"]:
                    print(f"  • {key}: {value}")
                elif isinstance(value, (int, float)):
                    print(f"  • {key}: {value:.2f} mm")
                elif isinstance(value, list) and len(value) > 0:
                    print(f"  • {key}: {value}")
                else:
                    print(f"  • {key}: {value}")
        print()

    # ============================================================================
    # DATOS DE CELDAS INDIVIDUALES (row_col)
    # ============================================================================
    print("🔢 DATOS DE CELDAS INDIVIDUALES:")
    print("-" * 80)
    row_col_keys = [
        k for k in dim_celds.keys() if isinstance(k, str) and k.startswith("row_col:")
    ]
    if row_col_keys:
        for key in sorted(row_col_keys):
            celda_data = dim_celds[key]
            print(f"\n  📦 {key}:")
            if isinstance(celda_data, dict):
                # Dimensiones de celda
                if "celda_w" in celda_data or "celda_h" in celda_data:
                    print(
                        f"      Dimensiones: {celda_data.get('celda_w', 0):.2f} × {celda_data.get('celda_h', 0):.2f} mm"
                    )

                # Sangres
                sangres = []
                for s_key, s_label in [
                    ("sangre_izq_deseada", "sangre_izq"),
                    ("sangre_der_deseada", "sangre_der"),
                    ("sangre_sup_deseada", "sangre_sup"),
                    ("sangre_inf_deseada", "sangre_inf"),
                ]:
                    if s_key in celda_data:
                        sangres.append(f"{s_label}={celda_data[s_key]:.2f}")
                if sangres:
                    print(f"      Sangres: {', '.join(sangres)} mm")

                # Offsets de imagen (UI y FRITZ)
                if (
                    "offset_imagen_x_left" in celda_data
                    or "offset_imagen_y_top" in celda_data
                ):
                    print(
                        f"      Offset UI: x={celda_data.get('offset_imagen_x_left', 0):.2f}, y={celda_data.get('offset_imagen_y_top', 0):.2f} mm"
                    )
                if (
                    "offset_imagen_fritz_x_left" in celda_data
                    or "offset_imagen_fritz_y_top" in celda_data
                ):
                    print(
                        f"      Offset FRITZ: x={celda_data.get('offset_imagen_fritz_x_left', 0):.2f}, y={celda_data.get('offset_imagen_fritz_y_top', 0):.2f} mm"
                    )

                # Calles
                if "calle" in celda_data:
                    print(f"      Calles: {celda_data['calle']}")
                if "calle_margen_w" in celda_data or "calle_margen_h" in celda_data:
                    print(
                        f"      Márgenes calle: w={celda_data.get('calle_margen_w', 0):.2f}, h={celda_data.get('calle_margen_h', 0):.2f} mm"
                    )
    else:
        print("  ⚠️ No se encontraron datos de celdas individuales (row_col:*)")
    print()

    # ============================================================================
    # INFORMACIÓN DE CRUCES Y CORTE
    # ============================================================================
    # if "cruces_corte" in dim_celds:
    #     print("✂️ INFORMACIÓN DE CRUCES Y CORTE:")
    #     print("-" * 80)
    #     cruces_data = dim_celds["cruces_corte"]
    #     if isinstance(cruces_data, dict):
    #         for key, value in sorted(cruces_data.items()):
    #             if isinstance(value, (int, float)):
    #                 print(f"  • {key}: {value:.2f} mm")
    #             else:
    #                 print(f"  • {key}: {value}")
    #     print()

    # ============================================================================
    # OTROS DATOS RELEVANTES
    # ============================================================================
    otros_keys = [
        k
        for k in dim_celds.keys()
        if k
        not in [
            "tamano_total_w",
            "tamano_total_h",
            "grid_cols",
            "grid_rows",
            "capas",
            "offsets_celdas",
            "offsets_grid_info",
            "cruces_corte",
        ]
        and not (isinstance(k, str) and k.startswith("row_col:"))
    ]

    print("=" * 80)
    print(f"✅ FIN DE {titulo}")
    print("=" * 80 + "\n")


# funcion para calcular los offsets de las lineas de corte
def calculo_linea_corte_offsets(
    tamano_usuario_w,
    tamano_usuario_h,
    calles,
    grid_cols,
    grid_rows,
):

    # Calles verticales (entre columnas), calles horizontales (entre filas)
    n_v = max(0, grid_cols - 1)
    n_h = max(0, grid_rows - 1)
    expected = n_v + n_h
    if not isinstance(calles, (list, tuple)) or len(calles) < expected:
        raise ValueError(
            f"compute_linea_corte_offsets: 'calles' debe tener al menos {expected} valores (V-first). Recibido: {calles!r}"
        )

    # Extraer V-first: [V1, V2, ..., H1, H2, ...]
    vert = [float(x) for x in calles[:n_v]] if n_v > 0 else []
    horiz = [float(x) for x in calles[n_v : n_v + n_h]] if n_h > 0 else []

    # left edges X starting at 0 (usa calles verticales entre columnas)
    left_edges = []
    x = 0.0
    for col in range(grid_cols):
        left_edges.append(round(x, 6))
        x += float(tamano_usuario_w)
        if col < n_v:
            x += vert[col]
    tamano_total_w = round(x, 6)

    # top edges Y starting at 0 (usa calles horizontales entre filas)
    top_edges = []
    y = 0.0
    for row in range(grid_rows):
        top_edges.append(round(y, 6))
        y += float(tamano_usuario_h)
        if row < n_h:
            y += horiz[row]
    tamano_total_h = round(y, 6)

    # rects por celda (posición donde va el container tamano_usuario)
    lineas_corte = []
    for r in range(grid_rows):
        for c in range(grid_cols):
            rect = {
                "row": r,
                "col": c,
                "x_mm": left_edges[c],
                "y_mm": top_edges[r],
                "w_mm": float(tamano_usuario_w),
                "h_mm": float(tamano_usuario_h),
            }
            lineas_corte.append(rect)

    return {
        "left_edges": left_edges,
        "top_edges": top_edges,
        "lineas_corte": lineas_corte,
        "tamano_total_w": tamano_total_w,
        "tamano_total_h": tamano_total_h,
        "horiz_calles": horiz,
        "vert_calles": vert,
    }


def calcular_marcas_de_corte_exterior(
    dim_celds, grid_cols, grid_rows, cruces_corte_data=None
):
    """
    Calcula TODAS las marcas de corte exterior usando DATOS_CELDAS.

    PARÁMETRO:
    - dim_celds: Diccionario maestro de celdas (DATOS_CELDAS)

    IMPORTANTE: Cada celda usa DIFERENTES calles según su posición:
    - Celda [r,c] izquierda: usa calle[c-1] (si c > 0)
    - Celda [r,c] derecha: usa calle[c] (si c < grid_cols-1)
    - Celda [r,c] superior: usa calle[grid_cols-1+r] (si r > 0)
    - Celda [r,c] inferior: usa calle[grid_cols-1+r] (si r < grid_rows-1)

    Devuelve:
    - lineas_verticales: lista de dicts con tipo y x_mm
    - lineas_horizontales: lista de dicts con tipo y y_mm
    - tamano_total_w, tamano_total_h: tamaño total
    """

    # Extraer información de DATOS_CELDAS
    lineas_verticales = set()
    lineas_horizontales = set()

    # ┌─────────────────────────────────────────────────────────┐
    # │ CALCULAR LÍNEAS VERTICALES (X)                          │
    # └─────────────────────────────────────────────────────────┘

    for row in range(grid_rows):
        for col in range(grid_cols):
            key = f"row_col: {row},{col}"
            if key not in dim_celds:
                continue

            celda = dim_celds[key]
            celda_w = celda.get("celda_w", 0)
            calle_list = celda.get("calle", [])

            # Calcular posición X de esta celda
            x_inicio = 0.0
            for c in range(col):
                x_inicio += celda_w
                if (
                    c < len(calle_list) // 2
                ):  # Calles horizontales están en la primera mitad
                    calle_h = calle_list[c]
                    x_inicio += calle_h / 2.0

            # Línea de INICIO de celda (borde izquierdo)
            lineas_verticales.add(round(x_inicio, 6))

            # Línea de FINAL de celda (borde derecho)
            x_final = x_inicio + celda_w
            lineas_verticales.add(round(x_final, 6))

            # Línea en CENTRO de calle DERECHA (si no es última columna)
            if col < grid_cols - 1 and len(calle_list) > 0:
                calle_der = calle_list[0]  # Primera calle (derecha)
                x_centro_calle = x_final + calle_der / 2.0
                lineas_verticales.add(round(x_centro_calle, 6))

    # ┌─────────────────────────────────────────────────────────┐
    # │ CALCULAR LÍNEAS HORIZONTALES (Y)                        │
    # └─────────────────────────────────────────────────────────┘

    for row in range(grid_rows):
        for col in range(grid_cols):
            key = f"row_col: {row},{col}"
            if key not in dim_celds:
                continue

            celda = dim_celds[key]
            celda_h = celda.get("celda_h", 0)
            calle_list = celda.get("calle", [])

            # Calcular posición Y de esta celda
            y_inicio = 0.0
            n_h = (len(calle_list) + 1) // 2  # Número de calles horizontales
            for r in range(row):
                y_inicio += celda_h
                if (
                    r < len(calle_list) - n_h
                ):  # Calles verticales están en la segunda mitad
                    calle_v = calle_list[n_h + r]
                    y_inicio += calle_v / 2.0

            # Línea de INICIO de celda (borde superior)
            lineas_horizontales.add(round(y_inicio, 6))

            # Línea de FINAL de celda (borde inferior)
            y_final = y_inicio + celda_h
            lineas_horizontales.add(round(y_final, 6))

            # Línea en CENTRO de calle INFERIOR (si no es última fila)
            if row < grid_rows - 1 and len(calle_list) > 0:
                n_h = (len(calle_list) + 1) // 2
                if n_h < len(calle_list):
                    calle_inf = calle_list[n_h]  # Primera calle vertical
                    y_centro_calle = y_final + calle_inf / 2.0
                    lineas_horizontales.add(round(y_centro_calle, 6))

    # Convertir a listas ordenadas
    lineas_verticales = sorted(list(lineas_verticales))
    lineas_horizontales = sorted(list(lineas_horizontales))

    # Obtener tamaño total
    tamano_total_w = lineas_verticales[-1] if lineas_verticales else 0.0
    tamano_total_h = lineas_horizontales[-1] if lineas_horizontales else 0.0

    # Convertir a dicts con tipo
    lineas_vert_dict = [{"tipo": "linea", "x_mm": x} for x in lineas_verticales]
    lineas_horiz_dict = [{"tipo": "linea", "y_mm": y} for y in lineas_horizontales]

    return {
        "lineas_verticales": lineas_vert_dict,
        "lineas_horizontales": lineas_horiz_dict,
        "tamano_total_w": tamano_total_w,
        "tamano_total_h": tamano_total_h,
    }


# funcion para calcular los offsets de las lineas de samgre
def calculo_linea_sangre_offsets(dim_celds):
    """
    Calcula los offsets de las sangres usando los tamaños y márgenes definidos en DATOS_CELDAS.

    PARÁMETRO:
    - dim_celds: Diccionario maestro de celdas (DATOS_CELDAS)

    Extrae el grid (rows y cols) directamente de las claves.
    Devuelve dict con left_edges, top_edges, lineas_sangre y tamano_total (mm).
    """
    # Extraer filas y columnas únicas del grid interno
    rows = set()
    cols = set()
    for k in dim_celds:
        if k.startswith("row_col: "):
            _, rc = k.split(": ")
            r, c = rc.split(",")
            rows.add(int(r))
            cols.add(int(c))
    rows = sorted(rows)
    cols = sorted(cols)

    left_edges = []
    top_edges = []

    # Preferir usar los offsets de corte ya calculados (si existen) para mantener coherencia
    offsets_corte = dim_celds.get("offsets_corte_tamano_usuario")
    if offsets_corte:
        cut_left = offsets_corte.get("left_edges", [])
        cut_top = offsets_corte.get("top_edges", [])
        # Construir left_edges y top_edges para sangres restando la sangre izquierda/superior de cada celda
        for c in cols:
            key = f"row_col: {rows[0]},{c}"
            celda = dim_celds[key]
            sangre_izq = celda.get("sangre_izq_deseada", 0.0)
            # left_edges para sangre = corte_left - sangre_izq
            left_edges.append(round(cut_left[c] - float(sangre_izq), 6))
        for r in rows:
            key = f"row_col: {r},{cols[0]}"
            celda = dim_celds[key]
            sangre_sup = celda.get("sangre_sup_deseada", 0.0)
            top_edges.append(round(cut_top[r] - float(sangre_sup), 6))

        # tamano_total basado en corte (el área de trabajo principal)
        tamano_total_w = offsets_corte.get("tamano_total_w", 0.0)
        tamano_total_h = offsets_corte.get("tamano_total_h", 0.0)
    else:
        # Fallback: antiguo método (menos preciso) si no hay offsets de corte
        x = 0.0
        for col in cols:
            key = f"row_col: {rows[0]},{col}"
            celda = dim_celds[key]
            left_edges.append(round(x, 6))
            x += celda["celda_w"]
            if col < cols[-1]:
                x += celda["calle_margen_w"]
        tamano_total_w = round(x, 6)

        y = 0.0
        for row in rows:
            key = f"row_col: {row},{cols[0]}"
            celda = dim_celds[key]
            top_edges.append(round(y, 6))
            y += celda["celda_h"]
            if row < rows[-1]:
                y += celda["calle_margen_h"]
        tamano_total_h = round(y, 6)

    # Rects por celda (posición y tamaño)
    lineas_sangre = []
    for r in rows:
        for c in cols:
            key = f"row_col: {r},{c}"
            celda = dim_celds[key]
            rect = {
                "row": r,
                "col": c,
                # Si left_edges/top_edges representan el borde exterior de la sangre ya restado, usarlos
                "x_mm": left_edges[c],
                "y_mm": top_edges[r],
                "w_mm": celda["celda_w"],
                "h_mm": celda["celda_h"],
            }
            lineas_sangre.append(rect)

    return {
        "left_edges": left_edges,
        "top_edges": top_edges,
        "lineas_sangre": lineas_sangre,
        "tamano_total_w": tamano_total_w,
        "tamano_total_h": tamano_total_h,
    }


# esta funcion sera eliminada, los offsets de imagen se calculan en dimensiones_mediabox_celdas_impo
def calcular_offset_imagen(
    mediabox_w,
    mediabox_h,
    celda_w,
    celda_h,
    pos_col,
    pos_row,
    grid_cols,
    grid_rows,
    tamano_usuario_w,
    tamano_usuario_h,
    sangre,
    calles,
    calle_efectiva=None,
):

    # Determinar sangre deseada según posición (izq/der/sup/inf)
    sangre_medianal = min(sangre, calles / 2.0)

    # si solo hay una pagina
    if grid_rows == 1 and grid_cols == 1:
        sangre_izq_deseada = float(sangre)
        sangre_der_deseada = float(sangre)
        sangre_sup_deseada = float(sangre)
        sangre_inf_deseada = float(sangre)

    # si es la primera celda
    if pos_row == 0 and pos_col == 0:
        sangre_izq_deseada = float(sangre)
        sangre_der_deseada = float(sangre_medianal)
        sangre_sup_deseada = float(sangre)
        sangre_inf_deseada = float(sangre_medianal)

    # si es la ultima celda de la primera fila
    if pos_row == 0 and pos_col == grid_rows - 1:
        sangre_izq_deseada = float(sangre)
        sangre_der_deseada = float(sangre_medianal)
        sangre_sup_deseada = float(sangre_medianal)
        sangre_inf_deseada = float(sangre)

    # si es la primera celda de la ultima fila
    if pos_row == grid_rows - 1 and pos_col == 0:
        sangre_izq_deseada = float(sangre)
        sangre_der_deseada = float(sangre_medianal)
        sangre_sup_deseada = float(sangre)
        sangre_inf_deseada = float(sangre_medianal)

    # si es la ultima celda
    if pos_row == grid_rows - 1 and pos_col == grid_cols - 1:
        sangre_izq_deseada = float(sangre_medianal)
        sangre_der_deseada = float(sangre)
        sangre_sup_deseada = float(sangre_medianal)
        sangre_inf_deseada = float(sangre)

    # si es una celda inteior
    if (
        pos_row > 0
        and pos_row < grid_rows - 1
        and pos_col > 0
        and pos_col < grid_cols - 1
    ):
        sangre_izq_deseada = float(sangre_medianal)
        sangre_der_deseada = float(sangre_medianal)
        sangre_sup_deseada = float(sangre_medianal)
        sangre_inf_deseada = float(sangre_medianal)

    # Para posicionar la imagen dentro de la celda usamos el offset izquierdo/superior
    # Offset para centrar la imagen del PDF en la celda
    offset_x = (tamano_usuario_w - mediabox_w) / 2.0
    offset_y = (tamano_usuario_h - mediabox_h) / 2.0

    return offset_x, offset_y


def extraer_pagina_como_imagen(pdf_path, num_pagina, dpi=150):
    """Extrae una página del PDF como imagen base64"""
    try:
        doc = fitz.open(pdf_path)
        if num_pagina >= len(doc):
            return None

        page = doc[num_pagina]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")
        img_base64 = base64.b64encode(img_bytes).decode()
        doc.close()
        return img_base64
    except Exception as e:
        print(f"Error extrayendo página {num_pagina}: {e}")
        return None


def calc_viewer_scale_and_boundary(
    contenido_w_px, contenido_h_px, viewer_w_px, viewer_h_px, correction_factor=1
):
    """Calcula zoom y márgenes dinámicos para el InteractiveViewer."""
    # Evitar división por cero
    if contenido_w_px <= 0 or contenido_h_px <= 0:
        return (
            1.0,
            int(max(viewer_w_px, viewer_h_px)),
            int(max(viewer_w_px, viewer_h_px)),
        )

    # Calcular si el contenido cabe en ambas dimensiones
    cabe_en_ancho = contenido_w_px <= viewer_w_px
    cabe_en_alto = contenido_h_px <= viewer_h_px

    if cabe_en_ancho and cabe_en_alto:
        # Contenido cabe completamente, pero puede no llenar el espacio
        # Calcular zoom para que use el máximo espacio disponible
        zoom_w = viewer_w_px / contenido_w_px if contenido_w_px > 0 else 1.0
        zoom_h = viewer_h_px / contenido_h_px if contenido_h_px > 0 else 1.0
        # Usar el menor para que quepa completamente
        zoom = min(zoom_w, zoom_h)
    else:
        # Contenido no cabe: reducir zoom para que quepa
        scale_w = viewer_w_px / contenido_w_px if contenido_w_px > 0 else 1.0
        scale_h = viewer_h_px / contenido_h_px if contenido_h_px > 0 else 1.0
        zoom = min(scale_w, scale_h)

    # Boundary / márgenes dinámicos para permitir panning/centrado
    margen_base_px = 150  # 150px de margen mínimo en el viewer

    # Margen proporcional al zoom: margen_base × zoom
    margen_dinamico_h = int(margen_base_px * zoom)
    margen_dinamico_v = int(margen_base_px * zoom)

    return round(zoom, 2), margen_dinamico_h, margen_dinamico_v


def compute_zoom_final(
    papel_w_mm,
    papel_h_mm,
    viewer_w_px,
    viewer_h_px,
    escala=ESCALA_VISUAL,
    factor=1.0,
    correction_factor=1,
):
    """Calcula el zoom final y márgenes dinámicos para el viewer."""
    try:
        papel_w_px = float(papel_w_mm) * escala
        papel_h_px = float(papel_h_mm) * escala
    except Exception:
        # Valores por defecto razonables si falla la conversión
        papel_w_px = max(1.0, float(papel_w_mm or 1.0)) * escala
        papel_h_px = max(1.0, float(papel_h_mm or 1.0)) * escala

    zoom_auto, margen_h, margen_v = calc_viewer_scale_and_boundary(
        papel_w_px,
        papel_h_px,
        viewer_w_px,
        viewer_h_px,
        correction_factor=correction_factor,
    )

    # Aplicar factor
    try:
        zoom_final = round(float(zoom_auto) * float(factor), 3)
    except Exception:
        zoom_final = round(float(zoom_auto), 3)

    return zoom_final, int(margen_h), int(margen_v), zoom_auto


def extraer_datos_base(dim_celds, grid_cols, grid_rows):
    """
    Extrae dimensiones base de DATOS_CELDAS (estructura nueva).
    """
    # Obtener primera celda para extraer dimensiones base
    first_key = f"row_col: 0,0"
    if first_key not in dim_celds:
        return {
            "celda_w": 0,
            "celda_h": 0,
            "calle_efectiva_w": 0,
            "calle_efectiva_h": 0,
            "tamano_total_w": dim_celds.get("tamano_total_w", 0),
            "tamano_total_h": dim_celds.get("tamano_total_h", 0),
        }

    first_cell = dim_celds[first_key]
    celda_w = first_cell.get("celda_w", 0)
    celda_h = first_cell.get("celda_h", 0)
    calle_margen_w = first_cell.get("calle_margen_w", 0)
    calle_margen_h = first_cell.get("calle_margen_h", 0)

    # Calcular calle_efectiva (es el margen que queda entre celdas)
    calle_efectiva_w = calle_margen_w
    calle_efectiva_h = calle_margen_h

    return {
        "celda_w": celda_w,
        "celda_h": celda_h,
        "calle_efectiva_w": calle_efectiva_w,
        "calle_efectiva_h": calle_efectiva_h,
        "tamano_total_w": dim_celds.get("tamano_total_w", 0),
        "tamano_total_h": dim_celds.get("tamano_total_h", 0),
    }


def read_float_field_safe(field_ref, fallback=None):
    """Lee de forma segura un TextField referenciado y devuelve float o fallback."""
    try:
        if field_ref and field_ref.current:
            val = field_ref.current.value
            if val is None:
                return fallback
            val_s = str(val).strip()
            if val_s == "":
                return fallback
            return float(val_s)
    except Exception:
        pass
    return fallback


def obtener_tamano_real_pdf(pdf_path):
    """Obtiene el tamaño real del mediabox del PDF en mm"""
    try:
        doc = fitz.open(pdf_path)
        if len(doc) == 0:
            return None

        page = doc[0]
        rect = page.mediabox
        width_pt = rect.width
        height_pt = rect.height
        width_mm = width_pt * PT_TO_MM
        height_mm = height_pt * PT_TO_MM
        doc.close()

        return (width_mm, height_mm)
    except Exception as e:
        print(f"Error leyendo PDF: {e}")
        return None


# los calculos ya estan creados en dimensiones_mediabox_celdas_impo,quitar lo que no proceda
def crear_celda_imposicion(
    img_base64,
    mediabox_w,
    mediabox_h,
    celda_w,
    celda_h,
    offset_auto_x,
    offset_auto_y,
    user_offset_x,
    user_offset_y,
    escala_visual,
    sangre,
    calles,
    pos_col=None,
    pos_row=None,
    img_src=None,  # Nuevo parámetro para ruta de archivo
):
    """Crea una celda con la imagen del PDF posicionada"""

    # --- Calcular sangres y calles EFECTIVAS antes de aplicar escala ---
    # Reglas solicitadas por el usuario:
    # 1) si sangre == calles -> sangre = calles / 2
    # 2) si sangre > calles  -> calles = calles / 2
    # 3) si sangre < calles  -> mantener ambos
    sangre_eff = float(sangre)
    calles_eff = float(calles)

    if sangre_eff == calles_eff:
        # sangre igual a calle -> la sangre efectiva en la calle será la mitad
        sangre_eff = calles_eff / 2.0
    elif sangre_eff > calles_eff:
        # sangre mayor que calle -> la calle se reduce a la mitad
        calles_eff = calles_eff / 2.0
    # else: sangre < calles -> mantener valores

    # Sangre medianal (la que cabe en las calles interiores)
    # Si no hay calles (calles_eff == 0) no hay sangre interior
    sangre_medianal = min(sangre_eff, calles_eff / 2.0) if calles_eff > 0 else 0.0

    # Calcular celda en mm según las sangres efectivas:
    # La celda nominal ya viene calculada fuera (celda_w/celda_h) pero
    # en preimpresión la sangre exterior no debe agrandar el trazado interno
    # salvo en los bordes exteriores. Aquí ajustamos celda (en mm) si es
    # necesario: mantenemos celda_w/celda_h como área total de celda;
    # los offsets de la imagen se ajustarán para posicionar la sangre.

    # Convertir a píxeles usando la escala_visual
    celda_w_px = celda_w * escala_visual
    celda_h_px = celda_h * escala_visual
    img_w_px = mediabox_w * escala_visual
    img_h_px = mediabox_h * escala_visual

    # Ajuste de offsets en mm: debemos aplicar la sangre deseada según
    # posición de la celda (offset_auto ya viene calculado teniendo en cuenta
    # la sangre del PDF). Aquí sumamos el offset automático y el del usuario
    # pero ambos se expresan en mm y se convierten a px *tras* aplicar la
    # lógica de sangre/calles (ya hecho arriba)
    offset_total_x = (offset_auto_x + user_offset_x) * escala_visual
    offset_total_y = (offset_auto_y + user_offset_y) * escala_visual

    # Si se pasó la posición en el grid, calcular qué sangres están presentes
    try:
        if pos_col is not None and pos_row is not None:
            spacing_w = (
                0
                if "calle_efectiva_w" not in globals()
                else globals().get("calle_efectiva_w", 0)
            )
            sangre_medianal_local = (
                min(float(sangre), float(calles) / 2.0) if float(calles) > 0 else 0.0
            )
            sangre_izq = float(sangre) if pos_col == 0 else sangre_medianal_local
            sangre_der = (
                float(sangre) if pos_col == GRID_COLS - 1 else sangre_medianal_local
            )
            sangre_sup = float(sangre) if pos_row == 0 else sangre_medianal_local
            sangre_inf = (
                float(sangre) if pos_row == GRID_ROWS - 1 else sangre_medianal_local
            )

            sangre_izq_px = sangre_izq * escala_visual
            sangre_der_px = sangre_der * escala_visual
            sangre_sup_px = sangre_sup * escala_visual
            sangre_inf_px = sangre_inf * escala_visual

            # Posición de la celda en px
            celda_w_px_local = celda_w_px
            celda_h_px_local = celda_h_px

    except Exception:
        pass

    # Crear imagen usando src (archivo) o src_base64
    imagen_args = {
        "width": img_w_px,
        "height": img_h_px,
        "fit": ft.BoxFit.FILL,
    }

    # Las imágenes ahora tienen timestamp en el nombre del archivo (pagina_0000_timestamp.png)
    # No es necesario añadir query parameter adicional
    if img_src:
        imagen_args["src"] = img_src
    elif img_base64:
        imagen_args["src_base64"] = img_base64
    else:
        # Fallback si no hay imagen
        imagen_args["src_base64"] = ""  # O placeholder

    imagen = ft.Image(**imagen_args)

    return ft.Container(
        width=celda_w_px,
        height=celda_h_px,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        # bgcolor=ft.Colors.GREEN_400,  # ✅ Fondo naranja para ver las celdas
        content=ft.Stack(
            [
                ft.Container(
                    width=celda_w_px,
                    height=celda_h_px,
                    bgcolor=ft.Colors.BLUE_100,  # ✅ Fondo naranja para ver la sangre o fondo de celdas
                ),
                ft.Container(
                    content=imagen,
                    left=offset_total_x,
                    top=offset_total_y,
                ),
            ]
        ),
    )


# Variables globales para controles y funciones expuestas por impo_ui
# Inicializadas a None; se asignarán a los controles reales cuando se cree la ventana.
textfield_ancho = None
textfield_alto = None
textfield_sangre = None
textfield_medianil = None

texto_archivo = None
texto_paginas = None
texto_paginas_requeridas = None
texto_validacion = None

dropdown_copias = None
checkbox_xerox = None
dropdown_doble_cara = None
dropdown_rotacion = None

file_picker = None
boton_cargar_pdf = None
boton_crear = None
boton_cancelar = None

progress_bar = None
texto_contador_pliegos = None
progress_row = None

# Control opcional para tipos de corte (si existe en versiones antiguas)
dropdown_tipo_corte = None

dropdown_tamanos_general = None
main_col = None
right_column = None

# Variables para funciones/utilidades (expuestas para que la app pueda reasignarlas si es necesario)
ref_mostrar_alert_dialog = None
ref_crear_dialogo_tamano_final = None

boton_crear_tamaño_pliego = None

# Reusar utilidades definidas en app_ui_items (mostrar_snackbar, mostrar_alert_dialog, crear_dropdown_tamanos, boton_abrir_dialogo_tamano_final, safe_update_dropdown, registrar_listener_tamanos, unregistrar_listener_tamanos)
try:
    from app_ui_items import mostrar_snackbar, mostrar_alert_dialog
except Exception:
    # Stubs ligeros si no se pueden importar desde app_ui_items
    def mostrar_snackbar(page, texto, _bgcolor=None, duracion=3000):
        try:
            page.show_dialog(ft.SnackBar(ft.Text(texto, color=SNACKBAR_COLOR_TEXTO), bgcolor=_bgcolor or SNACKBAR_COLOR_FONDO))
        except Exception:
            pass

    def mostrar_alert_dialog(page, exito, ruta_pdf=None, error_msg=None):
        try:
            if exito:
                dialog = ft.AlertDialog(
                    title=ft.Text(t("PDF guardado correctamente")),
                    content=ft.Text(str(ruta_pdf)),
                    bgcolor=FONDO_ALERT_DIALOG,
                )
            else:
                dialog = ft.AlertDialog(
                    title=ft.Text(t("Error")),
                    content=ft.Text(str(error_msg)),
                    bgcolor=FONDO_ALERT_DIALOG,
                )
            page.show_dialog(dialog)
        except Exception:
            pass

    def notificar_actualizacion_tamanos(tamanos):
        """Notifica a los listeners registrados con la lista de tamaños actualizada."""
        try:
            for f in list(_tamanos_listeners):
                try:
                    f(tamanos)
                except Exception:
                    pass
        except Exception:
            pass

    def crear_dialogo_tamano_final(page, ruta_json_tamanos="tamanos_pliego.json"):
        """Diálogo para crear/guardar un nuevo tamaño en `ruta_json_tamanos`.
        Al guardar, actualiza el archivo JSON y notifica listeners registrados.
        """
        try:
            # Trace de pila para depuración: imprimir quién llama cuando DEBUG activo
            if DEBUG_IMPO_UI:
                try:
                    import traceback

                    print(
                        "[IMPO_UI DEBUG] abrir crear_dialogo_tamano_final llamado. Stack:"
                    )
                    traceback.print_stack(limit=10)
                except Exception:
                    pass
            # Campos - usar unidad actual para los labels
            current_unit = _estado_impo_ui.get("unit", _initial_unit_pref) or "mm"
            unit_label = get_unit_abbr(current_unit)

            textfield_ancho_local = ft.TextField(
                label=t("Ancho ({0})").format(unit_label),
                value="",
                width=90,
                height=40,
                bgcolor=FONDO_TEXTFIELDS_COLOR,
                border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)),
                color=TEXTOS_FASE_1_COLOR,
                text_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
                label_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
                content_padding=ft.Padding(8, 0, 0, 0),
            )
            textfield_alto_local = ft.TextField(
                label=t("Alto ({0})").format(unit_label),
                value="",
                width=90,
                height=40,
                bgcolor=FONDO_TEXTFIELDS_COLOR,
                border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)),
                color=TEXTOS_FASE_1_COLOR,
                text_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
                label_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
                content_padding=ft.Padding(8, 0, 0, 0),
            )
            texto_feedback = ft.Text(
                "", size=16, color="red", visible=True, text_align=ft.TextAlign.CENTER
            )

            # Cargar lista actual
            try:
                if os.path.exists(ruta_json_tamanos):
                    with open(ruta_json_tamanos, "r") as f:
                        tamanos = json.load(f)
                else:
                    tamanos = [{"nombre": "Tamaño pliego", "ancho": "", "alto": ""}]
            except Exception:
                tamanos = [{"nombre": "Tamaño pliego", "ancho": "", "alto": ""}]

            def generar_nombre():
                try:
                    a = float(textfield_ancho_local.value)
                    h = float(textfield_alto_local.value)
                    return f"{int(a)} x {int(h)}"
                except Exception:
                    return ""

            def guardar_tamano(e):
                nombre = generar_nombre()
                try:
                    ancho_input = float(textfield_ancho_local.value)
                    alto_input = float(textfield_alto_local.value)

                    # Convertir de unidad actual a mm para guardar
                    current_unit = (
                        _estado_impo_ui.get("unit", _initial_unit_pref) or "mm"
                    )
                    ancho = convert_to_mm(ancho_input, current_unit)
                    alto = convert_to_mm(alto_input, current_unit)

                    if ancho <= 0 or alto <= 0:
                        raise ValueError
                except Exception:
                    texto_feedback.value = "Introduce valores válidos (números > 0)."
                    texto_feedback.color = "red"
                    texto_feedback.visible = True
                    try:
                        texto_feedback.update()
                    except Exception:
                        pass
                    return

                # Comprobar duplicado
                existe = any(
                    float(t.get("ancho") or 0) == ancho
                    and float(t.get("alto") or 0) == alto
                    for t in tamanos
                )
                if existe:
                    texto_feedback.value = f"El tamaño {nombre} ya existe."
                    texto_feedback.color = "orange"
                    texto_feedback.visible = True
                    try:
                        texto_feedback.update()
                    except Exception:
                        pass
                    return

                nuevo = {"nombre": nombre, "ancho": ancho, "alto": alto}
                registro_0 = (
                    tamanos[0]
                    if tamanos
                    else {"nombre": "Tamaño", "ancho": "", "alto": ""}
                )
                otros = tamanos[1:] if len(tamanos) > 1 else []
                # Insertar ordenado por ancho ascendente
                pos = len(otros)
                for i, t in enumerate(otros):
                    try:
                        if float(nuevo["ancho"]) < float(t.get("ancho") or 0):
                            pos = i
                            break
                    except Exception:
                        continue
                otros.insert(pos, nuevo)
                tamanos_ordenados = [registro_0] + otros
                try:
                    with open(ruta_json_tamanos, "w") as f:
                        json.dump(tamanos_ordenados, f, indent=2)
                    texto_feedback.value = f"Guardado: {nombre}"
                    texto_feedback.color = "green"
                    texto_feedback.visible = True
                    try:
                        texto_feedback.update()
                    except Exception:
                        pass
                    # Notificar listeners
                    try:
                        notificar_actualizacion_tamanos(tamanos_ordenados)
                    except Exception:
                        pass
                except Exception:
                    texto_feedback.value = "Error guardando el tamaño."
                    texto_feedback.color = "red"
                    texto_feedback.visible = True
                    try:
                        texto_feedback.update()
                    except Exception:
                        pass

            def cerrar(e):
                try:
                    page.pop_dialog()
                except Exception:
                    pass

            # Diseño copiado exactamente desde app_ui_items.py para mantener consistencia visual
            dialogo = ft.AlertDialog(
                modal=True,
                bgcolor=FONDO_ALERT_DIALOG,
                shape=ft.RoundedRectangleBorder(radius=10),
                content=ft.Container(
                    content=ft.Column(
                        [
                            ft.Container(
                                ft.Text(
                                    t("Tamaño de pliego"),
                                    weight=ft.FontWeight.BOLD,
                                    size=18,
                                    color=TEXTOS_FASE_1_COLOR,
                                ),
                                alignment=ft.Alignment.CENTER,
                                width=340,
                            ),
                            ft.Container(height=10),
                            ft.Container(
                                ft.Row(
                                    [textfield_ancho_local, textfield_alto_local],
                                    spacing=16,
                                    alignment=ft.MainAxisAlignment.CENTER,
                                ),
                                alignment=ft.Alignment.CENTER,
                                width=380,
                            ),
                            ft.Container(height=8),
                            ft.Container(
                                texto_feedback,
                                alignment=ft.Alignment.CENTER,
                                width=380,
                                height=32,
                            ),
                            ft.Row(
                                [
                                    ft.Button(
                                        "Guardar",
                                        on_click=guardar_tamano,
                                        width=110,
                                        bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                                        style=ft.ButtonStyle(
                                            color={
                                                ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                                                "hovered": BOTONES_GENERICOS_HOVER_COLOR,
                                            },
                                            overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                                            padding=ft.Padding(0, 0, 0, 0),
                                            shape=ft.RoundedRectangleBorder(radius=10),
                                        ),
                                    ),
                                    ft.Button(
                                        "Cerrar",
                                        on_click=cerrar,
                                        width=110,
                                        bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                                        style=ft.ButtonStyle(
                                            color={
                                                ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                                                "hovered": BOTONES_GENERICOS_HOVER_COLOR,
                                            },
                                            overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                                            padding=ft.Padding(0, 0, 0, 0),
                                            shape=ft.RoundedRectangleBorder(radius=10),
                                        ),
                                    ),
                                ],
                                spacing=18,
                                alignment=ft.MainAxisAlignment.CENTER,
                            ),
                        ],
                        spacing=20,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    bgcolor=FONDO_ALERT_DIALOG,
                    width=340,
                    height=380,
                    border_radius=10,
                    padding=ft.Padding(18, 18, 18, 18),
                    margin=ft.Margin(0, 0, 0, 0),
                ),
                content_padding=ft.Padding(0, 0, 0, 0),
            )
            page.show_dialog(dialogo)
        except Exception:
            try:
                mostrar_snackbar(
                    page,
                    t("Error abriendo diálogo de tamaños"),
                    SNACKBAR_COLOR_ERROR,
                    3000,
                )
            except Exception:
                pass

    def boton_abrir_dialogo_tamano_final(page, ruta_json_tamanos="tamanos_pliego.json"):
        def _on_click(e):
            try:
                if DEBUG_IMPO_UI:
                    try:
                        print(
                            f"[IMPO_UI DEBUG] boton_abrir_dialogo_tamano_final pulsado, ruta_json={ruta_json_tamanos}"
                        )
                    except Exception:
                        pass
                try:
                    mostrar_snackbar(
                        page,
                        t("Abriendo diálogo de tamaños: {0}").format(ruta_json_tamanos),
                        SNACKBAR_COLOR_FONDO,
                        1200,
                    )
                except Exception:
                    pass
                crear_dialogo_tamano_final(page, ruta_json_tamanos)
            except Exception:
                pass

        boton_crear_tamaño_pliego = ft.Button(
            "Crear tamaño final",
            on_click=_on_click,
            width=180,
            visible=True,
            bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
            style=ft.ButtonStyle(
                color={
                    ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                    "hovered": BOTONES_GENERICOS_HOVER_COLOR,
                },
                overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                padding=ft.Padding(0, 0, 0, 0),
                shape=ft.RoundedRectangleBorder(radius=10),
            ),
        )

        return boton_crear_tamaño_pliego

    def safe_update_dropdown(dropdown, opciones, nuevo_valor=None):
        try:
            dropdown.options = opciones
            if nuevo_valor is not None:
                dropdown.value = nuevo_valor
            dropdown.update()
        except Exception:
            pass

    _tamanos_listeners = []

    def registrar_listener_tamanos(func):
        try:
            if callable(func) and func not in _tamanos_listeners:
                _tamanos_listeners.append(func)
        except Exception:
            pass

    def unregistrar_listener_tamanos(func):
        try:
            if func in _tamanos_listeners:
                _tamanos_listeners.remove(func)
        except Exception:
            pass

    # Nota: Refs globales ya declaradas al inicio del módulo.

    # Asignar refs de funciones a las implementaciones disponibles (stubs)
    try:
        # Evitar depender de ft.Ref: asignar directamente la función al nombre global
        ref_mostrar_alert_dialog = mostrar_alert_dialog
    except Exception:
        try:
            ref_mostrar_alert_dialog = mostrar_alert_dialog
        except Exception:
            pass
    try:
        ref_crear_dialogo_tamano_final = crear_dialogo_tamano_final
    except Exception:
        try:
            ref_crear_dialogo_tamano_final = crear_dialogo_tamano_final
        except Exception:
            pass


def abrir_dialogo_calles(
    page, textfield_grid_cols, textfield_grid_rows, actualizar_trazado_func
):
    """
    Abre un diálogo modal para editar los valores de las calles de forma visual.
    Todas las celdas tienen el mismo tamaño y los TextFields están alineados con las calles.
    """
    print(f"[DEBUG DIALOGO CALLES] 🔍 CALLES_L global AL ABRIR diálogo: {CALLES_L}")
    try:
        cols = int(textfield_grid_cols.value)
        rows = int(textfield_grid_rows.value)
        # USAR GLOBAL DIRECTAMENTE
        calles_list = list(CALLES_L)  # Copia para no modificar global hasta guardar
        print(
            f"[DEBUG DIALOGO CALLES] 🔍 calles_list (copia de CALLES_L): {calles_list}"
        )
    except (ValueError, TypeError):
        # Si los valores no son válidos, no abre el diálogo
        mostrar_snackbar(page, t("Valores de grid o calles no válidos."), "red")
        return

    num_v_calles = max(0, cols - 1)
    num_h_calles = max(0, rows - 1)

    # Asegurarse de que la lista de calles tenga la longitud correcta
    expected_len = num_v_calles + num_h_calles
    while len(calles_list) < expected_len:
        calles_list.append(0.0)
    calles_list = calles_list[:expected_len]

    v_calles_values = calles_list[:num_v_calles]
    h_calles_values = calles_list[num_v_calles:]

    vertical_street_fields = []
    horizontal_street_fields = []

    # Exponer estas estructuras al ámbito global para que otras partes (ej. update_units)
    # puedan leer/actualizar los valores cuando el diálogo está abierto.
    try:
        globals()["vertical_street_fields"] = vertical_street_fields
        globals()["horizontal_street_fields"] = horizontal_street_fields
        globals()["v_calles_values"] = v_calles_values
        globals()["h_calles_values"] = h_calles_values
    except Exception:
        pass

    # Estado para almacenar el TextField activo (último editado)
    active_field = {"tf": None}

    def set_active_field(tf):
        try:
            active_field["tf"] = tf
        except Exception:
            pass

    # ========== CONFIGURACIÓN DE TAMAÑOS Y ESPACIADOS ==========
    # Tamaño uniforme para todas las celdas
    CELL_SIZE = 40  # Tamaño medio para buena visibilidad
    # Tamaño de los TextFields de calles: ancho y alto por separado
    STREET_TF_WIDTH = 72  # Ancho de los TextFields (6 caracteres: "100.00")
    STREET_TF_HEIGHT = 28  # Alto de los TextFields (horizontales)
    # Espaciado entre TextFields izquierdos y las celdas (ajustar aquí para más/menos espacio)
    SPACING_TF_TO_CELLS = 8  # Espaciado horizontal (izquierda)
    # Espaciado entre TextFields superiores y las celdas (ajustar aquí para más/menos espacio)
    SPACING_TF_TO_CELLS_VERTICAL = 8  # Espaciado vertical (arriba)
    # ===========================================================

    # ========== CÁLCULO DINÁMICO DEL TAMAÑO DEL GRID ==========
    # Calcular el ancho total del grid
    # Ancho = STREET_TF_WIDTH (esquina) + SPACING + (CELL_SIZE * cols) + (STREET_TF_WIDTH * (cols-1))
    grid_width = (
        STREET_TF_WIDTH
        + SPACING_TF_TO_CELLS
        + (CELL_SIZE * cols)
        + (STREET_TF_WIDTH * num_v_calles)
    )

    # Calcular el alto total del grid
    # Alto = STREET_TF_HEIGHT (fila superior de TFs) + SPACING_VERTICAL + (CELL_SIZE * rows) + (CELL_SIZE * (rows-1) para calles horizontales)
    # Añadimos la fila de TFs superiores solo si hay calles verticales
    tf_row_height = STREET_TF_HEIGHT if num_v_calles > 0 else 0
    vertical_spacing = SPACING_TF_TO_CELLS_VERTICAL if num_v_calles > 0 else 0
    # Las filas de calles horizontales ahora tienen altura CELL_SIZE (para centrar los TextFields)
    grid_height = (
        tf_row_height
        + vertical_spacing
        + (CELL_SIZE * rows)
        + (CELL_SIZE * num_h_calles)
    )

    # Añadir espacio para controles y botones
    CONTROL_ROW_HEIGHT = 50  # Altura del botón superior
    ACTIONS_HEIGHT = 60  # Altura de los botones inferiores
    PADDING_V = 36  # Padding vertical adicional
    PADDING_H = 64  # Padding horizontal adicional

    # Tamaño total del contenedor del diálogo
    dialog_width = grid_width + PADDING_H
    dialog_height = grid_height + CONTROL_ROW_HEIGHT + ACTIONS_HEIGHT + PADDING_V

    # Limitar tamaños máximos para que nunca exceda el tamaño de la ventana.
    # El alto se capa al 70% de la página (diálogo dinámico según calles, con scroll interno).
    if page.width and page.height:
        # Dejar un pequeño margen (50px en cada lado)
        MAX_DIALOG_WIDTH = int(page.width - 100)
        MAX_DIALOG_HEIGHT = int(min(page.height - 100, page.height * 0.7))
    else:
        # Valores por defecto conservadores si no hay información
        MAX_DIALOG_WIDTH = 800
        MAX_DIALOG_HEIGHT = 600

    # Ajustar si excede los límites
    needs_scroll = False
    if dialog_width > MAX_DIALOG_WIDTH:
        dialog_width = MAX_DIALOG_WIDTH
        needs_scroll = True
    if dialog_height > MAX_DIALOG_HEIGHT:
        dialog_height = MAX_DIALOG_HEIGHT
        needs_scroll = True

    print(
        f"[DEBUG DIALOG] Grid: {cols}x{rows}, Grid size: {grid_width}x{grid_height}px, Dialog size: {dialog_width}x{dialog_height}px, Scroll: {needs_scroll}"
    )
    # ===========================================================

    dialog_content = ft.Column(
        scroll=ft.ScrollMode.ADAPTIVE,
        spacing=0,
        tight=True,
    )

    # Fila de control superior: botón centrado para copiar el valor del campo activo a todas las calles

    control_row = ft.Row(alignment=ft.MainAxisAlignment.CENTER, spacing=5)
    copiar_btn = ft.Button(
        t("Aplicar a todos"),
        on_click=lambda e: None,
        width=120,
        bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
        style=ft.ButtonStyle(
            color={
                ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                "hovered": BOTONES_GENERICOS_HOVER_COLOR,
            },
            overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
            padding=ft.Padding(0, 0, 0, 0),
            shape=ft.RoundedRectangleBorder(radius=10),
        ),
    )
    control_row.controls.append(
        ft.Text(
            t("Separación"),
            size=16,
            weight=ft.FontWeight.BOLD,
            color=TEXTOS_FASE_1_COLOR,
            text_align=ft.TextAlign.LEFT,
        )
    )
    control_row.controls.append(ft.Container(expand=True))
    control_row.controls.append(copiar_btn)
    dialog_content.controls.append(control_row)
    dialog_content.controls.append(ft.Container(height=20))

    # Construir el grid completo con celdas y calles
    grid_layout = ft.Column(spacing=0)

    # Fila superior con TextFields de calles verticales y separadores (celdas)
    # Determinar unidad actual para mostrar valores convertidos en la UI
    try:
        current_unit = _estado_impo_ui.get("unit", _initial_unit_pref) or "mm"
    except Exception:
        current_unit = _initial_unit_pref or "mm"

    if num_v_calles > 0:
        top_tf_row = ft.Row(spacing=0, alignment=ft.MainAxisAlignment.START)
        # Esquina vacía
        top_tf_row.controls.append(
            ft.Container(width=STREET_TF_WIDTH, height=STREET_TF_HEIGHT)
        )
        # Espaciado después de la esquina (para alinear con otras filas)
        top_tf_row.controls.append(
            ft.Container(width=SPACING_TF_TO_CELLS, height=STREET_TF_HEIGHT)
        )

        # Intercalar separadores (celdas) con TextFields de calles verticales
        for col_idx in range(num_v_calles):
            # Separador (celda)
            top_tf_row.controls.append(
                ft.Container(
                    width=CELL_SIZE,
                    height=STREET_TF_HEIGHT,
                    alignment=ft.Alignment.CENTER,
                )
            )

            # TextField de calle vertical
            # Mostrar el valor convertido desde mm a la unidad actual (solo presentación)
            try:
                displayed_v = f"{convert_from_mm(float(v_calles_values[col_idx]), current_unit):.2f}"
            except Exception:
                displayed_v = str(v_calles_values[col_idx])

            tf = ft.TextField(
                value=displayed_v,
                width=STREET_TF_WIDTH,
                height=STREET_TF_HEIGHT,
                text_align=ft.TextAlign.CENTER,
                content_padding=2,
                # Permitir sólo dígitos y punto (no coma). Escapar el punto en el patrón.
                input_filter=ft.InputFilter(
                    allow=True, regex_string=r"[0-9\\.]", replacement_string=""
                ),
                on_change=lambda e, t=None: (
                    set_active_field(e.control) if hasattr(e, "control") else None
                ),
            )
            vertical_street_fields.append(tf)
            top_tf_row.controls.append(tf)

        # Última celda separadora
        top_tf_row.controls.append(
            ft.Container(
                width=CELL_SIZE, height=STREET_TF_HEIGHT, alignment=ft.Alignment.CENTER
            )
        )

        scrollable_top_tf_row = ft.Row([top_tf_row], scroll=ft.ScrollMode.ADAPTIVE)
        grid_layout.controls.append(scrollable_top_tf_row)

        # Fila de espaciado vertical entre TextFields superiores y celdas
        if SPACING_TF_TO_CELLS_VERTICAL > 0:
            spacing_row = ft.Container(height=SPACING_TF_TO_CELLS_VERTICAL)
            grid_layout.controls.append(spacing_row)

    # Fila de celdas superiores con calles verticales visuales
    top_cells_row = ft.Row(spacing=0, alignment=ft.MainAxisAlignment.START)
    # Esquina vacía
    top_cells_row.controls.append(ft.Container(width=STREET_TF_WIDTH, height=CELL_SIZE))
    # Espaciado entre esquina y celdas (para alinear con otras filas)
    top_cells_row.controls.append(
        ft.Container(width=SPACING_TF_TO_CELLS, height=CELL_SIZE)
    )

    # Intercalar celdas con calles verticales visuales
    for col_idx in range(cols):
        # Celda
        top_cells_row.controls.append(
            ft.Container(
                width=CELL_SIZE,
                height=CELL_SIZE,
                border=ft.Border.all(1, "grey20"),
                alignment=ft.Alignment.CENTER,
            )
        )

        # Calle vertical visual (si no es la última columna)
        if col_idx < cols - 1:
            top_cells_row.controls.append(
                ft.Container(
                    width=STREET_TF_WIDTH,
                    height=CELL_SIZE,
                    alignment=ft.Alignment.CENTER,
                )
            )

    scrollable_top_cells_row = ft.Row([top_cells_row], scroll=ft.ScrollMode.ADAPTIVE)
    grid_layout.controls.append(scrollable_top_cells_row)

    # Filas del grid: intercalar filas de calles horizontales con filas de celdas
    for row_idx in range(rows - 1):  # rows - 1 porque la primera fila ya está arriba
        # Fila de calle horizontal
        if row_idx < num_h_calles:
            h_street_row = ft.Row(spacing=0, alignment=ft.MainAxisAlignment.START)

            # TextField de calle horizontal
            # Mostrar el valor convertido desde mm a la unidad actual (solo presentación)
            try:
                displayed_h = f"{convert_from_mm(float(h_calles_values[row_idx]), current_unit):.2f}"
            except Exception:
                displayed_h = str(h_calles_values[row_idx])

            tf = ft.TextField(
                value=displayed_h,
                width=STREET_TF_WIDTH,
                height=STREET_TF_HEIGHT,
                text_align=ft.TextAlign.CENTER,
                content_padding=2,
                # Permitir sólo dígitos y punto (no coma). Escapar el punto en el patrón.
                input_filter=ft.InputFilter(
                    allow=True, regex_string=r"[0-9\\.]", replacement_string=""
                ),
                on_change=lambda e, t=None: (
                    set_active_field(e.control) if hasattr(e, "control") else None
                ),
            )
            horizontal_street_fields.append(tf)

            # Calcular espaciado vertical para centrar el TextField
            # La fila de calle tiene altura CELL_SIZE, el TextField tiene STREET_TF_HEIGHT
            vertical_spacing = (CELL_SIZE - STREET_TF_HEIGHT) / 2

            # Contenedor con espaciadores verticales para centrar el TextField
            h_street_row.controls.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Container(
                                height=vertical_spacing
                            ),  # Espaciador superior
                            tf,
                            ft.Container(
                                height=vertical_spacing
                            ),  # Espaciador inferior
                        ],
                        spacing=0,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    width=STREET_TF_WIDTH,
                    height=CELL_SIZE,  # Altura de la celda para alinearse con las celdas
                )
            )

            # Espaciado entre TextField y celdas
            h_street_row.controls.append(
                ft.Container(width=SPACING_TF_TO_CELLS, height=STREET_TF_HEIGHT)
            )

            # Celdas y calles verticales intercaladas en la fila de calle horizontal
            for col_idx in range(cols):
                # Representación visual de la calle horizontal
                h_street_row.controls.append(
                    ft.Container(
                        width=CELL_SIZE,
                        height=STREET_TF_HEIGHT,
                        alignment=ft.Alignment.CENTER,
                    )
                )

                # Calle vertical (si no es la última columna)
                if col_idx < cols - 1:
                    # Intersección de calles
                    h_street_row.controls.append(
                        ft.Container(
                            width=STREET_TF_WIDTH,
                            height=STREET_TF_HEIGHT,
                            alignment=ft.Alignment.CENTER,
                        )
                    )

            scrollable_h_street_row = ft.Row(
                [h_street_row], scroll=ft.ScrollMode.ADAPTIVE
            )
            grid_layout.controls.append(scrollable_h_street_row)

        # Fila de celdas
        cell_row = ft.Row(spacing=0, alignment=ft.MainAxisAlignment.START)
        # Espaciador a la izquierda
        cell_row.controls.append(ft.Container(width=STREET_TF_WIDTH, height=CELL_SIZE))
        # Espaciado entre espaciador y celdas (para alinear con las filas de calles)
        cell_row.controls.append(
            ft.Container(width=SPACING_TF_TO_CELLS, height=CELL_SIZE)
        )

        # Intercalar celdas con calles verticales
        for col_idx in range(cols):
            # Celda
            cell_row.controls.append(
                ft.Container(
                    width=CELL_SIZE,
                    height=CELL_SIZE,
                    border=ft.Border.all(1, "grey20"),
                    alignment=ft.Alignment.CENTER,
                )
            )

            # Calle vertical (si no es la última columna)
            if col_idx < cols - 1:
                cell_row.controls.append(
                    ft.Container(
                        width=STREET_TF_WIDTH,
                        height=CELL_SIZE,
                        alignment=ft.Alignment.CENTER,
                    )
                )

        scrollable_cell_row = ft.Row([cell_row], scroll=ft.ScrollMode.ADAPTIVE)
        grid_layout.controls.append(scrollable_cell_row)

    dialog_content.controls.append(
        ft.Row(
            [ft.Container(grid_layout)],
            alignment=ft.MainAxisAlignment.CENTER,
        )
    )

    def guardar_calles(e):
        # Si algún TextField fue borrado, mantener el valor previo usado para inicializar
        nuevas_v_calles = []
        nuevas_h_calles = []

        try:
            # Unidad actual (los TextFields muestran valores en esta unidad)
            try:
                unit_for_parse = _estado_impo_ui.get("unit", _initial_unit_pref) or "mm"
            except Exception:
                unit_for_parse = _initial_unit_pref or "mm"

            for idx, tf in enumerate(vertical_street_fields):
                val = tf.value
                if val is None or str(val).strip() == "":
                    # usar el valor original (ya en mm) mostrado al abrir el diálogo
                    nuevas_v_calles.append(float(v_calles_values[idx]))
                else:
                    # Convertir desde la unidad mostrada a mm antes de guardar internamente
                    try:
                        mm_val = convert_to_mm(
                            str(val).strip().replace(",", "."), unit_for_parse
                        )
                        nuevas_v_calles.append(float(mm_val))
                    except Exception:
                        nuevas_v_calles.append(float(v_calles_values[idx]))

            for idx, tf in enumerate(horizontal_street_fields):
                val = tf.value
                if val is None or str(val).strip() == "":
                    nuevas_h_calles.append(float(h_calles_values[idx]))
                else:
                    try:
                        mm_val = convert_to_mm(
                            str(val).strip().replace(",", "."), unit_for_parse
                        )
                        nuevas_h_calles.append(float(mm_val))
                    except Exception:
                        nuevas_h_calles.append(float(h_calles_values[idx]))

            nueva_lista_calles = nuevas_v_calles + nuevas_h_calles

            # ACTUALIZAR GLOBAL DIRECTAMENTE
            global CALLES_L
            CALLES_L = nueva_lista_calles

            # Guardar estado y marcar como modificado
            guardar_estado_impo_ui()
            if _mark_modified_callback:
                _mark_modified_callback()

            actualizar_trazado_func(None)
            page.pop_dialog()
        except ValueError:
            mostrar_snackbar(page, t("Todos los valores deben ser números."), "red")
            return

    # Implementar la acción del botón copiar: copia el valor del campo activo a todos los TextFields
    def copiar_activo_a_todas(e):
        try:
            tf_act = active_field.get("tf")
            if not tf_act:
                mostrar_snackbar(
                    page,
                    t("Edita o cambia cualquier campo para marcarlo como activo."),
                    "orange",
                )
                return
            val = tf_act.value
            # Asignar a todas las calles
            for tf in vertical_street_fields:
                tf.value = val
                try:
                    tf.update()
                except Exception:
                    pass
            for tf in horizontal_street_fields:
                tf.value = val
                try:
                    tf.update()
                except Exception:
                    pass
            mostrar_snackbar(page, t("Valor copiado a todas las calles."), "green")
        except Exception:
            mostrar_snackbar(page, t("Error al copiar el valor."), "red")

    # Conectar el botón al handler
    try:
        copiar_btn.on_click = copiar_activo_a_todas
    except Exception:
        pass

    def cerrar_dialogo(e):
        page.pop_dialog()

    dialogo = ft.AlertDialog(
        modal=True,
        content=ft.Container(
            content=dialog_content,
            width=dialog_width,
            height=dialog_height - ACTIONS_HEIGHT,
            padding=ft.Padding(0, 0, 0, 20),
        ),
        actions=[
            ft.Button(
                t("Cancelar"),
                width=110,
                bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                on_click=cerrar_dialogo,
                style=ft.ButtonStyle(
                    color={
                        ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                        "hovered": BOTONES_GENERICOS_HOVER_COLOR,
                    },
                    overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                    padding=ft.Padding(0, 0, 0, 0),
                    shape=ft.RoundedRectangleBorder(radius=10),
                ),
            ),
            ft.Button(
                t("Aceptar"),
                width=110,
                bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                on_click=guardar_calles,
                style=ft.ButtonStyle(
                    color={
                        ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                        "hovered": BOTONES_GENERICOS_HOVER_COLOR,
                    },
                    overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                    padding=ft.Padding(0, 0, 0, 0),
                    shape=ft.RoundedRectangleBorder(radius=10),
                ),
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.CENTER,
        content_padding=ft.Padding(10, 10, 10, 0),
        actions_padding=ft.Padding(0, 0, 0, 10),
        bgcolor=FONDO_ALERT_DIALOG,
    )

    page.show_dialog(dialogo)


# ═══════════════════════════════════════════════════════════════════════════════
# SISTEMA DE PREFERENCIAS DE IMPOSICIÓN
# ═══════════════════════════════════════════════════════════════════════════════


def obtener_ruta_preferencias():
    """
    Obtiene la ruta del archivo de preferencias de imposición.

    Returns:
        str: Ruta completa al archivo JSON de preferencias
    """
    print("[PREF DEBUG] obtener_ruta_preferencias() llamada")
    try:
        # Preferir carpeta de configuración persistente de la app (TalNumStack)
        try:
            from talnum_preferences import get_config_dir

            config_dir = get_config_dir()
            ruta = os.path.join(str(config_dir), "preferencias_imposicion.json")
            print(f"[PREF DEBUG] Ruta preferencias persistente: {ruta}")
            return ruta
        except Exception:
            # Fallback: usar el directorio temporal de sesión (legacy)
            from pdf_ordenado_ui import obtener_directorio_temp_sesion

            directorio_temp = obtener_directorio_temp_sesion()
            ruta = os.path.join(directorio_temp, "preferencias_imposicion.json")
            print(f"[PREF DEBUG] Ruta preferencias (fallback temp): {ruta}")
            return ruta
    except Exception as e:
        print(f"[ERROR PREF] No se pudo obtener ruta de preferencias: {e}")
        import traceback

        traceback.print_exc()
        return None


def guardar_preferencias_imposicion(datos_seleccionados):
    """
    Guarda las preferencias de imposición en un archivo JSON.

    Args:
        datos_seleccionados: Dict con las claves a guardar y sus valores
        Ejemplo: {
            "cruces": True,
            "marcas_texto": True,
            "checks_trazado": True
        }

    Returns:
        bool: True si se guardó correctamente, False en caso contrario
    """
    global LONGITUD_CRUZ_MM, GROSOR_CRUZ_PT, OFFSET_CRUZ_MM, AUTO_SANGRE_OFFSET_CRUZ
    global OFFSET_SEGURIDAD_MM, LONGITUD_BRAZO_MAX_MM  # ✨ NUEVO
    global MARCA_TEXTO_CONTENIDO, MARCA_TEXTO_POS_SUP_IZQ, MARCA_TEXTO_POS_SUP_DER
    global MARCA_TEXTO_POS_INF_IZQ, MARCA_TEXTO_POS_INF_DER, MARCA_TEXTO_POS_CENTRO_SUP
    global MARCA_TEXTO_POS_CENTRO_INF, MARCA_TEXTO_POS_CENTRO_LAT_IZQ, MARCA_TEXTO_POS_CENTRO_LAT_DER
    global MARCA_TEXTO_ROTACION, MARCA_TEXTO_FAMILIA, MARCA_TEXTO_TIPO, MARCA_TEXTO_CUERPO
    global MARCA_TEXTO_COLOR, MARCA_TEXTO_OFFSET_H_MM, MARCA_TEXTO_OFFSET_V_MM

    print("[PREF DEBUG] guardar_preferencias_imposicion() llamada")
    print(f"[PREF DEBUG] datos_seleccionados: {datos_seleccionados}")

    try:
        ruta_archivo = obtener_ruta_preferencias()
        if not ruta_archivo:
            print("[ERROR PREF] No se pudo obtener la ruta del archivo de preferencias")
            return False

        print(f"[PREF DEBUG] Ruta archivo obtenida: {ruta_archivo}")
        preferencias = {}

        # Guardar datos de cruces si está seleccionado
        if datos_seleccionados.get("cruces", False):
            preferencias["cruces"] = {
                "longitud_mm": float(LONGITUD_CRUZ_MM),
                "grosor_pt": float(GROSOR_CRUZ_PT),
                "offset_mm": float(OFFSET_CRUZ_MM),
                "auto_sangre": bool(AUTO_SANGRE_OFFSET_CRUZ),
                "offset_seguridad_mm": float(OFFSET_SEGURIDAD_MM),  # ✨ NUEVO
                "longitud_brazo_max_mm": float(LONGITUD_BRAZO_MAX_MM),  # ✨ NUEVO
            }
            print(f"[PREF] Guardando cruces: {preferencias['cruces']}")

        # Guardar datos de marcas de texto si está seleccionado
        if datos_seleccionados.get("marcas_texto", False):
            # Convertir color a string hexadecimal si es necesario
            color_str = MARCA_TEXTO_COLOR
            if hasattr(MARCA_TEXTO_COLOR, "value"):
                color_str = MARCA_TEXTO_COLOR.value
            elif not isinstance(MARCA_TEXTO_COLOR, str):
                color_str = str(MARCA_TEXTO_COLOR)

            preferencias["marcas_texto"] = {
                "contenido": str(MARCA_TEXTO_CONTENIDO),
                "posiciones": {
                    "sup_izq": bool(MARCA_TEXTO_POS_SUP_IZQ),
                    "sup_der": bool(MARCA_TEXTO_POS_SUP_DER),
                    "inf_izq": bool(MARCA_TEXTO_POS_INF_IZQ),
                    "inf_der": bool(MARCA_TEXTO_POS_INF_DER),
                    "centro_sup": bool(MARCA_TEXTO_POS_CENTRO_SUP),
                    "centro_inf": bool(MARCA_TEXTO_POS_CENTRO_INF),
                    "centro_lat_izq": bool(MARCA_TEXTO_POS_CENTRO_LAT_IZQ),
                    "centro_lat_der": bool(MARCA_TEXTO_POS_CENTRO_LAT_DER),
                },
                "rotacion": int(MARCA_TEXTO_ROTACION),
                "familia": str(MARCA_TEXTO_FAMILIA),
                "tipo": str(MARCA_TEXTO_TIPO),
                "cuerpo": int(MARCA_TEXTO_CUERPO),
                "color": color_str,
                "offset_h_mm": float(MARCA_TEXTO_OFFSET_H_MM),
                "offset_v_mm": float(MARCA_TEXTO_OFFSET_V_MM),
            }
            print(f"[PREF] Guardando marcas de texto")

        # Guardar estados de checks de trazado si está seleccionado
        if datos_seleccionados.get("checks_trazado", False):
            preferencias["checks_trazado"] = {
                "cruces_y_marcas": bool(
                    datos_seleccionados.get("check_cruces_y_marcas", False)
                ),
                "lineas_corte": bool(
                    datos_seleccionados.get("check_lineas_corte", False)
                ),
                "marcas_texto": bool(
                    datos_seleccionados.get("check_marcas_texto_estado", False)
                ),
                "linea_exterior": bool(
                    datos_seleccionados.get("check_linea_exterior", False)
                ),
            }
            print(
                f"[PREF] Guardando checks de trazado: {preferencias['checks_trazado']}"
            )

        # Guardar en archivo JSON
        print(f"[PREF DEBUG] Guardando JSON con {len(preferencias)} grupos de datos")
        print(f"[PREF DEBUG] Contenido a guardar: {preferencias}")

        with open(ruta_archivo, "w", encoding="utf-8") as f:
            json.dump(preferencias, f, indent=2, ensure_ascii=False)

        print(f"[PREF] ✅ Preferencias guardadas en: {ruta_archivo}")
        print(
            f"[PREF DEBUG] Archivo existe después de guardar: {os.path.exists(ruta_archivo)}"
        )
        return True

    except Exception as e:
        print(f"[ERROR] Error al guardar preferencias: {e}")
        import traceback

        traceback.print_exc()
        return False


def cargar_preferencias_imposicion(
    checkbox_cruces=None,
    checkbox_lineas_corte=None,
    checkbox_marcas_texto=None,
    checkbox_linea_exterior=None,
):
    """
    Carga las preferencias de imposición desde el archivo JSON.

    """
    global LONGITUD_CRUZ_MM, GROSOR_CRUZ_PT, OFFSET_CRUZ_MM, AUTO_SANGRE_OFFSET_CRUZ
    global OFFSET_SEGURIDAD_MM, LONGITUD_BRAZO_MAX_MM  # ✨ NUEVO
    global MARCA_TEXTO_CONTENIDO, MARCA_TEXTO_POS_SUP_IZQ, MARCA_TEXTO_POS_SUP_DER
    global MARCA_TEXTO_POS_INF_IZQ, MARCA_TEXTO_POS_INF_DER, MARCA_TEXTO_POS_CENTRO_SUP
    global MARCA_TEXTO_POS_CENTRO_INF, MARCA_TEXTO_POS_CENTRO_LAT_IZQ, MARCA_TEXTO_POS_CENTRO_LAT_DER
    global MARCA_TEXTO_ROTACION, MARCA_TEXTO_FAMILIA, MARCA_TEXTO_TIPO, MARCA_TEXTO_CUERPO
    global MARCA_TEXTO_COLOR, MARCA_TEXTO_OFFSET_H_MM, MARCA_TEXTO_OFFSET_V_MM

    print("[PREF DEBUG] cargar_preferencias_imposicion() llamada")

    # Si ya existe una imposición activa, NO aplicar las preferencias porque
    # podrían sobrescribir valores previamente calculados/guardados.
    try:
        if _estado_impo_ui.get("impo_creada", False):
            print(
                "[PREF] impo_creada=True -> saltando carga de preferencias para evitar sobrescritura"
            )
            return False
    except Exception:
        pass

    try:
        ruta_archivo = obtener_ruta_preferencias()
        print(f"[PREF DEBUG] Ruta obtenida: {ruta_archivo}")

        if not ruta_archivo:
            print("[PREF] No se pudo obtener ruta, usando valores por defecto")
            return False

        if not os.path.exists(ruta_archivo):
            print(f"[PREF] Archivo no existe: {ruta_archivo}")
            print("[PREF] Usando valores por defecto")
            return False

        print(f"[PREF DEBUG] Archivo existe, procediendo a leer")
        # Leer archivo JSON
        with open(ruta_archivo, "r", encoding="utf-8") as f:
            preferencias = json.load(f)

        print(f"[PREF] 📂 Cargando preferencias desde: {ruta_archivo}")

        # Cargar datos de cruces
        if "cruces" in preferencias:
            cruces = preferencias["cruces"]
            LONGITUD_CRUZ_MM = float(cruces.get("longitud_mm", LONGITUD_CRUZ_MM))
            GROSOR_CRUZ_PT = float(cruces.get("grosor_pt", GROSOR_CRUZ_PT))
            OFFSET_CRUZ_MM = float(cruces.get("offset_mm", OFFSET_CRUZ_MM))
            AUTO_SANGRE_OFFSET_CRUZ = bool(
                cruces.get("auto_sangre", AUTO_SANGRE_OFFSET_CRUZ)
            )
            OFFSET_SEGURIDAD_MM = float(
                cruces.get("offset_seguridad_mm", OFFSET_SEGURIDAD_MM)
            )  # ✨ NUEVO
            LONGITUD_BRAZO_MAX_MM = float(
                cruces.get("longitud_brazo_max_mm", LONGITUD_BRAZO_MAX_MM)
            )  # ✨ NUEVO
            print(
                f"[PREF] ✅ Cruces cargadas: {LONGITUD_CRUZ_MM}mm, {GROSOR_CRUZ_PT}pt, offset={OFFSET_CRUZ_MM}mm, seg={OFFSET_SEGURIDAD_MM}mm, brazo_max={LONGITUD_BRAZO_MAX_MM}mm"
            )

        # Cargar datos de marcas de texto
        if "marcas_texto" in preferencias:
            marcas = preferencias["marcas_texto"]
            MARCA_TEXTO_CONTENIDO = str(marcas.get("contenido", MARCA_TEXTO_CONTENIDO))

            posiciones = marcas.get("posiciones", {})
            MARCA_TEXTO_POS_SUP_IZQ = bool(
                posiciones.get("sup_izq", MARCA_TEXTO_POS_SUP_IZQ)
            )
            MARCA_TEXTO_POS_SUP_DER = bool(
                posiciones.get("sup_der", MARCA_TEXTO_POS_SUP_DER)
            )
            MARCA_TEXTO_POS_INF_IZQ = bool(
                posiciones.get("inf_izq", MARCA_TEXTO_POS_INF_IZQ)
            )
            MARCA_TEXTO_POS_INF_DER = bool(
                posiciones.get("inf_der", MARCA_TEXTO_POS_INF_DER)
            )
            MARCA_TEXTO_POS_CENTRO_SUP = bool(
                posiciones.get("centro_sup", MARCA_TEXTO_POS_CENTRO_SUP)
            )
            MARCA_TEXTO_POS_CENTRO_INF = bool(
                posiciones.get("centro_inf", MARCA_TEXTO_POS_CENTRO_INF)
            )
            MARCA_TEXTO_POS_CENTRO_LAT_IZQ = bool(
                posiciones.get("centro_lat_izq", MARCA_TEXTO_POS_CENTRO_LAT_IZQ)
            )
            MARCA_TEXTO_POS_CENTRO_LAT_DER = bool(
                posiciones.get("centro_lat_der", MARCA_TEXTO_POS_CENTRO_LAT_DER)
            )

            MARCA_TEXTO_ROTACION = int(marcas.get("rotacion", MARCA_TEXTO_ROTACION))
            MARCA_TEXTO_FAMILIA = str(marcas.get("familia", MARCA_TEXTO_FAMILIA))
            MARCA_TEXTO_TIPO = str(marcas.get("tipo", MARCA_TEXTO_TIPO))
            MARCA_TEXTO_CUERPO = int(marcas.get("cuerpo", MARCA_TEXTO_CUERPO))

            # Cargar color (puede ser string o ft.Colors)
            color_guardado = marcas.get("color", MARCA_TEXTO_COLOR)
            if isinstance(color_guardado, str):
                MARCA_TEXTO_COLOR = color_guardado

            MARCA_TEXTO_OFFSET_H_MM = float(
                marcas.get("offset_h_mm", MARCA_TEXTO_OFFSET_H_MM)
            )
            MARCA_TEXTO_OFFSET_V_MM = float(
                marcas.get("offset_v_mm", MARCA_TEXTO_OFFSET_V_MM)
            )
            print(f"[PREF] ✅ Marcas de texto cargadas")
            # Volcar valores cargados al estado compartido para visibilidad/persistencia
            try:
                _estado_impo_ui["marca_texto_contenido"] = MARCA_TEXTO_CONTENIDO
                _estado_impo_ui["marca_texto_pos_sup_izq"] = MARCA_TEXTO_POS_SUP_IZQ
                _estado_impo_ui["marca_texto_pos_sup_der"] = MARCA_TEXTO_POS_SUP_DER
                _estado_impo_ui["marca_texto_pos_inf_izq"] = MARCA_TEXTO_POS_INF_IZQ
                _estado_impo_ui["marca_texto_pos_inf_der"] = MARCA_TEXTO_POS_INF_DER
                _estado_impo_ui["marca_texto_pos_centro_sup"] = (
                    MARCA_TEXTO_POS_CENTRO_SUP
                )
                _estado_impo_ui["marca_texto_pos_centro_inf"] = (
                    MARCA_TEXTO_POS_CENTRO_INF
                )
                _estado_impo_ui["marca_texto_pos_centro_lat_izq"] = (
                    MARCA_TEXTO_POS_CENTRO_LAT_IZQ
                )
                _estado_impo_ui["marca_texto_pos_centro_lat_der"] = (
                    MARCA_TEXTO_POS_CENTRO_LAT_DER
                )
                _estado_impo_ui["marca_texto_rotacion"] = MARCA_TEXTO_ROTACION
                _estado_impo_ui["marca_texto_familia"] = MARCA_TEXTO_FAMILIA
                _estado_impo_ui["marca_texto_tipo"] = MARCA_TEXTO_TIPO
                _estado_impo_ui["marca_texto_cuerpo"] = MARCA_TEXTO_CUERPO
                _estado_impo_ui["marca_texto_color"] = MARCA_TEXTO_COLOR
                _estado_impo_ui["marca_texto_offset_h_mm"] = MARCA_TEXTO_OFFSET_H_MM
                _estado_impo_ui["marca_texto_offset_v_mm"] = MARCA_TEXTO_OFFSET_V_MM
                print(
                    f"[PREF DEBUG] Marcas volcadas en _estado_impo_ui: offset_h={MARCA_TEXTO_OFFSET_H_MM}, offset_v={MARCA_TEXTO_OFFSET_V_MM}"
                )
            except Exception:
                pass

        # Cargar estados de checks de trazado
        if "checks_trazado" in preferencias:
            checks = preferencias["checks_trazado"]
            print(f"[PREF] ✅ Aplicando preferencias de checks de trazado (invocado)")
            print(
                f"[PREF] Valores en preferencias: cruces={checks.get('cruces_y_marcas')}, lineas={checks.get('lineas_corte')}, marcas={checks.get('marcas_texto')}, exterior={checks.get('linea_exterior')}"
            )

            # Notificar: preferencias cargadas (no se actualizan widgets aquí)

            # Volcar siempre en el estado compartido para visibilidad y persistencia
            try:
                _estado_impo_ui["checkbox_cruces"] = bool(
                    checks.get("cruces_y_marcas", False)
                )
                _estado_impo_ui["checkbox_lineas_corte"] = bool(
                    checks.get("lineas_corte", False)
                )
                _estado_impo_ui["checkbox_marcas_texto"] = bool(
                    checks.get("marcas_texto", False)
                )
                _estado_impo_ui["checkbox_linea_exterior"] = bool(
                    checks.get("linea_exterior", True)
                )
                # Formatos en MAYÚSCULAS usados en partes del código
                _estado_impo_ui["CHECK_BOX_CRUCES_Y_MARCAS"] = _estado_impo_ui.get(
                    "checkbox_cruces", False
                )
                _estado_impo_ui["CHECK_BOX_LINEAS_DE_CORTE"] = _estado_impo_ui.get(
                    "checkbox_lineas_corte", False
                )
                _estado_impo_ui["CHECK_BOX_MARCAS_DE_TEXTO"] = _estado_impo_ui.get(
                    "checkbox_marcas_texto", False
                )
                _estado_impo_ui["CHECK_BOX_LINEA_EXTERIOR"] = _estado_impo_ui.get(
                    "checkbox_linea_exterior", True
                )
            except Exception:
                pass

            print(f"[PREF] Checks aplicados: {checks}")

        print(f"[PREF] ✅ Preferencias cargadas correctamente")
        return True

    except FileNotFoundError:
        print(
            "[PREF] No se encontró archivo de preferencias, usando valores por defecto"
        )
        return False
    except json.JSONDecodeError as e:
        print(f"[ERROR] Error al leer JSON de preferencias: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] Error al cargar preferencias: {e}")
        import traceback

        traceback.print_exc()
        return False


def crear_ventana_ordenar_imposicion(
    page,
    on_guardar_trabajo=None,
    initial_project_modified=False,
    initial_project_path=None,
    initial_project_name="Sin título",
    loading_dialog=None,
):
    global GRID_COLS, GRID_ROWS, CALLES_L, dropdown_doble_cara, _archivo_seleccionado, _ordenamiento_calculado, _pdf_ordenado_actual
    global _estado_impo_ui, _PDF_VALIDATED

    print(f"[DEBUG OVERLAY] Tamaño de página: {page.width} x {page.height}")
    print("Ejecutando crear_ventana_ordenar_imposicion() impo_ui.py")
    try:
        import builtins

        try:
            builtins._impo_page = page
        except Exception:
            pass
    except Exception:
        pass

    # ════════════════════════════════════════════════════════════════════════════════
    # 1. RESTAURAR ESTADO SOLO SI HAY PDF VÁLIDO EN MEMORIA
    # ════════════════════════════════════════════════════════════════════════════════
    # Restaurar si hay datos previos guardados - detectar por campos que siempre tienen valor
    # Verificar: última modificación, dropdown_doble_cara, o cualquier dato de configuración
    tiene_estado_previo = (
        _estado_impo_ui.get("ultima_modificacion") is not None
        or _estado_impo_ui.get("dropdown_doble_cara") is not None
        or _estado_impo_ui.get("sangre") is not None
    )

    if tiene_estado_previo:
        print(
            f"[DEBUG] NO se aplican preferencias, hay estado previo de trabajo cargado"
        )
        print("[ESTADO] 🔄 Restaurando estado desde sesión anterior...")
        print(
            f"[ESTADO] 🔍 dropdown_doble_cara ANTES de restaurar: {_estado_impo_ui.get('dropdown_doble_cara', 'NO EXISTE')}"
        )
        restaurar_estado_impo_ui()
        print(
            f"[ESTADO] 🔍 dropdown_doble_cara DESPUÉS de restaurar: {_estado_impo_ui.get('dropdown_doble_cara', 'NO EXISTE')}"
        )
    else:
        print(
            f"[DEBUG] SÍ se aplican preferencias, NO hay estado previo de trabajo cargado"
        )
        print("[ESTADO] ℹ️ Sin estado previo - usando valores por defecto")
        print(
            f"[ESTADO] 🔍 dropdown_doble_cara en estado vacío: {_estado_impo_ui.get('dropdown_doble_cara', 'NO EXISTE')}"
        )
        # Resetear sangre a 0 para nueva imposición
        global SANGRE
        SANGRE = 0.0
        # Agrego prints para mostrar cuándo y con qué valores se aplican las preferencias al crear un trabajo nuevo.
        try:
            from pdf_ordenado_ui import cargar_preferencias_checkboxes

            checks = cargar_preferencias_checkboxes()
            print(
                f"[DEBUG] CREANDO TRABAJO NUEVO: se aplican preferencias a los checkboxes"
            )
            print(
                f"[DEBUG] Valores de preferencias: cruces={checks.get('cruces_y_marcas')}, lineas={checks.get('lineas_corte')}, marcas={checks.get('marcas_texto')}, exterior={checks.get('linea_exterior')}"
            )
        except Exception as ex:
            print(f"[DEBUG] Error al cargar preferencias de checkboxes: {ex}")

    # Calcular tamaño del viewer basado en el tamaño de la página.
    # Cromo horizontal: padding wrapper/inner (5+5) + columna derecha (320) +
    # bordes del Row (~5) = 335~350 → se usa 345 (paridad con el resize).
    CROMA_HORIZONTAL_OVERLAY = 345
    # Cromo vertical hasta el visor: padding wrapper.top (5) + padding inner.top
    # (5) + fila botones/zoom (50) + spacer (2) + paddings inferiores (10) = 72.
    # (con `expand`, el visor ocupa el resto real; estas constantes deben
    # coincidir con él para que el clamp de pan y el centrado sean exactos)
    CROMA_VERTICAL_OVERLAY = 72
    VIEWER_WIDTH = int(page.width - CROMA_HORIZONTAL_OVERLAY) if page.width else 925
    VIEWER_HEIGHT = int(page.height - CROMA_VERTICAL_OVERLAY) if page.height else 750

    print(f"[DEBUG VIEWER] VIEWER_WIDTH: {VIEWER_WIDTH}")
    print(f"[DEBUG VIEWER] VIEWER_HEIGHT: {VIEWER_HEIGHT}")

    """Diálogo de imposición — versión consolidada exportada a `impo_ui`.

    Devuelve un Container (overlay) que implementa la UI para cargar el PDF,
    configurar opciones y lanzar la función de imposición en background.
    """
    # Usar las variables globales persistentes (ya no son locales)
    archivo_seleccionado = _archivo_seleccionado
    ordenamiento_calculado = _ordenamiento_calculado

    print(
        f"[DEBUG ABRIR] PDF: {_archivo_seleccionado.get('nombre', 'Sin PDF')}, Páginas: {_archivo_seleccionado.get('paginas', 0)}"
    )
    print(
        f"[DEBUG ABRIR] PDF ordenado: {os.path.basename(_pdf_ordenado_actual) if _pdf_ordenado_actual else 'N/A'}"
    )
    orden_dict = (
        _ordenamiento_calculado.get("ordenamiento") if _ordenamiento_calculado else None
    )
    num_pliegos = len(orden_dict) if orden_dict and isinstance(orden_dict, dict) else 0
    print(f"[DEBUG ABRIR] Ordenamiento: {num_pliegos} pliegos")

    # ========================================================================
    # 2. VALIDAR PDF: Si hay datos en memoria, verificar stamp del PDF
    # ========================================================================
    pdf_temp_ordenado = obtener_pdf_ordenado_temp()
    stamp_guardado = _estado_impo_ui.get("pdf_stamp")

    if (
        _archivo_seleccionado["ruta"]
        and pdf_temp_ordenado
        and os.path.exists(pdf_temp_ordenado)
    ):
        # Generar stamp del PDF actual (tamaño archivo + timestamp modificación)
        try:
            stat = os.stat(pdf_temp_ordenado)
            stamp_actual = f"{stat.st_size}_{stat.st_mtime}"
        except:
            stamp_actual = None

        # Comparar stamp
        if stamp_guardado and stamp_actual and stamp_guardado != stamp_actual:
            # ❌ PDF diferente - RESETEAR TODO
            print(f"[VALIDAR] ⚠️ PDF cambió - reseteando datos")
            print(f"[VALIDAR]   stamp_memoria: {stamp_guardado}")
            print(f"[VALIDAR]   stamp_actual: {stamp_actual}")

            # Preservar valor del dropdown antes de limpiar
            dropdown_doble_cara_anterior = _estado_impo_ui.get(
                "dropdown_doble_cara", "cara"
            )
            print(
                f"[VALIDAR] Preservando dropdown_doble_cara: {dropdown_doble_cara_anterior}"
            )

            # Limpiar estado completo
            ultima_modificacion_actual = _estado_impo_ui.get(
                "ultima_modificacion", None
            )
            _estado_impo_ui.clear()
            _estado_impo_ui.update(
                {
                    "pdf_stamp": None,
                    "pdf_ruta": "",
                    "pdf_nombre": "",
                    "pdf_paginas": 0,
                    "pdf_ordenado_ruta": None,
                    "ordenamiento": None,
                    "ordenamiento_paginas_requeridas": 0,
                    "grid_cols": 1,
                    "grid_rows": 1,
                    "calles_list": [],
                    "tamano_usuario_w": 0.0,
                    "tamano_usuario_h": 0.0,
                    "sangre": 3.0,
                    "pliego_ancho": None,
                    "pliego_alto": None,
                    "pliego_congelado": False,
                    "offset_img_x": 0.0,
                    "offset_img_y": 0.0,
                    "offset_trazado_x": 0.0,
                    "offset_trazado_y": 0.0,
                    "dropdown_copias": "1",
                    "dropdown_doble_cara": dropdown_doble_cara_anterior,
                    "dropdown_rotacion": "0°",
                    "dropdown_tipo_corte": None,
                    "checkbox_cruces": False,
                    "checkbox_lineas_corte": False,
                    "checkbox_marcas_texto": False,
                    "checkbox_linea_exterior": True,
                    "checkbox_xerox": False,
                    "pliego_index": 0,
                    "pliego_actual_texto": "1",
                    "total_pliegos": 0,
                    "zoom_level": 0.96,
                    "auto_zoom": True,
                    "controles_visibles": False,
                    "boton_crear_disabled": True,
                    "navegacion_visible": False,
                    "ultima_modificacion": ultima_modificacion_actual,
                }
            )
            try:
                _PDF_VALIDATED = False
                print("[VALIDAR] _PDF_VALIDATED = False (reset)")
            except Exception:
                pass

            # Limpiar variables globales
            _archivo_seleccionado.clear()
            _archivo_seleccionado.update({"ruta": "", "nombre": "", "paginas": 0})
            _ordenamiento_calculado.clear()
            _ordenamiento_calculado.update(
                {"ordenamiento": None, "paginas_requeridas": 0}
            )
            _pdf_ordenado_actual = None

            # Limpiar cache de imágenes
            try:
                from pdf_ordenado_ui import limpiar_temp_sesion

                limpiar_temp_sesion()
                print("[VALIDAR] ✅ Cache de imágenes limpiado")
            except Exception as ex:
                print(f"[VALIDAR] Error limpiando cache: {ex}")
        else:
            print("[VALIDAR] ✅ PDF coincide - usando datos en memoria")
            # Marcar que el PDF ha sido validado: sólo ahora permitimos que
            # `guardar_estado_impo_ui()` persista metadatos del PDF en el stamp.
            try:
                _PDF_VALIDATED = True
                print("[VALIDAR] _PDF_VALIDATED = True")
            except Exception:
                pass

            # Persistir inmediatamente el estado ahora que el PDF fue validado
            try:
                guardar_estado_impo_ui()
                print("[VALIDAR] Estado persistido tras validar PDF")
            except Exception as _save_ex:
                print(
                    f"[VALIDAR] Error guardando estado después de validar PDF: {_save_ex}"
                )

    # Variables de estado del proyecto de imposición (sincronizadas con app.py)
    project_name = initial_project_name
    current_project_path = initial_project_path
    project_modified = initial_project_modified

    def mark_modified():
        """Marca rápidamente que hubo un cambio en la imposición"""
        nonlocal project_modified
        global _SUSPEND_MARK_MODIFIED
        # Si la marcación está suspendida (p. ej. durante carga), evitar cambios.
        if _SUSPEND_MARK_MODIFIED:
            print("[IMPO STATE] mark_modified ignorado (suspendido)")
            return

        if not project_modified:
            project_modified = True
            update_project_state_ui()
            try:
                import inspect

                caller = inspect.stack()[1]
                print(
                    f"[IMPO STATE] Proyecto de imposición marcado como modificado by {caller.filename}:{caller.lineno} in {caller.function}"
                )
                try:
                    import traceback

                    stack = traceback.format_stack()
                    # Mostrar las últimas líneas de la pila para contexto (omitimos frames internos)
                    print(
                        "[IMPO STATE] Stack (últimos frames):\n" + "".join(stack[-6:])
                    )
                except Exception:
                    pass
            except Exception:
                print("[IMPO STATE] Proyecto de imposición marcado como modificado")
        # Marcar el flag en el estado para el stamp
        try:
            global _estado_impo_ui
            _estado_impo_ui["trabajo_modificado"] = True
        except Exception:
            pass
        # Asegurar actualización local del botón incluso si project_modified
        # ya era True (caso en que sólo se notifica el callback global).
        try:
            update_project_state_ui()
        except Exception:
            pass
        # Notificar a cualquier callback registrado globalmente (ej. app.py)
        try:
            import builtins

            cb = getattr(builtins, "_on_trabajo_modificado_change", None)
            try:
                import inspect

                caller = inspect.stack()[1]
                print(
                    f"[IMPO STATE] mark_modified called by {caller.filename}:{caller.lineno} in {caller.function} -> trabajo_modificado={_estado_impo_ui.get('trabajo_modificado', None)} callback_exists={callable(cb)}"
                )
            except Exception:
                print(
                    f"[IMPO STATE] mark_modified: trabajo_modificado={_estado_impo_ui.get('trabajo_modificado', None)} callback_exists={callable(cb)}"
                )
            if callable(cb):
                try:
                    cb()
                except Exception:
                    pass
        except Exception:
            pass
        # Lanzar actualización debounced del stamp para persistir cambios
        try:
            update_stamp_on_change()
        except Exception:
            # Si la función no existe aún (por orden de definición), ignorar
            pass

    # Asignar a variable global para que los diálogos puedan acceder
    global _mark_modified_callback
    _mark_modified_callback = mark_modified

    # Debounce/save helper: agrupa cambios frecuentes y guarda el estado (stamp)
    _stamp_timer = None

    def update_stamp_on_change(delay: float = 0.5):
        """Debounce wrapper: espera `delay` segundos sin nuevas llamadas y guarda el estado.

        Llamar desde handlers de UI o desde `mark_modified()` para asegurar que el
        stamp se actualiza en disco/estado sin escrituras excesivas.
        """
        nonlocal _stamp_timer

        def _flush():
            try:
                guardar_estado_impo_ui()
            except Exception:
                pass

        # Cancelar timer previo
        try:
            if _stamp_timer is not None:
                _stamp_timer.cancel()
        except Exception:
            pass

        # Crear nuevo timer
        _stamp_timer = threading.Timer(delay, _flush)
        _stamp_timer.daemon = True
        _stamp_timer.start()

    textfield_ancho = ft.TextField(
        label=t("Ancho ({0})").format(
            get_unit_abbr(_initial_unit_pref)
        ),  # Se actualizará dinámicamente
        value="",
        width=110,
        height=40,
        text_size=16,
        text_align=ft.TextAlign.LEFT,
        text_vertical_align=ft.VerticalAlignment.CENTER,
        content_padding=ft.Padding(8, 0, 0, 0),
        color=TEXTOS_FASE_1_COLOR,
        bgcolor=FONDO_TEXTFIELDS_COLOR,
        border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)),
        focused_color=None,
        focused_bgcolor=None,
        text_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
        label_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
        read_only=False,
        visible=True,
    )
    textfield_alto = ft.TextField(
        label=t("Alto ({0})").format(
            get_unit_abbr(_initial_unit_pref)
        ),  # Se actualizará dinámicamente
        value="",
        width=110,
        height=40,
        text_size=16,
        text_align=ft.TextAlign.LEFT,
        text_vertical_align=ft.VerticalAlignment.CENTER,
        content_padding=ft.Padding(8, 0, 0, 0),
        color=TEXTOS_FASE_1_COLOR,
        bgcolor=FONDO_TEXTFIELDS_COLOR,
        border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)),
        focused_color=None,
        focused_bgcolor=None,
        text_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
        label_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
        read_only=False,
        visible=True,
    )
    textfield_sangre = ft.TextField(
        label=t("Sangre ({0})").format(
            get_unit_abbr(_initial_unit_pref)
        ),  # Se actualizará dinámicamente
        value=f"{SANGRE:.2f}",
        width=110,
        height=40,
        text_size=16,
        text_align=ft.TextAlign.LEFT,
        text_vertical_align=ft.VerticalAlignment.CENTER,
        content_padding=ft.Padding(8, 0, 0, 0),
        color=TEXTOS_FASE_1_COLOR,
        bgcolor=FONDO_TEXTFIELDS_COLOR,
        border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)),
        focused_color=None,
        focused_bgcolor=None,
        text_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
        label_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
        read_only=False,
        visible=True,
    )
    # Campo para calles (acepta valores separados por comas como en trazado_ui.py)
    # Formato: "calle1,calle2,..." donde primero van las verticales (entre columnas) y luego las horizontales (entre filas)
    # Campo para calles (acepta valores separados por comas como en trazado_ui.py)
    # Formato: "calle1,calle2,..." donde primero van las verticales (entre columnas) y luego las horizontales (entre filas)
    # TEXTFIELD ELIMINADO - SE USA DIALOGO

    # Botón para abrir diálogo de calles
    boton_calles = ft.IconButton(
        icon=ft.Icons.GRID_ON,
        tooltip=t("Configurar calles individuales"),
        icon_color=TEXTOS_FASE_1_COLOR,
        on_click=lambda e: abrir_dialogo_calles(
            page, textfield_grid_cols, textfield_grid_rows, actualizar_trazado
        ),
    )

    # Botón para Offset Pliego
    boton_offset_pliego = ft.IconButton(
        icon=ft.Icons.CROP_FREE,
        tooltip=t("Offset Pliego"),
        icon_color=TEXTOS_FASE_1_COLOR,
        on_click=lambda e: abrir_dialogo_offset_pliego(
            page,
            textfield_offset_trazado_x,
            textfield_offset_trazado_y,
            actualizar_trazado,
        ),
    )

    # Botón para Offset PDFs
    boton_offset_pdfs = ft.IconButton(
        icon=ft.Icons.IMAGE_ASPECT_RATIO,
        tooltip=t("Offset páginas"),
        icon_color=TEXTOS_FASE_1_COLOR,
        on_click=lambda e: abrir_dialogo_offset_pdfs(
            page, textfield_offset_img_x, textfield_offset_img_y, actualizar_trazado
        ),
    )

    # Nota: `boton_offsets` (diálogo combinado) eliminado — usar botones específicos de offsets

    # Botón para abrir diálogo de cruces
    boton_cruces = ft.IconButton(
        icon=ft.Icons.ADD,
        tooltip=t("Configurar Cruces"),
        icon_color=TEXTOS_FASE_1_COLOR,
        on_click=lambda e: abrir_dialogo_cruces(page, actualizar_trazado),
    )

    # Botón para abrir diálogo de marcas de texto
    boton_marcas_texto = ft.IconButton(
        icon=ft.Icons.TEXT_FIELDS,
        tooltip=t("Configurar Marcas de Texto"),
        icon_color=TEXTOS_FASE_1_COLOR,
        on_click=lambda e: abrir_dialogo_marcas_texto(
            page, actualizar_trazado, zoom_level, user_changed_zoom
        ),
    )

    # ═══════════════════════════════════════════════════════════════════════════════
    # DIÁLOGO DE PREFERENCIAS
    # ═══════════════════════════════════════════════════════════════════════════════

    def abrir_dialogo_preferencias(
        page_ref,
        checkbox_cruces_ref,
        checkbox_lineas_corte_ref,
        checkbox_marcas_texto_ref,
        checkbox_linea_exterior_ref,
    ):
        """
        Abre el diálogo para seleccionar qué preferencias guardar.

        Args:
            page_ref: Referencia a la página
            checkbox_cruces_ref: Referencia al checkbox de cruces y marcas
            checkbox_lineas_corte_ref: Referencia al checkbox de líneas de corte
            checkbox_marcas_texto_ref: Referencia al checkbox de marcas de texto
            checkbox_linea_exterior_ref: Referencia al checkbox de línea exterior
        """
        # NO CARGAR preferencias aquí - usamos los valores actuales de las variables globales
        # que ya fueron actualizados por los diálogos de configuración

        # Checkboxes para seleccionar qué guardar
        check_guardar_cruces = ft.Checkbox(
            label=t("Cruces (longitud, grosor, offset, auto sangre)"),
            fill_color=BOTONES_GENERICOS_FONDO_COLOR,
            value=True,
        )
        check_guardar_marcas_texto = ft.Checkbox(
            label=t("Marcas de Texto (posición, contenido, fuente, formato)"),
            fill_color=BOTONES_GENERICOS_FONDO_COLOR,
            value=True,
        )
        check_guardar_checks_trazado = ft.Checkbox(
            label=t("Estados de Checks de Trazado"),
            fill_color=BOTONES_GENERICOS_FONDO_COLOR,
            value=True,
        )

        # Checkboxes individuales para los checks de trazado (solo se usan si el check principal está activo)
        check_estado_cruces_y_marcas = ft.Checkbox(
            label=t("  • Cruces y marcas"),
            value=checkbox_cruces_ref.value if checkbox_cruces_ref else False,
            fill_color=BOTONES_GENERICOS_FONDO_COLOR,
            disabled=True,
        )
        check_estado_lineas_corte = ft.Checkbox(
            label=t("  • Líneas de corte"),
            value=(
                checkbox_lineas_corte_ref.value if checkbox_lineas_corte_ref else False
            ),
            fill_color=BOTONES_GENERICOS_FONDO_COLOR,
            disabled=True,
        )
        check_estado_marcas_texto_check = ft.Checkbox(
            label=t("  • Marcas de texto"),
            value=(
                checkbox_marcas_texto_ref.value if checkbox_marcas_texto_ref else False
            ),
            fill_color=BOTONES_GENERICOS_FONDO_COLOR,
            disabled=True,
        )
        check_estado_linea_exterior = ft.Checkbox(
            label=t("  • Línea exterior"),
            value=(
                checkbox_linea_exterior_ref.value
                if checkbox_linea_exterior_ref
                else True
            ),
            fill_color=BOTONES_GENERICOS_FONDO_COLOR,
            disabled=True,
        )

        # Habilitar/deshabilitar checks individuales según el check principal
        def toggle_checks_individuales(e):
            activado = check_guardar_checks_trazado.value
            check_estado_cruces_y_marcas.disabled = not activado
            check_estado_lineas_corte.disabled = not activado
            check_estado_marcas_texto_check.disabled = not activado
            check_estado_linea_exterior.disabled = not activado
            check_estado_cruces_y_marcas.update()
            check_estado_lineas_corte.update()
            check_estado_marcas_texto_check.update()
            check_estado_linea_exterior.update()

        check_guardar_checks_trazado.on_change = toggle_checks_individuales

        # ═══ Sección: Offsets adicionales (mostrados para transparencia) ═══
        try:
            current_unit = _estado_impo_ui.get("unit", _initial_unit_pref) or "mm"
        except Exception:
            current_unit = "mm"
        try:
            unit_label_small = get_unit_abbr(current_unit)
        except Exception:
            unit_label_small = current_unit

        try:
            seg_disp = (
                f"{convert_from_mm(float(OFFSET_SEGURIDAD_MM), current_unit):.2f}"
            )
        except Exception:
            seg_disp = str(OFFSET_SEGURIDAD_MM)

        try:
            len_disp = (
                f"{convert_from_mm(float(LONGITUD_BRAZO_MAX_MM), current_unit):.2f}"
            )
        except Exception:
            len_disp = str(LONGITUD_BRAZO_MAX_MM)

        cont_offsets = ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        t("Marcas medianales:"),
                        size=13,
                        weight=ft.FontWeight.BOLD,
                        color=TEXTO_COLOR_GENERICO,
                    ),
                    ft.Container(height=6),
                    # Mostrar los valores en la unidad seleccionada (solo visual)
                    ft.Text(
                        f"{t('Margen seguridad ({0})').format(unit_label_small)}: {seg_disp}",
                        size=12,
                        color=TEXTO_COLOR_GENERICO,
                    ),
                    ft.Text(
                        f"{t('Longitud ({0})').format(unit_label_small)}: {len_disp}",
                        size=12,
                        color=TEXTO_COLOR_GENERICO,
                    ),
                ],
                spacing=6,
                horizontal_alignment=ft.CrossAxisAlignment.START,
            ),
            padding=ft.Padding(8, 6, 8, 6),
            bgcolor=FONDO_ALERT_DIALOG,
        )

        def guardar_preferencias_seleccionadas(e):
            """Guarda las preferencias seleccionadas por el usuario."""
            # Recopilar datos seleccionados
            datos_seleccionados = {
                "cruces": check_guardar_cruces.value,
                "marcas_texto": check_guardar_marcas_texto.value,
                "checks_trazado": check_guardar_checks_trazado.value,
                # Estados actuales de los checks de trazado
                "check_cruces_y_marcas": check_estado_cruces_y_marcas.value,
                "check_lineas_corte": check_estado_lineas_corte.value,
                "check_marcas_texto_estado": check_estado_marcas_texto_check.value,
                "check_linea_exterior": check_estado_linea_exterior.value,
            }

            # Guardar preferencias
            exito = guardar_preferencias_imposicion(datos_seleccionados)

            # Cerrar diálogo
            page_ref.pop_dialog()

            # Mostrar mensaje al usuario
            if exito:
                _snack = ft.SnackBar(
                    content=ft.Text(t("✅ Preferencias guardadas correctamente"), color=SNACKBAR_COLOR_TEXTO),
                    bgcolor=SUCCESS_COLOR,
                )
            else:
                _snack = ft.SnackBar(
                    content=ft.Text(t("❌ Error al guardar preferencias"), color=SNACKBAR_COLOR_TEXTO),
                    bgcolor=SNACKBAR_COLOR_ERROR,
                )
            page_ref.show_dialog(_snack)

        def cerrar_dialogo_pref(e):
            """Cierra el diálogo sin guardar."""
            page_ref.pop_dialog()

        # Crear diálogo
        dialogo_pref = ft.AlertDialog(
            title=ft.Text(
                t("Guardar Ajustes avanzados y trazado por defecto"),
                size=18,
                weight=ft.FontWeight.BOLD,
                color=TEXTO_COLOR_GENERICO,
            ),
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Container(height=10),
                        ft.Row(
                            [
                                # Spacer para alinear el título con las etiquetas de los Checkboxes
                                ft.Container(width=5),
                                ft.Text(
                                    t("Selecciona qué preferencias deseas guardar:"),
                                    size=16,
                                    weight=ft.FontWeight.BOLD,
                                    color=TEXTO_COLOR_GENERICO,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.START,
                        ),
                        ft.Container(height=10),
                        check_guardar_cruces,
                        cont_offsets,
                        check_guardar_marcas_texto,
                        ft.Container(height=5),
                        ft.Divider(height=1, thickness=1, color=BORDE_TEXTFIELDS_COLOR),
                        ft.Container(height=5),
                        check_guardar_checks_trazado,
                        ft.Container(height=5),
                        ft.Text(
                            t("Checks de Trazado:"),
                            size=14,
                            weight=ft.FontWeight.BOLD,
                            color=TEXTO_COLOR_GENERICO,
                        ),
                        check_estado_cruces_y_marcas,
                        check_estado_lineas_corte,
                        check_estado_marcas_texto_check,
                        check_estado_linea_exterior,
                    ],
                    spacing=5,
                    scroll=ft.ScrollMode.HIDDEN,
                ),
                width=470,
                height=500,
                padding=ft.Padding(10, 10, 10, 10),
            ),
            actions=[
                ft.Button(
                    t("Cancelar"),
                    width=110,
                    bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                    on_click=cerrar_dialogo_pref,
                    style=ft.ButtonStyle(
                        color={
                            ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                            "hovered": BOTONES_GENERICOS_HOVER_COLOR,
                        },
                        overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                        padding=ft.Padding(0, 0, 0, 0),
                        shape=ft.RoundedRectangleBorder(radius=10),
                    ),
                ),
                ft.Button(
                    t("Aceptar"),
                    width=110,
                    bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                    on_click=guardar_preferencias_seleccionadas,
                    style=ft.ButtonStyle(
                        color={
                            ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                            "hovered": BOTONES_GENERICOS_HOVER_COLOR,
                        },
                        overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                        padding=ft.Padding(0, 0, 0, 0),
                        shape=ft.RoundedRectangleBorder(radius=10),
                    ),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.CENTER,
            content_padding=ft.Padding(0, 0, 0, 0),
            bgcolor=FONDO_ALERT_DIALOG,
        )

        page_ref.show_dialog(dialogo_pref)

    # Botón para abrir diálogo de preferencias (IconButton con icono de archivo)
    boton_preferencias = ft.IconButton(
        icon=ft.Icons.ARCHIVE,
        tooltip=t("Guardar ajustes"),
        icon_color=TEXTOS_FASE_1_COLOR,
        on_click=lambda e: abrir_dialogo_preferencias(
            page,
            checkbox_cruces,
            checkbox_lineas_corte,
            checkbox_marcas_texto,
            checkbox_linea_exterior,
        ),
    )

    # Cuando el usuario cambia el grid (cols/rows), regenerar las calles por defecto y actualizar el textfield
    def _on_grid_size_change(e=None):
        global CALLES_L
        try:
            cols = (
                int(textfield_grid_cols.value)
                if textfield_grid_cols and textfield_grid_cols.value
                else GRID_COLS
            )
        except Exception:
            cols = GRID_COLS
        try:
            rows = (
                int(textfield_grid_rows.value)
                if textfield_grid_rows and textfield_grid_rows.value
                else GRID_ROWS
            )
        except Exception:
            rows = GRID_ROWS

        n_v = max(0, cols - 1)
        n_h = max(0, rows - 1)
        default_vert = 0
        default_horiz = 0
        nueva = [default_vert] * n_v + [default_horiz] * n_h
        # Normalizar y asegurar longitud correcta usando build_calles_list
        try:
            CALLES_L = build_calles_list(nueva, cols, rows)
        except Exception:
            CALLES_L = nueva
        try:
            # Deshabilitar botón de calles y cruces si el grid es 1x1 (no hay calles ni cruces internas)
            if cols == 1 and rows == 1:
                boton_calles.disabled = True
                boton_cruces.disabled = True
            else:
                boton_calles.disabled = False
                boton_cruces.disabled = False
            boton_calles.update()
            boton_cruces.update()
        except Exception:
            pass
        # Marcar como modificado
        mark_modified()

    try:
        textfield_grid_cols.on_change = _on_grid_size_change
        textfield_grid_rows.on_change = _on_grid_size_change
    except Exception:
        pass

    texto_archivo = ft.Text(
        archivo_seleccionado["nombre"] or t("Ningún archivo seleccionado"),
        size=12,
        color=TEXTO_COLOR_GENERICO,
    )
    texto_paginas = ft.Text(
        t("Páginas: {0}").format(archivo_seleccionado["paginas"]),
        size=16,
        color=TEXTO_COLOR_GENERICO,
    )
    texto_paginas_requeridas = ft.Text(
        "", size=12, color=TEXTO_COLOR_GENERICO, visible=True
    )
    # Campo para mostrar validación del PDF cargado (número de páginas)
    texto_validacion = ft.Text("", size=14, color=TEXTO_COLOR_GENERICO, visible=True)

    # Barra de progreso y contador de pliegos (ocultos inicialmente)
    dialog_w = int(page.window.width)
    dialog_h = int(page.window.height)

    progress_bar = ft.ProgressBar(width=dialog_w - 40, height=12, value=0)
    texto_contador_pliegos = ft.Text(
        t("Pliego 0/0"), size=14, color=TEXTO_COLOR_GENERICO
    )

    # Fila de progreso controlable desde fuera
    # Progress row: only the progress bar and counter (remove the 'Progreso:' label)
    progress_row = ft.Row(
        [
            ft.Column([progress_bar], expand=True),
            # texto_contador_pliegos movido a navegacion_pliegos_container
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        visible=True,
    )

    def _init_progress_counter(total_pliegos: int):
        try:
            if (
                not total_pliegos
                or not isinstance(total_pliegos, int)
                or total_pliegos <= 0
            ):
                texto_contador_pliegos.value = "Pliego 0/0"
                # Indeterminada (null) → barra animada mientras se procesa;
                # una barra determinista a 0 parecía congelada.
                progress_bar.value = None
            else:
                texto_contador_pliegos.value = f"Pliego 0/{total_pliegos}"
                progress_bar.value = 0.0
            texto_contador_pliegos.update()
            progress_bar.update()
        except Exception:
            pass

    def recalcular_ordenamiento():
        """Recalcula las páginas requeridas basadas en el gráfico generado."""
        # Si estamos cargando datos, no recalcular nada
        if _CARGANDO_DATOS:
            print("[DEBUG] recalcular_ordenamiento: IGNORADO (Cargando datos)")
            return

        try:
            # Verificar que tenemos los datos del gráfico
            if "orden_grafico_visual" not in grafico_datos:
                texto_paginas_requeridas.value = (
                    "Error: Debe generar un gráfico primero"
                )
                texto_paginas_requeridas.color = ERROR_COLOR
                texto_paginas_requeridas.visible = True
                boton_cargar_pdf.visible = False
                try:
                    boton_cargar_pdf.update()
                    texto_paginas_requeridas.update()
                except Exception:
                    pass
                return

            # Obtener parámetros (asumiendo valores por defecto para imposición)
            num_copias = 1  # En imposición, normalmente 1 copia

            # Detectar doble cara desde el dropdown
            doble_cara = False
            if dropdown_doble_cara and dropdown_doble_cara.value:
                val_dc = str(dropdown_doble_cara.value).lower()
                doble_cara = val_dc == "dorso" or val_dc.startswith("d")

            orden_grafico_visual = grafico_datos["orden_grafico_visual"]
            comienzo_numeracion = grafico_datos.get("entrada", {}).get("comienzo", 1)

            # Generar ordenamiento para calcular páginas requeridas
            ordenamiento_pdf = generar_ordenamiento_pdf_montaje(
                orden_grafico_visual=orden_grafico_visual,
                doble_cara=doble_cara,
                numero_copias=num_copias,
                comienzo_numeracion=comienzo_numeracion,
            )

            if not ordenamiento_pdf:
                texto_paginas_requeridas.value = "Error al calcular ordenamiento"
                texto_paginas_requeridas.color = ERROR_COLOR
                texto_paginas_requeridas.visible = True
                boton_cargar_pdf.visible = False
                try:
                    boton_cargar_pdf.update()
                    texto_paginas_requeridas.update()
                except Exception:
                    pass
                return

            # Calcular páginas requeridas del PDF original
            paginas_requeridas = None
            if "_metadata" in ordenamiento_pdf and isinstance(
                ordenamiento_pdf["_metadata"], dict
            ):
                paginas_requeridas = ordenamiento_pdf["_metadata"].get(
                    "paginas_pdf_original"
                )

            # Fallback si no había metadata
            if paginas_requeridas is None:
                max_pagina_requerida = 0
                for k, datos in ordenamiento_pdf.items():
                    if (
                        isinstance(k, int)
                        and isinstance(datos, dict)
                        and datos.get("datos")
                    ):
                        max_pagina_requerida = max(
                            max_pagina_requerida, max(datos["datos"])
                        )
                paginas_requeridas = max_pagina_requerida

            if paginas_requeridas == 0:
                texto_paginas_requeridas.value = "Error: El gráfico no tiene páginas"
                texto_paginas_requeridas.color = ERROR_COLOR
                texto_paginas_requeridas.visible = True
                boton_cargar_pdf.visible = False
                try:
                    boton_cargar_pdf.update()
                    texto_paginas_requeridas.update()
                except Exception:
                    pass
                return

            # Guardar el ordenamiento completo y las páginas requeridas
            ordenamiento_calculado["ordenamiento"] = ordenamiento_pdf
            ordenamiento_calculado["paginas_requeridas"] = paginas_requeridas
            print(
                f"[IMPO_UI] Ordenamiento recalculado: {len(ordenamiento_pdf)} pliegos, {paginas_requeridas} páginas"
            )
            # TODO CONTROL VISTAS COLUMNA IMPOSICION
            # Mostrar información al usuario
            texto_paginas_requeridas.value = t(
                "Necesita un PDF de exactamente {0} páginas"
            ).format(paginas_requeridas)
            texto_paginas_requeridas.color = INFO_COLOR
            texto_paginas_requeridas.visible = True

            # Mostrar botón para cargar PDF
            # boton_cargar_pdf.visible = True

            # Actualizar la UI
            try:
                # boton_cargar_pdf.update()
                texto_paginas_requeridas.update()
            except Exception:
                pass
        except Exception as ex:
            print(f"Error en recalcular_ordenamiento: {ex}")

    # Inicializar valores de Grid desde grafico_datos si existen
    try:
        if grafico_datos and "entrada" in grafico_datos:
            entrada = grafico_datos["entrada"]
            if "horizontal" in entrada and "vertical" in entrada:
                GRID_COLS = int(entrada["horizontal"])
                GRID_ROWS = int(entrada["vertical"])
                # Asegurar que CALLES_L tenga el tamaño correcto
                expected_calles = max(0, GRID_COLS - 1) + max(0, GRID_ROWS - 1)
                if len(CALLES_L) < expected_calles:
                    val_calle = (
                        float(textfield_medianil.value)
                        if textfield_medianil.value
                        else 0.0
                    )
                    CALLES_L = build_calles_list(val_calle, GRID_COLS, GRID_ROWS)
    except Exception as ex:
        print(f"Error inicializando grid desde grafico_datos: {ex}")

    # Variables de Zoom
    zoom_level = {"value": 1.0}  # Factor de zoom del usuario (1.0 = 100%)
    zoom_final = {"value": 1.0}  # Zoom final aplicado al viewer
    user_changed_zoom = {"value": False}  # Flag para saber si el usuario tocó el zoom
    # Timer para resetear el flag `user_changed_zoom` tras interacción del usuario
    user_changed_zoom_reset = {"timer": None}
    # Secuencia para evitar race-conditions entre timers consecutivos
    user_changed_zoom_seq = {"v": 0}

    # Stack principal y Viewer — patron PageNumber (Flet 1.0.1).
    # ft.InteractiveViewer NO renderiza este Stack en 1.0.1 (fondo gris incluso
    # con su config exacta de 0.28.2) -> fuera. Pan manual con GestureDetector y
    # zoom aparcado para Fase 2, igual que PageNumber/ui/interactive_viewer.py
    # (zoom manual por redimension + pan por offsets, sin ft.InteractiveViewer).
    # El Stack lleva width/height explicitos: todas sus capas estan posicionadas
    # (left/top) y sin tamano Flutter lo deja a 0x0. El pan mueve left/top del
    # GestureDetector dentro de viewer_stack, con clamp a los limites.
    stack_principal = ft.Stack()
    pan_offset = {"x": 0.0, "y": 0.0}
    pan_limits = {"min_x": 0.0, "max_x": 0.0, "min_y": 0.0, "max_y": 0.0}
    # Primera vez: centrar el contenido aunque nadie pida do_center (si no,
    # sale en la esquina sup-izq hasta el primer reset).
    _pan_centrado_inicial = {"hecho": False}
    # Ultimo zoom aplicado en el visor: al cambiar z se conserva el centro
    # visual (igual que PageNumber, que recentra el mismo punto en mm).
    _zoom_aplicado = {"z": None}

    def _on_viewer_pan_start(e=None):
        pass

    def _on_viewer_pan_update(e=None):
        try:
            _ld = getattr(e, "local_delta", None)
            # local_delta viene en el espacio del receptor (pre-transform): es
            # delta_pantalla / z. Pan y limites van en pixeles de pantalla ->
            # hay que devolverlo a pantalla multiplicando por el zoom aplicado.
            _zp = float(zoom_final.get("value", 1.0) or 1.0)
            dx = _ld.x * _zp * PAN_MULTIPLICADOR if _ld else 0
            dy = _ld.y * _zp * PAN_MULTIPLICADOR if _ld else 0
            if not dx and not dy:
                return
            nx = pan_offset["x"] + dx
            ny = pan_offset["y"] + dy
            pan_offset["x"] = max(pan_limits["min_x"], min(pan_limits["max_x"], nx))
            pan_offset["y"] = max(pan_limits["min_y"], min(pan_limits["max_y"], ny))
            gesture_viewer.left = pan_offset["x"]
            gesture_viewer.top = pan_offset["y"]
            try:
                gesture_viewer.update()
            except Exception as _e:
                print(f"[DIAG] pan update fallo: {type(_e).__name__}: {_e}")
        except Exception as _e:
            print(f"[DIAG] pan handler fallo: {type(_e).__name__}: {_e}")

    def _on_viewer_pan_end(e=None):
        pass

    def _fijar_limites_pan(w_px, h_px, centrar=False):
        """Limites del pan con formula unica (patron PageNumber adaptado):
        - Contenido mayor que el visor: min=viewer-w (negativo), max=0.
        - Contenido menor: min=0, max=viewer-w (se puede mover sin sacarlo).
        Posicion centrada = (viewer-w)/2 en ambos casos (si excede da negativo,
        igual que el -(big-viewer)/2 de PageNumber).
        Si centrar=True (do_center o primera vez), recentra; si no, sujeta el
        offset actual del usuario a los nuevos limites."""
        try:
            w = float(w_px)
            h = float(h_px)
            pan_limits["min_x"] = min(0.0, VIEWER_WIDTH - w)
            pan_limits["max_x"] = max(0.0, VIEWER_WIDTH - w)
            pan_limits["min_y"] = min(0.0, VIEWER_HEIGHT - h)
            pan_limits["max_y"] = max(0.0, VIEWER_HEIGHT - h)
            if centrar or not _pan_centrado_inicial.get("hecho", False):
                pan_offset["x"] = (VIEWER_WIDTH - w) / 2.0
                pan_offset["y"] = (VIEWER_HEIGHT - h) / 2.0
                _pan_centrado_inicial["hecho"] = True
            else:
                pan_offset["x"] = max(
                    pan_limits["min_x"], min(pan_limits["max_x"], pan_offset["x"])
                )
                pan_offset["y"] = max(
                    pan_limits["min_y"], min(pan_limits["max_y"], pan_offset["y"])
                )
            gesture_viewer.left = pan_offset["x"]
            gesture_viewer.top = pan_offset["y"]
        except Exception as _e:
            print(f"[DIAG] fijar fallo: {type(_e).__name__}: {_e}")

    gesture_viewer = ft.GestureDetector(
        content=stack_principal,
        on_pan_start=_on_viewer_pan_start,
        on_pan_update=_on_viewer_pan_update,
        on_pan_end=_on_viewer_pan_end,
        drag_interval=16,
        left=0.0,
        top=0.0,
    )
    viewer_stack = ft.Stack(
        controls=[gesture_viewer],
        expand=True,
    )

    def actualizar_viewer_zoom(do_center=False, skip_auto_zoom=False):
        """Dimensiona stack_principal y fija los limites del pan usando los últimos
        tamaños calculados por `actualizar_trazado`. Esta función permite cambiar
        el encaje sin volver a recalcular todo el trazado/JSON.
        """
        try:
            global LAST_GRUPO_W_MM, LAST_GRUPO_H_MM, LAST_TAMANO_TOTAL_W_MM, LAST_TAMANO_TOTAL_H_MM
            global zoom_level, zoom_final, AUTO_ZOOM, ESCALA_VISUAL
            # Preferir valores más recientes calculados; si faltan, usar TAMANO_FINAL_PLIEGO/TAMANO_TRAZADO
            trazado_w = LAST_GRUPO_W_MM or TAMANO_TRAZADO.get("w_mm") or 0
            trazado_h = LAST_GRUPO_H_MM or TAMANO_TRAZADO.get("h_mm") or 0
            tamano_total_w = (
                LAST_TAMANO_TOTAL_W_MM or TAMANO_FINAL_PLIEGO.get("w_mm") or trazado_w
            )
            tamano_total_h = (
                LAST_TAMANO_TOTAL_H_MM or TAMANO_FINAL_PLIEGO.get("h_mm") or trazado_h
            )

            # Si no hay dimensiones válidas, no tocar el viewer
            if (not trazado_w or not trazado_h) and (
                not tamano_total_w or not tamano_total_h
            ):
                return

            # Intentar leer directamente el valor del slider (si está disponible)
            try:
                try:
                    sv = float(zoom_slider.value)
                except Exception:
                    sv = float(zoom_level.get("value", 1.0))
                try:
                    zoom_level["value"] = round(sv, 2)
                except Exception:
                    pass
                print(
                    f"[DEBUG VIEWER_ZOOM] zoom_slider={getattr(zoom_slider, 'value', 'NA')} zoom_level={zoom_level.get('value')} | trazado={trazado_w:.1f}×{trazado_h:.1f} mm | tamano_total={tamano_total_w:.1f}×{tamano_total_h:.1f} mm"
                )
            except Exception:
                # Si no existe zoom_slider o falla, mantener zoom_level
                try:
                    print(
                        f"[DEBUG VIEWER_ZOOM] zoom_slider=NA zoom_level={zoom_level.get('value')} | trazado={trazado_w:.1f}×{trazado_h:.1f} mm"
                    )
                except Exception:
                    pass

            # Calcular zoom final con helper existente
            # Usar directamente el valor del slider si está disponible (más fiable)
            try:
                factor_val = 1.0
                try:
                    try:
                        factor_val = float(zoom_slider.value)
                    except Exception:
                        factor_val = float(zoom_level.get("value", 1.0))
                except Exception:
                    factor_val = float(zoom_level.get("value", 1.0))

                # Mantener zoom_level sincronizado
                try:
                    zoom_level["value"] = round(factor_val, 2)
                except Exception:
                    pass

                # Calcular zoom automático y final directamente para evitar
                # ambigüedades en la resolución de la función `compute_zoom_final`.
                try:
                    papel_w_px = float(tamano_total_w) * float(ESCALA_VISUAL)
                    papel_h_px = float(tamano_total_h) * float(ESCALA_VISUAL)
                except Exception:
                    papel_w_px = max(1.0, float(tamano_total_w or 1.0)) * float(
                        ESCALA_VISUAL
                    )
                    papel_h_px = max(1.0, float(tamano_total_h or 1.0)) * float(
                        ESCALA_VISUAL
                    )

                try:
                    z_auto, m_h, m_v = calc_viewer_scale_and_boundary(
                        papel_w_px,
                        papel_h_px,
                        VIEWER_WIDTH,
                        VIEWER_HEIGHT,
                        correction_factor=1,
                    )
                except Exception:
                    z_auto = 1.0
                    m_h = 0
                    m_v = 0

                try:
                    z_final = round(float(z_auto) * float(factor_val), 3)
                except Exception:
                    z_final = round(float(z_auto), 3)
            except Exception:
                z_final = zoom_final.get("value", 1.0)
                m_h = 0
                m_v = 0

            try:
                print(
                    f"[DEBUG VIEWER_ZOOM] compute -> z_final={z_final}, m_h={m_h}, m_v={m_v}, z_auto={z_auto if 'z_auto' in locals() else 'NA'}"
                )
            except Exception:
                pass

            zoom_final["value"] = z_final

            # Tamano explicito del contenido (patron PageNumber): todas las capas
            # del Stack estan posicionadas (left/top) y sin width/height Flutter
            # lo deja a 0x0 -> nada pinta.
            try:
                papel_w_px = float(tamano_total_w) * float(ESCALA_VISUAL)
                papel_h_px = float(tamano_total_h) * float(ESCALA_VISUAL)
                stack_principal.width = papel_w_px
                stack_principal.height = papel_h_px
            except Exception:
                papel_w_px = 0.0
                papel_h_px = 0.0

            # Zoom Fase 2: `transform` + Matrix4 con origen TOP_LEFT.
            # Con origen arriba-izquierda, left/top es la esquina visual de la
            # caja ampliada, que es lo que calcula `_fijar_limites_pan`.
            # (con CENTER el escalado pivotaba en el centro de la caja SIN
            # ampliar y mezclaba dos sistemas de coordenadas: descentrado).
            try:
                _zt = float(zoom_final.get("value", 1.0))
                if _zt and _zt != 1.0:
                    gesture_viewer.transform = ft.Transform(
                        matrix=ft.Matrix4.diagonal3_values(_zt, _zt, 1.0),
                        alignment=ft.Alignment.TOP_LEFT,
                    )
                else:
                    gesture_viewer.transform = None
            except Exception as _e:
                print(f"[ZOOM T2] fallo aplicando transform: {type(_e).__name__}: {_e}")

            # Limites del pan (patron PageNumber) con el tamano MAGNIFICADO:
            # si el contenido ampliado excede el visor se puede desplazar hasta
            # mostrar el borde; si cabe entero, se puede mover sin sacarlo.
            # do_center (p. ej. boton reset) recentra; si no, se conserva el
            # arrastre del usuario sujetandolo a los nuevos limites.
            try:
                _zl = float(zoom_final.get("value", 1.0))
            except Exception:
                _zl = 1.0
            # Conservar el centro visual al cambiar el zoom: desplazar el pan
            # lo mismo que crece el contenido (w*(z_old-z_new)/2). Sin esto, el
            # clamp de _fijar_limites_pan lleva el pliego a la esquina sup-izq.
            try:
                _z_prev = _zoom_aplicado.get("z")
                if (
                    _z_prev
                    and _zl != _z_prev
                    and not do_center
                    and papel_w_px > 0
                    and papel_h_px > 0
                ):
                    pan_offset["x"] += papel_w_px * (_z_prev - _zl) / 2.0
                    pan_offset["y"] += papel_h_px * (_z_prev - _zl) / 2.0
                _zoom_aplicado["z"] = _zl
            except Exception:
                pass
            _fijar_limites_pan(papel_w_px * _zl, papel_h_px * _zl, centrar=bool(do_center))

            try:
                if "viewer_container" in globals():
                    try:
                        viewer_container.update()
                    except Exception as _e:
                        print(
                            f"[DIAG] viewer_container.update fallo: "
                            f"{type(_e).__name__}: {_e}"
                        )
            except Exception as _e:
                print(f"[DIAG] bloque viewer_container fallo: {type(_e).__name__}: {_e}")

            try:
                gesture_viewer.update()
            except Exception as _e:
                print(f"[DIAG] gesture_viewer.update fallo: {type(_e).__name__}: {_e}")

            try:
                if "stack_principal" in globals() and stack_principal:
                    try:
                        stack_principal.update()
                    except Exception as _e:
                        print(f"[DIAG] stack.update fallo: {type(_e).__name__}: {_e}")
                    # Intentar actualizar controles internos (capas)
                    try:
                        for c in getattr(stack_principal, "controls", []):
                            try:
                                c.update()
                            except Exception as _e:
                                if DEBUG_IMPO_UI:
                                    print(
                                        f"[DIAG] capa.update fallo: {type(_e).__name__}: {_e}"
                                    )
                                break
                    except Exception as _e:
                        print(f"[DIAG] loop capas fallo: {type(_e).__name__}: {_e}")

            except Exception as _e:
                print(f"[DIAG] bloque stack fallo: {type(_e).__name__}: {_e}")

            try:
                print(f"✅ Viewer actualizado: zoom={zoom_final['value']}")
            except Exception:
                pass
        except Exception as e:
            print(f"[ERROR] actualizar_viewer_zoom: {e}")

    # Controles de Grid
    textfield_grid_cols = ft.TextField(
        label=t("Cols"),
        value=str(GRID_COLS),
        width=60,
        height=48,
        text_size=14,
        content_padding=ft.Padding(8, 0, 0, 0),
        color=TEXTOS_FASE_1_COLOR,
        bgcolor=FONDO_TEXTFIELDS_COLOR,
        border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)),
        text_vertical_align=ft.VerticalAlignment.CENTER,
    )
    textfield_grid_rows = ft.TextField(
        label=t("Rows"),
        value=str(GRID_ROWS),
        width=60,
        height=48,
        text_size=14,
        content_padding=ft.Padding(8, 0, 0, 0),
        color=TEXTOS_FASE_1_COLOR,
        bgcolor=FONDO_TEXTFIELDS_COLOR,
        border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)),
        text_vertical_align=ft.VerticalAlignment.CENTER,
    )

    # Auto-generar valores de calles según el grid actual (verticales primero, luego horizontales)
    # SOLO si CALLES_L está vacío (no fue restaurado del estado)
    try:
        n_v = max(0, GRID_COLS - 1)
        n_h = max(0, GRID_ROWS - 1)

        # Solo generar calles si CALLES_L está vacío o tiene longitud incorrecta
        expected_len = n_v + n_h
        if not CALLES_L or len(CALLES_L) != expected_len:
            # Valores por defecto para calles (mm) - se pueden ajustar más tarde desde la UI
            default_calles_vert = 0
            default_calles_horiz = 0
            CALLES_L = [default_calles_vert] * n_v + [default_calles_horiz] * n_h
            print(f"[IMPO_UI] CALLES generadas por defecto: {CALLES_L}")
        else:
            print(f"[IMPO_UI] CALLES conservadas del estado: {CALLES_L}")
    except Exception as ex:
        print(f"[ERROR] Error generando calles: {ex}")

    # Controles de Offsets Imagen
    textfield_offset_img_x = ft.TextField(
        label=t("Off Img X"),
        value=str(USER_OFFSET_IMAGEN_X_MM),
        width=120,
        height=48,
        text_size=16,
        text_align=ft.TextAlign.LEFT,
        text_vertical_align=ft.VerticalAlignment.CENTER,
        content_padding=ft.Padding(8, 0, 0, 0),
        color=TEXTOS_FASE_1_COLOR,
        bgcolor=FONDO_TEXTFIELDS_COLOR,
        border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)),
        focused_color=None,
        focused_bgcolor=None,
        text_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
        label_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
    )
    textfield_offset_img_y = ft.TextField(
        label=t("Off Img Y"),
        value=str(USER_OFFSET_IMAGEN_Y_MM),
        width=120,
        height=48,
        text_size=16,
        text_align=ft.TextAlign.LEFT,
        text_vertical_align=ft.VerticalAlignment.CENTER,
        content_padding=ft.Padding(8, 0, 0, 0),
        color=TEXTOS_FASE_1_COLOR,
        bgcolor=FONDO_TEXTFIELDS_COLOR,
        border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)),
        focused_color=None,
        focused_bgcolor=None,
        text_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
        label_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
    )

    # Controles de Offsets Trazado
    textfield_offset_trazado_x = ft.TextField(
        label=t("Off Traz X"),
        value=str(USER_OFFSET_TRAZADO_X_MM),
        width=160,
        height=48,
        text_size=16,
        text_align=ft.TextAlign.LEFT,
        text_vertical_align=ft.VerticalAlignment.CENTER,
        content_padding=ft.Padding(8, 0, 0, 0),
        color=TEXTOS_FASE_1_COLOR,
        bgcolor=FONDO_TEXTFIELDS_COLOR,
        border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)),
        focused_color=None,
        focused_bgcolor=None,
        text_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
        label_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
    )
    textfield_offset_trazado_y = ft.TextField(
        label=t("Off Traz Y"),
        value=str(USER_OFFSET_TRAZADO_Y_MM),
        width=160,
        height=48,
        text_size=16,
        text_align=ft.TextAlign.LEFT,
        text_vertical_align=ft.VerticalAlignment.CENTER,
        content_padding=ft.Padding(8, 0, 0, 0),
        color=TEXTOS_FASE_1_COLOR,
        bgcolor=FONDO_TEXTFIELDS_COLOR,
        border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)),
        focused_color=None,
        focused_bgcolor=None,
        text_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
        label_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
    )

    # Controles de Cruces
    # TEXTFIELDS ELIMINADOS - SE USA DIALOGO

    # Checkboxes
    # Checkboxes (Restaurados de trazado_ui.py)
    # Usar los mismos colores que los TextFields para mantener coherencia visual
    global checkbox_cruces, checkbox_lineas_corte, checkbox_marcas_texto, checkbox_linea_exterior

    checkbox_cruces = ft.Checkbox(
        label=t("Cruces y marcas"),
        value=False,
        active_color=BORDE_TEXTFIELDS_COLOR,
        check_color=TEXTOS_FASE_1_COLOR,
        label_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
        fill_color=BOTONES_GENERICOS_FONDO_COLOR,
    )
    checkbox_lineas_corte = ft.Checkbox(
        label=t("Línea de Corte"),
        value=False,
        active_color=BORDE_TEXTFIELDS_COLOR,
        check_color=TEXTOS_FASE_1_COLOR,
        label_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
        fill_color=BOTONES_GENERICOS_FONDO_COLOR,
    )
    checkbox_marcas_texto = ft.Checkbox(
        label=t("Marcas de texto"),
        value=False,
        active_color=BORDE_TEXTFIELDS_COLOR,
        check_color=TEXTOS_FASE_1_COLOR,
        label_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
        fill_color=BOTONES_GENERICOS_FONDO_COLOR,
    )
    checkbox_linea_exterior = ft.Checkbox(
        label=t("Línea exterior"),
        value=True,
        active_color=BORDE_TEXTFIELDS_COLOR,
        check_color=TEXTOS_FASE_1_COLOR,
        label_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
        fill_color=BOTONES_GENERICOS_FONDO_COLOR,
    )

    # Botones Zoom
    def zoom_in(e):
        zoom_level["value"] = min(5.0, zoom_level["value"] * 1.2)
        user_changed_zoom["value"] = True
        print(f"🔍 ZOOM IN: factor={zoom_level['value']:.3f}")
        # Solo actualizar viewer (no recalcular trazado ni exportar JSON)
        try:
            actualizar_viewer_zoom()
        except Exception:
            pass

    def zoom_out(e):
        # El zoom mínimo es 1.0 (zoom automático)
        # No se puede hacer zoom OUT más allá del zoom automático
        zoom_level["value"] = max(1.0, zoom_level["value"] / 1.2)
        user_changed_zoom["value"] = True
        print(f"🔍 ZOOM OUT: factor={zoom_level['value']:.3f}")
        # Solo actualizar viewer (no recalcular trazado ni exportar JSON)
        try:
            actualizar_viewer_zoom()
        except Exception:
            pass

    def reset_zoom(e):
        zoom_level["value"] = 1.0
        user_changed_zoom["value"] = False
        print(f"🔄 RESET ZOOM: factor={zoom_level['value']:.3f}")
        # Sincronizar slider y forzar viewer a escala absoluta 1.0 y centrar
        try:
            safe_set_zoom_slider(1.0)
        except Exception:
            pass
        try:
            actualizar_viewer_zoom(do_center=True, skip_auto_zoom=True)
        except Exception:
            pass

    boton_zoom_in = ft.IconButton(
        icon=ft.Icons.ZOOM_IN,
        on_click=zoom_in,
        icon_color=TEXTOS_FASE_1_COLOR,
        visible=True,
    )
    boton_zoom_out = ft.IconButton(
        icon=ft.Icons.ZOOM_OUT,
        on_click=zoom_out,
        icon_color=TEXTOS_FASE_1_COLOR,
        visible=True,
    )

    boton_reset_zoom = ft.IconButton(
        icon=ft.Icons.CENTER_FOCUS_STRONG,
        icon_size=30,
        on_click=reset_zoom,
        icon_color=TEXTOS_FASE_1_COLOR,
        tooltip=t("Resetear zoom y centrar"),
        visible=True,
    )

    # Flag para cambios programaticos: safe_set_zoom_slider lo activa para que
    # _slider_on_change ignore el evento. Asi NO se toca nunca on_change (en
    # Flet 1.0 desuscribirlo con on_change=None + update() lo deja muerto en el
    # cliente, porque tras reasignar el handler no se hacia update()).
    _slider_programmatic = {"v": False}

    # Slider de zoom (similar a PageNumber)
    def _slider_on_change(e):
        if _slider_programmatic.get("v"):
            return
        try:
            v = float(e.control.value)
        except Exception:
            return
        # Normalizar a 2 decimales
        v = round(v, 2)
        zoom_level["value"] = v
        # Marcar que el usuario ha cambiado el zoom y poner un timer para resetearlo
        user_changed_zoom["value"] = True

        # Zoom en vivo como PageNumber (set_zoom_live): aplicar ya durante el
        # arrastre; el timer de abajo confirma el estado final al soltar.
        try:
            actualizar_viewer_zoom()
        except Exception:
            pass

        # Cancelar timer previo si existe
        try:
            prev = user_changed_zoom_reset.get("timer")
            if prev is not None:
                try:
                    prev.cancel()
                except Exception:
                    pass
        except Exception:
            pass

        # Crear nuevo timer que resetee el flag pasado un breve intervalo
        def _reset_user_changed_flag(seq):
            try:
                # Solo aplicar si la secuencia coincide (timer vigente)
                if seq != user_changed_zoom_seq.get("v"):
                    return
                user_changed_zoom["value"] = False
            except Exception:
                pass
            try:
                user_changed_zoom_reset["timer"] = None
            except Exception:
                pass

            # Al terminar la interacción del usuario, actualizar el viewer
            # para aplicar el centrado final con el valor actual del slider.
            try:
                # No centrar automáticamente al soltar el slider.
                actualizar_viewer_zoom()
            except Exception:
                pass

        try:
            # Capturar la secuencia actual y pasarla al timer
            seq = user_changed_zoom_seq.get("v", 0)
            t = threading.Timer(0.5, _reset_user_changed_flag, args=(seq,))
            t.daemon = True
            user_changed_zoom_reset["timer"] = t
            t.start()
        except Exception:
            # Si falla el timer, asegurarse de que el flag se pueda resetear manualmente más tarde
            try:
                user_changed_zoom["value"] = False
            except Exception:
                pass

        print(f"🔍 SLIDER ZOOM: factor={zoom_level['value']:.3f}")
        try:
            # Solo actualizar el viewer (no recalcular trazado ni exportar JSON)
            actualizar_viewer_zoom()
        except Exception:
            pass

    zoom_slider = ft.Slider(
        min=1.0,
        max=5.0,
        width=250,
        height=18,
        value=zoom_level.get("value", 1.0),
        divisions=40,
        on_change=_slider_on_change,
    )

    def safe_set_zoom_slider(val):
        """Setea el valor del `zoom_slider` de forma segura:
        - No sobrescribe si `user_changed_zoom` está activo.
        - Marca `_slider_programmatic` para que `on_change` ignore el evento
          (sin desuscribir el handler, que en Flet 1.0 lo deja muerto).
        - Clampea el valor al rango del slider y actualiza `zoom_level`.
        """
        try:
            if user_changed_zoom.get("value", False):
                if DEBUG_IMPO_UI:
                    print(
                        "🔒 safe_set_zoom_slider: omitiendo por user_changed_zoom=True"
                    )
                return
        except Exception:
            pass

        _slider_programmatic["v"] = True
        try:
            min_v = getattr(zoom_slider, "min", 1.0)
            max_v = getattr(zoom_slider, "max", 5.0)
            try:
                v = max(float(min_v), min(float(max_v), round(float(val), 2)))
            except Exception:
                v = round(float(val), 2)
            zoom_slider.value = v
            zoom_level["value"] = v
            try:
                zoom_slider.update()
            except Exception:
                pass
        except Exception:
            pass
        finally:
            _slider_programmatic["v"] = False

    # Estado y control de navegación de pliegos
    # state_pliego: índice 0-based e total de pliegos
    state_pliego = {"index": 0, "total": 0}

    # Texto que muestra el total de pliegos. Se colocará en la fila de controles (derecha)
    texto_total_pliegos = ft.Text(f"", size=14, color=TEXTO_COLOR_GENERICO)

    def actualizar_total_pliegos(total_imgs: int, rows_calc: int, cols_calc: int):
        """
        Calcula y actualiza `state_pliego['total']` y el widget `texto_total_pliegos`.
        Tiene en cuenta el modo doble cara (usa `ordenamiento_calculado` o `dropdown_doble_cara`).
        """
        # ✅ PRIORIDAD: Consultar índice completo de pdf_ordenado_ui si existe
        total_pliegos_desde_indice = obtener_total_pliegos_indice()

        if total_pliegos_desde_indice > 0:
            # Usar el índice completo creado en pdf_ordenado_ui
            # print(f"[ÍNDICE COMPLETO] Usando total de pliegos desde índice: {total_pliegos_desde_indice}")
            nuevo_total = total_pliegos_desde_indice

            # Detectar modo doble cara desde ordenamiento
            es_modo_doble = False
            try:
                orden = ordenamiento_calculado.get("ordenamiento", {})
                if orden:
                    es_modo_doble = any(
                        _es_dorso_val(v.get("doble_cara"))
                        for k, v in orden.items()
                        if isinstance(k, int) and isinstance(v, dict)
                    )
            except Exception:
                es_modo_doble = False

            # Para navegación: cada pliego es una página navegable
            state_pliego["total"] = max(1, nuevo_total)
            display_total = nuevo_total
        else:
            # FALLBACK: Calcular desde imágenes cargadas (legacy)
            print(f"[CÁLCULO LEGACY] Calculando total desde imágenes: {total_imgs}")
            try:
                celdas_por_pliego = max(1, int(rows_calc) * int(cols_calc))
            except Exception:
                celdas_por_pliego = 1

            # Detectar modo doble cara usando el ordenamiento si está disponible
            es_modo_doble = False
            try:
                orden = ordenamiento_calculado.get("ordenamiento", {})
                if orden:
                    es_modo_doble = any(
                        _es_dorso_val(v.get("doble_cara"))
                        for k, v in orden.items()
                        if isinstance(k, int) and isinstance(v, dict)
                    )
                else:
                    es_modo_doble = bool(dropdown_doble_cara.value) and str(
                        dropdown_doble_cara.value
                    ).lower().startswith("d")
            except Exception:
                es_modo_doble = False

            import math

            divisor = celdas_por_pliego * (2 if es_modo_doble else 1)
            nuevo_total = math.ceil(max(0, int(total_imgs)) / max(1, int(divisor)))

            # IMPORTANTE: state_pliego["total"] debe contener el número total de PÁGINAS navegables
            # Para doble cara, esto es el doble del número de pliegos físicos
            # porque navegamos por cada cara individualmente (cara y dorso)
            if es_modo_doble:
                # En doble cara: nuevo_total ya es el número de pliegos físicos
                # Necesitamos multiplicar por 2 para obtener el número de páginas navegables
                state_pliego["total"] = max(1, nuevo_total * 2)
                display_total = nuevo_total  # Mostrar el número de pliegos físicos
            else:
                # En una cara: cada página es un pliego
                state_pliego["total"] = max(1, nuevo_total)
                display_total = nuevo_total

        # ✅ GUARDAR display_total en state_pliego para usarlo en el diálogo de éxito
        state_pliego["display_total"] = display_total

        try:
            if es_modo_doble:
                # Mostrar texto específico para doble cara
                texto_total_pliegos.value = t("{0} Pliegos doble cara.").format(
                    display_total
                )
            else:
                # Texto para impresión a una sola cara
                texto_total_pliegos.value = t("{0} Pliegos.").format(display_total)

            texto_total_pliegos.update()
        except Exception:
            pass

        # Debug
        try:
            print(
                f"[DEBUG PLIEGOS] total_imgs={total_imgs}, rows={rows_calc}, cols={cols_calc}, celdas_por_pliego={celdas_por_pliego}, es_modo_doble={es_modo_doble} -> state_total={state_pliego.get('total')} display_total={display_total}"
            )
        except Exception:
            pass

    # Street configuration is now done directly in textfield_medianil (comma-separated values)
    # No need for a separate dialog anymore

    # Controles de Tamaño de Usuario
    textfield_tamano_usuario_w = ft.TextField(
        label=t("Ancho ({0})").format(get_unit_abbr(_initial_unit_pref)),
        value=str(TAMANO_USUARIO_W),
        width=110,
        height=40,
        text_size=16,
        text_align=ft.TextAlign.LEFT,
        text_vertical_align=ft.VerticalAlignment.CENTER,
        content_padding=ft.Padding(8, 0, 0, 0),
        color=TEXTOS_FASE_1_COLOR,
        bgcolor=FONDO_TEXTFIELDS_COLOR,
        border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)),
        focused_color=None,
        focused_bgcolor=None,
        text_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
        label_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
    )
    textfield_tamano_usuario_h = ft.TextField(
        label=t("Alto ({0})").format(get_unit_abbr(_initial_unit_pref)),
        value=str(TAMANO_USUARIO_H),
        width=110,
        height=40,
        text_size=16,
        text_align=ft.TextAlign.LEFT,
        text_vertical_align=ft.VerticalAlignment.CENTER,
        content_padding=ft.Padding(8, 0, 0, 0),
        color=TEXTOS_FASE_1_COLOR,
        bgcolor=FONDO_TEXTFIELDS_COLOR,
        border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)),
        focused_color=None,
        focused_bgcolor=None,
        text_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
        label_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
    )

    # Controles para información del PDF (MediaBox, TrimBox, BleedBox)
    texto_info_pdf_mediabox = ft.Text(
        t("Total: -"),
        size=11,
        color=TEXTOS_FASE_1_COLOR,
        text_align=ft.TextAlign.CENTER,
    )
    texto_info_pdf_trimbox = ft.Text(
        t("Corte: -"),
        size=11,
        color=TEXTOS_FASE_1_COLOR,
        text_align=ft.TextAlign.CENTER,
    )
    texto_info_pdf_bleedbox = ft.Text(
        t("Sangre: -"),
        size=11,
        color=TEXTOS_FASE_1_COLOR,
        text_align=ft.TextAlign.CENTER,
    )

    # Exportar variables del container verde para acceso desde update_units
    globals()["texto_info_pdf_mediabox"] = texto_info_pdf_mediabox
    globals()["texto_info_pdf_trimbox"] = texto_info_pdf_trimbox
    globals()["texto_info_pdf_bleedbox"] = texto_info_pdf_bleedbox

    container_info_pdf = ft.Container(
        content=ft.Column(
            [
                ft.Text(
                    t("Tamaño del PDF"),
                    size=10,
                    weight=ft.FontWeight.BOLD,
                    color=TEXTOS_FASE_1_COLOR,
                ),
                ft.Divider(height=2, thickness=1, color=BORDE_TEXTFIELDS_COLOR),
                texto_info_pdf_mediabox,
                texto_info_pdf_trimbox,
                texto_info_pdf_bleedbox,
            ],
            spacing=2,
            alignment=ft.MainAxisAlignment.CENTER,
        ),
        bgcolor=FONDO_TEXTFIELDS_COLOR,
        padding=8,
        border_radius=6,
        alignment=ft.Alignment.CENTER,
        width=200,
        border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
    )

    # Actualizar el color de fondo del contenedor según el valor de 'sangre'
    def _actualizar_bg_container_info_pdf(e=None):
        try:
            val = 0.0

            # Intentar leer la sangre desde el texto informativo del PDF (soporta varios idiomas)
            try:
                if texto_info_pdf_bleedbox and texto_info_pdf_bleedbox.value:
                    import re

                    texto = str(texto_info_pdf_bleedbox.value)
                    # Buscar un número seguido de "mm" (p. ej. "Sangre: 3.0 mm" o "Bleed: 3,0 mm")
                    m = re.search(r"([-+]?\d+[\.,]?\d*)\s*mm", texto, re.IGNORECASE)
                    if m:
                        numero_str = m.group(1).replace(",", ".")
                        val = float(numero_str)
                    else:
                        # Si no aparece "mm", intentar extraer cualquier número presente
                        m2 = re.search(r"([-+]?\d+[\.,]?\d*)", texto)
                        if m2:
                            numero_str = m2.group(1).replace(",", ".")
                            val = float(numero_str)
            except Exception:
                # Si falla, usar la variable global SANGRE (en mm) como fallback
                try:
                    val = (
                        float(SANGRE)
                        if "SANGRE" in globals() and SANGRE is not None
                        else 0.0
                    )
                except Exception:
                    val = 0.0

            # Si la sangre es exactamente 0 -> mostrar fondo de error (rojo/naranja)
            if val == 0.0:
                container_info_pdf.bgcolor = ERROR_COLOR
            else:
                # Si hay sangre -> mostrar fondo verde
                container_info_pdf.bgcolor = SUCCESS_COLOR
            try:
                container_info_pdf.update()
            except Exception:
                pass
        except Exception:
            pass

    # Vincular al evento on_change del TextField de sangre y ejecutar una vez al crear
    try:
        textfield_sangre.on_change = _actualizar_bg_container_info_pdf
    except Exception:
        # En versiones antiguas de flet puede ser on_change diferente; ignorar si falla
        pass

    # Ejecutar inicialmente para reflejar el valor por defecto
    try:
        _actualizar_bg_container_info_pdf()
    except Exception:
        pass

    # Exportar la función al ámbito global para que pueda ser llamada desde trabajo_manager.py
    globals()["_actualizar_bg_container_info_pdf"] = _actualizar_bg_container_info_pdf
    globals()["container_info_pdf"] = container_info_pdf

    # --- Unit handling: actualizar labels/valores según unidad seleccionada ---
    def _safe_float_from_str(s):
        try:
            if s is None:
                return None
            s2 = str(s).strip().replace(",", ".")
            return float(s2)
        except Exception:
            return None

    # Inicializar referencias seguras para los campos de calles y valores asociados.
    # Estas variables se exportan desde `abrir_dialogo_calles` cuando el diálogo
    # está abierto; aquí las obtenemos desde `globals()` con fallback a listas
    # vacías para evitar errores de referencia y para que el linter/Pylance no
    # marque variables como "no definidas".
    try:
        vertical_street_fields = globals().get("vertical_street_fields", [])
    except Exception:
        vertical_street_fields = []
    try:
        horizontal_street_fields = globals().get("horizontal_street_fields", [])
    except Exception:
        horizontal_street_fields = []
    try:
        v_calles_values = globals().get("v_calles_values", [])
    except Exception:
        v_calles_values = []
    try:
        h_calles_values = globals().get("h_calles_values", [])
    except Exception:
        h_calles_values = []

    def update_units(new_unit=None):
        """Actualiza labels y valores mostrados en los textfields según la unidad.
        Internals siguen estando en mm; aquí convertimos para la UI.
        """
        try:
            unit = new_unit or _estado_impo_ui.get("unit") or _initial_unit_pref or "mm"
        except Exception:
            unit = "mm"

        # Actualizar labels visibles
        try:
            label_u = get_unit_abbr(unit)
            try:
                textfield_ancho.label = t("Ancho ({0})").format(label_u)
            except Exception:
                pass
            try:
                textfield_alto.label = t("Alto ({0})").format(label_u)
            except Exception:
                pass
            try:
                textfield_sangre.label = t("Sangre ({0})").format(label_u)
            except Exception:
                pass
            try:
                textfield_tamano_usuario_w.label = t("Ancho ({0})").format(label_u)
            except Exception:
                pass
            try:
                textfield_tamano_usuario_h.label = t("Alto ({0})").format(label_u)
            except Exception:
                pass
        except Exception:
            pass

        # Actualizar valores mostrados convirtiendo desde mm -> unidad seleccionada
        try:
            # Pliego ancho/alto desde estado
            pliego_ancho_mm = _estado_impo_ui.get("pliego_ancho", None)
            pliego_alto_mm = _estado_impo_ui.get("pliego_alto", None)
            if pliego_ancho_mm is not None:
                try:
                    textfield_ancho.value = (
                        f"{convert_from_mm(float(pliego_ancho_mm), unit):.2f}"
                    )
                    textfield_ancho.update()
                except Exception:
                    pass
            if pliego_alto_mm is not None:
                try:
                    textfield_alto.value = (
                        f"{convert_from_mm(float(pliego_alto_mm), unit):.2f}"
                    )
                    textfield_alto.update()
                except Exception:
                    pass

            # Sangre desde estado o variable global SANGRE
            sang_mm = _estado_impo_ui.get("sangre", None)
            if sang_mm is None:
                try:
                    sang_mm = float(SANGRE)
                except Exception:
                    sang_mm = None
            if sang_mm is not None:
                try:
                    textfield_sangre.value = (
                        f"{convert_from_mm(float(sang_mm), unit):.2f}"
                    )
                    textfield_sangre.update()
                except Exception:
                    pass

            # Tamaño usuario
            tam_w_mm = _estado_impo_ui.get("tamano_usuario_w", None)
            tam_h_mm = _estado_impo_ui.get("tamano_usuario_h", None)
            if tam_w_mm is None:
                try:
                    tam_w_mm = float(TAMANO_USUARIO_W)
                except Exception:
                    tam_w_mm = None
            if tam_h_mm is None:
                try:
                    tam_h_mm = float(TAMANO_USUARIO_H)
                except Exception:
                    tam_h_mm = None
            if tam_w_mm is not None:
                try:
                    textfield_tamano_usuario_w.value = (
                        f"{convert_from_mm(float(tam_w_mm), unit):.2f}"
                    )
                    textfield_tamano_usuario_w.update()
                except Exception:
                    pass
            if tam_h_mm is not None:
                try:
                    textfield_tamano_usuario_h.value = (
                        f"{convert_from_mm(float(tam_h_mm), unit):.2f}"
                    )
                    textfield_tamano_usuario_h.update()
                except Exception:
                    pass

            # Actualizar campos de separación (calles) si existen en este diálogo
            try:
                for idx, tf in enumerate(vertical_street_fields):
                    try:
                        val_mm = (
                            v_calles_values[idx] if idx < len(v_calles_values) else 0.0
                        )
                        tf.value = f"{convert_from_mm(float(val_mm), unit):.2f}"
                        tf.update()
                    except Exception:
                        pass
            except Exception:
                pass

            try:
                for idx, tf in enumerate(horizontal_street_fields):
                    try:
                        val_mm = (
                            h_calles_values[idx] if idx < len(h_calles_values) else 0.0
                        )
                        tf.value = f"{convert_from_mm(float(val_mm), unit):.2f}"
                        tf.update()
                    except Exception:
                        pass
            except Exception:
                pass

            # Offsets imagenes
            try:
                off_ix_mm = _estado_impo_ui.get("offset_img_x", None)
                if off_ix_mm is None:
                    try:
                        off_ix_mm = float(USER_OFFSET_IMAGEN_X_MM)
                    except Exception:
                        off_ix_mm = None
                if off_ix_mm is not None:
                    textfield_offset_img_x.value = (
                        f"{convert_from_mm(float(off_ix_mm), unit):.2f}"
                    )
                    textfield_offset_img_x.update()
            except Exception:
                pass
            try:
                off_iy_mm = _estado_impo_ui.get("offset_img_y", None)
                if off_iy_mm is None:
                    try:
                        off_iy_mm = float(USER_OFFSET_IMAGEN_Y_MM)
                    except Exception:
                        off_iy_mm = None
                if off_iy_mm is not None:
                    textfield_offset_img_y.value = (
                        f"{convert_from_mm(float(off_iy_mm), unit):.2f}"
                    )
                    textfield_offset_img_y.update()
            except Exception:
                pass

            # Offsets trazado
            try:
                off_tx_mm = _estado_impo_ui.get("offset_trazado_x", None)
                if off_tx_mm is None:
                    try:
                        off_tx_mm = float(USER_OFFSET_TRAZADO_X_MM)
                    except Exception:
                        off_tx_mm = None
                if off_tx_mm is not None:
                    textfield_offset_trazado_x.value = (
                        f"{convert_from_mm(float(off_tx_mm), unit):.2f}"
                    )
                    textfield_offset_trazado_x.update()
            except Exception:
                pass
            try:
                off_ty_mm = _estado_impo_ui.get("offset_trazado_y", None)
                if off_ty_mm is None:
                    try:
                        off_ty_mm = float(USER_OFFSET_TRAZADO_Y_MM)
                    except Exception:
                        off_ty_mm = None
                if off_ty_mm is not None:
                    textfield_offset_trazado_y.value = (
                        f"{convert_from_mm(float(off_ty_mm), unit):.2f}"
                    )
                    textfield_offset_trazado_y.update()
            except Exception:
                pass

        except Exception:
            pass

        # Actualizar textos del container verde (info PDF) directamente
        try:
            # Acceder a variables del container verde desde globals()
            mediabox_text = globals().get("texto_info_pdf_mediabox")
            trimbox_text = globals().get("texto_info_pdf_trimbox")
            bleedbox_text = globals().get("texto_info_pdf_bleedbox")

            if mediabox_text and trimbox_text and bleedbox_text:
                # Solo actualizar si hay datos del PDF cargados
                if (
                    _archivo_seleccionado.get("boxes_by_page")
                    and 0 in _archivo_seleccionado["boxes_by_page"]
                ):
                    boxes_p0 = _archivo_seleccionado["boxes_by_page"][0]
                    unit_label = get_unit_abbr(unit)

                    def fmt_box(box_tuple):
                        if not box_tuple or len(box_tuple) != 4:
                            return "-"
                        w_pt = box_tuple[2] - box_tuple[0]
                        h_pt = box_tuple[3] - box_tuple[1]
                        w_mm = w_pt * 0.352778
                        h_mm = h_pt * 0.352778

                        # Convertir a unidad seleccionada
                        w_converted = convert_from_mm(w_mm, unit)
                        h_converted = convert_from_mm(h_mm, unit)

                        return f"{w_converted:.2f} x {h_converted:.2f} {unit_label}"

                    # Actualizar Total (mediabox)
                    if boxes_p0.get("mediabox"):
                        mediabox_text.value = t("Total: {0}").format(
                            fmt_box(boxes_p0.get("mediabox"))
                        )
                        try:
                            mediabox_text.update()
                        except:
                            pass

                    # Actualizar Corte (trimbox)
                    if boxes_p0.get("trimbox"):
                        trimbox_text.value = t("Corte: {0}").format(
                            fmt_box(boxes_p0.get("trimbox"))
                        )
                        try:
                            trimbox_text.update()
                        except:
                            pass

                    # Actualizar Sangre (diferencia entre mediabox y trimbox)
                    try:
                        mb = boxes_p0.get("mediabox")
                        tb = boxes_p0.get("trimbox")
                        if mb and tb:
                            mb_w = mb[2] - mb[0]
                            tb_w = tb[2] - tb[0]
                            sangre_pt = (mb_w - tb_w) / 2
                            sangre_mm = sangre_pt * 0.352778
                            sangre_converted = convert_from_mm(sangre_mm, unit)

                            bleedbox_text.value = t("Sangre: {0}").format(
                                f"{sangre_converted:.2f} {unit_label}"
                            )
                            try:
                                bleedbox_text.update()
                            except:
                                pass
                        else:
                            bleedbox_text.value = t("Sangre: -")
                            try:
                                bleedbox_text.update()
                            except:
                                pass
                    except:
                        bleedbox_text.value = t("Sangre: -")
                        try:
                            bleedbox_text.update()
                        except:
                            pass
        except Exception:
            pass

        # Guardar unidad en estado para referencia
        try:
            _estado_impo_ui["unit"] = unit
        except Exception:
            pass

    # Exponer la función para que otros módulos (ej. preferencias) la llamen
    globals()["update_units_in_impo"] = update_units

    # Si hubo una petición pendiente antes de crear la UI, aplicarla ahora
    try:
        global _pending_unit_change
        if _pending_unit_change:
            try:
                update_units(_pending_unit_change)
            except Exception:
                pass
            _pending_unit_change = None
    except Exception:
        pass

    # ═══════════════════════════════════════════════════════════════════════════
    # LISTENERS PARA TAMAÑO DE USUARIO Y SANGRE - GUARDAR ESTADO
    # ═══════════════════════════════════════════════════════════════════════════

    # Último texto de pliego ya aplicado (dedupe Enter→blur encadenado:
    # Enter no desenfoca por defecto, y el blur posterior llegaría con el
    # mismo valor). Solo se aplica al salir del textfield (submit o blur).
    _pliego_textfield_aplicado = {"w": None, "h": None}

    def on_ancho_pliego_change(e):
        """Aplica ancho de pliego en modo manual (solo al salir: Enter o blur)"""
        global TAMANO_FINAL_PLIEGO, PLIEGO_CONGELADO
        try:
            if PLIEGO_CONGELADO:
                raw = (e.control.value or "").strip()
                if raw == _pliego_textfield_aplicado["w"]:
                    return
                # Modo manual: convertir desde unidad del usuario a mm antes de guardar
                unit = _estado_impo_ui.get("unit", _initial_unit_pref)
                v = _safe_float_from_str(e.control.value)
                if v is None:
                    return
                mm = convert_to_mm(v, unit)
                TAMANO_FINAL_PLIEGO["w_mm"] = float(mm)
                guardar_estado_impo_ui()
                if _mark_modified_callback:
                    _mark_modified_callback()
                _pliego_textfield_aplicado["w"] = raw
                print(
                    f"[PLIEGO MANUAL] Ancho actualizado: {TAMANO_FINAL_PLIEGO['w_mm']}mm"
                )
                # Actualizar trazado con el nuevo tamaño
                actualizar_trazado(e)
            else:
                # Modo auto: solo actualizar si el usuario escribe, pero se recalculará automáticamente
                print(
                    f"[PLIEGO AUTO] Cambio en ancho ignorado - se recalculará automáticamente"
                )
        except (ValueError, AttributeError):
            pass

    def on_alto_pliego_change(e):
        """Aplica alto de pliego en modo manual (solo al salir: Enter o blur)"""
        global TAMANO_FINAL_PLIEGO, PLIEGO_CONGELADO
        try:
            if PLIEGO_CONGELADO:
                raw = (e.control.value or "").strip()
                if raw == _pliego_textfield_aplicado["h"]:
                    return
                # Modo manual: convertir desde unidad del usuario a mm antes de guardar
                unit = _estado_impo_ui.get("unit", _initial_unit_pref)
                v = _safe_float_from_str(e.control.value)
                if v is None:
                    return
                mm = convert_to_mm(v, unit)
                TAMANO_FINAL_PLIEGO["h_mm"] = float(mm)
                guardar_estado_impo_ui()
                if _mark_modified_callback:
                    _mark_modified_callback()
                _pliego_textfield_aplicado["h"] = raw
                print(
                    f"[PLIEGO MANUAL] Alto actualizado: {TAMANO_FINAL_PLIEGO['h_mm']}mm"
                )
                # Actualizar trazado con el nuevo tamaño
                actualizar_trazado(e)
            else:
                # Modo auto: solo actualizar si el usuario escribe, pero se recalculará automáticamente
                print(
                    f"[PLIEGO AUTO] Cambio en alto ignorado - se recalculará automáticamente"
                )
        except (ValueError, AttributeError):
            pass

    def on_tamano_usuario_w_change(e):
        """NO-OP durante edición: evitar recalcular en cada tecla.
        La acción de guardado/redibujo se realizará en on_submit."""
        return

    def on_tamano_usuario_w_submit(e):
        """Ejecuta la actualización final al confirmar (Enter/submit)."""
        global TAMANO_USUARIO_W
        try:
            unit = _estado_impo_ui.get("unit", _initial_unit_pref)
            v = _safe_float_from_str(e.control.value)
            if v is None:
                return
            mm = convert_to_mm(v, unit)
            TAMANO_USUARIO_W = float(mm)
            guardar_estado_impo_ui()
            if _mark_modified_callback:
                _mark_modified_callback()
            print(f"[TAMANO] Ancho actualizado: {TAMANO_USUARIO_W}mm")
            # Mostrar valor en la unidad seleccionada
            try:
                textfield_tamano_usuario_w.value = (
                    f"{convert_from_mm(TAMANO_USUARIO_W, unit):.2f}"
                )
                textfield_tamano_usuario_w.update()
            except Exception:
                pass
            # Actualizar trazado ahora que el usuario terminó de editar
            actualizar_trazado(e)
        except (ValueError, AttributeError):
            pass

    def on_tamano_usuario_h_change(e):
        """NO-OP durante edición: evitar recalcular en cada tecla."""
        return

    def on_tamano_usuario_h_submit(e):
        """Ejecuta la actualización final al confirmar (Enter/submit)."""
        global TAMANO_USUARIO_H
        try:
            unit = _estado_impo_ui.get("unit", _initial_unit_pref)
            v = _safe_float_from_str(e.control.value)
            if v is None:
                return
            mm = convert_to_mm(v, unit)
            TAMANO_USUARIO_H = float(mm)
            guardar_estado_impo_ui()
            if _mark_modified_callback:
                _mark_modified_callback()
            print(f"[TAMANO] Alto actualizado: {TAMANO_USUARIO_H}mm")
            try:
                textfield_tamano_usuario_h.value = (
                    f"{convert_from_mm(TAMANO_USUARIO_H, unit):.2f}"
                )
                textfield_tamano_usuario_h.update()
            except Exception:
                pass
            # Actualizar trazado ahora que el usuario terminó de editar
            actualizar_trazado(e)
        except (ValueError, AttributeError):
            pass

    def on_sangre_change(e):
        """Actualiza SANGRE y guarda estado"""
        global SANGRE
        try:
            unit = _estado_impo_ui.get("unit", _initial_unit_pref)
            v = _safe_float_from_str(e.control.value)
            if v is None:
                return
            mm = convert_to_mm(v, unit)
            SANGRE = float(mm)
            guardar_estado_impo_ui()
            if _mark_modified_callback:
                _mark_modified_callback()
            print(f"[TAMANO] Sangre actualizada: {SANGRE}mm")
            # También actualizar el background
            _actualizar_bg_container_info_pdf(e)
            # Mostrar valor en unidad seleccionada
            try:
                textfield_sangre.value = f"{convert_from_mm(SANGRE, unit):.2f}"
                textfield_sangre.update()
            except Exception:
                pass
            # Actualizar trazado automáticamente
            actualizar_trazado(e)
        except (ValueError, AttributeError):
            pass

    # Asignar listeners: solo al salir del textfield (Enter o perder foco),
    # sin auto-actualizar en cada tecla (paridad campos "Tamaño de usuario")
    textfield_ancho.on_submit = on_ancho_pliego_change
    textfield_ancho.on_blur = on_ancho_pliego_change
    textfield_alto.on_submit = on_alto_pliego_change
    textfield_alto.on_blur = on_alto_pliego_change
    # Para los campos de "Tamaño de usuario" evitar recalcular en cada tecla:
    # - on_change es NO-OP (evita redibujos continuos)
    # - on_submit procesa el valor final y recalcula/guarda
    try:
        textfield_tamano_usuario_w.on_change = on_tamano_usuario_w_change
        textfield_tamano_usuario_w.on_submit = on_tamano_usuario_w_submit
    except Exception:
        pass
    try:
        textfield_tamano_usuario_h.on_change = on_tamano_usuario_h_change
        textfield_tamano_usuario_h.on_submit = on_tamano_usuario_h_submit
    except Exception:
        pass
    # Reemplazar el listener de sangre con el nuevo que también guarda
    textfield_sangre.on_change = on_sangre_change

    # Botón AUTO/MANUAL para bloqueo de tamaño de pliego
    def toggle_auto_manual_pliego(e):
        """
        Alterna entre modo AUTO (descongela papel) y MANUAL (congela con valores actuales).
        Actualiza botón visualmente y recalcula trazado.
        """
        global PLIEGO_CONGELADO, TAMANO_FINAL_PLIEGO, boton_auto_manual_pliego

        PLIEGO_CONGELADO = not PLIEGO_CONGELADO

        if PLIEGO_CONGELADO:
            # Congelar con valores actuales - CONVERTIR DE UNIDAD USUARIO A MM
            try:
                unit = _estado_impo_ui.get("unit", _initial_unit_pref)
                w_usuario = _safe_float_from_str(textfield_ancho.value or "0")
                h_usuario = _safe_float_from_str(textfield_alto.value or "0")

                if w_usuario and w_usuario > 0 and h_usuario and h_usuario > 0:
                    w_mm = convert_to_mm(w_usuario, unit)
                    h_mm = convert_to_mm(h_usuario, unit)
                    TAMANO_FINAL_PLIEGO["w_mm"] = w_mm
                    TAMANO_FINAL_PLIEGO["h_mm"] = h_mm
                    print(
                        f"\n🔒 MODO MANUAL: Pliego congelado a {w_mm:.1f} × {h_mm:.1f}mm"
                    )
            except (ValueError, TypeError):
                print(f"❌ Valores inválidos en textfields")
                PLIEGO_CONGELADO = False
                TAMANO_FINAL_PLIEGO["w_mm"] = None
                TAMANO_FINAL_PLIEGO["h_mm"] = None
        else:
            # Descongelar a modo automático
            TAMANO_FINAL_PLIEGO["w_mm"] = None
            TAMANO_FINAL_PLIEGO["h_mm"] = None
            print(f"\n📐 MODO AUTO: Papel se recalculará automáticamente")

        # Actualizar botón visualmente (Flet 1.0: Button no tiene `.text`, usar `.content`)
        boton_auto_manual_pliego.content = (
            t("Tamaño manual") if PLIEGO_CONGELADO else t("Tamaño auto")
        )
        # Aplicar estilos de color acordes al tema (no usar black/white hardcoded)
        try:
            actualizar_estilo_boton_auto_manual()
        except Exception:
            boton_auto_manual_pliego.update()

        # Guardar estado después del cambio
        guardar_estado_impo_ui()
        mark_modified()

        # Recalcular inmediatamente
        print("\n🔄 RECALCULANDO trazado...\n")
        actualizar_trazado(None)

    global boton_auto_manual_pliego

    # Helper para aplicar el estilo del botón según el estado `PLIEGO_CONGELADO`
    def actualizar_estilo_boton_auto_manual():
        try:
            global boton_auto_manual_pliego
            if PLIEGO_CONGELADO:
                bg = BOTONES_GENERICOS_COLOR
                txt = BOTONES_GENERICOS_FONDO_COLOR
            else:
                bg = BOTONES_GENERICOS_FONDO_COLOR
                txt = BOTONES_GENERICOS_COLOR

            boton_auto_manual_pliego.bgcolor = bg
            boton_auto_manual_pliego.style = ft.ButtonStyle(
                color={ft.ControlState.DEFAULT: txt, "hovered": BOTONES_GENERICOS_HOVER_COLOR},
                overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                padding=ft.Padding(0, 0, 0, 0),
                shape=ft.RoundedRectangleBorder(radius=10),
            )
            boton_auto_manual_pliego.update()
        except Exception:
            try:
                boton_auto_manual_pliego.update()
            except Exception:
                pass

    boton_auto_manual_pliego = ft.Button(
        t("Tamaño auto"), on_click=toggle_auto_manual_pliego, width=140
    )
    # Aplicar estilo inicial según tema/stamp
    try:
        actualizar_estilo_boton_auto_manual()
    except Exception:
        pass

    # Actualizar texto del botón según estado congelado
    boton_auto_manual_pliego.content = (
        t("Tamaño manual") if PLIEGO_CONGELADO else t("Tamaño auto")
    )
    print(
        f"[DEBUG] Botón creado con texto: '{boton_auto_manual_pliego.content}' (PLIEGO_CONGELADO={PLIEGO_CONGELADO})"
    )

    # --- FUNCIONES HELPER PARA ZOOM Y BOUNDARY (Portadas de trazado_ui.py) ---
    def calc_viewer_scale_and_boundary(
        contenido_w_px, contenido_h_px, viewer_w_px, viewer_h_px, correction_factor=1
    ):
        """
        Calcula zoom automático para que el contenido encaje en el viewer.

        IMPORTANTE: Esta función calcula el zoom AUTOMÁTICO (min_scale).
        Los márgenes retornados son SIEMPRE 0 porque este zoom hace que el contenido
        encaje perfectamente en el viewer sin necesidad de movimiento.

        El boundary_margin real se calculará después en base al zoom FINAL aplicado.
        """
        # Evitar división por cero
        if contenido_w_px <= 0 or contenido_h_px <= 0:
            return 1.0, 0, 0

        # Calcular si el contenido cabe en ambas dimensiones
        # Restar padding del viewer para cálculo preciso (border + padding interno + margen visual ~30px por lado)
        viewer_effective_w = viewer_w_px - 60
        viewer_effective_h = viewer_h_px - 60

        cabe_en_ancho = contenido_w_px <= viewer_effective_w
        cabe_en_alto = contenido_h_px <= viewer_effective_h

        if cabe_en_ancho and cabe_en_alto:
            # Contenido cabe completamente
            zoom_w = viewer_effective_w / contenido_w_px if contenido_w_px > 0 else 1.0
            zoom_h = viewer_effective_h / contenido_h_px if contenido_h_px > 0 else 1.0
            zoom = min(zoom_w, zoom_h)
        else:
            # Contenido no cabe: reducir zoom para que quepa
            scale_w = viewer_effective_w / contenido_w_px if contenido_w_px > 0 else 1.0
            scale_h = viewer_effective_h / contenido_h_px if contenido_h_px > 0 else 1.0
            zoom = min(scale_w, scale_h)

        # ✅ CORRECCIÓN: Los márgenes retornados son 0 porque este zoom es el automático
        # El boundary_margin real se calculará después basándose en el zoom FINAL
        margen_h = 0
        margen_v = 0

        print(
            f"[MARGEN DEBUG] zoom_auto={zoom:.3f}, margen_inicial=0 (se calculará después con zoom final)"
        )
        print(f"  📐 DEBUG calc_viewer_scale_and_boundary:")
        print(f"     • papel: {contenido_w_px:.1f}×{contenido_h_px:.1f}px")
        print(f"     • viewer: {viewer_w_px:.1f}×{viewer_h_px:.1f}px")
        print(f"     • zoom_auto_calc: {zoom:.3f}")
        print(f"     • margen_h: {margen_h}, margen_v: {margen_v}")

        return round(zoom, 2), margen_h, margen_v

    def compute_zoom_final(
        papel_w_mm,
        papel_h_mm,
        viewer_w_px,
        viewer_h_px,
        escala=ESCALA_VISUAL,
        factor=1.0,
        correction_factor=1,
    ):
        """Calcula el zoom final y márgenes dinámicos para el viewer."""
        try:
            papel_w_px = float(papel_w_mm) * escala
            papel_h_px = float(papel_h_mm) * escala
        except Exception:
            papel_w_px = max(1.0, float(papel_w_mm or 1.0)) * escala
            papel_h_px = max(1.0, float(papel_h_mm or 1.0)) * escala

        zoom_auto, margen_h, margen_v = calc_viewer_scale_and_boundary(
            papel_w_px,
            papel_h_px,
            viewer_w_px,
            viewer_h_px,
            correction_factor=correction_factor,
        )

        # Aplicar factor
        try:
            zoom_final = round(float(zoom_auto) * float(factor), 3)
        except Exception:
            zoom_final = round(float(zoom_auto), 3)

        return zoom_final, int(margen_h), int(margen_v), zoom_auto

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # FUNCIONES PARA INVERSIÓN DE OFFSETS EN DORSO
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def determinar_si_es_dorso():
        """
        Determina si el pliego actual es DORSO basándose en el ordenamiento.

        Returns:
            bool: True si es DORSO, False si es CARA
        """
        try:
            ordenamiento = ordenamiento_calculado.get("ordenamiento", {})
            if not ordenamiento:
                return False

            # Obtener índice del pliego actual (0-based)
            current_index = state_pliego.get("index", 0)

            # El índice del pliego en ordenamiento es 1-based
            pliego_key = current_index + 1

            # Obtener datos del pliego actual
            pliego_data = ordenamiento.get(pliego_key, {})
            tipo_cara_dorso = pliego_data.get("doble_cara", "cara")

            es_dorso = tipo_cara_dorso == "dorso"
            # print(f"[DEBUG DORSO] Pliego {pliego_key}: tipo={tipo_cara_dorso}, es_dorso={es_dorso}")

            return es_dorso
        except Exception as ex:
            print(f"[ERROR] Error determinando CARA/DORSO: {ex}")
            return False

    # Función invertir_offsets_para_dorso ELIMINADA (Lógica integrada en actualizar_trazado)

    # Función principal de actualización
    def actualizar_trazado(e, skip_auto_zoom=False):
        """
        Función PRINCIPAL que recalcula todo el trazado y actualiza el stack.
        Se llama al cambiar cualquier parámetro.
        """
        print("Actualizando trazado...")

        global CALLES_L, GRID_COLS, GRID_ROWS, TAMANO_USUARIO_W, TAMANO_USUARIO_H, SANGRE, PLIEGO_CONGELADO, TAMANO_FINAL_PLIEGO
        global MARCA_TEXTO_CONTENIDO, MARCA_TEXTO_POS_SUP_IZQ, MARCA_TEXTO_POS_SUP_DER
        global MARCA_TEXTO_POS_INF_IZQ, MARCA_TEXTO_POS_INF_DER, MARCA_TEXTO_POS_CENTRO_SUP
        global MARCA_TEXTO_POS_CENTRO_INF, MARCA_TEXTO_POS_CENTRO_LAT_IZQ, MARCA_TEXTO_POS_CENTRO_LAT_DER
        global MARCA_TEXTO_ROTACION, MARCA_TEXTO_FAMILIA, MARCA_TEXTO_TIPO, MARCA_TEXTO_CUERPO
        global MARCA_TEXTO_COLOR, MARCA_TEXTO_OFFSET_H_MM, MARCA_TEXTO_OFFSET_V_MM

        # ✅ LÓGICA DE BLOQUEO AL INICIO: Si el usuario congeló el papel, leer y mantener tamaño
        if PLIEGO_CONGELADO:
            # El usuario congeló el tamaño → usar valores de los textfields CONVERTIDOS A MM
            print(f"\n🔒 MODO MANUAL: Pliego congelado")

            try:
                unit = _estado_impo_ui.get("unit", _initial_unit_pref)
                w_usuario_unit = _safe_float_from_str(textfield_ancho.value or "0")
                h_usuario_unit = _safe_float_from_str(textfield_alto.value or "0")

                if (
                    w_usuario_unit
                    and w_usuario_unit > 0
                    and h_usuario_unit
                    and h_usuario_unit > 0
                ):
                    w_usuario = convert_to_mm(w_usuario_unit, unit)
                    h_usuario = convert_to_mm(h_usuario_unit, unit)
                    print(
                        f"   Ancho (usuario en {unit}): {w_usuario_unit}, en mm: {w_usuario}"
                    )
                    print(
                        f"   Alto (usuario en {unit}): {h_usuario_unit}, en mm: {h_usuario}"
                    )

                    TAMANO_FINAL_PLIEGO["w_mm"] = w_usuario
                    TAMANO_FINAL_PLIEGO["h_mm"] = h_usuario
                    print(
                        f"   ✅ PAPEL BLOQUEADO a {w_usuario:.1f} × {h_usuario:.1f}mm"
                    )
            except ValueError:
                print(f"   ❌ Valores inválidos en textfield")
                PLIEGO_CONGELADO = False
                TAMANO_FINAL_PLIEGO["w_mm"] = None
                TAMANO_FINAL_PLIEGO["h_mm"] = None
        else:
            # Modo automático → DESBLOQUEAR
            # print(f"\n📐 MODO AUTOMÁTICO - Calculando tamaño dinámico")
            TAMANO_FINAL_PLIEGO["w_mm"] = None
            TAMANO_FINAL_PLIEGO["h_mm"] = None

        # 1. Leer valores de la UI
        try:
            # Grid
            g_cols = int(textfield_grid_cols.value)
            g_rows = int(textfield_grid_rows.value)

            # Tamaños usuario - USAR VARIABLES GLOBALES EN MM, NO TEXTFIELDS
            # Los textfields ahora muestran valores convertidos, pero los cálculos deben usar valores en mm
            t_ancho = TAMANO_USUARIO_W
            t_alto = TAMANO_USUARIO_H
            t_sangre = SANGRE

            # Actualizar globales de grid (no tamaño, ya están en mm)
            GRID_COLS = g_cols
            GRID_ROWS = g_rows
            # NO actualizar TAMANO_USUARIO_W/H/SANGRE aquí - ya están en mm y correctos

            # Parsear calles como cadena de comas (igual que trazado_ui.py líneas 3381-3384)
            # Formato: "calle1,calle2,..." → [calle1, calle2, ...]
            # YA NO SE LEE DEL TEXTFIELD, SE USA LA GLOBAL CALLES_L DIRECTAMENTE
            # Si CALLES_L está vacía o incorrecta, regenerar por defecto
            if not CALLES_L:
                CALLES_L = build_calles_list(0, g_cols, g_rows)

            # Offsets Imagen - Leer desde globales primero, fallback a textfields si existen
            try:
                off_img_x = USER_OFFSET_IMAGEN_X_MM
                off_img_y = USER_OFFSET_IMAGEN_Y_MM
            except NameError:
                # Fallback si las globales no existen - convertir desde textfields
                try:
                    unit = _estado_impo_ui.get("unit", _initial_unit_pref)
                    off_x_val = (
                        _safe_float_from_str(textfield_offset_img_x.value)
                        if textfield_offset_img_x.value
                        else 0.0
                    )
                    off_y_val = (
                        _safe_float_from_str(textfield_offset_img_y.value)
                        if textfield_offset_img_y.value
                        else 0.0
                    )
                    off_img_x = convert_to_mm(off_x_val, unit) if off_x_val else 0.0
                    off_img_y = convert_to_mm(off_y_val, unit) if off_y_val else 0.0
                except Exception:
                    off_img_x = 0.0
                    off_img_y = 0.0

            # Offsets Trazado - Leer desde globales primero, fallback a textfields si existen
            try:
                off_trazado_x = USER_OFFSET_TRAZADO_X_MM
                off_trazado_y = USER_OFFSET_TRAZADO_Y_MM
            except NameError:
                # Fallback si las globales no existen - convertir desde textfields
                try:
                    unit = _estado_impo_ui.get("unit", _initial_unit_pref)
                    off_x_val = (
                        _safe_float_from_str(textfield_offset_trazado_x.value)
                        if textfield_offset_trazado_x.value
                        else 0.0
                    )
                    off_y_val = (
                        _safe_float_from_str(textfield_offset_trazado_y.value)
                        if textfield_offset_trazado_y.value
                        else 0.0
                    )
                    off_trazado_x = convert_to_mm(off_x_val, unit) if off_x_val else 0.0
                    off_trazado_y = convert_to_mm(off_y_val, unit) if off_y_val else 0.0
                except Exception:
                    off_trazado_x = 0.0
                    off_trazado_y = 0.0

            # Offset de cruces - regla centralizada:
            # Si AUTO_SANGRE_OFFSET_CRUZ está activado: usar la sangre pero
            # garantizando al menos el margen de seguridad (OFFSET_SEGURIDAD_MM).
            # Si está desactivado: respetar el valor histórico OFFSET_CRUZ_MM.
            if AUTO_SANGRE_OFFSET_CRUZ:
                try:
                    offset_cruz_mm = max(float(t_sangre), float(OFFSET_SEGURIDAD_MM))
                except Exception:
                    # Fallback defensivo
                    offset_cruz_mm = float(t_sangre)
            else:
                # Si el usuario pone un OFFSET_CRUZ_MM menor que el margen de seguridad,
                # prevalece el margen de seguridad aplicado al uso efectivo.
                try:
                    offset_cruz_mm = max(
                        float(OFFSET_CRUZ_MM), float(OFFSET_SEGURIDAD_MM)
                    )
                except Exception:
                    offset_cruz_mm = float(OFFSET_CRUZ_MM)

            # Depuración: mostrar de dónde salen los valores efectivos
            print(
                f"[DEBUG] AUTO_SANGRE_OFFSET_CRUZ={AUTO_SANGRE_OFFSET_CRUZ}, sangre={t_sangre}, OFFSET_SEGURIDAD_MM={OFFSET_SEGURIDAD_MM}, OFFSET_CRUZ_MM={OFFSET_CRUZ_MM} -> offset_cruz_mm={offset_cruz_mm}"
            )

            # PDF Info
            mediabox_w = t_ancho  # Default si no hay PDF
            mediabox_h = t_alto

            if archivo_seleccionado["ruta"]:
                # Intentar leer tamaño real del PDF
                dims = obtener_tamano_real_pdf(archivo_seleccionado["ruta"])
                if dims:
                    mediabox_w, mediabox_h = dims

        except Exception as ex:
            print(f"Error leyendo valores UI: {ex}")
            return

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # INVERSIÓN DORSO - PASO 0: DETERMINAR TIPO Y PREPARAR CALLES
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # IMPORTANTE: Esto debe hacerse ANTES de calcular dimensiones de celdas
        # para que las celdas se calculen con las calles ya invertidas
        es_dorso = determinar_si_es_dorso()

        # Preparar calles para DORSO si es necesario
        CALLES_L_para_calculo = CALLES_L

        if es_dorso:
            # Separar calles verticales y horizontales
            n_v = max(0, g_cols - 1)
            n_h = max(0, g_rows - 1)

            if isinstance(CALLES_L, (list, tuple)) and len(CALLES_L) >= n_v + n_h:
                vert_calles = [float(x) for x in CALLES_L[:n_v]]
                horiz_calles = [float(x) for x in CALLES_L[n_v : n_v + n_h]]

                # Invertir calles verticales si son asimétricas
                if len(vert_calles) > 1 and len(set(vert_calles)) > 1:
                    vert_calles_orig = list(vert_calles)
                    vert_calles = list(reversed(vert_calles))
                    print(
                        f"\n[DORSO - PREPARACIÓN] Calles verticales invertidas: {vert_calles_orig} → {vert_calles}"
                    )

                    # Reconstruir CALLES_L con calles invertidas (orden V-FIRST)
                    CALLES_L_para_calculo = vert_calles + horiz_calles
                    print(
                        f"[DORSO - PREPARACIÓN] CALLES_L para cálculo: {CALLES_L_para_calculo}\n"
                    )

        # 2. Calcular dimensiones celdas (Lógica Core)
        # ✅ Usar CALLES_L_para_calculo que ya tiene las calles invertidas si es DORSO
        datos_celdas = dimensiones_mediabox_celdas_impo(
            tamano_usuario_w=t_ancho,
            tamano_usuario_h=t_alto,
            sangre=t_sangre,
            calles=CALLES_L_para_calculo,  # ✅ Usar calles preparadas (invertidas si es DORSO)
            grid_cols=g_cols,
            grid_rows=g_rows,
            mediabox_w=mediabox_w,
            mediabox_h=mediabox_h,
        )

        # 3. Calcular offsets de corte y sangre
        # ✅ Usar CALLES_L_para_calculo que ya tiene las calles invertidas si es DORSO
        offsets_corte = calculo_linea_corte_offsets(
            t_ancho, t_alto, CALLES_L_para_calculo, g_cols, g_rows
        )
        datos_celdas["offsets_corte_tamano_usuario"] = offsets_corte

        # ⚠️ NOTA: El offset de líneas de corte se calcula MÁS ABAJO,
        # DESPUÉS de crear las cruces, para tener el tamaño correcto del trazado

        offsets_sangre = calculo_linea_sangre_offsets(datos_celdas)

        # --- CAPA LINEAS CORTE (Azules) ---
        capa_corte_container = None
        capa_marcas_ext_container = None
        capa_marcas_medianales = None
        # Inicializar con tamaño del grid para que los prints sean coherentes
        corte_w_mm = datos_celdas["tamano_total_w"]
        corte_h_mm = datos_celdas["tamano_total_h"]

        if checkbox_lineas_corte.value:
            # Calcular grosor correcto: 0.50pt convertido a px
            PT_TO_MM = 0.352778
            grosor_pt = 0.50
            grosor_mm = grosor_pt * PT_TO_MM
            grosor_px = grosor_mm * ESCALA_VISUAL

            # Crear un Stack para las líneas de corte
            stack_corte = ft.Stack()

            # Usar offsets_corte para dibujar lineas
            print(f"  Número de líneas de corte: {len(offsets_corte['lineas_corte'])}")
            for item in offsets_corte["lineas_corte"]:
                stack_corte.controls.append(
                    ft.Container(
                        width=item["w_mm"] * ESCALA_VISUAL,
                        height=item["h_mm"] * ESCALA_VISUAL,
                        left=(item["x_mm"] + t_sangre) * ESCALA_VISUAL,
                        top=(item["y_mm"] + t_sangre) * ESCALA_VISUAL,
                        border=ft.Border.all(grosor_px, ft.Colors.BLUE),
                    )
                )

            # Envolver en Container para pasar a crear_grupo_trazado_centrado
            # El tamaño debe ser el mismo que el grid para que coincidan, o calculado
            corte_w_mm = datos_celdas["tamano_total_w"]
            corte_h_mm = datos_celdas["tamano_total_h"]

            capa_corte_container = ft.Container(
                content=stack_corte,
                width=corte_w_mm * ESCALA_VISUAL,
                height=corte_h_mm * ESCALA_VISUAL,
            )

        # --- CAPA CRUCES ---
        capa_cruces_container = None
        cruces_w_mm = 0
        cruces_h_mm = 0

        # Handle cruces (crop marks)
        if checkbox_cruces.value:
            # Create cruces layer using standard function
            capa_cruces_container, margen_cruces = crear_capa_cruces(
                t_sangre,
                datos_celdas,
                LONGITUD_CRUZ_MM,
                GROSOR_CRUZ_PT,
                offset_cruz_mm,  # ✅ Usar valor leído del textfield
                ESCALA_VISUAL,
            )
            capa_cruces_container.visible = True
            # ✅ SOLO actualizar TAMANO_FINAL_PLIEGO si NO está congelado
            if not PLIEGO_CONGELADO:
                # Update final sheet size based on cruces dimensions if available
                if "cruces_corte" in datos_celdas:
                    TAMANO_FINAL_PLIEGO["w_mm"] = datos_celdas["cruces_corte"][
                        "cruces_solo_w_mm"
                    ]
                    TAMANO_FINAL_PLIEGO["h_mm"] = datos_celdas["cruces_corte"][
                        "cruces_solo_h_mm"
                    ]
                else:
                    TAMANO_FINAL_PLIEGO["w_mm"] = datos_celdas["tamano_total_w"]
                    TAMANO_FINAL_PLIEGO["h_mm"] = datos_celdas["tamano_total_h"]
            # ✅ SIEMPRE actualizar cruces_w_mm y cruces_h_mm para crear_grupo_trazado_centrado
            if "cruces_corte" in datos_celdas:
                cruces_w_mm = datos_celdas["cruces_corte"]["cruces_solo_w_mm"]
                cruces_h_mm = datos_celdas["cruces_corte"]["cruces_solo_h_mm"]
            else:
                cruces_w_mm = datos_celdas["tamano_total_w"]
                cruces_h_mm = datos_celdas["tamano_total_h"]
        else:
            capa_cruces_container = None
            # ✅ SOLO actualizar TAMANO_FINAL_PLIEGO si NO está congelado
            if not PLIEGO_CONGELADO:
                # No cruces, use grid size for final sheet
                TAMANO_FINAL_PLIEGO["w_mm"] = datos_celdas["tamano_total_w"]
                TAMANO_FINAL_PLIEGO["h_mm"] = datos_celdas["tamano_total_h"]

        # ✅ CALCULAR Y GUARDAR OFFSET DE CENTRADO PARA LÍNEAS DE CORTE
        # IMPORTANTE: Esto se hace DESPUÉS de crear las cruces para tener el tamaño correcto
        # El área de corte es más pequeña que el trazado (no tiene sangre exterior)
        tamano_trazado_w_mm = datos_celdas.get("tamano_total_w", 0)
        tamano_trazado_h_mm = datos_celdas.get("tamano_total_h", 0)
        tamano_corte_w_mm = offsets_corte.get("tamano_total_w", 0)
        tamano_corte_h_mm = offsets_corte.get("tamano_total_h", 0)

        offset_lineas_corte_x_mm = (tamano_trazado_w_mm - tamano_corte_w_mm) / 2.0
        offset_lineas_corte_y_mm = (tamano_trazado_h_mm - tamano_corte_h_mm) / 2.0

        # Guardar offset en datos_celdas para uso posterior (crear_capa_lineas_corte y fitz PDF)
        datos_celdas["offset_lineas_corte_x_mm"] = offset_lineas_corte_x_mm
        datos_celdas["offset_lineas_corte_y_mm"] = offset_lineas_corte_y_mm

        # --- CAPA MARCAS DE TEXTO (Slug / Info del trabajo) ---
        # ✅ SIEMPRE crear la capa, independientemente del checkbox
        # La visibilidad se controla después en actualizar_capa_marca_texto()
        capa_marca_texto_container = None
        try:
            # Usar la función específica para marca de texto con TODOS los argumentos
            # ✅ IMPORTANTE: Usar tamaño del PLIEGO FINAL, no del trazado
            # El texto debe posicionarse respecto al pliego completo, no solo al área de trazado
            papel_final_w_mm = (
                TAMANO_FINAL_PLIEGO.get("w_mm") or datos_celdas["tamano_total_w"]
            )
            papel_final_h_mm = (
                TAMANO_FINAL_PLIEGO.get("h_mm") or datos_celdas["tamano_total_h"]
            )
            papel_final_w_px = papel_final_w_mm * ESCALA_VISUAL
            papel_final_h_px = papel_final_h_mm * ESCALA_VISUAL

            print(
                f"[DEBUG] Tamaño pliego para marca texto: {papel_final_w_mm:.1f}×{papel_final_h_mm:.1f}mm = {papel_final_w_px:.1f}×{papel_final_h_px:.1f}px"
            )

            capa_marca_texto_container = crear_capa_marca_texto(
                dim_celds=datos_celdas,
                contenido=MARCA_TEXTO_CONTENIDO,
                pos_sup_izq=MARCA_TEXTO_POS_SUP_IZQ,
                pos_sup_der=MARCA_TEXTO_POS_SUP_DER,
                pos_inf_izq=MARCA_TEXTO_POS_INF_IZQ,
                pos_inf_der=MARCA_TEXTO_POS_INF_DER,
                pos_centro_sup=MARCA_TEXTO_POS_CENTRO_SUP,
                pos_centro_inf=MARCA_TEXTO_POS_CENTRO_INF,
                pos_centro_lat_izq=MARCA_TEXTO_POS_CENTRO_LAT_IZQ,
                pos_centro_lat_der=MARCA_TEXTO_POS_CENTRO_LAT_DER,
                familia=MARCA_TEXTO_FAMILIA,
                tipo=MARCA_TEXTO_TIPO,
                cuerpo=MARCA_TEXTO_CUERPO,
                color=MARCA_TEXTO_COLOR,
                offset_h_mm=MARCA_TEXTO_OFFSET_H_MM,
                offset_v_mm=MARCA_TEXTO_OFFSET_V_MM,
                tamano_corte_w_mm=papel_final_w_px,  # ✅ Usar tamaño del pliego final en px
                tamano_corte_h_mm=papel_final_h_px,  # ✅ Usar tamaño del pliego final en px
                escala_visual=ESCALA_VISUAL,
                rotacion_grados=MARCA_TEXTO_ROTACION,
            )
            if capa_marca_texto_container:
                print(f"   ✅ Capa de marca de texto creada correctamente")
        except Exception as e:
            print(f"[ERROR] Falló creación de marca de texto: {e}")
            import traceback

            traceback.print_exc()

        # --- LÓGICA PLIEGO CONGELADO ---
        # ✅ MOVER AQUÍ: Ahora que tenemos el tamaño final con cruces, decidir qué tamaño usar
        if (
            PLIEGO_CONGELADO
            and TAMANO_FINAL_PLIEGO["w_mm"]
            and TAMANO_FINAL_PLIEGO["h_mm"]
        ):
            tamano_total_w = TAMANO_FINAL_PLIEGO["w_mm"]
            tamano_total_h = TAMANO_FINAL_PLIEGO["h_mm"]
            # print(f"[DEBUG PLIEGO] Usando tamaño congelado: {tamano_total_w} x {tamano_total_h}")
        else:
            # Si no está congelado, usar el tamaño final calculado (con o sin cruces)
            # ✅ CORREGIDO: Si TAMANO_FINAL_PLIEGO no tiene valores, usar el tamaño del grid calculado
            if TAMANO_FINAL_PLIEGO["w_mm"] and TAMANO_FINAL_PLIEGO["h_mm"]:
                tamano_total_w = TAMANO_FINAL_PLIEGO["w_mm"]
                tamano_total_h = TAMANO_FINAL_PLIEGO["h_mm"]
            else:
                # Fallback: usar tamaño del grid calculado (debe haberse calculado en líneas 2607-2629)
                tamano_total_w = datos_celdas.get("tamano_total_w", 0)
                tamano_total_h = datos_celdas.get("tamano_total_h", 0)
            # print(f"[DEBUG PLIEGO] Usando tamaño calculado (con cruces si aplica): {tamano_total_w} x {tamano_total_h}")

        # Actualizar textfields del pliego CON EL TAMAÑO FINAL
        # ⚠️ IMPORTANTE: En modo manual NO sobrescribir los textfields (el usuario los está editando)
        if not PLIEGO_CONGELADO:
            # Actualizar textfields SIN disparar sus handlers on_change
            # (evita que la actualización programática marque el trabajo como modificado
            #  y dispare el guardado del stamp cuando solo cambiamos el zoom).
            try:
                _ancho_handler = getattr(textfield_ancho, "on_change", None)
            except Exception:
                _ancho_handler = None
            try:
                _alto_handler = getattr(textfield_alto, "on_change", None)
            except Exception:
                _alto_handler = None

            try:
                try:
                    textfield_ancho.on_change = None
                except Exception:
                    pass
                try:
                    textfield_alto.on_change = None
                except Exception:
                    pass

                # Asignación de valores (programática)
                unit = _estado_impo_ui.get("unit", _initial_unit_pref)
                try:
                    textfield_ancho.value = (
                        f"{convert_from_mm(float(tamano_total_w), unit):.2f}"
                    )
                    textfield_alto.value = (
                        f"{convert_from_mm(float(tamano_total_h), unit):.2f}"
                    )
                except Exception:
                    # Fallback sin conversión si hay error
                    textfield_ancho.value = f"{tamano_total_w:.2f}"
                    textfield_alto.value = f"{tamano_total_h:.2f}"
            finally:
                # Restaurar handlers originales
                try:
                    textfield_ancho.on_change = _ancho_handler
                except Exception:
                    pass
                try:
                    textfield_alto.on_change = _alto_handler
                except Exception:
                    pass
        else:
            pass
            # print(f"[DEBUG PLIEGO] Modo MANUAL - textfields NO actualizados (usuario tiene control)")
        textfield_ancho.visible = True
        textfield_alto.visible = True
        textfield_ancho.update()
        textfield_alto.update()

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # INVERSIÓN DORSO - PASO 1: IMÁGENES (Antes de crear widgets)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Las imágenes se invierten en espejo horizontal dentro de sus celdas
        # IMPORTANTE: Solo se invierte el offset MANUAL del usuario, NO el offset automático de centrado
        # offset_imagen_fritz_x = offset_auto + user_offset
        # En DORSO: offset_imagen_fritz_x = offset_auto + (-user_offset)
        es_dorso = determinar_si_es_dorso()
        if es_dorso and (off_img_x != 0.0 or off_img_y != 0.0):
            print(f"\n{'='*60}")
            print(f"🔄 DORSO DETECTADO: Invirtiendo offsets MANUALES de imágenes")
            print(f"{'='*60}")
            print(f"   Offset usuario: X={off_img_x:.2f}, Y={off_img_y:.2f} mm")

            for key in datos_celdas.keys():
                if isinstance(key, str) and key.startswith("row_col:"):
                    celda_data = datos_celdas[key]

                    # El offset_imagen_fritz_x tiene dos componentes:
                    # offset_imagen_fritz_x = offset_auto + user_offset
                    # Solo invertimos el user_offset, manteniendo offset_auto igual

                    if "offset_imagen_fritz_x_left" in celda_data:
                        offset_fritz_x = celda_data.get(
                            "offset_imagen_fritz_x_left", 0.0
                        )
                        # Calcular offset automático (sin el offset del usuario)
                        offset_auto_x = offset_fritz_x - off_img_x
                        # Recalcular con offset de usuario invertido
                        offset_fritz_x_invertido = offset_auto_x + (-off_img_x)
                        celda_data["offset_imagen_fritz_x_left"] = (
                            offset_fritz_x_invertido
                        )

                        if off_img_x != 0:
                            if DEBUG_IMPO_UI:
                                print(
                                    f"[DORSO] {key} offset_fritz_x: {offset_fritz_x:.2f} → {offset_fritz_x_invertido:.2f} mm"
                                )

                    if "offset_imagen_fritz_y_top" in celda_data:
                        offset_fritz_y = celda_data.get(
                            "offset_imagen_fritz_y_top", 0.0
                        )
                        # Calcular offset automático (sin el offset del usuario)
                        offset_auto_y = offset_fritz_y - off_img_y
                        # Recalcular con offset de usuario invertido
                        offset_fritz_y_invertido = offset_auto_y + (-off_img_y)
                        celda_data["offset_imagen_fritz_y_top"] = (
                            offset_fritz_y_invertido
                        )

                    # Invertir offset UI (para visualización en pantalla)
                    # Este también tiene componentes, pero solo invertimos el user_offset
                    if "offset_imagen_x_left" in celda_data:
                        offset_ui_x = celda_data.get("offset_imagen_x_left", 0.0)
                        offset_auto_ui_x = offset_ui_x - off_img_x
                        offset_ui_x_invertido = offset_auto_ui_x + (-off_img_x)
                        celda_data["offset_imagen_x_left"] = offset_ui_x_invertido

                    if "offset_imagen_y_top" in celda_data:
                        offset_ui_y = celda_data.get("offset_imagen_y_top", 0.0)
                        offset_auto_ui_y = offset_ui_y - off_img_y
                        offset_ui_y_invertido = offset_auto_ui_y + (-off_img_y)
                        celda_data["offset_imagen_y_top"] = offset_ui_y_invertido

            print(f"{'='*60}\n")
        elif es_dorso:
            print(
                f"\n[INFO] DORSO detectado pero offset usuario es 0 - No se invierte nada\n"
            )

        # Limpiar stack actual
        stack_principal.controls.clear()

        # print("\n" + "="*80)
        # print("📏 CONSTRUCCIÓN DE CAPAS - actualizar_trazado()")
        # print("="*80)
        # print(f"  Tamaño total pliego: {tamano_total_w:.2f} × {tamano_total_h:.2f} mm")
        # print(f"  Tamaño total (px): {tamano_total_w * ESCALA_VISUAL:.2f} × {tamano_total_h * ESCALA_VISUAL:.2f} px")
        # print("="*80 + "\n")

        # ✅ INICIALIZAR STACK CON PLACEHOLDERS Y REFERENCIAS (si no existen)
        # Las funciones actualizar_capa_* esperan que el stack tenga:
        # 1. Las capas en posiciones específicas: [0]=Fondo, [1]=Trazado, [2]=Línea ext, [3]=Marcas
        # 2. Referencias a cada capa: ref_capa_fondo, ref_grupo_trazado, ref_linea_exterior, ref_capa_marca_texto

        if len(stack_principal.controls) == 0:
            # Primera vez: crear placeholders y asignar referencias
            papel_w_px = tamano_total_w * ESCALA_VISUAL
            papel_h_px = tamano_total_h * ESCALA_VISUAL

            # CAPA 0: FONDO
            capa_fondo = ft.Stack(
                [
                    ft.Container(
                        width=papel_w_px, height=papel_h_px, bgcolor=ft.Colors.WHITE
                    )
                ],
                width=papel_w_px,
                height=papel_h_px,
            )
            stack_principal.controls.append(capa_fondo)
            stack_principal.ref_capa_fondo = capa_fondo

            # CAPA 1: GRUPO TRAZADO (placeholder)
            grupo_trazado = ft.Container(
                width=papel_w_px, height=papel_h_px, left=0, top=0
            )
            stack_principal.controls.append(grupo_trazado)
            stack_principal.ref_grupo_trazado = grupo_trazado

            # CAPA 2: LÍNEA EXTERIOR (placeholder)
            linea_exterior = ft.Stack(
                [], width=papel_w_px, height=papel_h_px, visible=True
            )
            stack_principal.controls.append(linea_exterior)
            stack_principal.ref_linea_exterior = linea_exterior

            # CAPA 3: MARCA DE TEXTO (placeholder)
            capa_marca_texto = ft.Container(
                width=papel_w_px,
                height=papel_h_px,
                bgcolor=ft.Colors.TRANSPARENT,
                visible=True,
                content=ft.Stack([]),
            )
            stack_principal.controls.append(capa_marca_texto)
            stack_principal.ref_capa_marca_texto = capa_marca_texto

            print(f"✅ Stack inicializado con 4 capas y referencias")

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # ✅ USAR FUNCIONES actualizar_capa_* (igual que trazado_ui.py)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        print(f"\n[CAPA 1] TRAZADO (Imágenes):")
        print(f"  Grid: {g_cols} × {g_rows} celdas")

        # --- CAPA TRAZADO (Imágenes) ---
        # Generar widgets de celdas
        celdas_widgets = []
        for r in range(g_rows):
            row_widgets = []
            for c in range(g_cols):
                key = f"row_col: {r},{c}"
                if key in datos_celdas:
                    info = datos_celdas[key]
                    info = datos_celdas[key]
                    # ✅ CORREGIDO: Usar offset_imagen_x_left estándar
                    # La inversión ya se aplicó directamente sobre este valor en el bloque de arriba
                    off_auto_x = info.get("offset_imagen_x_left", 0.0)
                    off_auto_y = info.get("offset_imagen_y_top", 0.0)

                    # Calcular índice global de la imagen para esta celda
                    offset_pliego = state_pliego["index"] * (g_rows * g_cols)
                    indice_celda = offset_pliego + (r * g_cols) + c

                    # Obtener imagen de imagenes_secuenciales (ya verificadas en la carga)
                    img_celda_base64 = None
                    img_celda_src = None

                    # RE-CALCULAR TOTAL PLIEGOS si cambió el grid
                    # Si imagenes_secuenciales está vacío (trabajo cargado sin generar vistas), usar num_paginas
                    imgs_seq = archivo_seleccionado.get("imagenes_secuenciales", {})
                    total_imgs_nav = (
                        len(imgs_seq)
                        if imgs_seq
                        else archivo_seleccionado.get(
                            "num_paginas", archivo_seleccionado.get("paginas", 0)
                        )
                    )
                    celdas_pliego_nav = max(1, g_rows * g_cols)
                    # Si estamos en modo doble cara, cada pliego físico contiene dos caras
                    es_modo_doble = False
                    try:
                        orden = ordenamiento_calculado.get("ordenamiento", {})
                        if orden:
                            es_modo_doble = any(
                                _es_dorso_val(v.get("doble_cara"))
                                for k, v in orden.items()
                                if isinstance(k, int) and isinstance(v, dict)
                            )
                        else:
                            es_modo_doble = bool(dropdown_doble_cara.value) and str(
                                dropdown_doble_cara.value
                            ).lower().startswith("d")
                    except Exception:
                        es_modo_doble = False

                    import math

                    divisor = celdas_pliego_nav * (2 if es_modo_doble else 1)
                    nuevo_total = math.ceil(total_imgs_nav / divisor)

                    if state_pliego["total"] != nuevo_total:
                        # Usar helper centralizado para actualizar el total y el widget
                        actualizar_total_pliegos(total_imgs_nav, g_rows, g_cols)

                        # Si el índice actual está fuera de rango, corregirlo
                        if state_pliego["index"] >= state_pliego["total"]:
                            state_pliego["index"] = state_pliego["total"] - 1
                            # Actualizar el textfield usando la misma lógica que en actualizar_estado_botones_pliego
                            actualizar_estado_botones_pliego()

                    # ✅ CARGAR IMAGEN DESDE CACHE EN DISCO (índice global)
                    # El indice_celda es el índice global de la imagen
                    try:
                        ruta_imagen_cache = obtener_ruta_imagen(indice_celda)
                        # print(f"  [CHECK] Celda [{r},{c}] - Buscando idx global: {indice_celda} en: {ruta_imagen_cache}")

                        if os.path.exists(ruta_imagen_cache):
                            # Imagen está en cache en disco
                            img_celda_src = ruta_imagen_cache
                            # print(f"  [CACHE DISK HIT] ✅ Celda [{r},{c}] - idx global: {indice_celda} cargada desde cache")
                        elif (
                            indice_celda
                            in archivo_seleccionado["imagenes_secuenciales"]
                        ):
                            # Fallback: usar imagenes_secuenciales (legacy)
                            val = archivo_seleccionado["imagenes_secuenciales"][
                                indice_celda
                            ]
                            if isinstance(val, str) and os.path.exists(val):
                                img_celda_src = val
                            else:
                                img_celda_base64 = val
                            if DEBUG_IMPO_UI:
                                print(
                                    f"  [FALLBACK] Celda [{r},{c}] - idx: {indice_celda} desde imagenes_secuenciales"
                                )
                        else:
                            if DEBUG_IMPO_UI:
                                print(
                                    f"  [MISSING] ❌ Celda [{r},{c}] - idx: {indice_celda} no disponible en cache ni en imagenes_secuenciales"
                                )
                                print(f"           Ruta esperada: {ruta_imagen_cache}")
                                print(
                                    f"           Existe: {os.path.exists(ruta_imagen_cache)}"
                                )
                    except Exception as ex_img:
                        import traceback

                        if DEBUG_IMPO_UI:
                            print(
                                f"  [ERROR] ❌ Celda [{r},{c}] - Error cargando imagen: {ex_img}"
                            )
                            print(f"         Traceback: {traceback.format_exc()}")

                    widget = None

                    widget = crear_celda_imposicion(
                        img_base64=img_celda_base64,
                        img_src=img_celda_src,
                        mediabox_w=mediabox_w,
                        mediabox_h=mediabox_h,
                        celda_w=info["celda_w"],
                        celda_h=info["celda_h"],
                        offset_auto_x=off_auto_x,
                        offset_auto_y=off_auto_y,
                        user_offset_x=off_img_x,
                        user_offset_y=off_img_y,
                        escala_visual=ESCALA_VISUAL,
                        sangre=t_sangre,
                        calles=CALLES_L[0] if CALLES_L else 0.0,  # Simplificado
                        pos_col=c,
                        pos_row=r,
                    )
                    row_widgets.append(widget)
            celdas_widgets.append(row_widgets)

        # Preparar listas de calles ANTES de calcular offsets (igual que trazado_ui.py)
        # ✅ CORREGIDO: n_v entre COLUMNAS, n_h entre FILAS, orden V-FIRST
        n_v = max(0, g_cols - 1)  # Calles verticales entre COLUMNAS
        n_h = max(0, g_rows - 1)  # Calles horizontales entre FILAS
        vert_calles = []  # calles verticales (entre columnas)
        horiz_calles = []  # calles horizontales (entre filas)

        # ✅ Usar CALLES_L_para_calculo que ya tiene las calles invertidas si es DORSO
        if isinstance(CALLES_L_para_calculo, (list, tuple)):
            if len(CALLES_L_para_calculo) >= n_v + n_h:
                # ORDEN V-FIRST: primero verticales, luego horizontales
                vert_calles = [float(x) for x in CALLES_L_para_calculo[:n_v]]
                horiz_calles = [
                    float(x) for x in CALLES_L_para_calculo[n_v : n_v + n_h]
                ]
            else:
                fallback = (
                    float(CALLES_L_para_calculo[0])
                    if len(CALLES_L_para_calculo) > 0
                    else float(t_sangre)
                )
                vert_calles = [fallback] * n_v
                horiz_calles = [fallback] * n_h
        else:
            val = float(CALLES_L_para_calculo)
            vert_calles = [val] * n_v
            horiz_calles = [val] * n_h

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # INVERSIÓN DORSO - PASO 2: CALLES VERTICALES (YA REALIZADO EN PASO 0)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # NOTA: La inversión de calles ya se realizó en el PASO 0 y está reflejada
        # en CALLES_L_para_calculo y por tanto en vert_calles.
        if es_dorso and len(vert_calles) > 1 and len(set(vert_calles)) > 1:
            print(
                f"[DORSO] Confirmación: Calles verticales ya invertidas en PASO 0: {vert_calles}"
            )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # INVERSIÓN DORSO - PASO 3: OFFSET DE TRAZADO (Usuario)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # El offset del usuario también debe invertirse para mantener la simetría
        # Si en CARA el usuario mueve el trazado +10mm a la derecha,
        # en DORSO debe moverse -10mm (10mm a la izquierda, espejo)
        off_trazado_x_final = off_trazado_x
        off_trazado_y_final = off_trazado_y

        if es_dorso:
            off_trazado_x_final = -off_trazado_x
            if off_trazado_x != 0:
                print(
                    f"[DORSO] Offset trazado usuario invertido: X={off_trazado_x:.2f} → {off_trazado_x_final:.2f} mm"
                )

        # ✅ Guardar offsets ORIGINALES (sin inversión) para generar JSON del otro lado
        datos_celdas["offset_usuario_original_x_mm"] = off_trazado_x
        datos_celdas["offset_usuario_original_y_mm"] = off_trazado_y

        # ✅ Guardar offsets de usuario para exportación a JSON (con inversión si es DORSO)
        datos_celdas["offset_usuario_x_mm"] = off_trazado_x_final
        datos_celdas["offset_usuario_y_mm"] = off_trazado_y_final

        # ✅ Guardar offsets de imagen para exportación a JSON
        datos_celdas["offset_imagen_x_mm"] = off_img_x
        datos_celdas["offset_imagen_y_mm"] = off_img_y

        # Calcular offsets de celdas (posiciones absolutas) usando la función correcta
        # Esto replica exactamente lo que hace trazado_ui.py en crear_grid_imposicion_NEW
        offsets_result = calcular_offsets_celdas(
            datos_celdas=datos_celdas,
            grid_cols=g_cols,
            grid_rows=g_rows,
            calles_v=vert_calles,
            calles_h=horiz_calles,
            origin="actualizar_trazado",
            force=True,
        )
        datos_celdas["offsets_celdas"] = offsets_result["offsets_celdas"]
        datos_celdas["offsets_grid_info"] = offsets_result["grid_info"]

        # --- CAPA MARCAS DE CORTE EXTERIORES (Líneas en bordes) ---
        # ✅ AHORA SE LLAMA AQUÍ: Después de guardar offsets_grid_info
        # Estas marcas son parte del grupo de cruces/corte, no de "marcas de texto"
        if (
            checkbox_cruces.value
        ):  # ✅ CORREGIDO: Eliminar condición "is None" para permitir recálculo
            try:
                # ✅ CORREGIDO: Usar tamaño de la capa de cruces (igual que trazado_ui.py)
                # Las marcas exteriores deben calcularse sobre el tamaño CON cruces, no sobre el trazado
                if "cruces_corte" in datos_celdas:
                    cruces_w_mm = datos_celdas["cruces_corte"]["cruces_solo_w_mm"]
                    cruces_h_mm = datos_celdas["cruces_corte"]["cruces_solo_h_mm"]
                else:
                    # Fallback: usar tamaño del trazado
                    cruces_w_mm = datos_celdas["tamano_total_w"]
                    cruces_h_mm = datos_celdas["tamano_total_h"]

                ancho_corte_px = cruces_w_mm * ESCALA_VISUAL
                alto_corte_px = cruces_h_mm * ESCALA_VISUAL
                extension_fuera_px = (LONGITUD_CRUZ_MM + offset_cruz_mm) * ESCALA_VISUAL

                # ✅ RECIBIR 3 VALORES (Container, margen, datos_calles)
                capa_marcas_ext_container, margen_ext, datos_calles_ext = (
                    crear_capa_marcas_corte_exteriores(
                        datos_celdas,
                        LONGITUD_CRUZ_MM,
                        offset_cruz_mm,
                        ESCALA_VISUAL,
                        ancho_corte_px,
                        alto_corte_px,
                        extension_fuera_px,
                        GROSOR_CRUZ_PT,
                    )
                )
                if capa_marcas_ext_container:
                    print(
                        f"   ✅ Capa de marcas exteriores creada correctamente. Controles: {len(capa_marcas_ext_container.content.controls) if capa_marcas_ext_container.content else 'N/A'}"
                    )
                else:
                    print(f"   ⚠️ Capa de marcas exteriores es None")
            except Exception as e:
                print(f"[ERROR] Falló creación de marcas exteriores: {e}")
                import traceback

                traceback.print_exc()

        # ✅ USAR crear_trazado_con_rows_from_widgets igual que trazado_ui.py
        # Esta función maneja correctamente el posicionamiento con Row/Column y spacing
        grid_visual, info_grid = crear_trazado_con_rows_from_widgets(
            celdas_matriz=celdas_widgets,  # Matriz de widgets ya creados
            calles_h=horiz_calles,  # Calles entre FILAS (verticales)
            calles_v=vert_calles,  # Calles entre COLUMNAS (horizontales)
            escala=ESCALA_VISUAL,
            datos_celdas=datos_celdas,  # Información de sangres
        )

        # ✅ CREAR CAPA DE LÍNEAS DE CORTE (Azules)
        # Esta capa se superpone al trazado para mostrar las áreas de corte
        capa_corte_container = None
        if (
            checkbox_lineas_corte.value
        ):  # Asegurarse de tener este checkbox o usar uno existente
            try:
                print("\n[INFO] Creando capa de líneas de corte azules...")
                capa_corte_container = crear_capa_lineas_corte(
                    dim_celds=datos_celdas,
                    escala=ESCALA_VISUAL,
                    grosor_pt=GROSOR_CRUZ_PT,
                )
                if capa_corte_container:
                    print(f"   ✅ Capa de líneas de corte creada correctamente")
            except Exception as e:
                print(f"[ERROR] Falló creación de líneas de corte: {e}")

        # ✅ UNIFICAR GRID Y CORTE EN UN SOLO GRUPO (Standard Architecture)
        # Combinar capa de corte y capa de cruces si existen

        # Obtener offsets de trazado si existen (calculados en crear_capa_cruces)
        offset_trazado_x_mm = 0.0
        offset_trazado_y_mm = 0.0
        if "cruces_corte" in datos_celdas:
            offset_trazado_x_mm = datos_celdas["cruces_corte"].get(
                "offset_trazado_x_mm", 0.0
            )
            offset_trazado_y_mm = datos_celdas["cruces_corte"].get(
                "offset_trazado_y_mm", 0.0
            )

        offset_trazado_x_px = offset_trazado_x_mm * ESCALA_VISUAL
        offset_trazado_y_px = offset_trazado_y_mm * ESCALA_VISUAL

        # 4. Marcas Medianales - Se agregan más abajo después de crearse

        # ✅ CREAR CAPA DE MARCAS MEDIANALES INTERNAS (Cruces de plegado)
        # Solo si hay cruces activadas (o checkbox específico si existiera)
        if checkbox_cruces.value:
            try:
                # Calcular dimensiones necesarias
                # ✅ IMPORTANTE: Usar tamaño de cruces para que coincida con el sistema de coordenadas de marcas exteriores
                if "cruces_corte" in datos_celdas:
                    cruces_w_mm = datos_celdas["cruces_corte"]["cruces_solo_w_mm"]
                    cruces_h_mm = datos_celdas["cruces_corte"]["cruces_solo_h_mm"]
                else:
                    cruces_w_mm = datos_celdas["tamano_total_w"]
                    cruces_h_mm = datos_celdas["tamano_total_h"]

                ancho_corte_px = cruces_w_mm * ESCALA_VISUAL
                alto_corte_px = cruces_h_mm * ESCALA_VISUAL
                extension_fuera_px = (LONGITUD_CRUZ_MM + offset_cruz_mm) * ESCALA_VISUAL

                capa_marcas_medianales = crear_capa_marcas_medianales_internas(
                    datos_celdas,
                    10,  # longitud_cruz_mm para medianales (10mm total)
                    ESCALA_VISUAL,
                    ancho_corte_px,
                    alto_corte_px,
                    extension_fuera_px,
                    LONGITUD_CRUZ_MM,
                    offset_cruz_mm,
                    TAMANO_USUARIO_W,
                    TAMANO_USUARIO_H,
                    horiz_calles,  # Calles horizontales (entre filas)
                    vert_calles,  # Calles verticales (entre columnas)
                    OFFSET_SEGURIDAD_MM,  # ✨ NUEVO: Margen de seguridad adicional
                    AUTO_SANGRE_OFFSET_CRUZ,  # ✨ NUEVO: usar sangre automáticamente si está activo
                    LONGITUD_BRAZO_MAX_MM,  # ✨ NUEVO: Longitud máxima del brazo
                    GROSOR_CRUZ_PT,
                )

                if capa_marcas_medianales:
                    print(f"   ✅ Capa de marcas medianales creada correctamente")
            except Exception as e:
                print(f"[ERROR] Falló creación de marcas medianales: {e}")

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # ✅ ENSAMBLAJE DE GRUPOS (Replicando lógica de trazado_ui.py)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        # GRUPO 1: TRAZADO + LÍNEAS DE CORTE (Mismo tamaño, alineados a 0,0)
        grid_visual_con_lineas = grid_visual
        if capa_corte_container and checkbox_lineas_corte.value:
            # Crear Stack con grid + líneas azules superpuestas
            grid_visual_con_lineas = ft.Stack(
                controls=[
                    grid_visual,  # Trazado base (abajo)
                    capa_corte_container,  # Líneas azules (encima)
                ],
                # El tamaño es el del trazado
            )
            print("   ✅ Grid combinado con líneas de corte")

        # GRUPO 2: CRUCES + MARCAS (Mismo tamaño extendido, alineados a 0,0)
        capa_cruces_completa = None
        if capa_cruces_container:
            controles_cruces = [capa_cruces_container]

            # Agregar marcas exteriores (ya tienen offsets internos correctos)
            if capa_marcas_ext_container:
                controles_cruces.append(capa_marcas_ext_container)

            # Agregar marcas medianales (ya tienen offsets internos correctos)
            if capa_marcas_medianales:
                controles_cruces.append(capa_marcas_medianales)

            capa_cruces_completa = ft.Stack(controles_cruces)
            print("   ✅ Grupo de cruces completo creado (Cruces + Marcas)")

        # Esto usa la misma lógica que trazado_ui.py
        # ✅ CORREGIDO: Pasar None para que calcule automáticamente los offsets de centrado
        grupo_trazado_stack, grupo_w_mm, grupo_h_mm = crear_grupo_trazado_centrado(
            grid_visual=grid_visual_con_lineas,
            capa_cruces=capa_cruces_completa,  # Pasamos la combinación de capas de cruces
            offset_cruces_x_mm=None,  # None = calcular automáticamente
            offset_cruces_y_mm=None,
            offset_trazado_x_mm=None,  # None = calcular automáticamente
            offset_trazado_y_mm=None,
            trazado_w_mm=datos_celdas["tamano_total_w"],
            trazado_h_mm=datos_celdas["tamano_total_h"],
            cruces_w_mm=cruces_w_mm if cruces_w_mm > 0 else corte_w_mm,
            cruces_h_mm=cruces_h_mm if cruces_h_mm > 0 else corte_h_mm,
            escala=ESCALA_VISUAL,
        )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # ✅ ACTUALIZAR CAPAS USANDO FUNCIONES DEL MÓDULO stack_trazado_ui
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        # CAPA 0: CRUCES
        cruces_visible = checkbox_cruces.value
        actualizar_capa_cruces(
            stack_principal,
            capa_cruces=capa_cruces_container,
            visible=cruces_visible,
            offset_pliego_x_mm=off_trazado_x_final,  # ✅ Usar versión invertida para DORSO
            offset_pliego_y_mm=off_trazado_y_final,  # ✅ Usar versión invertida para DORSO
        )
        print(f"  [0] CRUCES: visible={cruces_visible}")

        # CAPA 1: TRAZADO
        actualizar_capa_trazado(
            stack=stack_principal, grid_visual=grupo_trazado_stack, escala=ESCALA_VISUAL
        )
        # ✅ ASIGNAR REFERENCIA (necesaria para centrar_grupo_trazado_en_pliego)
        stack_principal.ref_grupo_trazado = stack_principal.controls[1]
        print(f"  [1] TRAZADO: {grupo_w_mm:.1f}×{grupo_h_mm:.1f}mm")

        # CAPA 2: FONDO + LÍNEA EXTERIOR
        linea_ext_visible = checkbox_linea_exterior.value
        actualizar_capa_fondo(
            stack_principal,
            papel_w_mm=tamano_total_w,
            papel_h_mm=tamano_total_h,
            mostrar_linea_exterior=linea_ext_visible,
            escala=ESCALA_VISUAL,
        )
        print(
            f"  [2] FONDO: {tamano_total_w:.1f}×{tamano_total_h:.1f}mm, linea_ext={linea_ext_visible}"
        )

        # CAPA 3: MARCA DE TEXTO
        marca_texto_visible = checkbox_marcas_texto.value
        actualizar_capa_marca_texto(
            stack_principal,
            capa_marca_texto=capa_marca_texto_container,
            visible=marca_texto_visible,
            papel_w_mm=tamano_total_w,
            papel_h_mm=tamano_total_h,
            escala=ESCALA_VISUAL,
        )
        print(f"  [3] MARCA_TEXTO: visible={marca_texto_visible}")

        # ✅ CENTRAR GRUPO TRAZADO EN PLIEGO
        # Esto asegura que el grid quede centrado en el papel blanco
        centrar_grupo_trazado_en_pliego(
            stack_principal,
            grupo_w_mm,  # Ancho del GRUPO UNIFICADO
            grupo_h_mm,  # Alto del GRUPO UNIFICADO
            tamano_total_w,  # Ancho del PLIEGO (papel)
            tamano_total_h,  # Alto del PLIEGO (papel)
            escala=ESCALA_VISUAL,
            extra_offset_x_mm=off_trazado_x_final,  # ✅ Usar versión invertida para DORSO
            extra_offset_y_mm=off_trazado_y_final,  # ✅ Usar versión invertida para DORSO
        )
        print(
            f"✅ Grupo de trazado centrado en pliego con offsets X={off_trazado_x_final:.2f}mm, Y={off_trazado_y_final:.2f}mm"
        )
        # Guardar últimos tamaños calculados para que la actualización del viewer
        # pueda realizarse sin rehacer todo el trazado/JSON.
        try:
            global LAST_GRUPO_W_MM, LAST_GRUPO_H_MM, LAST_TAMANO_TOTAL_W_MM, LAST_TAMANO_TOTAL_H_MM
            # ¿Cambió el tamaño del pliego respecto al último trazado? (modo
            # manual). El transform usa origen TOP_LEFT, así que el centrado
            # depende solo del pan; tras un cambio de tamaño hay que recentrar.
            _size_changed = (
                LAST_TAMANO_TOTAL_W_MM is not None
                and (
                    abs(LAST_TAMANO_TOTAL_W_MM - float(tamano_total_w)) > 0.001
                    or abs(LAST_TAMANO_TOTAL_H_MM - float(tamano_total_h)) > 0.001
                )
            )
            LAST_GRUPO_W_MM = grupo_w_mm
            LAST_GRUPO_H_MM = grupo_h_mm
            LAST_TAMANO_TOTAL_W_MM = tamano_total_w
            LAST_TAMANO_TOTAL_H_MM = tamano_total_h
        except Exception:
            _size_changed = False

        # Sincronizar slider y actualizar únicamente el viewer (escala + boundary)
        try:
            safe_set_zoom_slider(zoom_level.get("value", 1.0))
        except Exception:
            pass

        # Paridad PageNumber (set_page_size): al cambiar el tamaño del pliego en
        # modo manual el zoom del usuario vuelve al automático (factor 1.0).
        try:
            if _size_changed and not skip_auto_zoom:
                zoom_level["value"] = 1.0
                user_changed_zoom["value"] = False
                safe_set_zoom_slider(1.0)
        except Exception:
            pass

        try:
            # Recentrar solo si cambió el tamaño (edición manual); la navegación
            # entre pliegos pide explícitamente no recentrar (skip_auto_zoom=True).
            actualizar_viewer_zoom(
                do_center=bool(_size_changed and not skip_auto_zoom)
            )
        except Exception:
            pass

        # ✅ (debug) IMPRIMIR ANÁLISIS DE dims_impo DESPUÉS DE ACTUALIZAR EL VIEWER
        # La impresión del análisis se desactiva por defecto para evitar ruido en terminal.
        # Si necesitas ver el análisis, descomenta la siguiente línea o llama manualmente a la función.
        if False and datos_celdas:
            imprimir_analisis_dim_celds(
                datos_celdas, "ANÁLISIS dims_impo - dimensiones_mediabox_celdas_impo"
            )

        # ============================================================================
        # GENERACIÓN DE JSON PARA FRITZ (IMPOSICIÓN PDF)
        # ============================================================================
        try:
            # Verificar si hay datos de celdas calculados
            if datos_celdas:
                # Determinar si es doble cara o una sola cara
                # Determinar si es doble cara o una sola cara
                es_doble_cara = False
                try:
                    # Usar ordenamiento_calculado como fuente de verdad (igual que en actualizar_estado_botones_pliego)
                    ordenamiento = ordenamiento_calculado.get("ordenamiento", {})
                    if ordenamiento:
                        es_doble_cara = any(
                            _es_dorso_val(v.get("doble_cara"))
                            for k, v in ordenamiento.items()
                            if isinstance(k, int) and isinstance(v, dict)
                        )
                    else:
                        # Fallback al dropdown si no hay ordenamiento (caso raro)
                        es_doble_cara = bool(dropdown_doble_cara.value) and str(
                            dropdown_doble_cara.value
                        ).lower().startswith("d")
                except Exception:
                    es_doble_cara = False

                # Obtener tamaño del pliego
                pliego_w = tamano_total_w if tamano_total_w else None
                pliego_h = tamano_total_h if tamano_total_h else None

                # ============================================================================
                # AGREGAR DATOS DE CAPAS A datos_celdas (para JSON completo)
                # ============================================================================
                # Construir estructura de capas similar a trazado_ui.py
                trazado_w = datos_celdas.get("tamano_total_w", 0.0)
                trazado_h = datos_celdas.get("tamano_total_h", 0.0)

                # ✅ CALCULAR OFFSETS DE CENTRADO DEL TRAZADO DENTRO DEL PLIEGO
                # Estos offsets son CRÍTICOS para la inversión DORSO
                # El trazado se centra dentro del pliego más grande
                offset_trazado_x_mm = 0.0
                offset_trazado_y_mm = 0.0

                if pliego_w and pliego_h and trazado_w and trazado_h:
                    # Calcular offset de centrado
                    # El centrado es simétrico por naturaleza, no necesita inversión
                    # Solo el offset del usuario (off_trazado_x_final) se invierte para DORSO
                    centrado_x = (pliego_w - trazado_w) / 2.0
                    centrado_y = (pliego_h - trazado_h) / 2.0

                    offset_trazado_x_mm = centrado_x
                    offset_trazado_y_mm = centrado_y

                    # Agregar offsets extra del usuario (ya invertidos para DORSO si aplica)
                    offset_trazado_x_mm += off_trazado_x_final
                    offset_trazado_y_mm += off_trazado_y_final

                    print(f"[DEBUG OFFSETS] Trazado centrado en pliego:")
                    print(f"  • Pliego: {pliego_w:.2f} × {pliego_h:.2f} mm")
                    print(f"  • Trazado: {trazado_w:.2f} × {trazado_h:.2f} mm")
                    print(f"  • Offset X: {offset_trazado_x_mm:.2f} mm")
                    print(f"  • Offset Y: {offset_trazado_y_mm:.2f} mm")

                # Calcular offsets y tamaños para cada capa
                # CAPA 3 (Cruces): si existen datos en 'cruces_corte' usar sus dimensiones
                capa3_x = 0.0
                capa3_y = 0.0
                capa3_w = pliego_w or 0.0
                capa3_h = pliego_h or 0.0
                try:
                    if "cruces_corte" in datos_celdas:
                        cruces_w_mm = float(
                            datos_celdas["cruces_corte"].get("cruces_solo_w_mm", 0.0)
                        )
                        cruces_h_mm = float(
                            datos_celdas["cruces_corte"].get("cruces_solo_h_mm", 0.0)
                        )
                        capa3_w = cruces_w_mm
                        capa3_h = cruces_h_mm
                        if pliego_w:
                            capa3_x = (pliego_w - cruces_w_mm) / 2.0
                        if pliego_h:
                            capa3_y = (pliego_h - cruces_h_mm) / 2.0
                except Exception:
                    pass

                # CAPA 4 (Trazado): offset INTERNO del trazado respecto al GRUPO de cruces
                # Preferimos el valor calculado durante la creación de cruces (datos_celdas['cruces_corte'])
                # porque contiene el offset real (ej. 13.00,13.00) cuando hay extensión de cruces.
                cruces_info = (
                    datos_celdas.get("cruces_corte", {})
                    if isinstance(datos_celdas, dict)
                    else {}
                )
                capa4_x = float(
                    cruces_info.get("offset_trazado_x_mm", offset_trazado_x_mm)
                )
                capa4_y = float(
                    cruces_info.get("offset_trazado_y_mm", offset_trazado_y_mm)
                )
                capa4_w = trazado_w
                capa4_h = trazado_h

                # CAPA 5 (Pliego): origen de la página. No debe llevar offsets de posicionamiento del trazado.
                capa5_x = 0.0
                capa5_y = 0.0
                capa5_w = pliego_w or 0.0
                capa5_h = pliego_h or 0.0

                # Diagnostic: imprimir valores finales que se asignarán a las capas
                print(
                    f"[DEBUG CAPAS] capa_3_cruces (grupo) = ({capa3_x:.2f},{capa3_y:.2f}) w/h=({capa3_w:.2f},{capa3_h:.2f})"
                )
                print(
                    f"[DEBUG CAPAS] capa_4_trazado (interno) = ({capa4_x:.2f},{capa4_y:.2f}) w/h=({capa4_w:.2f},{capa4_h:.2f})"
                )
                print(
                    f"[DEBUG CAPAS] capa_5_pliego (origen) = ({capa5_x:.2f},{capa5_y:.2f}) w/h=({capa5_w:.2f},{capa5_h:.2f})"
                )

                datos_celdas["capas"] = {
                    "capa_0_texto": {
                        "x_mm": 0.0,
                        "y_mm": 0.0,
                        "w_mm": pliego_w or 0.0,
                        "h_mm": pliego_h or 0.0,
                    },
                    "capa_1_marcas_med": {
                        "x_mm": 0.0,
                        "y_mm": 0.0,
                        "w_mm": pliego_w or 0.0,
                        "h_mm": pliego_h or 0.0,
                    },
                    "capa_2_marcas_ext": {
                        "x_mm": 0.0,
                        "y_mm": 0.0,
                        "w_mm": pliego_w or 0.0,
                        "h_mm": pliego_h or 0.0,
                    },
                    "capa_3_cruces": {
                        "x_mm": capa3_x,
                        "y_mm": capa3_y,
                        "w_mm": capa3_w,
                        "h_mm": capa3_h,
                    },
                    "capa_4_trazado": {
                        "x_mm": capa4_x,
                        "y_mm": capa4_y,
                        "w_mm": capa4_w,
                        "h_mm": capa4_h,
                    },
                    "capa_5_pliego": {
                        "x_mm": capa5_x,
                        "y_mm": capa5_y,
                        "w_mm": capa5_w,
                        "h_mm": capa5_h,
                    },
                }

                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # ✅ APLICAR INVERSIÓN DE OFFSETS SI ES DORSO
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # NOTA: La inversión ya se realizó al inicio de la función (imágenes)
                # y al generar las calles (vert_calles). No es necesario hacer nada aquí.
                if es_dorso:
                    print(f"[INFO] Pliego DORSO - Inversión ya aplicada en UI y Datos")
                else:
                    print(f"[INFO] Pliego CARA - Sin inversión de offsets")

                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # EXTRAE MEDIABOX DEL PDF PROCESADO (ya disponible en archivo_seleccionado)
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                mediabox_pts = None
                try:
                    boxes = archivo_seleccionado.get("boxes_by_page")
                    if boxes and isinstance(boxes, dict) and 0 in boxes:
                        boxes_p0 = boxes[0]
                        mediabox_pts = boxes_p0.get("mediabox")
                        if mediabox_pts and len(mediabox_pts) == 4:
                            print(f"[INFO] Mediabox extraído del PDF: {mediabox_pts}")
                        else:
                            mediabox_pts = None
                except Exception as ex:
                    print(f"[WARNING] Error extrayendo mediabox: {ex}")

                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # GENERACIÓN DE JSON SEGÚN TIPO DE PLIEGO ACTUAL Y OPUESTO
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # 1. Generar JSON del pliego ACTUAL (lo que se ve en pantalla)
                tipo_cara_actual = "DORSO" if es_dorso else "CARA"

                # Preparar copia de datos para exportación respetando los checkboxes
                dims_export = (
                    copy.deepcopy(datos_celdas)
                    if isinstance(datos_celdas, dict)
                    else {}
                )
                try:
                    # Mantener la estructura: si está desactivado, dejar objetos vacíos
                    if not bool(checkbox_cruces.value):
                        dims_export["cruces"] = {}
                        dims_export["cruces_corte"] = {}
                        dims_export["capas"] = {}
                        dims_export["offsets_corte_tamano_usuario"] = {}
                        dims_export["marcas_corte"] = {}
                        dims_export["marcas_exteriores"] = {}
                        dims_export["marcas_medianales"] = {}
                    if not bool(checkbox_marcas_texto.value):
                        dims_export["marca_texto"] = {}
                except Exception:
                    pass

                # --- SAFETY CHECK: RESTORE CAPAS IF EMPTY (Cruces OFF) ---
                # Si 'capas' se borró porque cruces=False, restaurar la estructura básica
                # para que fritz_pdf_generator pueda calcular offsets y tamaños de grupo/pliego.
                if not dims_export.get("capas"):
                    if "capas" in datos_celdas:
                        # Copiar capas de datos_celdas pero desactivando cruces si es necesario
                        dims_export["capas"] = copy.deepcopy(datos_celdas["capas"])
                        # Si cruces off, podemos vaciar las coordenadas de la capa 3 para que no pinte nada (aunque el OCG se apague)
                        if not bool(checkbox_cruces.value):
                            # Mantener w/h del grupo, pero vaciar contenido visual si hubiera
                            pass
                    else:
                        print("[WARN Export] 'capas' no encontrada en datos_celdas")

                # --- SAFETY CHECK FOR PLIEGO DIMS ---
                # Si pliego_w/h son 0 o None, intentar recuperar del tamaño del trazado base
                # Esto ocurre si NO hay cruces (TAMANO_FINAL_PLIEGO es None) y los datos_celdas no propagaron bien
                if not pliego_w or float(pliego_w) <= 0.1:
                    pliego_w = datos_celdas.get("tamano_total_w", 0.0)
                    print(
                        f"[WARN] Pliego W era 0/None, recuperado de trazado: {pliego_w}"
                    )

                if not pliego_h or float(pliego_h) <= 0.1:
                    pliego_h = datos_celdas.get("tamano_total_h", 0.0)
                    print(
                        f"[WARN] Pliego H era 0/None, recuperado de trazado: {pliego_h}"
                    )

                # Si aún así es 0, usar el tamaño de la capa de corte o celdas
                if (
                    not pliego_w or float(pliego_w) <= 0.1
                ) and "cruces_corte" in datos_celdas:
                    pliego_w = datos_celdas["cruces_corte"].get(
                        "tamano_final_w_mm", 0.0
                    )
                if (
                    not pliego_h or float(pliego_h) <= 0.1
                ) and "cruces_corte" in datos_celdas:
                    pliego_h = datos_celdas["cruces_corte"].get(
                        "tamano_final_h_mm", 0.0
                    )

                json_actual = generar_impo_export_data(
                    dims=dims_export,
                    tipo_cara=tipo_cara_actual,
                    tamano_pliego_w_mm=pliego_w,
                    tamano_pliego_h_mm=pliego_h,
                    grid_cols=g_cols,
                    grid_rows=g_rows,
                    mediabox_pts=mediabox_pts,
                    sangre_mm=SANGRE * 2,  # 6mm total de sangre
                )

                if json_actual:
                    guardar_impo_export_data(json_actual, tipo_cara=tipo_cara_actual)
                    imprimir_impo_export_data(json_actual, enabled=True)
                    print(f"[INFO] JSON generado: {tipo_cara_actual}")

                # 2. Si es DOBLE CARA, generar AUTOMÁTICAMENTE el JSON del OTRO lado
                #    (para que Fritz tenga los datos sin necesidad de navegar a la página)
                if es_doble_cara:
                    otro_lado_es_dorso = not es_dorso
                    tipo_otro_lado = "DORSO" if otro_lado_es_dorso else "CARA"
                    # print(f"\n[INFO] Generando JSON automático para: {tipo_otro_lado} (Doble Cara)")

                    try:
                        # A. Preparar CALLES para el otro lado
                        calles_otro = (
                            CALLES_L  # Asumimos que CALLES_L siempre es la base (CARA)
                        )

                        # print(f"[DEBUG DORSO] CALLES_L desde CARA = {CALLES_L}")

                        # Si el otro lado es DORSO, invertir SOLO las calles verticales
                        if otro_lado_es_dorso:
                            n_v = max(0, g_cols - 1)
                            n_h = max(0, g_rows - 1)
                            if (
                                isinstance(CALLES_L, (list, tuple))
                                and len(CALLES_L) >= n_v + n_h
                            ):
                                vert_calles_otro = [float(x) for x in CALLES_L[:n_v]]
                                horiz_calles_otro = [
                                    float(x) for x in CALLES_L[n_v : n_v + n_h]
                                ]
                                # print(f"[DEBUG DORSO] Antes invert: vert={vert_calles_otro}, horiz={horiz_calles_otro}")
                                # ✅ SIEMPRE invertir calles verticales para DORSO (espejo horizontal)
                                # No importa si son iguales o diferentes - el orden importa para el espejo
                                if len(vert_calles_otro) > 1:
                                    vert_calles_otro = list(reversed(vert_calles_otro))
                                    print(
                                        f"[DORSO CALLES] Invirtiendo calles verticales: {vert_calles_otro}"
                                    )
                                calles_otro = vert_calles_otro + horiz_calles_otro
                                # print(f"[DEBUG DORSO] Después invert: vert={vert_calles_otro}, calles_otro={calles_otro}")
                        # Si el otro lado es CARA, usar CALLES_L original (ya asignado)

                        # print(f"[DEBUG DORSO] Calles finales para {tipo_otro_lado} = {calles_otro}")

                        # B. Preparar OFFSETS IMAGEN para el otro lado
                        # Solo invertir el offset manual del usuario
                        off_img_x_otro = off_img_x
                        off_img_y_otro = (
                            off_img_y  # Y no se invierte en espejo horizontal
                        )

                        if otro_lado_es_dorso:
                            off_img_x_otro = -off_img_x
                        # Si era dorso y vamos a cara, off_img_x ya venía invertido?
                        # No, off_img_x es el valor del textfield.
                        # Si estamos en DORSO, el textfield muestra el valor... ¿invertido?
                        # No, el textfield muestra el valor "lógico" o el valor guardado.
                        # Asumimos que off_img_x es el valor BASE del usuario.
                        # Si estamos en DORSO, off_img_x es el valor base.
                        # REVISIÓN: off_img_x viene de textfield_offset_img_x.value.
                        # Ese valor es único para el pliego.
                        # Si el usuario pone "10", en CARA es +10, en DORSO es -10.
                        # Por tanto, si vamos a DORSO, usamos -off_img_x.
                        # Si vamos a CARA, usamos off_img_x.

                        user_offset_x_otro = (
                            -off_img_x if otro_lado_es_dorso else off_img_x
                        )

                        # C. Calcular CELDAS para el otro lado
                        datos_celdas_otro = dimensiones_mediabox_celdas_impo(
                            tamano_usuario_w=t_ancho,
                            tamano_usuario_h=t_alto,
                            sangre=t_sangre,
                            calles=calles_otro,
                            grid_cols=g_cols,
                            grid_rows=g_rows,
                            mediabox_w=mediabox_w,
                            mediabox_h=mediabox_h,
                        )

                        # D. Calcular LÍNEAS DE CORTE para el otro lado
                        offsets_corte_otro = calculo_linea_corte_offsets(
                            t_ancho, t_alto, calles_otro, g_cols, g_rows
                        )
                        datos_celdas_otro["offsets_corte_tamano_usuario"] = (
                            offsets_corte_otro
                        )

                        # E. Calcular MARCAS MEDIANALES para el otro lado
                        # Para DORSO: copiar datos de CARA y reorganizar para garantizar valores idénticos
                        if otro_lado_es_dorso and "marcas_medianales" in datos_celdas:
                            # Copiar datos de CARA
                            datos_medianales_otro = copy.deepcopy(
                                datos_celdas["marcas_medianales"]
                            )
                            # print(f"[🔍 MARCAS MED DORSO] Copiando desde CARA: {len(datos_medianales_otro.get('lineas_medianales', []))} líneas")
                        else:
                            # Para CARA: calcular normalmente
                            n_v_original = max(0, g_cols - 1)
                            n_h_original = max(0, g_rows - 1)
                            if (
                                isinstance(CALLES_L, (list, tuple))
                                and len(CALLES_L) >= n_v_original + n_h_original
                            ):
                                vert_calles_para_marcas = [
                                    float(x) for x in CALLES_L[:n_v_original]
                                ]
                                horiz_calles_para_marcas = [
                                    float(x) for x in CALLES_L[n_v_original:]
                                ]
                            else:
                                val_original = (
                                    float(CALLES_L[0])
                                    if isinstance(CALLES_L, (list, tuple))
                                    and len(CALLES_L) > 0
                                    else float(CALLES_L)
                                )
                                vert_calles_para_marcas = [val_original] * max(
                                    0, g_cols - 1
                                )
                                horiz_calles_para_marcas = [val_original] * max(
                                    0, g_rows - 1
                                )

                            datos_medianales_otro = calcular_datos_medianales_para_json(
                                longitud_cruz_mm=LONGITUD_CRUZ_MM,
                                longitud_marcas_exteriores_mm=LONGITUD_CRUZ_MM,
                                offset_cruz_mm=offset_cruz_mm,
                                tamano_usuario_w=t_ancho,
                                tamano_usuario_h=t_alto,
                                calles_h=horiz_calles_para_marcas,
                                calles_v=vert_calles_para_marcas,
                                longitud_brazo_max_mm=LONGITUD_BRAZO_MAX_MM,
                                offset_seguridad_mm=OFFSET_SEGURIDAD_MM,
                            )

                        # Inversión de coordenadas X Y reorganización para marcas medianales en DORSO
                        if (
                            otro_lado_es_dorso
                            and datos_medianales_otro
                            and "lineas_medianales" in datos_medianales_otro
                        ):
                            # Determinar ancho de referencia para espejo:
                            # Preferir el ancho del GRUPO/CRUCES (cruces_solo_w_mm),
                            # luego el valor en capas.capa_3_cruces.w_mm, y solo como
                            # último recurso usar el ancho del pliego.
                            ancho_total = None
                            try:
                                if isinstance(datos_celdas, dict):
                                    ancho_total = datos_celdas.get(
                                        "cruces_corte", {}
                                    ).get("cruces_solo_w_mm")
                            except Exception:
                                ancho_total = None

                            try:
                                if not ancho_total and isinstance(
                                    datos_celdas_otro, dict
                                ):
                                    ancho_total = (
                                        datos_celdas_otro.get("capas", {})
                                        .get("capa_3_cruces", {})
                                        .get("w_mm")
                                    )
                            except Exception:
                                pass

                            if not ancho_total:
                                ancho_total = (
                                    pliego_w
                                    if (pliego_w and pliego_w > 0)
                                    else (
                                        datos_celdas_otro.get("tamano_total_w")
                                        if isinstance(datos_celdas_otro, dict)
                                        else None
                                    )
                                )
                            if not ancho_total:
                                ancho_total = 667.0

                            # PASO 1: Invertir coordenadas X de todas las líneas
                            # Usar espejo basado en el centro de cada línea para evitar
                            # sesgos producidos por usar la arista izquierda/derecha.
                            for linea in datos_medianales_otro["lineas_medianales"]:
                                if "x_mm" in linea:
                                    x_original = float(linea.get("x_mm", 0.0))
                                    width = float(linea.get("width_mm", 0.0))
                                    center = x_original + width / 2.0
                                    new_center = float(ancho_total) - center
                                    linea["x_mm"] = round(new_center - width / 2.0, 6)

                            # PASO 1b: Tras invertir X, actualizar la semántica del 'brazo'
                            # para marcas horizontales: lo que era 'izquierdo' en CARA ahora
                            # debe llamarse 'derecho' en DORSO y viceversa, para que el
                            # nombre del brazo coincida con la posición real.
                            for linea in datos_medianales_otro["lineas_medianales"]:
                                try:
                                    if linea.get("tipo") == "horizontal":
                                        b = linea.get("brazo", "").lower()
                                        if b == "izquierdo":
                                            linea["brazo"] = "derecho"
                                        elif b == "derecho":
                                            linea["brazo"] = "izquierdo"
                                except Exception:
                                    pass

                            # PASO 2: Agrupar líneas por intersección
                            lineas_por_interseccion = {}
                            for linea in datos_medianales_otro["lineas_medianales"]:
                                interseccion = linea.get("interseccion", "")
                                if interseccion not in lineas_por_interseccion:
                                    lineas_por_interseccion[interseccion] = []
                                lineas_por_interseccion[interseccion].append(linea)

                            # PASO 3: Ordenar intersecciones por su posición X (promedio de sus líneas)
                            intersecciones_ordenadas = []
                            for interseccion, lineas in lineas_por_interseccion.items():
                                # Calcular X promedio de las líneas horizontales de esta intersección
                                x_promedio = sum(
                                    l["x_mm"]
                                    for l in lineas
                                    if l.get("tipo") == "horizontal"
                                ) / max(
                                    1,
                                    sum(
                                        1
                                        for l in lineas
                                        if l.get("tipo") == "horizontal"
                                    ),
                                )
                                intersecciones_ordenadas.append(
                                    (x_promedio, interseccion, lineas)
                                )

                            # Ordenar de izquierda a derecha (menor X a mayor X)
                            intersecciones_ordenadas.sort(key=lambda x: x[0])

                            # PASO 4: Reconstruir el array de líneas en el orden correcto
                            lineas_reordenadas = []
                            for idx, (x_prom, interseccion, lineas) in enumerate(
                                intersecciones_ordenadas
                            ):
                                lineas_reordenadas.extend(lineas)
                                # print(f"[DORSO MARCAS MED] Intersección {interseccion} → x_prom={x_prom:.2f}mm (posición #{idx})")

                            datos_medianales_otro["lineas_medianales"] = (
                                lineas_reordenadas
                            )
                            print(
                                f"[DORSO MARCAS MED] Líneas reordenadas: {len(lineas_reordenadas)} líneas"
                            )

                        datos_celdas_otro["marcas_medianales"] = datos_medianales_otro

                        # E2. Calcular y copiar CRUCES INTERNAS para DORSO
                        # Las cruces internas deben invertirse igual que las calles verticales
                        # Las cruces exteriores (esquinas) NO se invierten
                        if "cruces_corte" in datos_celdas and otro_lado_es_dorso:
                            cruces_cara = datos_celdas["cruces_corte"]
                            cruces_dorso = copy.deepcopy(cruces_cara)

                            # ✅ Invertir coordenadas X SOLO de las cruces internas (no esquinas)
                            if (
                                "lineas_cruces" in cruces_dorso
                                and cruces_dorso["lineas_cruces"]
                            ):
                                # Usar el ancho del área de cruces como referencia para invertir cruces internas
                                ancho_cruces = datos_celdas.get("cruces_corte", {}).get(
                                    "cruces_solo_w_mm"
                                )
                                if not ancho_cruces:
                                    ancho_cruces = datos_celdas.get(
                                        "tamano_total_w", 0.0
                                    )
                                for cruz in cruces_dorso["lineas_cruces"]:
                                    # Solo invertir si NO es una cruz de esquina
                                    es_esquina = cruz.get("esquina") in [
                                        "tl",
                                        "tr",
                                        "bl",
                                        "br",
                                    ]
                                    if "x_mm" in cruz and not es_esquina:
                                        # Espejo horizontal: x_nuevo = ancho_cruces - x_viejo - width
                                        x_original = float(cruz.get("x_mm", 0.0))
                                        width = float(cruz.get("width_mm", 0.0))
                                        # Mirror using center of the mark to avoid left-edge bias
                                        center = x_original + width / 2.0
                                        new_center = float(ancho_cruces) - center
                                        cruz["x_mm"] = round(
                                            new_center - width / 2.0, 6
                                        )
                                        # print(f"[DORSO CRUCES INTERNAS] Invirtiendo X: {x_original:.2f} → {cruz['x_mm']:.2f} mm")
                                    # elif es_esquina:
                                    #     print(f"[DORSO CRUCES] Manteniendo esquina {cruz.get('esquina')}: x_mm={cruz.get('x_mm')}")

                            datos_celdas_otro["cruces_corte"] = cruces_dorso
                        elif "cruces_corte" in datos_celdas:
                            # Para CARA o si no hay cruces, copiar directamente
                            datos_celdas_otro["cruces_corte"] = datos_celdas[
                                "cruces_corte"
                            ]

                        # E3. MARCAS EXTERIORES: invertir posiciones X de marcas verticales para DORSO
                        if "marcas_corte" in datos_celdas:
                            if otro_lado_es_dorso:
                                marcas_cara = datos_celdas["marcas_corte"]
                                marcas_dorso = copy.deepcopy(marcas_cara)

                                # Invertir coordenadas X de las marcas verticales
                                if (
                                    "lineas_marcas" in marcas_dorso
                                    and marcas_dorso["lineas_marcas"]
                                ):
                                    ancho_total = marcas_dorso.get(
                                        "ancho_total_mm", 0.0
                                    )
                                    for marca in marcas_dorso["lineas_marcas"]:
                                        # Solo invertir marcas verticales
                                        if (
                                            marca.get("tipo") == "vertical"
                                            and "x_mm" in marca
                                        ):
                                            x_original = float(marca.get("x_mm", 0.0))
                                            width = float(marca.get("width_mm", 0.0))
                                            # Mirror using center of the mark to avoid left-edge bias
                                            center = x_original + width / 2.0
                                            new_center = float(ancho_total) - center
                                            marca["x_mm"] = round(
                                                new_center - width / 2.0, 6
                                            )
                                            # print(f"[DORSO MARCAS EXT] Invirtiendo X vertical: {x_original:.6f} → {marca['x_mm']:.6f} mm")

                                datos_celdas_otro["marcas_corte"] = marcas_dorso
                            else:
                                # Para CARA, copiar directamente
                                datos_celdas_otro["marcas_corte"] = datos_celdas[
                                    "marcas_corte"
                                ]
                        if "marca_texto" in datos_celdas:
                            datos_celdas_otro["marca_texto"] = datos_celdas[
                                "marca_texto"
                            ]

                        # Respetar checkboxes: si están desactivadas, dejar objetos vacíos
                        try:
                            if not bool(checkbox_cruces.value):
                                datos_celdas_otro["cruces"] = {}
                                datos_celdas_otro["cruces_corte"] = {}
                                datos_celdas_otro["capas"] = {}
                            # El control sobre si las marcas de corte se copian al DORSO
                            # debe venir del checkbox de "Cruces y marcas" (checkbox_cruces),
                            # no del checkbox visual "Linea Corte".
                            if not bool(checkbox_cruces.value):
                                datos_celdas_otro["offsets_corte_tamano_usuario"] = {}
                                datos_celdas_otro["marcas_corte"] = {}
                                datos_celdas_otro["marcas_exteriores"] = {}
                                datos_celdas_otro["marcas_medianales"] = {}
                            if not bool(checkbox_marcas_texto.value):
                                datos_celdas_otro["marca_texto"] = {}
                        except Exception:
                            pass

                        # F. Calcular OFFSET TRAZADO para el otro lado
                        # Centrado (simétrico)
                        centrado_x = (pliego_w - trazado_w) / 2.0
                        centrado_y = (pliego_h - trazado_h) / 2.0

                        # Offset usuario invertido si es DORSO
                        off_trazado_x_otro = (
                            -off_trazado_x if otro_lado_es_dorso else off_trazado_x
                        )

                        offset_trazado_x_final_otro = centrado_x + off_trazado_x_otro
                        offset_trazado_y_final_otro = (
                            centrado_y + off_trazado_y
                        )  # Y no cambia

                        # ✅ GUARDAR offset INVERTIDO para DORSO (ya invertido aquí, no en fritz_json_export)
                        datos_celdas_otro["offset_usuario_x_mm"] = off_trazado_x_otro
                        datos_celdas_otro["offset_usuario_y_mm"] = off_trazado_y

                        # ✅ GUARDAR offsets de imagen (NO se invierten, se copian igual)
                        datos_celdas_otro["offset_imagen_x_mm"] = datos_celdas.get(
                            "offset_imagen_x_mm", 0.0
                        )
                        datos_celdas_otro["offset_imagen_y_mm"] = datos_celdas.get(
                            "offset_imagen_y_mm", 0.0
                        )

                        # G. Construir CAPAS para el otro lado
                        # Calcular offsets para capa_3 (cruces) si existen
                        capa3_x_otro = 0.0
                        capa3_y_otro = 0.0
                        capa3_w_otro = pliego_w
                        capa3_h_otro = pliego_h
                        try:
                            if "cruces_corte" in datos_celdas_otro:
                                cruces_w_mm_otro = float(
                                    datos_celdas_otro["cruces_corte"].get(
                                        "cruces_solo_w_mm", 0.0
                                    )
                                )
                                cruces_h_mm_otro = float(
                                    datos_celdas_otro["cruces_corte"].get(
                                        "cruces_solo_h_mm", 0.0
                                    )
                                )
                                capa3_w_otro = cruces_w_mm_otro
                                capa3_h_otro = cruces_h_mm_otro
                                if pliego_w:
                                    capa3_x_otro = (pliego_w - cruces_w_mm_otro) / 2.0
                                if pliego_h:
                                    capa3_y_otro = (pliego_h - cruces_h_mm_otro) / 2.0
                        except Exception:
                            pass

                        # capa_4 debe usar el offset INTERNO fijo del trazado (NO el offset de usuario)
                        cruces_info_otro = (
                            datos_celdas_otro.get("cruces_corte", {})
                            if isinstance(datos_celdas_otro, dict)
                            else {}
                        )
                        capa4_x_otro = float(
                            cruces_info_otro.get("offset_trazado_x_mm", 11.0)
                        )
                        capa4_y_otro = float(
                            cruces_info_otro.get("offset_trazado_y_mm", 11.0)
                        )

                        datos_celdas_otro["capas"] = {
                            "capa_0_texto": {
                                "x_mm": 0.0,
                                "y_mm": 0.0,
                                "w_mm": pliego_w,
                                "h_mm": pliego_h,
                            },
                            "capa_1_marcas_med": {
                                "x_mm": 0.0,
                                "y_mm": 0.0,
                                "w_mm": pliego_w,
                                "h_mm": pliego_h,
                            },
                            "capa_2_marcas_ext": {
                                "x_mm": 0.0,
                                "y_mm": 0.0,
                                "w_mm": pliego_w,
                                "h_mm": pliego_h,
                            },
                            "capa_3_cruces": {
                                "x_mm": capa3_x_otro,
                                "y_mm": capa3_y_otro,
                                "w_mm": capa3_w_otro,
                                "h_mm": capa3_h_otro,
                            },
                            "capa_4_trazado": {
                                "x_mm": capa4_x_otro,
                                "y_mm": capa4_y_otro,
                                "w_mm": trazado_w,
                                "h_mm": trazado_h,
                            },
                            "capa_5_pliego": {
                                "x_mm": 0.0,
                                "y_mm": 0.0,
                                "w_mm": pliego_w,
                                "h_mm": pliego_h,
                            },
                        }

                        # H. Actualizar offsets_grid_info para DORSO CON LAS CALLES INVERTIDAS
                        # Esto es CRÍTICO: sin esto, las posiciones de celdas no reflejan las calles
                        # ✅ Separar calles del valor final calculado en calles_otro
                        n_v_grid = max(0, g_cols - 1)
                        n_h_grid = max(0, g_rows - 1)
                        if (
                            isinstance(calles_otro, (list, tuple))
                            and len(calles_otro) >= n_v_grid + n_h_grid
                        ):
                            vert_calles_grid = [
                                float(x) for x in calles_otro[:n_v_grid]
                            ]
                            horiz_calles_grid = [
                                float(x)
                                for x in calles_otro[n_v_grid : n_v_grid + n_h_grid]
                            ]
                        else:
                            val_grid = (
                                float(calles_otro[0])
                                if isinstance(calles_otro, (list, tuple))
                                and len(calles_otro) > 0
                                else float(calles_otro)
                            )
                            vert_calles_grid = [val_grid] * n_v_grid
                            horiz_calles_grid = [val_grid] * n_h_grid

                        datos_celdas_otro["offsets_grid_info"] = {
                            "grid_cols": g_cols,
                            "grid_rows": g_rows,
                            "calles_v": vert_calles_grid,  # Calles verticales para DORSO (ya invertidas en calles_otro)
                            "calles_h": horiz_calles_grid,  # Calles horizontales para DORSO (sin invertir)
                        }
                        # print(f"[DEBUG DORSO GRID INFO] calles_v={vert_calles_grid}, calles_h={horiz_calles_grid}")

                        # I. Generar y Guardar JSON
                        json_otro = generar_impo_export_data(
                            dims=datos_celdas_otro,
                            tipo_cara=tipo_otro_lado,
                            tamano_pliego_w_mm=pliego_w,
                            tamano_pliego_h_mm=pliego_h,
                            grid_cols=g_cols,
                            grid_rows=g_rows,
                            mediabox_pts=mediabox_pts,
                            sangre_mm=SANGRE * 2,  # 6mm total de sangre
                        )

                        if json_otro:
                            guardar_impo_export_data(
                                json_otro, tipo_cara=tipo_otro_lado
                            )
                            imprimir_impo_export_data(
                                json_otro, enabled=True
                            )  # ✅ Imprimir JSON de DORSO
                            # print(f"[INFO] JSON automático generado: {tipo_otro_lado}")

                    except Exception as e:
                        print(
                            f"[ERROR] Fallo al generar JSON automático para {tipo_otro_lado}: {e}"
                        )
                        import traceback

                        traceback.print_exc()

        except Exception as ex:
            print(f"[WARNING] Error generando JSON para Fritz: {ex}")

        # Actualizar estado de botones y contador de pliegos
        try:
            if (
                "actualizar_estado_botones_pliego" in locals()
                or "actualizar_estado_botones_pliego" in globals()
            ):
                actualizar_estado_botones_pliego()
        except Exception:
            pass

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 🔍 PUNTO DE CONTROL: STAMP DESPUÉS DE RECALCULAR IMPOSICIÓN
        # (Imprimible solo si DEBUG_STAMP=True al inicio del archivo)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if DEBUG_STAMP:
            print("\n" + "=" * 80)
            print("🔄 STAMP DESPUÉS DE RECALCULAR IMPOSICIÓN")
            print("=" * 80)
            try:
                import json

                try:
                    # Importar localmente para evitar import circular al cargar módulos
                    from app import get_stamp_limpio

                    print(
                        json.dumps(
                            get_stamp_limpio(_estado_impo_ui),
                            indent=2,
                            ensure_ascii=False,
                        )
                    )
                except Exception:
                    print(json.dumps(_estado_impo_ui, indent=2, ensure_ascii=False))
            except Exception as ex:
                print(f"[ERROR] No se pudo imprimir stamp: {ex}")
                print(_estado_impo_ui)
            print("=" * 80 + "\n")

    # Botón Recalcular
    def _boton_recalcular_click(e=None):
        # Forzar zoom automático al recalcular: cancelar timer de interacción
        # y resetear el flag y el factor de usuario.
        try:
            prev = user_changed_zoom_reset.get("timer")
            if prev is not None:
                try:
                    prev.cancel()
                except Exception:
                    pass
                user_changed_zoom_reset["timer"] = None
        except Exception:
            pass

        try:
            user_changed_zoom["value"] = False
        except Exception:
            pass

        try:
            zoom_level["value"] = 1.0
        except Exception:
            pass

        # Sincronizar slider y forzar zoom automático + centrado después del recalculo
        try:
            safe_set_zoom_slider(1.0)
        except Exception:
            pass

        # Llamar al recalculo principal
        try:
            actualizar_trazado(e)
        except Exception:
            pass

        # Asegurar que el viewer aplique el zoom/centrado correcto tras recalcular
        try:
            actualizar_viewer_zoom(do_center=True, skip_auto_zoom=True)
        except Exception:
            pass

    boton_recalcular = ft.Container(
        content=ft.Icon(ft.Icons.REFRESH, size=24, color=BOTONES_GENERICOS_COLOR),
        width=40,
        height=40,
        border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
        border_radius=4,
        bgcolor=FONDO_TEXTFIELDS_COLOR,
        alignment=ft.Alignment.CENTER,
        visible=True,
        on_click=_boton_recalcular_click,
        tooltip=t("Recalcular"),
    )

    # Asignar eventos a controles para auto-actualizar (después de definir la función)
    checkbox_cruces.on_change = lambda e: (
        mark_modified(),
        guardar_estado_impo_ui(),
        actualizar_trazado(e),
    )
    checkbox_lineas_corte.on_change = lambda e: (
        mark_modified(),
        guardar_estado_impo_ui(),
        actualizar_trazado(e),
    )
    checkbox_marcas_texto.on_change = lambda e: (
        mark_modified(),
        guardar_estado_impo_ui(),
        actualizar_trazado(e),
    )
    checkbox_linea_exterior.on_change = lambda e: (
        mark_modified(),
        guardar_estado_impo_ui(),
        actualizar_trazado(e),
    )

    dropdown_copias = ft.Dropdown(
        label=t("Número de copias"),
        width=100,
        value="1",
        options=[ft.dropdown.Option(str(i)) for i in range(1, 11)],
        text_size=16,
        content_padding=ft.Padding(8, 0, 0, 0),
        border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR), border_radius=6),
        filled=True,
        fill_color=FONDO_TEXTFIELDS_COLOR,
        color=DROPDOWN_TEXT_STYLE_COLOR,
        bgcolor=DROPDOWN_FONDO_MENU_COLOR,
        label_style=ft.TextStyle(color=DROPDOWN_TEXT_STYLE_COLOR),
        trailing_icon=ft.Icon(
            ft.Icons.ARROW_DROP_DOWN, color=DROPDOWN_TRAILING_ICON_COLOR
        ),
        selected_trailing_icon=ft.Icon(
            ft.Icons.ARROW_DROP_UP, color=DROPDOWN_TRAILING_ICON_COLOR
        ),
        visible=True,
        on_select=lambda e: (
            mark_modified(),
            guardar_estado_impo_ui(),
            recalcular_ordenamiento(),
        ),
    )

    def on_dropdown_doble_cara_change(e):
        try:
            nuevo_valor = e.control.value
            print(f"[DROPDOWN CHANGE] 🔄 Nuevo valor: {nuevo_valor}")
            mark_modified()
            guardar_estado_impo_ui()
            recalcular_ordenamiento()
            print(f"[DROPDOWN CHANGE] ✅ Cambio procesado completamente")
        except Exception as ex:
            print(f"[DROPDOWN CHANGE] ❌ Error: {ex}")
            import traceback

            traceback.print_exc()

    dropdown_doble_cara = ft.Dropdown(
        label=t("Tipo de impresión"),
        width=150,
        value=_estado_impo_ui.get("dropdown_doble_cara", "cara"),
        options=[
            ft.dropdown.Option("cara", t("Una cara")),
            ft.dropdown.Option("dorso", t("Doble cara")),
        ],
        text_size=16,
        content_padding=ft.Padding(8, 0, 0, 0),
        border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR), border_radius=6),
        filled=True,
        fill_color=FONDO_TEXTFIELDS_COLOR,
        color=DROPDOWN_TEXT_STYLE_COLOR,
        bgcolor=DROPDOWN_FONDO_MENU_COLOR,
        label_style=ft.TextStyle(color=DROPDOWN_TEXT_STYLE_COLOR),
        trailing_icon=ft.Icon(
            ft.Icons.ARROW_DROP_DOWN, color=DROPDOWN_TRAILING_ICON_COLOR
        ),
        selected_trailing_icon=ft.Icon(
            ft.Icons.ARROW_DROP_UP, color=DROPDOWN_TRAILING_ICON_COLOR
        ),
        visible=True,
        on_select=on_dropdown_doble_cara_change,
    )
    if DEBUG_STAMP:
        print(
            f"[INIT DROPDOWN] 🔍 _estado_impo_ui tenía: {_estado_impo_ui.get('dropdown_doble_cara', 'NO EXISTE')}"
        )
        print(f"[INIT DROPDOWN] 🔍 STAMP COMPLETO: {_estado_impo_ui}")

    dropdown_rotacion = ft.Dropdown(
        label=t("Orientación"),
        width=150,
        value="Horizontal",
        options=[
            ft.dropdown.Option("Horizontal", t("Horizontal")),
            ft.dropdown.Option("Vertical", t("Vertical")),
        ],
        text_size=16,
        content_padding=ft.Padding(8, 0, 0, 0),
        border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR), border_radius=6),
        filled=True,
        fill_color=FONDO_TEXTFIELDS_COLOR,
        color=DROPDOWN_TEXT_STYLE_COLOR,
        bgcolor=DROPDOWN_FONDO_MENU_COLOR,
        label_style=ft.TextStyle(color=DROPDOWN_TEXT_STYLE_COLOR),
        trailing_icon=ft.Icon(
            ft.Icons.ARROW_DROP_DOWN, color=DROPDOWN_TRAILING_ICON_COLOR
        ),
        selected_trailing_icon=ft.Icon(
            ft.Icons.ARROW_DROP_UP, color=DROPDOWN_TRAILING_ICON_COLOR
        ),
        on_select=lambda e: (
            mark_modified(),
            guardar_estado_impo_ui(),
            actualizar_trazado(e),
        ),
    )

    page.overlay[:] = [
        control for control in page.overlay if not isinstance(control, ft.FilePicker)
    ]
    file_picker = ft.FilePicker()

    async def procesar_pdf_para_imposicion(ruta_pdf, ordenamiento_precalculado=None):
        """
        Procesa un PDF para imposición: lee boxes, calcula tamaños, carga imágenes.

        Args:
            ruta_pdf: Ruta al PDF a procesar
            ordenamiento_precalculado: Ordenamiento ya calculado (opcional, evita recálculo)

        Returns:
            bool: True si procesamiento exitoso, False si error
        """
        global _CARGANDO_DATOS, boton_auto_manual_pliego, _PDF_VALIDATED, SANGRE
        _CARGANDO_DATOS = True
        print(f"[PROCESAR_PDF] Iniciando procesamiento de: {ruta_pdf}")

        # ✅ LIMPIAR CELDAS VISUALES DEL STACK Y FORZAR UPDATE
        try:
            stack_principal.controls.clear()
            stack_principal.update()
            print(f"[PROCESAR_PDF] Celdas del stack limpiadas y actualizadas")
        except Exception as ex:
            print(f"[PROCESAR_PDF] Error limpiando stack: {ex}")

        # ✅ RESETEAR ÍNDICE DE PLIEGO AL CARGAR NUEVO PDF
        state_pliego["index"] = 0
        textfield_pliego_actual.value = "1"
        print(f"[PROCESAR_PDF] Pliego reseteado a índice 0")

        # ✅ LIMPIAR COMPLETAMENTE archivo_seleccionado
        # Preservar dimensiones del MediaBox si fueron pasadas desde pdf_ordenado_ui
        mediabox_w = archivo_seleccionado.get("mediabox_width_mm")
        mediabox_h = archivo_seleccionado.get("mediabox_height_mm")

        archivo_seleccionado.clear()
        archivo_seleccionado["ruta"] = ""
        archivo_seleccionado["nombre"] = ""
        archivo_seleccionado["paginas"] = 0
        archivo_seleccionado["imagenes_secuenciales"] = {}
        archivo_seleccionado["boxes_by_page"] = {}

        # Restaurar dimensiones del MediaBox si existían
        if mediabox_w and mediabox_h:
            archivo_seleccionado["mediabox_width_mm"] = mediabox_w
            archivo_seleccionado["mediabox_height_mm"] = mediabox_h
            print(f"[PROCESAR_PDF] MediaBox preservado: {mediabox_w}×{mediabox_h} mm")

        print(f"[PROCESAR_PDF] archivo_seleccionado limpiado")

        try:
            # 1. INFORMACIÓN BÁSICA
            archivo_seleccionado["ruta"] = ruta_pdf

            # Obtener ruta original del PDF (del usuario, no temporal)
            ruta_original_real = obtener_ruta_pdf_original()
            if ruta_original_real:
                archivo_seleccionado["ruta_original"] = ruta_original_real
                print(f"[PROCESAR_PDF] Ruta original (usuario): {ruta_original_real}")
            else:
                # Fallback: si no hay ruta_original en memoria, usar la ruta actual
                archivo_seleccionado["ruta_original"] = ruta_pdf
                print(f"[PROCESAR_PDF] Ruta original (fallback): {ruta_pdf}")
            # Mostrar nombre original (si el PDF cargado es un PDF temporal ordenado, intentar derivar
            # el nombre del archivo original eliminando el sufijo "_ordenado_temp" para no mostrar
            # el nombre temporal en la UI)
            nombre_archivo_real = os.path.basename(ruta_pdf)
            try:
                # Eliminar extensión .pdf primero
                nombre_sin_ext = nombre_archivo_real
                if nombre_sin_ext.lower().endswith(".pdf"):
                    nombre_sin_ext = nombre_sin_ext[:-4]
                # Eliminar sufijos temporales
                if nombre_sin_ext.endswith("_ordenado_temp"):
                    nombre_sin_ext = nombre_sin_ext[: -len("_ordenado_temp")]
                elif nombre_sin_ext.endswith("_temp"):
                    nombre_sin_ext = nombre_sin_ext[: -len("_temp")]
                elif nombre_sin_ext.endswith("_ordenado"):
                    nombre_sin_ext = nombre_sin_ext[: -len("_ordenado")]
                # Guardar nombre limpio (sin extensión .pdf ni sufijos temporales)
                archivo_seleccionado["nombre"] = nombre_sin_ext
            except Exception:
                archivo_seleccionado["nombre"] = nombre_archivo_real

            # NOTA: no modificamos aquí la variable global MARCA_TEXTO_CONTENIDO para evitar
            # duplicados (antes se concatenaba nombre dentro de MARCA_TEXTO_CONTENIDO y luego
            # la UI añadía el nombre otra vez). La UI preferirá mostrar el nombre del archivo
            # cuando esté disponible.

            try:
                paginas, _ = await asyncio.to_thread(contar_paginas_pdf, ruta_pdf)
                archivo_seleccionado["paginas"] = paginas or 0
                print(
                    f"[PROCESAR_PDF] Páginas detectadas: {archivo_seleccionado['paginas']}"
                )
            except Exception as ex:
                print(f"[PROCESAR_PDF] Error contando páginas: {ex}")
                _CARGANDO_DATOS = False
                return False

            # Generar stamp del PDF para validación futura
            global _pdf_stamp
            try:
                stat = os.stat(ruta_pdf)
                _pdf_stamp = f"{stat.st_size}_{stat.st_mtime}"
                print(f"[PROCESAR_PDF] Stamp generado: {_pdf_stamp}")
            except:
                _pdf_stamp = None

            # 🔄 COPIA AUTOMÁTICA DEL PDF A TEMPORAL (si no está ya copiado)
            # Este paso es CRÍTICO para la extracción on-demand de imágenes
            # cuando se navega a pliegos no cacheados
            try:
                pdf_temporal_actual = obtener_pdf_ordenado_temp()
                if not pdf_temporal_actual:
                    print(
                        f"[PROCESAR_PDF] PDF temporal no disponible, copiando PDF original..."
                    )
                    pdf_temporal_actual = copiar_pdf_a_temporal(ruta_pdf)
                    if pdf_temporal_actual:
                        print(
                            f"[PROCESAR_PDF] ✅ PDF copiado a temporal: {pdf_temporal_actual}"
                        )
                        # Guardar en global para que cache on-demand pueda usarlo
                        guardar_pdf_ordenado_temp(pdf_temporal_actual)
                    else:
                        print(f"[PROCESAR_PDF] ⚠️ Error copiando PDF a temporal")
                else:
                    print(
                        f"[PROCESAR_PDF] PDF temporal ya disponible: {pdf_temporal_actual}"
                    )
            except Exception as ex:
                print(f"[PROCESAR_PDF] ⚠️ Error en copia automática de PDF: {ex}")
                # No abortamos, continuamos sin cache on-demand

            # 2. LEER BOXES DEL PDF (CRÍTICO)
            try:
                archivo_seleccionado["boxes_by_page"] = await asyncio.to_thread(
                    leer_cajas_por_pagina, ruta_pdf
                )
                print(f"[PROCESAR_PDF] Boxes leídas correctamente")

                # Actualizar info visual de boxes (usando página 0)
                if (
                    archivo_seleccionado["boxes_by_page"]
                    and 0 in archivo_seleccionado["boxes_by_page"]
                ):
                    boxes_p0 = archivo_seleccionado["boxes_by_page"][0]

                    def fmt_box(box_tuple):
                        if not box_tuple or len(box_tuple) != 4:
                            return "-"
                        w_pt = box_tuple[2] - box_tuple[0]
                        h_pt = box_tuple[3] - box_tuple[1]
                        w_mm = w_pt * 0.352778
                        h_mm = h_pt * 0.352778

                        # Obtener unidad actual
                        current_unit = get_preference("unit", "mm")
                        unit_label = get_unit_abbr(current_unit)
                        print(
                            f"[PDF LOAD] 🔄 Aplicando unidad {current_unit} al container verde"
                        )

                        # Convertir a unidad actual
                        w_converted = convert_from_mm(w_mm, current_unit)
                        h_converted = convert_from_mm(h_mm, current_unit)

                        return f"{w_converted:.2f} x {h_converted:.2f} {unit_label}"

                    texto_info_pdf_mediabox.value = t("Total: {0}").format(
                        fmt_box(boxes_p0.get("mediabox"))
                    )
                    texto_info_pdf_trimbox.value = t("Corte: {0}").format(
                        fmt_box(boxes_p0.get("trimbox"))
                    )

                    # Calcular sangre: (MediaBox - TrimBox) / 2 (asumiendo centrado) o usar BleedBox
                    # El usuario pidió: valor de la sangre = mediabox - bledbox (esto da el total de sangre, dividir por 2 para por lado)
                    # Pero BleedBox suele ser igual a MediaBox si hay sangre completa, o TrimBox si no.
                    # Vamos a calcular la diferencia entre TrimBox y MediaBox para ver la sangre real disponible

                    try:
                        mb = boxes_p0.get("mediabox")
                        tb = boxes_p0.get("trimbox")
                        if mb and tb:
                            mb_w = mb[2] - mb[0]
                            tb_w = tb[2] - tb[0]
                            sangre_pt = (mb_w - tb_w) / 2
                            sangre_mm = sangre_pt * 0.352778
                            # Obtener unidad actual y convertir
                            current_unit = get_preference("unit", "mm")
                            unit_label = get_unit_abbr(current_unit)
                            sangre_converted = convert_from_mm(sangre_mm, current_unit)

                            texto_info_pdf_bleedbox.value = t("Sangre: {0}").format(
                                f"{sangre_converted:.2f} {unit_label}"
                            )
                            print(
                                f"[PDF LOAD] ✅ Sangre calculada: {sangre_converted:.2f} {unit_label}"
                            )
                            # Solo si es trabajo nuevo (sin pdf_stamp): aplicar al
                            # textfield de sangre. ultima_modificacion NO sirve de
                            # indicador: persiste entre trabajos (la preservan
                            # limpiar_estado_imposicion y el reset de validación).
                            # En carga de .tns NO se toca (el archivo la reescribe
                            # via trabajo_manager, sin pasar por aqui).
                            try:
                                if not _estado_impo_ui.get("pdf_stamp"):
                                    SANGRE = float(sangre_mm)
                                    _estado_impo_ui["sangre"] = float(sangre_mm)
                                    textfield_sangre.value = (
                                        f"{sangre_converted:.2f}"
                                    )
                                    textfield_sangre.update()
                                    print(
                                        f"[PDF LOAD] ✅ Sangre del PDF aplicada al campo: {sangre_converted:.2f} {unit_label}"
                                    )
                            except Exception as ex:
                                print(
                                    f"[PDF LOAD] ⚠️ No se pudo aplicar sangre al campo: {ex}"
                                )
                        else:
                            texto_info_pdf_bleedbox.value = t("Sangre: -")
                    except:
                        texto_info_pdf_bleedbox.value = t("Sangre: -")

                    try:
                        texto_info_pdf_mediabox.update()
                        texto_info_pdf_trimbox.update()
                        texto_info_pdf_bleedbox.update()
                        # Actualizar el color del container según la sangre detectada
                        _actualizar_bg_container_info_pdf()
                        print(
                            f"[PDF LOAD] ✅ Container verde actualizado correctamente"
                        )
                    except:
                        pass  # Si aún no están en el árbol visual

                    # CRÍTICO: Llamar update_units después de cargar datos del PDF
                    try:
                        print(
                            f"[PDF LOAD] 🔄 Llamando update_units() después de cargar PDF..."
                        )
                        current_unit = get_preference("unit", "mm")
                        if "update_units_in_impo" in globals():
                            globals()["update_units_in_impo"](current_unit)
                            print(
                                f"[PDF LOAD] ✅ update_units() ejecutado con unidad: {current_unit}"
                            )
                        else:
                            print(
                                f"[PDF LOAD] ❌ update_units_in_impo no disponible en globals()"
                            )
                    except Exception as ex:
                        print(f"[PDF LOAD] ❌ Error ejecutando update_units(): {ex}")

                # Guardar metadata PDF en el estado de imposición inmediatamente
                try:
                    # Normalizar boxes a formato list para el stamp
                    p0 = archivo_seleccionado["boxes_by_page"].get(0, {})

                    def _box_to_list(b):
                        if not b:
                            return None
                        return [float(x) for x in b]

                    _estado_impo_ui.update(
                        {
                            "mediabox": _box_to_list(p0.get("mediabox")),
                            "cropbox": _box_to_list(
                                p0.get("trimbox") or p0.get("cropbox")
                            ),
                            "bleedbox": _box_to_list(p0.get("bleedbox")),
                            "pdf_ruta": archivo_seleccionado.get("ruta", ""),
                            "pdf_nombre": archivo_seleccionado.get("nombre", ""),
                            "pdf_paginas": archivo_seleccionado.get("paginas", 0),
                        }
                    )

                    # Marcar PDF como validado para permitir que guardar_estado_impo_ui
                    # persista los campos relacionados con el PDF.
                    try:
                        _PDF_VALIDATED = True
                    except Exception:
                        pass

                    # Persistir inmediatamente para evitar que otros flujos limpien datos
                    try:
                        guardar_estado_impo_ui()
                        print("[PROCESAR_PDF] Estado persistido tras leer boxes PDF")
                    except Exception as _e_st:
                        print(
                            f"[PROCESAR_PDF] Error persisting estado tras boxes: {_e_st}"
                        )
                except Exception as _e:
                    print(
                        f"[PROCESAR_PDF] No se pudo actualizar estado con boxes: {_e}"
                    )

            except Exception as ex:
                print(f"[PROCESAR_PDF] Error leyendo boxes: {ex}")
                _CARGANDO_DATOS = False
                return False

            # 3. CARGAR IMÁGENES SECUENCIALES
            archivo_seleccionado["imagenes_secuenciales"] = {}
            try:
                pdf_temp_ordenado = obtener_pdf_ordenado_temp()
                if pdf_temp_ordenado and os.path.abspath(ruta_pdf) == os.path.abspath(
                    pdf_temp_ordenado
                ):
                    imagenes_dir = os.path.join(
                        os.path.dirname(pdf_temp_ordenado), "imagenes"
                    )
                    if os.path.exists(imagenes_dir):
                        print(f"[PROCESAR_PDF] Cargando imágenes desde: {imagenes_dir}")
                        archivos_img = sorted(
                            [f for f in os.listdir(imagenes_dir) if f.endswith(".png")]
                        )

                        for f in archivos_img:
                            try:
                                # Extraer índice de página del nombre: pagina_0000_timestamp.png
                                parts = f.replace("pagina_", "").replace(".png", "")
                                # Si tiene timestamp, separar por guion bajo y tomar el primer número
                                idx_str = parts.split("_")[0] if "_" in parts else parts
                                idx = int(idx_str)
                                if idx < archivo_seleccionado["paginas"]:
                                    img_path = os.path.join(imagenes_dir, f)
                                    archivo_seleccionado["imagenes_secuenciales"][
                                        idx
                                    ] = img_path
                            except Exception as ex:
                                if DEBUG_IMPO_UI:
                                    print(
                                        f"[PROCESAR_PDF] Error procesando imagen {f}: {ex}"
                                    )
                                pass

                        print(
                            f"[PROCESAR_PDF] Cargadas {len(archivo_seleccionado['imagenes_secuenciales'])} imágenes"
                        )

                        # Calcular total de pliegos (considerar modo doble cara)
                        total_imgs = len(archivo_seleccionado["imagenes_secuenciales"])
                        rows_calc = (
                            int(textfield_grid_rows.value)
                            if textfield_grid_rows.value
                            else 1
                        )
                        cols_calc = (
                            int(textfield_grid_cols.value)
                            if textfield_grid_cols.value
                            else 1
                        )
                        celdas_por_pliego = max(1, rows_calc * cols_calc)
                        # Detectar modo doble cara usando el ordenamiento si está disponible
                        es_modo_doble = False
                        try:
                            orden = ordenamiento_calculado.get("ordenamiento", {})
                            if orden:
                                es_modo_doble = any(
                                    _es_dorso_val(v.get("doble_cara"))
                                    for k, v in orden.items()
                                    if isinstance(k, int) and isinstance(v, dict)
                                )
                            else:
                                es_modo_doble = bool(dropdown_doble_cara.value) and str(
                                    dropdown_doble_cara.value
                                ).lower().startswith("d")
                        except Exception:
                            es_modo_doble = False

                        # Delegar al helper para calcular y actualizar el total
                        actualizar_total_pliegos(total_imgs, rows_calc, cols_calc)
                        navegacion_pliegos_container.visible = True
                        actualizar_estado_botones_pliego()
            except Exception as ex:
                print(f"[PROCESAR_PDF] Error cargando imágenes: {ex}")

            # 4. USAR ORDENAMIENTO PRE-CALCULADO O CALCULAR
            if ordenamiento_precalculado:
                print("[PROCESAR_PDF] ✅ Usando ordenamiento pre-calculado")
                ordenamiento_calculado["ordenamiento"] = ordenamiento_precalculado

                # Calcular páginas requeridas
                paginas_requeridas = None
                if "_metadata" in ordenamiento_precalculado:
                    paginas_requeridas = ordenamiento_precalculado["_metadata"].get(
                        "paginas_pdf_original"
                    )

                if paginas_requeridas is None:
                    max_pagina = 0
                    for k, datos in ordenamiento_precalculado.items():
                        if (
                            isinstance(k, int)
                            and isinstance(datos, dict)
                            and datos.get("datos")
                        ):
                            max_pagina = max(max_pagina, max(datos["datos"]))
                    paginas_requeridas = max_pagina

                ordenamiento_calculado["paginas_requeridas"] = paginas_requeridas
            else:
                print("[PROCESAR_PDF] ⚠️ Recalculando ordenamiento (fallback)")
                recalcular_ordenamiento()

            # 5. VALIDAR PDF
            paginas_requeridas = ordenamiento_calculado.get("paginas_requeridas")

            if not (
                paginas_requeridas
                and archivo_seleccionado["paginas"] == paginas_requeridas
            ):
                print(f"[PROCESAR_PDF] ❌ PDF inválido")
                texto_validacion.value = f"❌ Error: tiene {archivo_seleccionado['paginas']}, necesita {paginas_requeridas}"
                texto_validacion.color = ERROR_COLOR
                boton_crear.disabled = True
                _CARGANDO_DATOS = False
                return False

            print(f"[PROCESAR_PDF] ✅ PDF válido")
            texto_validacion.value = (
                f"✅ Correcto: {archivo_seleccionado['paginas']} páginas"
            )
            texto_validacion.color = SUCCESS_COLOR

            if (
                isinstance(grafico_datos, dict)
                and "orden_grafico_visual" in grafico_datos
            ):
                boton_crear.disabled = False

            # 6. EXTRAER TAMAÑOS DE USUARIO (CRÍTICO)
            try:
                global TAMANO_USUARIO_W, TAMANO_USUARIO_H
                # Si la imposición NO está creada, pasamos los valores del mediabox y ponemos el chivato a True
                if not _estado_impo_ui.get("impo_creada", False):
                    # Regla: si TrimBox existe y difiere del MediaBox, usar TrimBox como tamaño de usuario
                    try:
                        boxes_tmp = _archivo_seleccionado.get("boxes_by_page")
                        p0_tmp = (
                            boxes_tmp.get(0)
                            if isinstance(boxes_tmp, dict) and 0 in boxes_tmp
                            else None
                        )
                        if p0_tmp:
                            tb_tmp = p0_tmp.get("trimbox")
                            mb_tmp = p0_tmp.get("mediabox")
                            if (
                                tb_tmp
                                and mb_tmp
                                and len(tb_tmp) == 4
                                and len(mb_tmp) == 4
                            ):
                                tb_w = abs(tb_tmp[2] - tb_tmp[0])
                                tb_h = abs(tb_tmp[3] - tb_tmp[1])
                                mb_w = abs(mb_tmp[2] - mb_tmp[0])
                                mb_h = abs(mb_tmp[3] - mb_tmp[1])
                                if (abs(tb_w - mb_w) > 0.001) or (
                                    abs(tb_h - mb_h) > 0.001
                                ):
                                    pt2mm = lambda pts: pts * 25.4 / 72.0
                                    TAMANO_USUARIO_W = pt2mm(tb_w)
                                    TAMANO_USUARIO_H = pt2mm(tb_h)
                                    print(
                                        f"[PROCESAR_PDF] [IMPO NUEVA] Tamaño preferido desde TrimBox (diferente de MediaBox): {TAMANO_USUARIO_W:.2f} x {TAMANO_USUARIO_H:.2f} mm"
                                    )
                    except Exception:
                        pass

                    # Si no se asignó desde TrimBox, usar valores preservados o boxes
                    if not (
                        isinstance(TAMANO_USUARIO_W, (int, float))
                        and isinstance(TAMANO_USUARIO_H, (int, float))
                    ):
                        if _archivo_seleccionado.get(
                            "mediabox_width_mm"
                        ) and _archivo_seleccionado.get("mediabox_height_mm"):
                            TAMANO_USUARIO_W = _archivo_seleccionado[
                                "mediabox_width_mm"
                            ]
                            TAMANO_USUARIO_H = _archivo_seleccionado[
                                "mediabox_height_mm"
                            ]
                            print(
                                f"[PROCESAR_PDF] [IMPO NUEVA] Tamaño desde _archivo_seleccionado: {TAMANO_USUARIO_W:.2f} x {TAMANO_USUARIO_H:.2f} mm"
                            )
                        else:
                            boxes = _archivo_seleccionado.get("boxes_by_page")
                            first = (
                                boxes.get(0)
                                if isinstance(boxes, dict) and 0 in boxes
                                else None
                            )
                            box = None
                            if first:
                                box = first.get("trimbox")
                                if not box or not all(
                                    isinstance(x, (int, float)) for x in box
                                ):
                                    box = first.get("mediabox")
                            if box and len(box) == 4:
                                x0, y0, x1, y1 = box
                                width_pts = abs(x1 - x0)
                                height_pts = abs(y1 - y0)
                                pt2mm = lambda pts: pts * 25.4 / 72.0
                                TAMANO_USUARIO_W = pt2mm(width_pts)
                                TAMANO_USUARIO_H = pt2mm(height_pts)
                                print(
                                    f"[PROCESAR_PDF] [IMPO NUEVA] Tamaño extraído del PDF boxes: {TAMANO_USUARIO_W:.2f} x {TAMANO_USUARIO_H:.2f} mm"
                                )
                    # Guardar en el estado y marcar impo_creada=True
                    _estado_impo_ui["tamano_usuario_w"] = TAMANO_USUARIO_W
                    _estado_impo_ui["tamano_usuario_h"] = TAMANO_USUARIO_H
                    _estado_impo_ui["impo_creada"] = True
                else:
                    print(
                        f"[PROCESAR_PDF] Tamaño restaurado del stamp: {TAMANO_USUARIO_W:.2f} x {TAMANO_USUARIO_H:.2f} mm (impo_creada=True)"
                    )
                # Actualizar textfields con los valores (ya sea extraídos o restaurados)
                unit = _estado_impo_ui.get("unit", _initial_unit_pref)
                try:
                    textfield_tamano_usuario_w.value = (
                        f"{convert_from_mm(TAMANO_USUARIO_W, unit):.2f}"
                    )
                    textfield_tamano_usuario_h.value = (
                        f"{convert_from_mm(TAMANO_USUARIO_H, unit):.2f}"
                    )
                except Exception:
                    # Fallback sin conversión si hay error
                    textfield_tamano_usuario_w.value = f"{TAMANO_USUARIO_W:.2f}"
                    textfield_tamano_usuario_h.value = f"{TAMANO_USUARIO_H:.2f}"
                textfield_tamano_usuario_w.visible = True
                textfield_tamano_usuario_h.visible = True
                textfield_tamano_usuario_w.update()
                textfield_tamano_usuario_h.update()
            except Exception as ex:
                print(f"[PROCESAR_PDF] Error extrayendo tamaños: {ex}")
                _CARGANDO_DATOS = False
                return False

            # 7. MOSTRAR CONTROLES Y GENERAR TRAZADO
            controles_trazado_container.visible = True
            boton_recalcular.visible = True
            boton_zoom_in.visible = True
            boton_zoom_out.visible = True
            boton_reset_zoom.visible = True
            viewer_container.visible = True

            # Hacer visibles todos los controles individuales
            # dropdown_tamanos_general.visible = True  # ELIMINADO
            textfield_ancho.visible = True
            textfield_alto.visible = True
            boton_auto_manual_pliego.visible = True

            textfield_tamano_usuario_w.visible = True
            textfield_tamano_usuario_h.visible = True
            textfield_sangre.visible = True

            # Controles avanzados y opciones
            try:
                dropdown_doble_cara.visible = True
                dropdown_rotacion.visible = True
                dropdown_copias.visible = True
                if "dropdown_tipo_corte" in globals():
                    dropdown_tipo_corte.visible = True
            except Exception:
                pass

            # Botones de ajustes
            boton_calles.visible = True
            boton_offset_pliego.visible = True
            boton_offset_pdfs.visible = True
            boton_cruces.visible = True
            boton_marcas_texto.visible = True

            # Actualizar UI
            try:
                texto_validacion.update()
                boton_crear.update()
                textfield_tamano_usuario_w.update()
                textfield_tamano_usuario_h.update()
                controles_trazado_container.update()
                viewer_container.update()
            except Exception:
                pass

            # 7.5. ACTUALIZAR TODOS LOS CONTROLES DESDE ESTADO (ANTES de generar trazado)
            # Esto es CRÍTICO: todos los datos del archivo deben estar en los widgets
            # ANTES de llamar a actualizar_trazado() para que la imposición se calcule correctamente
            # NOTA: NO llamar .update() aquí - los widgets aún no están en la página
            if (
                _estado_impo_ui
            ):  # Cambio: verificar si hay CUALQUIER dato en estado, no solo pdf_stamp
                print(
                    f"[PROCESAR_PDF] 🔄 Asignando valores a controles desde estado (ANTES de generar trazado)..."
                )
                try:
                    # Asegurar que las preferencias están cargadas para usar sus valores
                    try:
                        cargar_preferencias_imposicion()
                    except Exception:
                        pass

                    def _resolve_checkbox(*keys, default=False):
                        for k in keys:
                            if k in _estado_impo_ui:
                                return bool(_estado_impo_ui.get(k))
                        return bool(default)

                    # 1. CHECKBOXES (CRÍTICO - afectan el cálculo de imposición)
                    # Resolver con preferencia por claves históricas/variantes, usar
                    # valores cargados desde preferencias como default si no existe clave.
                    default_cruces = _estado_impo_ui.get("checkbox_cruces", False)
                    default_lineas = _estado_impo_ui.get("checkbox_lineas_corte", False)
                    default_marcas = _estado_impo_ui.get("checkbox_marcas_texto", False)
                    default_exterior = _estado_impo_ui.get(
                        "checkbox_linea_exterior", True
                    )

                    checkbox_cruces.value = _resolve_checkbox(
                        "CHECK_BOX_CRUCES",
                        "CHECK_BOX_CRUCES_Y_MARCAS",
                        "checkbox_cruces",
                        default=default_cruces,
                    )
                    checkbox_lineas_corte.value = _resolve_checkbox(
                        "CHECK_BOX_LINEAS_CORTE",
                        "CHECK_BOX_LINEAS_DE_CORTE",
                        "checkbox_lineas_corte",
                        default=default_lineas,
                    )
                    checkbox_marcas_texto.value = _resolve_checkbox(
                        "CHECK_BOX_MARCAS_TEXTO",
                        "CHECK_BOX_MARCAS_DE_TEXTO",
                        "checkbox_marcas_texto",
                        default=default_marcas,
                    )
                    checkbox_linea_exterior.value = _resolve_checkbox(
                        "CHECK_BOX_LINEA_EXTERIOR",
                        "checkbox_linea_exterior",
                        default=default_exterior,
                    )

                    print(f"[PASO 7.5] ✅ Checkboxes asignados desde estado:")
                    print(
                        f"   cruces={checkbox_cruces.value} (estado_keys_tried=['CHECK_BOX_CRUCES','CHECK_BOX_CRUCES_Y_MARCAS','checkbox_cruces'])"
                    )
                    print(
                        f"   lineas={checkbox_lineas_corte.value} (estado_keys_tried=['CHECK_BOX_LINEAS_CORTE','CHECK_BOX_LINEAS_DE_CORTE','checkbox_lineas_corte'])"
                    )
                    print(
                        f"   marcas={checkbox_marcas_texto.value} (estado_keys_tried=['CHECK_BOX_MARCAS_TEXTO','CHECK_BOX_MARCAS_DE_TEXTO','checkbox_marcas_texto'])"
                    )
                    print(
                        f"   exterior={checkbox_linea_exterior.value} (estado_keys_tried=['CHECK_BOX_LINEA_EXTERIOR','checkbox_linea_exterior'])"
                    )

                    # 2. OFFSETS - NO actualizar widgets (no están en scope, son de diálogos)
                    # Los offsets se actualizarán desde las globales cuando el usuario abra los diálogos
                    if "offset_img_x" in _estado_impo_ui:
                        print(
                            f"   offset_img_x en estado: {_estado_impo_ui.get('offset_img_x')}"
                        )
                    if "offset_img_y" in _estado_impo_ui:
                        print(
                            f"   offset_img_y en estado: {_estado_impo_ui.get('offset_img_y')}"
                        )
                    if "offset_trazado_x" in _estado_impo_ui:
                        print(
                            f"   offset_trazado_x en estado: {_estado_impo_ui.get('offset_trazado_x')}"
                        )
                    if "offset_trazado_y" in _estado_impo_ui:
                        print(
                            f"   offset_trazado_y en estado: {_estado_impo_ui.get('offset_trazado_y')}"
                        )

                    # 3. GRID
                    if "grid_cols" in _estado_impo_ui:
                        textfield_grid_cols.value = str(
                            _estado_impo_ui.get("grid_cols", 1)
                        )
                        print(f"   grid_cols: {_estado_impo_ui.get('grid_cols')}")
                    if "grid_rows" in _estado_impo_ui:
                        textfield_grid_rows.value = str(
                            _estado_impo_ui.get("grid_rows", 1)
                        )
                        print(f"   grid_rows: {_estado_impo_ui.get('grid_rows')}")

                    # 4. PLIEGO (ancho/alto)
                    unit = _estado_impo_ui.get("unit", _initial_unit_pref)
                    if "pliego_ancho" in _estado_impo_ui and _estado_impo_ui.get(
                        "pliego_ancho"
                    ):
                        try:
                            textfield_ancho.value = f"{convert_from_mm(float(_estado_impo_ui.get('pliego_ancho')), unit):.2f}"
                        except Exception:
                            textfield_ancho.value = (
                                f"{_estado_impo_ui.get('pliego_ancho'):.2f}"
                            )
                        print(f"   pliego_ancho: {_estado_impo_ui.get('pliego_ancho')}")
                    if "pliego_alto" in _estado_impo_ui and _estado_impo_ui.get(
                        "pliego_alto"
                    ):
                        try:
                            textfield_alto.value = f"{convert_from_mm(float(_estado_impo_ui.get('pliego_alto')), unit):.2f}"
                        except Exception:
                            textfield_alto.value = (
                                f"{_estado_impo_ui.get('pliego_alto'):.2f}"
                            )
                        print(f"   pliego_alto: {_estado_impo_ui.get('pliego_alto')}")

                    # 5. SANGRE
                    if "sangre" in _estado_impo_ui:
                        try:
                            textfield_sangre.value = f"{convert_from_mm(float(_estado_impo_ui.get('sangre', 3.0)), unit):.2f}"
                        except Exception:
                            textfield_sangre.value = (
                                f"{_estado_impo_ui.get('sangre', 3.0):.2f}"
                            )
                        print(f"   sangre: {_estado_impo_ui.get('sangre')}")

                    print(
                        f"[PROCESAR_PDF] ✅ Valores asignados a controles (se actualizarán cuando se muestren)"
                    )

                except Exception as ex:
                    print(
                        f"[PROCESAR_PDF] ❌ Error asignando valores a controles: {ex}"
                    )
                    import traceback

                    traceback.print_exc()

            # 7.6. ACTUALIZAR VARIABLES GLOBALES desde estado (CRÍTICO para actualizar_trazado)
            # Los widgets ya están actualizados, ahora actualizar las globales que usa actualizar_trazado()
            if _estado_impo_ui.get("pdf_stamp"):
                print(
                    f"[PROCESAR_PDF] 🔄 Actualizando variables GLOBALES desde estado..."
                )
                try:
                    # NOTA: TAMANO_USUARIO_W/H y SANGRE ya están declaradas global
                    # al inicio de la función, no redeclarar
                    global LONGITUD_CRUZ_MM, GROSOR_CRUZ_PT, OFFSET_CRUZ_MM, AUTO_SANGRE_OFFSET_CRUZ
                    global OFFSET_SEGURIDAD_MM, LONGITUD_BRAZO_MAX_MM
                    global USER_OFFSET_IMAGEN_X_MM, USER_OFFSET_IMAGEN_Y_MM
                    global USER_OFFSET_TRAZADO_X_MM, USER_OFFSET_TRAZADO_Y_MM
                    global GRID_COLS, GRID_ROWS, CALLES_L
                    global MARCA_TEXTO_CONTENIDO, MARCA_TEXTO_POS_SUP_IZQ, MARCA_TEXTO_POS_SUP_DER
                    global MARCA_TEXTO_POS_INF_IZQ, MARCA_TEXTO_POS_INF_DER, MARCA_TEXTO_POS_CENTRO_SUP
                    global MARCA_TEXTO_POS_CENTRO_INF, MARCA_TEXTO_POS_CENTRO_LAT_IZQ, MARCA_TEXTO_POS_CENTRO_LAT_DER
                    global MARCA_TEXTO_ROTACION, MARCA_TEXTO_FAMILIA, MARCA_TEXTO_TIPO, MARCA_TEXTO_CUERPO
                    global MARCA_TEXTO_COLOR, MARCA_TEXTO_OFFSET_H_MM, MARCA_TEXTO_OFFSET_V_MM

                    # Configuración de cruces
                    if "longitud_cruz_mm" in _estado_impo_ui:
                        LONGITUD_CRUZ_MM = _estado_impo_ui.get("longitud_cruz_mm", 10.0)
                        print(f"   LONGITUD_CRUZ_MM: {LONGITUD_CRUZ_MM}")
                    if "grosor_cruz_pt" in _estado_impo_ui:
                        GROSOR_CRUZ_PT = _estado_impo_ui.get("grosor_cruz_pt", 0.5)
                        print(f"   GROSOR_CRUZ_PT: {GROSOR_CRUZ_PT}")
                    if "offset_cruz_mm" in _estado_impo_ui:
                        OFFSET_CRUZ_MM = _estado_impo_ui.get("offset_cruz_mm", 5.0)
                        print(f"   OFFSET_CRUZ_MM: {OFFSET_CRUZ_MM}")
                    if "auto_sangre_offset_cruz" in _estado_impo_ui:
                        AUTO_SANGRE_OFFSET_CRUZ = _estado_impo_ui.get(
                            "auto_sangre_offset_cruz", False
                        )
                        print(f"   AUTO_SANGRE_OFFSET_CRUZ: {AUTO_SANGRE_OFFSET_CRUZ}")
                    if "offset_seguridad_mm" in _estado_impo_ui:
                        OFFSET_SEGURIDAD_MM = _estado_impo_ui.get(
                            "offset_seguridad_mm", 1.0
                        )
                        print(f"   OFFSET_SEGURIDAD_MM: {OFFSET_SEGURIDAD_MM}")
                    if "longitud_brazo_max_mm" in _estado_impo_ui:
                        LONGITUD_BRAZO_MAX_MM = _estado_impo_ui.get(
                            "longitud_brazo_max_mm", 5.0
                        )
                        print(f"   LONGITUD_BRAZO_MAX_MM: {LONGITUD_BRAZO_MAX_MM}")

                    # Offsets de imagen y trazado
                    if "offset_img_x" in _estado_impo_ui:
                        USER_OFFSET_IMAGEN_X_MM = _estado_impo_ui.get(
                            "offset_img_x", 0.0
                        )
                        print(f"   USER_OFFSET_IMAGEN_X_MM: {USER_OFFSET_IMAGEN_X_MM}")
                    if "offset_img_y" in _estado_impo_ui:
                        USER_OFFSET_IMAGEN_Y_MM = _estado_impo_ui.get(
                            "offset_img_y", 0.0
                        )
                        print(f"   USER_OFFSET_IMAGEN_Y_MM: {USER_OFFSET_IMAGEN_Y_MM}")
                    if "offset_trazado_x" in _estado_impo_ui:
                        USER_OFFSET_TRAZADO_X_MM = _estado_impo_ui.get(
                            "offset_trazado_x", 0.0
                        )
                        print(
                            f"   USER_OFFSET_TRAZADO_X_MM: {USER_OFFSET_TRAZADO_X_MM}"
                        )
                    if "offset_trazado_y" in _estado_impo_ui:
                        USER_OFFSET_TRAZADO_Y_MM = _estado_impo_ui.get(
                            "offset_trazado_y", 0.0
                        )
                        print(
                            f"   USER_OFFSET_TRAZADO_Y_MM: {USER_OFFSET_TRAZADO_Y_MM}"
                        )

                    # Grid, tamaños y sangre (ya deberían estar, pero verificar)
                    if "grid_cols" in _estado_impo_ui:
                        GRID_COLS = _estado_impo_ui.get("grid_cols", 1)
                        print(f"   GRID_COLS: {GRID_COLS}")
                    if "grid_rows" in _estado_impo_ui:
                        GRID_ROWS = _estado_impo_ui.get("grid_rows", 1)
                        print(f"   GRID_ROWS: {GRID_ROWS}")
                    if "tamano_usuario_w" in _estado_impo_ui:
                        TAMANO_USUARIO_W = _estado_impo_ui.get(
                            "tamano_usuario_w", 210.0
                        )
                        print(f"   TAMANO_USUARIO_W: {TAMANO_USUARIO_W}")
                    if "tamano_usuario_h" in _estado_impo_ui:
                        TAMANO_USUARIO_H = _estado_impo_ui.get(
                            "tamano_usuario_h", 100.0
                        )
                        print(f"   TAMANO_USUARIO_H: {TAMANO_USUARIO_H}")
                    if "sangre" in _estado_impo_ui:
                        SANGRE = _estado_impo_ui.get("sangre", 3.0)
                        print(f"   SANGRE: {SANGRE}")
                    if "calles_list" in _estado_impo_ui:
                        CALLES_L = _estado_impo_ui.get("calles_list", [])
                        print(f"   CALLES_L: {CALLES_L}")

                    # Configuración de marca de texto
                    if "marca_texto_contenido" in _estado_impo_ui:
                        MARCA_TEXTO_CONTENIDO = _estado_impo_ui.get(
                            "marca_texto_contenido", "NumStack - Imposición"
                        )
                        print(f"   MARCA_TEXTO_CONTENIDO: {MARCA_TEXTO_CONTENIDO}")
                    if "marca_texto_pos_sup_izq" in _estado_impo_ui:
                        MARCA_TEXTO_POS_SUP_IZQ = _estado_impo_ui.get(
                            "marca_texto_pos_sup_izq", False
                        )
                        print(f"   MARCA_TEXTO_POS_SUP_IZQ: {MARCA_TEXTO_POS_SUP_IZQ}")
                    if "marca_texto_pos_sup_der" in _estado_impo_ui:
                        MARCA_TEXTO_POS_SUP_DER = _estado_impo_ui.get(
                            "marca_texto_pos_sup_der", False
                        )
                        print(f"   MARCA_TEXTO_POS_SUP_DER: {MARCA_TEXTO_POS_SUP_DER}")
                    if "marca_texto_pos_inf_izq" in _estado_impo_ui:
                        MARCA_TEXTO_POS_INF_IZQ = _estado_impo_ui.get(
                            "marca_texto_pos_inf_izq", False
                        )
                        print(f"   MARCA_TEXTO_POS_INF_IZQ: {MARCA_TEXTO_POS_INF_IZQ}")
                    if "marca_texto_pos_inf_der" in _estado_impo_ui:
                        MARCA_TEXTO_POS_INF_DER = _estado_impo_ui.get(
                            "marca_texto_pos_inf_der", False
                        )
                        print(f"   MARCA_TEXTO_POS_INF_DER: {MARCA_TEXTO_POS_INF_DER}")
                    if "marca_texto_pos_centro_sup" in _estado_impo_ui:
                        MARCA_TEXTO_POS_CENTRO_SUP = _estado_impo_ui.get(
                            "marca_texto_pos_centro_sup", False
                        )
                        print(
                            f"   MARCA_TEXTO_POS_CENTRO_SUP: {MARCA_TEXTO_POS_CENTRO_SUP}"
                        )
                    if "marca_texto_pos_centro_inf" in _estado_impo_ui:
                        MARCA_TEXTO_POS_CENTRO_INF = _estado_impo_ui.get(
                            "marca_texto_pos_centro_inf", False
                        )
                        print(
                            f"   MARCA_TEXTO_POS_CENTRO_INF: {MARCA_TEXTO_POS_CENTRO_INF}"
                        )
                    if "marca_texto_pos_centro_lat_izq" in _estado_impo_ui:
                        MARCA_TEXTO_POS_CENTRO_LAT_IZQ = _estado_impo_ui.get(
                            "marca_texto_pos_centro_lat_izq", False
                        )
                        print(
                            f"   MARCA_TEXTO_POS_CENTRO_LAT_IZQ: {MARCA_TEXTO_POS_CENTRO_LAT_IZQ}"
                        )
                    if "marca_texto_pos_centro_lat_der" in _estado_impo_ui:
                        MARCA_TEXTO_POS_CENTRO_LAT_DER = _estado_impo_ui.get(
                            "marca_texto_pos_centro_lat_der", False
                        )
                        print(
                            f"   MARCA_TEXTO_POS_CENTRO_LAT_DER: {MARCA_TEXTO_POS_CENTRO_LAT_DER}"
                        )
                    if "marca_texto_rotacion" in _estado_impo_ui:
                        MARCA_TEXTO_ROTACION = _estado_impo_ui.get(
                            "marca_texto_rotacion", 0
                        )
                        print(f"   MARCA_TEXTO_ROTACION: {MARCA_TEXTO_ROTACION}")
                    if "marca_texto_familia" in _estado_impo_ui:
                        MARCA_TEXTO_FAMILIA = _estado_impo_ui.get(
                            "marca_texto_familia", "Arial"
                        )
                        print(f"   MARCA_TEXTO_FAMILIA: {MARCA_TEXTO_FAMILIA}")
                    if "marca_texto_tipo" in _estado_impo_ui:
                        MARCA_TEXTO_TIPO = _estado_impo_ui.get(
                            "marca_texto_tipo", "Regular"
                        )
                        print(f"   MARCA_TEXTO_TIPO: {MARCA_TEXTO_TIPO}")
                    if "marca_texto_cuerpo" in _estado_impo_ui:
                        MARCA_TEXTO_CUERPO = _estado_impo_ui.get(
                            "marca_texto_cuerpo", 12
                        )
                        print(f"   MARCA_TEXTO_CUERPO: {MARCA_TEXTO_CUERPO}")
                    if "marca_texto_color" in _estado_impo_ui:
                        MARCA_TEXTO_COLOR = _estado_impo_ui.get(
                            "marca_texto_color", "black"
                        )
                        print(f"   MARCA_TEXTO_COLOR: {MARCA_TEXTO_COLOR}")
                    if "marca_texto_offset_h_mm" in _estado_impo_ui:
                        MARCA_TEXTO_OFFSET_H_MM = _estado_impo_ui.get(
                            "marca_texto_offset_h_mm", 0.0
                        )
                        print(f"   MARCA_TEXTO_OFFSET_H_MM: {MARCA_TEXTO_OFFSET_H_MM}")
                    if "marca_texto_offset_v_mm" in _estado_impo_ui:
                        MARCA_TEXTO_OFFSET_V_MM = _estado_impo_ui.get(
                            "marca_texto_offset_v_mm", 0.0
                        )
                        print(f"   MARCA_TEXTO_OFFSET_V_MM: {MARCA_TEXTO_OFFSET_V_MM}")

                    # Tamaño de pliego y estado congelado
                    global TAMANO_FINAL_PLIEGO, PLIEGO_CONGELADO
                    if (
                        "pliego_ancho" in _estado_impo_ui
                        and "pliego_alto" in _estado_impo_ui
                    ):
                        TAMANO_FINAL_PLIEGO["w_mm"] = _estado_impo_ui.get(
                            "pliego_ancho"
                        )
                        TAMANO_FINAL_PLIEGO["h_mm"] = _estado_impo_ui.get("pliego_alto")
                        print(
                            f"   TAMANO_FINAL_PLIEGO: {TAMANO_FINAL_PLIEGO['w_mm']}x{TAMANO_FINAL_PLIEGO['h_mm']} mm"
                        )
                    if "pliego_congelado" in _estado_impo_ui:
                        PLIEGO_CONGELADO = _estado_impo_ui.get(
                            "pliego_congelado", False
                        )
                        print(f"   PLIEGO_CONGELADO: {PLIEGO_CONGELADO}")
                        # Actualizar botón si existe
                        if boton_auto_manual_pliego is not None:
                            boton_auto_manual_pliego.content = (
                                t("Tamaño manual")
                                if PLIEGO_CONGELADO
                                else t("Tamaño auto")
                            )
                            print(
                                f"   boton_auto_manual_pliego.content actualizado: {boton_auto_manual_pliego.content}"
                            )

                    print(
                        f"[PROCESAR_PDF] ✅ Variables globales actualizadas correctamente"
                    )

                except Exception as ex:
                    print(f"[PROCESAR_PDF] ❌ Error actualizando globales: {ex}")
                    import traceback

                    traceback.print_exc()

            # 8. GENERAR TRAZADO (CRÍTICO - ahora con TODOS los valores correctos en globales)
            print(f"[PROCESAR_PDF] Llamando a actualizar_trazado()")
            actualizar_trazado(None)
            print(f"[PROCESAR_PDF] ✅ Procesamiento completado")

            # 9. GUARDAR ESTADO COMPLETO (incluye tamaños de usuario)
            print(f"[PROCESAR_PDF] 💾 Guardando estado de la UI...")
            guardar_estado_impo_ui()

            # Solo marcar como modificado si NO estamos restaurando desde un stamp guardado
            # (si hay stamp, significa que cargamos un trabajo guardado, no hay cambios todavía)
            tiene_stamp_guardado = (
                _estado_impo_ui.get("pdf_stamp")
                and ordenamiento_precalculado is not None
            )
            if not tiene_stamp_guardado:
                print(
                    f"[PROCESAR_PDF] 📝 Marcando como modificado (PDF nuevo o sin stamp previo)"
                )
                mark_modified()
            else:
                print(
                    f"[PROCESAR_PDF] ✅ Datos restaurados - NO marcar como modificado"
                )

            _CARGANDO_DATOS = False
            return True

        except Exception as ex:
            print(f"[PROCESAR_PDF] ❌ Error general: {ex}")
            import traceback

            traceback.print_exc()
            _CARGANDO_DATOS = False
            return False

    async def on_file_picker_result(e):
        """Callback del file picker - ahora solo llama a procesar_pdf_para_imposicion()"""
        print("[DEBUG PDF] on_file_picker_result llamado")
        try:
            if e.files and len(e.files) > 0:
                archivo = e.files[0]
                print(f"[DEBUG PDF] Archivo seleccionado: {archivo.name}")

                # ═══════════════════════════════════════════════════════════════════════════════
                # CARGAR PREFERENCIAS ANTES DE PROCESAR PDF
                # ═══════════════════════════════════════════════════════════════════════════════
                # ⚠️ IMPORTANTE: NO cargar preferencias si ya hay datos de trabajo cargado
                estado = _estado_impo_ui
                # Determinar si ya hay un trabajo cargado comprobando campos significativos
                trabajo_cargado = bool(
                    estado.get("pdf_stamp") or estado.get("ultima_modificacion")
                )

                if not trabajo_cargado:
                    print("[PREF] 🔄 Cargando preferencias antes de procesar PDF...")
                    cargar_preferencias_imposicion(
                        checkbox_cruces=checkbox_cruces,
                        checkbox_lineas_corte=checkbox_lineas_corte,
                        checkbox_marcas_texto=checkbox_marcas_texto,
                        checkbox_linea_exterior=checkbox_linea_exterior,
                    )
                else:
                    print(
                        "[PREF] ⏭️ Trabajo cargado detectado en file picker - saltando carga de preferencias (pdf_stamp/ultima_modificacion presente)"
                    )

                # Procesar PDF usando la función refactorizada
                exito = await procesar_pdf_para_imposicion(
                    archivo.path, ordenamiento_precalculado=None
                )

                if exito:
                    # Marcar como modificado al cargar un PDF
                    mark_modified()

                    # Actualizar checkboxes desde estado (CRÍTICO - mostrar valores correctos visualmente)
                    if _estado_impo_ui:
                        if "CHECK_BOX_CRUCES" in _estado_impo_ui:
                            checkbox_cruces.value = _estado_impo_ui.get(
                                "CHECK_BOX_CRUCES", False
                            )
                        if "CHECK_BOX_LINEAS_CORTE" in _estado_impo_ui:
                            checkbox_lineas_corte.value = _estado_impo_ui.get(
                                "CHECK_BOX_LINEAS_CORTE", False
                            )
                        if "CHECK_BOX_MARCAS_TEXTO" in _estado_impo_ui:
                            checkbox_marcas_texto.value = _estado_impo_ui.get(
                                "CHECK_BOX_MARCAS_TEXTO", False
                            )
                        if "CHECK_BOX_LINEA_EXTERIOR" in _estado_impo_ui:
                            checkbox_linea_exterior.value = _estado_impo_ui.get(
                                "CHECK_BOX_LINEA_EXTERIOR", True
                            )
                        print(
                            f"[UI UPDATE] Checkboxes actualizados visualmente: cruces={checkbox_cruces.value}, lineas={checkbox_lineas_corte.value}, marcas={checkbox_marcas_texto.value}, exterior={checkbox_linea_exterior.value}"
                        )
                        try:
                            checkbox_cruces.update()
                            checkbox_lineas_corte.update()
                            checkbox_marcas_texto.update()
                            checkbox_linea_exterior.update()
                        except Exception as ex:
                            print(f"[UI UPDATE] Error actualizando checkboxes: {ex}")

                    # Actualizar textos de UI
                    texto_archivo.value = archivo_seleccionado["nombre"]
                    texto_paginas.value = f"Páginas: {archivo_seleccionado['paginas']}"
                    texto_paginas_requeridas.visible = False

                    try:
                        texto_archivo.update()
                        texto_paginas.update()
                        texto_paginas_requeridas.update()
                    except Exception:
                        pass
            else:
                print(f"[DEBUG PDF] No se seleccionó ningún archivo")
                archivo_seleccionado.update({"ruta": "", "nombre": "", "paginas": 0})
                texto_archivo.value = "Ningún archivo seleccionado"
                texto_paginas.value = "Páginas: 0"
                boton_crear.disabled = True

                try:
                    texto_archivo.update()
                    texto_paginas.update()
                    boton_crear.update()
                except Exception:
                    pass
        except Exception as ex:
            print(f"[DEBUG PDF] Error en on_file_picker_result: {ex}")

    # Flet 1.0: FilePicker es Service (auto-registra en construcción)

    async def abrir_filepicker(e):
        try:
            files = await file_picker.pick_files(
                dialog_title="Seleccionar PDF para imposición",
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["pdf"],
            )
        except Exception:
            mostrar_snackbar(
                page,
                t("Error al abrir selector de archivos"),
                SNACKBAR_COLOR_ERROR,
                3000,
            )
            return
        # Flet 1.0: on_file_picker_result actualiza UI (updates) → correr en el loop;
        # el fitz pesado ya va a to_thread dentro de procesar_pdf_para_imposicion
        await on_file_picker_result(
            SimpleNamespace(
                files=files or [],
                path=(files[0].path if files else None),
            )
        )

    boton_cargar_pdf = ft.Button(
        "Cargar PDF",
        icon=ft.Icons.PICTURE_AS_PDF,
        width=120,
        height=35,
        visible=False,
        on_click=abrir_filepicker,
        bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
        style=ft.ButtonStyle(
            color={
                ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                "hovered": BOTONES_GENERICOS_HOVER_COLOR,
            },
            overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
            padding=ft.Padding(0, 0, 0, 0),
            shape=ft.RoundedRectangleBorder(radius=10),
        ),
    )

    def procesar_imposicion(e):
        if not (
            isinstance(grafico_datos, dict) and "orden_grafico_visual" in grafico_datos
        ):
            mostrar_snackbar(
                page,
                t("Error: Debe generar un gráfico antes de crear la imposición."),
                SNACKBAR_COLOR_ERROR,
                4000,
            )
            return
        paginas_requeridas = ordenamiento_calculado.get("paginas_requeridas")
        if (
            paginas_requeridas
            and archivo_seleccionado.get("paginas") != paginas_requeridas
        ):
            mostrar_snackbar(
                page,
                t("El PDF cargado no tiene {0} páginas requeridas.").format(
                    paginas_requeridas
                ),
                SNACKBAR_COLOR_ERROR,
                4000,
            )
            return

        # NUEVO: obtener papel_w_mm y papel_h_mm desde TAMANO_FINAL_PLIEGO (en mm)
        # NO leer de textfields que ahora muestran valores convertidos
        papel_w_mm = None
        papel_h_mm = None
        try:
            # Usar las variables globales en mm, no los textfields convertidos
            papel_w_mm = TAMANO_FINAL_PLIEGO.get("w_mm", 0) or 0
            papel_h_mm = TAMANO_FINAL_PLIEGO.get("h_mm", 0) or 0
            if papel_w_mm <= 0 or papel_h_mm <= 0:
                raise ValueError
        except Exception:
            mostrar_snackbar(
                page,
                t("Introduzca dimensiones válidas de pliego (ancho y alto)."),
                SNACKBAR_COLOR_ERROR,
                4000,
            )
            return

        try:
            rot = dropdown_rotacion.value or ""
            if isinstance(rot, str) and rot.lower().startswith("v"):
                papel_w_mm, papel_h_mm = papel_h_mm, papel_w_mm
        except Exception:
            pass

        try:
            doble_cara = bool(dropdown_doble_cara.value) and str(
                dropdown_doble_cara.value
            ).lower().startswith("d")
        except Exception:
            doble_cara = False

        try:
            progress_row.visible = True
            _init_progress_counter(0)
            progress_row.update()
        except Exception:
            pass

        async def worker():
            # La implementación de imposición basada en IMPO_PDF fue eliminada.
            # En lugar de intentar importar módulos que ya no existen, avisamos al usuario.
            try:
                try:
                    mostrar_alert_dialog(
                        page,
                        False,
                        error_msg="La funcionalidad de imposición ha sido eliminada del código.",
                    )
                except Exception:
                    mostrar_snackbar(
                        page,
                        t("La funcionalidad de imposición no está disponible."),
                        SNACKBAR_COLOR_ERROR,
                        5000,
                    )
            finally:
                try:
                    _cerrar_imposicion_overlay()
                except Exception:
                    pass

        page.run_task(worker)

    boton_crear = ft.Button(
        "Crear imposición",
        width=160,
        on_click=procesar_imposicion,
        disabled=False,
        visible=False,
        bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
        style=ft.ButtonStyle(
            color={
                ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                "hovered": BOTONES_GENERICOS_HOVER_COLOR,
            },
            overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
            padding=ft.Padding(0, 0, 0, 0),
            shape=ft.RoundedRectangleBorder(radius=10),
        ),
    )

    boton_cancelar = ft.Container(
        content=ft.Icon(ft.Icons.EXIT_TO_APP, size=24, color=BOTONES_GENERICOS_COLOR),
        width=40,
        height=40,
        border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
        border_radius=4,
        bgcolor=FONDO_TEXTFIELDS_COLOR,
        alignment=ft.Alignment.CENTER,
        on_click=lambda e: _cerrar_imposicion_overlay(e),
        tooltip=t("Cerrar"),
    )

    # Wrapper para guardar trabajo que sincroniza el estado local de impo_ui
    def guardar_trabajo_wrapper(e):
        """Llama a on_guardar_trabajo de app.py y luego sincroniza el estado local"""
        if on_guardar_trabajo:
            # Llamar a la función de guardado de app.py
            on_guardar_trabajo(e)
            # Sincronizar estado local de impo_ui
            nonlocal project_modified
            # NO resetear project_modified al cerrar, solo actualizar UI si es necesario
            update_project_state_ui()
        else:
            print("[TODO] Guardar trabajo")

    # Botón Guardar Trabajo
    boton_guardar_trabajo = ft.Container(
        content=ft.Icon(ft.Icons.FILE_DOWNLOAD, size=24, color=BOTONES_GENERICOS_COLOR),
        width=40,
        height=40,
        border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
        border_radius=4,
        bgcolor=FONDO_TEXTFIELDS_COLOR,
        alignment=ft.Alignment.CENTER,
        on_click=guardar_trabajo_wrapper,
        tooltip=t("Guardar trabajo"),
    )

    # Definir función de actualización del estado DESPUÉS de crear el botón
    def update_project_state_ui():
        """Actualiza el estado visual del botón guardar según estado del proyecto"""
        try:
            # Si la app principal expuso una callback global, delegar en ella
            try:
                cb = getattr(builtins, "_on_trabajo_modificado_change", None)
            except Exception:
                cb = None

            if callable(cb):
                try:
                    cb()
                    # No hacemos return: permitir que impo_ui también actualice
                    # su propio botón usando la misma fuente de verdad.
                except Exception:
                    # Si falla la delegación, caer al fallback local
                    pass
            # Intentar obtener flag global expuesto por la app (si existe)
            try:
                app_proj_mod = getattr(builtins, "_project_modified", None)
            except Exception:
                app_proj_mod = None

            # Fallback local: mantener la lógica original si no hay callback
            print(
                f"[UPDATE STATE UI] (fallback) project_modified={project_modified}, path={current_project_path}, name={project_name}"
            )
            try:
                trabajo_flag = bool(
                    (_estado_impo_ui.get("trabajo_modificado", False))
                    or bool(app_proj_mod)
                )
            except Exception:
                trabajo_flag = bool(app_proj_mod) or project_modified

            if trabajo_flag:
                print("[IMPO UI BUTTON COLOR] set ORANGE (trabajo_flag=True)")
                boton_guardar_trabajo.bgcolor = ft.Colors.ORANGE_700
                boton_guardar_trabajo.content.color = ft.Colors.WHITE
            else:
                print("[IMPO UI BUTTON COLOR] set NORMAL (trabajo_flag=False)")
                boton_guardar_trabajo.bgcolor = FONDO_TEXTFIELDS_COLOR
                boton_guardar_trabajo.content.color = TEXTOS_FASE_1_COLOR

            try:
                if boton_guardar_trabajo.page:
                    boton_guardar_trabajo.update()
                else:
                    print("[UPDATE STATE UI] Botón no está en página todavía")
            except Exception as e:
                print(f"[UPDATE STATE UI] Error al actualizar botón: {e}")
        except Exception as ex:
            print(f"[ERROR update_project_state_ui] {ex}")

    # Permitir que el módulo `app.py` registre un callback global
    # `_on_trabajo_modificado_change` para sincronizar su icono.

    # Inicializar estado visual del botón guardar
    # Exponer la función para que `guardar_estado_impo_ui()` (módulo) pueda invocarla
    try:
        globals()["_impo_update_project_state_ui"] = update_project_state_ui
    except Exception:
        pass

    # Exponer en builtins para que app.py pueda llamarla después del guardado
    try:
        builtins._impo_update_project_state_ui = update_project_state_ui
        print("[IMPO UI] Función update_project_state_ui expuesta en builtins")
    except Exception:
        pass

    update_project_state_ui()

    instruction_text = ft.Text(
        t(
            "Seleccione copias, Rotación, Tipo de impresión y cargue el PDF. El sistema comprobará que el PDF tiene las páginas requeridas por el ordenamiento."
        ),
        size=13,
        color=TEXTOS_FASE_1_COLOR,
        visible=True,
    )

    campos_dimensiones = ft.Row(
        [
            textfield_sangre,
            textfield_medianil,
            # boton_abrir_dialogo_tamano_final(page)  # ELIMINADO: ya no se usa
        ],
        spacing=12,
    )

    # ruta_json_tamanos = "tamanos_pliego.json"
    # ELIMINADO: construcción del dropdown_tamanos_general y listeners
    # (ya no se usa, solo quedan textfield_ancho y textfield_alto)
    # Código comentado para referencia futura si se necesita restaurar:
    # ...
    # dropdown_tamanos_general = None  # Stub para evitar errores

    # Contenedor del Viewer (Oculto inicialmente)
    viewer_container = ft.Container(
        content=viewer_stack,
        expand=True,
        width=VIEWER_WIDTH,
        height=VIEWER_HEIGHT,
        border=ft.Border.all(1, ft.Colors.GREY_400),
        border_radius=8,
        bgcolor=(
            ft.Colors.GREY_100
            if page.theme_mode == ft.ThemeMode.LIGHT
            else ft.Colors.GREY_900
        ),
        visible=True,  # Ahora visible por defecto
        alignment=ft.Alignment.CENTER,
        # patron PageNumber: el viewport recorta; el pan mueve el contenido dentro
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
    )
    # Estado de navegación de pliegos
    state_pliego = {"index": 0, "total": 1}

    # Controles de navegación de pliegos
    def cambiar_pliego(delta):
        print(
            f"[DEBUG NAV] cambiar_pliego delta={delta}, actual={state_pliego['index']}, total={state_pliego['total']}"
        )
        nuevo_index = state_pliego["index"] + delta
        if 0 <= nuevo_index < state_pliego["total"]:
            state_pliego["index"] = nuevo_index

            # ✅ CACHEAR PLIEGO BAJO DEMANDA SI NO ESTÁ CACHEADO
            try:
                # Calcular número de pliego (1-based) desde el índice (0-based)
                numero_pliego = nuevo_index + 1

                if not esta_pliego_cacheado(numero_pliego):
                    print(
                        f"[CACHE ON-DEMAND] Pliego {numero_pliego} no está cacheado, extrayendo imágenes..."
                    )

                    # Usar variables globales del scope (mismas que en cache inicial)
                    ordenamiento = ordenamiento_calculado.get("ordenamiento", {})
                    pdf_original = archivo_seleccionado["ruta"]

                    if ordenamiento and pdf_original:
                        # Obtener páginas del pliego (ej: [6, 31, 56, 81])
                        paginas = obtener_paginas_del_pliego(
                            ordenamiento, numero_pliego
                        )

                        if paginas:
                            # Extraer y cachear imágenes (IGUAL que cache inicial)
                            imagenes = extraer_imagenes_pliego(
                                pdf_original,
                                paginas,
                                numero_pliego,
                                len(paginas),
                                dpi=100,
                            )

                            # Marcar como cacheado
                            marcar_pliego_cacheado(numero_pliego)

                            print(
                                f"[CACHE ON-DEMAND] Pliego {numero_pliego} cacheado exitosamente ({len(imagenes)} imágenes)"
                            )
                        else:
                            print(
                                f"[CACHE ON-DEMAND] No se encontraron páginas para pliego {numero_pliego}"
                            )
                    else:
                        print(f"[CACHE ON-DEMAND] No hay ordenamiento o PDF disponible")
                else:
                    print(f"[CACHE HIT] Pliego {numero_pliego} ya está cacheado")
            except Exception as ex:
                print(f"[CACHE ERROR] Error cacheando pliego: {ex}")

            # Actualizar UI
            actualizar_estado_botones_pliego()
            print(
                f"[DEBUG NAV] Nuevo índice: {state_pliego['index']}. Actualizando trazado (preservando zoom)..."
            )
            try:
                actualizar_trazado(None, skip_auto_zoom=True)
            except Exception:
                pass
            # Actualizar viewer sin centrar
            try:
                actualizar_viewer_zoom(do_center=False, skip_auto_zoom=True)
            except Exception:
                pass
        else:
            print(f"[DEBUG NAV] Índice fuera de rango: {nuevo_index}")
            pass

    def on_pliego_submit(e):
        try:
            val = int(e.control.value)
            print(f"[DEBUG NAV] on_pliego_submit: valor ingresado={val}")

            # Determinar si estamos en modo doble cara usando el ordenamiento
            ordenamiento = ordenamiento_calculado.get("ordenamiento", {})
            es_modo_doble_cara = any(
                _es_dorso_val(v.get("doble_cara"))
                for k, v in ordenamiento.items()
                if isinstance(k, int) and isinstance(v, dict)
            )

            print(f"[DEBUG NAV] es_modo_doble_cara detectado: {es_modo_doble_cara}")

            nuevo_index = -1
            if es_modo_doble_cara:
                # Si el usuario introduce "1", quiere ir al Pliego 1 Cara (índice 0)
                # Si introduce "2", quiere ir al Pliego 2 Cara (índice 2)
                # Fórmula: (Pliego - 1) * 2
                nuevo_index = (val - 1) * 2
            else:
                # Si es una cara, el índice es directo (val - 1)
                nuevo_index = val - 1

            print(f"[DEBUG NAV] Nuevo índice calculado: {nuevo_index}")

            if 0 <= nuevo_index < state_pliego["total"]:
                state_pliego["index"] = nuevo_index

                # ✅ CACHEAR PLIEGO BAJO DEMANDA SI NO ESTÁ CACHEADO
                try:
                    # Calcular número de pliego (1-based) desde el índice (0-based)
                    numero_pliego = nuevo_index + 1

                    if not esta_pliego_cacheado(numero_pliego):
                        print(
                            f"[CACHE ON-DEMAND] Pliego {numero_pliego} no está cacheado, extrayendo imágenes..."
                        )

                        # Usar variables globales del scope (mismas que en cache inicial)
                        ordenamiento = ordenamiento_calculado.get("ordenamiento", {})
                        pdf_original = archivo_seleccionado["ruta"]

                        if ordenamiento and pdf_original:
                            # Obtener páginas del pliego (ej: [6, 31, 56, 81])
                            paginas = obtener_paginas_del_pliego(
                                ordenamiento, numero_pliego
                            )

                            if paginas:
                                # Extraer y cachear imágenes (IGUAL que cache inicial)
                                imagenes = extraer_imagenes_pliego(
                                    pdf_original,
                                    paginas,
                                    numero_pliego,
                                    len(paginas),
                                    dpi=100,
                                )

                                # Marcar como cacheado
                                marcar_pliego_cacheado(numero_pliego)

                                print(
                                    f"[CACHE ON-DEMAND] Pliego {numero_pliego} cacheado exitosamente ({len(imagenes)} imágenes)"
                                )
                            else:
                                print(
                                    f"[CACHE ON-DEMAND] No se encontraron páginas para pliego {numero_pliego}"
                                )
                        else:
                            print(
                                f"[CACHE ON-DEMAND] No hay ordenamiento o PDF disponible"
                            )
                    else:
                        print(f"[CACHE HIT] Pliego {numero_pliego} ya está cacheado")
                except Exception as ex:
                    print(f"[CACHE ERROR] Error cacheando pliego: {ex}")

                actualizar_estado_botones_pliego()
                try:
                    actualizar_trazado(None, skip_auto_zoom=True)
                except Exception:
                    pass
                # Evitar auto-centrado del viewer al navegar por índice ingresado
                try:
                    actualizar_viewer_zoom(do_center=False, skip_auto_zoom=True)
                except Exception:
                    pass
            else:
                print(f"[DEBUG NAV] Valor fuera de rango. Restaurando.")
                actualizar_estado_botones_pliego()
        except ValueError:
            print(f"[DEBUG NAV] Error de valor (no numérico). Restaurando.")
            actualizar_estado_botones_pliego()

    def actualizar_estado_botones_pliego():
        # print(f"[DEBUG NAV] actualizar_estado_botones_pliego. Index: {state_pliego['index']}, Total: {state_pliego['total']}")
        boton_pliego_anterior.disabled = state_pliego["index"] <= 0
        boton_pliego_siguiente.disabled = (
            state_pliego["index"] >= state_pliego["total"] - 1
        )
        boton_pliego_anterior.update()
        boton_pliego_siguiente.update()

        # Actualizar contador de pliegos con Cara/Dorso y número de pliego
        try:
            # Obtener información directamente del ordenamiento (fuente de verdad)
            ordenamiento = ordenamiento_calculado.get("ordenamiento", {})

            # Validar que ordenamiento no sea None antes de continuar
            if not ordenamiento or not isinstance(ordenamiento, dict):
                # Si no hay ordenamiento válido, salir silenciosamente
                return

            current_index = state_pliego["index"]

            # El índice del pliego es 0-based, pero las claves del ordenamiento son 1-based
            pliego_key = current_index + 1

            # Obtener datos del pliego actual
            pliego_data = ordenamiento.get(pliego_key, {})
            tipo_cara_dorso = pliego_data.get("doble_cara", "cara")  # 'cara' o 'dorso'

            # print(f"[DEBUG NAV UPDATE] pliego_key: {pliego_key}, tipo_cara_dorso: {tipo_cara_dorso}")

            # Determinar si estamos en modo doble cara (hay pliegos con 'dorso')
            es_modo_doble_cara = any(
                _es_dorso_val(v.get("doble_cara"))
                for k, v in ordenamiento.items()
                if isinstance(k, int) and isinstance(v, dict)
            )

            # print(f"[DEBUG NAV UPDATE] es_modo_doble_cara: {es_modo_doble_cara}")

            # Calcular número de pliego visual
            numero_pliego_visual = 1
            if es_modo_doble_cara:
                # Índice 0 -> Pliego 1, Índice 1 -> Pliego 1
                # Índice 2 -> Pliego 2, Índice 3 -> Pliego 2
                numero_pliego_visual = (current_index // 2) + 1
            else:
                numero_pliego_visual = current_index + 1

            # print(f"[DEBUG NAV UPDATE] numero_pliego_visual: {numero_pliego_visual}")

            # Actualizar TextField con el número de pliego visual
            textfield_pliego_actual.value = str(numero_pliego_visual)
            textfield_pliego_actual.update()

            # Actualizar texto Cara/Dorso según el dato del ordenamiento
            if tipo_cara_dorso == "dorso":
                texto_contador_pliegos.value = " " + t("Pliego Dorso")
                texto_contador_pliegos.color = TEXTO_COLOR_GENERICO
                texto_contador_pliegos.weight = ft.FontWeight.BOLD
            else:
                texto_contador_pliegos.value = " " + t("Pliego Cara")
                texto_contador_pliegos.color = TEXTO_COLOR_GENERICO
                texto_contador_pliegos.weight = ft.FontWeight.BOLD

            texto_contador_pliegos.visible = True
            texto_contador_pliegos.update()

            # ===== Actualizar la capa de marca de texto dinámica para que coincida con el PDF =====
            try:
                # Calcular número de página de salida (1-based) y número de pliego visual
                pagina_salida = current_index + 1
                if es_modo_doble_cara:
                    numero_pliego_visual = (current_index // 2) + 1
                else:
                    numero_pliego_visual = current_index + 1

                # Tipo legible traducido
                tipo_str = t("DORSO") if tipo_cara_dorso == "dorso" else t("CARA")

                # Construir contenido de la marca de texto igual que en el generador PDF
                # Añadir el nombre de archivo si está disponible (archivo_seleccionado['nombre'])
                # Intentar obtener el nombre del archivo desde el scope exterior.
                archivo_nombre = None
                try:
                    # Si existe la variable en el scope exterior (closure), acceder directamente
                    archivo_nombre = (
                        archivo_seleccionado.get("nombre")
                        if archivo_seleccionado
                        else None
                    )
                except NameError:
                    # Fallback: intentar globals (por si fue definido globalmente)
                    archivo_sel = globals().get("archivo_seleccionado") or {}
                    archivo_nombre = (
                        archivo_sel.get("nombre")
                        if isinstance(archivo_sel, dict)
                        else None
                    )
                except Exception:
                    archivo_nombre = None

                # Último recurso: si existe un control texto que muestra el nombre, leer su valor
                if not archivo_nombre:
                    try:
                        ta = locals().get("texto_archivo") or globals().get(
                            "texto_archivo"
                        )
                        if ta and getattr(ta, "value", None):
                            archivo_nombre = str(ta.value)
                    except Exception:
                        pass
                # Preferir mostrar el nombre del archivo (sin prefijos) cuando esté disponible
                lbl_pliego = t("Pliego:")
                lbl_pagina = t("Página:")
                if archivo_nombre:
                    contenido_dynamic = f"{archivo_nombre} - {lbl_pliego} {numero_pliego_visual} - {tipo_str} - {lbl_pagina} {pagina_salida}"
                else:
                    # Si no hay nombre de archivo, usar la cadena global de marca (configurable)
                    contenido_dynamic = f"{MARCA_TEXTO_CONTENIDO} - {lbl_pliego} {numero_pliego_visual} - {tipo_str} - {lbl_pagina} {pagina_salida}"

                # Imprimir el nombre de archivo usado (si existe) para facilitar debug
                # try:
                #     # print(f"[DEBUG UI MARCA] archivo_nombre={archivo_nombre}", flush=True)
                # except Exception:
                #     pass

                # try:
                #     # print(f"[DEBUG UI MARCA] pliego={numero_pliego_visual} tipo={tipo_str} pagina_salida={pagina_salida} -> '{contenido_dynamic}'", flush=True)

                # Cargar utilidades de unidades si están disponibles
                try:
                    from utils.unit_utils import (
                        convert_to_mm,
                        convert_from_mm,
                        get_unit_label,
                    )
                except Exception:
                    # Fallbacks minimalistas si el módulo no está disponible
                    def convert_to_mm(value, from_unit):
                        try:
                            return float(value)
                        except Exception:
                            return 0.0

                    def convert_from_mm(value_mm, to_unit):
                        try:
                            return float(value_mm)
                        except Exception:
                            return 0.0

                    def get_unit_label(unit_code, t_func=None):
                        return unit_code or "mm"

                try:
                    from talnum_preferences import get_preference

                    _initial_unit_pref = get_preference("unit", "mm") or "mm"
                except Exception:
                    _initial_unit_pref = "mm"
                # except Exception:
                #     pass

                # Crear nueva capa de marca de texto (Stack) usando la función del stack
                # Usar una referencia segura a `datos_celdas` (puede no estar en el scope local)
                try:
                    dc = (
                        locals().get("datos_celdas")
                        or globals().get("datos_celdas")
                        or {}
                    )
                    papel_w_mm = TAMANO_FINAL_PLIEGO.get("w_mm") or dc.get(
                        "tamano_total_w"
                    )
                    papel_h_mm = TAMANO_FINAL_PLIEGO.get("h_mm") or dc.get(
                        "tamano_total_h"
                    )
                except Exception:
                    dc = {}
                    papel_w_mm = None
                    papel_h_mm = None

                nueva_capa_marca = None
                try:
                    nueva_capa_marca = crear_capa_marca_texto(
                        dim_celds=dc or {},
                        contenido=contenido_dynamic,
                        pos_sup_izq=MARCA_TEXTO_POS_SUP_IZQ,
                        pos_sup_der=MARCA_TEXTO_POS_SUP_DER,
                        pos_inf_izq=MARCA_TEXTO_POS_INF_IZQ,
                        pos_inf_der=MARCA_TEXTO_POS_INF_DER,
                        pos_centro_sup=MARCA_TEXTO_POS_CENTRO_SUP,
                        pos_centro_inf=MARCA_TEXTO_POS_CENTRO_INF,
                        pos_centro_lat_izq=MARCA_TEXTO_POS_CENTRO_LAT_IZQ,
                        pos_centro_lat_der=MARCA_TEXTO_POS_CENTRO_LAT_DER,
                        familia=MARCA_TEXTO_FAMILIA,
                        tipo=MARCA_TEXTO_TIPO,
                        cuerpo=MARCA_TEXTO_CUERPO,
                        color=MARCA_TEXTO_COLOR,
                        offset_h_mm=MARCA_TEXTO_OFFSET_H_MM,
                        offset_v_mm=MARCA_TEXTO_OFFSET_V_MM,
                        tamano_corte_w_mm=(papel_w_mm or 0) * ESCALA_VISUAL,
                        tamano_corte_h_mm=(papel_h_mm or 0) * ESCALA_VISUAL,
                        escala_visual=ESCALA_VISUAL,
                        rotacion_grados=MARCA_TEXTO_ROTACION,
                    )
                except Exception as _ex_crear:
                    print(
                        f"[WARN] No se pudo crear nueva marca de texto dinámica: {_ex_crear}"
                    )
                    nueva_capa_marca = None

                # Mostrar/ocultar según checkbox
                marca_vis = (
                    bool(checkbox_marcas_texto.value)
                    if "checkbox_marcas_texto" in globals()
                    else True
                )

                if nueva_capa_marca is not None:
                    try:
                        actualizar_capa_marca_texto(
                            stack_principal,
                            capa_marca_texto=nueva_capa_marca,
                            visible=marca_vis,
                            papel_w_mm=papel_w_mm,
                            papel_h_mm=papel_h_mm,
                            escala=ESCALA_VISUAL,
                        )
                    except Exception as _ex_upd:
                        print(f"[WARN] actualizar_capa_marca_texto falló: {_ex_upd}")
            except Exception as ex_dyn:
                print(f"[WARN] No se pudo actualizar marca de texto dinámica: {ex_dyn}")
        except Exception as ex:
            print(f"[ERROR] Error actualizando contador pliegos: {ex}")

    boton_pliego_anterior = ft.IconButton(
        icon=ft.Icons.CHEVRON_LEFT,
        tooltip=t("Pliego anterior"),
        on_click=lambda e: cambiar_pliego(-1),
        icon_color=TEXTOS_FASE_1_COLOR,
        disabled=True,
    )

    boton_pliego_siguiente = ft.IconButton(
        icon=ft.Icons.CHEVRON_RIGHT,
        tooltip=t("Pliego siguiente"),
        on_click=lambda e: cambiar_pliego(1),
        icon_color=TEXTOS_FASE_1_COLOR,
        disabled=True,
    )

    textfield_pliego_actual = ft.TextField(
        value="1",
        width=100,
        height=35,
        text_align=ft.TextAlign.CENTER,
        on_submit=on_pliego_submit,
        content_padding=ft.Padding(0, 0, 0, 0),
        text_size=16,
        bgcolor=FONDO_TEXTFIELDS_COLOR,
        color=TEXTOS_FASE_1_COLOR,
        border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)),
        text_vertical_align=ft.VerticalAlignment.CENTER,
    )

    # Contenedor de navegación
    navegacion_pliegos_container = ft.Row(
        [
            boton_pliego_anterior,
            textfield_pliego_actual,
            boton_pliego_siguiente,
            ft.Container(
                content=texto_contador_pliegos, width=120, alignment=ft.Alignment.CENTER
            ),
        ],
        alignment=ft.MainAxisAlignment.CENTER,
        spacing=5,
        visible=True,  # Se hace visible cuando hay PDF ordenado
    )

    # ------------------ Botón y diálogo 'Generar PDF' ------------------
    def abrir_dialogo_generar_pdf(e):
        try:
            # Debug: confirmar que el handler se ha invocado
            try:
                val_dropdown_db = (
                    dropdown_doble_cara.value if dropdown_doble_cara else "N/A"
                )
                print(
                    f"[DEBUG GENERAR_PDF] abrir_dialogo_generar_pdf invoked. Dropdown Doble Cara: {val_dropdown_db}"
                )
            except Exception:
                pass

            # --- Si estamos en DORSO, simular pulsación flecha izquierda para pasar a CARA ---
            try:
                try:
                    es_actual_dorso = determinar_si_es_dorso()
                except Exception:
                    es_actual_dorso = False

                if es_actual_dorso:
                    print(
                        "[INFO GENERAR_PDF] Pliego actual marcado como DORSO; navegando a CARA (cambiar_pliego(-1))."
                    )
                    try:
                        # Utilizar la misma función que usa el botón de la UI
                        cambiar_pliego(-1)
                    except Exception as _ex_nav:
                        print(
                            f"[WARN GENERAR_PDF] Error llamando a cambiar_pliego(-1): {_ex_nav}"
                        )
                else:
                    # No es dorso: no hacemos nada especial (se mantiene la vista actual)
                    pass
            except Exception:
                pass
            # --- /Comprobación CARA/DORSO ---
            # Valores iniciales
            default_path = os.path.join(os.path.expanduser("~"), "Desktop")

            # Dropdown de copias 1..20 (más estrecho)
            opciones_copias = [ft.dropdown.Option(str(i)) for i in range(1, 21)]

            # Usar pref global
            val_copias = globals().get("_PREF_COPIAS", "1")

            dropdown_copias_local = ft.Dropdown(
                options=opciones_copias,
                value=val_copias,
                width=90,
                text_size=16,
                content_padding=ft.Padding(8, 0, 0, 0),
                border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR), border_radius=6),
                filled=True,
                fill_color=FONDO_TEXTFIELDS_COLOR,
                color=DROPDOWN_TEXT_STYLE_COLOR,
                bgcolor=DROPDOWN_FONDO_MENU_COLOR,
                label_style=ft.TextStyle(color=DROPDOWN_TEXT_STYLE_COLOR),
                trailing_icon=ft.Icon(
                    ft.Icons.ARROW_DROP_DOWN, color=DROPDOWN_TRAILING_ICON_COLOR
                ),
                selected_trailing_icon=ft.Icon(
                    ft.Icons.ARROW_DROP_UP, color=DROPDOWN_TRAILING_ICON_COLOR
                ),
            )

            # Checkbox Xerox Fiery(desactivado por defecto)
            val_xerox = globals().get("_PREF_XEROX", False)
            # Solo visible si copias > 1
            visible_xerox = int(val_copias) > 1

            checkbox_xerox_local = ft.Checkbox(
                label=t("Crear archivo Fiery  - Xerox"),
                value=val_xerox,
                active_color=BORDE_TEXTFIELDS_COLOR,
                check_color=TEXTOS_FASE_1_COLOR,
                label_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
                fill_color=BOTONES_GENERICOS_FONDO_COLOR,
                visible=visible_xerox,
            )

            # Texto de estado para la ruta seleccionada (el FilePicker gestiona la selección)
            texto_ruta_seleccionada = ft.Text(
                t("Ningún archivo seleccionado. Usar 'Seleccionar archivo de salida'"),
                size=13,
                color=TEXTOS_FASE_1_COLOR,
                selectable=False,
            )

            # Nota: campo de nombre personalizado eliminado.
            # El filepicker se usará para seleccionar archivo de salida (ruta + nombre).

            # ── SELECTOR DE OPTIMIZACIÓN PDF ──────────────────────────────────────
            _OPT_LEVELS_IMPO = [
                dict(garbage=0, deflate=False, clean=False, use_objstms=0),
                dict(garbage=2, deflate=True, clean=False, use_objstms=1),
                dict(garbage=4, deflate=True, clean=False, use_objstms=1),
            ]
            _opt_labels_impo = [
                t("PDF sin optimizar"),
                t("PDF con fuentes optimizadas"),
                t("PDF con fuentes e imágenes optimizadas"),
            ]
            _opt_descs_impo = [
                t("Más rápido, tamaño de archivo grande"),
                t("Más lento, tamaño de archivo intermedio"),
                t("Bastante lento, tamaño de archivo mínimo"),
            ]
            _opt_level_impo = {"value": globals().get("_LAST_OPT_LEVEL_IMPO", 0)}

            _opt_desc_text_impo = ft.Text(
                _opt_descs_impo[_opt_level_impo["value"]],
                size=12,
                color=TEXTOS_FASE_1_COLOR,
                italic=False,
                width=360,
                max_lines=2,
            )
            _opt_desc_container_impo = ft.Container(
                content=_opt_desc_text_impo, height=34
            )

            def _on_opt_change_impo(e):
                try:
                    new_level = int(e.control.value)
                except (ValueError, TypeError):
                    return
                _opt_level_impo["value"] = new_level
                globals()["_LAST_OPT_LEVEL_IMPO"] = new_level
                _opt_desc_text_impo.value = _opt_descs_impo[new_level]
                page.update()

            _opt_radio_group_impo = ft.RadioGroup(
                value=str(_opt_level_impo["value"]),
                on_change=_on_opt_change_impo,
                content=ft.Column(
                    [
                        ft.Radio(
                            value="0",
                            label=_opt_labels_impo[0],
                            label_style=ft.TextStyle(
                                color=TEXTOS_FASE_1_COLOR, size=13
                            ),
                            fill_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                        ),
                        ft.Radio(
                            value="1",
                            label=_opt_labels_impo[1],
                            label_style=ft.TextStyle(
                                color=TEXTOS_FASE_1_COLOR, size=13
                            ),
                            fill_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                        ),
                        ft.Radio(
                            value="2",
                            label=_opt_labels_impo[2],
                            label_style=ft.TextStyle(
                                color=TEXTOS_FASE_1_COLOR, size=13
                            ),
                            fill_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                        ),
                    ],
                    spacing=2,
                    tight=True,
                ),
            )
            # ─────────────────────────────────────────────────────────────────────

            # FilePicker (opcional) - si existe global file_picker intentar usarlo
            local_file_picker = None

            def _on_filepicker_result(ev):
                try:
                    # Para get_directory_path() / save_file, el resultado está en ev.path
                    ruta = getattr(ev, "path", None)
                    # Si el usuario seleccionó una ruta/archivo -> iniciar generación
                    if ruta:
                        try:
                            texto_ruta_seleccionada.value = ruta
                            texto_ruta_seleccionada.update()
                        except Exception:
                            pass
                        # Quitar el filepicker del overlay si está presente
                        try:
                            if local_file_picker in page.overlay:
                                page.overlay.remove(local_file_picker)
                        except Exception:
                            pass
                        # Emular comportamiento del botón "Aceptar" pasando la ruta seleccionada
                        try:
                            aceptar_generar(ruta)
                        except Exception:
                            pass
                    else:
                        # Cancelado: asegurarse de que el diálogo principal siga visible
                        try:
                            # `dialog` existe en el scope exterior cuando se abre el diálogo
                            if "dialog" in locals() or "dialog" in globals():
                                try:
                                    page.show_dialog(dialog)
                                except Exception:
                                    pass
                            page.update()
                        except Exception:
                            pass
                except Exception:
                    pass

            try:
                if "file_picker" in globals() and globals().get("file_picker"):
                    local_file_picker = globals().get("file_picker")
                    try:
                        # si no tiene on_result, intentar reasignarlo
                        local_file_picker.on_result = _on_filepicker_result
                    except Exception:
                        pass
                else:
                    # Crear uno temporal para seleccionar archivos/carpetas
                    try:
                        local_file_picker = ft.FilePicker(
                            on_result=_on_filepicker_result
                        )
                    except Exception:
                        # Fallback: intentar crear sin on_result (versiones antiguas)
                        try:
                            local_file_picker = ft.FilePicker()
                            local_file_picker.on_result = _on_filepicker_result
                        except Exception:
                            local_file_picker = None
            except Exception:
                local_file_picker = None

            def on_change_copias(ev):
                try:
                    v = int(ev.control.value)
                    checkbox_xerox_local.visible = v > 1
                    checkbox_xerox_local.update()
                    # Marcar como modificado
                    mark_modified()
                    # Actualizar el container informativo si existe
                    try:
                        # pliegos
                        try:
                            pliegos_val = (
                                int(state_pliego.get("total"))
                                if isinstance(state_pliego, dict)
                                and state_pliego.get("total") is not None
                                else int(getattr(state_pliego, "total", 0) or 0)
                            )
                        except Exception:
                            pliegos_val = 0
                        # Determinar si es doble cara consultando el ordenamiento calculado
                        try:
                            orden = (
                                ordenamiento_calculado.get("ordenamiento", {})
                                if isinstance(ordenamiento_calculado, dict)
                                else {}
                            )
                            # Las claves del ordenamiento pueden ser str o int según el origen; iterar sobre los valores es más robusto
                            es_doble = False
                            if orden:
                                for v2 in orden.values():
                                    if isinstance(v2, dict) and _es_dorso_val(
                                        v2.get("doble_cara")
                                    ):
                                        es_doble = True
                                        break

                            # Fallback: Revisar dropdown global si el ordenamiento no tiene suficientes datos
                            if not es_doble and dropdown_doble_cara:
                                val_dropdown = str(dropdown_doble_cara.value).lower()
                                if (
                                    val_dropdown.startswith("d")
                                    or "dorso" in val_dropdown
                                ):
                                    es_doble = True
                        except Exception:
                            es_doble = False
                        caras_val = 2 if es_doble else 1
                        paginas_calc = pliegos_val * caras_val * v
                        # actualizar controles informativos si están definidos
                        try:
                            info_copias_generar.value = t(
                                "Copias a generar: {0}"
                            ).format(v)
                            info_copias_generar.update()
                        except Exception:
                            pass
                        try:
                            info_total_paginas.value = t(
                                "Total páginas a generar en el PDF: {0}"
                            ).format(paginas_calc)
                            info_total_paginas.update()
                        except Exception:
                            pass
                        try:
                            tipo_text = (
                                t("Doble cara") if caras_val == 2 else t("Una Cara")
                            )
                            info_tipo.value = t("Tipo: {0}").format(tipo_text)
                            info_tipo.update()
                        except Exception:
                            pass
                    except Exception:
                        pass
                except Exception:
                    pass

            dropdown_copias_local.on_select = on_change_copias

            async def seleccionar_path(e_sel):
                # Flet 1.0: Service + await save_file; shim → _on_filepicker_result
                try:
                    if local_file_picker:
                        sugerido = None
                        try:
                            import fritz_pdf_generator as fpg

                            sugerido = fpg.sugerir_nombre_salida(
                                pdf_ordenado_path=globals().get(
                                    "_pdf_ordenado_actual"
                                ),
                                archivo_seleccionado=globals().get(
                                    "_archivo_seleccionado"
                                ),
                                pref_nombre_personalizado=globals().get(
                                    "_PREF_NOMBRE_PERSONALIZADO", False
                                ),
                                pref_filename=globals().get("_PREF_FILENAME", None),
                            )
                        except Exception:
                            sugerido = globals().get(
                                "_PREF_FILENAME", "imposicion_output.pdf"
                            )

                        if not str(sugerido).lower().endswith(".pdf"):
                            sugerido = str(sugerido) + ".pdf"

                        try:
                            path = await local_file_picker.save_file(
                                dialog_title=t("Seleccionar archivo PDF de salida"),
                                file_type=ft.FilePickerFileType.CUSTOM,
                                allowed_extensions=["pdf"],
                                file_name=sugerido,
                            )
                        except Exception as ex:
                            print(f"[SAVE OUT] Error save_file: {ex}")
                            path = None
                        _on_filepicker_result(
                            SimpleNamespace(path=path, files=[])
                        )
                except Exception:
                    pass

            # Flag de cancelación compartido entre funciones
            cancelado = {"valor": False}

            def _cerrar_dialogo_principal(dlg):
                """Cierra un diálogo abierto con page.open/page.close (sin tocar overlay manual)."""
                try:
                    page.pop_dialog()
                except Exception:
                    pass
                try:
                    dlg.open = False
                except Exception:
                    pass
                try:
                    page.update()
                except Exception:
                    pass

            def aceptar_generar(e_accept_or_path):
                # Resetear flag de cancelación
                cancelado["valor"] = False

                try:
                    copies = int(dropdown_copias_local.value)
                except Exception:
                    copies = 1
                crear_xerox = bool(checkbox_xerox_local.value)
                # 'tipo' eliminado
                # Si se invoca con una ruta (string) usarla, si no, intentar leer texto de estado
                salida = None
                try:
                    if isinstance(e_accept_or_path, str):
                        salida = e_accept_or_path
                except Exception:
                    salida = None
                if not salida:
                    try:
                        # texto_ruta_seleccionada puede contener la ruta si ya fue seleccionada
                        val = getattr(texto_ruta_seleccionada, "value", None)
                        if val and isinstance(val, str) and val.strip():
                            salida = val
                    except Exception:
                        salida = None
                if not salida:
                    salida = default_path
                if not salida.lower().endswith(".pdf"):
                    salida = salida + ".pdf"

                # Opciones de guardado: fijo nivel 1 (como PageNumber, que
                # exporta siempre con fuentes subseteadas + deflate).
                save_opts_final = _OPT_LEVELS_IMPO[1]

                # Cerrar el diálogo de configuración inmediatamente
                _cerrar_dialogo_principal(dialog)

                # ── CREAR DIÁLOGO DE PROGRESO ─────────────────────────────────────
                _prog_bar = ft.ProgressBar(
                    value=0,
                    width=400,
                    bgcolor=FONDO_TEXTFIELDS_COLOR,
                    color=BOTONES_GENERICOS_OVERLAY_COLOR,
                )
                _prog_text = ft.Text(
                    t("Pliegos generados: {0}/{1}").format(0, "?"),
                    size=14,
                    color=TEXTO_COLOR_GENERICO,
                    text_align=ft.TextAlign.CENTER,
                    width=420,
                )

                def _on_cancel_progress(e):
                    cancelado["valor"] = True
                    print("[DEBUG] Cancelación solicitada desde diálogo de progreso")
                    _cerrar_dialogo_principal(progress_dialog)

                _cancel_btn_progress = ft.Button(
                    t("Cancelar"),
                    on_click=_on_cancel_progress,
                    width=110,
                    bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                    style=ft.ButtonStyle(
                        color={
                            ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                            "hovered": BOTONES_GENERICOS_HOVER_COLOR,
                        },
                        overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                        padding=ft.Padding(0, 0, 0, 0),
                        shape=ft.RoundedRectangleBorder(radius=10),
                    ),
                )

                progress_dialog = ft.AlertDialog(
                    modal=True,
                    title=ft.Container(
                        content=ft.Text(
                            t("Generando PDF"),
                            size=18,
                            weight=ft.FontWeight.BOLD,
                            color=TEXTO_COLOR_GENERICO,
                            text_align=ft.TextAlign.CENTER,
                        ),
                        alignment=ft.Alignment.CENTER,
                    ),
                    content=ft.Container(
                        content=ft.Column(
                            [
                                _prog_text,
                                ft.Container(height=12),
                                _prog_bar,
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        width=440,
                        height=110,
                        padding=ft.Padding.only(left=20, right=20, top=18, bottom=18),
                    ),
                    actions=[_cancel_btn_progress],
                    actions_alignment=ft.MainAxisAlignment.CENTER,
                    bgcolor=FONDO_ALERT_DIALOG,
                )
                page.show_dialog(progress_dialog)
                # ─────────────────────────────────────────────────────────────────

                # Lanzar trabajo en hilo para no bloquear UI
                async def worker():
                    try:
                        from fritz_pdf_generator import generar_pdf_imposicion
                        from fritz_json_export import obtener_impo_export_data

                        global _pdf_ordenado_actual

                        print(f"[DEBUG WORKER] Iniciando worker")

                        # Obtener PDF ordenado desde variable global
                        pdf_ordenado = _pdf_ordenado_actual

                        # -----------------------------------------------------
                        # Save preferences to globals
                        # -----------------------------------------------------
                        global _PREF_COPIAS, _PREF_XEROX, _PREF_NOMBRE_PERSONALIZADO, _PREF_FILENAME
                        _PREF_COPIAS = str(copies)
                        _PREF_XEROX = bool(crear_xerox)
                        # Guardar nombre de salida sin modificar la preferencia de nombre personalizado
                        try:
                            _PREF_FILENAME = os.path.basename(salida)
                        except Exception:
                            pass

                        # Trigger save state to persist these new values
                        try:
                            guardar_estado_impo_ui()
                        except:
                            pass
                        # -----------------------------------------------------

                        print(
                            f"[DEBUG WORKER] PDF ordenado desde variable global: {pdf_ordenado}"
                        )

                        if not pdf_ordenado:
                            raise Exception(
                                "No se encontró el PDF ordenado temporal. Debes generar primero el PDF ordenado usando el botón 'Crear PDF Ordenado' en la pestaña anterior."
                            )

                        if not os.path.exists(pdf_ordenado):
                            raise Exception(
                                f"El PDF ordenado temporal no existe en la ruta: {pdf_ordenado}"
                            )

                        print(f"[DEBUG WORKER] Usando PDF ordenado: {pdf_ordenado}")

                        # Obtener ordenamiento
                        orden = ordenamiento_calculado.get("ordenamiento")
                        print(
                            f"[DEBUG WORKER] Ordenamiento keys: {list(orden.keys()) if orden else None}"
                        )
                        if not orden:
                            raise Exception(
                                "No hay ordenamiento calculado. Debes generar primero el PDF ordenado."
                            )

                        # Obtener JSONs de trazado
                        json_cara = obtener_impo_export_data(tipo_cara="CARA")
                        json_dorso = obtener_impo_export_data(tipo_cara="DORSO")

                        print(
                            f"[DEBUG WORKER] JSON cara: {bool(json_cara)}, JSON dorso: {bool(json_dorso)}"
                        )

                        if not json_cara:
                            raise Exception("No se pudo obtener JSON de trazado CARA")

                        # Callback de progreso - corre en el hilo de to_thread →
                        # Flet 1.0: marshal de UI al loop
                        def actualizar_progreso(pliego_actual, pliego_total):
                            if cancelado["valor"]:
                                raise InterruptedError(
                                    "Generación cancelada por el usuario"
                                )
                            page.run_task(pintar_progreso, pliego_actual, pliego_total)

                        async def pintar_progreso(pliego_actual, pliego_total):
                            try:
                                if (
                                    isinstance(pliego_total, (int, float))
                                    and pliego_total > 0
                                    and pliego_actual >= pliego_total
                                ):
                                    _prog_text.value = t("Creando PDF final...")
                                    _prog_bar.value = None  # indeterminado
                                else:
                                    _prog_text.value = t(
                                        "Pliegos generados: {0}/{1}"
                                    ).format(pliego_actual, pliego_total)
                                    _prog_bar.value = (
                                        pliego_actual / pliego_total if pliego_total else 0
                                    )
                                page.update()
                            except Exception as e:
                                print(f"[ERROR] Actualizando progreso: {e}")

                        # Aplicar filtro de rango seleccionado (si corresponde)
                        try:
                            pliegos_ordenados = sorted(
                                [k for k in orden.keys() if isinstance(k, int)]
                            )
                            total_pliegos_available = len(pliegos_ordenados)
                            try:
                                sel_from = int(selector_rango_from.value)
                            except Exception:
                                sel_from = 1
                            try:
                                sel_to = int(selector_rango_to.value)
                            except Exception:
                                sel_to = total_pliegos_available

                            # Clamp
                            sel_from = max(1, min(sel_from, total_pliegos_available))
                            sel_to = max(1, min(sel_to, total_pliegos_available))
                            if sel_from > sel_to:
                                sel_from, sel_to = sel_to, sel_from

                            # Si el ordenamiento es doble cara, interpretar los valores de
                            # selector como números de pliego físico (1-based) y mapear
                            # cada pliego a sus dos páginas (cara+dorso) contiguas.
                            is_double_overall = any(
                                _es_dorso_val(v.get("doble_cara"))
                                for k, v in orden.items()
                                if isinstance(k, int) and isinstance(v, dict)
                            )

                            selected_keys = []
                            if is_double_overall:
                                # Mapear pliegos físicos a claves consecutivas (1-> [1,2], 2-> [3,4], ...)
                                for p in range(sel_from, sel_to + 1):
                                    k1 = (p - 1) * 2 + 1
                                    k2 = k1 + 1
                                    if k1 in orden:
                                        selected_keys.append(k1)
                                    if k2 in orden:
                                        selected_keys.append(k2)
                            else:
                                start_idx = sel_from - 1
                                end_idx = sel_to  # slice is exclusive
                                selected_keys = pliegos_ordenados[start_idx:end_idx]

                            if selected_keys:
                                orden_filtrado = {k: orden[k] for k in selected_keys}
                            else:
                                orden_filtrado = orden
                        except Exception:
                            orden_filtrado = orden

                        print(
                            f"[DEBUG WORKER] Llamando a generar_pdf_imposicion... (rango {sel_from}-{sel_to})"
                        )
                        # Generar PDF de imposición usando el ordenamiento filtrado
                        await asyncio.to_thread(
                            generar_pdf_imposicion,
                            pdf_ordenado_path=pdf_ordenado,
                            ordenamiento=orden_filtrado,
                            json_cara=json_cara,
                            json_dorso=json_dorso,
                            num_copias=copies,
                            crear_xerox=crear_xerox,
                            ruta_salida=salida,
                            progress_callback=actualizar_progreso,
                            save_opts_final=save_opts_final,
                            cancel_checker=lambda: bool(cancelado["valor"]),
                        )

                        if cancelado["valor"]:
                            raise InterruptedError(
                                "Generación cancelada por el usuario"
                            )

                        print(f"[DEBUG WORKER] PDF generado exitosamente")

                        # Detectar si es doble cara (manejar bool y string)
                        def es_dorso(valor):
                            if isinstance(valor, bool):
                                return valor  # True = dorso, False = cara
                            elif isinstance(valor, str):
                                return valor.lower() == "dorso"
                            return False

                        hay_doble_cara = any(
                            es_dorso(orden[k].get("doble_cara", "cara"))
                            for k in orden.keys()
                        )

                        # ✅ USAR DIRECTAMENTE display_total del contador de la barra superior
                        # Este valor ya está calculado correctamente en actualizar_total_pliegos()
                        try:
                            # Calcular número de entradas efectivamente generadas en el orden_filtrado
                            try:
                                paginas_generadas = len(
                                    [
                                        k
                                        for k in orden_filtrado.keys()
                                        if isinstance(k, int)
                                    ]
                                )
                            except Exception:
                                paginas_generadas = 0

                            if hay_doble_cara:
                                # Cada pliego doble cara corresponde a 2 entradas (cara+dorso)
                                pliegos_generados = (
                                    paginas_generadas // 2 if paginas_generadas else 0
                                )
                                mensaje_pliegos = t(
                                    "Se generaron {0} pliegos a doble cara"
                                ).format(pliegos_generados)
                                try:
                                    rango_text = t("Rango solicitado: {0}-{1}").format(
                                        sel_from, sel_to
                                    )
                                except Exception:
                                    rango_text = ""
                            else:
                                mensaje_pliegos = t(
                                    "Se generaron {0} páginas a una cara"
                                ).format(paginas_generadas)
                                try:
                                    rango_text = t("Rango solicitado: {0}-{1}").format(
                                        sel_from, sel_to
                                    )
                                except Exception:
                                    rango_text = ""

                            print(
                                f"[DEBUG DIALOGO] paginas_generadas={paginas_generadas}, doble_cara={hay_doble_cara}, rango={rango_text}"
                            )
                        except Exception as ex:
                            print(f"[ERROR] Obteniendo pliegos calculados: {ex}")
                            mensaje_pliegos = t("Error calculando pliegos")
                            rango_text = ""

                        # Cerrar diálogo de progreso
                        _cerrar_dialogo_principal(progress_dialog)

                        # Mostrar diálogo de éxito
                        def mostrar_dialogo_exito():
                            # Construir lista de elementos del content
                            content_items = [
                                ft.Container(height=6),
                                ft.Text(
                                    mensaje_pliegos,
                                    size=18,
                                    color=TEXTOS_FASE_1_COLOR,
                                    weight=ft.FontWeight.BOLD,
                                    text_align=ft.TextAlign.CENTER,
                                ),
                                ft.Container(height=6),
                                ft.Text(
                                    rango_text,
                                    size=16,
                                    color=TEXTOS_FASE_1_COLOR,
                                    weight=ft.FontWeight.BOLD,
                                    text_align=ft.TextAlign.CENTER,
                                ),
                                ft.Container(height=8),
                                ft.Text(
                                    t("Copias: {0}").format(copies),
                                    size=16,
                                    color=TEXTOS_FASE_1_COLOR,
                                    text_align=ft.TextAlign.CENTER,
                                ),
                            ]

                            # Si se creó archivo Xerox, añadir información
                            if crear_xerox:
                                content_items.extend(
                                    [
                                        ft.Container(height=12),
                                        ft.Text(
                                            t("✓ Archivo Fiery - Xerox generado"),
                                            size=15,
                                            color=TEXTOS_FASE_1_COLOR,
                                            weight=ft.FontWeight.W_500,
                                            text_align=ft.TextAlign.CENTER,
                                        ),
                                    ]
                                )

                            content_items.extend(
                                [
                                    ft.Container(height=16),
                                    ft.Text(
                                        t("PDF generado en:"),
                                        size=16,
                                        color=TEXTOS_FASE_1_COLOR,
                                        text_align=ft.TextAlign.CENTER,
                                    ),
                                    ft.Container(height=8),
                                    ft.Container(
                                        content=ft.Text(
                                            salida,
                                            size=14,
                                            color=TEXTO_COLOR_GENERICO,
                                            selectable=True,
                                            text_align=ft.TextAlign.CENTER,
                                        ),
                                        bgcolor=FONDO_TEXTFIELDS_COLOR,
                                        padding=ft.Padding(8, 8, 8, 8),
                                        border_radius=6,
                                        border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
                                    ),
                                    ft.Container(height=6),
                                ]
                            )

                            # Función para abrir el PDF
                            def abrir_pdf(e):
                                try:
                                    import subprocess

                                    if platform.system() == "Darwin":  # macOS
                                        subprocess.run(["open", salida])
                                    elif platform.system() == "Windows":
                                        os.startfile(salida)
                                    else:  # Linux
                                        subprocess.run(["xdg-open", salida])
                                except Exception as ex:
                                    print(f"[ERROR] No se pudo abrir el PDF: {ex}")
                                    try:
                                        mostrar_snackbar(
                                            page,
                                            t("No se pudo abrir el PDF: {0}").format(
                                                ex
                                            ),
                                            SNACKBAR_COLOR_ERROR,
                                            3000,
                                        )
                                    except Exception:
                                        pass

                            def abrir_carpeta(e):
                                try:
                                    import os
                                    import subprocess
                                    import platform

                                    # Obtener el directorio del archivo
                                    directorio = os.path.dirname(
                                        os.path.abspath(salida)
                                    )

                                    sistema = platform.system()
                                    if sistema == "Darwin":  # macOS
                                        # Abrir la carpeta
                                        subprocess.run(["open", directorio], check=True)
                                    elif sistema == "Windows":
                                        # Abrir la carpeta en Windows
                                        subprocess.Popen(
                                            f'explorer "{directorio}"',
                                            shell=True,
                                            stdout=subprocess.DEVNULL,
                                            stderr=subprocess.DEVNULL,
                                        )
                                    else:  # Linux y otros
                                        # Abrir el directorio
                                        subprocess.run(
                                            ["xdg-open", directorio], check=True
                                        )
                                except Exception as ex:
                                    print(f"[ERROR] No se pudo abrir la carpeta: {ex}")
                                    try:
                                        mostrar_snackbar(
                                            page,
                                            t(
                                                "No se pudo abrir la carpeta: {0}"
                                            ).format(ex),
                                            SNACKBAR_COLOR_ERROR,
                                            3000,
                                        )
                                    except Exception:
                                        pass

                            dialog_exito = ft.AlertDialog(
                                modal=True,
                                title=ft.Row(
                                    [
                                        ft.Icon(
                                            ft.Icons.CHECK_CIRCLE,
                                            color=ft.Colors.GREEN,
                                            size=32,
                                        ),
                                        ft.Container(width=8),
                                        ft.Text(
                                            t("Generación Exitosa"),
                                            color=TEXTOS_FASE_1_COLOR,
                                            weight=ft.FontWeight.BOLD,
                                        ),
                                    ],
                                    alignment=ft.MainAxisAlignment.CENTER,
                                ),
                                content=ft.Container(
                                    content=ft.Column(
                                        content_items,
                                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                        tight=True,
                                    ),
                                    width=460,
                                    bgcolor=FONDO_ALERT_DIALOG,
                                    padding=ft.Padding(10, 10, 10, 10),
                                ),
                                actions=[
                                    ft.Button(
                                        t("Abrir PDF"),
                                        icon=ft.Icons.OPEN_IN_NEW,
                                        on_click=abrir_pdf,
                                        bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                                        color=BOTONES_GENERICOS_COLOR,
                                        style=ft.ButtonStyle(
                                            color={
                                                ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                                                "hovered": BOTONES_GENERICOS_HOVER_COLOR,
                                            },
                                            overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                                            padding=ft.Padding(0, 0, 0, 0),
                                            shape=ft.RoundedRectangleBorder(radius=10),
                                        ),
                                        width=120,
                                    ),
                                    ft.Button(
                                        t("Abrir carpeta"),
                                        icon=ft.Icons.FOLDER_OPEN,
                                        on_click=abrir_carpeta,
                                        bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                                        color=BOTONES_GENERICOS_COLOR,
                                        style=ft.ButtonStyle(
                                            color={
                                                ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                                                "hovered": BOTONES_GENERICOS_HOVER_COLOR,
                                            },
                                            overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                                            padding=ft.Padding(0, 0, 0, 0),
                                            shape=ft.RoundedRectangleBorder(radius=10),
                                        ),
                                        width=140,
                                    ),
                                    ft.Button(
                                        t("Cerrar"),
                                        on_click=lambda e: page.pop_dialog(),
                                        bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                                        color=BOTONES_GENERICOS_COLOR,
                                        style=ft.ButtonStyle(
                                            color={
                                                ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                                                "hovered": BOTONES_GENERICOS_HOVER_COLOR,
                                            },
                                            overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                                            padding=ft.Padding(0, 0, 0, 0),
                                            shape=ft.RoundedRectangleBorder(radius=10),
                                        ),
                                        width=110,
                                    ),
                                ],
                                actions_alignment=ft.MainAxisAlignment.CENTER,
                                bgcolor=FONDO_ALERT_DIALOG,
                            )
                            page.show_dialog(dialog_exito)

                        try:
                            mostrar_dialogo_exito()
                        except Exception as ex_dialog:
                            print(f"[ERROR] Mostrando diálogo de éxito: {ex_dialog}")
                            # Fallback a snackbar
                            try:
                                mostrar_snackbar(
                                    page, t("PDF generado en: {0}").format(salida)
                                )
                            except Exception:
                                pass
                    except InterruptedError as ie:
                        # Cancelación por el usuario
                        print(f"[INFO] Generación cancelada: {ie}")
                        # Cerrar diálogo de progreso
                        _cerrar_dialogo_principal(progress_dialog)
                        # Intentar eliminar el PDF parcial si existe
                        try:
                            if os.path.exists(salida):
                                os.remove(salida)
                                print(f"[INFO] PDF parcial eliminado: {salida}")
                        except Exception as del_ex:
                            print(
                                f"[WARNING] No se pudo eliminar PDF parcial: {del_ex}"
                            )
                        # Mostrar mensaje de cancelación
                        try:
                            mostrar_snackbar(
                                page,
                                t("Generación cancelada por el usuario"),
                                SNACKBAR_COLOR_FONDO,
                                3000,
                            )
                        except Exception:
                            pass
                    except Exception as ex:
                        import traceback

                        print(f"[ERROR WORKER] Error generando PDF: {ex}")
                        traceback.print_exc()
                        # Cerrar diálogo de progreso
                        _cerrar_dialogo_principal(progress_dialog)
                        try:
                            mostrar_snackbar(
                                page,
                                t("Error generando PDF: {0}").format(ex),
                                SNACKBAR_COLOR_ERROR,
                                5000,
                            )
                        except Exception:
                            pass
                    finally:
                        try:
                            cancelado["valor"] = False
                        except Exception:
                            pass

                page.run_task(worker)

            def cancelar_generar(e_cancel):
                print("[DEBUG] Cancelación solicitada por el usuario")
                _cerrar_dialogo_principal(dialog)

            # Dialog content
            # Mostrar información de pliego/contador si está disponible (ya no mostramos la línea "Pliego: N Pliego Cara/Dorso")
            try:
                pl_act = getattr(textfield_pliego_actual, "value", None)
                cont = getattr(texto_contador_pliegos, "value", None) or getattr(
                    texto_contador_pliegos, "text", None
                )
            except Exception:
                pl_act = None
                cont = None

            # Calcular textos para el container informativo
            try:
                traz_cols = (
                    int(GRID_COLS)
                    if "GRID_COLS" in globals() and GRID_COLS is not None
                    else "-"
                )
            except Exception:
                traz_cols = "-"
            try:
                traz_rows = (
                    int(GRID_ROWS)
                    if "GRID_ROWS" in globals() and GRID_ROWS is not None
                    else "-"
                )
            except Exception:
                traz_rows = "-"
            try:
                # Usar variables globales en mm, no textfields convertidos
                tam_w_mm = (
                    float(TAMANO_FINAL_PLIEGO.get("w_mm", 0) or 0)
                    if TAMANO_FINAL_PLIEGO.get("w_mm")
                    else 0
                )
            except Exception:
                tam_w_mm = 0
            try:
                tam_h_mm = (
                    float(TAMANO_FINAL_PLIEGO.get("h_mm", 0) or 0)
                    if TAMANO_FINAL_PLIEGO.get("h_mm")
                    else 0
                )
            except Exception:
                try:
                    tam_h_mm = float(TAMANO_FINAL_PLIEGO.get("h_mm", 0) or 0)
                except Exception:
                    tam_h_mm = 0

            # Convertir a la unidad activa para mostrar en el diálogo
            try:
                _dlg_unit = _estado_impo_ui.get("unit", _initial_unit_pref) or "mm"
                tam_w = convert_from_mm(tam_w_mm, _dlg_unit)
                tam_h = convert_from_mm(tam_h_mm, _dlg_unit)
                _dlg_unit_abbr = get_unit_abbr(_dlg_unit)
            except Exception:
                tam_w = tam_w_mm
                tam_h = tam_h_mm
                _dlg_unit_abbr = "mm"

            try:
                pliegos_val = (
                    int(state_pliego.get("total"))
                    if isinstance(state_pliego, dict)
                    and state_pliego.get("total") is not None
                    else int(getattr(state_pliego, "total", 0) or 0)
                )
            except Exception:
                pliegos_val = 0

            try:
                copias_val = int(dropdown_copias_local.value)
            except Exception:
                copias_val = 1

            try:
                # Determinar si es doble cara consultando el ordenamiento calculado (más fiable que depender de un global)
                orden = (
                    ordenamiento_calculado.get("ordenamiento", {})
                    if isinstance(ordenamiento_calculado, dict)
                    else {}
                )
                es_doble_init = False
                if orden:
                    for v in orden.values():
                        if isinstance(v, dict) and _es_dorso_val(v.get("doble_cara")):
                            es_doble_init = True
                            break
                caras_val = 2 if es_doble_init else 1
            except Exception:
                caras_val = 1

            paginas_calc = pliegos_val * caras_val * copias_val

            # Crear controles informativos individuales para poder actualizarlos dinámicamente
            info_trazado = ft.Text(
                t("trazado: {0}x{1}").format(traz_cols, traz_rows),
                color=TEXTOS_FASE_1_COLOR,
            )
            info_tamano = ft.Text(
                t("Tamaño del pliego: {0:.2f} x {1:.2f}").format(tam_w, tam_h)
                + f" {_dlg_unit_abbr}",
                color=TEXTOS_FASE_1_COLOR,
            )
            info_pliegos_generar = ft.Text(
                t("Pliegos a generar: {0}").format(pliegos_val),
                color=TEXTOS_FASE_1_COLOR,
            )
            # Determinar tipo (Cara / Doble cara) a partir del ordenamiento calculado
            try:
                orden = (
                    ordenamiento_calculado.get("ordenamiento", {})
                    if isinstance(ordenamiento_calculado, dict)
                    else {}
                )
                # Uso de valores para evitar depender del tipo de clave
                es_doble_init = False
                if orden:
                    for v in orden.values():
                        if isinstance(v, dict) and _es_dorso_val(v.get("doble_cara")):
                            es_doble_init = True
                            break

                # Fallback: Revisar dropdown global si el ordenamiento no tiene suficientes datos
                if not es_doble_init and dropdown_doble_cara:
                    val_dropdown = str(dropdown_doble_cara.value).lower()
                    if val_dropdown.startswith("d") or "dorso" in val_dropdown:
                        es_doble_init = True
            except Exception:
                es_doble_init = False
            info_tipo = ft.Text(
                t("Tipo: {0}").format(
                    t("Doble cara") if es_doble_init else t("Una Cara")
                ),
                color=TEXTOS_FASE_1_COLOR,
            )
            info_copias_generar = ft.Text(
                t("Copias a generar: {0}").format(copias_val), color=TEXTOS_FASE_1_COLOR
            )
            info_total_paginas = ft.Text(
                t("Total páginas a generar en el PDF: {0}").format(paginas_calc),
                color=TEXTOS_FASE_1_COLOR,
            )

            # Campos selector rango (creados afuera del dialog para leer sus valores desde el worker)
            # Etiqueta dinámica: 'Pliegos' si es doble cara, sino 'Páginas'
            try:
                label_selector = t("Pliegos") if es_doble_init else t("Páginas")
            except Exception:
                label_selector = t("Páginas")

            selector_rango_from = ft.TextField(
                value="1",
                width=70,
                height=35,
                text_align=ft.TextAlign.CENTER,
                content_padding=ft.Padding(6, 0, 0, 0),
                text_size=14,
                bgcolor=FONDO_TEXTFIELDS_COLOR,
                color=TEXTOS_FASE_1_COLOR,
                border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)),
                text_vertical_align=ft.VerticalAlignment.CENTER,
            )

            selector_rango_to = ft.TextField(
                value=str(pliegos_val if copias_val == 1 else pliegos_val),
                width=70,
                height=35,
                text_align=ft.TextAlign.CENTER,
                content_padding=ft.Padding(6, 0, 0, 0),
                text_size=14,
                bgcolor=FONDO_TEXTFIELDS_COLOR,
                color=TEXTOS_FASE_1_COLOR,
                border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)),
                text_vertical_align=ft.VerticalAlignment.CENTER,
            )

            info_container = ft.Container(
                ft.Column(
                    [
                        info_trazado,
                        info_tamano,
                        info_pliegos_generar,
                        info_tipo,
                        info_copias_generar,
                        info_total_paginas,
                    ],
                    tight=True,
                    spacing=4,
                ),
                alignment=ft.Alignment.CENTER,
                padding=ft.Padding(8, 8, 8, 8),
                bgcolor=FONDO_HEADER_FASE_1,
            )

            dialog = ft.AlertDialog(
                modal=True,
                shape=ft.RoundedRectangleBorder(radius=12),
                title=ft.Row(
                    [
                        ft.Text(
                            t("Crear PDF - Imposición"),
                            color=TEXTOS_FASE_1_COLOR,
                            weight=ft.FontWeight.BOLD,
                        )
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                title_padding=ft.Padding(16, 16, 16, 8),
                content=ft.Container(
                    content=ft.Column(
                        [
                            # Contenedor informativo centrado
                            info_container,
                            ft.Container(height=12),
                            # Copias y opciones (dropdown para copias)
                            ft.Row(
                                [
                                    ft.Text(t("Copias:")),
                                    dropdown_copias_local,
                                    ft.Container(width=12),
                                    checkbox_xerox_local,
                                ],
                                alignment=ft.MainAxisAlignment.CENTER,
                            ),
                            ft.Container(height=12),
                            # Selector de rango de impresión (páginas/pliegos)
                            ft.Row(
                                [
                                    ft.Text(
                                        t("{0}:").format(label_selector),
                                        color=TEXTOS_FASE_1_COLOR,
                                    ),
                                    ft.Container(width=6),
                                    ft.Text(t("Desde:"), color=TEXTOS_FASE_1_COLOR),
                                    ft.Container(width=4),
                                    selector_rango_from,
                                    ft.Container(width=6),
                                    ft.Text(t("Hasta:"), color=TEXTOS_FASE_1_COLOR),
                                    ft.Container(width=4),
                                    selector_rango_to,
                                ],
                                alignment=ft.MainAxisAlignment.CENTER,
                                spacing=4,
                            ),
                            ft.Container(height=12),
                            ft.Divider(height=1, color=BORDE_TEXTFIELDS_COLOR),
                            ft.Container(height=8),
                            ft.Container(height=16),
                            ft.Button(
                                t("Generar PDF y guardar"),
                                on_click=seleccionar_path,
                                bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                                style=ft.ButtonStyle(
                                    color={
                                        ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                                        "hovered": BOTONES_GENERICOS_HOVER_COLOR,
                                    },
                                    overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                                    padding=ft.Padding(2, 2, 2, 2),
                                    shape=ft.RoundedRectangleBorder(radius=10),
                                ),
                                width=200,
                            ),
                            ft.Container(height=8),
                            ft.Button(
                                t("Cancelar"),
                                on_click=cancelar_generar,
                                bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                                style=ft.ButtonStyle(
                                    color={
                                        ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                                        "hovered": BOTONES_GENERICOS_HOVER_COLOR,
                                    },
                                    overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                                    padding=ft.Padding(0, 0, 0, 0),
                                    shape=ft.RoundedRectangleBorder(radius=10),
                                ),
                                width=110,
                            ),
                        ],
                        tight=True,
                        spacing=4,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    width=460,
                    bgcolor=FONDO_ALERT_DIALOG,
                    border_radius=ft.BorderRadius(
                        top_left=0,
                        top_right=0,
                        bottom_left=12,
                        bottom_right=12,
                    ),
                    padding=ft.Padding(16, 10, 16, 6),
                ),
                content_padding=ft.Padding(0, 0, 0, 0),
                bgcolor=FONDO_ALERT_DIALOG,
            )

            try:
                page.show_dialog(dialog)
            except Exception:
                pass
        except Exception as ex:
            print(f"[ERROR dialog generar pdf] {ex}")

    boton_generar_pdf = ft.Container(
        content=ft.Icon(ft.Icons.PRINT, size=24, color=BOTONES_GENERICOS_COLOR),
        width=40,
        height=40,
        border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
        border_radius=4,
        bgcolor=FONDO_TEXTFIELDS_COLOR,
        alignment=ft.Alignment.CENTER,
        visible=True,
        on_click=abrir_dialogo_generar_pdf,
        tooltip=t("Generar PDF"),
    )

    # TODO: main col (columna principal)
    main_col = ft.Column(
        [
            ft.Row(
                [
                    # Navegador de pliegos al principio
                    navegacion_pliegos_container,
                    ft.Container(width=5),
                    # Slider de zoom y botón reset dentro de un contenedor centrado
                    ft.Container(
                        content=ft.Row(
                            [
                                zoom_slider,
                                boton_reset_zoom,
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                            spacing=0,
                        ),
                        alignment=ft.Alignment.CENTER,
                        expand=True,
                        padding=0,
                    ),
                    ft.Container(width=5),
                    texto_total_pliegos,
                    ft.Container(width=10),
                ],
                alignment=ft.MainAxisAlignment.START,
                spacing=8,
                height=50,
            ),
            ft.Container(height=2),  # Espacio mínimo entre botones y viewer
            viewer_container,
        ],
        spacing=0,  # Sin spacing automático para control total
        expand=True,
    )

    # Contenedor de controles de trazado (Oculto inicialmente)
    controles_trazado_container = ft.Column(
        [
            # Botón de preferencias MOVIDO AL FINAL
            # Sección Tamaño Pliego
            ft.Text(
                t("Pliego"),
                size=16,
                weight=ft.FontWeight.BOLD,
                color=TEXTOS_FASE_1_COLOR,
            ),
            ft.Container(height=3),
            # dropdown_tamanos_general,  # ELIMINADO: ya no se usa
            ft.Row(
                [textfield_ancho, textfield_alto],
                spacing=5,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            ft.Container(height=5),
            # textfield_sangre movido abajo
            ft.Row([boton_auto_manual_pliego], alignment=ft.MainAxisAlignment.CENTER),
            ft.Divider(height=1, thickness=1, color=BORDE_TEXTFIELDS_COLOR),
            # Info PDF Boxes (moved arriba of 'Tamaño Usuario')
            ft.Container(height=3),
            ft.Row([container_info_pdf], alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(height=3),
            ft.Divider(height=1, thickness=1, color=BORDE_TEXTFIELDS_COLOR),
            # Sección Tamaño Usuario
            ft.Text(
                t("Tamaño Usuario"),
                size=16,
                weight=ft.FontWeight.BOLD,
                color=TEXTOS_FASE_1_COLOR,
            ),
            ft.Container(height=5),
            ft.Row(
                [textfield_tamano_usuario_w, textfield_tamano_usuario_h],
                spacing=5,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            ft.Container(height=5),
            ft.Row(
                [textfield_sangre], spacing=5, alignment=ft.MainAxisAlignment.CENTER
            ),
            ft.Container(height=5),
            ft.Divider(height=1, thickness=1, color=BORDE_TEXTFIELDS_COLOR),
            ft.Text(
                t("Ajustes Avanzados"),
                size=16,
                weight=ft.FontWeight.BOLD,
                color=TEXTOS_FASE_1_COLOR,
            ),
            ft.Row(
                [
                    boton_calles,
                    boton_offset_pliego,
                    boton_offset_pdfs,
                    boton_cruces,
                    boton_marcas_texto,
                    boton_preferencias,
                ],
                spacing=10,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            # Línea divisoria después de Ajustes avanzados
            ft.Divider(height=1, thickness=1, color=BORDE_TEXTFIELDS_COLOR),
            # Sección Trazado
            ft.Text(
                t("Trazado"),
                size=16,
                weight=ft.FontWeight.BOLD,
                color=TEXTOS_FASE_1_COLOR,
            ),
            ft.Column(
                [
                    checkbox_cruces,
                    checkbox_lineas_corte,
                    checkbox_marcas_texto,
                    checkbox_linea_exterior,
                ],
                spacing=0,
            ),
            # ft.Container(height=0, expand=True),
            # boton_recalcular movido al final
        ],
        spacing=5,
        visible=True,
    )  # Oculto hasta cargar PDF

    right_column = ft.Container(
        ft.Column(
            [
                ft.Container(
                    boton_cargar_pdf, alignment=ft.Alignment.TOP_CENTER, visible=False
                ),
                ft.Container(
                    texto_paginas_requeridas,
                    alignment=ft.Alignment.CENTER,
                    visible=False,
                ),
                ft.Container(
                    texto_validacion, alignment=ft.Alignment.CENTER, visible=False
                ),
                ft.Container(
                    texto_archivo, alignment=ft.Alignment.CENTER, visible=False
                ),
                controles_trazado_container,
                ft.Container(
                    expand=True, height=5
                ),  # Spacer con altura mínima para empujar botones al fondo
                # Línea divisoria final
                ft.Divider(height=1, thickness=1, color=BORDE_TEXTFIELDS_COLOR),
                # Fila de botones de acción
                # Barra de botones con iconos (estilo PageNumber)
                ft.Row(
                    [
                        boton_recalcular,
                        boton_guardar_trabajo,
                        boton_generar_pdf,
                        boton_cancelar,
                    ],
                    spacing=10,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                ft.Divider(height=1, thickness=1, color=BORDE_TEXTFIELDS_COLOR),
                # # Sección Guardar Ajustes (placeholder para mantener espacio bajo la barra del SO)
                ft.Container(width=160, height=48),
            ],
            spacing=5,
            expand=True,
        ),
        width=320,
        border_radius=ft.BorderRadius(
            top_left=6, top_right=6, bottom_left=6, bottom_right=6
        ),
        padding=ft.Padding(10, 10, 10, 10),
        bgcolor=FONDO_CALCULO_FASE_1,
    )

    # Exponer instancias en refs globales para que la app pueda acceder a los controles

    # Lista de todos los refs globales definidos al inicio del archivo
    _refs_globales = [
        "textfield_ancho",
        "textfield_alto",
        "textfield_sangre",
        "textfield_medianil",
        "texto_archivo",
        "texto_paginas",
        "texto_paginas_requeridas",
        "texto_validacion",
        "dropdown_copias",
        "checkbox_xerox",
        "dropdown_doble_cara",
        "dropdown_rotacion",
        "file_picker",
        "boton_cargar_pdf",
        "boton_crear",
        "boton_cancelar",
        "progress_bar",
        "texto_contador_pliegos",
        "progress_row",
        "dropdown_tamanos_general",
        "main_col",
        "right_column",
        "boton_crear_tamaño_pliego",
        "texto_info_pdf_mediabox",
        "texto_info_pdf_trimbox",
        "texto_info_pdf_bleedbox",
    ]
    for _ref in _refs_globales:
        try:

            globals()[_ref] = locals().get(_ref, globals().get(_ref))
        except Exception:
            pass

    inner = ft.Container(
        ft.Row(
            [
                ft.Container(
                    main_col, expand=True
                ),  # Envolver main_col en Container con expand
                right_column,
            ],
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
            spacing=0,
        ),
        padding=ft.Padding(5, 5, 5, 5),
        bgcolor=FONDO_ALERT_DIALOG,
        border_radius=ft.BorderRadius(
            top_left=6, top_right=6, bottom_left=6, bottom_right=6
        ),
        expand=True,
    )

    wrapper = ft.Container(
        ft.Column(
            [
                ft.Row([inner], alignment=ft.MainAxisAlignment.START, expand=True),
            ],
            expand=True,
        ),
        expand=True,
        alignment=ft.Alignment.CENTER,
        padding=ft.Padding(5, 5, 5, 5),
        bgcolor=ft.Colors.with_opacity(0.45, ft.Colors.BLACK),
    )

    def _cerrar_imposicion_overlay(e=None):
        """
        Cierra la ventana de imposición SIN resetear ningún dato.
        Solo restaura el handler de ventana y remueve el overlay.
        Los datos (PDF, offsets, tamaños, grid, etc.) se mantienen para reapertura.
        """
        # Guardar estado antes de cerrar
        try:
            print("[IMPO WINDOW] Guardando estado antes de cerrar...")
            guardar_estado_impo_ui()
            # STAMP COMPLETO AL CERRAR (activado para debug)
            print(f"\n{'='*80}")
            print(f"[STAMP AL CERRAR] Estado completo guardado:")
            print(f"{'='*80}")
            print(_estado_impo_ui)
            print(f"{'='*80}\n")
        except Exception as ex:
            print(f"[IMPO WINDOW] Error guardando estado: {ex}")

        # Restaurar el handler de ventana anterior
        page.window.on_event = _previous_window_handler
        print("[IMPO WINDOW] Handler de ventana restaurado")

        # Remover overlay de imposición
        if wrapper in page.overlay:
            page.overlay.remove(wrapper)
        page.update()
        print("[IMPO WINDOW] Ventana de imposición cerrada - datos conservados")

    # Flet 1.0: FilePicker es Service (auto-registra en construcción); no va a overlay

    # Inicializar unidades después de crear los controles
    try:
        # Llamar update_units para aplicar la unidad guardada en las preferencias
        try:
            update_units(_initial_unit_pref)
            print(f"[INIT] ✅ Unidad inicial aplicada: {_initial_unit_pref}")
        except Exception as ex:
            print(f"[INIT] ⚠️ Error llamando update_units, aplicando manualmente: {ex}")
            # Si update_units no está definida aún, intentar aplicar manualmente
            unit_label = get_unit_abbr(_initial_unit_pref)
            if textfield_ancho:
                textfield_ancho.label = t("Ancho ({0})").format(unit_label)
            if textfield_alto:
                textfield_alto.label = t("Alto ({0})").format(unit_label)
            if textfield_sangre:
                textfield_sangre.label = t("Sangre ({0})").format(unit_label)
    except Exception as ex:
        print(f"[INIT] ❌ Error aplicando unidad inicial: {ex}")

    # ELIMINADO: Timer 1 que causaba race condition
    # El ordenamiento ya viene pre-calculado desde pdf_ordenado_ui.py
    # def on_ventana_open():
    #     recalcular_ordenamiento()
    # threading.Timer(0.1, on_ventana_open).start()

    # Estado del debounce de resize (clausura)
    _resize_state = {"pending": None, "task": None}

    # Handler para redimensionar el viewer cuando cambia el tamaño de la ventana.
    # Paridad PageNumber (main_screen._on_window_resize + _apply_resize_debounced):
    # durante el gesto solo se guarda el tamaño pendiente; al parar (0.2s) se
    # aplica UN ÚNICO reajuste de zoom+centrado.
    def _on_page_resize(e=None):
        # actualizar VIEWER_* definidos en el scope exterior
        nonlocal VIEWER_WIDTH, VIEWER_HEIGHT
        try:
            new_w = (
                int(page.width - CROMA_HORIZONTAL_OVERLAY)
                if page.width
                else VIEWER_WIDTH
            )
            new_h = (
                int(page.height - CROMA_VERTICAL_OVERLAY)
                if page.height
                else VIEWER_HEIGHT
            )
        except Exception:
            return
        _resize_state["pending"] = (new_w, new_h)
        if _resize_state.get("task") is None:
            _resize_state["task"] = page.run_task(_apply_resize_debounced)

    async def _apply_resize_debounced():
        nonlocal VIEWER_WIDTH, VIEWER_HEIGHT
        try:
            await asyncio.sleep(0.2)
            pending = _resize_state.get("pending")
            _resize_state["pending"] = None
            if pending:
                new_w, new_h = pending
                if new_w != VIEWER_WIDTH or new_h != VIEWER_HEIGHT:
                    VIEWER_WIDTH, VIEWER_HEIGHT = new_w, new_h
                    print(f"[RESIZE] Nuevo viewer: {VIEWER_WIDTH}×{VIEWER_HEIGHT}px")
                    # Sincronizar el tamaño del container con las variables: el
                    # width explícito SÍ manda en el eje horizontal (el expand
                    # solo rellena el eje vertical del Column padre). Sin esto
                    # el visor se queda con el ancho de creación al ensanchar.
                    try:
                        viewer_container.width = VIEWER_WIDTH
                        viewer_container.height = VIEWER_HEIGHT
                        viewer_container.update()
                    except Exception:
                        pass
                    # Re-escalar al nuevo tamaño: igual que pulsar el botón reset
                    # (reset_zoom hace zoom_level=1.0 + actualizar_viewer_zoom con
                    # do_center=True, que con VIEWER_* actualizados re-encaja).
                    try:
                        reset_zoom(None)
                    except Exception as ex:
                        print(f"[RESIZE] reset zoom fallo: {ex}")
        except Exception as ex:
            print(f"[RESIZE] aplicar resize fallo: {ex}")
        finally:
            _resize_state["task"] = None

    try:
        page.on_resize = _on_page_resize
    except Exception:
        pass

    # Bloquear cierre de ventana con botón nativo mientras imposición está abierta
    def _on_window_event_impo(e):
        """Delega el cierre al handler principal para respetar cambios sin guardar."""
        # Flet 1.0: el cierre llega en e.type (WindowEventType.CLOSE="close"), e.data es None
        _ev_type = getattr(getattr(e, "type", None), "value", getattr(e, "type", None))
        if _ev_type == "close" or getattr(e, "data", None) == "close":
            try:
                trabajo_mod = bool(_estado_impo_ui.get("trabajo_modificado", False))
            except Exception:
                trabajo_mod = False

            print(
                f"[IMPO WINDOW] Evento close en imposicion: trabajo_modificado={trabajo_mod}. Delegando al handler principal."
            )

            if callable(_previous_window_handler):
                _previous_window_handler(e)
            else:
                page.run_task(page.window.destroy)
            return

        if callable(_previous_window_handler):
            _previous_window_handler(e)

    # Guardar el handler anterior si existe
    _previous_window_handler = page.window.on_event
    page.window.prevent_close = True
    page.window.on_event = _on_window_event_impo

    # Si hay loading_dialog, hacer wrapper invisible inicialmente
    # Se hará visible cuando auto_load termine
    if loading_dialog:
        wrapper.visible = False

    page.overlay.append(wrapper)
    page.update()

    # Restaurar PDF si hay uno cargado previamente (solo actualizar UI, NO reprocesar)
    if (
        _pdf_ordenado_actual
        and os.path.exists(_pdf_ordenado_actual)
        and _archivo_seleccionado["ruta"]
    ):
        print(f"[IMPO_UI] ✅ PDF ya cargado en memoria: {_pdf_ordenado_actual}")
        print(f"[IMPO_UI] ✅ Todos los datos conservados - UI lista")
        # El PDF ya fue procesado, la UI ya tiene todos los controles configurados
        # Solo necesitamos que la ventana se muestre con los datos que ya existen en memoria

    # Iniciar un watcher en background para detectar cambios de tamaño si page.on_resize
    # no es fiable/compatible en la plataforma en uso.
    def _start_resize_watcher():
        async def _watch():
            try:
                prev_w = int(page.width or 0)
                prev_h = int(page.height or 0)
            except Exception:
                prev_w = 0
                prev_h = 0
            # loop hasta que el overlay se cierre
            while True:
                try:
                    await asyncio.sleep(0.25)
                except Exception:
                    pass
                try:
                    # si el wrapper ya no está en overlay, terminar watcher
                    if wrapper not in page.overlay:
                        # print("[WATCHER] Overlay cerrado, deteniendo watcher")
                        break
                except Exception:
                    break

                try:
                    cur_w = int(page.width or 0)
                    cur_h = int(page.height or 0)
                except Exception:
                    cur_w = prev_w
                    cur_h = prev_h

                if cur_w != prev_w or cur_h != prev_h:
                    prev_w = cur_w
                    prev_h = cur_h
                    try:
                        if DEBUG_IMPO_UI:
                            print(f"[WATCHER] Detectado resize: {cur_w}x{cur_h}")
                    except Exception:
                        pass
                    try:
                        # Llamar al handler definido anteriormente
                        _on_page_resize(None)
                    except Exception as e:
                        try:
                            if DEBUG_IMPO_UI:
                                print(f"[WATCHER] Error al invocar _on_page_resize: {e}")
                        except Exception:
                            pass
            # watcher terminado

        page.run_task(_watch)

    try:
        _start_resize_watcher()
    except Exception:
        pass

    try:
        boton_cancelar.on_click = lambda e: _cerrar_imposicion_overlay(e)
    except Exception:
        pass

    try:
        boton_cancelar.on_click = lambda e: _cerrar_imposicion_overlay(e)
    except Exception:
        pass

    # ========================================================================
    # AUTO-CARGA DE PDF ORDENADO (solo si no hay datos en memoria)
    # ========================================================================
    try:
        # Solo auto-cargar si NO hay PDF ya cargado en memoria
        if not _archivo_seleccionado["ruta"]:
            pdf_temp_ordenado = obtener_pdf_ordenado_temp()
            ordenamiento_precalculado = obtener_ordenamiento_calculado()

            if pdf_temp_ordenado and os.path.exists(pdf_temp_ordenado):
                print(f"[IMPO_UI] Auto-cargando PDF ordenado: {pdf_temp_ordenado}")

                # Guardar en variable global
                _pdf_ordenado_actual = pdf_temp_ordenado

                async def auto_load():
                    try:
                        # ═══════════════════════════════════════════════════════════════════════════════
                        # CARGAR PREFERENCIAS ANTES DE PROCESAR PDF (AUTO-CARGA)
                        # ═══════════════════════════════════════════════════════════════════════════════
                        # ⚠️ IMPORTANTE: NO cargar preferencias si ya hay datos de trabajo cargado
                        # Verificar si hay valores de checkboxes en estado (vienen de trabajo guardado)
                        estado = _estado_impo_ui
                        # Determinar si ya hay un trabajo cargado comprobando campos significativos
                        trabajo_cargado = bool(
                            estado.get("pdf_stamp") or estado.get("ultima_modificacion")
                        )

                        if not trabajo_cargado:
                            # Solo cargar preferencias si NO hay trabajo cargado
                            print(
                                "[PREF] 🔄 Cargando preferencias antes de auto-carga de PDF..."
                            )
                            cargar_preferencias_imposicion(
                                checkbox_cruces=checkbox_cruces,
                                checkbox_lineas_corte=checkbox_lineas_corte,
                                checkbox_marcas_texto=checkbox_marcas_texto,
                                checkbox_linea_exterior=checkbox_linea_exterior,
                            )
                        else:
                            print(
                                "[PREF] ⏭️ Trabajo cargado detectado - saltando carga de preferencias (pdf_stamp/ultima_modificacion presente)"
                            )

                        # Usar función refactorizada con ordenamiento pre-calculado
                        exito = await procesar_pdf_para_imposicion(
                            pdf_temp_ordenado,
                            ordenamiento_precalculado=ordenamiento_precalculado,
                        )

                        if exito:
                            print("[IMPO_UI] ✅ Auto-carga exitosa")
                            # ⚠️ NO limpiar archivos temporales - se necesitan para reapertura
                            # limpiar_pdf_ordenado_temp()
                            # limpiar_ordenamiento_calculado()
                        else:
                            print("[IMPO_UI] ❌ Error en auto-carga")

                        # Cerrar loading_dialog y mostrar wrapper
                        if loading_dialog:
                            try:
                                page.pop_dialog()
                            except Exception:
                                pass
                            wrapper.visible = True
                            try:
                                wrapper.update()
                                page.update()
                            except Exception:
                                pass
                            print("[IMPO_UI] 🎉 Diálogo cerrado y ventana visible")

                    except Exception as ex:
                        print(f"[IMPO_UI] Error en auto-load: {ex}")
                        import traceback

                        traceback.print_exc()
                        # Aún así cerrar diálogo y mostrar UI para que no quede bloqueado
                        if loading_dialog:
                            try:
                                page.pop_dialog()
                            except Exception:
                                pass
                            wrapper.visible = True
                            try:
                                wrapper.update()
                                page.update()
                            except Exception:
                                pass

                async def auto_load_async():
                    await asyncio.sleep(0.5)
                    await auto_load()

                page.run_task(auto_load_async)
            else:
                # No hay PDF temp válido - cerrar diálogo y mostrar wrapper
                print("[IMPO_UI] ⚠️ No hay PDF temp válido para auto-cargar")
                if loading_dialog:
                    try:
                        page.pop_dialog()
                    except Exception:
                        pass
                    wrapper.visible = True
                    try:
                        wrapper.update()
                        page.update()
                    except Exception:
                        pass
        else:
            print("[IMPO_UI] ✅ PDF ya en memoria - sin reprocesar")

            # Aunque el PDF esté en cache, necesitamos activar la UI y renderizar el pliego
            def activar_ui_desde_cache():
                try:
                    print("[IMPO_UI] 🔄 Activando UI desde cache...")

                    # 1. Mostrar controles de trazado (mismo código que en procesar_pdf_para_imposicion)
                    controles_trazado_container.visible = True
                    boton_recalcular.visible = True
                    boton_zoom_in.visible = True
                    boton_zoom_out.visible = True
                    boton_reset_zoom.visible = True
                    viewer_container.visible = True
                    navegacion_pliegos_container.visible = True

                    # Controles individuales
                    textfield_ancho.visible = True
                    textfield_alto.visible = True
                    boton_auto_manual_pliego.visible = True
                    textfield_tamano_usuario_w.visible = True
                    textfield_tamano_usuario_h.visible = True
                    textfield_sangre.visible = True

                    # RESTAURAR VALORES DE TAMAÑO DE PLIEGO (AUTO/MANUAL)
                    estado = _estado_impo_ui
                    unit = estado.get("unit", _initial_unit_pref)
                    if estado.get("pliego_ancho") is not None:
                        try:
                            textfield_ancho.value = f"{convert_from_mm(float(estado['pliego_ancho']), unit):.2f}"
                        except Exception:
                            textfield_ancho.value = f"{estado['pliego_ancho']:.2f}"
                    if estado.get("pliego_alto") is not None:
                        try:
                            textfield_alto.value = f"{convert_from_mm(float(estado['pliego_alto']), unit):.2f}"
                        except Exception:
                            textfield_alto.value = f"{estado['pliego_alto']:.2f}"

                    # Restaurar estado del botón AUTO/MANUAL
                    pliego_congelado = estado.get("pliego_congelado", False)
                    boton_auto_manual_pliego.content = (
                        t("Tamaño manual") if pliego_congelado else t("Tamaño auto")
                    )

                    try:
                        textfield_ancho.update()
                        textfield_alto.update()
                        boton_auto_manual_pliego.update()
                    except:
                        pass

                    # Dropdowns
                    try:
                        dropdown_doble_cara.visible = True
                        if dropdown_doble_cara:
                            dropdown_doble_cara.value = estado.get(
                                "dropdown_doble_cara", "cara"
                            )

                        dropdown_rotacion.visible = True
                        if dropdown_rotacion:
                            dropdown_rotacion.value = estado.get(
                                "dropdown_rotacion", "0°"
                            )

                        dropdown_copias.visible = True
                        if dropdown_copias:
                            dropdown_copias.value = estado.get("dropdown_copias", "1")

                        if "dropdown_tipo_corte" in globals():
                            dropdown_tipo_corte.visible = True
                    except Exception:
                        pass

                    # Botones de configuración
                    boton_calles.visible = True
                    boton_offset_pliego.visible = True
                    boton_offset_pdfs.visible = True
                    boton_cruces.visible = True
                    boton_marcas_texto.visible = True

                    # RESTAURAR CHECKBOXES (usar claves en MAYÚSCULAS como se guardan en trabajo_manager)
                    estado = _estado_impo_ui
                    if checkbox_cruces:
                        checkbox_cruces.value = estado.get("CHECK_BOX_CRUCES", False)
                        try:
                            checkbox_cruces.update()
                        except:
                            pass
                    if checkbox_lineas_corte:
                        checkbox_lineas_corte.value = estado.get(
                            "CHECK_BOX_LINEAS_CORTE", False
                        )
                        try:
                            checkbox_lineas_corte.update()
                        except:
                            pass
                    if checkbox_marcas_texto:
                        checkbox_marcas_texto.value = estado.get(
                            "CHECK_BOX_MARCAS_TEXTO", False
                        )
                        try:
                            checkbox_marcas_texto.update()
                        except:
                            pass
                    if checkbox_linea_exterior:
                        checkbox_linea_exterior.value = estado.get(
                            "CHECK_BOX_LINEA_EXTERIOR", True
                        )
                        try:
                            checkbox_linea_exterior.update()
                        except:
                            pass

                    # ACTUALIZAR INFO DEL PDF (mediabox, trimbox, bleedbox)
                    if (
                        _archivo_seleccionado.get("boxes_by_page")
                        and 0 in _archivo_seleccionado["boxes_by_page"]
                    ):
                        boxes_p0 = _archivo_seleccionado["boxes_by_page"][0]

                        def fmt_box(box_tuple):
                            if not box_tuple or len(box_tuple) != 4:
                                return "-"
                            w_pt = box_tuple[2] - box_tuple[0]
                            h_pt = box_tuple[3] - box_tuple[1]
                            w_mm = w_pt * 0.352778
                            h_mm = h_pt * 0.352778

                            # Obtener unidad actual
                            current_unit = get_preference("unit", "mm")
                            unit_label = get_unit_abbr(current_unit)

                            # Convertir a unidad actual
                            w_converted = convert_from_mm(w_mm, current_unit)
                            h_converted = convert_from_mm(h_mm, current_unit)

                            return f"{w_converted:.2f} x {h_converted:.2f} {unit_label}"

                        texto_info_pdf_mediabox.value = t("Total: {0}").format(
                            fmt_box(boxes_p0.get("mediabox"))
                        )
                        texto_info_pdf_trimbox.value = t("Corte: {0}").format(
                            fmt_box(boxes_p0.get("trimbox"))
                        )

                        try:
                            mb = boxes_p0.get("mediabox")
                            tb = boxes_p0.get("trimbox")
                            if mb and tb:
                                mb_w = mb[2] - mb[0]
                                tb_w = tb[2] - tb[0]
                                sangre_pt = (mb_w - tb_w) / 2
                                sangre_mm = sangre_pt * 0.352778
                                # Obtener unidad actual
                                current_unit = get_preference("unit", "mm")
                                unit_label = get_unit_abbr(current_unit)
                                sangre_converted = convert_from_mm(
                                    sangre_mm, current_unit
                                )

                                texto_info_pdf_bleedbox.value = t("Sangre: {0}").format(
                                    f"{sangre_converted:.2f} {unit_label}"
                                )
                            else:
                                texto_info_pdf_bleedbox.value = t("Sangre: -")
                        except:
                            texto_info_pdf_bleedbox.value = t("Sangre: -")

                        try:
                            texto_info_pdf_mediabox.update()
                            texto_info_pdf_trimbox.update()
                            texto_info_pdf_bleedbox.update()
                        except:
                            pass

                    # Actualizar validación y botón crear
                    paginas_requeridas = ordenamiento_calculado.get(
                        "paginas_requeridas", 0
                    )
                    paginas_actuales = _archivo_seleccionado.get("paginas", 0)

                    if paginas_actuales == paginas_requeridas:
                        texto_validacion.value = t("Correcto: {0} páginas").format(
                            paginas_actuales
                        )
                        texto_validacion.color = SUCCESS_COLOR
                        boton_crear.disabled = False
                    else:
                        texto_validacion.value = t(
                            "Error: tiene {0}, necesita {1}"
                        ).format(paginas_actuales, paginas_requeridas)
                        texto_validacion.color = ERROR_COLOR
                        boton_crear.disabled = True

                    # 2. ACTUALIZAR TOTAL DE PLIEGOS (CRÍTICO para contador "Pliego X/Y")
                    # Usar num_paginas del PDF como total de imágenes si imagenes_secuenciales está vacío
                    total_imgs = len(
                        _archivo_seleccionado.get("imagenes_secuenciales", {})
                    )
                    if total_imgs == 0:
                        total_imgs = _archivo_seleccionado.get(
                            "num_paginas", _archivo_seleccionado.get("paginas", 0)
                        )

                    rows_calc = (
                        int(textfield_grid_rows.value)
                        if textfield_grid_rows.value
                        else 1
                    )
                    cols_calc = (
                        int(textfield_grid_cols.value)
                        if textfield_grid_cols.value
                        else 1
                    )

                    print(
                        f"[ACTIVAR_CACHE] Actualizando total pliegos: total_imgs={total_imgs}, rows={rows_calc}, cols={cols_calc}"
                    )
                    actualizar_total_pliegos(total_imgs, rows_calc, cols_calc)
                    navegacion_pliegos_container.visible = True

                    # 3. Actualizar estado de navegación de pliegos
                    actualizar_estado_botones_pliego()

                    # 4. Actualizar todos los controles (incluyendo main_col que contiene texto_total_pliegos)
                    try:
                        texto_validacion.update()
                        boton_crear.update()
                        controles_trazado_container.update()
                        viewer_container.update()
                        navegacion_pliegos_container.update()
                        texto_total_pliegos.update()
                        main_col.update()  # CRÍTICO: Forzar actualización del contenedor que tiene texto_total_pliegos
                    except Exception as ex:
                        print(f"[IMPO_UI] Error actualizando controles: {ex}")

                    # 5. RECALCULAR ORDENAMIENTO (Importante para restaurar estado correcto)
                    try:
                        print(
                            "[IMPO_UI] 🔄 Forzando recálculo de ordenamiento al restaurar..."
                        )
                        recalcular_ordenamiento()
                    except Exception as ex:
                        print(
                            f"[IMPO_UI] ⚠️ Error recalculando ordenamiento (puede ser normal en carga): {ex}"
                        )

                    # 6. RENDERIZAR PLIEGO desde cache (CRÍTICO)
                    print("[IMPO_UI] 🎨 Renderizando pliego desde cache...")
                    actualizar_trazado(None)

                    print("[IMPO_UI] ✅ UI activada y pliego renderizado desde cache")

                    # Cerrar loading_dialog y mostrar wrapper
                    if loading_dialog:
                        try:
                            page.pop_dialog()
                        except Exception:
                            pass
                        wrapper.visible = True
                        try:
                            wrapper.update()
                            page.update()
                        except Exception:
                            pass
                        print(
                            "[IMPO_UI] 🎉 Diálogo cerrado y ventana visible (desde cache)"
                        )

                except Exception as ex:
                    print(f"[IMPO_UI] ❌ Error activando UI desde cache: {ex}")
                    import traceback

                    traceback.print_exc()
                    # Aún así cerrar diálogo y mostrar UI
                    if loading_dialog:
                        try:
                            page.pop_dialog()
                        except Exception:
                            pass
                        wrapper.visible = True
                        try:
                            wrapper.update()
                            page.update()
                        except Exception:
                            pass

            # Ejecutar activación en el event loop (mismo patrón que auto_load)
            async def activar_ui_desde_cache_async():
                await asyncio.sleep(0.5)
                activar_ui_desde_cache()

            page.run_task(activar_ui_desde_cache_async)

    except Exception as ex:
        print(f"[IMPO_UI] Error en auto-carga de PDF ordenado: {ex}")
        # Asegurar que el diálogo se cierre y la UI se muestre aún si hay error
        if loading_dialog:
            try:
                page.pop_dialog()
            except Exception:
                pass
            wrapper.visible = True
            try:
                wrapper.update()
                page.update()
            except Exception:
                pass

    # ════════════════════════════════════════════════════════════════════════════════
    # ACTUALIZAR CONTROLES DESDE ESTADO GUARDADO
    # Solo cuando NO hay PDF en cache (para evitar doble renderizado)
    # ════════════════════════════════════════════════════════════════════════════════
    # Cuando hay PDF en cache, activar_ui_desde_cache() ya actualiza todo
    tiene_pdf_en_cache = (
        _pdf_ordenado_actual
        and os.path.exists(_pdf_ordenado_actual)
        and _archivo_seleccionado["ruta"]
    )

    if (
        _estado_impo_ui.get("pdf_stamp")
        and _estado_impo_ui.get("pdf_ruta")
        and not tiene_pdf_en_cache
    ):
        try:
            print("[ESTADO] 🔄 Actualizando controles UI desde estado guardado...")
            actualizar_controles_desde_estado(
                textfield_ancho=textfield_ancho,
                textfield_alto=textfield_alto,
                textfield_sangre=textfield_sangre,
                textfield_grid_cols=textfield_grid_cols,
                textfield_grid_rows=textfield_grid_rows,
                textfield_tamano_usuario_w=textfield_tamano_usuario_w,
                textfield_tamano_usuario_h=textfield_tamano_usuario_h,
                textfield_offset_img_x=textfield_offset_img_x,
                textfield_offset_img_y=textfield_offset_img_y,
                textfield_offset_trazado_x=textfield_offset_trazado_x,
                textfield_offset_trazado_y=textfield_offset_trazado_y,
                dropdown_copias=dropdown_copias,
                dropdown_doble_cara=dropdown_doble_cara,
                dropdown_rotacion=dropdown_rotacion,
                checkbox_cruces=checkbox_cruces,
                checkbox_lineas_corte=checkbox_lineas_corte,
                checkbox_marcas_texto=checkbox_marcas_texto,
                checkbox_linea_exterior=checkbox_linea_exterior,
            )
        except Exception as ex:
            print(f"[ESTADO] Error actualizando controles: {ex}")
    else:
        print("[ESTADO] ℹ️ Sin estado previo - controles usan valores por defecto")

    # CRÍTICO: Aplicar conversión de unidades inicial según preferencias
    try:
        unit_inicial = _estado_impo_ui.get("unit") or _initial_unit_pref or "mm"
        print(f"[UNIT INIT] 🔄 Aplicando unidad inicial: {unit_inicial}")
        update_units(unit_inicial)
        print(f"[UNIT INIT] ✅ Conversión de unidades aplicada")
    except Exception as ex:
        print(f"[UNIT INIT] ❌ Error aplicando unidad inicial: {ex}")

    return wrapper


def abrir_dialogo_offset_pliego(
    page,
    textfield_offset_trazado_x,
    textfield_offset_trazado_y,
    actualizar_trazado_func,
):
    """
    Abre un diálogo modal para editar los offsets del trazado (pliego) usando page.show_dialog().
    """
    print("[DEBUG DIALOG] abrir_dialogo_offset_pliego (page.open) llamado")

    try:
        # Obtener unidad actual para labels y conversión
        unit = _estado_impo_ui.get("unit", _initial_unit_pref)
        unit_label = get_unit_abbr(unit)

        # Crear nuevos TextFields para el diálogo con estilo completo
        tf_x = ft.TextField(
            label=t("Offset H ({0})").format(unit_label),
            value=textfield_offset_trazado_x.value,
            width=120,
            height=48,
            text_size=16,
            content_padding=5,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
            color=TEXTOS_FASE_1_COLOR,
            border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)),
            text_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
            label_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
        )
        tf_y = ft.TextField(
            label=t("Offset V ({0})").format(unit_label),
            value=textfield_offset_trazado_y.value,
            width=120,
            height=48,
            text_size=16,
            content_padding=5,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
            color=TEXTOS_FASE_1_COLOR,
            border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)),
            text_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
            label_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
        )

        def cerrar_dialogo(e):
            print("[DEBUG DIALOG] Cerrando diálogo pliego")
            page.pop_dialog()

        def aceptar_cambios(e):
            print("[DEBUG DIALOG] Aceptando cambios diálogo pliego")
            global USER_OFFSET_TRAZADO_X_MM, USER_OFFSET_TRAZADO_Y_MM
            try:
                # Convertir valores del usuario de la unidad seleccionada a mm para las variables globales
                unit = _estado_impo_ui.get("unit", _initial_unit_pref)
                # Usar parser seguro que acepta coma o punto
                vx = (
                    _safe_float_from_str(tf_x.value)
                    if tf_x and getattr(tf_x, "value", None) is not None
                    else 0.0
                )
                vy = (
                    _safe_float_from_str(tf_y.value)
                    if tf_y and getattr(tf_y, "value", None) is not None
                    else 0.0
                )
                USER_OFFSET_TRAZADO_X_MM = convert_to_mm(vx, unit)
                USER_OFFSET_TRAZADO_Y_MM = convert_to_mm(vy, unit)

                # Actualizar valores de los textfields originales (manteniendo la unidad actual)
                # Formatear a 2 decimales para consistencia visual
                try:
                    textfield_offset_trazado_x.value = f"{vx:.2f}"
                except Exception:
                    textfield_offset_trazado_x.value = str(tf_x.value)
                try:
                    textfield_offset_trazado_y.value = f"{vy:.2f}"
                except Exception:
                    textfield_offset_trazado_y.value = str(tf_y.value)
            except ValueError as ve:
                print(f"[DEBUG DIALOG] Error valor numérico: {ve}")
                pass

            # Guardar estado y marcar como modificado
            guardar_estado_impo_ui()
            if _mark_modified_callback:
                _mark_modified_callback()

            page.pop_dialog()
            actualizar_trazado_func(None)

        content = ft.Column(
            [
                # Texto eliminado por redundante
                ft.Row([tf_x, tf_y], spacing=10, alignment=ft.MainAxisAlignment.CENTER),
            ],
            tight=True,
            spacing=10,
        )

        dlg_modal = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                [ft.Text(t("Offset Pliego"), color=TEXTOS_FASE_1_COLOR)],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            content=content,
            actions=[
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Button(
                                t("Cancelar"),
                                width=110,
                                bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                                on_click=cerrar_dialogo,
                                style=ft.ButtonStyle(
                                    color={
                                        ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                                        "hovered": BOTONES_GENERICOS_HOVER_COLOR,
                                    },
                                    overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                                    padding=ft.Padding(0, 0, 0, 0),
                                    shape=ft.RoundedRectangleBorder(radius=10),
                                ),
                            ),
                            ft.Button(
                                t("Aceptar"),
                                width=110,
                                bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                                on_click=aceptar_cambios,
                                style=ft.ButtonStyle(
                                    color={
                                        ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                                        "hovered": BOTONES_GENERICOS_HOVER_COLOR,
                                    },
                                    overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                                    padding=ft.Padding(0, 0, 0, 0),
                                    shape=ft.RoundedRectangleBorder(radius=10),
                                ),
                            ),
                        ],
                        spacing=10,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    alignment=ft.Alignment.CENTER,
                    width=350,
                )
            ],
            actions_alignment=ft.MainAxisAlignment.CENTER,
            bgcolor=FONDO_ALERT_DIALOG,
        )

        page.show_dialog(dlg_modal)
        print("[DEBUG DIALOG] page.show_dialog(dlg_modal) llamado para pliego")
    except Exception as e:
        print(f"[DEBUG DIALOG] Error en abrir_dialogo_offset_pliego: {e}")


# Función combinada `abrir_dialogo_offsets` eliminada: usar `abrir_dialogo_offset_pliego`
# y `abrir_dialogo_offset_pdfs` (se mantuvieron las funciones específicas).


def abrir_dialogo_offset_pdfs(
    page, textfield_offset_img_x, textfield_offset_img_y, actualizar_trazado_func
):
    """
    Abre un diálogo modal para editar los offsets de las imágenes (PDFs) usando page.show_dialog().
    """
    print("[DEBUG DIALOG] abrir_dialogo_offset_pdfs (page.open) llamado")

    try:
        # Obtener unidad actual para labels y conversión
        unit = _estado_impo_ui.get("unit", _initial_unit_pref)
        unit_label = get_unit_abbr(unit)

        tf_x = ft.TextField(
            label=t("Offset H ({0})").format(unit_label),
            value=textfield_offset_img_x.value,
            width=120,
            height=48,
            text_size=16,
            content_padding=5,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
            color=TEXTOS_FASE_1_COLOR,
            border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)),
            text_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
            label_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
        )
        tf_y = ft.TextField(
            label=t("Offset V ({0})").format(unit_label),
            value=textfield_offset_img_y.value,
            width=120,
            height=48,
            text_size=16,
            content_padding=5,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
            color=TEXTOS_FASE_1_COLOR,
            border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)),
            text_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
            label_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
        )

        def cerrar_dialogo(e):
            print("[DEBUG DIALOG] Cerrando diálogo PDFs")
            page.pop_dialog()

        def aceptar_cambios(e):
            print("[DEBUG DIALOG] Aceptando cambios diálogo PDFs")
            global USER_OFFSET_IMAGEN_X_MM, USER_OFFSET_IMAGEN_Y_MM
            try:
                # Convertir valores del usuario de la unidad seleccionada a mm para las variables globales
                unit = _estado_impo_ui.get("unit", _initial_unit_pref)
                vx = (
                    _safe_float_from_str(tf_x.value)
                    if tf_x and getattr(tf_x, "value", None) is not None
                    else 0.0
                )
                vy = (
                    _safe_float_from_str(tf_y.value)
                    if tf_y and getattr(tf_y, "value", None) is not None
                    else 0.0
                )
                USER_OFFSET_IMAGEN_X_MM = convert_to_mm(vx, unit)
                USER_OFFSET_IMAGEN_Y_MM = convert_to_mm(vy, unit)

                # Actualizar valores de los textfields originales (manteniendo la unidad actual)
                try:
                    textfield_offset_img_x.value = f"{vx:.2f}"
                except Exception:
                    textfield_offset_img_x.value = str(tf_x.value)
                try:
                    textfield_offset_img_y.value = f"{vy:.2f}"
                except Exception:
                    textfield_offset_img_y.value = str(tf_y.value)
            except ValueError as ve:
                print(f"[DEBUG DIALOG] Error valor numérico: {ve}")
                pass

            # Guardar estado y marcar como modificado
            guardar_estado_impo_ui()
            if _mark_modified_callback:
                _mark_modified_callback()

            page.pop_dialog()
            actualizar_trazado_func(None)

        content = ft.Column(
            [
                # Texto eliminado por redundante
                ft.Row([tf_x, tf_y], spacing=10, alignment=ft.MainAxisAlignment.CENTER),
            ],
            tight=True,
            spacing=10,
        )

        dlg_modal = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                [ft.Text(t("Offset páginas"), color=TEXTOS_FASE_1_COLOR)],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            content=content,
            actions=[
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Button(
                                t("Cancelar"),
                                width=110,
                                bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                                on_click=cerrar_dialogo,
                                style=ft.ButtonStyle(
                                    color={
                                        ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                                        "hovered": BOTONES_GENERICOS_HOVER_COLOR,
                                    },
                                    overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                                    padding=ft.Padding(0, 0, 0, 0),
                                    shape=ft.RoundedRectangleBorder(radius=10),
                                ),
                            ),
                            ft.Button(
                                t("Aceptar"),
                                width=110,
                                bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                                on_click=aceptar_cambios,
                                style=ft.ButtonStyle(
                                    color={
                                        ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                                        "hovered": BOTONES_GENERICOS_HOVER_COLOR,
                                    },
                                    overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                                    padding=ft.Padding(0, 0, 0, 0),
                                    shape=ft.RoundedRectangleBorder(radius=10),
                                ),
                            ),
                        ],
                        spacing=10,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    alignment=ft.Alignment.CENTER,
                    width=300,
                )
            ],
            actions_alignment=ft.MainAxisAlignment.CENTER,
            bgcolor=FONDO_ALERT_DIALOG,
        )

        page.show_dialog(dlg_modal)
        print("[DEBUG DIALOG] page.show_dialog(dlg_modal) llamado para PDFs")
    except Exception as e:
        print(f"[DEBUG DIALOG] Error en abrir_dialogo_offset_pdfs: {e}")


def abrir_dialogo_cruces(page, actualizar_trazado_func):
    """
    Abre un diálogo modal para editar los parámetros de las cruces.
    """
    print("[DEBUG DIALOG] abrir_dialogo_cruces (page.open) llamado")

    try:
        # ═══════════════════════════════════════════════════════════
        # SECCIÓN 1: CRUCES DE CORTE
        # ═══════════════════════════════════════════════════════════
        # Usar la unidad actual para etiquetas/valores (presentación)
        current_unit = _estado_impo_ui.get("unit", _initial_unit_pref) or "mm"
        unit_label = get_unit_abbr(current_unit)

        tf_largo = ft.TextField(
            label=t("Longitud ({0})").format(unit_label),
            value=f"{convert_from_mm(float(LONGITUD_CRUZ_MM), current_unit):.2f}",
            width=120,
            height=48,
            text_size=16,
            content_padding=5,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
            color=TEXTOS_FASE_1_COLOR,
            border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)),
            text_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
            label_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
        )
        # El grosor siempre se muestra/edita en puntos y su etiqueta no cambia
        tf_grosor = ft.TextField(
            label=t("Grosor Pt."),
            value=str(GROSOR_CRUZ_PT),
            width=120,
            height=48,
            text_size=16,
            content_padding=5,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
            color=TEXTOS_FASE_1_COLOR,
            border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)),
            text_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
            label_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
        )
        tf_offset = ft.TextField(
            label=t("Offset ({0})").format(unit_label),
            value=f"{convert_from_mm(float(OFFSET_CRUZ_MM), current_unit):.2f}",
            width=120,
            height=48,
            text_size=16,
            content_padding=5,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
            color=TEXTOS_FASE_1_COLOR,
            border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)),
            text_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
            label_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
        )

        # Checkbox Auto Sangre
        checkbox_auto_sangre = ft.Checkbox(
            label=t("Auto sangre"),
            value=AUTO_SANGRE_OFFSET_CRUZ,
            label_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
            fill_color=BOTONES_GENERICOS_FONDO_COLOR,
        )

        # ═══════════════════════════════════════════════════════════
        # SECCIÓN 2: MARCAS MEDIANALES INTERNAS
        # ═══════════════════════════════════════════════════════════
        tf_offset_seguridad = ft.TextField(
            label=t("Margen seguridad ({0})").format(unit_label),
            value=f"{convert_from_mm(float(OFFSET_SEGURIDAD_MM), current_unit):.2f}",
            width=160,
            height=48,
            text_size=16,
            content_padding=5,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
            color=TEXTOS_FASE_1_COLOR,
            border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)),
            text_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
            label_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
        )

        tf_longitud_brazo_max = ft.TextField(
            label=t("Longitud ({0})").format(unit_label),
            value=f"{convert_from_mm(float(LONGITUD_BRAZO_MAX_MM), current_unit):.2f}",
            width=160,
            height=48,
            text_size=16,
            content_padding=5,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
            color=TEXTOS_FASE_1_COLOR,
            border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)),
            text_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
            label_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
        )

        def cerrar_dialogo(e):
            print("[DEBUG DIALOG] Cerrando diálogo cruces")
            page.pop_dialog()

        def aceptar_cambios(e):
            print("[DEBUG DIALOG] Aceptando cambios diálogo cruces")
            global LONGITUD_CRUZ_MM, GROSOR_CRUZ_PT, OFFSET_CRUZ_MM, AUTO_SANGRE_OFFSET_CRUZ
            global OFFSET_SEGURIDAD_MM, LONGITUD_BRAZO_MAX_MM  # ✨ NUEVO
            try:
                # Unidad actual para parseo (los TextFields muestran la unidad seleccionada)
                unit_for_parse = _estado_impo_ui.get("unit", _initial_unit_pref) or "mm"

                # Actualizar globales de cruces (convertir desde la unidad de la UI a mm)
                v_largo = _safe_float_from_str(tf_largo.value)
                if v_largo is not None:
                    LONGITUD_CRUZ_MM = convert_to_mm(v_largo, unit_for_parse)

                g = _safe_float_from_str(tf_grosor.value)
                if g is not None:
                    # Grosor se mantiene en puntos (sin conversión)
                    GROSOR_CRUZ_PT = g

                v_offset = _safe_float_from_str(tf_offset.value)
                if v_offset is not None:
                    OFFSET_CRUZ_MM = convert_to_mm(v_offset, unit_for_parse)

                AUTO_SANGRE_OFFSET_CRUZ = checkbox_auto_sangre.value

                # ✨ Actualizar globales de marcas medianales (convertir a mm)
                v_seg = _safe_float_from_str(tf_offset_seguridad.value)
                if v_seg is not None:
                    OFFSET_SEGURIDAD_MM = convert_to_mm(v_seg, unit_for_parse)

                v_brazo = _safe_float_from_str(tf_longitud_brazo_max.value)
                if v_brazo is not None:
                    LONGITUD_BRAZO_MAX_MM = convert_to_mm(v_brazo, unit_for_parse)

                # YA NO SE ACTUALIZAN TEXTFIELDS
            except Exception as ve:
                print(f"[DEBUG DIALOG] Error valor numérico o conversión: {ve}")
                pass

            # Guardar estado y marcar como modificado
            guardar_estado_impo_ui()
            if _mark_modified_callback:
                _mark_modified_callback()

            page.pop_dialog()
            actualizar_trazado_func(None)

        content = ft.Container(
            content=ft.Column(
                [
                    # Sección Cruces de Corte: título alineado a la izquierda
                    # respecto al inicio del Row interno; bloque centrado.
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Column(
                                    [
                                        ft.Text(
                                            t("Cruces de Corte"),
                                            size=14,
                                            weight=ft.FontWeight.BOLD,
                                            color=TEXTOS_FASE_1_COLOR,
                                        ),
                                        ft.Container(height=5),
                                        ft.Row(
                                            [tf_largo, tf_grosor, tf_offset],
                                            spacing=10,
                                            alignment=ft.MainAxisAlignment.CENTER,
                                        ),
                                    ],
                                    tight=True,
                                    spacing=6,
                                    alignment=ft.MainAxisAlignment.START,
                                )
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                        ),
                        height=80,
                    ),
                    ft.Container(height=5),  # Espaciado pequeño
                    ft.Row(
                        [checkbox_auto_sangre], alignment=ft.MainAxisAlignment.CENTER
                    ),
                    # Separador
                    ft.Container(height=10),
                    ft.Divider(height=1, color=BORDE_TEXTFIELDS_COLOR),
                    ft.Container(height=10),
                    # Sección Marcas Medianales Internas: mismo patrón visual
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Column(
                                    [
                                        ft.Text(
                                            t("Marcas Medianales Internas"),
                                            size=14,
                                            weight=ft.FontWeight.BOLD,
                                            color=TEXTOS_FASE_1_COLOR,
                                        ),
                                        ft.Container(height=5),
                                        ft.Row(
                                            [
                                                tf_offset_seguridad,
                                                tf_longitud_brazo_max,
                                            ],
                                            spacing=10,
                                            alignment=ft.MainAxisAlignment.CENTER,
                                        ),
                                    ],
                                    tight=True,
                                    spacing=6,
                                    alignment=ft.MainAxisAlignment.START,
                                )
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                        ),
                        height=80,
                    ),
                    ft.Container(height=30),
                    # Botones centrados dentro del contenido para asegurar centrado real
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Button(
                                    t("Cancelar"),
                                    width=110,
                                    bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                                    on_click=cerrar_dialogo,
                                    style=ft.ButtonStyle(
                                        color={
                                            ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                                            "hovered": BOTONES_GENERICOS_HOVER_COLOR,
                                        },
                                        overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                                        padding=ft.Padding(0, 0, 0, 0),
                                        shape=ft.RoundedRectangleBorder(radius=10),
                                    ),
                                ),
                                ft.Button(
                                    t("Aceptar"),
                                    width=110,
                                    bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                                    on_click=aceptar_cambios,
                                    style=ft.ButtonStyle(
                                        color={
                                            ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                                            "hovered": BOTONES_GENERICOS_HOVER_COLOR,
                                        },
                                        overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                                        padding=ft.Padding(0, 0, 0, 0),
                                        shape=ft.RoundedRectangleBorder(radius=10),
                                    ),
                                ),
                            ],
                            spacing=10,
                            alignment=ft.MainAxisAlignment.CENTER,
                        ),
                        alignment=ft.Alignment.CENTER,
                        width=380,
                    ),
                ],
                tight=True,
                spacing=10,
            ),
            width=410,
            height=350,
            padding=ft.Padding(10, 0, 10, 0),
        )

        dlg_modal = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                [
                    ft.Text(
                        t("Configuración Cruces y Marcas"), color=TEXTOS_FASE_1_COLOR
                    )
                ],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            content=content,
            actions=[],
            bgcolor=FONDO_ALERT_DIALOG,
        )

        page.show_dialog(dlg_modal)
        print("[DEBUG DIALOG] page.show_dialog(dlg_modal) llamado para cruces")
    except Exception as e:
        print(f"[DEBUG DIALOG] Error en abrir_dialogo_cruces: {e}")


def abrir_dialogo_marcas_texto(
    page, actualizar_trazado_func, zoom_level, user_changed_zoom
):
    """
    Abre un diálogo modal para configurar las marcas de texto.
    """
    print("[DEBUG DIALOG] abrir_dialogo_marcas_texto llamado")

    try:
        # Variables para los botones de posición
        posiciones = {
            "SUP_IZQ": MARCA_TEXTO_POS_SUP_IZQ,
            "CENTRO_SUP": MARCA_TEXTO_POS_CENTRO_SUP,
            "SUP_DER": MARCA_TEXTO_POS_SUP_DER,
            "LAT_IZQ": MARCA_TEXTO_POS_CENTRO_LAT_IZQ,
            "LAT_DER": MARCA_TEXTO_POS_CENTRO_LAT_DER,
            "INF_IZQ": MARCA_TEXTO_POS_INF_IZQ,
            "CENTRO_INF": MARCA_TEXTO_POS_CENTRO_INF,
            "INF_DER": MARCA_TEXTO_POS_INF_DER,
        }

        # Botones de posición (comportamiento radio button)
        botones_pos = {}
        posicion_activa_actual = [
            None
        ]  # Lista para permitir modificación en función anidada

        # Determinar posición inicial activa
        for nombre, activo in posiciones.items():
            if activo:
                posicion_activa_actual[0] = nombre
                break

        def crear_boton_posicion(nombre, icono):
            activo = posiciones[nombre]
            btn = ft.Button(
                content=ft.Icon(icono, size=20),
                width=60,
                height=60,
                bgcolor=(
                    BOTONES_GENERICOS_FONDO_COLOR if activo else FONDO_TEXTFIELDS_COLOR
                ),
                style=ft.ButtonStyle(
                    color={
                        ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR if activo else TEXTOS_FASE_1_COLOR,
                    },
                    shape=ft.RoundedRectangleBorder(radius=6),
                ),
                data=nombre,
                on_click=lambda e: seleccionar_posicion(e.control.data),
            )
            botones_pos[nombre] = btn
            return btn

        def seleccionar_posicion(nombre):
            # Desactivar todos
            for key, btn in botones_pos.items():
                btn.bgcolor = FONDO_TEXTFIELDS_COLOR
                btn.style.color = {ft.ControlState.DEFAULT: TEXTOS_FASE_1_COLOR}
                btn.update()
            # Activar el seleccionado
            botones_pos[nombre].bgcolor = BOTONES_GENERICOS_FONDO_COLOR
            botones_pos[nombre].style.color = {ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR}
            botones_pos[nombre].update()
            # Actualizar variable de estado
            posicion_activa_actual[0] = nombre

        # Grid 3x3 de posición
        grid_posicion = ft.Column(
            [
                ft.Row(
                    [
                        crear_boton_posicion("SUP_IZQ", ft.Icons.NORTH_WEST),
                        crear_boton_posicion("CENTRO_SUP", ft.Icons.NORTH),
                        crear_boton_posicion("SUP_DER", ft.Icons.NORTH_EAST),
                    ],
                    spacing=5,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                ft.Row(
                    [
                        crear_boton_posicion("LAT_IZQ", ft.Icons.WEST),
                        ft.Container(width=60, height=60),  # Centro vacío
                        crear_boton_posicion("LAT_DER", ft.Icons.EAST),
                    ],
                    spacing=5,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                ft.Row(
                    [
                        crear_boton_posicion("INF_IZQ", ft.Icons.SOUTH_WEST),
                        crear_boton_posicion("CENTRO_INF", ft.Icons.SOUTH),
                        crear_boton_posicion("INF_DER", ft.Icons.SOUTH_EAST),
                    ],
                    spacing=5,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
            ],
            spacing=5,
        )

        # Obtener unidad actual para labels/valores
        current_unit = _estado_impo_ui.get("unit", _initial_unit_pref) or "mm"
        unit_label = get_unit_abbr(current_unit)

        # Dropdown de rotación
        dd_rotacion = ft.Dropdown(
            label=t("Rotación"),
            value=str(MARCA_TEXTO_ROTACION),
            options=[
                ft.dropdown.Option("0", "0°"),
                ft.dropdown.Option("90", "90°"),
                ft.dropdown.Option("180", "180°"),
                ft.dropdown.Option("270", "270°"),
            ],
            width=120,
            text_size=16,
            content_padding=ft.Padding(8, 0, 0, 0),
            border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR), border_radius=6),
            filled=True,
            fill_color=FONDO_TEXTFIELDS_COLOR,
            color=DROPDOWN_TEXT_STYLE_COLOR,
            bgcolor=DROPDOWN_FONDO_MENU_COLOR,
            label_style=ft.TextStyle(color=DROPDOWN_TEXT_STYLE_COLOR),
            trailing_icon=ft.Icon(
                ft.Icons.ARROW_DROP_DOWN, color=DROPDOWN_TRAILING_ICON_COLOR
            ),
            selected_trailing_icon=ft.Icon(
                ft.Icons.ARROW_DROP_UP, color=DROPDOWN_TRAILING_ICON_COLOR
            ),
        )
        # Nota: no envolver el Dropdown en un Container aquí — usar el Dropdown directo

        # TextFields de offset (presentación en la unidad seleccionada)
        tf_offset_h = ft.TextField(
            label=t("Offset H ({0})").format(unit_label),
            value=f"{convert_from_mm(float(MARCA_TEXTO_OFFSET_H_MM), current_unit):.2f}",
            width=120,
            height=48,
            text_size=16,
            content_padding=5,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
            color=TEXTOS_FASE_1_COLOR,
            border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)),
            text_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
            label_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
        )

        tf_offset_v = ft.TextField(
            label=t("Offset V ({0})").format(unit_label),
            value=f"{convert_from_mm(float(MARCA_TEXTO_OFFSET_V_MM), current_unit):.2f}",
            width=120,
            height=48,
            text_size=16,
            content_padding=5,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
            color=TEXTOS_FASE_1_COLOR,
            border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)),
            text_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
            label_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
        )

        # Dropdowns de fuente
        dd_familia = ft.Dropdown(
            label=t("Familia"),
            value=MARCA_TEXTO_FAMILIA,
            options=[
                ft.dropdown.Option("Arial"),
                ft.dropdown.Option("Times New Roman"),
                ft.dropdown.Option("Courier New"),
                ft.dropdown.Option("Helvetica"),
                ft.dropdown.Option("Verdana"),
                ft.dropdown.Option("Georgia"),
            ],
            width=205,
            text_size=16,
            content_padding=ft.Padding(8, 0, 0, 0),
            border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR), border_radius=6),
            filled=True,
            fill_color=FONDO_TEXTFIELDS_COLOR,
            color=DROPDOWN_TEXT_STYLE_COLOR,
            bgcolor=DROPDOWN_FONDO_MENU_COLOR,
            label_style=ft.TextStyle(color=DROPDOWN_TEXT_STYLE_COLOR),
            trailing_icon=ft.Icon(
                ft.Icons.ARROW_DROP_DOWN, color=DROPDOWN_TRAILING_ICON_COLOR
            ),
            selected_trailing_icon=ft.Icon(
                ft.Icons.ARROW_DROP_UP, color=DROPDOWN_TRAILING_ICON_COLOR
            ),
        )
        # Usar dd_familia directamente (no envolver en Container)

        dd_tipo = ft.Dropdown(
            label=t("Tipo"),
            value=MARCA_TEXTO_TIPO,
            options=[
                ft.dropdown.Option("Regular", t("Regular")),
                ft.dropdown.Option("Bold", t("Bold")),
                ft.dropdown.Option("Italic", t("Italic")),
                ft.dropdown.Option("Bold Italic", t("Bold Italic")),
            ],
            width=120,
            text_size=16,
            content_padding=ft.Padding(8, 0, 0, 0),
            border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR), border_radius=6),
            filled=True,
            fill_color=FONDO_TEXTFIELDS_COLOR,
            color=DROPDOWN_TEXT_STYLE_COLOR,
            bgcolor=DROPDOWN_FONDO_MENU_COLOR,
            label_style=ft.TextStyle(color=DROPDOWN_TEXT_STYLE_COLOR),
            trailing_icon=ft.Icon(
                ft.Icons.ARROW_DROP_DOWN, color=DROPDOWN_TRAILING_ICON_COLOR
            ),
            selected_trailing_icon=ft.Icon(
                ft.Icons.ARROW_DROP_UP, color=DROPDOWN_TRAILING_ICON_COLOR
            ),
        )
        # Usar dd_tipo directamente (no envolver en Container)

        tf_cuerpo = ft.TextField(
            label=t("Size point"),
            value=str(MARCA_TEXTO_CUERPO),
            width=90,
            height=48,
            text_size=16,
            content_padding=5,
            bgcolor=FONDO_TEXTFIELDS_COLOR,
            color=TEXTOS_FASE_1_COLOR,
            border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)),
            text_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
            label_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
        )

        def cerrar_dialogo(e):
            print("[DEBUG DIALOG] Cerrando diálogo marcas texto")
            page.pop_dialog()

        def aceptar_cambios(e):
            print("[DEBUG DIALOG] Aceptando cambios diálogo marcas texto")
            global MARCA_TEXTO_POS_SUP_IZQ, MARCA_TEXTO_POS_SUP_DER, MARCA_TEXTO_POS_INF_IZQ, MARCA_TEXTO_POS_INF_DER
            global MARCA_TEXTO_POS_CENTRO_SUP, MARCA_TEXTO_POS_CENTRO_INF, MARCA_TEXTO_POS_CENTRO_LAT_IZQ, MARCA_TEXTO_POS_CENTRO_LAT_DER
            global MARCA_TEXTO_ROTACION, MARCA_TEXTO_OFFSET_H_MM, MARCA_TEXTO_OFFSET_V_MM
            global MARCA_TEXTO_FAMILIA, MARCA_TEXTO_TIPO, MARCA_TEXTO_CUERPO

            try:
                # Usar la variable de estado en lugar de comparar colores
                posicion_activa = posicion_activa_actual[0]

                # Actualizar todas las posiciones (solo una en True)
                MARCA_TEXTO_POS_SUP_IZQ = posicion_activa == "SUP_IZQ"
                MARCA_TEXTO_POS_SUP_DER = posicion_activa == "SUP_DER"
                MARCA_TEXTO_POS_INF_IZQ = posicion_activa == "INF_IZQ"
                MARCA_TEXTO_POS_INF_DER = posicion_activa == "INF_DER"
                MARCA_TEXTO_POS_CENTRO_SUP = posicion_activa == "CENTRO_SUP"
                MARCA_TEXTO_POS_CENTRO_INF = posicion_activa == "CENTRO_INF"
                MARCA_TEXTO_POS_CENTRO_LAT_IZQ = posicion_activa == "LAT_IZQ"
                MARCA_TEXTO_POS_CENTRO_LAT_DER = posicion_activa == "LAT_DER"

                # Actualizar otros valores
                MARCA_TEXTO_ROTACION = int(dd_rotacion.value)
                # Offsets: parsear en unidad UI y convertir a mm
                unit_for_parse = _estado_impo_ui.get("unit", _initial_unit_pref) or "mm"
                v_off_h = _safe_float_from_str(tf_offset_h.value)
                v_off_v = _safe_float_from_str(tf_offset_v.value)
                if v_off_h is not None:
                    MARCA_TEXTO_OFFSET_H_MM = convert_to_mm(v_off_h, unit_for_parse)
                if v_off_v is not None:
                    MARCA_TEXTO_OFFSET_V_MM = convert_to_mm(v_off_v, unit_for_parse)
                MARCA_TEXTO_FAMILIA = dd_familia.value
                MARCA_TEXTO_TIPO = dd_tipo.value
                # Font size always stored/edited in points
                MARCA_TEXTO_CUERPO = int(tf_cuerpo.value)

            except ValueError as ve:
                print(f"[DEBUG DIALOG] Error valor numérico: {ve}")
                pass

            # Guardar estado y marcar como modificado
            guardar_estado_impo_ui()
            if _mark_modified_callback:
                _mark_modified_callback()

            page.pop_dialog()
            # Resetear zoom antes de actualizar trazado (como hace reset_zoom)
            zoom_level["value"] = 1.0
            user_changed_zoom["value"] = False
            print(f"🔄 RESET ZOOM (marcas texto): factor={zoom_level['value']:.3f}")
            actualizar_trazado_func(None)
            try:
                page.update()
            except Exception:
                pass

        content = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(
                                t("Posición"),
                                size=16,
                                color=TEXTOS_FASE_1_COLOR,
                                weight=ft.FontWeight.BOLD,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    grid_posicion,
                    ft.Container(height=10),
                    # Centrar el bloque de controles; dentro del bloque, el título
                    # se alinea a la izquierda respecto al inicio del Row de controles.
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Column(
                                    [
                                        ft.Text(
                                            t("Rotación y Offset"),
                                            size=16,
                                            color=TEXTOS_FASE_1_COLOR,
                                            weight=ft.FontWeight.BOLD,
                                        ),
                                        ft.Row(
                                            [dd_rotacion, tf_offset_h, tf_offset_v],
                                            spacing=10,
                                            alignment=ft.MainAxisAlignment.CENTER,
                                            vertical_alignment=ft.CrossAxisAlignment.END,
                                        ),
                                    ],
                                    tight=True,
                                    spacing=6,
                                    alignment=ft.MainAxisAlignment.START,
                                )
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                        ),
                        height=80,
                    ),
                    ft.Container(height=10),
                    # Centrar el bloque de controles 'Fuente' y alinear el texto
                    # a la izquierda respecto al inicio del Row interno.
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Column(
                                    [
                                        ft.Text(
                                            t("Fuente"),
                                            size=16,
                                            color=TEXTOS_FASE_1_COLOR,
                                            weight=ft.FontWeight.BOLD,
                                        ),
                                        ft.Row(
                                            [dd_familia, dd_tipo, tf_cuerpo],
                                            spacing=10,
                                            alignment=ft.MainAxisAlignment.CENTER,
                                            vertical_alignment=ft.CrossAxisAlignment.END,
                                        ),
                                    ],
                                    tight=True,
                                    spacing=6,
                                    alignment=ft.MainAxisAlignment.START,
                                )
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                        ),
                        height=80,
                    ),
                ],
                tight=True,
                spacing=10,
            ),
            width=450,
            padding=ft.Padding(10, 10, 10, 10),
        )

        dlg_modal = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                [ft.Text(t("Marcas de Texto"), color=TEXTOS_FASE_1_COLOR)],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            content=content,
            actions=[
                ft.Row(
                    [
                        ft.Button(
                            t("Cancelar"),
                            width=110,
                            bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                            on_click=cerrar_dialogo,
                            style=ft.ButtonStyle(
                                color={
                                    ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                                    "hovered": BOTONES_GENERICOS_HOVER_COLOR,
                                },
                                overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                                padding=ft.Padding(0, 0, 0, 0),
                                shape=ft.RoundedRectangleBorder(radius=10),
                            ),
                        ),
                        ft.Button(
                            t("Aceptar"),
                            width=110,
                            bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                            on_click=aceptar_cambios,
                            style=ft.ButtonStyle(
                                color={
                                    ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                                    "hovered": BOTONES_GENERICOS_HOVER_COLOR,
                                },
                                overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                                padding=ft.Padding(0, 0, 0, 0),
                                shape=ft.RoundedRectangleBorder(radius=10),
                            ),
                        ),
                    ],
                    spacing=10,
                    alignment=ft.MainAxisAlignment.CENTER,
                )
            ],
            actions_alignment=ft.MainAxisAlignment.CENTER,
            bgcolor=FONDO_ALERT_DIALOG,
        )

        page.show_dialog(dlg_modal)
        print("[DEBUG DIALOG] page.show_dialog(dlg_modal) llamado para marcas texto")
    except Exception as e:
        print(f"[DEBUG DIALOG] Error en abrir_dialogo_marcas_texto: {e}")


def actualizar_checkboxes_desde_estado():
    """
    Actualiza los checkboxes visuales desde _estado_impo_ui.
    Se debe llamar cuando se navega a la imposición con datos precargados.
    """
    # Printer local que se puede silenciar mediante DEBUG_CHECKBOXES
    debug_print = print if DEBUG_CHECKBOXES else (lambda *a, **k: None)

    debug_print(f"\n{'='*80}")
    debug_print(f"[ACTUALIZAR CHECKBOXES] ⚙️ FUNCIÓN LLAMADA")
    debug_print(f"{'='*80}")
    debug_print(f"[ACTUALIZAR CHECKBOXES] Estado existe: {_estado_impo_ui is not None}")

    if not _estado_impo_ui:
        debug_print(f"[ACTUALIZAR CHECKBOXES] ⚠️ No hay estado, saliendo")
        return

    debug_print(
        f"[ACTUALIZAR CHECKBOXES] Claves en estado: {list(_estado_impo_ui.keys())}"
    )
    debug_print(f"[ACTUALIZAR CHECKBOXES] Valores en estado:")

    # Buscar valores soportando múltiples nomenclaturas (archivo .tns, stamp minúsculas, stamp mayúsculas)
    cruces_val = _estado_impo_ui.get(
        "CHECK_BOX_CRUCES_Y_MARCAS",
        _estado_impo_ui.get("checkbox_cruces", _estado_impo_ui.get("CHECK_BOX_CRUCES")),
    )
    lineas_val = _estado_impo_ui.get(
        "CHECK_BOX_LINEAS_DE_CORTE",
        _estado_impo_ui.get(
            "checkbox_lineas_corte", _estado_impo_ui.get("CHECK_BOX_LINEAS_CORTE")
        ),
    )
    marcas_val = _estado_impo_ui.get(
        "CHECK_BOX_MARCAS_DE_TEXTO",
        _estado_impo_ui.get(
            "checkbox_marcas_texto", _estado_impo_ui.get("CHECK_BOX_MARCAS_TEXTO")
        ),
    )
    exterior_val = _estado_impo_ui.get(
        "CHECK_BOX_LINEA_EXTERIOR", _estado_impo_ui.get("checkbox_linea_exterior")
    )

    debug_print(f"   cruces: {cruces_val}")
    debug_print(f"   lineas_corte: {lineas_val}")
    debug_print(f"   marcas_texto: {marcas_val}")
    debug_print(f"   linea_exterior: {exterior_val}")
    debug_print(
        f"[STAMP CHECKS] checkbox_cruces.value={checkbox_cruces.value if checkbox_cruces else 'None'}"
    )
    debug_print(
        f"[STAMP CHECKS] checkbox_lineas_corte.value={checkbox_lineas_corte.value if checkbox_lineas_corte else 'None'}"
    )
    debug_print(
        f"[STAMP CHECKS] checkbox_marcas_texto.value={checkbox_marcas_texto.value if checkbox_marcas_texto else 'None'}"
    )
    debug_print(
        f"[STAMP CHECKS] checkbox_linea_exterior.value={checkbox_linea_exterior.value if checkbox_linea_exterior else 'None'}"
    )

    # CRÍTICO: Guardar eventos on_change originales para restaurarlos después
    eventos_originales = {}
    if checkbox_cruces is not None:
        eventos_originales["cruces"] = checkbox_cruces.on_change
        checkbox_cruces.on_change = None
    if checkbox_lineas_corte is not None:
        eventos_originales["lineas_corte"] = checkbox_lineas_corte.on_change
        checkbox_lineas_corte.on_change = None
    if checkbox_marcas_texto is not None:
        eventos_originales["marcas_texto"] = checkbox_marcas_texto.on_change
        checkbox_marcas_texto.on_change = None
    if checkbox_linea_exterior is not None:
        eventos_originales["linea_exterior"] = checkbox_linea_exterior.on_change
        checkbox_linea_exterior.on_change = None

    debug_print(
        f"[ACTUALIZAR CHECKBOXES] 🚫 Eventos on_change desactivados temporalmente"
    )

    try:
        # Restaurar valores encontrados
        if checkbox_cruces is not None and cruces_val is not None:
            checkbox_cruces.value = cruces_val
            debug_print(
                f"[ACTUALIZAR CHECKBOXES] ✅ checkbox_cruces.value = {checkbox_cruces.value}"
            )

        if checkbox_lineas_corte is not None and lineas_val is not None:
            checkbox_lineas_corte.value = lineas_val
            debug_print(
                f"[ACTUALIZAR CHECKBOXES] ✅ checkbox_lineas_corte.value = {checkbox_lineas_corte.value}"
            )

        if checkbox_marcas_texto is not None and marcas_val is not None:
            checkbox_marcas_texto.value = marcas_val
            debug_print(
                f"[ACTUALIZAR CHECKBOXES] ✅ checkbox_marcas_texto.value = {checkbox_marcas_texto.value}"
            )

        if checkbox_linea_exterior is not None and exterior_val is not None:
            checkbox_linea_exterior.value = exterior_val
            debug_print(
                f"[ACTUALIZAR CHECKBOXES] ✅ checkbox_linea_exterior.value = {checkbox_linea_exterior.value}"
            )

        # Solo imprimir valores finales si los checkboxes existen
        valores = []
        if checkbox_cruces is not None:
            valores.append(f"cruces={checkbox_cruces.value}")
        if checkbox_lineas_corte is not None:
            valores.append(f"lineas={checkbox_lineas_corte.value}")
        if checkbox_marcas_texto is not None:
            valores.append(f"marcas={checkbox_marcas_texto.value}")
        if checkbox_linea_exterior is not None:
            valores.append(f"exterior={checkbox_linea_exterior.value}")

        if valores:
            debug_print(
                f"[ACTUALIZAR CHECKBOXES] Valores finales: {', '.join(valores)}"
            )
        else:
            debug_print(f"[ACTUALIZAR CHECKBOXES] ⚠️ Ningún checkbox está creado aún")

        # Actualizar visualmente solo los que existen (proteger si no están añadidos a la página)
        def _safe_update(ctrl, name):
            try:
                if ctrl is not None:
                    ctrl.update()
                    debug_print(f"[ACTUALIZAR CHECKBOXES] ✅ {name} updated")
            except AssertionError as ae:
                debug_print(
                    f"[ACTUALIZAR CHECKBOXES] ⚠️ {name} no agregado a la página aún (skip update): {ae}"
                )
            except Exception as ex:
                debug_print(
                    f"[ACTUALIZAR CHECKBOXES] ❌ Error actualizando {name}: {ex}"
                )

        _safe_update(checkbox_cruces, "checkbox_cruces")
        _safe_update(checkbox_lineas_corte, "checkbox_lineas_corte")
        _safe_update(checkbox_marcas_texto, "checkbox_marcas_texto")
        _safe_update(checkbox_linea_exterior, "checkbox_linea_exterior")
        debug_print(f"[ACTUALIZAR CHECKBOXES] ✅ Intento de actualización finalizado")
    except Exception as ex:
        debug_print(f"[ACTUALIZAR CHECKBOXES] ❌ Error: {ex}")
        import traceback

    finally:
        # CRÍTICO: Restaurar eventos on_change
        if checkbox_cruces is not None and "cruces" in eventos_originales:
            checkbox_cruces.on_change = eventos_originales["cruces"]
        if checkbox_lineas_corte is not None and "lineas_corte" in eventos_originales:
            checkbox_lineas_corte.on_change = eventos_originales["lineas_corte"]
        if checkbox_marcas_texto is not None and "marcas_texto" in eventos_originales:
            checkbox_marcas_texto.on_change = eventos_originales["marcas_texto"]
        if (
            checkbox_linea_exterior is not None
            and "linea_exterior" in eventos_originales
        ):
            checkbox_linea_exterior.on_change = eventos_originales["linea_exterior"]
        debug_print(f"[ACTUALIZAR CHECKBOXES] ✅ Eventos on_change restaurados")
