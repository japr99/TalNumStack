"""
Módulo para la ventana "Crear PDF Ordenado"
Permite configurar, visualizar y generar PDFs ordenados para imposición
Compatible con PyInstaller en macOS y Windows
"""

import flet as ft
from types import SimpleNamespace
import os
import platform
import shutil
import base64
import threading
import asyncio

# import json  # No utilizado por ahora
from grafico import (
    grafico_datos,
    generar_ordenamiento_pdf_montaje,
)  # , generar_listas_fiery  # No utilizado por ahora

# from fiery_export import generar_archivo_xerox_manual  # No utilizado por ahora
from color_design import *

# internacionalización
from lang import t

# Silenciar prints de depuración en este módulo por defecto.
# Para activar, cambiar _PRINT_DEBUG = True durante desarrollo.
_PRINT_DEBUG = False
if not _PRINT_DEBUG:

    def _no_print(*args, **kwargs):
        return None

    print = _no_print


# Timestamp de sesión para nombres de imágenes (invalida caché de Flet)
import time

# Variables globales persistentes para conservar datos entre aperturas
_archivo_seleccionado_pdf = {"ruta": "", "nombre": "", "paginas": 0}
_ordenamiento_calculado_pdf = {"ordenamiento": None, "paginas_requeridas": 0}
TIMESTAMP_SESION_IMAGENES = str(int(time.time()))

# Importar ventana de imposición
# Importar ventana de imposición (Lazy import para evitar ciclos)
crear_ventana_ordenar_imposicion_externa = None

# ============================================================================
# VARIABLE GLOBAL PARA COMPARTIR PDF ORDENADO CON IMPOSICIÓN
# ============================================================================

_PDF_ORDENADO_TEMP = None
_RUTA_PDF_ORIGINAL = None


def obtener_pdf_ordenado_temp():
    """Obtiene la ruta del PDF ordenado temporal."""
    global _PDF_ORDENADO_TEMP
    return _PDF_ORDENADO_TEMP


def obtener_ruta_pdf_original():
    """Obtiene la ruta original del PDF seleccionado por el usuario."""
    global _RUTA_PDF_ORIGINAL
    return _RUTA_PDF_ORIGINAL


def guardar_ruta_pdf_original(ruta):
    """Guarda la ruta original del PDF."""
    global _RUTA_PDF_ORIGINAL
    _RUTA_PDF_ORIGINAL = ruta
    print(f"[PDF_ORIGINAL] Guardada ruta original: {ruta}")


def guardar_pdf_ordenado_temp(pdf_path):
    """Guarda la ruta del PDF ordenado temporal."""
    global _PDF_ORDENADO_TEMP
    _PDF_ORDENADO_TEMP = pdf_path
    print(f"[PDF_TEMP] Guardada ruta del PDF temporal: {pdf_path}")


def limpiar_pdf_ordenado_temp():
    """Limpia la referencia al PDF ordenado temporal."""
    global _PDF_ORDENADO_TEMP
    _PDF_ORDENADO_TEMP = None


# ============================================================================
# VARIABLE GLOBAL PARA COMPARTIR ORDENAMIENTO CON IMPOSICIÓN
# ============================================================================

_ORDENAMIENTO_CALCULADO = None


def guardar_ordenamiento_calculado(ordenamiento):
    """Guarda el ordenamiento calculado para que imposición lo use."""
    global _ORDENAMIENTO_CALCULADO
    _ORDENAMIENTO_CALCULADO = ordenamiento


def obtener_ordenamiento_calculado():
    """Obtiene el ordenamiento calculado desde pdf_ordenado_ui."""
    global _ORDENAMIENTO_CALCULADO
    return _ORDENAMIENTO_CALCULADO


def limpiar_ordenamiento_calculado():
    """Limpia el ordenamiento calculado."""
    global _ORDENAMIENTO_CALCULADO
    _ORDENAMIENTO_CALCULADO = None


# ============================================================================
# GESTIÓN DE DIRECTORIO TEMPORAL (COMPATIBLE CON PYINSTALLER)
# ============================================================================

_SESSION_TEMP_DIR = None


def limpiar_cache_completa():
    """Limpia TODO el contenido del directorio de cache."""
    global _SESSION_TEMP_DIR

    if _SESSION_TEMP_DIR and os.path.exists(_SESSION_TEMP_DIR):
        try:
            # Eliminar todo el contenido pero mantener el directorio
            # EXCEPTO el archivo de preferencias y caches persistentes de fuentes
            # Archivos que NUNCA deben eliminarse al limpiar cache
            archivos_a_preservar = {
                "preferencias_imposicion.json",
                "preferences.json",
                "talnumstack_errors.log",
            }
            directorios_persistentes = {
                "font_cache",
                "fonts_prefs",
                "font_metrics",
                "fonts",
            }

            for item in os.listdir(_SESSION_TEMP_DIR):
                # Preservar archivos concretos
                if item in archivos_a_preservar:
                    continue

                # Preservar directorios relacionados con cachés persistentes de fuentes
                if item in directorios_persistentes:
                    continue

                item_path = os.path.join(_SESSION_TEMP_DIR, item)
                if os.path.isfile(item_path):
                    try:
                        os.remove(item_path)
                    except Exception:
                        pass
                elif os.path.isdir(item_path):
                    try:
                        shutil.rmtree(item_path)
                    except Exception:
                        pass
            print(
                f"[INFO] Cache limpiada (preservando preferencias y caches persistentes): {_SESSION_TEMP_DIR}"
            )
        except Exception as e:
            print(f"[WARNING] No se pudo limpiar cache completa: {e}")


def obtener_directorio_temp_sesion():
    """
    Obtiene o crea directorio de cache para la aplicación.
    Ubicaciones específicas por plataforma:
    - macOS: ~/Library/Application Support/TalNumStack
    - Windows: %LOCALAPPDATA%/Temp/TalNumStack
    - Linux/otros: ~/.cache/TalNumStack

    IMPORTANTE: Se limpia TODO el contenido al inicio y al cerrar ventana de imposición.
    """
    global _SESSION_TEMP_DIR

    if _SESSION_TEMP_DIR is None:
        sistema = platform.system()

        if sistema == "Darwin":  # macOS
            # Usar el directorio de Application Support de la app como cache.
            # NO eliminar nunca los archivos de preferencias y log listados
            # en `archivos_a_preservar`. Solo se eliminarán caches y carpetas
            # temporales como 'imagenes'.
            _SESSION_TEMP_DIR = os.path.expanduser(
                "~/Library/Application Support/TalNumStack"
            )
        elif sistema == "Windows":
            # %LOCALAPPDATA% normalmente es C:\Users\[usuario]\AppData\Local
            localappdata = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
            _SESSION_TEMP_DIR = os.path.join(localappdata, "Temp", "TalNumStack")
        else:  # Linux u otros
            # Fallback a directorio temporal del usuario
            _SESSION_TEMP_DIR = os.path.join(
                os.path.expanduser("~"), ".cache", "TalNumStack"
            )

        # Crear directorio si no existe
        os.makedirs(_SESSION_TEMP_DIR, exist_ok=True)

        # LIMPIAR TODO el contenido al inicio (por si hubo crash anterior)
        limpiar_cache_completa()

        # print(f"[INFO] Directorio de cache: {_SESSION_TEMP_DIR}")

    return _SESSION_TEMP_DIR


def limpiar_temp_sesion():
    """Limpia el contenido del directorio de cache (llamado al cerrar ventana imposición)."""
    # Limpiar archivos en disco
    limpiar_cache_completa()
    # Limpiar cache en memoria del pliego actual (imagenes en RAM)
    try:
        limpiar_cache_pliego()
    except Exception:
        pass
    # Limpiar tracking de pliegos cacheados
    try:
        limpiar_tracking_cache()
    except Exception:
        pass
    # Limpiar referencias globales al PDF y al ordenamiento calculado
    try:
        limpiar_pdf_ordenado_temp()
    except Exception:
        pass
    try:
        limpiar_ordenamiento_calculado()
    except Exception:
        pass


# ============================================================================
# GESTIÓN DE PDF TEMPORAL
# ============================================================================


def crear_ruta_pdf_temp(nombre_base="documento"):
    """Crea ruta para el PDF temporal ordenado."""
    temp_dir = obtener_directorio_temp_sesion()
    return os.path.join(temp_dir, f"{nombre_base}_ordenado_temp.pdf")


def copiar_pdf_a_temporal(pdf_original_path):
    """
    Copia PDF original a carpeta temporal SIN reordenar páginas.
    Esta es la nueva estrategia optimizada que elimina el costoso reordenamiento.

    Args:
        pdf_original_path: Ruta del PDF original

    Returns:
        str: Ruta del PDF copiado en temporal
    """
    import shutil

    temp_dir = obtener_directorio_temp_sesion()
    nombre_base = os.path.splitext(os.path.basename(pdf_original_path))[0]
    # Evitar sufijos duplicados: si el archivo original ya tenía sufijo temporal,
    # eliminarlo antes de crear el nuevo nombre (previene _temp_temp)
    if nombre_base.endswith("_ordenado_temp"):
        nombre_base = nombre_base[: -len("_ordenado_temp")]
    elif nombre_base.endswith("_temp"):
        nombre_base = nombre_base[: -len("_temp")]

    pdf_temp_path = os.path.join(temp_dir, f"{nombre_base}_temp.pdf")

    try:
        # Si el origen y destino coinciden (ya es un temp en la misma carpeta), no copiar
        if os.path.abspath(pdf_original_path) == os.path.abspath(pdf_temp_path):
            print(f"[OPTIMIZACIÓN] El PDF ya está en temporal: {pdf_temp_path}")
            return pdf_temp_path

        shutil.copy2(pdf_original_path, pdf_temp_path)
        print(f"[OPTIMIZACIÓN] PDF copiado a temporal (sin reordenar): {pdf_temp_path}")
        return pdf_temp_path
    except Exception as ex:
        print(f"[ERROR] Error copiando PDF a temporal: {ex}")
        return None


# ============================================================================
# GESTIÓN DE IMÁGENES EN DISCO (CON CACHE INTELIGENTE)
# ============================================================================


def regenerar_timestamp_sesion():
    """Regenera timestamp de sesión para forzar nuevos nombres de archivo."""
    global TIMESTAMP_SESION_IMAGENES
    TIMESTAMP_SESION_IMAGENES = str(int(time.time()))
    print(f"[TIMESTAMP] Nuevo timestamp de sesión: {TIMESTAMP_SESION_IMAGENES}")


def obtener_directorio_imagenes():
    """Obtiene o crea subdirectorio para imágenes."""
    temp_dir = obtener_directorio_temp_sesion()
    imagenes_dir = os.path.join(temp_dir, "imagenes")
    os.makedirs(imagenes_dir, exist_ok=True)
    return imagenes_dir


def obtener_ruta_imagen(numero_pagina):
    """Obtiene ruta de archivo para una imagen con timestamp."""
    imagenes_dir = obtener_directorio_imagenes()
    return os.path.join(
        imagenes_dir, f"pagina_{numero_pagina:04d}_{TIMESTAMP_SESION_IMAGENES}.png"
    )


def guardar_imagen_disco(imagen_base64, numero_pagina):
    """
    Guarda imagen en disco.

    Args:
        imagen_base64: Imagen codificada en base64
        numero_pagina: Número de página (0-based)

    Returns:
        str: Ruta del archivo guardado
    """
    ruta_imagen = obtener_ruta_imagen(numero_pagina)

    # Decodificar y guardar
    imagen_bytes = base64.b64decode(imagen_base64)
    with open(ruta_imagen, "wb") as f:
        f.write(imagen_bytes)

    return ruta_imagen


def cargar_imagen_disco(numero_pagina):
    """
    Carga imagen desde disco.

    Args:
        numero_pagina: Número de página (0-based)

    Returns:
        str: Imagen en base64, o None si no existe
    """
    ruta_imagen = obtener_ruta_imagen(numero_pagina)

    if not os.path.exists(ruta_imagen):
        return None

    # Leer y codificar
    with open(ruta_imagen, "rb") as f:
        imagen_bytes = f.read()

    return base64.b64encode(imagen_bytes).decode("utf-8")


# ============================================================================
# CACHE INTELIGENTE (SOLO PLIEGO ACTUAL EN RAM)
# ============================================================================

_CACHE_PLIEGO_ACTUAL = {}
_PLIEGO_ACTUAL_NUM = None


def cachear_pliego(numero_pliego, imagenes_pliego):
    """
    Cachea las imágenes del pliego actual en RAM.

    Args:
        numero_pliego: Número del pliego
        imagenes_pliego: Dict {numero_pagina: imagen_base64}
    """
    global _CACHE_PLIEGO_ACTUAL, _PLIEGO_ACTUAL_NUM

    # Limpiar cache anterior
    _CACHE_PLIEGO_ACTUAL.clear()

    # Cachear nuevo pliego
    _CACHE_PLIEGO_ACTUAL = imagenes_pliego.copy()
    _PLIEGO_ACTUAL_NUM = numero_pliego

    print(
        f"[INFO] Pliego {numero_pliego} cacheado en RAM ({len(imagenes_pliego)} imágenes)"
    )


def obtener_imagen_cache(numero_pagina):
    """Obtiene imagen del cache del pliego actual."""
    return _CACHE_PLIEGO_ACTUAL.get(numero_pagina)


def limpiar_cache_pliego():
    """Limpia el cache del pliego actual."""
    global _CACHE_PLIEGO_ACTUAL, _PLIEGO_ACTUAL_NUM
    _CACHE_PLIEGO_ACTUAL.clear()
    _PLIEGO_ACTUAL_NUM = None


# ============================================================================
# FUNCIÓN PRINCIPAL: OBTENER IMAGEN (DISCO + CACHE)
# ============================================================================


def obtener_imagen_pagina(pdf_path, numero_pagina, dpi=150):
    """
    Obtiene imagen de una página, usando cache si está disponible,
    sino carga desde disco, y si no existe la extrae del PDF.

    Args:
        pdf_path: Ruta del PDF
        numero_pagina: Número de página (0-based)
        dpi: Resolución de la imagen

    Returns:
        str: Imagen en base64
    """
    # 1. Intentar obtener del cache RAM
    imagen_cache = obtener_imagen_cache(numero_pagina)
    if imagen_cache:
        return imagen_cache

    # 2. Intentar cargar desde disco
    imagen_disco = cargar_imagen_disco(numero_pagina)
    if imagen_disco:
        return imagen_disco

    # 3. Extraer del PDF y guardar en disco
    from impo_ui import extraer_pagina_como_imagen

    imagen_base64 = extraer_pagina_como_imagen(pdf_path, numero_pagina, dpi)

    # Guardar en disco para futuros accesos
    guardar_imagen_disco(imagen_base64, numero_pagina)

    return imagen_base64


# ============================================================================
# UTILIDADES
# ============================================================================


def es_pliego_dorso(numero_pliego):
    """
    Determina si un pliego es cara o dorso.

    Args:
        numero_pliego: Número del pliego (1-based)

    Returns:
        bool: True si es dorso, False si es cara

    Lógica:
        - Pliego 1 = CARA
        - Pliego 2 = DORSO
        - Pliego 3 = CARA
        - Pliego 4 = DORSO
        - ...
    """
    return numero_pliego % 2 == 0


def grid_dorso(grid_rows, grid_cols, lista):
    """
    Construye el dorso a partir de la lista de cara aplicando la inversión por filas

    Args:
        grid_rows: número de filas en el pliego
        grid_cols: número de columnas en el pliego
        lista: lista lineal de números de la CARA (orden fila-por-fila)

    Devuelve:
        lista transformada donde cada bloque de tamaño grid_cols es invertido y
        cada valor incrementado en 1 (x + 1) tal como pidió el usuario.

    Ejemplo (grid_rows=2, grid_cols=3):
        lista = [1,41,81,121,161,201]
        -> [82,42,2,202,162,122]
    """
    if not lista:
        return []

    # Seguridad: si grid_cols <= 0 usar longitud total para evitar división por cero
    if not grid_cols or grid_cols <= 0:
        grid_cols = len(lista)

    resultado = [
        x + 1
        for i in range(0, len(lista), grid_cols)
        for x in reversed(lista[i : i + grid_cols])
    ]

    # print(f"resultado dorso para grid {grid_rows}x{grid_cols} y lista {lista} -> {resultado}")
    return resultado


# ============================================================================
# EXTRACCIÓN DE IMÁGENES DESDE PDF
# ============================================================================


def extraer_pagina_como_imagen(pdf_path, num_pagina, dpi=150):
    """
    Extrae una página del PDF como imagen base64.

    Args:
        pdf_path: Ruta del PDF
        num_pagina: Número de página (0-based)
        dpi: Resolución

    Returns:
        str: Imagen en base64, o None si error
    """
    import fitz
    import base64

    try:
        doc = fitz.open(pdf_path)
        if num_pagina >= len(doc):
            doc.close()
            return None

        page = doc[num_pagina]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")
        img_base64 = base64.b64encode(img_bytes).decode()
        doc.close()
        return img_base64
    except Exception as e:
        print(f"[ERROR] Error extrayendo página {num_pagina}: {e}")
        return None


# ============================================================================
# ÍNDICE COMPLETO DE PLIEGOS CON ESTADO DE CACHE
# ============================================================================

_INDICE_PLIEGOS = {}  # {pliego_num: {'inicio': 0, 'fin': 3, 'cacheado': False}}


def crear_indice_completo_pliegos(ordenamiento_pdf, paginas_por_pliego=4):
    """
    Crea el índice COMPLETO de todos los pliegos con sus rangos de imágenes.
    Este índice se crea UNA VEZ al inicio, ANTES de cachear ninguna imagen.

    Args:
        ordenamiento_pdf: Diccionario de ordenamiento
        paginas_por_pliego: Número de páginas por pliego (default 4)

    Returns:
        dict: Índice completo {pliego_num: {'inicio': idx_inicio, 'fin': idx_fin, 'cacheado': False}}
    """
    global _INDICE_PLIEGOS
    _INDICE_PLIEGOS.clear()

    # Obtener todos los pliegos del ordenamiento
    total_pliegos = len([k for k in ordenamiento_pdf.keys() if isinstance(k, int)])

    # print(f"[ÍNDICE] Creando índice completo para {total_pliegos} pliegos")

    for pliego_num in range(1, total_pliegos + 1):
        # Calcular rango de índices globales para este pliego
        inicio = (pliego_num - 1) * paginas_por_pliego
        fin = inicio + paginas_por_pliego - 1

        _INDICE_PLIEGOS[pliego_num] = {
            "inicio": inicio,
            "fin": fin,
            "cacheado": False,  # Inicialmente ninguno está cacheado
        }

        # print(f"[ÍNDICE] Pliego {pliego_num} → índices globales [{inicio}-{fin}] cacheado=False")

    # print(f"[ÍNDICE] Índice completo creado: {len(_INDICE_PLIEGOS)} pliegos registrados")
    return _INDICE_PLIEGOS


def marcar_pliego_cacheado(numero_pliego):
    """Marca un pliego como cacheado en el índice."""
    if numero_pliego in _INDICE_PLIEGOS:
        _INDICE_PLIEGOS[numero_pliego]["cacheado"] = True
        # print(f"[ÍNDICE] Pliego {numero_pliego} marcado como cacheado")


def esta_pliego_cacheado(numero_pliego):
    """Verifica si un pliego está cacheado consultando el índice."""
    if numero_pliego in _INDICE_PLIEGOS:
        return _INDICE_PLIEGOS[numero_pliego]["cacheado"]
    return False


def obtener_info_pliego(numero_pliego):
    """Obtiene la información completa de un pliego del índice."""
    return _INDICE_PLIEGOS.get(numero_pliego, None)


def obtener_total_pliegos_indice():
    """Obtiene el total de pliegos registrados en el índice."""
    return len(_INDICE_PLIEGOS)


def limpiar_tracking_cache():
    """Limpia el índice de pliegos."""
    _INDICE_PLIEGOS.clear()
    print("[ÍNDICE] Índice limpiado")


def restaurar_estado_desde_impo_ui():
    """Restaura el estado de PDF ordenado desde impo_ui (al cargar un trabajo)."""
    global _archivo_seleccionado_pdf, _ordenamiento_calculado_pdf, _RUTA_PDF_ORIGINAL

    try:
        import impo_ui

        estado = impo_ui._estado_impo_ui

        if not estado:
            print("[PDF_ORDENADO] No hay estado en impo_ui para restaurar")
            return

        # ✅ OBTENER DATOS ACTUALES DE LA VARIABLE EN MEMORIA (no del estado guardado)
        ruta_temporal_actual = impo_ui._archivo_seleccionado.get("ruta", "")
        ruta_original = impo_ui._archivo_seleccionado.get("ruta_original", "")
        nombre_pdf = impo_ui._archivo_seleccionado.get(
            "nombre", impo_ui._archivo_seleccionado.get("nombre_archivo", "")
        )
        paginas_pdf = impo_ui._archivo_seleccionado.get(
            "paginas", impo_ui._archivo_seleccionado.get("num_paginas", 0)
        )

        # Restaurar archivo seleccionado - metadata + ruta temporal ACTUAL
        _archivo_seleccionado_pdf["ruta"] = (
            ruta_temporal_actual  # ✅ Ruta temporal en memoria
        )
        _archivo_seleccionado_pdf["ruta_original"] = (
            ruta_original  # ✅ Ruta original del PDF
        )
        _archivo_seleccionado_pdf["nombre"] = nombre_pdf  # ✅ Nombre del PDF
        _archivo_seleccionado_pdf["paginas"] = paginas_pdf  # ✅ Páginas del PDF

        # Restaurar también en variable global para compartir
        if ruta_original:
            _RUTA_PDF_ORIGINAL = ruta_original
            print(f"[PDF_ORDENADO] Ruta original restaurada en global: {ruta_original}")

        # Restaurar ordenamiento. Preferir el ordenamiento guardado en el
        # estado completo (`estado`) pero si no está presente, intentar leer
        # desde la variable interna de impo_ui (`_ordenamiento_calculado`).
        orden_from_estado = estado.get("ordenamiento")
        paginas_req_from_estado = estado.get("ordenamiento_paginas_requeridas", 0)

        if orden_from_estado:
            _ordenamiento_calculado_pdf["ordenamiento"] = orden_from_estado
            _ordenamiento_calculado_pdf["paginas_requeridas"] = paginas_req_from_estado
        else:
            # Fallback: leer desde impo_ui._ordenamiento_calculado si existe
            try:
                orden_global = (
                    impo_ui._ordenamiento_calculado
                    if hasattr(impo_ui, "_ordenamiento_calculado")
                    else None
                )
                if orden_global and isinstance(orden_global, dict):
                    _ordenamiento_calculado_pdf["ordenamiento"] = (
                        orden_global.get("ordenamiento") or orden_global
                    )
                    _ordenamiento_calculado_pdf["paginas_requeridas"] = (
                        orden_global.get("paginas_requeridas", paginas_req_from_estado)
                        if isinstance(orden_global, dict)
                        else paginas_req_from_estado
                    )
                else:
                    _ordenamiento_calculado_pdf["ordenamiento"] = None
                    _ordenamiento_calculado_pdf["paginas_requeridas"] = (
                        paginas_req_from_estado
                    )
            except Exception:
                _ordenamiento_calculado_pdf["ordenamiento"] = None
                _ordenamiento_calculado_pdf["paginas_requeridas"] = (
                    paginas_req_from_estado
                )

        print(
            f"[PDF_ORDENADO] ✅ Estado restaurado: {_archivo_seleccionado_pdf['nombre']} ({_archivo_seleccionado_pdf['paginas']} págs)"
        )
        print(
            f"[PDF_ORDENADO]    Ruta temporal actual: {ruta_temporal_actual if ruta_temporal_actual else 'N/A'}"
        )
        print(
            f"[PDF_ORDENADO]    Ruta original: {ruta_original if ruta_original else 'N/A'}"
        )
        print(
            f"[PDF_ORDENADO]    Ordenamiento: {'OK' if _ordenamiento_calculado_pdf['ordenamiento'] else 'None'}"
        )

    except Exception as ex:
        print(f"[PDF_ORDENADO] ❌ Error restaurando estado: {ex}")
        import traceback

        traceback.print_exc()


def limpiar_estado_pdf_ordenado():
    """Limpia todo el estado de PDF ordenado al crear un nuevo proyecto."""
    global _archivo_seleccionado_pdf, _ordenamiento_calculado_pdf, _PDF_ORDENADO_TEMP, _ORDENAMIENTO_CALCULADO

    print("[PDF_ORDENADO] Limpiando estado completo...")

    # Limpiar archivo seleccionado
    _archivo_seleccionado_pdf = {"ruta": "", "nombre": "", "paginas": 0}

    # Limpiar ordenamiento calculado
    _ordenamiento_calculado_pdf = {"ordenamiento": None, "paginas_requeridas": 0}

    # Limpiar PDFs temporales
    _PDF_ORDENADO_TEMP = None
    _ORDENAMIENTO_CALCULADO = None

    # Limpiar cache de imágenes
    limpiar_cache_pliego()
    limpiar_tracking_cache()

    # Limpiar dropdown en estado compartido de impo_ui
    try:
        import impo_ui

        impo_ui._estado_impo_ui["dropdown_doble_cara"] = "cara"
        print("[PDF_ORDENADO] Dropdown resetado a 'cara' en estado compartido")
    except Exception as ex:
        print(f"[PDF_ORDENADO] No se pudo resetear dropdown en impo_ui: {ex}")

    print("[PDF_ORDENADO] Estado limpiado completamente")


def precachear_pliegos_siguientes(pdf_path, ordenamiento_pdf, pliego_actual, ventana=4):
    """
    Precachea los próximos N pliegos después del pliego actual.
    Solo cachea si NO están ya cacheados.

    Args:
        pdf_path: Ruta del PDF original
        ordenamiento_pdf: Diccionario de ordenamiento
        pliego_actual: Número del pliego actual
        ventana: Cuántos pliegos precachear (default 4)
    """
    total_pliegos = len([k for k in ordenamiento_pdf.keys() if isinstance(k, int)])

    for offset in range(1, ventana + 1):
        pliego_siguiente = pliego_actual + offset

        if pliego_siguiente > total_pliegos:
            break

        if not esta_pliego_cacheado(pliego_siguiente):
            try:
                paginas = obtener_paginas_del_pliego(ordenamiento_pdf, pliego_siguiente)
                if paginas:
                    # Extraer y cachear (extraer_imagenes_pliego ya guarda en disco)
                    # Pasar pliego_siguiente para índice global correcto
                    extraer_imagenes_pliego(
                        pdf_path, paginas, pliego_siguiente, len(paginas), dpi=100
                    )
                    marcar_pliego_cacheado(pliego_siguiente)
                    if _PRINT_DEBUG:
                        print(f"[PRECACHE] Pliego {pliego_siguiente} pre-cacheado")
            except Exception as ex:
                if _PRINT_DEBUG:
                    print(
                        f"[PRECACHE ERROR] Error pre-cacheando pliego {pliego_siguiente}: {ex}"
                    )


# ============================================================================
# EXTRACCIÓN Y MAPEO DE IMÁGENES
# ============================================================================


def extraer_imagenes_pliego(
    pdf_path, paginas_pliego, numero_pliego, paginas_por_pliego=4, dpi=150
):
    """
    Extrae las imágenes de las páginas de un pliego desde PDF ORIGINAL.
    Guarda imágenes con ÍNDICE GLOBAL para evitar sobreescritura entre pliegos.

    ARQUITECTURA CRÍTICA:
    - Pliego 1: índices globales 0-3  (pagina_0000.png - pagina_0003.png)
    - Pliego 2: índices globales 4-7  (pagina_0004.png - pagina_0007.png)
    - Pliego 3: índices globales 8-11 (pagina_0008.png - pagina_0011.png)

    Args:
        pdf_path: Ruta del PDF ORIGINAL (sin reordenar)
        paginas_pliego: Lista de números de página del PDF original (1-based) [11, 36, 61, 86]
        numero_pliego: Número del pliego (1-based) para calcular offset global
        paginas_por_pliego: Número de páginas por pliego (default 4)
        dpi: Resolución de las imágenes

    Returns:
        dict: {indice_global: imagen_base64}  # {0: img1, 1: img2, 2: img3, 3: img4}
    """
    imagenes = {}

    # Calcular offset global: (numero_pliego - 1) * paginas_por_pliego
    # Pliego 1 (1-1)*4 = 0 → índices 0,1,2,3
    # Pliego 2 (2-1)*4 = 4 → índices 4,5,6,7
    offset_global = (numero_pliego - 1) * paginas_por_pliego

    for idx_local, num_pagina in enumerate(paginas_pliego):
        # Calcular índice global
        idx_global = offset_global + idx_local

        # Convertir a 0-based para la función de extracción del PDF
        num_pagina_0based = num_pagina - 1

        # Verificar si imagen YA existe en disco (con índice global)
        ruta_imagen = obtener_ruta_imagen(idx_global)

        if os.path.exists(ruta_imagen):
            # Cargar desde disco (rápido)
            imagen = cargar_imagen_disco(idx_global)
            # print(f"[CACHE HIT] Imagen global {idx_global} (pliego {numero_pliego}, local {idx_local}) cargada desde disco (página PDF {num_pagina})")
        else:
            # Extraer del PDF original y guardar con índice global
            imagen = extraer_pagina_como_imagen(pdf_path, num_pagina_0based, dpi)
            if imagen:
                guardar_imagen_disco(imagen, idx_global)
                # print(f"[CACHE MISS] Imagen global {idx_global} (pliego {numero_pliego}, local {idx_local}) extraída y guardada (página PDF {num_pagina})")

        if imagen:
            imagenes[idx_local] = imagen  # Retornar con índice local para mapeo en grid

    return imagenes


def obtener_pliegos_del_ordenamiento(ordenamiento_pdf):
    """
    Obtiene la lista de pliegos del ordenamiento.

    Args:
        ordenamiento_pdf: Diccionario de ordenamiento

    Returns:
        list: Lista de números de pliego ordenados
    """
    # print(f"[DEBUG] ordenamiento_pdf completo: {ordenamiento_pdf}")
    # print(f"[DEBUG] ordenamiento_pdf keys: {list(ordenamiento_pdf.keys())}")

    pliegos = []

    for key in ordenamiento_pdf.keys():
        if isinstance(key, int):
            pliegos.append(key)

    # print(f"[DEBUG] pliegos encontrados: {pliegos}")
    return sorted(pliegos)


def obtener_paginas_del_pliego(ordenamiento_pdf, numero_pliego):
    """
    Obtiene las páginas que pertenecen a un pliego específico.

    Args:
        ordenamiento_pdf: Diccionario de ordenamiento
        numero_pliego: Número del pliego (1-based)

    Returns:
        list: Lista de números de página del pliego
    """
    # print(f"[DEBUG] Buscando pliego {numero_pliego} en ordenamiento")
    # print(f"[DEBUG] ordenamiento_pdf[{numero_pliego}] = {ordenamiento_pdf.get(numero_pliego, 'NO EXISTE')}")

    if numero_pliego not in ordenamiento_pdf:
        return []

    datos_pliego = ordenamiento_pdf[numero_pliego]

    if isinstance(datos_pliego, dict) and "datos" in datos_pliego:
        # print(f"[DEBUG] Páginas del pliego {numero_pliego}: {datos_pliego['datos']}")
        return datos_pliego["datos"]

    # print(f"[DEBUG] datos_pliego no tiene estructura esperada: {datos_pliego}")
    return []


def mapear_imagenes_a_grid(
    ordenamiento_pdf, numero_pliego, imagenes_cache, grid_config
):
    """
    Mapea las imágenes del pliego a las posiciones del grid.

    Args:
        ordenamiento_pdf: Diccionario de ordenamiento
        numero_pliego: Número del pliego actual
        imagenes_cache: Cache de imágenes {numero_pagina: imagen_base64}
        grid_config: Configuración del grid {rows, cols}

    Returns:
        list: Lista de listas (grid) con las imágenes
              [[img1, img2], [img3, img4]] para grid 2x2
    """
    rows = grid_config["rows"]
    cols = grid_config["cols"]

    # Obtener páginas del pliego
    paginas = obtener_paginas_del_pliego(ordenamiento_pdf, numero_pliego)

    # Crear grid vacío
    grid = [[None for _ in range(cols)] for _ in range(rows)]

    # Llenar grid con imágenes
    # Las páginas se colocan en orden: fila por fila, de izquierda a derecha
    idx = 0
    for row in range(rows):
        for col in range(cols):
            if idx < len(paginas):
                num_pagina = paginas[idx]
                if num_pagina in imagenes_cache:
                    grid[row][col] = {
                        "numero_pagina": num_pagina,
                        "imagen": imagenes_cache[num_pagina],
                    }
                idx += 1

    return grid


# ============================================================================
# RENDERIZADO DEL GRID CON IMÁGENES
# ============================================================================


def crear_celda_con_imagen(celda_data, ancho_celda=200, alto_celda=150):
    """
    Crea una celda del grid con la imagen y el número de página.

    Args:
        celda_data: Dict con 'numero_pagina' e 'imagen' (base64)
        ancho_celda: Ancho de la celda en px
        alto_celda: Alto de la celda en px

    Returns:
        ft.Container: Celda con imagen y overlay de número
    """
    if not celda_data:
        # Celda vacía
        return ft.Container(
            width=ancho_celda,
            height=alto_celda,
            bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.WHITE),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.3, ft.Colors.WHITE)),
            border_radius=4,
        )

    numero_pagina = celda_data["numero_pagina"]
    imagen_base64 = celda_data["imagen"]

    # Crear imagen
    imagen = ft.Image(
        src_base64=imagen_base64,
        width=ancho_celda,
        height=alto_celda,
        fit=ft.BoxFit.CONTAIN,
    )

    # Overlay con número de página
    numero_overlay = ft.Container(
        content=ft.Text(
            str(numero_pagina),
            size=14,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.WHITE,
        ),
        bgcolor=ft.Colors.with_opacity(0.7, ft.Colors.BLACK),
        padding=ft.Padding(4, 2, 4, 2),
        border_radius=4,
    )

    # Stack con imagen y número
    return ft.Container(
        content=ft.Stack(
            [
                imagen,
                ft.Container(
                    content=numero_overlay,
                    alignment=ft.Alignment.TOP_RIGHT,
                    padding=ft.Padding(4, 4, 4, 4),
                ),
            ]
        ),
        width=ancho_celda,
        height=alto_celda,
        border=ft.Border.all(2, TEXTO_COLOR_GENERICO),
        border_radius=4,
    )


def crear_grid_visual(grid_data, ancho_celda=200, alto_celda=150):
    """
    Crea el grid visual con todas las celdas.

    Args:
        grid_data: Lista de listas con datos de celdas
        ancho_celda: Ancho de cada celda
        alto_celda: Alto de cada celda

    Returns:
        ft.Column: Grid visual completo
    """
    filas = []

    for row_data in grid_data:
        celdas_fila = []
        for celda_data in row_data:
            celda = crear_celda_con_imagen(celda_data, ancho_celda, alto_celda)
            celdas_fila.append(celda)

        fila = ft.Row(
            controls=celdas_fila, spacing=8, alignment=ft.MainAxisAlignment.CENTER
        )
        filas.append(fila)

    return ft.Column(
        controls=filas, spacing=8, horizontal_alignment=ft.CrossAxisAlignment.CENTER
    )


# ============================================================================
# VIEWER DE PLIEGOS CON NAVEGACIÓN
# ============================================================================


def crear_viewer_pliegos(
    page, pdf_temp_path, pdf_original_path, ordenamiento_pdf, grid_config
):
    """
    Crea el viewer de pliegos con navegación.

    Args:
        page: Página de Flet
        pdf_temp_path: Ruta del PDF temporal (para compatibilidad, ya no se usa)
        pdf_original_path: Ruta del PDF original sin reordenar
        ordenamiento_pdf: Diccionario de ordenamiento
        grid_config: Configuración del grid {rows, cols}

    Returns:
        ft.AlertDialog: Diálogo con el viewer
    """
    # Obtener total de pliegos desde el índice completo
    total_pliegos = obtener_total_pliegos_indice()

    if total_pliegos == 0:
        from app_ui_items import mostrar_snackbar

        mostrar_snackbar(
            page, t("No hay pliegos para mostrar"), SNACKBAR_COLOR_ERROR, 3000
        )
        return None

    print(f"[VIEWER] Inicializando con {total_pliegos} pliegos (índice completo)")

    # Estado del viewer
    pliego_actual = {"numero": 1, "imagenes": {}, "grid_visual": None}

    # Controles de navegación
    texto_pliego = ft.Text(
        f"Pliego 1 de {total_pliegos}",
        size=18,
        weight=ft.FontWeight.BOLD,
        color=TEXTO_COLOR_GENERICO,
    )

    texto_tipo = ft.Text(
        "CARA", size=16, weight=ft.FontWeight.BOLD, color=SUCCESS_COLOR
    )

    # Container para el grid (se actualizará dinámicamente)
    container_grid = ft.Container(
        content=ft.Text(t("Cargando..."), size=16, color=TEXTO_COLOR_GENERICO),
        alignment=ft.Alignment.CENTER,
        height=400,
    )

    # ProgressBar para carga de imágenes
    progress_carga = ft.ProgressBar(
        width=400,
        height=10,
        visible=False,
        color=TEXTO_COLOR_GENERICO,
        bgcolor=ICONO_PREF_HOVER_COLOR,
    )

    def cargar_y_mostrar_pliego(numero_pliego):
        """Carga las imágenes de un pliego y actualiza el viewer con cache inteligente."""
        try:
            # Verificar si pliego está cacheado
            if esta_pliego_cacheado(numero_pliego):
                # Carga instantánea desde disco
                print(f"[CACHE HIT] Pliego {numero_pliego} cargado desde cache")
            else:
                # Mostrar progress solo si necesita cachear
                progress_carga.visible = True
                container_grid.content = ft.Column(
                    [
                        ft.Text(
                            t("Cargando imágenes..."),
                            size=16,
                            color=TEXTO_COLOR_GENERICO,
                        ),
                        progress_carga,
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                )
                container_grid.update()

            # Obtener páginas del pliego
            paginas = obtener_paginas_del_pliego(ordenamiento_pdf, numero_pliego)

            if not paginas:
                container_grid.content = ft.Text(
                    t("No hay páginas en este pliego"), size=16, color=ERROR_COLOR
                )
                progress_carga.visible = False
                container_grid.update()
                return

            # CRÍTICO: Extraer desde PDF ORIGINAL (no temporal)
            # pdf_original_path tiene el PDF original sin reordenar (parámetro de función)
            if not pdf_original_path:
                print("[ERROR] No hay PDF original disponible")
                return

            # Extraer imágenes (usa cache automático interno)
            # Pasar numero_pliego para índice global correcto
            imagenes = extraer_imagenes_pliego(
                pdf_original_path, paginas, numero_pliego, len(paginas), dpi=100
            )

            # Marcar pliego como cacheado
            marcar_pliego_cacheado(numero_pliego)

            # Cachear en RAM
            cachear_pliego(numero_pliego, imagenes)

            # Precachear próximos pliegos si no es el primer pliego
            if numero_pliego == 1:
                # Primer pliego: precachear próximos 4 (total 5)
                precachear_pliegos_siguientes(
                    pdf_original_path, ordenamiento_pdf, numero_pliego, ventana=4
                )
            elif not esta_pliego_cacheado(numero_pliego + 1):
                # No es primer pliego y siguiente no está cacheado: precachear próximos 4
                precachear_pliegos_siguientes(
                    pdf_original_path, ordenamiento_pdf, numero_pliego, ventana=4
                )

            # Mapear al grid
            grid_data = mapear_imagenes_a_grid(
                ordenamiento_pdf, numero_pliego, imagenes, grid_config
            )

            # Crear grid visual
            grid_visual = crear_grid_visual(grid_data, ancho_celda=180, alto_celda=120)

            # Actualizar container
            container_grid.content = grid_visual
            progress_carga.visible = False

            # Actualizar estado
            pliego_actual["numero"] = numero_pliego
            pliego_actual["imagenes"] = imagenes
            pliego_actual["grid_visual"] = grid_visual

            # Actualizar textos
            texto_pliego.value = f"Pliego {numero_pliego} de {total_pliegos}"

            # Determinar si es cara o dorso
            if es_pliego_dorso(numero_pliego):
                texto_tipo.value = "DORSO"
                texto_tipo.color = INFO_COLOR
            else:
                texto_tipo.value = "CARA"
                texto_tipo.color = SUCCESS_COLOR

            # Actualizar botones de navegación
            boton_anterior.disabled = numero_pliego <= 1
            boton_siguiente.disabled = numero_pliego >= total_pliegos

            # Actualizar UI
            container_grid.update()
            texto_pliego.update()
            texto_tipo.update()
            boton_anterior.update()
            boton_siguiente.update()

        except Exception as ex:
            print(f"[ERROR] Error al cargar pliego {numero_pliego}: {ex}")
            container_grid.content = ft.Text(
                f"Error: {str(ex)}", size=14, color=ERROR_COLOR
            )
            progress_carga.visible = False
            container_grid.update()

    def navegar_anterior(e):
        """Navega al pliego anterior."""
        numero_actual = pliego_actual["numero"]
        if numero_actual > 1:
            cargar_y_mostrar_pliego(numero_actual - 1)

    def navegar_siguiente(e):
        """Navega al pliego siguiente."""
        numero_actual = pliego_actual["numero"]
        if numero_actual < total_pliegos:
            cargar_y_mostrar_pliego(numero_actual + 1)

    # Botones de navegación
    boton_anterior = ft.IconButton(
        icon=ft.Icons.ARROW_BACK,
        icon_size=30,
        on_click=navegar_anterior,
        disabled=True,
        icon_color=TEXTO_COLOR_GENERICO,
        bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
    )

    boton_siguiente = ft.IconButton(
        icon=ft.Icons.ARROW_FORWARD,
        icon_size=30,
        on_click=navegar_siguiente,
        disabled=(total_pliegos <= 1),
        icon_color=TEXTO_COLOR_GENERICO,
        bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
    )

    # Crear diálogo
    dialog = ft.AlertDialog(
        modal=True,
        bgcolor=FONDO_ALERT_DIALOG,
        title=ft.Text(
            t("Vista Previa - PDF Ordenado"),
            weight=ft.FontWeight.BOLD,
            size=20,
            text_align=ft.TextAlign.CENTER,
            color=TEXTO_COLOR_GENERICO,
        ),
        content=ft.Container(
            content=ft.Column(
                [
                    # Barra de navegación
                    ft.Container(
                        content=ft.Row(
                            [
                                boton_anterior,
                                ft.Column(
                                    [texto_pliego, texto_tipo],
                                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                    spacing=4,
                                ),
                                boton_siguiente,
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        padding=ft.Padding(10, 10, 10, 10),
                        bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.WHITE),
                        border_radius=8,
                    ),
                    ft.Divider(color=TEXTO_COLOR_GENERICO),
                    # Grid de imágenes
                    container_grid,
                ],
                spacing=12,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            width=800,
            height=600,
            bgcolor=FONDO_ALERT_DIALOG,
        ),
        actions=[
            ft.Container(
                content=ft.Button(
                    content=t("Cerrar"),
                    width=120,
                    height=40,
                    bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                    on_click=lambda e: page.pop_dialog(),
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
                alignment=ft.Alignment.CENTER,
            )
        ],
    )

    # Cargar primer pliego automáticamente
    def cargar_inicial():
        cargar_y_mostrar_pliego(1)

    async def cargar_inicial_async():
        await asyncio.sleep(0.2)
        cargar_inicial()

    page.run_task(cargar_inicial_async)

    return dialog


# ============================================================================
# VENTANA PRINCIPAL
# ============================================================================

print(
    "🔥🔥🔥 MÓDULO pdf_ordenado_ui.py CARGADO/RECARGADO - TIMESTAMP: {0} 🔥🔥🔥".format(
        __import__("time").time()
    )
)


def crear_ventana_pdf_ordenado(
    page,
    on_guardar_trabajo=None,
    initial_project_modified=False,
    initial_project_path=None,
    initial_project_name="Sin título",
):
    global _archivo_seleccionado_pdf, _ordenamiento_calculado_pdf
    print("=" * 80)
    # print("[PDF_ORDENADO] ✅✅✅ FUNCIÓN crear_ventana_pdf_ordenado() EJECUTADA ✅✅✅")
    # print("="*80)
    """
    Crea la ventana principal para ordenar PDFs con vista previa.
    Integra la funcionalidad existente de crear_ventana_ordenar_pdfs
    con la nueva visualización de imágenes en grid.
    """

    # Restaurar estado solo si la imposición fue creada (impo_creada True)
    try:
        import impo_ui

        if impo_ui._estado_impo_ui.get("impo_creada", True):
            restaurar_estado_desde_impo_ui()
        else:
            # Limpiar variables globales para asegurar que no hay PDF cargado
            global _archivo_seleccionado_pdf, _ordenamiento_calculado_pdf, _PDF_ORDENADO_TEMP, _ORDENAMIENTO_CALCULADO
            _archivo_seleccionado_pdf = {"ruta": "", "nombre": "", "paginas": 0}
            _ordenamiento_calculado_pdf = {
                "ordenamiento": None,
                "paginas_requeridas": 0,
            }
            _PDF_ORDENADO_TEMP = None
            _ORDENAMIENTO_CALCULADO = None
            print(
                "[PDF_ORDENADO] No hay imposición activa, estado no restaurado, variables limpiadas"
            )

            # Cuando no hay imposición activa, NO aplicar preferencias aquí.
            # La carga de preferencias se realiza justo antes de generar la vista
            # previa (en `generar_vista_previa`) si `impo_creada` es False.
    except Exception:
        pass

    # Usar variables globales persistentes - NO recalcular nada
    archivo_seleccionado = _archivo_seleccionado_pdf
    ordenamiento_calculado = _ordenamiento_calculado_pdf

    # print(f"[PDF_ORDENADO] archivo_seleccionado actual: {archivo_seleccionado}")
    # print(f"[PDF_ORDENADO] ordenamiento_calculado actual: {ordenamiento_calculado}")

    pdf_temp_path = {"ruta": ""}

    # Controles de la interfaz - inicializar con datos del PDF si existe
    texto_archivo = ft.Text(
        (
            t(archivo_seleccionado["nombre"])
            if archivo_seleccionado["nombre"]
            else t("Ningún archivo seleccionado")
        ),
        size=16,
        color=TEXTO_COLOR_GENERICO,
        max_lines=2,
        overflow=ft.TextOverflow.ELLIPSIS,
    )
    texto_paginas = ft.Text(
        (
            t("Páginas: {0}").format(archivo_seleccionado["paginas"])
            if archivo_seleccionado["paginas"] > 0
            else t("Páginas: -")
        ),
        size=16,
        color=TEXTO_COLOR_GENERICO,
    )
    texto_paginas_requeridas = ft.Text(
        "", size=16, color=TEXTO_COLOR_GENERICO, visible=False
    )

    # Dropdown para doble cara
    # print("="*80)
    # print("[PDF_ORDENADO] >>>>>>> CREANDO DROPDOWN TIPO IMPRESIÓN <<<<<<<")

    # Inicializar valor desde múltiples fuentes (prioridad: ordenamiento > estado > default)
    valor_tipo_impresion = "cara"

    # 1. Intentar leer desde metadatos del ordenamiento (mayor prioridad)
    if ordenamiento_calculado.get("ordenamiento"):
        try:
            metadata = ordenamiento_calculado["ordenamiento"].get("_metadata", {})
            if metadata.get("doble_cara") is True:
                valor_tipo_impresion = "dorso"
                print(
                    f"[PDF_ORDENADO] Dropdown inicializado desde ordenamiento._metadata: {valor_tipo_impresion}"
                )
            else:
                print(
                    f"[PDF_ORDENADO] Ordenamiento tiene doble_cara=False, usando 'cara'"
                )
        except Exception as ex:
            print(f"[PDF_ORDENADO] Error leyendo metadata del ordenamiento: {ex}")

    # 2. Fallback: leer desde estado compartido de impo_ui
    if valor_tipo_impresion == "cara":  # Solo si no se obtuvo del ordenamiento
        try:
            import impo_ui

            valor_estado = impo_ui._estado_impo_ui.get("dropdown_doble_cara", "cara")
            if valor_estado:
                valor_tipo_impresion = valor_estado
                print(
                    f"[PDF_ORDENADO] Dropdown inicializado desde _estado_impo_ui: {valor_tipo_impresion}"
                )
        except Exception as ex:
            print(f"[PDF_ORDENADO] No se pudo leer _estado_impo_ui: {ex}")

    def on_dropdown_tipo_impresion_change(e):
        print("=" * 80)
        print("[PDF_ORDENADO] >>>>>>> DROPDOWN CHANGE EJECUTADO <<<<<<<")
        try:
            nuevo_valor = e.control.value
            print(f"[PDF_ORDENADO] Nuevo valor: {nuevo_valor}")

            # Actualizar estado compartido de impo_ui
            try:
                import impo_ui

                impo_ui._estado_impo_ui["dropdown_doble_cara"] = nuevo_valor
                print(
                    f"[PDF_ORDENADO] Estado actualizado en _estado_impo_ui: {impo_ui._estado_impo_ui.get('dropdown_doble_cara')}"
                )
            except Exception as ex:
                print(f"[PDF_ORDENADO] ERROR actualizando _estado_impo_ui: {ex}")

            # Recalcular ordenamiento
            try:
                recalcular_ordenamiento()
                print(f"[PDF_ORDENADO] Ordenamiento recalculado OK")
            except Exception as ex:
                print(f"[PDF_ORDENADO] ERROR en recalcular_ordenamiento: {ex}")
                import traceback

                traceback.print_exc()

        except Exception as ex:
            print(f"[PDF_ORDENADO] ERROR GENERAL en handler: {ex}")
            import traceback

            traceback.print_exc()
        print("=" * 80)

    dropdown_doble_cara = ft.Dropdown(
        label=t("Tipo de impresión"),
        width=175,
        value=valor_tipo_impresion,
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
        on_select=on_dropdown_tipo_impresion_change,
    )

    # print(f"[PDF_ORDENADO] Dropdown creado con valor: {dropdown_doble_cara.value}")
    # print(f"[PDF_ORDENADO] Handler asignado: {dropdown_doble_cara.on_select}")
    # print("="*80)

    # Texto de validación de páginas
    texto_validacion = ft.Text("", size=16, visible=False)

    # ProgressBar para mostrar el progreso de generación
    progress_bar = ft.ProgressBar(
        width=400,
        height=20,
        value=0,
        visible=False,
        color=TEXTO_COLOR_GENERICO,
        bgcolor=ICONO_PREF_HOVER_COLOR,
        border_radius=10,
    )

    # Texto para mostrar el progreso
    texto_progreso = ft.Text(
        "",
        size=14,
        color=TEXTO_COLOR_GENERICO,
        text_align=ft.TextAlign.CENTER,
        visible=False,
    )

    def recalcular_ordenamiento():
        """Recalcula el ordenamiento cuando cambian los parámetros."""
        try:
            # Verificar que tenemos los datos del gráfico
            if "orden_grafico_visual" not in grafico_datos:
                texto_paginas_requeridas.value = t("Debe generar un gráfico primero")
                texto_paginas_requeridas.color = ERROR_COLOR
                texto_paginas_requeridas.visible = True
                boton_cargar_pdf.visible = False
                try:
                    boton_cargar_pdf.update()
                    texto_paginas_requeridas.update()
                except Exception:
                    pass
                return

            # Obtener parámetros (número de copias siempre 1 en este módulo)
            num_copias = 1
            doble_cara = dropdown_doble_cara.value == "dorso"
            orden_grafico_visual = grafico_datos["orden_grafico_visual"]
            comienzo_numeracion = int(grafico_datos["entrada"].get("comienzo", 1))

            # Generar ordenamiento usando el mismo modo de doble_cara que el usuario seleccionó.
            # Si el usuario pidió doble cara, construiremos los dorsos a partir de las CARAS generadas.

            # Si NO está en modo doble cara pedimos el ordenamiento tal cual al generador
            if not doble_cara:
                ordenamiento_pdf = generar_ordenamiento_pdf_montaje(
                    orden_grafico_visual=orden_grafico_visual,
                    doble_cara=False,
                    numero_copias=num_copias,
                    comienzo_numeracion=comienzo_numeracion,
                )

                if not ordenamiento_pdf:
                    texto_paginas_requeridas.value = t("Error al calcular ordenamiento")
                    texto_paginas_requeridas.color = ERROR_COLOR
                    texto_paginas_requeridas.visible = True
                    boton_cargar_pdf.visible = False
                    try:
                        boton_cargar_pdf.update()
                        texto_paginas_requeridas.update()
                    except Exception:
                        pass
                    return
            else:
                # Modo doble cara solicitado: obtener solo las CARAS del generador y construir DORSOS
                # Pedimos al generador el modo doble_cara para obtener las CARAS
                # tal como el generador las produce originalmente (esto preserva
                # el salto/offset correcto entre entradas). Luego tomamos sólo
                # las entradas 'cara' y construimos los dorsos con grid_dorso.
                ordenamiento_base = generar_ordenamiento_pdf_montaje(
                    orden_grafico_visual=orden_grafico_visual,
                    doble_cara=True,
                    numero_copias=num_copias,
                    comienzo_numeracion=comienzo_numeracion,
                )

                if not ordenamiento_base:
                    texto_paginas_requeridas.value = t(
                        "Error al calcular ordenamiento (base)"
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

                # Construir intercalado (cara, dorso) a partir de las CARAS
                nuevo = {}
                numero_pagina_actual = 1

                # Obtener sólo los pliegos que representan las CARAS
                # (el generador en modo doble_cara devuelve pares cara/dorso)
                pliegos = [
                    k
                    for k, v in ordenamiento_base.items()
                    if isinstance(k, int)
                    and isinstance(v, dict)
                    and v.get("doble_cara") == "cara"
                ]
                pliegos = sorted(pliegos)

                entrada = (
                    grafico_datos.get("entrada", {})
                    if isinstance(grafico_datos, dict)
                    else {}
                )
                raw_cols = (
                    entrada.get("horizontal") or entrada.get("hojas_x_pliego") or None
                )
                raw_rows = (
                    entrada.get("vertical") or entrada.get("hojas_y_pliego") or None
                )

                for pl in pliegos:
                    itm = ordenamiento_base.get(pl)
                    if not itm or "datos" not in itm:
                        continue

                    datos_cara = itm["datos"]

                    # Añadir CARA como página independiente
                    nuevo[numero_pagina_actual] = {
                        "datos": datos_cara,
                        "numero_copia": itm.get("numero_copia", 1),
                        "doble_cara": "cara",
                    }
                    numero_pagina_actual += 1

                    # Determinar cols/rows seguros (pasar rows,cols correctamente)
                    cols = None
                    rows = None
                    try:
                        cols = int(raw_cols) if raw_cols is not None else None
                    except Exception:
                        cols = None
                    try:
                        rows = int(raw_rows) if raw_rows is not None else None
                    except Exception:
                        rows = None

                    # Inferir valores si faltan
                    if cols is None and rows is None:
                        cols = len(datos_cara)
                        rows = 1
                    elif cols is None:
                        cols = (
                            (len(datos_cara) // rows)
                            if rows and rows > 0
                            else len(datos_cara)
                        )
                    elif rows is None:
                        rows = (len(datos_cara) // cols) if cols and cols > 0 else 1

                    # Seguridad adicional
                    if not cols or cols <= 0:
                        cols = len(datos_cara)
                    if not rows or rows <= 0:
                        rows = (len(datos_cara) // cols) if cols else 1

                    # Usar grid_dorso pasando rows THEN cols (tal como pidió el usuario)
                    datos_dorso = grid_dorso(rows, cols, datos_cara)

                    nuevo[numero_pagina_actual] = {
                        "datos": datos_dorso,
                        "numero_copia": itm.get("numero_copia", 1),
                        "doble_cara": "dorso",
                    }
                    numero_pagina_actual += 1

                ordenamiento_pdf = nuevo

                # Ajustar metadata inferida a partir del nuevo ordenamiento
                paginas_pdf_original = 0
                for v in ordenamiento_pdf.values():
                    if isinstance(v, dict) and v.get("datos"):
                        try:
                            paginas_pdf_original = max(
                                paginas_pdf_original, max(v["datos"])
                            )
                        except Exception:
                            pass

                ordenamiento_pdf["_metadata"] = {
                    "paginas_pdf_original": paginas_pdf_original,
                    "paginas_generadas": len(
                        [k for k in ordenamiento_pdf.keys() if isinstance(k, int)]
                    ),
                    "numero_copias": num_copias,
                    "doble_cara": doble_cara,
                }
                # DEBUG: imprimir las primeras entradas del nuevo ordenamiento construido
                # try:
                #     print("[DEBUG recalcular_ordenamiento] Primeras 16 páginas del ordenamiento (construido en UI):")
                #     contador = 0
                #     for key in sorted([k for k in ordenamiento_pdf.keys() if isinstance(k, int)]):
                #         if contador >= 16:
                #             break
                #         print(f"  Página {key}: {ordenamiento_pdf.get(key)}")
                #         contador += 1
                # except Exception as _ex_print:
                #     print(f"[DEBUG recalcular_ordenamiento] Error imprimiendo ordenamiento: {_ex_print}")

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

            # Guardar el ordenamiento calculado
            ordenamiento_calculado["ordenamiento"] = ordenamiento_pdf
            ordenamiento_calculado["paginas_requeridas"] = paginas_requeridas

            # NUEVO: Guardar en variable global para compartir con imposición
            guardar_ordenamiento_calculado(ordenamiento_pdf)

            # Mostrar información al usuario
            texto_paginas_requeridas.value = t(
                "Necesita un PDF de exactamente {0} páginas"
            ).format(paginas_requeridas)
            texto_paginas_requeridas.color = INFO_COLOR
            texto_paginas_requeridas.visible = True

            # Mostrar botón para cargar PDF
            boton_cargar_pdf.visible = True

            # Actualizar la UI
            try:
                boton_cargar_pdf.update()
                texto_paginas_requeridas.update()
            except Exception:
                pass

            # Revalidar PDF cargado si existe
            if archivo_seleccionado["ruta"]:
                revalidar_pdf_cargado()

        except Exception as ex:
            print(f"[ERROR] Error al recalcular ordenamiento: {ex}")
            texto_paginas_requeridas.value = f"Error: {str(ex)}"
            texto_paginas_requeridas.color = ERROR_COLOR
            texto_paginas_requeridas.visible = True
            boton_cargar_pdf.visible = False
            try:
                boton_cargar_pdf.update()
                texto_paginas_requeridas.update()
            except Exception:
                pass

    def revalidar_pdf_cargado():
        """Revalida el PDF cargado cuando cambian los parámetros."""
        # print(f"[PDF_ORDENADO] revalidar_pdf_cargado() - Iniciando")
        # print(f"[PDF_ORDENADO] archivo_seleccionado['ruta'] = {archivo_seleccionado.get('ruta')}")
        # print(f"[PDF_ORDENADO] archivo_seleccionado['ruta_original'] = {archivo_seleccionado.get('ruta_original')}")
        # print(f"[PDF_ORDENADO] archivo_seleccionado['paginas'] = {archivo_seleccionado.get('paginas')}")
        # print(f"[PDF_ORDENADO] ordenamiento_calculado['paginas_requeridas'] = {ordenamiento_calculado.get('paginas_requeridas')}")

        # Aceptar ruta temporal O ruta_original (para trabajos cargados)
        tiene_ruta = archivo_seleccionado.get("ruta") or archivo_seleccionado.get(
            "ruta_original"
        )
        if not tiene_ruta or not ordenamiento_calculado["paginas_requeridas"]:
            print(
                f"[PDF_ORDENADO] Validación abortada: faltan datos (ruta={tiene_ruta}, pag_req={ordenamiento_calculado.get('paginas_requeridas')})"
            )
            return

        paginas_pdf = archivo_seleccionado["paginas"]
        paginas_requeridas = ordenamiento_calculado["paginas_requeridas"]

        # print(f"[PDF_ORDENADO] Comparando: PDF={paginas_pdf} vs Requeridas={paginas_requeridas}")

        if paginas_pdf == paginas_requeridas:
            texto_validacion.value = t("✅ Correcto: {0} páginas").format(paginas_pdf)
            texto_validacion.color = SUCCESS_COLOR
            boton_generar_preview.disabled = False
            # print(f"[PDF_ORDENADO] ✅ Validación exitosa - Botón habilitado")
        else:
            texto_validacion.value = t("❌ Error: tiene {0}, necesita {1}").format(
                paginas_pdf, paginas_requeridas
            )
            texto_validacion.color = ERROR_COLOR
            boton_generar_preview.disabled = True
            print(
                f"[PDF_ORDENADO] ❌ Error: tiene {paginas_pdf}, necesita {paginas_requeridas}"
            )
            print(f"[PDF_ORDENADO] ❌ Validación fallida - Botón deshabilitado")
        texto_validacion.visible = True

        try:
            texto_validacion.update()
            boton_generar_preview.update()
            # print(f"[PDF_ORDENADO] UI actualizada correctamente")
        except Exception as ex:
            print(f"[PDF_ORDENADO] Error actualizando UI: {ex}")

    # Función para manejar selección de archivo
    def on_file_picker_result(e):
        if e.files and len(e.files) > 0:
            archivo = e.files[0]
            archivo_seleccionado["ruta"] = archivo.path
            archivo_seleccionado["ruta_original"] = (
                archivo.path
            )  # Guardar ruta original para persistencia
            archivo_seleccionado["nombre"] = archivo.name

            # Guardar en variable global para compartir con impo_ui
            guardar_ruta_pdf_original(archivo.path)

            # Siempre contar páginas del PDF seleccionado, nunca usar datos de impo_ui
            try:
                from pdf_manipulator import contar_paginas_pdf

                paginas_pdf, error_pdf = contar_paginas_pdf(archivo.path)
                print(f"[PDF_ORDENADO] Páginas contadas: {paginas_pdf}")
            except Exception as ex:
                print(f"[PDF_ORDENADO] Error contando páginas del PDF: {ex}")
                paginas_pdf = 0

            archivo_seleccionado["paginas"] = paginas_pdf

            # Extraer cajas de la página 0 usando el extractor común (pdf_manipulator)
            try:
                from pdf_manipulator import leer_cajas_pdf

                boxes = leer_cajas_pdf(archivo.path, pagina=0)
                print(f"[DEBUG] leer_cajas_pdf returned: {boxes}")
                if boxes and not boxes.get("error"):
                    mediabox = (
                        list(boxes.get("mediabox")) if boxes.get("mediabox") else None
                    )
                    trimbox = (
                        list(boxes.get("trimbox")) if boxes.get("trimbox") else None
                    )
                    cropbox = (
                        list(boxes.get("cropbox"))
                        if boxes.get("cropbox")
                        else (trimbox or mediabox)
                    )
                    bleedbox = (
                        list(boxes.get("bleedbox"))
                        if boxes.get("bleedbox")
                        else (trimbox or mediabox)
                    )

                    # Preferir trimbox (corte) para calcular tamaño usuario, si existe
                    ref_box = trimbox or cropbox or mediabox
                    if ref_box:
                        PT_TO_MM = 0.352778
                        width_mm = (ref_box[2] - ref_box[0]) * PT_TO_MM
                        height_mm = (ref_box[3] - ref_box[1]) * PT_TO_MM
                        archivo_seleccionado["mediabox_width_mm"] = round(width_mm, 2)
                        archivo_seleccionado["mediabox_height_mm"] = round(height_mm, 2)
                        src = (
                            "trimbox"
                            if trimbox
                            else ("cropbox" if cropbox else "mediabox")
                        )
                        print(
                            f"[DEBUG] Calculated mediabox from {src}: {ref_box} -> {archivo_seleccionado['mediabox_width_mm']}x{archivo_seleccionado['mediabox_height_mm']} mm"
                        )
                    else:
                        print(
                            "[DEBUG] No ref_box found (mediabox/trimbox/cropbox missing)"
                        )

                    # --- Actualizar estado compartido en impo_ui con todas las boxes ---
                    try:
                        import impo_ui

                        print(
                            f"[DEBUG] impo_ui._estado_impo_ui (antes): tamano_usuario_w={impo_ui._estado_impo_ui.get('tamano_usuario_w')}, tamano_usuario_h={impo_ui._estado_impo_ui.get('tamano_usuario_h')}, mediabox={impo_ui._estado_impo_ui.get('mediabox')}"
                        )
                        # Avisar cambio de tamaño usuario si difiere
                        mediabox_anterior = impo_ui._estado_impo_ui.get("mediabox")
                        if mediabox_anterior:
                            PT_TO_MM = 0.352778
                            width_mm_ant = round(
                                (mediabox_anterior[2] - mediabox_anterior[0])
                                * PT_TO_MM,
                                2,
                            )
                            height_mm_ant = round(
                                (mediabox_anterior[3] - mediabox_anterior[1])
                                * PT_TO_MM,
                                2,
                            )
                            tam_w = impo_ui._estado_impo_ui.get("tamano_usuario_w")
                            tam_h = impo_ui._estado_impo_ui.get("tamano_usuario_h")
                            print(
                                f"[DEBUG] mediabox_anterior mm: {width_mm_ant}x{height_mm_ant} ; estado tamano_usuario={tam_w}x{tam_h}"
                            )
                            if ref_box and (
                                width_mm_ant
                                != round((ref_box[2] - ref_box[0]) * PT_TO_MM, 2)
                                or height_mm_ant
                                != round((ref_box[3] - ref_box[1]) * PT_TO_MM, 2)
                            ):
                                new_w = round((ref_box[2] - ref_box[0]) * PT_TO_MM, 2)
                                new_h = round((ref_box[3] - ref_box[1]) * PT_TO_MM, 2)
                                impo_ui._estado_impo_ui["tamano_usuario_w"] = new_w
                                impo_ui._estado_impo_ui["tamano_usuario_h"] = new_h
                                impo_ui._estado_impo_ui["trabajo_modificado"] = True
                                print(
                                    f"[DEBUG] Actualizado impo_ui._estado_impo_ui tamano_usuario -> {new_w}x{new_h}"
                                )
                                try:
                                    import builtins

                                    cb = getattr(
                                        builtins, "_on_trabajo_modificado_change", None
                                    )
                                    if callable(cb):
                                        cb()
                                except Exception:
                                    pass
                        else:
                            # Si no había mediabox anterior, setear tamano_usuario directamente si tenemos ref_box
                            if ref_box:
                                PT_TO_MM = 0.352778
                                impo_ui._estado_impo_ui["tamano_usuario_w"] = round(
                                    (ref_box[2] - ref_box[0]) * PT_TO_MM, 2
                                )
                                impo_ui._estado_impo_ui["tamano_usuario_h"] = round(
                                    (ref_box[3] - ref_box[1]) * PT_TO_MM, 2
                                )
                                print(
                                    f"[DEBUG] No mediabox anterior; estableciendo tamano_usuario a {impo_ui._estado_impo_ui['tamano_usuario_w']}x{impo_ui._estado_impo_ui['tamano_usuario_h']}"
                                )

                        # Guardar boxes en el estado para que otros módulos (restaurar/guardar) las usen
                        impo_ui._estado_impo_ui["mediabox"] = mediabox
                        impo_ui._estado_impo_ui["trimbox"] = trimbox
                        impo_ui._estado_impo_ui["cropbox"] = cropbox
                        impo_ui._estado_impo_ui["bleedbox"] = bleedbox

                        # También actualizar _archivo_seleccionado mínimo en impo_ui para visibilidad
                        try:
                            impo_ui._archivo_seleccionado.clear()
                            impo_ui._archivo_seleccionado.update(
                                {
                                    "ruta": archivo.path,
                                    "ruta_original": archivo.path,
                                    "nombre": archivo.name,
                                    "paginas": paginas_pdf,
                                    "boxes_by_page": {
                                        0: {
                                            "mediabox": mediabox,
                                            "trimbox": trimbox,
                                            "cropbox": cropbox,
                                            "bleedbox": bleedbox,
                                        }
                                    },
                                }
                            )
                        except Exception:
                            pass

                        import json

                        print(
                            "[DEBUG] STAMP ACTUALIZADO TRAS CARGA PDF (leer_cajas_pdf):"
                        )
                        print(
                            json.dumps(
                                impo_ui._estado_impo_ui,
                                indent=2,
                                ensure_ascii=False,
                                default=str,
                            )
                        )
                        print(
                            f"[PDF_ORDENADO] Boxes extraídas: mediabox={mediabox}, trimbox={trimbox}, cropbox={cropbox}"
                        )
                    except Exception as ex_state:
                        print(
                            f"[PDF_ORDENADO] Error actualizando estado impo_ui con boxes: {ex_state}"
                        )
                else:
                    print(
                        f"[PDF_ORDENADO] leer_cajas_pdf devolvió error o boxes vacías: {boxes}"
                    )
            except Exception as ex:
                print(
                    f"[PDF_ORDENADO] Error extrayendo boxes con pdf_manipulator: {ex}"
                )

            # Actualizar UI
            texto_archivo.value = t("Archivo: {0}").format(archivo.name)
            texto_paginas.value = t("Páginas en archivo: {0}").format(paginas_pdf)

            # Validar páginas
            paginas_requeridas = ordenamiento_calculado["paginas_requeridas"]
            if paginas_requeridas and paginas_pdf == paginas_requeridas:
                texto_validacion.value = t("✅ Correcto: {0} páginas").format(
                    paginas_pdf
                )
                texto_validacion.color = SUCCESS_COLOR
                boton_generar_preview.disabled = False
            else:
                texto_validacion.value = t("❌ Error: tiene {0}, necesita {1}").format(
                    paginas_pdf, paginas_requeridas
                )
                texto_validacion.color = ERROR_COLOR
                boton_generar_preview.disabled = True

            texto_validacion.visible = True

            # Actualizar todos los controles
            texto_archivo.update()
            texto_paginas.update()
            texto_validacion.update()
            boton_generar_preview.update()
        else:
            # Limpiar selección
            archivo_seleccionado["ruta"] = ""
            archivo_seleccionado["nombre"] = ""
            archivo_seleccionado["paginas"] = 0

            texto_archivo.value = t("Ningún archivo seleccionado")
            texto_paginas.value = t("Páginas en archivo: {0}").format("")
            texto_validacion.visible = False
            boton_generar_preview.disabled = True

            texto_archivo.update()
            texto_paginas.update()
            texto_validacion.update()
            boton_generar_preview.update()

    # FilePicker
    page.overlay[:] = [
        control for control in page.overlay if not isinstance(control, ft.FilePicker)
    ]
    file_picker = ft.FilePicker()

    async def _pick_pdf(e):
        try:
            files = await file_picker.pick_files(
                dialog_title=t("Seleccionar PDF para ordenar"),
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["pdf"],
            )
        except Exception as ex:
            print(f"[PDF_ORDENADO] Error pick_files: {ex}")
            files = []
        # Flet 1.0: handlers en el loop → contar_paginas/leer_cajas fuera del loop
        await asyncio.to_thread(
            on_file_picker_result,
            SimpleNamespace(
                files=files or [],
                path=(files[0].path if files else None),
            ),
        )

    # Botón para cargar PDF (inicialmente oculto) — Flet 1.0: async on_click + await
    boton_cargar_pdf = ft.Button(
        t("Cargar PDF"),
        icon=ft.Icons.PICTURE_AS_PDF,
        width=120,
        height=35,
        visible=False,
        on_click=_pick_pdf,
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

    # Botón para generar vista previa (inicialmente deshabilitado)
    boton_generar_preview = ft.Button(
        t("Generar Vista Previa"),
        expand=True,
        icon=ft.Icons.PREVIEW,
        width=210,
        height=40,
        # Flet 1.0: copiar_pdf_a_temporal + preview pesado → fuera del loop
        on_click=lambda e: page.run_task(generar_vista_previa),
        disabled=True,
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
    )

    async def generar_vista_previa():
        """Genera el PDF temporal y la vista previa con imágenes."""
        if (
            not archivo_seleccionado["ruta"]
            or not ordenamiento_calculado["ordenamiento"]
        ):
            from app_ui_items import mostrar_snackbar

            mostrar_snackbar(
                page,
                t("Debe cargar el PDF original antes de generar vista previa"),
                SNACKBAR_COLOR_ERROR,
                3000,
            )
            return

        # Antes de cualquier serialización / paso a JSON, si no hay una imposición
        # creada en el estado global, cargar las preferencias (no marcar impo_creada
        # aquí; lo maneja `impo_ui` o `trabajo_manager`).
        try:
            import impo_ui

            try:
                if not impo_ui._estado_impo_ui.get("impo_creada", False):
                    try:
                        impo_ui.cargar_preferencias_imposicion()
                        print(
                            "[PDF_ORDENADO] Preferencias cargadas antes de generar vista previa"
                        )
                        # Marcar trabajo como modificado ya que se aplicaron preferencias
                        try:
                            impo_ui._estado_impo_ui["trabajo_modificado"] = True
                            import builtins

                            cb = getattr(
                                builtins, "_on_trabajo_modificado_change", None
                            )
                            if callable(cb):
                                cb()
                            else:
                                # fallback: intentar forzar refresh UI si existe
                                upd = getattr(
                                    builtins, "_update_project_state_ui", None
                                )
                                if callable(upd):
                                    upd()
                        except Exception as _ex_flag:
                            print(
                                f"[PDF_ORDENADO] No se pudo marcar trabajo_modificado tras cargar prefs: {_ex_flag}"
                            )
                    except Exception as _ex_pref:
                        print(
                            f"[PDF_ORDENADO] No se pudieron cargar preferencias antes de generar vista previa: {_ex_pref}"
                        )
            except Exception:
                pass
        except Exception:
            pass

        try:
            # Mostrar ProgressBar
            progress_bar.visible = True
            texto_progreso.visible = True
            boton_generar_preview.disabled = True
            progress_bar.value = 0
            texto_progreso.value = t("Generando PDF temporal ordenado...")
            progress_bar.update()
            texto_progreso.update()
            boton_generar_preview.update()

            # Crear PDF temporal ordenado
            nombre_base = os.path.splitext(archivo_seleccionado["nombre"])[0]
            pdf_temp = crear_ruta_pdf_temp(nombre_base)

            # ═══════════════════════════════════════════════════════════════
            # OPTIMIZACIÓN: Copiar PDF en lugar de reordenarlo (elimina 5-10s)
            # ═══════════════════════════════════════════════════════════
            texto_progreso.value = t("Copiando PDF...")
            progress_bar.value = 0.1
            progress_bar.update()
            texto_progreso.update()

            # Copiar PDF simple (sin reordenar)
            pdf_temp = await asyncio.to_thread(
                copiar_pdf_a_temporal, archivo_seleccionado["ruta"]
            )

            if not pdf_temp:
                progress_bar.visible = False
                texto_progreso.visible = False
                boton_generar_preview.disabled = False
                progress_bar.update()
                texto_progreso.update()
                boton_generar_preview.update()
                from app_ui_items import mostrar_snackbar

                # traducción de mensaje
                mostrar_snackbar(
                    page, t("Error al copiar PDF temporal"), SNACKBAR_COLOR_ERROR, 3000
                )
                return

            # Guardar ruta del PDF temp en variable global para que imposición lo cargue
            pdf_temp_path["ruta"] = pdf_temp
            global _PDF_ORDENADO_TEMP
            _PDF_ORDENADO_TEMP = pdf_temp

            progress_bar.value = 0.3
            texto_progreso.value = t("PDF copiado, preparando cache...")
            progress_bar.update()
            texto_progreso.update()

            # ----------------------------------------------------------------
            # FASE 2A: Crear índice COMPLETO de todos los pliegos
            # ----------------------------------------------------------------
            texto_progreso.value = t("Creando índice de pliegos...")
            progress_bar.value = 0.35
            progress_bar.update()
            texto_progreso.update()

            try:
                # Crear directorio de imágenes en temp
                imagenes_dir = os.path.join(os.path.dirname(pdf_temp), "imagenes")
                if os.path.exists(imagenes_dir):
                    shutil.rmtree(imagenes_dir)
                os.makedirs(imagenes_dir, exist_ok=True)

                # Regenerar timestamp para nuevos nombres de archivo
                regenerar_timestamp_sesion()

                # Obtener ordenamiento
                ordenamiento = ordenamiento_calculado["ordenamiento"]

                # PASO 1: Crear índice COMPLETO de TODOS los pliegos
                # Obtener páginas del primer pliego para calcular paginas_por_pliego
                paginas_primer_pliego = obtener_paginas_del_pliego(ordenamiento, 1)
                paginas_por_pliego = (
                    len(paginas_primer_pliego) if paginas_primer_pliego else 4
                )

                crear_indice_completo_pliegos(ordenamiento, paginas_por_pliego)
                total_pliegos = obtener_total_pliegos_indice()

                # print(f"[ÍNDICE COMPLETO] Creado para {total_pliegos} pliegos")

                # ----------------------------------------------------------------
                # FASE 2B: Cachear solo primeros 5 pliegos
                # ----------------------------------------------------------------
                texto_progreso.value = t("Cacheando primeros 5 pliegos...")
                progress_bar.value = 0.4
                progress_bar.update()
                texto_progreso.update()

                pliegos_a_cachear = min(5, total_pliegos)  # Máximo 5 pliegos

                # print(f"[CACHE INICIAL] Cacheando {pliegos_a_cachear} de {total_pliegos} pliegos")

                # Cachear primeros 5 pliegos desde PDF ORIGINAL
                for pliego_num in range(1, pliegos_a_cachear + 1):
                    try:
                        paginas = obtener_paginas_del_pliego(ordenamiento, pliego_num)
                        if paginas:
                            # CRÍTICO: Usar PDF ORIGINAL, no el temporal
                            # Pasar numero_pliego para calcular índice global
                            await asyncio.to_thread(
                                extraer_imagenes_pliego,
                                archivo_seleccionado["ruta"],
                                paginas,
                                pliego_num,
                                len(paginas),
                                dpi=100,
                            )
                            marcar_pliego_cacheado(pliego_num)

                            # Actualizar progreso (0.4 a 0.9)
                            progreso = 0.4 + (pliego_num / pliegos_a_cachear) * 0.5
                            progress_bar.value = progreso
                            texto_progreso.value = t(
                                "Cacheando pliego {0}/{1}..."
                            ).format(pliego_num, pliegos_a_cachear)
                            progress_bar.update()
                            texto_progreso.update()
                    except Exception as ex_pliego:
                        if _PRINT_DEBUG:
                            print(
                                f"[ERROR] Error cacheando pliego {pliego_num}: {ex_pliego}"
                            )

                # print(f"[CACHE INICIAL] Completado. {obtener_total_pliegos_indice()} pliegos registrados, {pliegos_a_cachear} cacheados")

            except Exception as ex_img:
                print(f"[ERROR] Error en cache inicial: {ex_img}")
                # No abortamos, seguimos con la apertura

            # Completar ProgressBar
            progress_bar.value = 1.0
            texto_progreso.value = t("Procesando, espere...")
            progress_bar.update()
            texto_progreso.update()

            # NO Ocultar progress ni cerrar diálogo todavía
            # Esperar a que se abra la otra ventana

            # Abrir ventana de imposición (cargará automáticamente el PDF temp)
            # Lazy import para evitar ciclos
            from impo_ui import (
                crear_ventana_ordenar_imposicion as crear_ventana_ordenar_imposicion_externa,
            )

            print("[PDF_ORDENADO] Importación de impo_ui exitosa")

            # Sincronizar el estado del dropdown con impo_ui antes de abrir la ventana de imposición
            try:
                import impo_ui

                # asegurar que el estado compartido contiene el valor actual
                impo_ui._estado_impo_ui["dropdown_doble_cara"] = (
                    dropdown_doble_cara.value
                    if hasattr(globals().get("dropdown_doble_cara"), "value")
                    else impo_ui._estado_impo_ui.get("dropdown_doble_cara", "cara")
                )
                # si el widget de impo ya existe en memoria, actualizar su valor y refrescar UI
                if getattr(impo_ui, "dropdown_doble_cara", None) is not None:
                    try:
                        impo_ui.dropdown_doble_cara.value = impo_ui._estado_impo_ui.get(
                            "dropdown_doble_cara", "cara"
                        )
                        impo_ui.dropdown_doble_cara.update()
                    except Exception:
                        pass
                print(
                    f"[PDF_ORDENADO] Estado sincronizado a impo_ui: {impo_ui._estado_impo_ui.get('dropdown_doble_cara')}"
                )

                # Sincronizar metadata del PDF con impo_ui para que la validación
                # de la ventana de imposición pueda leer el PDF temporal y sus metadatos.
                try:
                    impo_ui._archivo_seleccionado.clear()
                    impo_ui._archivo_seleccionado.update(
                        {
                            "ruta": archivo_seleccionado.get("ruta", ""),
                            "ruta_original": archivo_seleccionado.get("ruta", ""),
                            "nombre": archivo_seleccionado.get("nombre", ""),
                            "paginas": archivo_seleccionado.get("paginas", 0),
                            "mediabox_width_mm": archivo_seleccionado.get(
                                "mediabox_width_mm"
                            ),
                            "mediabox_height_mm": archivo_seleccionado.get(
                                "mediabox_height_mm"
                            ),
                        }
                    )
                    # Compartir ruta del PDF ordenado temporal para que impo_ui pueda validarlo
                    impo_ui._pdf_ordenado_actual = pdf_temp
                    # Compartir ordenamiento calculado
                    impo_ui._ordenamiento_calculado = ordenamiento_calculado
                    print(
                        f"[PDF_ORDENADO] Metadata PDF sincronizada con impo_ui: {impo_ui._archivo_seleccionado}"
                    )
                    print(
                        f"[PDF_ORDENADO] MediaBox dimensions: {archivo_seleccionado.get('mediabox_width_mm')}×{archivo_seleccionado.get('mediabox_height_mm')} mm"
                    )
                except Exception as _sync_ex:
                    print(
                        f"[PDF_ORDENADO] No se pudo sincronizar metadata PDF con impo_ui: {_sync_ex}"
                    )
                # Actualizar checkboxes desde estado
                if hasattr(impo_ui, "actualizar_checkboxes_desde_estado"):
                    print(
                        "[PDF_ORDENADO] Actualizando checkboxes antes de abrir imposición..."
                    )
                    impo_ui.actualizar_checkboxes_desde_estado()
            except Exception as _ex:
                print(f"[PDF_ORDENADO] No pudo sincronizar con impo_ui: {_ex}")

            # NO cerrar diálogo aquí - se cierra cuando auto_load termine en impo_ui
            # Pasar dialog para que impo_ui lo cierre cuando la carga esté completa
            crear_ventana_ordenar_imposicion_externa(
                page,
                on_guardar_trabajo,
                initial_project_modified,
                initial_project_path,
                initial_project_name,
                loading_dialog=dialog,
            )

            # Actualizar checkboxes DESPUÉS de abrir la ventana de imposición
            if hasattr(impo_ui, "actualizar_checkboxes_desde_estado"):
                print(
                    "[PDF_ORDENADO] Actualizando checkboxes DESPUÉS de abrir ventana...DESACTIVADO"
                )
                impo_ui.actualizar_checkboxes_desde_estado()

        except Exception as ex:
            print(f"[ERROR] Error al generar vista previa: {ex}")
            progress_bar.visible = False
            texto_progreso.visible = False
            boton_generar_preview.disabled = False
            progress_bar.update()
            texto_progreso.update()
            boton_generar_preview.update()
            from app_ui_items import mostrar_snackbar

            mostrar_snackbar(
                page, t("Error: {0}").format(str(ex)), SNACKBAR_COLOR_ERROR, 3000
            )

    # Crear el diálogo
    dialog = ft.AlertDialog(
        modal=True,
        bgcolor=FONDO_ALERT_DIALOG,
        title=ft.Text(
            t("Generar Imposición"),
            weight=ft.FontWeight.BOLD,
            size=20,
            text_align=ft.TextAlign.CENTER,
            color=TEXTO_COLOR_GENERICO,
        ),
        content=ft.Container(
            content=ft.Column(
                [
                    ft.Container(height=6),
                    # Sección de opciones
                    ft.Container(
                        content=ft.Column(
                            [
                                dropdown_doble_cara,
                            ],
                            spacing=0,
                        ),
                        height=80,
                        alignment=ft.Alignment.TOP_LEFT,
                    ),
                    # Información de páginas requeridas
                    ft.Container(
                        content=texto_paginas_requeridas,
                        height=30,
                        alignment=ft.Alignment.CENTER_LEFT,
                    ),
                    ft.Divider(color=TEXTO_COLOR_GENERICO),
                    # Sección de carga de PDF
                    ft.Container(
                        content=ft.Column(
                            [
                                boton_cargar_pdf,
                                ft.Container(content=texto_archivo, width=480),
                                texto_paginas,
                                texto_validacion,
                            ],
                            spacing=12,
                        ),
                        height=180,
                        alignment=ft.Alignment.TOP_LEFT,
                    ),
                    ft.Divider(color=TEXTO_COLOR_GENERICO),
                    ft.Container(height=20),
                ],
                spacing=12,
            ),
            width=500,
            height=410,
            bgcolor=FONDO_ALERT_DIALOG,
        ),
        actions=[
            ft.Container(
                content=ft.Column(
                    [
                        # ProgressBar y texto de progreso
                        ft.Container(
                            content=ft.Column(
                                [
                                    progress_bar,
                                    texto_progreso,
                                ],
                                spacing=8,
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            height=60,
                            alignment=ft.Alignment.CENTER,
                        ),
                        # Botones
                        boton_generar_preview,
                        ft.Button(
                            content=t("Cancelar"),
                            width=95,
                            bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                            on_click=lambda e: page.pop_dialog(),
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
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=10,
                ),
                alignment=ft.Alignment.CENTER,
            )
        ],
    )

    # Función para calcular cuando el diálogo esté listo
    def on_dialog_open():
        # print("[PDF_ORDENADO] on_dialog_open() - Iniciando")
        # print(f"[PDF_ORDENADO] archivo_seleccionado = {archivo_seleccionado}")
        recalcular_ordenamiento()
        # print(f"[PDF_ORDENADO] paginas_requeridas = {ordenamiento_calculado.get('paginas_requeridas')}")

        # Si hay PDF cargado previamente (ruta temporal o ruta_original), actualizar UI y revalidar
        tiene_pdf = (
            archivo_seleccionado["ruta"] or archivo_seleccionado.get("ruta_original")
        ) and archivo_seleccionado["paginas"] > 0

        if tiene_pdf:
            # print(f"[PDF_ORDENADO] PDF detectado: {archivo_seleccionado['nombre']}")
            # print(f"[PDF_ORDENADO]   ruta temporal: {archivo_seleccionado.get('ruta', 'N/A')}")
            print(
                f"[PDF_ORDENADO]   ruta_original: {archivo_seleccionado.get('ruta_original', 'N/A')}"
            )
            texto_archivo.value = t("Archivo: {0}").format(
                archivo_seleccionado["nombre"]
            )
            texto_paginas.value = t("Páginas en archivo: {0}").format(
                archivo_seleccionado["paginas"]
            )
            boton_cargar_pdf.visible = True
            try:
                texto_archivo.update()
                texto_paginas.update()
                boton_cargar_pdf.update()
            except Exception as ex:
                print(f"[PDF_ORDENADO] Error actualizando UI: {ex}")

            # Revalidar PDF con ordenamiento recién calculado
            print("[PDF_ORDENADO] Llamando a revalidar_pdf_cargado()")
            revalidar_pdf_cargado()
        else:
            print("[PDF_ORDENADO] No hay PDF previamente cargado")

    # Siempre mostrar el diálogo - si hay PDF cargado, se mostrará precargado en los campos

    # Abrir el diálogo
    print("[PDF_ORDENADO] ========================================")
    print("[PDF_ORDENADO] Abriendo diálogo 'Generar Imposición'")
    print("[PDF_ORDENADO] ========================================")
    page.show_dialog(dialog)

    # Actualizar checkboxes desde estado ANTES de abrir imposición
    try:
        if hasattr(impo_ui, "actualizar_checkboxes_desde_estado"):
            print("[PDF_ORDENADO] Actualizando checkboxes desde estado...")
            impo_ui.actualizar_checkboxes_desde_estado()
    except Exception as ex_check:
        print(f"[PDF_ORDENADO] Error actualizando checkboxes: {ex_check}")

    # Ejecutar cálculo DESPUÉS de abrir el diálogo
    try:
        print("[PDF_ORDENADO] Ejecutando on_dialog_open() directamente...")
        on_dialog_open()
    except Exception as ex:
        print(f"[PDF_ORDENADO] ❌ ERROR en on_dialog_open(): {ex}")
        import traceback

        traceback.print_exc()

    return dialog
