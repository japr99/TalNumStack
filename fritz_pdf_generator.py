"""
Generador de PDF de Imposicion con PyMuPDF (Fritz)
Crea PDFs de imposicion usando plantillas reutilizables y show_pdf_page()

SISTEMA DE CAPAS:
================
1. Capa 5 - Pliego (fondo)
2. Capa 4 - Trazado (grid de celdas)
3. Capa 3 - Cruces (cruces de registro)
4. Capa 2 - Marcas Exteriores
5. Capa 1 - Marcas Medianales
6. Capa 0 - Texto (informacion del pliego)
7. Imagenes del PDF (insertadas en celdas)

La plantilla se crea UNA VEZ y se reutiliza para todos los pliegos.
Solo cambia la capa de texto y las paginas insertadas.
"""

import fitz
import os
import shutil
import unicodedata
import logging
from typing import Dict, List, Optional, Callable
from lang import t
from talnum_preferences import get_config_dir

# Silenciar prints de depuración en este módulo por defecto.
# Para activar, cambiar _PRINT_DEBUG = True durante desarrollo.
_PRINT_DEBUG = False
if not _PRINT_DEBUG:

    def _no_print(*args, **kwargs):
        return None

    print = _no_print

logger = logging.getLogger(__name__)

# Constantes de conversion
MM_TO_PT = 1.0 / 0.352777778
PT_TO_MM = 0.352777778


def mm_to_pt(mm: float) -> float:
    """Convierte milimetros a puntos"""
    return mm * MM_TO_PT


def pt_to_mm(pt: float) -> float:
    """Convierte puntos a milimetros"""
    return pt * PT_TO_MM


def _map_font_name(font_name: str) -> str:
    """
    Mapea nombres comunes de fuente a identificadores que PyMuPDF entiende
    (intenta usar nombres base, si no devuelve el nombre tal cual).
    """
    normalized = font_name.lower().replace(" ", "-")
    base_fonts = {
        "helvetica": "helv",
        "times": "tiro",
        "times-roman": "tiro",
        "courier": "cour",
        "symbol": "symb",
        "zapfdingbats": "zadb",
    }
    return base_fonts.get(normalized, font_name)


# Caché global de fuentes para evitar busquedas/registro repetidos.
# Clave: nombre completo pedido (p.ej. 'Arial Bold') -> {'path': <fontfile>, 'alias': <safe_alias>}
_FONT_CACHE: Dict[str, Dict[str, str]] = {}


def _find_system_font_file(font_name: str) -> Optional[str]:
    """
    Busca un archivo de fuente en rutas típicas del sistema (macOS/Win/Linux).
    Devuelve la primera coincidencia razonable o None.

    ESTRATEGIA:
    1. Mapeo directo de nombres comunes a rutas conocidas (máxima prioridad)
    2. Búsqueda de coincidencia exacta en nombre de archivo
    3. Búsqueda de coincidencia que comienza con el nombre
    4. Fallback a búsqueda contenida (última opción)
    """
    import sys
    from pathlib import Path

    # ============================================================================
    # PASO 1: MAPEO DIRECTO (previene confusiones como Georgia vs SFGeorgian)
    # ============================================================================
    # Mapeo de nombres comunes a rutas conocidas por sistema operativo
    KNOWN_FONTS_MACOS = {
        "georgia": "/Library/Fonts/Georgia.ttf",
        "georgiabold": "/Library/Fonts/Georgia Bold.ttf",
        "georgiaitalic": "/Library/Fonts/Georgia Italic.ttf",
        "georgiabolditalic": "/Library/Fonts/Georgia Bold Italic.ttf",
        "arial": "/System/Library/Fonts/Supplemental/Arial.ttf",
        "arialbold": "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "arialitalic": "/System/Library/Fonts/Supplemental/Arial Italic.ttf",
        "arialblack": "/System/Library/Fonts/Supplemental/Arial Black.ttf",
        "timesnewroman": "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
        "courier": "/System/Library/Fonts/Courier.ttc",
        "couriernew": "/System/Library/Fonts/Supplemental/Courier New.ttf",
        "verdana": "/System/Library/Fonts/Supplemental/Verdana.ttf",
        "trebuchet": "/System/Library/Fonts/Supplemental/Trebuchet MS.ttf",
        "comicsans": "/System/Library/Fonts/Supplemental/Comic Sans MS.ttf",
        "impact": "/System/Library/Fonts/Supplemental/Impact.ttf",
    }

    KNOWN_FONTS_WINDOWS = {
        "georgia": "Georgia.ttf",
        "georgiabold": "Georgiab.ttf",
        "georgiaitalic": "Georgiai.ttf",
        "georgiabolditalic": "Georgiaz.ttf",
        "arial": "Arial.ttf",
        "arialbold": "Arialbd.ttf",
        "arialitalic": "Ariali.ttf",
        "arialblack": "Ariblk.ttf",
        "timesnewroman": "Times.ttf",
        "courier": "Cour.ttf",
        "couriernew": "Cour.ttf",
        "verdana": "Verdana.ttf",
        "trebuchet": "Trebuc.ttf",
        "comicsans": "Comic.ttf",
        "impact": "Impact.ttf",
    }

    # Normalizar nombre de búsqueda
    target_normalized = font_name.lower().replace(" ", "").replace("-", "")

    # Intentar mapeo directo
    if sys.platform == "darwin":
        if target_normalized in KNOWN_FONTS_MACOS:
            known_path = Path(KNOWN_FONTS_MACOS[target_normalized])
            if known_path.exists():
                return str(known_path)
    elif sys.platform == "win32":
        if target_normalized in KNOWN_FONTS_WINDOWS:
            windir = os.environ.get("WINDIR", "C:/Windows")
            known_path = Path(windir) / "Fonts" / KNOWN_FONTS_WINDOWS[target_normalized]
            if known_path.exists():
                return str(known_path)

    # ============================================================================
    # PASO 2: BÚSQUEDA EN CARPETAS DEL SISTEMA
    # ============================================================================
    candidates = []
    if sys.platform == "darwin":
        candidates = [
            Path("/Library/Fonts"),  # Prioridad a /Library/Fonts (fuentes estándar)
            Path("/System/Library/Fonts/Supplemental"),
            Path("/System/Library/Fonts"),
            Path.home() / "Library/Fonts",
        ]
    elif sys.platform == "win32":
        candidates = [Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"]
    else:
        candidates = [
            Path.home() / ".local/share/fonts",
            Path.home() / ".fonts",
            Path("/usr/share/fonts"),
            Path("/usr/local/share/fonts"),
        ]

    target = font_name.lower().replace(" ", "").replace("-", "")
    exts = (".ttf", ".otf", ".ttc")

    exact_match = None
    best_match = None
    fallback_match = None

    for folder in candidates:
        try:
            if not folder.exists():
                continue
            for fn in folder.iterdir():
                if not fn.suffix.lower() in exts:
                    continue
                fname = fn.stem.lower().replace(" ", "").replace("-", "")

                # 1. Coincidencia EXACTA (máxima prioridad)
                if fname == target:
                    exact_match = str(fn)
                    break

                # 2. Coincidencia que COMIENZA con el target
                # Evita que "georgia" haga match con "sfgeorgian"
                if fname.startswith(target):
                    is_variant = any(
                        v in fname
                        for v in (
                            "bold",
                            "italic",
                            "oblique",
                            "light",
                            "black",
                            "thin",
                            "extrabold",
                        )
                    )
                    target_is_variant = any(
                        v in target for v in ("bold", "italic", "oblique")
                    )
                    if not is_variant or target_is_variant:
                        if not best_match:
                            best_match = str(fn)
                    else:
                        if not fallback_match:
                            fallback_match = str(fn)

                # 3. Coincidencia CONTIENE (solo si no hay mejores opciones)
                elif target in fname and not best_match:
                    is_variant = any(
                        v in fname
                        for v in (
                            "bold",
                            "italic",
                            "oblique",
                            "light",
                            "black",
                            "thin",
                            "extrabold",
                        )
                    )
                    target_is_variant = any(
                        v in target for v in ("bold", "italic", "oblique")
                    )
                    if not is_variant or target_is_variant:
                        if not fallback_match:
                            fallback_match = str(fn)

            if exact_match:
                break
            if best_match:
                break
        except Exception:
            continue

    return exact_match or best_match or fallback_match


def sugerir_nombre_salida(
    pdf_ordenado_path: Optional[str] = None,
    archivo_seleccionado: Optional[Dict] = None,
    pref_nombre_personalizado: Optional[bool] = None,
    pref_filename: Optional[str] = None,
) -> str:
    """Devuelve un nombre de archivo sugerido para la exportación de imposición.

    La lógica aplica el siguiente orden de preferencia:
    1. Si `pref_nombre_personalizado` es True y `pref_filename` existe, usarlo.
    2. Si `archivo_seleccionado` contiene un nombre, usarlo (limpiando sufijos temporales).
    3. Derivar el nombre del `pdf_ordenado_path` (sin sufijos temporales).
    4. Fallback a 'imposicion_output.pdf'.
    """
    try:
        sugerido = None
        if pref_nombre_personalizado and pref_filename:
            sugerido = pref_filename

        if (
            not sugerido
            and archivo_seleccionado
            and isinstance(archivo_seleccionado, dict)
        ):
            nombre_arch = archivo_seleccionado.get(
                "nombre"
            ) or archivo_seleccionado.get("nombre_archivo")
            if nombre_arch:
                sugerido = nombre_arch

        if not sugerido and pdf_ordenado_path:
            try:
                base = os.path.basename(pdf_ordenado_path)
                name, ext = os.path.splitext(base)
                for suf in ("_ordenado_temp", "_ordenado", "_temp"):
                    if name.endswith(suf):
                        name = name[: -len(suf)]
                        break
                sugerido = (name + (ext or ".pdf")).strip()
            except Exception:
                sugerido = None

        if not sugerido:
            sugerido = pref_filename or "imposicion_output.pdf"

        if not str(sugerido).lower().endswith(".pdf"):
            sugerido = str(sugerido) + ".pdf"

        # Si no se está usando un nombre personalizado, añadir sufijo _TNS
        try:
            if not pref_nombre_personalizado:
                name, ext = os.path.splitext(str(sugerido))
                if not name.endswith("_TNS"):
                    sugerido = f"{name}_TNS{ext or '.pdf'}"
        except Exception:
            pass

        return sugerido
    except Exception:
        return "imposicion_output.pdf"


def crear_plantilla_trazado(
    json_trazado: Dict,
    pdf_ordenado_path: str,
    tipo_plantilla: str = "CARA",
    incluir_marcas_corte: bool = True,
) -> fitz.Page:
    """
    Crea una pagina de plantilla con el trazado completo usando OCGs (Capas).
    Se basa en el diccionario 'capas' para los offsets de cada grupo.
    """
    # print(f"\n{'='*80}")
    # print(f"CREANDO PLANTILLA {tipo_plantilla} (Multicapa)")
    # print(f"{'='*80}")
    # # DEBUG: mostrar valores de grosor que vienen en el JSON de trazado
    # try:
    #     cruces_dbg = json_trazado.get('cruces', {})
    #     marcas_med_dbg = json_trazado.get('marcas_medianales', {})
    #     marcas_ext_dbg = json_trazado.get('marcas_exteriores', {})
    #     print(f"[DBG PLANTILLA] cruces.grosor_cruz_pt={cruces_dbg.get('grosor_cruz_pt')}, marcas_medianales.grosor_pt={marcas_med_dbg.get('grosor_pt')}, marcas_exteriores.grosor_marca_pt={marcas_ext_dbg.get('grosor_marca_pt')}")
    #     print(f"[DBG PLANTILLA] lineas_cruces={len(cruces_dbg.get('lineas_cruces', []))}, lineas_med={len(marcas_med_dbg.get('lineas_medianales', []))}, lineas_ext={len(marcas_ext_dbg.get('lineas_marcas', []))}")
    # except Exception:
    #     pass

    doc_plantilla = fitz.open()
    capas_coords = json_trazado.get("capas", {})

    # ══════════════════════════════════════════════════════════════════════════════
    # PLANTILLA = GRUPO (capa_3)
    # ══════════════════════════════════════════════════════════════════════════════
    # La plantilla es el GRUPO (cruces+trazado), luego se copia al pliego con offset
    capa_3 = capas_coords.get("capa_3_cruces", {})
    capa_4 = capas_coords.get("capa_4_trazado", {})
    capa_5 = capas_coords.get("capa_5_pliego", {})

    # Tamaño del GRUPO
    grupo_w_mm = capa_3.get("w_mm", 0.0)
    grupo_h_mm = capa_3.get("h_mm", 0.0)
    grupo_w_pt = mm_to_pt(grupo_w_mm)
    grupo_h_pt = mm_to_pt(grupo_h_mm)

    # Tamaño del PLIEGO (puede ser >= grupo)
    pliego_w_mm = capa_5.get("w_mm") or json_trazado["general"]["tamano_pliego_w_mm"]
    pliego_h_mm = capa_5.get("h_mm") or json_trazado["general"]["tamano_pliego_h_mm"]

    if _PRINT_DEBUG:
        print(f"[GRUPO] Tamaño: {grupo_w_mm:.2f} x {grupo_h_mm:.2f} mm")
        print(f"[PLIEGO] Tamaño: {pliego_w_mm:.2f} x {pliego_h_mm:.2f} mm")

    # Crear plantilla del tamaño del GRUPO
    page = doc_plantilla.new_page(width=grupo_w_pt, height=grupo_h_pt)

    # DEFINIR OCGS (Capas PDF)
    # Trazado activado por defecto, Cruces y Marcas activadas
    ocg_trazado = doc_plantilla.add_ocg("Trazado", on=True)
    ocg_cruces = doc_plantilla.add_ocg("Cruces", on=True)
    ocg_marcas = doc_plantilla.add_ocg("Marcas", on=True)

    # Función auxiliar para dibujar líneas en una capa
    def dibujar_lineas_capa(
        lineas: List[Dict],
        offset_x_mm: float,
        offset_y_mm: float,
        color: tuple,
        ocg_name: int,
    ):
        if not lineas:
            return 0

        offset_x_pt = mm_to_pt(offset_x_mm)
        offset_y_pt = mm_to_pt(offset_y_mm)

        count = 0
        # Dibujar cada línea/rectángulo en su propio Shape para poder pasar un
        # ancho de trazo (width) por elemento cuando dibujamos con stroke.
        for linea in lineas:
            # Coordenadas relativas a la capa + Offset de la capa
            x_abs_pt = offset_x_pt + mm_to_pt(linea["x_mm"])
            y_abs_pt = offset_y_pt + mm_to_pt(linea["y_mm"])
            # Por defecto convertimos mm -> pt
            w_pt = mm_to_pt(linea["width_mm"])
            h_pt = mm_to_pt(linea["height_mm"])

            # Si el JSON de trazado contiene un grosor expresado en puntos para
            # esta capa, preferimos usar el valor en puntos directamente (mantener lo que
            # el usuario escribió en el diálogo).
            try:
                grosor_cruces_pt = json_trazado.get("cruces", {}).get("grosor_cruz_pt")
                if grosor_cruces_pt is not None:
                    expected_mm = float(grosor_cruces_pt) * PT_TO_MM
                    if abs(linea.get("width_mm", 0.0) - expected_mm) < 1e-3:
                        w_pt = float(grosor_cruces_pt)
                    if abs(linea.get("height_mm", 0.0) - expected_mm) < 1e-3:
                        h_pt = float(grosor_cruces_pt)
                        if _PRINT_DEBUG:
                            try:
                                print(
                                    f"[DBG GROSOR] Cruces: json_grosor_pt={grosor_cruces_pt} -> expected_mm={expected_mm:.6f} mm; linea height_mm={linea.get('height_mm')}; h_pt set={h_pt}"
                                )
                            except Exception:
                                pass
                grosor_med_pt = json_trazado.get("marcas_medianales", {}).get(
                    "grosor_pt"
                )
                if grosor_med_pt is not None:
                    expected_mm = float(grosor_med_pt) * PT_TO_MM
                    if abs(linea.get("width_mm", 0.0) - expected_mm) < 1e-3:
                        w_pt = float(grosor_med_pt)
                    if abs(linea.get("height_mm", 0.0) - expected_mm) < 1e-3:
                        h_pt = float(grosor_med_pt)
                        if _PRINT_DEBUG:
                            try:
                                print(
                                    f"[DBG GROSOR] Marcas medianales: json_grosor_pt={grosor_med_pt} -> expected_mm={expected_mm:.6f} mm; linea height_mm={linea.get('height_mm')}; h_pt set={h_pt}"
                                )
                            except Exception:
                                pass
                grosor_ext_pt = json_trazado.get("marcas_exteriores", {}).get(
                    "grosor_marca_pt"
                )
                if grosor_ext_pt is not None:
                    expected_mm = float(grosor_ext_pt) * PT_TO_MM
                    if abs(linea.get("width_mm", 0.0) - expected_mm) < 1e-3:
                        w_pt = float(grosor_ext_pt)
                    if abs(linea.get("height_mm", 0.0) - expected_mm) < 1e-3:
                        h_pt = float(grosor_ext_pt)
                        if _PRINT_DEBUG:
                            try:
                                print(
                                    f"[DBG GROSOR] Marcas exteriores: json_grosor_pt={grosor_ext_pt} -> expected_mm={expected_mm:.6f} mm; linea height_mm={linea.get('height_mm')}; h_pt set={h_pt}"
                                )
                            except Exception:
                                pass
            except Exception:
                pass

            # DEBUG: imprimir conversiones mm -> pt para detectar errores de grosor
            if _PRINT_DEBUG:
                try:
                    print(
                        f"[DBG LINE] x_mm={linea.get('x_mm')!s}, y_mm={linea.get('y_mm')!s}, width_mm={linea.get('width_mm')!s}, height_mm={linea.get('height_mm')!s} -> w_pt={w_pt:.4f}, h_pt={h_pt:.4f}"
                    )
                except Exception:
                    pass

            # Decidir si dibujamos como STROKE (línea centrada) o como RECT relleno.
            # Si una dimensión es mucho menor que la otra, tratamos ese elemento como línea.
            try:
                is_vertical_line = w_pt > 0 and h_pt > 0 and (w_pt < h_pt * 0.2)
                is_horizontal_line = w_pt > 0 and h_pt > 0 and (h_pt < w_pt * 0.2)
            except Exception:
                is_vertical_line = False
                is_horizontal_line = False

            if is_horizontal_line:
                # Dibujar línea horizontal centrada en el rect vertical
                y_center = y_abs_pt + h_pt / 2.0
                x0 = x_abs_pt
                x1 = x_abs_pt + w_pt
                stroke_width = h_pt if h_pt > 0 else 1.0
                if _PRINT_DEBUG:
                    try:
                        print(
                            f"[DBG DRAW] H-Line at ({x0:.3f},{y_center:.3f}) - x0->x1=({x0:.3f},{x1:.3f}), w_pt={w_pt:.4f}, h_pt={h_pt:.4f}, stroke_width(pt)={stroke_width:.4f}, stroke_width(mm)={pt_to_mm(stroke_width):.6f}"
                        )
                    except Exception:
                        pass
                tmp = page.new_shape()
                tmp.draw_line((x0, y_center), (x1, y_center))
                tmp.finish(color=color, fill=None, oc=ocg_name, width=stroke_width)
                tmp.commit()
            elif is_vertical_line:
                # Dibujar línea vertical centrada
                x_center = x_abs_pt + w_pt / 2.0
                y0 = y_abs_pt
                y1 = y_abs_pt + h_pt
                stroke_width = w_pt if w_pt > 0 else 1.0
                if _PRINT_DEBUG:
                    try:
                        print(
                            f"[DBG DRAW] V-Line at ({x_center:.3f},{y0:.3f}) - y0->y1=({y0:.3f},{y1:.3f}), w_pt={w_pt:.4f}, h_pt={h_pt:.4f}, stroke_width(pt)={stroke_width:.4f}, stroke_width(mm)={pt_to_mm(stroke_width):.6f}"
                        )
                    except Exception:
                        pass
                tmp = page.new_shape()
                tmp.draw_line((x_center, y0), (x_center, y1))
                tmp.finish(color=color, fill=None, oc=ocg_name, width=stroke_width)
                tmp.commit()
            else:
                # Fallback: rect relleno (áreas grandes)
                rect = fitz.Rect(x_abs_pt, y_abs_pt, x_abs_pt + w_pt, y_abs_pt + h_pt)
                tmp = page.new_shape()
                tmp.draw_rect(rect)
                tmp.finish(color=color, fill=color, oc=ocg_name)
                tmp.commit()

            count += 1

        return count

    # ══════════════════════════════════════════════════════════════════════════════
    # OFFSETS DENTRO DEL GRUPO
    # ══════════════════════════════════════════════════════════════════════════════
    # Dentro del grupo:
    # - Cruces @ (0,0) - origen del grupo
    # - Trazado @ capa_4.offset (11,11) - posición dentro del grupo

    offset_capa4_x = capa_4.get("x_mm", 0.0)
    offset_capa4_y = capa_4.get("y_mm", 0.0)

    if _PRINT_DEBUG:
        print(
            f"\n[OFFSETS GRUPO] Trazado interno: ({offset_capa4_x:.2f}, {offset_capa4_y:.2f})"
        )

    # ══════════════════════════════════════════════════════════════════════════════
    if incluir_marcas_corte:
        # ══════════════════════════════════════════════════════════════════════════
        # CAPA 1 - MARCAS MEDIANALES
        # ══════════════════════════════════════════════════════════════════════════
        # En el origen del grupo
        datos_med = json_trazado.get("marcas_medianales", {})
        if "lineas_medianales" in datos_med:
            n = dibujar_lineas_capa(
                datos_med["lineas_medianales"], 0.0, 0.0, (0, 0, 0), ocg_marcas
            )
            if _PRINT_DEBUG:
                print(f"[MARCAS MEDIANALES] {n} líneas @ (0,0)")

        # ══════════════════════════════════════════════════════════════════════════
        # CAPA 2 - MARCAS EXTERIORES
        # ══════════════════════════════════════════════════════════════════════════
        datos_ext = json_trazado.get("marcas_exteriores", {})
        if "lineas_marcas" in datos_ext:
            n = dibujar_lineas_capa(
                datos_ext["lineas_marcas"], 0.0, 0.0, (0, 0, 0), ocg_marcas
            )
            if _PRINT_DEBUG:
                print(f"[MARCAS EXTERIORES] {n} líneas @ (0,0)")

        # ══════════════════════════════════════════════════════════════════════════
        # CAPA 3 - CRUCES
        # ══════════════════════════════════════════════════════════════════════════
        datos_cruces = json_trazado.get("cruces", {})
        if "lineas_cruces" in datos_cruces:
            n = dibujar_lineas_capa(
                datos_cruces["lineas_cruces"], 0.0, 0.0, (0, 0, 0), ocg_cruces
            )
            if _PRINT_DEBUG:
                print(f"[CRUCES] {n} líneas @ (0,0)")
    elif _PRINT_DEBUG:
        print(
            "[PLANTILLA] Marcas de corte desactivadas en plantilla para dibujarlas sobre la imagen al final"
        )

    # ══════════════════════════════════════════════════════════════════════════════
    # CAPA 4 - TRAZADO
    # ══════════════════════════════════════════════════════════════════════════════
    # En su posición dentro del grupo
    datos_trazado_info = json_trazado.get("trazado", {})
    if "lineas_trazado" in datos_trazado_info:
        n = dibujar_lineas_capa(
            datos_trazado_info["lineas_trazado"],
            offset_capa4_x,
            offset_capa4_y,
            (0, 0, 1),
            ocg_trazado,
        )
        if _PRINT_DEBUG:
            print(f"[TRAZADO] {n} líneas @ ({offset_capa4_x:.2f},{offset_capa4_y:.2f})")

    # Info de Trazado para consola
    offset_capa3_x = capa_3.get("x_mm", 0.0)
    offset_capa3_y = capa_3.get("y_mm", 0.0)

    if _PRINT_DEBUG:
        print(f"\n[RESUMEN PLANTILLA {tipo_plantilla}]")
        print(f"  Grupo: {grupo_w_mm:.1f}×{grupo_h_mm:.1f} mm")
        print(
            f"  Offset grupo (capa_3): ({offset_capa3_x:.2f}, {offset_capa3_y:.2f}) mm"
        )
        print(
            f"  Trazado interno @ ({offset_capa4_x:.1f},{offset_capa4_y:.1f}): {capa_4.get('w_mm',0):.1f}×{capa_4.get('h_mm',0):.1f} mm"
        )
        print(f"✅ Plantilla grupo creada\n")

    # FLATTEN (Opcional, según preferencia user: "Flatten para máquina")
    # doc_plantilla.flatten() # Dejamos capas vivas por ahora para que Fritz las use

    # Guardar dimensiones para copiar al pliego con offset
    page._grupo_w_mm = grupo_w_mm
    page._grupo_h_mm = grupo_h_mm
    page._pliego_w_mm = pliego_w_mm
    page._pliego_h_mm = pliego_h_mm
    page._offset_grupo_x_mm = offset_capa3_x
    page._offset_grupo_y_mm = offset_capa3_y

    return page


def insertar_paginas_en_celdas(
    page: fitz.Page,
    json_trazado: Dict,
    pdf_ordenado: fitz.Document,
    lista_paginas: List[int],
    pliego_num: int = 0,
    pagina_base_pdf: int = 0,
    verbose: bool = False,
    tipo_cara: str = "CARA",
) -> None:
    """
    Inserta páginas del PDF ordenado en las celdas del pliego.

    NUEVA LÓGICA:
    - Prepara cada página con offset en un canvas temporal (preparar_pagina_con_offset)
    - Recorta y coloca desde ese canvas (dibujar_en_celda)
    - Elimina la limitación de 3mm en los offsets

    Args:
        page: Página del pliego donde insertar
        json_trazado: Diccionario con la configuración del trazado
        pdf_ordenado: Documento PDF con las páginas ordenadas
        lista_paginas: Lista de números de página a insertar
        pliego_num: Número del pliego (para logs)
        pagina_base_pdf: Página base (no usado actualmente)
        verbose: Si True, imprime información detallada
    """
    if not lista_paginas:
        return 0

    celdas_dibujadas = 0
    grid_cols = json_trazado["general"]["grid_cols"]
    celdas = json_trazado["trazado"]["celdas"]

    # ========== OFFSETS DEL USUARIO ==========
    imagen = json_trazado.get("imagen", {})
    user_offset_x_mm = float(imagen.get("offset_usuario_x_mm", 0.0))
    user_offset_y_mm = float(imagen.get("offset_usuario_y_mm", 0.0))
    bleed_mm = float(
        imagen.get("bleed_mm", 0.0)
    )  # Si es 0, respeta 0 (no usa default 3)

    # 🔄 Invertir offset X si es DORSO
    if tipo_cara == "DORSO":
        user_offset_x_mm = -user_offset_x_mm

    # ========== OFFSETS DE CAPAS ==========
    capas = json_trazado.get("capas", {})
    capa3 = capas.get("capa_3_cruces", {})
    capa4 = capas.get("capa_4_trazado", {})

    capa3_x_mm = float(capa3.get("x_mm", 0.0))
    capa3_y_mm = float(capa3.get("y_mm", 0.0))
    capa4_x_mm = float(capa4.get("x_mm", 0.0))
    capa4_y_mm = float(capa4.get("y_mm", 0.0))

    claves_ordenadas = sorted(
        celdas.keys(), key=lambda k: tuple(map(int, k.split(": ")[1].split(",")))
    )

    for celda_key in claves_ordenadas:
        celda = celdas[celda_key]
        row, col = map(int, celda_key.split(": ")[1].split(","))
        indice = row * grid_cols + col

        if indice >= len(lista_paginas):
            continue

        page_num = int(lista_paginas[indice]) - 1
        if page_num < 0 or page_num >= pdf_ordenado.page_count:
            continue

        pos_x_mm = celda["pos_x_mm"]
        pos_y_mm = celda["pos_y_mm"]
        celda_w_mm = celda["celda_w_mm"]
        celda_h_mm = celda["celda_h_mm"]

        # ========== OFFSET DE CELDA (Fritz) ==========
        # Este offset es el automático de cada celda (ajuste de centrado/posicionamiento)
        offset_celda_x_mm = float(celda.get("offset_imagen_fritz_x_mm", 0.0))
        offset_celda_y_mm = float(celda.get("offset_imagen_fritz_y_mm", 0.0))

        # ========== OFFSET TOTAL = USUARIO + CELDA ==========
        # El offset total es la suma del offset del usuario y el offset automático de la celda
        offset_total_x_mm = user_offset_x_mm + offset_celda_x_mm
        offset_total_y_mm = user_offset_y_mm + offset_celda_y_mm

        abs_x_mm = capa3_x_mm + capa4_x_mm + pos_x_mm
        abs_y_mm = capa3_y_mm + capa4_y_mm + pos_y_mm

        # 🔥 DIBUJAR DIRECTAMENTE EN LA CELDA (SIN DOCUMENTOS TEMPORALES)
        mm = 72.0 / 25.4

        # 1. Dimensiones de la página fuente (escala 1:1, keep_proportion=False)
        src_page = pdf_ordenado[page_num]
        if verbose:
            if _PRINT_DEBUG:
                print(
                    f"  [DRAW] celda={celda_key} page_num={page_num} abs=({abs_x_mm:.1f},{abs_y_mm:.1f}) "
                    f"celda={celda_w_mm:.1f}x{celda_h_mm:.1f} offset=({offset_total_x_mm:.2f},{offset_total_y_mm:.2f})"
                )
        src_w_pt = src_page.rect.width
        src_h_pt = src_page.rect.height

        # 2. Dónde caería la esquina superior-izquierda de la fuente en el pliego (con offset)
        dest_x_pt = (abs_x_mm + offset_total_x_mm) * mm
        dest_y_pt = (abs_y_mm + offset_total_y_mm) * mm
        full_dest = fitz.Rect(
            dest_x_pt, dest_y_pt, dest_x_pt + src_w_pt, dest_y_pt + src_h_pt
        )

        # 3. Ventana visible: celda expandida por sangre (en coords del pliego/destino)
        cell_window = fitz.Rect(
            (abs_x_mm - bleed_mm) * mm,
            (abs_y_mm - bleed_mm) * mm,
            (abs_x_mm + celda_w_mm + bleed_mm) * mm,
            (abs_y_mm + celda_h_mm + bleed_mm) * mm,
        )

        # 4. Área visible real = intersección de la fuente con la ventana de la celda
        visible_dest = full_dest & cell_window  # operador & de PyMuPDF
        if visible_dest.is_empty:
            if verbose:
                if _PRINT_DEBUG:
                    print(
                        f"[SKIP] Celda {celda_key}: la fuente no solapa con la ventana de la celda."
                    )
            continue

        # 5. Clip en coordenadas FUENTE: mapeo inverso de visible_dest → src
        #    Como escala es 1:1, es simplemente restar el origen de full_dest
        src_clip = fitz.Rect(
            visible_dest.x0 - dest_x_pt,
            visible_dest.y0 - dest_y_pt,
            visible_dest.x1 - dest_x_pt,
            visible_dest.y1 - dest_y_pt,
        )

        page.show_pdf_page(
            visible_dest,  # sólo el área que realmente se ve
            docsrc=pdf_ordenado,
            pno=page_num,
            clip=src_clip,  # porción de la fuente que corresponde a visible_dest
            keep_proportion=False,
            overlay=True,
        )
        celdas_dibujadas += 1

        if _PRINT_DEBUG and verbose:
            print(
                f"[OK] Pliego {pliego_num} celda {celda_key} "
                f"offset_usuario=({user_offset_x_mm:.2f},{user_offset_y_mm:.2f}) "
                f"offset_celda=({offset_celda_x_mm:.2f},{offset_celda_y_mm:.2f}) "
                f"offset_total=({offset_total_x_mm:.2f},{offset_total_y_mm:.2f})"
            )

    if _PRINT_DEBUG:
        print(f"✔ Pliego {pliego_num}: {celdas_dibujadas} celdas dibujadas.")
    return celdas_dibujadas


def dibujar_marcas_corte_sobre_imagen(page: fitz.Page, json_trazado: Dict) -> int:
    """
    Dibuja cruces y marcas de corte al final del render para que siempre queden
    por encima de la imagen insertada.

    Nota: lineas_trazado se excluye porque es guía de UI y no marca de corte.
    """

    def _dibujar_lineas(
        lineas: List[Dict],
        offset_x_mm: float,
        offset_y_mm: float,
        grosor_pt: Optional[float] = None,
    ) -> int:
        if not lineas:
            return 0

        offset_x_pt = mm_to_pt(offset_x_mm)
        offset_y_pt = mm_to_pt(offset_y_mm)
        dibujadas = 0

        for linea in lineas:
            x_abs_pt = offset_x_pt + mm_to_pt(linea["x_mm"])
            y_abs_pt = offset_y_pt + mm_to_pt(linea["y_mm"])
            w_pt = mm_to_pt(linea["width_mm"])
            h_pt = mm_to_pt(linea["height_mm"])

            if grosor_pt is not None:
                expected_mm = float(grosor_pt) * PT_TO_MM
                if abs(linea.get("width_mm", 0.0) - expected_mm) < 1e-3:
                    w_pt = float(grosor_pt)
                if abs(linea.get("height_mm", 0.0) - expected_mm) < 1e-3:
                    h_pt = float(grosor_pt)

            is_vertical_line = w_pt > 0 and h_pt > 0 and (w_pt < h_pt * 0.2)
            is_horizontal_line = w_pt > 0 and h_pt > 0 and (h_pt < w_pt * 0.2)

            if is_horizontal_line:
                y_center = y_abs_pt + h_pt / 2.0
                x0 = x_abs_pt
                x1 = x_abs_pt + w_pt
                stroke_width = h_pt if h_pt > 0 else 1.0
                page.draw_line(
                    (x0, y_center), (x1, y_center), color=(0, 0, 0), width=stroke_width
                )
            elif is_vertical_line:
                x_center = x_abs_pt + w_pt / 2.0
                y0 = y_abs_pt
                y1 = y_abs_pt + h_pt
                stroke_width = w_pt if w_pt > 0 else 1.0
                page.draw_line(
                    (x_center, y0), (x_center, y1), color=(0, 0, 0), width=stroke_width
                )
            else:
                rect = fitz.Rect(x_abs_pt, y_abs_pt, x_abs_pt + w_pt, y_abs_pt + h_pt)
                page.draw_rect(rect, color=(0, 0, 0), fill=(0, 0, 0), width=0)

            dibujadas += 1

        return dibujadas

    capas = json_trazado.get("capas", {})
    capa3 = capas.get("capa_3_cruces", {})
    offset_x_mm = float(capa3.get("x_mm", 0.0))
    offset_y_mm = float(capa3.get("y_mm", 0.0))

    total = 0

    datos_med = json_trazado.get("marcas_medianales", {})
    total += _dibujar_lineas(
        datos_med.get("lineas_medianales", []),
        offset_x_mm,
        offset_y_mm,
        datos_med.get("grosor_pt"),
    )

    datos_ext = json_trazado.get("marcas_exteriores", {})
    total += _dibujar_lineas(
        datos_ext.get("lineas_marcas", []),
        offset_x_mm,
        offset_y_mm,
        datos_ext.get("grosor_marca_pt"),
    )

    datos_cruces = json_trazado.get("cruces", {})
    total += _dibujar_lineas(
        datos_cruces.get("lineas_cruces", []),
        offset_x_mm,
        offset_y_mm,
        datos_cruces.get("grosor_cruz_pt"),
    )

    if _PRINT_DEBUG:
        print(f"[MARCAS SOBRE IMAGEN] {total} elementos dibujados sobre la imagen")

    return total


def agregar_texto_pliego(
    page: fitz.Page,
    json_trazado: Dict,
    numero_pliego: int,
    tipo_cara: str,
    numero_copia: int = 1,
    total_copias: int = 1,
    pagina_salida_num: Optional[int] = None,
) -> None:
    """Agrega texto informativo en la pagina del pliego."""
    # Si la marca_texto está presente y es un dict vacío, interpretarla como
    # "desactivada" por el usuario (se indicó `{}`) y no dibujar nada.
    if (
        "marca_texto" in json_trazado
        and isinstance(json_trazado["marca_texto"], dict)
        and not json_trazado["marca_texto"]
    ):
        return

    if "marca_texto" not in json_trazado:
        return

    marca = json_trazado["marca_texto"]
    contenido_base = marca.get("contenido", "NumStack")

    # Normalizar contenido_base a NFC (macOS usa NFD con acentos descompuestos)
    contenido_base = unicodedata.normalize("NFC", contenido_base)

    texto = f"{contenido_base} - {t('Pliego:')} {numero_pliego} - {t(tipo_cara)}"
    if total_copias > 1:
        texto += f" - {t('Copia:')} {numero_copia}/{total_copias}"
    # Añadir número de página de salida (si se proporcionó)
    if pagina_salida_num is not None:
        try:
            texto += f" - {t('Página:')} {int(pagina_salida_num)}"
        except Exception:
            texto += f" - {t('Página:')} {pagina_salida_num}"

    posicion = marca.get("posicion", "centro_sup")
    offset_h_mm = marca.get("offset_h_mm", 0.0)
    offset_v_mm = marca.get("offset_v_mm", 3.0)
    cuerpo = marca.get("cuerpo", 12)
    rotation = marca.get("rotacion", 0)
    familia_json = marca.get("familia", "Arial")
    tipo = marca.get("tipo", "Regular")

    # Construir nombre completo para búsqueda y registro
    # Si es 'Regular', ignoramos el tipo para no ensuciar la búsqueda
    if tipo and tipo.lower() != "regular":
        nombre_fuente_completo = f"{familia_json} {tipo}"
    else:
        nombre_fuente_completo = familia_json

    # Normalizar nombre de familia (para el mapeo base14)
    familia_normalizada = familia_json.lower().replace(" ", "")

    # Mapeo de fuentes Base14 estándar de PDF
    # Para estas, PyMuPDF ya entiende nombres como "Helvetica-Bold"
    mapeo_fuentes_base14 = {
        "arial": "Helvetica",
        "helvetica": "Helvetica",
        "helv": "Helvetica",
        "times": "Times-Roman",
        "timesnewroman": "Times-Roman",
        "courier": "Courier",
        "verdana": "Helvetica",
        "georgia": "Times-Roman",
    }

    familia_base14 = mapeo_fuentes_base14.get(familia_normalizada, "Helvetica")

    # Si es bold/italic, ajustar el nombre base14 (PyMuPDF usa guiones)
    # Ejemplo: Helvetica -> Helvetica-Bold
    if tipo and tipo.lower() != "regular":
        if "bold" in tipo.lower() and "italic" in tipo.lower():
            familia_base14 += "-BoldOblique"
        elif "bold" in tipo.lower():
            familia_base14 += "-Bold"
        elif "italic" in tipo.lower() or "oblique" in tipo.lower():
            familia_base14 += "-Oblique"

    # Preparar constantes para el cálculo de coordenadas
    page_rect = page.rect
    page_w_pt = page_rect.width
    page_h_pt = page_rect.height
    offset_h_pt = mm_to_pt(offset_h_mm)
    offset_v_pt = mm_to_pt(offset_v_mm)

    # Preparar nombre de fuente para fitz
    fitz_fontname = _map_font_name(nombre_fuente_completo)
    font_obj = None
    registered_fontname = None

    # 1) Intentar instanciar con el mapeo o nombre directo
    try:
        font_obj = fitz.Font(fitz_fontname)
        registered_fontname = fitz_fontname
        print(f"[PDF FONT] Usando fuente base14: {fitz_fontname}")
    except Exception:
        font_obj = None

    # 2) Si falla, intentar usar caché global antes de buscar/registrar
    if font_obj is None:
        cached = _FONT_CACHE.get(nombre_fuente_completo)
        if cached:
            safe_alias = cached.get("alias")
            fontbuffer = cached.get("buffer")
            try:
                # Preferir fontbuffer si está disponible (más robusto)
                if fontbuffer:
                    page.insert_font(fontname=safe_alias, fontbuffer=fontbuffer)
                    font_obj = fitz.Font(fontbuffer=fontbuffer)
                    print(f"[PDF FONT] Usando fuente cacheada (buffer): {safe_alias}")
                else:
                    # Fallback a fontfile si no hay buffer
                    font_path = cached.get("path")
                    font_obj = fitz.Font(fontfile=font_path)
                    print(
                        f"[PDF FONT] Usando fuente cacheada (file): {safe_alias} ({font_path})"
                    )
                registered_fontname = safe_alias
            except Exception:
                try:
                    del _FONT_CACHE[nombre_fuente_completo]
                except Exception:
                    pass
                font_obj = None

    # 3) Si no había cache o la carga falló, buscar el archivo y registrar, luego cachear
    if font_obj is None:
        font_path = _find_system_font_file(nombre_fuente_completo)
        if font_path:
            try:
                # Alias único: nombre + hash de ruta
                import hashlib

                hash_alias = hashlib.md5(font_path.encode()).hexdigest()[:6]
                safe_alias = f"{os.path.splitext(os.path.basename(font_path))[0].replace(' ', '')}_{hash_alias}"

                # ESTRATEGIA PageNumber: Leer fuente como buffer en memoria
                # Esto evita problemas de encoding y acceso al archivo
                with open(font_path, "rb") as fh:
                    fontbuffer = fh.read()

                # Registrar con fontbuffer (más robusto que fontfile)
                page.insert_font(fontname=safe_alias, fontbuffer=fontbuffer)
                font_obj = fitz.Font(fontbuffer=fontbuffer)
                registered_fontname = safe_alias
                print(
                    f"[PDF FONT] Registrada fuente personalizada: {safe_alias} ({font_path})"
                )
                try:
                    _FONT_CACHE[nombre_fuente_completo] = {
                        "path": font_path,
                        "alias": safe_alias,
                        "buffer": fontbuffer,
                    }
                except Exception:
                    pass
            except Exception as e:
                print(
                    f"[PDF FONT] Error registrando fuente personalizada: {font_path} -> {e}"
                )
                font_obj = None

    # 4) Fallback a fuente base segura
    if font_obj is None:
        try:
            font_obj = fitz.Font(familia_base14)
            registered_fontname = familia_base14
            print(f"[PDF FONT] Fallback a base14: {familia_base14}")
        except Exception:
            font_obj = fitz.Font("helv")
            registered_fontname = "helv"
            print(f"[PDF FONT] Fallback a Helvetica")

    try:
        # Usamos el bbox de una letra mayúscula 'H' para un desplazamiento visual preciso
        # y0 es la distancia desde la línea de base al tope (negativa)
        bbox_h = font_obj.text_bbox("H", fontsize=cuerpo)
        visual_ascent = -bbox_h.y0

        # Como margen de seguridad, si visual_ascent es muy raro, fallback heurístico
        if visual_ascent > 0 and visual_ascent < cuerpo * 1.5:
            baseline_offset = visual_ascent
        else:
            baseline_offset = cuerpo * 0.75
    except Exception:
        baseline_offset = cuerpo * 0.75

    # Calcular la posición X/Y y ajustar por alineamiento usando métricas del objeto font
    # Usamos font_obj.text_length para medir anchura real del texto
    try:
        text_width = font_obj.text_length(texto, fontsize=cuerpo)
    except Exception:
        # Fallback a la utilidad simple de fitz
        try:
            text_width = fitz.get_text_length(
                texto, fontname=registered_fontname or familia_base14, fontsize=cuerpo
            )
        except Exception:
            text_width = 0

    # --- DEFINICIÓN DE ANCLA (Punto de referencia en la página) ---
    if "sup" in posicion:
        ay = offset_v_pt
        v_zone = "T"
    elif "inf" in posicion:
        ay = page_h_pt - offset_v_pt
        v_zone = "B"
    else:
        ay = page_h_pt / 2
        v_zone = "C"

    if "izq" in posicion:
        ax = offset_h_pt
        h_zone = "L"
    elif "der" in posicion:
        ax = page_w_pt - offset_h_pt
        h_zone = "R"
    else:
        ax = page_w_pt / 2
        h_zone = "C"

    # Respetar alineación si viene en el JSON, o inferir de la zona
    align = marca.get(
        "align", "center" if h_zone == "C" else ("left" if h_zone == "L" else "right")
    )

    # ═══════════════════════════════════════════════════════════════════════════
    # --- MATRIZ DE TRANSFORMACIÓN (Ancla -> Baseline PyMuPDF) ---
    # ═══════════════════════════════════════════════════════════════════════════
    # W = text_width, H = baseline_offset (ascent visual)
    W = text_width
    H = baseline_offset
    pdf_rotation = -rotation  # Flet(CW) -> PyMuPDF(CCW)

    if rotation == 0:
        # Horizontal
        if h_zone == "L":
            x = ax
        elif h_zone == "R":
            x = ax - W
        else:
            x = ax - W / 2

        if v_zone == "T":
            y = ay + H
        elif v_zone == "B":
            y = ay
        else:
            y = ay + H / 2

    elif rotation == 90:
        # Vertical Down (Crece a la derecha de la base)
        if h_zone == "L":
            x = ax
        elif h_zone == "R":
            x = ax - H
        else:
            x = ax - H / 2

        if v_zone == "T":
            y = ay
        elif v_zone == "B":
            y = ay - W
        else:
            y = ay - W / 2

    elif rotation == 180:
        # Invertido (Crece a la izquierda y arriba de la base/boca abajo)
        if h_zone == "L":
            x = ax + W
        elif h_zone == "R":
            x = ax
        else:
            x = ax + W / 2

        if v_zone == "T":
            y = ay
        elif v_zone == "B":
            y = ay - H
        else:
            y = ay - H / 2

    elif rotation == 270:
        # Vertical Up (Crece a la izquierda de la base)
        if h_zone == "L":
            x = ax + H
        elif h_zone == "R":
            x = ax
        else:
            x = ax + H / 2

        if v_zone == "T":
            y = ay + W
        elif v_zone == "B":
            y = ay
        else:
            y = ay + W / 2
    else:
        x, y = ax, ay

    # Insertar texto: preferir el alias registrado si existe
    fontname_to_use = registered_fontname or fitz_fontname or familia_base14

    try:
        page.insert_text(
            (x, y),
            texto,
            fontsize=cuerpo,
            fontname=fontname_to_use,
            color=(0, 0, 0),
            rotate=pdf_rotation,
        )
    except Exception as e:
        print(f"[PDF FONT] Error insert_text con {fontname_to_use}: {e}")
        # Rescate: intentar con Helvetica
        try:
            page.insert_text(
                (x, y),
                texto,
                fontsize=cuerpo,
                fontname="helv",
                color=(0, 0, 0),
                rotate=pdf_rotation,
            )
        except Exception as e2:
            print(f"[PDF FONT] Error fallback helv: {e2}")


def generar_pdf_imposicion(
    pdf_ordenado_path: str,
    ordenamiento: Dict,
    json_cara: Dict,
    json_dorso: Optional[Dict],
    num_copias: int,
    crear_xerox: bool,
    ruta_salida: str,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    save_opts_final: Optional[Dict] = None,
    cancel_checker: Optional[Callable[[], bool]] = None,
) -> str:
    """Genera el PDF de imposicion completo."""

    if _PRINT_DEBUG:
        print(f"\n{'#'*80}")
        print(f"GENERADOR PDF IMPOSICION")
        print(f"{'#'*80}")
        print(f"PDF ordenado: {pdf_ordenado_path}")
        print(f"Copias: {num_copias}")
        print(f"Salida: {ruta_salida}")

    def _check_cancel():
        if callable(cancel_checker) and cancel_checker():
            raise InterruptedError("Generación cancelada por el usuario")

    # Abrir PDF ordenado
    _check_cancel()
    pdf_ordenado = fitz.open(pdf_ordenado_path)
    if _PRINT_DEBUG:
        print(f"PDF cargado: {pdf_ordenado.page_count} paginas")

    # Si la marca de texto está vacía o contiene el texto por defecto
    # (p. ej. comienza por 'NumStack'), reemplazarla por el nombre del
    # archivo ordenado para que aparezca en la plantilla y en todos los pliegos.
    try:
        # Preferir el nombre original (sin sufijos temporales como '_ordenado_temp')
        base = os.path.basename(pdf_ordenado_path) or pdf_ordenado_path
        name, ext = os.path.splitext(base)
        # Eliminar sufijos comunes generados por procesos intermedios
        had_temp_suffix = False
        for suf in ("_ordenado_temp", "_ordenado", "_temp"):
            if name.endswith(suf):
                name = name[: -len(suf)]
                had_temp_suffix = True
                break
        # Usar solo el nombre sin extensión .pdf
        nombre_archivo = name.strip()

        for j in (json_cara, json_dorso) if json_dorso is not None else (json_cara,):
            if not j:
                continue
            # Asegurar que la clave existe para mantener la estructura JSON.
            if "marca_texto" not in j:
                j["marca_texto"] = {}
            marca = j.get("marca_texto") or {}
            # Si la marca es un dict vacío ({}) lo consideramos "desactivada" por el usuario
            # y no debemos auto-rellenar ni forzar contenido. Respetar {} como "no imprimir".
            if isinstance(marca, dict) and not marca:
                continue
            contenido = marca.get("contenido", "")
            # Si el PDF temporal tiene sufijo, forzamos usar el nombre limpio del origen.
            if had_temp_suffix:
                j["marca_texto"]["contenido"] = nombre_archivo
            else:
                # Si no había sufijo temporal, solo sustituir si el contenido está vacío
                # o contiene el texto genérico 'NumStack' (evitar sobreescribir marcas personalizadas).
                if not contenido or str(contenido).strip().startswith("NumStack"):
                    j["marca_texto"]["contenido"] = nombre_archivo
    except Exception:
        pass

    # ═══════════════════════════════════════════════════════════════════════════
    # CREAR PLANTILLAS (UNA VEZ)
    # ═══════════════════════════════════════════════════════════════════════════
    plantilla_cara = crear_plantilla_trazado(
        json_cara,
        pdf_ordenado_path,
        "CARA",
        incluir_marcas_corte=False,
    )

    plantilla_dorso = None
    if json_dorso:
        plantilla_dorso = crear_plantilla_trazado(
            json_dorso,
            pdf_ordenado_path,
            "DORSO",
            incluir_marcas_corte=False,
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # INICIALIZAR GENERACIÓN POR LOTES
    # ═══════════════════════════════════════════════════════════════════════════
    # Patrón PyMuPDF para PDFs grandes:
    #   - Generar N páginas en un doc fresco (fitz.open() sin archivo base)
    #   - Guardar el lote a disco (siempre válido: doc sin backing file)
    #   - Cerrar + store_shrink(100) → libera RAM del doc Y caché interna MuPDF
    #   - Repetir con un doc nuevo
    #   - Al final, unir todos los lotes con insert_pdf en un único PDF final
    # Sin archivos alternos, sin renombrados, sin restricciones de PyMuPDF.
    BATCH_SIZE = 20  # páginas por lote

    # Carpeta temporal exclusiva para los lotes:
    #   - Se elimina al INICIO por si quedó basura de una ejecución anterior fallida
    #   - Se elimina al FINAL una vez copiado el PDF definitivo
    temp_dir = get_config_dir() / "pdf_temp"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
        if _PRINT_DEBUG:
            print(f"[BATCH] Carpeta temporal previa eliminada: {temp_dir}")
    temp_dir.mkdir(parents=True, exist_ok=True)
    if _PRINT_DEBUG:
        print(f"[BATCH] Carpeta temporal creada: {temp_dir}")

    batch_files: list = []
    batch_num = 0
    doc_salida = fitz.open()  # doc fresco para el lote actual (sin backing file)
    if _PRINT_DEBUG:
        print(f"[BATCH] Generación por lotes de {BATCH_SIZE} páginas en {temp_dir}")

    # Obtener lista de pliegos
    pliegos_ordenados = sorted([k for k in ordenamiento.keys() if isinstance(k, int)])
    total_pliegos = len(pliegos_ordenados)
    total_operaciones = total_pliegos * num_copias
    operacion_actual = 0

    if _PRINT_DEBUG:
        print(f"\n{'='*80}")
        print(f"GENERANDO PLIEGOS")
        print(f"{'='*80}")
        print(
            f"Total: {total_pliegos} pliegos x {num_copias} copias = {total_operaciones} paginas, pliegos_ordenados{pliegos_ordenados}"
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # GENERAR PLIEGOS
    # ═══════════════════════════════════════════════════════════════════════════
    # OPTIMIZACIÓN: Ya NO usamos lógica secuencial
    # Ahora usamos directamente los índices del ordenamiento [11, 36, 61, 86]

    # Detectar si hay modo doble cara (hay pliegos con 'dorso')
    hay_doble_cara = any(
        ordenamiento[k].get("doble_cara", "cara").lower() == "dorso"
        for k in pliegos_ordenados
    )
    if _PRINT_DEBUG:
        print(f"[DEBUG MODO] Doble cara detectado: {hay_doble_cara}")

    # Procesar pliegos: primero procesamos TODOS LOS PLIEGOS, luego duplicamos por copias
    # En modo UNA CARA: duplicamos cada pliego individual
    # En modo DOBLE CARA: duplicamos cada PAR (cara+dorso)
    idx_pliego = 0
    numero_pliego_fisico = 0  # Contador de pliegos físicos (independiente de copias)
    while idx_pliego < len(pliegos_ordenados):
        _check_cancel()
        # Obtener pliego(s) a procesar en este grupo
        pliego_keys = [pliegos_ordenados[idx_pliego]]

        # Si es doble cara y el siguiente es DORSO, agruparlos
        if hay_doble_cara and idx_pliego + 1 < len(pliegos_ordenados):
            siguiente_key = pliegos_ordenados[idx_pliego + 1]
            if ordenamiento[siguiente_key].get("doble_cara", "cara").lower() == "dorso":
                pliego_keys.append(siguiente_key)
                idx_pliego += 2
            else:
                idx_pliego += 1
        else:
            idx_pliego += 1

        # Incrementar el número de pliego físico (este es el mismo para todas las copias)
        numero_pliego_fisico += 1

        # Duplicar este grupo (pliego o par cara+dorso) por cada copia
        for copia in range(1, num_copias + 1):
            _check_cancel()
            # NOTA: Ya no se usa pagina_base_pdf (lógica secuencial eliminada)
            # Ahora se usan directamente los índices del ordenamiento [11, 36, 61, 86]

            # Procesar cada pliego del grupo
            for pliego_num in pliego_keys:
                _check_cancel()
                pliego_data = ordenamiento[pliego_num]
                lista_paginas = pliego_data["datos"]
                tipo_cara = pliego_data.get("doble_cara", "cara").upper()

                # Seleccionar plantilla
                if tipo_cara == "DORSO" and plantilla_dorso:
                    plantilla = plantilla_dorso
                    json_actual = json_dorso
                else:
                    plantilla = plantilla_cara
                    json_actual = json_cara

                # Obtener dimensiones y offset del grupo
                grupo_w_mm = getattr(
                    plantilla, "_grupo_w_mm", plantilla.rect.width * PT_TO_MM
                )
                grupo_h_mm = getattr(
                    plantilla, "_grupo_h_mm", plantilla.rect.height * PT_TO_MM
                )
                pliego_w_mm = getattr(
                    plantilla, "_pliego_w_mm", plantilla.rect.width * PT_TO_MM
                )
                pliego_h_mm = getattr(
                    plantilla, "_pliego_h_mm", plantilla.rect.height * PT_TO_MM
                )
                offset_x_mm = getattr(plantilla, "_offset_grupo_x_mm", 0.0)
                offset_y_mm = getattr(plantilla, "_offset_grupo_y_mm", 0.0)

                # Crear página del tamaño del PLIEGO
                pliego_w_pt = mm_to_pt(pliego_w_mm)
                pliego_h_pt = mm_to_pt(pliego_h_mm)
                nueva_pagina = doc_salida.new_page(
                    width=pliego_w_pt, height=pliego_h_pt
                )

                # Copiar GRUPO al pliego con offset de capa_3
                offset_x_pt = mm_to_pt(offset_x_mm)
                offset_y_pt = mm_to_pt(offset_y_mm)
                grupo_w_pt = mm_to_pt(grupo_w_mm)
                grupo_h_pt = mm_to_pt(grupo_h_mm)

                dest_rect = fitz.Rect(
                    offset_x_pt,
                    offset_y_pt,
                    offset_x_pt + grupo_w_pt,
                    offset_y_pt + grupo_h_pt,
                )

                nueva_pagina.show_pdf_page(
                    dest_rect, plantilla.parent, plantilla.number
                )

                if pliego_num == 1:  # Log solo en primer pliego
                    if _PRINT_DEBUG:
                        print(
                            f"[COPY] Grupo {grupo_w_mm:.1f}×{grupo_h_mm:.1f}mm → Pliego {pliego_w_mm:.1f}×{pliego_h_mm:.1f}mm"
                        )
                        print(
                            f"[COPY] Offset capa_3: ({offset_x_mm:.2f}, {offset_y_mm:.2f})mm"
                        )

                # ═══════════════════════════════════════════════════════════════
                # OPTIMIZACIÓN: Usar índices originales del ordenamiento
                # ═══════════════════════════════════════════════════════════════
                # ANTES (usaba PDF reordenado secuencialmente):
                #   lista_secuencial = [1, 2, 3, 4] → Extraía páginas 1,2,3,4 del PDF temporal
                #
                # AHORA (usa PDF original):
                #   lista_paginas = [11, 36, 61, 86] → Extrae páginas 11,36,61,86 del PDF original
                # ═══════════════════════════════════════════════════════════════

                if _PRINT_DEBUG:
                    print(
                        f"[DEBUG PLIEGO] Pliego {pliego_num} - {tipo_cara}: indices_originales={lista_paginas}"
                    )

                # Insertar paginas usando índices ORIGINALES del ordenamiento
                paginas_insertadas = insertar_paginas_en_celdas(
                    nueva_pagina,
                    json_actual,
                    pdf_ordenado,
                    lista_paginas,  # ← CAMBIO: Usar índices originales [11, 36, 61, 86]
                    pliego_num,
                    0,
                    verbose=(operacion_actual <= 2),  # verbose solo primeros 2 pliegos
                    tipo_cara=tipo_cara,
                )

                # Dibujar cruces y marcas de corte al final para garantizar que
                # queden por encima de la imagen insertada.
                dibujar_marcas_corte_sobre_imagen(nueva_pagina, json_actual)

                # NOTA: pagina_base_pdf ya NO se usa (se eliminó lógica secuencial)

                # Preparar y mostrar en consola el texto que se va a insertar en la capa de texto
                # IMPORTANTE: usar operacion_actual + 1 (contador global) en lugar de
                # nueva_pagina.number + 1 (que se resetea a 0 cada BATCH_SIZE páginas
                # cuando doc_salida se cierra y se abre uno nuevo).
                try:
                    pagina_salida = operacion_actual + 1
                except Exception:
                    pagina_salida = None

                try:
                    marca = json_actual.get("marca_texto", {})
                    contenido_base = marca.get("contenido", "NumStack")
                except Exception:
                    contenido_base = "NumStack"

                # Nota: la marca_texto ya fue normalizada al inicio del proceso,
                # por lo que no necesitamos sobrescribirla por-pliego aquí.

                # Usar el número de pliego físico calculado (independiente de copias)
                # Este número se mantiene constante para todas las copias del mismo pliego
                pliego_etiqueta = numero_pliego_fisico

                texto_preview = f"{contenido_base} - {t('Pliego:')} {pliego_etiqueta} - {t(tipo_cara)}"
                if num_copias > 1:
                    texto_preview += f" - {t('Copia:')} {copia}/{num_copias}"
                if pagina_salida is not None:
                    texto_preview += f" - {t('Página:')} {pagina_salida}"

                if _PRINT_DEBUG:
                    print(
                        f"[DEBUG TEXTO PLIEGO] Pliego {pliego_etiqueta} (orig_key={pliego_num}) -> {texto_preview}"
                    )

                # Agregar texto
                agregar_texto_pliego(
                    nueva_pagina,
                    json_actual,
                    pliego_etiqueta,
                    tipo_cara,
                    copia,
                    num_copias,
                    pagina_salida_num=pagina_salida,
                )

                # Log resumido por pliego
                if _PRINT_DEBUG:
                    print(
                        f"  Pliego {pliego_num:3d} ({tipo_cara:5s}) copia {copia}: "
                        f"{paginas_insertadas} celdas dibujadas"
                    )

                operacion_actual += 1

                # LOTE COMPLETO: guardar a disco, liberar RAM, empezar doc nuevo
                if operacion_actual % BATCH_SIZE == 0:
                    _check_cancel()
                    batch_path = str(temp_dir / f"imposicion_batch_{batch_num}.pdf")
                    doc_salida.save(batch_path, garbage=4, deflate=False, clean=True)
                    doc_salida.close()
                    fitz.TOOLS.store_shrink(
                        100
                    )  # vaciar caché MuPDF (fuentes, imágenes)
                    batch_files.append(batch_path)
                    batch_num += 1
                    doc_salida = fitz.open()  # doc fresco para el siguiente lote
                    if _PRINT_DEBUG:
                        print(
                            f"[BATCH] Lote {batch_num} guardado "
                            f"(op {operacion_actual}/{total_operaciones})"
                        )

                if progress_callback:
                    try:
                        progress_callback(operacion_actual, total_operaciones)
                    except InterruptedError:
                        if _PRINT_DEBUG:
                            print("[INFO] Generación cancelada por callback")
                        doc_salida.close()
                        pdf_ordenado.close()
                        # Limpiar carpeta temporal de lotes
                        try:
                            shutil.rmtree(temp_dir)
                        except Exception:
                            pass
                        raise

    # ═══════════════════════════════════════════════════════════════════════════
    # GUARDAR ÚLTIMO LOTE (las páginas que no llegaron a completar BATCH_SIZE)
    # ═══════════════════════════════════════════════════════════════════════════
    if _PRINT_DEBUG:
        print(f"\n{'='*80}")
        print(f"GUARDANDO Y UNIENDO LOTES")
        print(f"{'='*80}")

    if doc_salida.page_count > 0:
        _check_cancel()
        batch_path = str(temp_dir / f"imposicion_batch_{batch_num}.pdf")
        doc_salida.save(batch_path, garbage=4, deflate=False, clean=True)
        doc_salida.close()
        fitz.TOOLS.store_shrink(100)
        batch_files.append(batch_path)
        batch_num += 1
        if _PRINT_DEBUG:
            print(
                f"[BATCH] Último lote guardado ({doc_salida.page_count if False else 'resto'} páginas)"
            )
    else:
        doc_salida.close()

    pdf_ordenado.close()

    # ═══════════════════════════════════════════════════════════════════════════
    # UNIR TODOS LOS LOTES EN EL PDF FINAL
    # ═══════════════════════════════════════════════════════════════════════════
    if _PRINT_DEBUG:
        print(f"[BATCH] Uniendo {len(batch_files)} lotes → {ruta_salida}")
    doc_final = fitz.open()
    total_paginas = 0
    for bp in batch_files:
        _check_cancel()
        src = fitz.open(bp)
        doc_final.insert_pdf(src)
        total_paginas += src.page_count
        src.close()

    _save_opts = (
        save_opts_final
        if save_opts_final is not None
        else dict(garbage=2, deflate=True, clean=False, use_objstms=1)
    )
    # Subconjuntar fuentes siempre (como PageNumber): reduce los TTF embebidos
    # (p.ej. marcas de texto) a los glifos usados y deduplica las copias
    # duplicadas ×lote al unir los batches. Sin esto, cada batch aporta su
    # copia completa de la fuente (Arial 773KB×10 = ~8MB).
    try:
        doc_final.subset_fonts()
    except Exception as e_subset:
        if _PRINT_DEBUG:
            print(f"[BATCH][WARN] subset_fonts falló: {e_subset}")
    _check_cancel()
    doc_final.save(ruta_salida, **_save_opts)
    doc_final.close()
    fitz.TOOLS.store_shrink(100)

    if _PRINT_DEBUG:
        print(f"PDF guardado: {total_paginas} páginas")
        print(f"Ubicacion: {ruta_salida}")

    # Eliminar carpeta temporal completa
    try:
        shutil.rmtree(temp_dir)
        if _PRINT_DEBUG:
            print(f"[BATCH] Carpeta temporal eliminada: {temp_dir}")
    except Exception as e:
        if _PRINT_DEBUG:
            print(f"[BATCH][WARN] No se pudo eliminar la carpeta temporal: {e}")

    # ═══════════════════════════════════════════════════════════════════════════
    # GENERAR ARCHIVO XEROX (si está activado)
    # ═══════════════════════════════════════════════════════════════════════════
    if crear_xerox and num_copias > 1:
        try:
            from fiery_export import (
                generar_listas_xerox_para_pliegos,
                generar_archivo_xerox_para_pliegos,
            )

            if _PRINT_DEBUG:
                print(f"\n{'='*80}")
                print(f"GENERANDO ARCHIVO XEROX PARA PLIEGOS")
                print(f"{'='*80}")

            # Generar listas agrupadas por copia
            listas_xerox = generar_listas_xerox_para_pliegos(
                ordenamiento_pliegos=ordenamiento,
                num_copias=num_copias,
                modo_doble_cara=hay_doble_cara,
            )

            if listas_xerox:
                # Crear nombre de archivo Xerox igual que el PDF pero con sufijo '_CopyIndex.txt'
                base_path = os.path.splitext(ruta_salida)[0]
                archivo_xerox = f"{base_path}_CopyIndex.txt"

                # Generar archivo
                exito = generar_archivo_xerox_para_pliegos(
                    listas_xerox, archivo_xerox, modo_doble_cara=hay_doble_cara
                )

                if exito:
                    if _PRINT_DEBUG:
                        print(f"[SUCCESS] Archivo Xerox generado: {archivo_xerox}")
                else:
                    logger.error("[XEROX] No se pudo generar el archivo Xerox")
            else:
                if _PRINT_DEBUG:
                    print(
                        f"[WARNING] No se generaron listas Xerox (copias insuficientes o dict vacío)"
                    )

        except Exception:
            logger.exception("[XEROX] Error al generar archivo Xerox")

    return ruta_salida
