"""
STACK TRAZADO UI - ARQUITECTURA LIMPIA
═══════════════════════════════════════════════════════════════════════════════

Este módulo se encarga ÚNICAMENTE de crear y actualizar el STACK principal
de trazado de imposición.

EL STACK SE CREA VACÍO al inicializar y se va ACTUALIZANDO conforme se necesita.

"""

import flet as ft
import flet.canvas as cv
from typing import Optional, Dict, Any, List, Tuple
from lang import t


# Silenciar prints de depuración en este módulo por defecto.
# Para activar, cambiar _PRINT_DEBUG = True durante desarrollo.
_PRINT_DEBUG = False
if not _PRINT_DEBUG:

    def _no_print(*args, **kwargs):
        return None

    print = _no_print


# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTES
# ═══════════════════════════════════════════════════════════════════════════════

GROSOR_LINEA_EXTERIOR_MM = 0.25  # mm

# ═══════════════════════════════════════════════════════════════════════════════
# FUNCIONES AUXILIARES
# ═══════════════════════════════════════════════════════════════════════════════


def mm_a_px(mm: float, escala: float = 1) -> float:
    """Convierte milímetros a píxeles."""
    return mm * escala


def px_a_mm(px: float, escala: float = 1) -> float:
    """Convierte píxeles a milímetros."""
    return px / escala


# ═══════════════════════════════════════════════════════════════════════════════
# FUNCIONES HELPERS PARA MARCAS DE CORTE
# ═══════════════════════════════════════════════════════════════════════════════


def calcular_offsets_marcas(
    tamano_usuario_w: float,
    tamano_usuario_h: float,
    calles: List[float],
    grid_rows: int,
    grid_cols: int,
    longitud_cruz_mm: float,
    offset_cruz_mm: float = 0.0,
) -> Dict[str, Any]:
    """
    Calcula offsets (mm) para colocar las cajas de marcas externas.
    """
    # t_cruz = LONGITUD_CRUZ_MM + OFFSET_CRUZ_MM
    t_cruz = float(longitud_cruz_mm) + float(offset_cruz_mm)

    # Número de calles internas
    n_v = max(0, grid_cols - 1)  # Calles verticales (entre columnas)
    n_h = max(0, grid_rows - 1)  # Calles horizontales (entre filas)

    # Sanitizar lista de calles: formato V-first [V1..Vn_v, H1..Hn_h]
    expected = n_v + n_h
    calles_list = [float(x) for x in (calles or [])][:expected]
    if len(calles_list) < expected:
        calles_list += [0.0] * (expected - len(calles_list))

    calles_v = calles_list[:n_v]
    calles_h = calles_list[n_v : n_v + n_h]

    print(
        f"[DBG] calcular_offsets_marcas: tam_w={tamano_usuario_w} tam_h={tamano_usuario_h} grid_rows={grid_rows} grid_cols={grid_cols} calles={calles_list} t_cruz={t_cruz}"
    )
    print(
        f"[DBG]   longitud_cruz_mm={longitud_cruz_mm}, offset_cruz_mm={offset_cruz_mm}"
    )
    print(f"[DBG]   calles_h={calles_h}, calles_v={calles_v}")

    # Calcular offsets horizontales (Y) para marcas IZQUIERDA/DERECHA
    # Estas marcas van en las calles horizontales (entre filas) → usa calles_h
    h_offsets: List[float] = []
    offset_temp = t_cruz
    for i in range(n_h):
        offset_i = offset_temp + tamano_usuario_h
        h_offsets.append(round(offset_i, 6))
        offset_temp = offset_i + (calles_h[i] if i < len(calles_h) else 0.0)

    # Calcular offsets verticales (X) para marcas ARRIBA/ABAJO
    # Estas marcas van en las calles verticales (entre columnas) → usa calles_v
    v_offsets: List[float] = []
    offset_temp = t_cruz
    for j in range(n_v):
        offset_j = offset_temp + tamano_usuario_w
        v_offsets.append(round(offset_j, 6))
        offset_temp = offset_j + (calles_v[j] if j < len(calles_v) else 0.0)

    # print(f"[DBG] h_offsets_mm={h_offsets} v_offsets_mm={v_offsets}")

    return {
        "t_cruz_mm": round(t_cruz, 6),
        "h_offsets_mm": h_offsets,
        "v_offsets_mm": v_offsets,
    }


"""
Crea UNA SOLA línea de marca de corte para cuando calle=0.
"""


def crear_marca_linea_simple(
    longitud_cruz_mm: float, label: str = ""
) -> Dict[str, Any]:
    """
    Crea UNA SOLA línea de marca de corte para cuando calle=0.
    Más simple que crear_caja_marcas, solo devuelve la especificación de 1 línea.

    Devuelve un dict con:
      - 'longitud_mm': longitud de la línea (10mm)
      - 'ancho_mm': ancho visible de la línea (1mm)
      - 'label': identificador
    """
    return {
        "longitud_mm": float(longitud_cruz_mm),
        "ancho_mm": 1.0,  # Ancho visible mínimo
        "label": label,
    }


def crear_caja_marcas(
    calle_size_mm: float,
    longitud_cruz_mm: float,
    label: str = "",
    invertir: bool = False,
) -> Dict[str, Any]:
    """
    Crea la especificación geométrica (sin UI) de una "caja" que contiene 3 marcas de corte.
    SOLO se usa cuando calle_size_mm > 0.

    Args:
        invertir: Si True, invierte el orden (para cajas opuestas derecha/abajo)

    Devuelve un dict con:
      - 'box_w', 'box_h'
      - 'marks': lista de dicts {'x','y','w','h'} en mm relativos al (0,0) de la caja
      - 'label': texto identificador para debug visual
    """
    marks = []
    box_h = float(calle_size_mm)
    box_w = float(calle_size_mm)

    # Grosor de la marca: usar el mismo grosor que las cruces (0.5pt -> mm)
    PT_TO_MM = 25.4 / 72.0
    mark_h = float(0.5 * PT_TO_MM)
    mark_w = float(longitud_cruz_mm)

    # Posicionar las 3 marcas de forma simétrica teniendo en cuenta el grosor
    # Centros idealmente en: top (mark_h/2), middle (box_h/2), bottom (box_h - mark_h/2)
    centers = [mark_h / 2.0, box_h / 2.0, box_h - mark_h / 2.0]
    if invertir:
        centers = list(reversed(centers))

    for c in centers:
        # y debe ser la coordenada superior de la marca (top-left), por eso restamos mark_h/2
        y_top = c - (mark_h / 2.0)
        # Clamp por seguridad para no salir del box
        if y_top < 0:
            y_top = 0.0
        if y_top + mark_h > box_h:
            y_top = box_h - mark_h

        marks.append(
            {
                "x": 0.0,
                "y": round(y_top, 6),
                "w": mark_w,
                "h": mark_h,
            }
        )

    print(
        f"[DBG] crear_caja_marcas(calle_size_mm={calle_size_mm}, longitud_cruz_mm={longitud_cruz_mm})"
    )
    print(f"[DBG]   3 marcas apiladas")
    print(f"[DBG]   box_w={box_w}, box_h={box_h}")
    print(f"[DBG]   marks={marks}")

    return {"box_w": box_w, "box_h": box_h, "marks": marks, "label": label}


def crear_stack_marcas(
    group_w_mm: float,
    group_h_mm: float,
    h_offsets: List[float],
    v_offsets: List[float],
    caja_h_spec: Dict[str, Any],
    caja_v_spec: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Genera una lista de "placements" (especificaciones) para colocar las cajas de marcas
    dentro de un grupo de tamaño `group_w_mm` x `group_h_mm`.

    Estrategia:
    - Para cada offset Y en `h_offsets` (calles horizontales) ubicamos dos cajas:
      una a la izquierda (x=0) y otra a la derecha (x=group_w_mm - caja_w).
      La coordenada Y de la caja se sitúa en offset_y - caja_h/2 para centrar la caja
      sobre la posición de la calle (ajuste opcional).
    - Para cada offset X en `v_offsets` (calles verticales) ubicamos dos cajas:
      una arriba (y=0) y otra abajo (y=group_h_mm - caja_h), con X centrado en offset_x - caja_w/2.

    Devuelve dict con 'placements': lista de dicts con keys:
      - orientation: 'horizontal'|'vertical'
      - x,y,w,h (en mm) posición absoluta dentro del grupo
    """
    placements: List[Dict[str, Any]] = []

    # Colocar cajas horizontales (marcas a izquierda/derecha)
    box_w_h = caja_h_spec["box_w"]
    box_h_h = caja_h_spec["box_h"]

    for y in h_offsets:
        # izquierda
        x_left = 0.0
        y_top = float(y) - box_h_h / 2.0
        placements.append(
            {
                "orientation": "horizontal",
                "side": "left",
                "x": round(x_left, 6),
                "y": round(y_top, 6),
                "w": round(box_w_h, 6),
                "h": round(box_h_h, 6),
            }
        )
        # derecha
        x_right = float(group_w_mm) - box_w_h
        placements.append(
            {
                "orientation": "horizontal",
                "side": "right",
                "x": round(x_right, 6),
                "y": round(y_top, 6),
                "w": round(box_w_h, 6),
                "h": round(box_h_h, 6),
            }
        )

    # Colocar cajas verticales (marcas arriba/abajo)
    box_w_v = caja_v_spec["box_w"]
    box_h_v = caja_v_spec["box_h"]

    for x in v_offsets:
        # arriba
        y_top = 0.0
        x_left = float(x) - box_w_v / 2.0
        placements.append(
            {
                "orientation": "vertical",
                "side": "top",
                "x": round(x_left, 6),
                "y": round(y_top, 6),
                "w": round(box_w_v, 6),
                "h": round(box_h_v, 6),
            }
        )
        # abajo
        y_bottom = float(group_h_mm) - box_h_v
        placements.append(
            {
                "orientation": "vertical",
                "side": "bottom",
                "x": round(x_left, 6),
                "y": round(y_bottom, 6),
                "w": round(box_w_v, 6),
                "h": round(box_h_v, 6),
            }
        )

    return {
        "group_w_mm": group_w_mm,
        "group_h_mm": group_h_mm,
        "placements": placements,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# FUNCIONES DE CREACIÓN DE ELEMENTOS UI
# ═══════════════════════════════════════════════════════════════════════════════


def crear_linea_exterior(
    papel_w_mm: float,
    papel_h_mm: float,
    escala: float = 1,
    grosor_mm: float = GROSOR_LINEA_EXTERIOR_MM,
    color: str = ft.Colors.BLACK,
    visible: bool = True,
) -> ft.Stack:
    """
    Crea la línea exterior (borde del papel) como 4 rectángulos.

    Args:
        papel_w_mm: Ancho del papel en mm
        papel_h_mm: Alto del papel en mm
        escala: Factor de escala visual
        grosor_mm: Grosor de la línea en mm
        color: Color de la línea
        visible: Si debe ser visible

    Returns:
        ft.Stack con las 4 líneas del perímetro
    """
    ancho_px = mm_a_px(papel_w_mm, escala=escala)
    alto_px = mm_a_px(papel_h_mm, escala=escala)
    grosor_px = mm_a_px(grosor_mm, escala=escala)

    linea_exterior_container = ft.Container(
        width=ancho_px,
        height=alto_px,
        border=ft.Border.all(grosor_px, color),
        padding=0,
    )

    return ft.Stack(
        [linea_exterior_container],
        width=ancho_px,
        height=alto_px,
        left=0,
        top=0,
        visible=visible,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# CREACIÓN DEL STACK PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════


def crear_stack_vacio(
    grid_w_mm: float,
    grid_h_mm: float,
    sangre_mm: float,
    cruces_mm: float,
    offset_cruces_mm: float = 0.0,
    papel_w_mm: Optional[float] = None,
    papel_h_mm: Optional[float] = None,
    offset_pliego_x_mm: float = 0.0,
    offset_pliego_y_mm: float = 0.0,
    escala: float = 1,
) -> ft.Stack:
    """
    Crea el STACK PRINCIPAL VACÍO con estructura base de 3 capas.

    - Offset de cruces (separación adicional)

    Args:
        grid_w_mm: Ancho del grid/trazado en mm (660 mm típico)
        grid_h_mm: Alto del grid/trazado en mm (330 mm típico)
        sangre_mm: Sangre aplicada al trazado en mm (5 mm típico)
        cruces_mm: Longitud de cada brazo de la cruz en mm (10 mm típico)
        offset_cruces_mm: Offset adicional de cruces en mm (0 por defecto)
        papel_w_mm: Ancho del papel para el fondo (si None, usa tamaño de cruces)
        papel_h_mm: Alto del papel para el fondo (si None, usa tamaño de cruces)
        offset_pliego_x_mm: Offset X que posiciona todo el grupo (cruces+trazado) sobre el papel
        offset_pliego_y_mm: Offset Y que posiciona todo el grupo (cruces+trazado) sobre el papel
        escala: Factor de escala visual

    Returns:
        ft.Stack con estructura vacía lista para ser actualizada
    """
    # ─────────────────────────────────────────────────────────────────────────
    # CÁLCULOS DINÁMICOS DEL TAMAÑO DE CRUCES
    # ─────────────────────────────────────────────────────────────────────────

    # Paso 1: Tamaño sin sangre (donde se posicionan las cruces)
    sin_sangre_w = grid_w_mm - (2 * sangre_mm)
    sin_sangre_h = grid_h_mm - (2 * sangre_mm)

    # Paso 2: Tamaño de cruces = sin_sangre + cruces×2 + offset_cruces×2
    cruces_w = sin_sangre_w + (2 * cruces_mm) + (2 * offset_cruces_mm)
    cruces_h = sin_sangre_h + (2 * cruces_mm) + (2 * offset_cruces_mm)

    # Paso 3: Si no se especifica papel, usa el tamaño de cruces
    if papel_w_mm is None:
        papel_w_mm = cruces_w
    if papel_h_mm is None:
        papel_h_mm = cruces_h

    # ⚠️  IMPORTANTE: NO escalar usando ESCALA_VISUAL aquí
    # Los tamaños deben ser 1:1 con mm para que el InteractiveViewer.scale
    # sea la ÚNICA fuente de amplificación visual.
    # Si usamos ESCALA_VISUAL aquí + scale en viewer, se produce DOBLE escalado.
    papel_w_px = mm_a_px(papel_w_mm, escala=escala)
    papel_h_px = mm_a_px(papel_h_mm, escala=escala)
    cruces_w_px = mm_a_px(cruces_w, escala=escala)
    cruces_h_px = mm_a_px(cruces_h, escala=escala)
    grid_w_px = mm_a_px(grid_w_mm, escala=escala)
    grid_h_px = mm_a_px(grid_h_mm, escala=escala)
    offset_pliego_x_px = mm_a_px(offset_pliego_x_mm, escala=escala)
    offset_pliego_y_px = mm_a_px(offset_pliego_y_mm, escala=escala)

    # ─────────────────────────────────────────────────────────────────────────
    # CAPA 0: CRUCES Y MARCAS (dinámicamente dimensionada)
    # ─────────────────────────────────────────────────────────────────────────
    capa_cruces = ft.Container(
        width=cruces_w_px,
        height=cruces_h_px,
        bgcolor=ft.Colors.TRANSPARENT,
        visible=False,  # Por defecto las cruces no están visibles
        content=ft.Stack([]),  # Stack vacío
        left=offset_pliego_x_px,  # Posicionada por offset de pliego
        top=offset_pliego_y_px,
    )

    # ─────────────────────────────────────────────────────────────────────────
    # CAPA 1: TRAZADO GRID (siempre grid_w × grid_h)
    # ─────────────────────────────────────────────────────────────────────────
    # ⚠️  IMPORTANTE: Los offsets left/top se actualizan en centrar_grupo_trazado_en_pliego()
    capa_trazado = ft.Container(
        width=grid_w_px,
        height=grid_h_px,
        # TODO: bgcolor=ft.Colors.GREY_200,  # ← DESACTIVADO para ver celdas sin fondo
        visible=True,
        content=ft.Stack([]),  # Stack vacío, se llenará en actualizar_capa_trazado
        left=0,  # Se actualiza en centrar_grupo_trazado_en_pliego()
        top=0,  # Se actualiza en centrar_grupo_trazado_en_pliego()
    )

    # ─────────────────────────────────────────────────────────────────────────
    # CAPA 2: FONDO (Papel físico)
    # ─────────────────────────────────────────────────────────────────────────
    papel_fisico = ft.Container(
        width=papel_w_px,
        height=papel_h_px,
        # bgcolor=ft.Colors.AMBER_50,  # ← DESACTIVADO para ver GREY_100 del trazado
    )

    capa_fondo = ft.Stack(
        [papel_fisico],
        width=papel_w_px,
        height=papel_h_px,
    )

    # ─────────────────────────────────────────────────────────────────────────
    # CAPA 1: GRUPO TRAZADO (contiene trazado + cruces como una unidad)
    # ─────────────────────────────────────────────────────────────────────────
    # Este Stack interno engloba CRUCES y TRAZADO como UNA UNIDAD
    # Ambas capas se mueven y centran juntas
    # ⚠️  CAMBIO: Usar Container + Stack para que los left/top funcionen correctamente
    #     El Container es el contenedor del grupo (tamaño dinámico)
    #     El Stack dentro contiene cruces y trazado (con offsets)
    # ✅ Envolver el Stack en un Container para poder verlo con bgcolor
    grupo_stack_interno = ft.Stack(
        [capa_trazado, capa_cruces],
        width=cruces_w_px,
        height=cruces_h_px,
    )

    grupo_stack = ft.Container(
        content=grupo_stack_interno,
        width=cruces_w_px,
        height=cruces_h_px,
        bgcolor=ft.Colors.TRANSPARENT,
        padding=0,
        margin=0,
    )

    grupo_trazado = ft.Container(
        content=grupo_stack,
        width=cruces_w_px,
        height=cruces_h_px,
        bgcolor=ft.Colors.TRANSPARENT,
        left=0,
        top=0,
        padding=0,
        margin=0,
    )

    # ─────────────────────────────────────────────────────────────────────────
    # STACK PRINCIPAL CON 3 CAPAS
    # ─────────────────────────────────────────────────────────────────────────

    # Crear línea exterior que irá al final
    linea_exterior = crear_linea_exterior(
        papel_w_mm=papel_w_mm,
        papel_h_mm=papel_h_mm,
        escala=escala,
        visible=True,  # Mostrar siempre la línea exterior
    )

    # ─────────────────────────────────────────────────────────────────────────
    # CAPA 3: MARCA DE TEXTO (informativa, sobre el pliego completo)
    # ─────────────────────────────────────────────────────────────────────────
    # Esta capa usa el tamaño del PLIEGO COMPLETO, no el del grupo de cruces
    # Se posiciona relativa a los bordes del pliego
    # Se actualiza con actualizar_capa_marca_texto()
    capa_marca_texto = ft.Container(
        width=papel_w_px,
        height=papel_h_px,
        bgcolor=ft.Colors.TRANSPARENT,
        visible=False,
        content=ft.Stack([]),
    )

    stack_principal = ft.Stack(
        [
            capa_fondo,
            grupo_trazado,
            linea_exterior,
            capa_marca_texto,
        ],  # ✅ ORDEN: FONDO, GRUPO_TRAZADO, LÍNEA EXTERIOR, MARCA DE TEXTO (encima de todo)
        width=papel_w_px,
        height=papel_h_px,
    )

    # Guardar referencias para actualización posterior
    # ⚠️  NUEVA ESTRUCTURA: El grupo_trazado unifica trazado + cruces
    stack_principal.ref_capa_fondo = capa_fondo  # [0]
    stack_principal.ref_grupo_trazado = grupo_trazado  # [1]
    stack_principal.ref_linea_exterior = linea_exterior  # [2]
    stack_principal.ref_capa_marca_texto = capa_marca_texto  # [3]

    # Guardar parámetros para referencia
    stack_principal.grid_w_mm = grid_w_mm
    stack_principal.grid_h_mm = grid_h_mm
    stack_principal.cruces_w_mm = cruces_w
    stack_principal.cruces_h_mm = cruces_h
    stack_principal.papel_w_mm = papel_w_mm
    stack_principal.papel_h_mm = papel_h_mm
    stack_principal.offset_pliego_x_mm = offset_pliego_x_mm
    stack_principal.offset_pliego_y_mm = offset_pliego_y_mm

    return stack_principal


# ═══════════════════════════════════════════════════════════════════════════════
# ACTUALIZACIÓN DE CAPAS
# ═══════════════════════════════════════════════════════════════════════════════


def centrar_grupo_trazado_en_pliego(
    stack: ft.Stack,
    grupo_w_mm: float,
    grupo_h_mm: float,
    papel_w_mm: float,
    papel_h_mm: float,
    escala: float = 1,
    extra_offset_x_mm: float = 0.0,
    extra_offset_y_mm: float = 0.0,
) -> None:
    """
    Centra el GRUPO TRAZADO (que contiene trazado + cruces) dentro del papel.

    Se llama cuando cambia el tamaño del papel para recalcular offsets de centrado.

    Args:
        stack: El Stack principal
        grupo_w_mm: Ancho del grupo trazado+cruces en mm
        grupo_h_mm: Alto del grupo trazado+cruces en mm
        papel_w_mm: Ancho del papel en mm
        papel_h_mm: Alto del papel en mm
        escala: Factor de escala visual
    """
    if not hasattr(stack, "ref_grupo_trazado"):
        print(f"⚠️  Stack NO tiene ref_grupo_trazado")
        return

    # Calcular offsets para centrar y sumar offsets extra (p. ej. offsets de usuario)
    offset_x_mm = (papel_w_mm - grupo_w_mm) / 2.0 + (extra_offset_x_mm or 0.0)
    offset_y_mm = (papel_h_mm - grupo_h_mm) / 2.0 + (extra_offset_y_mm or 0.0)

    offset_x_px = mm_a_px(offset_x_mm, escala=escala)
    offset_y_px = mm_a_px(offset_y_mm, escala=escala)

    # Aplicar offsets al grupo trazado
    stack.controls[1].left = offset_x_px
    stack.controls[1].top = offset_y_px

    print(
        f"✅ Grupo trazado centrado: ({grupo_w_mm:.1f}×{grupo_h_mm:.1f}mm) en papel ({papel_w_mm:.1f}×{papel_h_mm:.1f}mm)"
    )
    print(
        f"   Offset: ({offset_x_mm:.1f}, {offset_y_mm:.1f})mm → ({offset_x_px:.1f}, {offset_y_px:.1f})px"
    )

    # ✅ IMPORTANTE: Marcar el grupo como necesitado de actualización
    stack.controls[1].update() if hasattr(stack.controls[1], "update") else None

    # Y actualizar el stack principal también
    stack.update() if hasattr(stack, "update") else None


def actualizar_capa_cruces(
    stack: ft.Stack,
    capa_cruces: Optional[ft.Container] = None,
    visible: bool = False,
    offset_pliego_x_mm: Optional[float] = None,
    offset_pliego_y_mm: Optional[float] = None,
    escala: float = 1,
) -> None:
    """
    Actualiza la CAPA CRUCES (dentro del grupo en stack.controls[1]).

    IMPORTANTE: Ahora stack.controls[1] es un Stack (el grupo completo), no un Container.
    El grupo tiene:
    - controls[0] = Container con trazado
    - controls[1] = Container con cruces

    Args:
        stack: El Stack principal
        capa_cruces: Container con las cruces (si es None, solo cambia visibilidad/offset)
        visible: Si la capa debe estar visible
        offset_pliego_x_mm: Offset X en mm que posiciona la capa sobre el papel
        offset_pliego_y_mm: Offset Y en mm que posiciona la capa sobre el papel
        escala: Factor de escala visual
    """
    if not hasattr(stack, "controls") or len(stack.controls) < 2:
        print(f"⚠️  Stack NO tiene suficientes controles")
        return

    # ✅ stack.controls[1] ahora es el Stack del grupo directamente
    grupo_stack = stack.controls[1]

    if not hasattr(grupo_stack, "controls") or len(grupo_stack.controls) < 2:
        print(f"⚠️  Grupo stack no tiene suficientes elementos")
        return

    # Las cruces están en [1] dentro del Stack del grupo
    if capa_cruces is not None:
        # Reemplazar control de cruces por el nuevo container creado
        grupo_stack.controls[1] = capa_cruces
        # Debug: mostrar el tamaño que trae la nueva capa
        try:
            w_new = getattr(capa_cruces, "width", None)
            h_new = getattr(capa_cruces, "height", None)
            print(f"   [DBG] nueva capa_cruces width={w_new}, height={h_new} (px)")
            # Si la capa trae tamaño explícito, asegurar que el control dentro del grupo
            # lo refleje (algunos objetos envuelven el Stack en un Container)
            if w_new is not None:
                grupo_stack.controls[1].width = w_new
            if h_new is not None:
                grupo_stack.controls[1].height = h_new
        except Exception as ex:
            print(f"   [DBG] no se pudo leer/ajustar tamaño de capa_cruces: {ex}")

    grupo_stack.controls[1].visible = visible

    # Actualizar offset de pliego si se proporciona
    if offset_pliego_x_mm is not None:
        left_px = mm_a_px(offset_pliego_x_mm, escala=escala)
        grupo_stack.controls[1].left = left_px
        print(
            f"   [DBG] aplicar offset_cruces_x: {offset_pliego_x_mm}mm -> {left_px}px"
        )

    if offset_pliego_y_mm is not None:
        top_px = mm_a_px(offset_pliego_y_mm, escala=escala)
        grupo_stack.controls[1].top = top_px
        print(f"   [DBG] aplicar offset_cruces_y: {offset_pliego_y_mm}mm -> {top_px}px")

    # Disparar actualización
    grupo_stack.update() if hasattr(grupo_stack, "update") else None
    stack.update() if hasattr(stack, "update") else None


def actualizar_capa_trazado(
    stack: ft.Stack,
    grid_visual: Optional[ft.Control] = None,
    offset_x_px: float = 0,
    offset_y_px: float = 0,
    ancho_mm: float = 660,
    alto_mm: float = 330,
    escala: float = 1,
) -> None:
    """
    Actualiza la CAPA TRAZADO (GRUPO COMPLETO).

    El grid_visual recibido ES el grupo completo (trazado + cruces) creado en
    crear_grupo_trazado_centrado(), con el tamaño correcto y posicionamiento correcto.

    IMPORTANTE: El grid_visual YA tiene:
    - Tamaño correcto (MAX de trazado y cruces)
    - Ambas capas (trazado + cruces) correctamente posicionadas
    - Offsets calculados correctamente (mayor a 0,0; menor centrado)

    Se envuelve en un Container para que centrar_grupo_trazado_en_pliego() pueda
    aplicar offsets adicionales de centrado en el papel.

    Args:
        stack: El Stack principal
        grid_visual: El grupo completo (Stack con trazado + cruces ya posicionados)
        offset_x_px: No se usa (ya está en grid_visual)
        offset_y_px: No se usa (ya está en grid_visual)
        ancho_mm: No se usa (ya está en grid_visual)
        alto_mm: No se usa (ya está en grid_visual)
        escala: Factor de escala visual
    """
    print(f"\n[📝 actualizar_capa_trazado]")
    print(f"   • grid_visual es None: {grid_visual is None}")

    if grid_visual is None:
        print(f"   ⚠️  grid_visual es None, no hay nada que actualizar")
        return

    if not hasattr(grid_visual, "width") or not hasattr(grid_visual, "height"):
        print(f"   ⚠️  grid_visual no tiene width/height")
        return

    print(f"   • grid_visual tamaño: {grid_visual.width}×{grid_visual.height}px")
    print(
        f"   • grid_visual tiene {len(grid_visual.controls) if hasattr(grid_visual, 'controls') else '?'} elementos"
    )

    # ✅ ENVOLVER grid_visual en un Container para permitir offsets de centrado en papel
    # El Container actúa como envolvente que centrar_grupo_trazado_en_pliego() puede manipular
    grupo_container = ft.Container(
        content=grid_visual,
        width=grid_visual.width,
        height=grid_visual.height,
        left=0,  # Inicialmente en (0,0), se actualiza en centrar_grupo_trazado_en_pliego()
        top=0,
    )

    # ✅ REEMPLAZAR el grupo anterior [1] con el nuevo grupo envuelto
    stack.controls[1] = grupo_container

    print(f"   ✅ Stack.controls[1] reemplazado con grid_visual envuelto en Container")
    print(f"   • Nuevo tamaño del grupo: {grid_visual.width}×{grid_visual.height}px")

    # Disparar actualización
    if hasattr(stack, "update"):
        stack.update()
        print(f"   ✅ Stack actualizado")
    else:
        print(f"   ⚠️  stack no tiene método update()")


def actualizar_capa_fondo(
    stack: ft.Stack,
    papel_w_mm: float,
    papel_h_mm: float,
    mostrar_linea_exterior: bool = True,
    escala: float = 1,
) -> None:
    """
    Actualiza la CAPA FONDO (ÍNDICE 0 en la nueva estructura).
    También regenera la LÍNEA EXTERIOR (ÍNDICE 2) con las nuevas dimensiones.

    Args:
        stack: El Stack principal
        papel_w_mm: Ancho del papel en mm
        papel_h_mm: Alto del papel en mm
        mostrar_linea_exterior: Si se debe mostrar el borde negro
        escala: Factor de escala visual
    """
    papel_w_px = mm_a_px(papel_w_mm, escala=escala)
    papel_h_px = mm_a_px(papel_h_mm, escala=escala)

    # Crear papel físico
    papel_fisico = ft.Container(
        width=papel_w_px,
        height=papel_h_px,
        bgcolor=ft.Colors.WHITE,  # ✅ Fondo blanco del pliego
    )

    # ⚠️  CAMBIO: La línea exterior ahora se agrega como ÚLTIMA capa del Stack principal
    # (para que esté ENCIMA del trazado y sea visible)
    # Aquí solo creamos el papel sin la línea

    # Crear nueva capa fondo (solo papel)
    capa_fondo = ft.Stack(
        [papel_fisico],
        width=papel_w_px,
        height=papel_h_px,
    )

    if hasattr(stack, "ref_capa_fondo"):
        stack.controls[0] = capa_fondo  # ✅ ÍNDICE 0 (papel siempre abajo)
        stack.ref_capa_fondo = capa_fondo

        # Actualizar tamaño del stack principal
        stack.width = papel_w_px
        stack.height = papel_h_px

        # ✅ REGENERAR LÍNEA EXTERIOR CON NUEVAS DIMENSIONES (ÍNDICE 2)
        # Siempre regenerar la línea, pero controlar su visibilidad según el parámetro
        if len(stack.controls) > 2:
            nueva_linea_exterior = crear_linea_exterior(
                papel_w_mm=papel_w_mm,
                papel_h_mm=papel_h_mm,
                escala=escala,
                visible=mostrar_linea_exterior,  # ✅ Controlar visibilidad
            )
            stack.controls[2] = nueva_linea_exterior  # ✅ ÍNDICE 2 (encima del trazado)
            stack.ref_linea_exterior = nueva_linea_exterior

        # Disparar actualización
        stack.update() if hasattr(stack, "update") else None


def actualizar_capa_marca_texto(
    stack: ft.Stack,
    capa_marca_texto: Optional[ft.Container] = None,
    visible: bool = True,
    papel_w_mm: Optional[float] = None,
    papel_h_mm: Optional[float] = None,
    escala: float = 1,
) -> None:
    """
    Actualiza la CAPA DE MARCA DE TEXTO (índice 3) en el stack principal.

    Esta capa es INDEPENDIENTE del grupo de cruces/trazado y usa el tamaño
    del PLIEGO COMPLETO para su posicionamiento.

    ⚠️ IMPORTANTE: La capa de texto NO está dentro del grupo de cruces porque:
    1. Usa dimensiones del PLIEGO FINAL (papel_w_mm × papel_h_mm)
    2. Se posiciona relativa a los bordes del pliego, no del área de cruces
    3. Debe ser visible independientemente del estado de las cruces

    Args:
        stack: Stack principal a actualizar
        capa_marca_texto: Container con el contenido de la marca de texto (o None)
        visible: Si True, muestra la capa; si False, oculta
        papel_w_mm: Ancho del pliego en mm (para ajustar tamaño si es necesario)
        papel_h_mm: Alto del pliego en mm (para ajustar tamaño si es necesario)
        escala: Factor de escala visual
    """
    if not hasattr(stack, "ref_capa_marca_texto"):
        print("[WARN] Stack no tiene ref_capa_marca_texto, saltando actualización")
        return

    # Obtener o crear la capa
    if len(stack.controls) <= 3:
        # No existe capa de texto, agregarla
        papel_w_px = mm_a_px(papel_w_mm or stack.papel_w_mm, escala=escala)
        papel_h_px = mm_a_px(papel_h_mm or stack.papel_h_mm, escala=escala)

        nueva_capa = ft.Container(
            width=papel_w_px,
            height=papel_h_px,
            bgcolor=ft.Colors.TRANSPARENT,
            visible=False,
            content=ft.Stack([]),
        )
        stack.controls.append(nueva_capa)
        stack.ref_capa_marca_texto = nueva_capa

    capa_actual = stack.controls[3]

    # Actualizar contenido si se proporciona
    if capa_marca_texto is not None:
        # capa_marca_texto ahora es un Stack, no un Container
        # Necesitamos copiar el contenido del Stack (los controles posicionados)
        if isinstance(capa_marca_texto, ft.Stack):
            # Es un Stack: copiar sus controles
            if isinstance(capa_actual.content, ft.Stack):
                capa_actual.content.controls = capa_marca_texto.controls.copy()
            else:
                # Crear nuevo Stack si no existe
                capa_actual.content = capa_marca_texto
            capa_actual.visible = visible
            # Si el contenido tiene su propia visibilidad, sincronizarla (solo visibilidad)
            try:
                if not visible and hasattr(capa_actual.content, "visible"):
                    capa_actual.content.visible = False
            except Exception:
                pass
            # Diagnóstico mínimo: comprobar estado real del control y su contenido
            try:
                ct = type(capa_actual.content).__name__
                cc = (
                    len(capa_actual.content.controls)
                    if hasattr(capa_actual.content, "controls")
                    else 0
                )
            except Exception:
                ct = "UNKNOWN"
                cc = "N/A"
            print(
                f"  [3] MARCA_TEXTO: actualizada (Stack con {len(capa_marca_texto.controls)} elementos), visible={visible} | content_type={ct} content_count={cc}"
            )
        else:
            # Fallback: es un Container antiguo
            capa_actual.content = (
                capa_marca_texto.content
                if hasattr(capa_marca_texto, "content")
                else capa_marca_texto
            )
            capa_actual.visible = visible
            try:
                if not visible and hasattr(capa_actual.content, "visible"):
                    capa_actual.content.visible = False
            except Exception:
                pass
            try:
                ct = type(capa_actual.content).__name__
                cc = (
                    len(capa_actual.content.controls)
                    if hasattr(capa_actual.content, "controls")
                    else 0
                )
            except Exception:
                ct = "UNKNOWN"
                cc = "N/A"
            print(
                f"  [3] MARCA_TEXTO: actualizada (Container), visible={visible} | content_type={ct} content_count={cc}"
            )
    else:
        # Solo actualizar visibilidad
        capa_actual.visible = visible
        try:
            if not visible and hasattr(capa_actual.content, "visible"):
                capa_actual.content.visible = False
        except Exception:
            pass
        try:
            ct = type(capa_actual.content).__name__
            cc = (
                len(capa_actual.content.controls)
                if hasattr(capa_actual.content, "controls")
                else 0
            )
        except Exception:
            ct = "UNKNOWN"
            cc = "N/A"
        print(
            f"  [3] MARCA_TEXTO: visibilidad={visible} (sin nuevo contenido) | content_type={ct} content_count={cc}"
        )

    # NOTE: No limpiar contenido ni cambiar tamaño aquí; solo controlar visibilidad

    # Actualizar tamaño si se proporciona papel nuevo
    if papel_w_mm is not None and papel_h_mm is not None:
        papel_w_px = mm_a_px(papel_w_mm, escala=escala)
        papel_h_px = mm_a_px(papel_h_mm, escala=escala)
        capa_actual.width = papel_w_px
        capa_actual.height = papel_h_px

    # Disparar actualización
    if hasattr(stack, "update"):
        stack.update()


# ═══════════════════════════════════════════════════════════════════════════════
# UTILIDADES
# ═══════════════════════════════════════════════════════════════════════════════


def obtener_info_stack(stack: ft.Stack) -> Dict[str, Any]:
    """
    Obtiene información del stack principal para debugging.

    Returns:
        Dict con información de cada capa
    """
    return {
        "tamaño_stack": f"{stack.width} × {stack.height} px",
        "capa_cruces": {
            "visible": stack.controls[0].visible if len(stack.controls) > 0 else None,
            "tamaño": (
                f"{stack.controls[0].width} × {stack.controls[0].height} px"
                if len(stack.controls) > 0
                else None
            ),
        },
        "capa_trazado": {
            "tamaño": (
                f"{stack.controls[1].width} × {stack.controls[1].height} px"
                if len(stack.controls) > 1
                else None
            ),
            "offset": (
                f"({stack.controls[1].left}, {stack.controls[1].top}) px"
                if len(stack.controls) > 1
                else None
            ),
        },
        "capa_fondo": {
            "tamaño": (
                f"{stack.controls[2].width} × {stack.controls[2].height} px"
                if len(stack.controls) > 2
                else None
            ),
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# EJEMPLO DE USO
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    """
    Ejemplo básico de cómo usar este módulo.
    """

    # 1. Crear stack vacío con parámetros dinámicos
    stack = crear_stack_vacio(
        grid_w_mm=0,
        grid_h_mm=0,
        sangre_mm=0,
        cruces_mm=0,
        offset_cruces_mm=0,
        papel_w_mm=0,
        papel_h_mm=0,
        offset_pliego_x_mm=0,
        offset_pliego_y_mm=0,
    )
    print("✅ Stack vacío creado con parámetros dinámicos")
    print(obtener_info_stack(stack))

    # 2. Simular actualización de cruces
    print("\n📍 Actualizando capa de cruces...")

    actualizar_capa_cruces(
        stack,
        capa_cruces=None,
        visible=False,
        offset_pliego_x_mm=0,
        offset_pliego_y_mm=0,
    )

    # 3. Simular actualización de trazado
    print("📍 Actualizando capa de trazado...")
    # Aquí vendría el grid real desde crear_grid_imposicion_NEW()
    actualizar_capa_trazado(
        stack, grid_visual=None, offset_x_px=0, offset_y_px=0, ancho_mm=0, alto_mm=0
    )

    # 4. Actualizar fondo
    print("📍 Actualizando capa de fondo...")
    actualizar_capa_fondo(
        stack, papel_w_mm=0, papel_h_mm=0, mostrar_linea_exterior=True
    )

    print("\n✅ Stack actualizado completamente")
    print(obtener_info_stack(stack))


# ═══════════════════════════════════════════════════════════════════════════════
# FUNCIONES DE GENERACIÓN DE CRUCES
# ═══════════════════════════════════════════════════════════════════════════════


def crear_cruz_esquina(
    punto_corte_x_px,
    punto_corte_y_px,
    longitud_mm,
    grosor_pt,
    offset_mm,
    escala_visual,
    tipo_esquina,
):
    """
    Crea una cruz de esquina (ángulo en L) en artes gráficas.

    IMPORTANTE:
    - La cruz siempre mide longitud_mm (ej: 10mm completos)
    - offset_mm controla dónde empieza la cruz desde el punto de corte
    - El usuario NO puede meter la cruz dentro del área de corte (máximo offset = -sangre_mm)

    Args:
        punto_corte_x_px: Posición X del punto de corte en píxeles
        punto_corte_y_px: Posición Y del punto de corte en píxeles
        longitud_mm: Longitud TOTAL de cada brazo en mm (siempre completo, ej: 10mm)
        grosor_pt: Grosor de las líneas en puntos
        offset_mm: Ajuste del usuario desde la sangre
        sangre_mm: Tamaño de la sangre
        escala_visual: Escala de conversión mm a píxeles
        tipo_esquina: "tl", "tr", "bl", "br" (top-left, top-right, etc.)

    Returns:
        Lista de ft.Container que forman el ángulo en L
    """
    longitud_px = longitud_mm * escala_visual
    # TODO GROSOR CRUCES
    # Usar el mismo grosor que las cruces (PT_TO_MM = 0.3528)

    grosor_px = grosor_pt * 0.3528
    grosor_px = grosor_px * escala_visual
    # grosor_px = grosor_pt / 72.0 * 96.0 * escala_visual  # Conversión simple pt a px

    offset_px = offset_mm * escala_visual

    longitud_cruz_px = longitud_px
    inicio_cruz_px = offset_px

    if longitud_cruz_px < 1:
        print(f"        ⚠️  Cruz demasiado pequeña: longitud={longitud_mm}mm")
        return []

    brazos = []

    if tipo_esquina == "tl":  # Superior izquierda
        brazos.append(
            ft.Container(
                width=grosor_px,
                height=longitud_cruz_px,
                bgcolor=ft.Colors.BLACK,
                left=punto_corte_x_px - grosor_px / 2,
                top=punto_corte_y_px - inicio_cruz_px - longitud_cruz_px,
            )
        )
        brazos.append(
            ft.Container(
                width=longitud_cruz_px,
                height=grosor_px,
                bgcolor=ft.Colors.BLACK,
                left=punto_corte_x_px - inicio_cruz_px - longitud_cruz_px,
                top=punto_corte_y_px - grosor_px / 2,
            )
        )

    elif tipo_esquina == "tr":  # Superior derecha
        brazos.append(
            ft.Container(
                width=grosor_px,
                height=longitud_cruz_px,
                bgcolor=ft.Colors.BLACK,
                left=punto_corte_x_px - grosor_px / 2,
                top=punto_corte_y_px - inicio_cruz_px - longitud_cruz_px,
            )
        )
        brazos.append(
            ft.Container(
                width=longitud_cruz_px,
                height=grosor_px,
                bgcolor=ft.Colors.BLACK,
                left=punto_corte_x_px + inicio_cruz_px,
                top=punto_corte_y_px - grosor_px / 2,
            )
        )

    elif tipo_esquina == "bl":  # Inferior izquierda
        brazos.append(
            ft.Container(
                width=grosor_px,
                height=longitud_cruz_px,
                bgcolor=ft.Colors.BLACK,
                left=punto_corte_x_px - grosor_px / 2,
                top=punto_corte_y_px + inicio_cruz_px,
            )
        )
        brazos.append(
            ft.Container(
                width=longitud_cruz_px,
                height=grosor_px,
                bgcolor=ft.Colors.BLACK,
                left=punto_corte_x_px - inicio_cruz_px - longitud_cruz_px,
                top=punto_corte_y_px - grosor_px / 2,
            )
        )

    elif tipo_esquina == "br":  # Inferior derecha
        brazos.append(
            ft.Container(
                width=grosor_px,
                height=longitud_cruz_px,
                bgcolor=ft.Colors.BLACK,
                left=punto_corte_x_px - grosor_px / 2,
                top=punto_corte_y_px + inicio_cruz_px,
            )
        )
        brazos.append(
            ft.Container(
                width=longitud_cruz_px,
                height=grosor_px,
                bgcolor=ft.Colors.BLACK,
                left=punto_corte_x_px + inicio_cruz_px,
                top=punto_corte_y_px - grosor_px / 2,
            )
        )

    return brazos


def crear_grupo_trazado_centrado(
    grid_visual,
    capa_cruces,
    offset_cruces_x_mm,
    offset_cruces_y_mm,
    offset_trazado_x_mm,
    offset_trazado_y_mm,
    trazado_w_mm,
    trazado_h_mm,
    cruces_w_mm,
    cruces_h_mm,
    escala=1.0,
):
    """
    Crea un GRUPO ÚNICO (trazado + cruces) ya centrado.

    Este grupo contiene AMBAS capas (trazado y cruces) posicionadas correctamente
    dentro de un contenedor único que se devuelve listo para usar en el Stack principal.

    Args:
        grid_visual: El Stack con el grid (celdas + imágenes)
        capa_cruces: El Container con las cruces
        offset_cruces_x_mm, offset_cruces_y_mm: Offsets para centrar cruces
        offset_trazado_x_mm, offset_trazado_y_mm: Offsets para centrar trazado
        trazado_w_mm, trazado_h_mm: Dimensiones del trazado
        cruces_w_mm, cruces_h_mm: Dimensiones de las cruces
        escala: Factor de escala (siempre 1.0, el viewer escala)

    Returns:
        Un Container que encapsula el grupo centrado (trazado + cruces)
    """
    # ✅ CALCULAR OFFSETS CORRECTAMENTE: El más grande siempre en (0,0), el pequeño centrado
    # Si recibimos None, calculamos automáticamente
    if offset_trazado_x_mm is None or offset_cruces_x_mm is None:
        if trazado_w_mm >= cruces_w_mm:
            offset_trazado_x_mm = 0
            offset_cruces_x_mm = (trazado_w_mm - cruces_w_mm) / 2
        else:
            offset_trazado_x_mm = (cruces_w_mm - trazado_w_mm) / 2
            offset_cruces_x_mm = 0

    if offset_trazado_y_mm is None or offset_cruces_y_mm is None:
        if trazado_h_mm >= cruces_h_mm:
            offset_trazado_y_mm = 0
            offset_cruces_y_mm = (trazado_h_mm - cruces_h_mm) / 2
        else:
            offset_trazado_y_mm = (cruces_h_mm - trazado_h_mm) / 2
            offset_cruces_y_mm = 0

    # Calcular el tamaño del grupo (el más grande entre ambos)
    grupo_w_mm = max(trazado_w_mm, cruces_w_mm)
    grupo_h_mm = max(trazado_h_mm, cruces_h_mm)

    # Convertir a píxeles (sin escala, el viewer lo hará)
    grupo_w_px = mm_a_px(grupo_w_mm, escala=escala)
    grupo_h_px = mm_a_px(grupo_h_mm, escala=escala)
    offset_trazado_x_px = mm_a_px(offset_trazado_x_mm, escala=escala)
    offset_trazado_y_px = mm_a_px(offset_trazado_y_mm, escala=escala)
    offset_cruces_x_px = mm_a_px(offset_cruces_x_mm, escala=escala)
    offset_cruces_y_px = mm_a_px(offset_cruces_y_mm, escala=escala)

    # Construir lista de controles ANTES de crear el Stack
    controles = [
        # CAPA 0: TRAZADO (primero, atrás)
        ft.Container(
            content=grid_visual,
            width=mm_a_px(trazado_w_mm, escala=escala),
            height=mm_a_px(trazado_h_mm, escala=escala),
            left=offset_trazado_x_px,
            top=offset_trazado_y_px,
            # visible=False,
            # TODO: bgcolor=ft.Colors.GREY_200,  # ← DESACTIVADO para ver celdas sin fondo
        ),
    ]

    # TODO CAPA 1: CRUCES
    if capa_cruces:
        controles.append(
            ft.Container(
                content=capa_cruces,
                width=mm_a_px(cruces_w_mm, escala=escala),
                height=mm_a_px(cruces_h_mm, escala=escala),
                left=offset_cruces_x_px,
                top=offset_cruces_y_px,
                bgcolor=ft.Colors.TRANSPARENT,  # Transparente para ver solo las cruces
            )
        )

    # Crear Stack con la lista de controles ya filtrada
    stack_grupo = ft.Stack(
        controles,
        width=grupo_w_px,
        height=grupo_h_px,
    )

    print(
        f"\n✅ GRUPO TRAZADO+CRUCES CENTRADO CREADO:"
        f"\n   • Tamaño final: {grupo_w_mm:.2f}×{grupo_h_mm:.2f}mm ({grupo_w_px:.0f}×{grupo_h_px:.0f}px)"
        f"\n   • Tamaño grupo (Stack): {grupo_w_px:.0f}×{grupo_h_px:.0f}px (FONDO AZUL)"
        f"\n   • Trazado: {trazado_w_mm:.2f}×{trazado_h_mm:.2f}mm ({mm_a_px(trazado_w_mm, escala=escala):.0f}×{mm_a_px(trazado_h_mm, escala=escala):.0f}px) en ({offset_trazado_x_mm:.2f}, {offset_trazado_y_mm:.2f})mm → ({offset_trazado_x_px:.0f}, {offset_trazado_y_px:.0f})px (BORDE ROJO)"
        f"\n   • Cruces: {cruces_w_mm:.2f}×{cruces_h_mm:.2f}mm ({mm_a_px(cruces_w_mm, escala=escala):.0f}×{mm_a_px(cruces_h_mm, escala=escala):.0f}px) en ({offset_cruces_x_mm:.2f}, {offset_cruces_y_mm:.2f})mm → ({offset_cruces_x_px:.0f}, {offset_cruces_y_px:.0f})px"
    )

    # ✅ Devolver el Stack directo (no envuelto en Container)
    # Esto asegura que sea compatible con actualizar_capa_trazado que espera un Stack
    return stack_grupo, grupo_w_mm, grupo_h_mm


def crear_capa_lineas_corte(
    dim_celds: Dict[str, Any],
    escala: float = 1,
    grosor_pt: float = 0.50,
) -> Optional[ft.Container]:
    """
    Crea la capa de líneas de corte azules (tamaño de usuario).

    Esta capa visualiza los rectángulos de corte final sobre el trazado.
    Las líneas se dibujan en azul y marcan el área de corte de cada celda.

    Args:
        dim_celds: Diccionario con datos de imposición (debe contener offsets_corte_tamano_usuario)
        escala: Factor de escala visual (mm a px)
        grosor_pt: Grosor de las líneas en puntos

    Returns:
        Container con las líneas de corte o None si no hay datos
    """
    print(f"\n{'='*80}")
    print("🔵 CREANDO CAPA DE LÍNEAS DE CORTE (Azules - Tamaño Usuario)")
    print(f"{'='*80}")

    # Obtener datos de offsets de corte
    offsets_corte = dim_celds.get("offsets_corte_tamano_usuario")
    if not offsets_corte:
        print("⚠️  No hay datos de offsets_corte_tamano_usuario en dim_celds")
        return None

    lineas_corte = offsets_corte.get("lineas_corte", [])
    if not lineas_corte:
        print("⚠️  No hay líneas de corte en offsets_corte_tamano_usuario")
        return None

    # Obtener tamaño total del trazado (sin cruces) - CON sangre exterior
    tamano_total_w_mm = dim_celds.get("tamano_total_w", 0)
    tamano_total_h_mm = dim_celds.get("tamano_total_h", 0)

    if tamano_total_w_mm <= 0 or tamano_total_h_mm <= 0:
        print("⚠️  Tamaño del trazado inválido")
        return None

    # ✅ LEER OFFSET PRECALCULADO (ya guardado en dims_impo)
    offset_x_mm = dim_celds.get("offset_lineas_corte_x_mm", 0)
    offset_y_mm = dim_celds.get("offset_lineas_corte_y_mm", 0)

    print(f"📐 Tamaño del trazado: {tamano_total_w_mm:.2f}×{tamano_total_h_mm:.2f}mm")
    print(f"📍 Offset de centrado: ({offset_x_mm:.2f}, {offset_y_mm:.2f})mm")
    print(f"📦 Número de líneas de corte: {len(lineas_corte)}")

    # Convertir grosor de puntos a mm y luego a px
    PT_TO_MM = 25.4 / 72.0  # Definir localmente para evitar importación circular
    grosor_mm = grosor_pt * PT_TO_MM
    grosor_px = grosor_mm * escala

    # Crear lista de líneas como Containers con bordes
    lineas_containers = []

    for i, linea in enumerate(lineas_corte):
        row = linea.get("row", 0)
        col = linea.get("col", 0)
        x_mm = linea.get("x_mm", 0)
        y_mm = linea.get("y_mm", 0)
        w_mm = linea.get("w_mm", 0)
        h_mm = linea.get("h_mm", 0)

        # ✅ APLICAR OFFSET para centrar las líneas
        x_mm_con_offset = x_mm + offset_x_mm
        y_mm_con_offset = y_mm + offset_y_mm

        # Convertir a píxeles
        x_px = x_mm_con_offset * escala
        y_px = y_mm_con_offset * escala
        w_px = w_mm * escala
        h_px = h_mm * escala

        if _PRINT_DEBUG:
            print(
                f"  Línea [{row},{col}]: pos=({x_mm:.1f},{y_mm:.1f})mm + offset({offset_x_mm:.1f},{offset_y_mm:.1f})mm = ({x_mm_con_offset:.1f},{y_mm_con_offset:.1f})mm, tamaño=({w_mm:.1f}×{h_mm:.1f})mm"
            )

        # Crear Container con borde azul
        # Solo dibujar los bordes exteriores para evitar duplicación
        container_linea = ft.Container(
            width=w_px,
            height=h_px,
            border=ft.Border.all(grosor_px, ft.Colors.BLUE),
            left=x_px,
            top=y_px,
        )

        lineas_containers.append(container_linea)

    # Crear Stack con todas las líneas
    stack_lineas = ft.Stack(
        controls=lineas_containers,
        width=tamano_total_w_mm * escala,
        height=tamano_total_h_mm * escala,
    )

    # Envolver en Container para control de visibilidad
    container_capa = ft.Container(
        content=stack_lineas,
        width=tamano_total_w_mm * escala,
        height=tamano_total_h_mm * escala,
        bgcolor=ft.Colors.TRANSPARENT,
    )

    # Calcular tamaño real del área de corte (sin sangre)
    tamano_corte_w_mm = offsets_corte.get("tamano_total_w", 0)
    tamano_corte_h_mm = offsets_corte.get("tamano_total_h", 0)

    print(f"✅ Capa de líneas de corte creada con {len(lineas_containers)} líneas")
    print(
        f"   Tamaño capa container: {tamano_total_w_mm:.2f}×{tamano_total_h_mm:.2f}mm (trazado con sangre)"
    )
    print(
        f"   Tamaño área de corte: {tamano_corte_w_mm:.2f}×{tamano_corte_h_mm:.2f}mm (sin sangre exterior)"
    )
    print(f"   Offsetaplicado: ({offset_x_mm:.2f}, {offset_y_mm:.2f})mm")
    print(f"{'='*80}\n")

    return container_capa


def crear_capa_marcas_medianales_internas(
    dim_celds,
    longitud_cruz_mm,
    escala_visual,
    ancho_corte_px,
    alto_corte_px,
    extension_fuera_px,
    longitud_marcas_exteriores_mm,
    offset_cruz_mm,
    tamano_usuario_w,
    tamano_usuario_h,
    calles_h,
    calles_v,
    offset_seguridad_mm=1.0,  # ✨ NUEVO: Offset de seguridad adicional
    use_auto_sangre: bool = False,  # Si True, usar sangre como base (con mínimo offset_seguridad_mm)
    longitud_brazo_max_mm=5.0,  # ✨ Longitud total de línea (valor de usuario, se divide /2 para cada brazo desde el centro)
    grosor_pt: float = 0.5,
):
    """
    Crea la capa de marcas medianales internas (cruces en intersecciones de calles).

    IMPORTANTE: Los offsets se calculan internamente desde el origen de la capa de cruces.

    Args:
        dim_celds: Dict para guardar información de las marcas
        longitud_cruz_mm: Longitud total de la cruz medianal (10mm típicamente)
        escala_visual: Factor de escala px/mm
        ancho_corte_px, alto_corte_px: Dimensiones del área de corte
        extension_fuera_px: Extensión total en px (con offset) - para tamaño del Stack
        longitud_marcas_exteriores_mm: Longitud de las marcas exteriores (20mm)
        offset_cruz_mm: Offset de usuario (dinámico, controlado desde UI)
        tamano_usuario_w: Ancho de cada celda usuario
        tamano_usuario_h: Alto de cada celda usuario
        calles_h: Anchos de calles verticales (entre columnas)
        calles_v: Anchos de calles horizontales (entre filas)

    Returns:
        Container con Stack de marcas medianales
    """
    # Grosor en puntos: preferir el valor pasado por la UI
    if grosor_pt is None:
        GROSOR_CRUZ_PT = 0.5
    else:
        GROSOR_CRUZ_PT = float(grosor_pt)
    PT_TO_MM = 25.4 / 72.0

    print(f"\n{'='*80}")
    print(f"🎯 CREANDO MARCAS MEDIANALES INTERNAS")
    print(f"{'='*80}")
    print(f"  tamano_usuario: {tamano_usuario_w}×{tamano_usuario_h}mm")
    print(f"  calles_h (verticales): {calles_h}")
    print(f"  calles_v (horizontales): {calles_v}")
    print(f"  longitud_marcas_exteriores: {longitud_marcas_exteriores_mm}mm")
    print(f"  offset_cruz_mm: {offset_cruz_mm}mm")

    marks_controls = []

    # Respetar el parámetro `longitud_brazo_max_mm` (proporcionado por la UI)
    try:
        longitud_brazo_mm = min(
            float(longitud_cruz_mm) / 2.0, float(longitud_brazo_max_mm)
        )
    except Exception:
        longitud_brazo_mm = float(longitud_cruz_mm) / 2.0
    stroke_mm = GROSOR_CRUZ_PT * PT_TO_MM
    stroke_px = stroke_mm * escala_visual

    # ✅ CALCULAR OFFSETS según especificación
    h_offsets_mm = []
    v_offsets_mm = []

    # Margen inicial (longitud marcas exteriores + offset usuario)
    # Si no hay calles en alguna dirección, no hay intersecciones internas -> capa vacía
    if len(calles_h) == 0 or len(calles_v) == 0:
        print(
            "[DBG] No hay calles suficientes para marcas medianales (grid=1). Devolviendo capa vacía."
        )
        dim_celds["marcas_medianales"] = {
            "h_offsets_mm": [],
            "v_offsets_mm": [],
            "calles_h": calles_h,
            "calles_v": calles_v,
            "offset_seguridad_mm": offset_seguridad_mm,
            "longitud_brazo_max_mm": longitud_brazo_max_mm,
            "num_cruces": 0,
        }
        stack_marcas = ft.Stack(
            [],
            width=ancho_corte_px + extension_fuera_px * 2,
            height=alto_corte_px + extension_fuera_px * 2,
            visible=True,
        )
        container_marcas = ft.Container(
            content=stack_marcas,
            width=ancho_corte_px + extension_fuera_px * 2,
            height=alto_corte_px + extension_fuera_px * 2,
            bgcolor=ft.Colors.TRANSPARENT,
            visible=True,
        )
        print("✅ Capa medianal vacía devuelta (grid=1).")
        return container_marcas

    # ✅ Obtener sangre para ajustar margen inicial
    sangre_mm = dim_celds.get("sangre_mm", 0.0)

    # El margen inicial debe incluir la sangre para saltar el área de sangrado exterior
    margen_inicial = longitud_marcas_exteriores_mm + offset_cruz_mm

    # Primera iteración: margen + tamaño celda
    h_offsets_mm.append(margen_inicial + tamano_usuario_h)
    v_offsets_mm.append(margen_inicial + tamano_usuario_w)

    # Siguientes iteraciones: offset anterior + tamaño celda + calle anterior
    # calles_h (horizontales, entre filas) afectan Y
    for i in range(1, len(calles_h)):
        offset_anterior_h = h_offsets_mm[-1]
        calle_anterior_h = calles_h[i - 1]
        h_offsets_mm.append(offset_anterior_h + tamano_usuario_h + calle_anterior_h)

    # calles_v (verticales, entre columnas) afectan X
    for j in range(1, len(calles_v)):
        offset_anterior_v = v_offsets_mm[-1]
        calle_anterior_v = calles_v[j - 1]
        v_offsets_mm.append(offset_anterior_v + tamano_usuario_w + calle_anterior_v)

    print(f"\n  📍 Offsets calculados:")
    print(f"     h_offsets_mm (Y): {h_offsets_mm}")
    print(f"     v_offsets_mm (X): {v_offsets_mm}")

    # ✅ Lista para guardar las líneas individuales para Fritz
    lineas_medianales = []
    grosor_mm = GROSOR_CRUZ_PT * PT_TO_MM  # Mismo grosor que las cruces

    # Iterar sobre intersecciones de calles
    for i, y_mm in enumerate(h_offsets_mm):
        # Calle horizontal (entre filas) afecta Y - usa calles_h
        calle_h_size = calles_h[i] if i < len(calles_h) else 0.0

        for j, x_mm in enumerate(v_offsets_mm):
            # Calle vertical (entre columnas) afecta X - usa calles_v
            calle_v_size = calles_v[j] if j < len(calles_v) else 0.0

            # ✅ LÓGICA CORRECTA: Longitud fija, visibilidad por espacio disponible
            margen_seguridad = float(
                offset_seguridad_mm if offset_seguridad_mm is not None else 1.0
            )

            # Longitud SIEMPRE fija: longitud_brazo_max_mm define el tamaño total de usuario
            # Cada brazo usa la mitad de este valor (desde el centro hacia cada lado)
            longitud_h = longitud_brazo_max_mm / 2
            longitud_v = longitud_brazo_max_mm / 2

            # Visibilidad: ¿Cabe la línea completa (ambos brazos) con el margen de seguridad?
            # Líneas horizontales dependen de calle_h (horizontal)
            # Líneas verticales dependen de calle_v (vertical)
            espacio_necesario = 2 * margen_seguridad

            puede_h = calle_h_size >= espacio_necesario and calle_h_size > 0
            puede_v = calle_v_size >= espacio_necesario and calle_v_size > 0

            if not puede_h and not puede_v:
                continue

            # Centro de la intersección (en medio de cada calle)
            center_x = calle_v_size / 2 if calle_v_size > 0 else 0
            center_y = calle_h_size / 2 if calle_h_size > 0 else 0

            cruz_x = x_mm + center_x
            cruz_y = y_mm + center_y

            if _PRINT_DEBUG:
                print(f"  ✓ Cruz en H{i}∩V{j}: ({cruz_x:.1f}, {cruz_y:.1f})mm")

            # Líneas horizontales
            if puede_h:
                # Brazo izquierdo
                marks_controls.append(
                    ft.Container(
                        width=longitud_h * escala_visual,
                        height=stroke_px,
                        bgcolor=ft.Colors.BLACK,
                        left=(cruz_x - longitud_h) * escala_visual,
                        top=cruz_y * escala_visual,
                    )
                )
                lineas_medianales.append(
                    {
                        "tipo": "horizontal",
                        "brazo": "izquierdo",
                        "x_mm": cruz_x - longitud_h,
                        "y_mm": cruz_y,
                        "width_mm": longitud_h,
                        "height_mm": grosor_mm,
                        "interseccion": f"H{i}∩V{j}",
                    }
                )

                # Brazo derecho
                marks_controls.append(
                    ft.Container(
                        width=longitud_h * escala_visual,
                        height=stroke_px,
                        bgcolor=ft.Colors.BLACK,
                        left=cruz_x * escala_visual,
                        top=cruz_y * escala_visual,
                    )
                )
                lineas_medianales.append(
                    {
                        "tipo": "horizontal",
                        "brazo": "derecho",
                        "x_mm": cruz_x,
                        "y_mm": cruz_y,
                        "width_mm": longitud_h,
                        "height_mm": grosor_mm,
                        "interseccion": f"H{i}∩V{j}",
                    }
                )

            # Líneas verticales
            if puede_v:
                # Brazo superior
                marks_controls.append(
                    ft.Container(
                        width=stroke_px,
                        height=longitud_v * escala_visual,
                        bgcolor=ft.Colors.BLACK,
                        left=(cruz_x - stroke_mm / 2.0) * escala_visual,
                        top=(cruz_y - longitud_v) * escala_visual,
                    )
                )
                lineas_medianales.append(
                    {
                        "tipo": "vertical",
                        "brazo": "superior",
                        "x_mm": cruz_x - grosor_mm / 2.0,
                        "y_mm": cruz_y - longitud_v,
                        "width_mm": grosor_mm,
                        "height_mm": longitud_v,
                        "interseccion": f"H{i}∩V{j}",
                    }
                )

                # Brazo inferior
                marks_controls.append(
                    ft.Container(
                        width=stroke_px,
                        height=longitud_v * escala_visual,
                        bgcolor=ft.Colors.BLACK,
                        left=(cruz_x - stroke_mm / 2.0) * escala_visual,
                        top=cruz_y * escala_visual,
                    )
                )
                lineas_medianales.append(
                    {
                        "tipo": "vertical",
                        "brazo": "inferior",
                        "x_mm": cruz_x - grosor_mm / 2.0,
                        "y_mm": cruz_y,
                        "width_mm": grosor_mm,
                        "height_mm": longitud_v,
                        "interseccion": f"H{i}∩V{j}",
                    }
                )

    # Guardar info en dim_celds
    dim_celds["marcas_medianales"] = {
        "lineas_medianales": lineas_medianales,  # ✅ Lista completa de líneas individuales
        "offset_seguridad_mm": offset_seguridad_mm,
        "longitud_brazo_max_mm": longitud_brazo_max_mm,
        "grosor_mm": grosor_mm,
        "grosor_pt": GROSOR_CRUZ_PT,
        "num_cruces": len(marks_controls) // 4,
        "num_lineas": len(lineas_medianales),
    }

    # Crear Stack con el tamaño completo (incluye offset de usuario)
    # extension_fuera_px ya viene calculado desde trazado_ui.py
    stack_marcas = ft.Stack(
        marks_controls,
        width=ancho_corte_px + extension_fuera_px * 2,
        height=alto_corte_px + extension_fuera_px * 2,
        visible=True,
    )

    container_marcas = ft.Container(
        content=stack_marcas,
        width=ancho_corte_px + extension_fuera_px * 2,
        height=alto_corte_px + extension_fuera_px * 2,
        bgcolor=ft.Colors.TRANSPARENT,
        visible=True,
    )

    print(
        f"✅ Capa de marcas medianales creada con {len(marks_controls)} líneas ({len(marks_controls)//4} cruces)"
    )
    print(f"{'='*80}\n")

    return container_marcas


def calcular_alignment_y_padding_marca_texto(
    pos_sup_izq: bool,
    pos_sup_der: bool,
    pos_inf_izq: bool,
    pos_inf_der: bool,
    pos_centro_sup: bool,
    pos_centro_inf: bool,
    pos_centro_lat_izq: bool,
    pos_centro_lat_der: bool,
    offset_h_mm: float,
    offset_v_mm: float,
    escala_visual: float = 1.0,
    aliniacion_texto_rotacion=None,
    tamano_corte_w_mm: float = 0.0,
    tamano_corte_h_mm: float = 0.0,
    rotacion: int = 0,
):
    """
    Calcula alignment y padding para posicionar la marca de texto.
    Las variables no usadas serviran para calcular el maximo offset posible segun la posicion.
    """
    print(f"rotacion antes de calcular alignment: {rotacion}")
    # Superior izquierda
    if pos_sup_izq:
        alignment = ft.Alignment.TOP_LEFT
        if rotacion == 90:
            aliniacion_texto_rotacion = ft.Alignment.BOTTOM_LEFT
        elif rotacion == 180:
            aliniacion_texto_rotacion = ft.Alignment.BOTTOM_RIGHT
        elif rotacion == 270:
            aliniacion_texto_rotacion = ft.Alignment.TOP_RIGHT
        else:
            aliniacion_texto_rotacion = ft.Alignment.TOP_LEFT

        pos_nombre = "SUPERIOR IZQUIERDA"

        print(
            f"rotacion: {rotacion}, alignment: {alignment} aliniacion_texto_rotacion: {aliniacion_texto_rotacion}"
        )

    # Superior derecha
    elif pos_sup_der:
        alignment = ft.Alignment.TOP_RIGHT
        if rotacion == 90:
            aliniacion_texto_rotacion = ft.Alignment.TOP_LEFT
        elif rotacion == 180:
            aliniacion_texto_rotacion = ft.Alignment.BOTTOM_LEFT
        elif rotacion == 270:
            aliniacion_texto_rotacion = ft.Alignment.BOTTOM_RIGHT
        else:
            aliniacion_texto_rotacion = ft.Alignment.TOP_RIGHT

        pos_nombre = "SUPERIOR DERECHA"

    # Inferior izquierda
    elif pos_inf_izq:
        alignment = ft.Alignment.BOTTOM_LEFT
        if rotacion == 90:
            aliniacion_texto_rotacion = ft.Alignment.BOTTOM_RIGHT
        elif rotacion == 180:
            aliniacion_texto_rotacion = ft.Alignment.TOP_RIGHT
        elif rotacion == 270:
            aliniacion_texto_rotacion = ft.Alignment.TOP_LEFT
        else:
            aliniacion_texto_rotacion = ft.Alignment.BOTTOM_LEFT

        pos_nombre = "INFERIOR IZQUIERDA"

    # Inferior derecha
    elif pos_inf_der:
        alignment = ft.Alignment.BOTTOM_RIGHT
        if rotacion == 90:
            aliniacion_texto_rotacion = ft.Alignment.TOP_RIGHT
        elif rotacion == 180:
            aliniacion_texto_rotacion = ft.Alignment.TOP_LEFT
        elif rotacion == 270:
            aliniacion_texto_rotacion = ft.Alignment.BOTTOM_LEFT
        else:
            aliniacion_texto_rotacion = ft.Alignment.BOTTOM_RIGHT

        pos_nombre = "INFERIOR DERECHA"

    # Centro superior
    elif pos_centro_sup:
        alignment = ft.Alignment.TOP_CENTER
        if rotacion == 90:
            aliniacion_texto_rotacion = ft.Alignment.CENTER_LEFT
        elif rotacion == 180:
            aliniacion_texto_rotacion = ft.Alignment.BOTTOM_CENTER
        elif rotacion == 270:
            aliniacion_texto_rotacion = ft.Alignment.CENTER_RIGHT
        else:
            aliniacion_texto_rotacion = ft.Alignment.TOP_CENTER

        pos_nombre = "CENTRO SUPERIOR - top_center "

    # Centro inferior
    elif pos_centro_inf:
        alignment = ft.Alignment.BOTTOM_CENTER
        if rotacion == 90:
            aliniacion_texto_rotacion = ft.Alignment.CENTER_RIGHT
        elif rotacion == 180:
            aliniacion_texto_rotacion = ft.Alignment.TOP_CENTER
        elif rotacion == 270:
            aliniacion_texto_rotacion = ft.Alignment.CENTER_LEFT
        else:
            aliniacion_texto_rotacion = ft.Alignment.BOTTOM_CENTER

        pos_nombre = "CENTRO INFERIOR - bottom_center"

    # Centro lateral izquierdo
    elif pos_centro_lat_izq:
        alignment = ft.Alignment.CENTER_LEFT
        if rotacion == 90:
            aliniacion_texto_rotacion = ft.Alignment.BOTTOM_CENTER
        elif rotacion == 180:
            aliniacion_texto_rotacion = ft.Alignment.CENTER_RIGHT
        elif rotacion == 270:
            aliniacion_texto_rotacion = ft.Alignment.TOP_CENTER
        else:
            aliniacion_texto_rotacion = ft.Alignment.CENTER_LEFT

        pos_nombre = "CENTRO LATERAL IZQUIERDO"

    # Centro lateral derecho
    elif pos_centro_lat_der:
        alignment = ft.Alignment.CENTER_RIGHT
        if rotacion == 90:
            aliniacion_texto_rotacion = ft.Alignment.TOP_CENTER
        elif rotacion == 180:
            aliniacion_texto_rotacion = ft.Alignment.CENTER_LEFT
        elif rotacion == 270:
            aliniacion_texto_rotacion = ft.Alignment.BOTTOM_CENTER
        else:
            aliniacion_texto_rotacion = ft.Alignment.CENTER_RIGHT

        pos_nombre = "CENTRO LATERAL DERECHO"

    else:
        # Default: superior izquierda
        alignment = ft.Alignment.TOP_LEFT
        rotacion = 0
        pos_nombre = "NINGUNA (default: superior izquierda)"

    print(f"\n{'─'*80}")
    print(f"📍 CALCULANDO ALIGNMENT Y ROTACION")
    print(f"{'─'*80}")
    print(f"  🎯 Posición: {pos_nombre}")
    print(f"  📐 Alignment: {alignment}")
    print(f"  📦 Rotación: {rotacion}")

    return (
        alignment,
        rotacion,
        pos_nombre,
        aliniacion_texto_rotacion,
        tamano_corte_w_mm,
        tamano_corte_h_mm,
    )


def crear_capa_marca_texto(
    dim_celds,
    contenido: str,
    pos_sup_izq: bool,
    pos_sup_der: bool,
    pos_inf_izq: bool,
    pos_inf_der: bool,
    pos_centro_sup: bool,
    pos_centro_inf: bool,
    pos_centro_lat_izq: bool,
    pos_centro_lat_der: bool,
    familia: str,
    tipo: str,
    cuerpo: float,
    color: str,
    offset_h_mm: float,
    offset_v_mm: float,
    tamano_corte_w_mm: float,
    tamano_corte_h_mm: float,
    escala_visual: float = 1.0,
    viewer_zoom: Optional[float] = None,
    rotacion_grados: int = 0,
):
    """
    Crea la capa de marca de texto informativa.

    Args:
        dim_celds: Diccionario con información de imposición
        contenido: Texto a mostrar
        pos_sup_izq: Posición superior izquierda
        pos_sup_der: Posición superior derecha
        pos_inf_izq: Posición inferior izquierda
        pos_inf_der: Posición inferior derecha
        pos_centro_sup: Posición centro superior
        pos_centro_inf: Posición centro inferior
        pos_centro_lat_izq: Posición centro lateral izquierdo
        pos_centro_lat_der: Posición centro lateral derecho
        rotacion: Rotación en grados (0, 90, 180, 270)
        familia: Familia de fuente (Arial, Helvetica, etc.)
        tipo: Tipo de fuente (Regular, Bold, Italic, Bold Italic)
        cuerpo: Tamaño de fuente en puntos
        color: Color del texto
        offset_h_mm: Offset horizontal adicional
        offset_v_mm: Offset vertical adicional
        ancho_corte_px: Ancho del área de corte en píxeles
        alto_corte_px: Alto del área de corte en píxeles
        extension_fuera_px: Extensión exterior en píxeles
        escala_visual: Factor de escala px/mm

    Returns:
        Container con el texto posicionado o None si hay error
    """
    import math

    print(f"\n{'='*80}")
    print(f"🎯 CREANDO CAPA DE MARCA DE TEXTO")
    print(f"{'='*80}")
    print(f"  Contenido: '{contenido}'")
    print(f"  Familia: {familia}, Tipo: {tipo}, Cuerpo: {cuerpo}pt")
    print(f"  Offsets: H={offset_h_mm}mm, V={offset_v_mm}mm")

    tamano_corte_w_mm = tamano_corte_w_mm / escala_visual
    tamano_corte_h_mm = tamano_corte_h_mm / escala_visual

    print(f"  Tamaño corte: {tamano_corte_w_mm:.1f}×{tamano_corte_h_mm:.1f}mm")

    print(f"rotacion_grados: {rotacion_grados}")

    texto_size_mm = cuerpo * 0.3528
    texto_size = texto_size_mm * escala_visual

    # Calcular alignment y padding
    (
        alignment_container,
        rotacion_por_posicion,
        posicion_nombre,
        aliniacion_texto_rotacion,
        tamano_corte_w_mm,
        tamano_corte_h_mm,
    ) = calcular_alignment_y_padding_marca_texto(
        pos_sup_izq,
        pos_sup_der,
        pos_inf_izq,
        pos_inf_der,
        pos_centro_sup,
        pos_centro_inf,
        pos_centro_lat_izq,
        pos_centro_lat_der,
        offset_h_mm=offset_h_mm,
        offset_v_mm=offset_v_mm,
        escala_visual=escala_visual,
        tamano_corte_w_mm=tamano_corte_w_mm,
        tamano_corte_h_mm=tamano_corte_h_mm,
        rotacion=rotacion_grados,
    )

    # Calcular rotación si es necesario
    # En Flet canvas los ángulos positivos son CCW, por lo que 270° CCW = 90° CW (visualmente igual a 90°).
    # Para obtener la rotación visual correcta, convertimos ángulos > 180° a su equivalente negativo:
    #   270° → -90°  (90° CW)
    radianes = None
    if rotacion_por_posicion != 0:
        angulo_normalizado = (
            rotacion_por_posicion
            if rotacion_por_posicion <= 180
            else rotacion_por_posicion - 360
        )
        radianes = math.radians(angulo_normalizado)
        print(
            f"  🔄 Rotación: {rotacion_por_posicion}° → normalizado {angulo_normalizado}° ({radianes:.4f} rad) - aplicada al ft.Text"
        )

    canvas_w = tamano_corte_w_mm
    canvas_h = tamano_corte_h_mm

    # Convertir offsets (mm) a píxeles del canvas (px = mm * escala_visual) (esta mierda no sirve para nada)
    offset_canvas_x = offset_h_mm * escala_visual
    offset_canvas_y = offset_v_mm * escala_visual

    print(
        f"[OFFSET CONVERTED] offset_mm=({offset_h_mm},{offset_v_mm}) -> canvas_px=({offset_canvas_x:.1f},{offset_canvas_y:.1f})"
    )

    # Mapear tipo de fuente a weight de Flet
    weight_map = {
        "Regular": ft.FontWeight.NORMAL,
        "Bold": ft.FontWeight.BOLD,
        "Italic": ft.FontWeight.NORMAL,  # Italic se maneja con italic=True
        "Bold Italic": ft.FontWeight.BOLD,
    }

    font_weight = weight_map.get(tipo, ft.FontWeight.NORMAL)
    is_italic = "Italic" in tipo

    print(
        f"[FONT] familia={familia}, tipo={tipo}, weight={font_weight}, italic={is_italic}"
    )

    # ponytail: fuentes de sistema (Arial, Helvetica...) no registradas en page.fonts
    # no resuelven en Canvas de Windows -> fallback a None (fuente por defecto)
    _font_family = familia or None
    if isinstance(_font_family, str) and _font_family.strip().lower() in (
        "arial",
        "arial unicode ms",
        "helvetica",
        "times new roman",
        "courier new",
        "verdana",
        "georgia",
        "sans-serif",
    ):
        _font_family = None
    _color_str = color.value if hasattr(color, "value") else str(color)
    print(
        f"[MARCA_TEXTO VIEWER] contenido={repr(contenido)} size={texto_size:.1f}px "
        f"color_type={type(color).__name__} familia={familia!r}->{_font_family!r} "
        f"canvas={canvas_w:.0f}x{canvas_h:.0f}"
    )

    cv_text = cv.Text(
        offset_canvas_x,
        offset_canvas_y,
        contenido,
        ft.TextStyle(
            size=texto_size,
            color=_color_str,
            height=1.0,
            letter_spacing=0,
            word_spacing=0,
            font_family=_font_family,
            weight=font_weight,
            italic=is_italic,
        ),
        # `rotate` es Number (no Optional) en Flet 1.0: pasar None lo rompe.
        rotate=radianes if radianes is not None else 0,
        alignment=aliniacion_texto_rotacion,
    )

    # Print de valores implícitos usados para depuración (petición del usuario)
    try:
        print(
            "[IMPLICIT VALUES]",
            f"offset_h_mm={offset_h_mm}",
            f"offset_v_mm={offset_v_mm}",
            f"contenido={repr(contenido)}",
            f"texto_size={texto_size}",
            f"color={color}",
            f"height={1.0}",
            f"letter_spacing={0}",
            f"word_spacing={0}",
            f"bgcolor={ft.Colors.BLUE_300}",
            f"rotate={radianes}",
            f"alignment_text={aliniacion_texto_rotacion}",
            f"canvas_w={canvas_w}",
            f"canvas_h={canvas_h}",
            f"alignment_container={alignment_container}",
        )
    except Exception as _e:
        print(f"[IMPLICIT VALUES] error al imprimir valores: {_e}")

    # ponytail: el Canvas necesita width/height explicitos. Antes de la migracion
    # a Flet 1.0 el ft.InteractiveViewer de impo_ui.py le imponia las restricciones
    # al hijo y `cv.Canvas([cv_text])` se autodimensionaba; al sustituirlo por un
    # ft.Container (sin `.scale` en 1.0) ese Canvas se quedaba sin tamano y no
    # pintaba nada -> el texto era invisible a cualquier tamano, en Mac y en PC.
    canvas_contenido = cv.Canvas(
        shapes=[cv_text],
        width=canvas_w,
        height=canvas_h,
    )

    contenedor_posicionado = ft.Container(
        content=canvas_contenido,
        alignment=alignment_container,
        width=canvas_w,
        height=canvas_h,
    )

    stack_final = ft.Stack(
        [contenedor_posicionado],
        width=canvas_w,
        height=canvas_h,
    )

    # Guardar configuración en dim_celds para exportación PDF
    # Determinar posición como string para el PDF
    if pos_sup_izq:
        pos_str = "sup_izq"
    elif pos_sup_der:
        pos_str = "sup_der"
    elif pos_inf_izq:
        pos_str = "inf_izq"
    elif pos_inf_der:
        pos_str = "inf_der"
    elif pos_centro_sup:
        pos_str = "centro_sup"
    elif pos_centro_inf:
        pos_str = "centro_inf"
    elif pos_centro_lat_izq:
        pos_str = "centro_lat_izq"
    elif pos_centro_lat_der:
        pos_str = "centro_lat_der"
    else:
        pos_str = "sup_izq"  # Default

    dim_celds["marca_texto"] = {
        "contenido": contenido,
        "posicion": pos_str,
        "offset_h_mm": offset_h_mm,
        "offset_v_mm": offset_v_mm,
        "rotacion": rotacion_por_posicion,
        "familia": familia,
        "tipo": tipo,
        "cuerpo": cuerpo,
        "color": color,
    }

    print(f"✅ Capa de marca de texto creada")

    print(f"{'='*80}\n")

    return stack_final


def crear_capa_marcas_corte_exteriores(
    dim_celds,
    longitud_cruz_mm,
    offset_cruz,
    escala_visual,
    ancho_corte_px,
    alto_corte_px,
    extension_fuera_px,
    grosor_pt: float = 0.5,
):
    """
    Crea la capa de marcas de corte exteriores (internas del trazado).
    Usa los globals TAMANO_USUARIO_W/H y CALLES_L directamente.
    Guarda la info en dim_celds["marcas_corte"] para crear el PDF.
    Devuelve (container_marcas, margen_exterior_px).
    """
    print(f"\n{'='*80}")
    print(f"📏 CREANDO CAPA DE MARCAS DE CORTE EXTERIORES")
    print(f"{'='*80}")
    # print(f"[DBG] dim_celds keys: {dim_celds}")

    # Grosor en puntos: preferir el valor pasado por la UI
    if grosor_pt is None:
        GROSOR_CRUZ_PT = 0.5
    else:
        GROSOR_CRUZ_PT = float(grosor_pt)
    PT_TO_MM = 25.4 / 72.0

    # Obtener dimensiones del grid desde dim_celds
    grid_info = dim_celds.get("offsets_grid_info", {})
    GRID_ROWS = grid_info.get("grid_rows", 0)  # ✅ CORREGIDO: era "rows"
    GRID_COLS = grid_info.get("grid_cols", 0)  # ✅ CORREGIDO: era "cols"

    # Valores por defecto si no están en offsets_corte
    TAMANO_USUARIO_W = 210.0
    TAMANO_USUARIO_H = 100.0

    # Obtener calles desde dim_celds (valores actualizados)
    calles_list = []
    calles_h = []
    calles_v = []

    # Intentar obtener calles de offsets_grid_info primero
    if (
        "offsets_grid_info" in dim_celds and grid_info.get("grid_rows", 0) > 0
    ):  # ✅ CORREGIDO: era "rows"
        calles_h = grid_info.get("calles_h", [])
        calles_v = grid_info.get("calles_v", [])

    # Si están vacías (o no existía offsets_grid_info), intentar fallback
    if not calles_h and not calles_v:
        if "horiz_calles" in dim_celds and "vert_calles" in dim_celds:
            # Fallback: usar las claves directas si existen
            calles_h = dim_celds["horiz_calles"]
            calles_v = dim_celds["vert_calles"]

            # Recalcular filas/cols si no venían en grid_info o eran 1x1 por defecto
            if GRID_ROWS <= 1:
                GRID_ROWS = len(calles_h) + 1
            if GRID_COLS <= 1:
                GRID_COLS = len(calles_v) + 1

            print(
                f"[DBG] Usando fallback horiz_calles/vert_calles. Rows={GRID_ROWS}, Cols={GRID_COLS}"
            )

    # Default a 1 si sigue siendo 0
    if GRID_ROWS == 0:
        GRID_ROWS = 1
    if GRID_COLS == 0:
        GRID_COLS = 1

    # Reconstruir formato V-first [V1, V2, H1, H2]
    calles_list = calles_v + calles_h
    print(f"[DBG] Usando calles desde dim_celds['offsets_grid_info']:")
    print(f"      calles_h: {calles_h}")
    print(f"      calles_v: {calles_v}")
    print(f"      calles_list: {calles_list}")

    # Extraer tamaño usuario desde dim_celds
    offsets_corte = dim_celds.get("offsets_corte_tamano_usuario", {})
    lineas_corte = offsets_corte.get("lineas_corte", [])
    if lineas_corte:
        tamano_usuario_w = lineas_corte[0]["w_mm"]
        tamano_usuario_h = lineas_corte[0]["h_mm"]
    else:
        tamano_usuario_w = TAMANO_USUARIO_W
        tamano_usuario_h = TAMANO_USUARIO_H

    # ✅ Obtener sangre de dim_celds para ajustar offsets
    sangre_mm = dim_celds.get("sangre_mm", 0.0)

    # Calcular offsets donde van las cajas de marcas
    offsets = calcular_offsets_marcas(
        tamano_usuario_w=tamano_usuario_w,
        tamano_usuario_h=tamano_usuario_h,
        calles=calles_list,
        grid_rows=GRID_ROWS,
        grid_cols=GRID_COLS,
        longitud_cruz_mm=longitud_cruz_mm,
        offset_cruz_mm=offset_cruz,
    )

    h_offsets_mm = offsets.get("h_offsets_mm", [])
    v_offsets_mm = offsets.get("v_offsets_mm", [])

    marks_controls: List[ft.Control] = []
    stroke_mm = GROSOR_CRUZ_PT * PT_TO_MM
    stroke_px = stroke_mm * escala_visual

    # Tamaño total del área CON extensión de cruces (para posicionar cajas opuestas)
    ancho_total_mm = ancho_corte_px / escala_visual
    alto_total_mm = alto_corte_px / escala_visual

    print(
        f"[DBG] Tamaño total CON cruces: ancho={ancho_total_mm:.1f}mm, alto={alto_total_mm:.1f}mm"
    )

    # Crear marcas horizontales (calles H): 2 cajas por calle (izquierda x=0, derecha x=ancho_total)
    # NOTA: Las cajas H (izq/der) usan calles_v (segunda parte de calles_list)
    for i, y_mm in enumerate(h_offsets_mm):
        calle_size_mm = (
            calles_list[len(v_offsets_mm) + i]
            if (len(v_offsets_mm) + i) < len(calles_list)
            else 10.0
        )

        if _PRINT_DEBUG:
            print(f"[DBG] Calle H{i+1}: y={y_mm}mm, calle_size={calle_size_mm}mm")

        if calle_size_mm == 0:
            # Usar función simple para 1 línea
            marca_simple = crear_marca_linea_simple(longitud_cruz_mm, label=f"H{i+1}")
            if _PRINT_DEBUG:
                print(f"[DBG]   -> CALLE=0: 1 línea simple de {marca_simple['ancho_mm']}mm")

            # y_relativo_mm = 0 para la única línea
            y_relativo_mm = 0.0

            # Caja IZQUIERDA (IGUAL que 3 líneas)
            line_left = ft.Container(
                width=longitud_cruz_mm * escala_visual,
                height=stroke_px,
                bgcolor=ft.Colors.BLACK,
                left=0,
                top=(y_mm + y_relativo_mm - (stroke_mm / 2.0)) * escala_visual,
            )
            marks_controls.append(line_left)

            # Caja DERECHA (usar longitud_cruz_mm, no calle_size_mm que es 0)
            line_right = ft.Container(
                width=longitud_cruz_mm * escala_visual,
                height=stroke_px,
                bgcolor=ft.Colors.BLACK,
                left=(ancho_total_mm - longitud_cruz_mm) * escala_visual,
                top=(y_mm + y_relativo_mm - (stroke_mm / 2.0)) * escala_visual,
            )
            marks_controls.append(line_right)

        else:
            # Usar función de 3 marcas
            if _PRINT_DEBUG:
                print(f"[DBG]   -> Caja IZQUIERDA en (x=0, y={y_mm}mm)")
                print(
                    f"[DBG]   -> Caja DERECHA en (x={ancho_total_mm - longitud_cruz_mm:.1f}mm, y={y_mm}mm)"
                )
            # TODO: crear cajas de 3 lineas
            # Crear caja izquierda (normal)
            caja_h_izq = crear_caja_marcas(
                calle_size_mm, longitud_cruz_mm, label=f"H{i+1}L", invertir=False
            )

            # Crear caja derecha (invertida para que se alinee desde el borde)
            caja_h_der = crear_caja_marcas(
                calle_size_mm, longitud_cruz_mm, label=f"H{i+1}R", invertir=True
            )

            # Caja IZQUIERDA
            for marca_spec in caja_h_izq.get("marks", []):
                y_relativo_mm = marca_spec.get("y", 0.0)
                line_left = ft.Container(
                    width=longitud_cruz_mm * escala_visual,
                    height=stroke_px,
                    bgcolor=ft.Colors.BLACK,
                    left=0,
                    top=(y_mm + y_relativo_mm) * escala_visual,
                )
                marks_controls.append(line_left)

            # Caja DERECHA (con marcas invertidas)
            for marca_spec in caja_h_der.get("marks", []):
                y_relativo_mm = marca_spec.get("y", 0.0)
                line_right = ft.Container(
                    width=longitud_cruz_mm * escala_visual,
                    height=stroke_px,
                    bgcolor=ft.Colors.BLACK,
                    left=(ancho_total_mm - longitud_cruz_mm) * escala_visual,
                    top=(y_mm + y_relativo_mm) * escala_visual,
                )
                marks_controls.append(line_right)

    # Crear marcas verticales (calles V): 2 cajas por calle (arriba y=0, abajo y=alto_total)
    # NOTA: Las cajas V (arriba/abajo) usan calles_h (primera parte de calles_list)
    for i, x_mm in enumerate(v_offsets_mm):
        calle_size_mm = calles_list[i] if i < len(calles_list) else 10.0

        # print(f"[DBG] Calle V{i+1}: x={x_mm}mm, calle_size={calle_size_mm}mm")

        if calle_size_mm == 0:
            # Usar función simple para 1 línea
            marca_simple = crear_marca_linea_simple(longitud_cruz_mm, label=f"V{i+1}")
            if _PRINT_DEBUG:
                print(f"[DBG]   -> CALLE=0: 1 línea simple de {marca_simple['ancho_mm']}mm")

            # x_relativo_mm = 0 para la única línea
            x_relativo_mm = 0.0

            # Caja ARRIBA (IGUAL que 3 líneas)
            line_top = ft.Container(
                width=stroke_px,
                height=longitud_cruz_mm * escala_visual,
                bgcolor=ft.Colors.BLACK,
                left=(x_mm + x_relativo_mm - (stroke_mm / 2.0)) * escala_visual,
                top=0,
            )
            marks_controls.append(line_top)

            # Caja ABAJO (usar longitud_cruz_mm, no calle_size_mm que es 0)
            line_bottom = ft.Container(
                width=stroke_px,
                height=longitud_cruz_mm * escala_visual,
                bgcolor=ft.Colors.BLACK,
                left=(x_mm + x_relativo_mm - (stroke_mm / 2.0)) * escala_visual,
                top=(alto_total_mm - longitud_cruz_mm) * escala_visual,
            )
            marks_controls.append(line_bottom)

        else:
            # Usar función de 3 marcas
            if _PRINT_DEBUG:
                print(f"[DBG]   -> Caja ARRIBA en (x={x_mm}mm, y=0)")
                print(
                    f"[DBG]   -> Caja ABAJO en (x={x_mm}mm, y={alto_total_mm - longitud_cruz_mm:.1f}mm)"
                )

            # Crear caja arriba (normal)
            caja_v_arr = crear_caja_marcas(
                calle_size_mm, longitud_cruz_mm, label=f"V{i+1}T", invertir=False
            )

            # Crear caja abajo (invertida para que se alinee desde el borde)
            caja_v_aba = crear_caja_marcas(
                calle_size_mm, longitud_cruz_mm, label=f"V{i+1}B", invertir=True
            )

            # Caja ARRIBA
            for marca_spec in caja_v_arr.get("marks", []):
                x_relativo_mm = marca_spec.get("y", 0.0)
                line_top = ft.Container(
                    width=stroke_px,
                    height=longitud_cruz_mm * escala_visual,
                    bgcolor=ft.Colors.BLACK,
                    left=(x_mm + x_relativo_mm) * escala_visual,
                    top=0,
                )
                marks_controls.append(line_top)

            # Caja ABAJO (con marcas invertidas)
            for marca_spec in caja_v_aba.get("marks", []):
                x_relativo_mm = marca_spec.get("y", 0.0)
                line_bottom = ft.Container(
                    width=stroke_px,
                    height=longitud_cruz_mm * escala_visual,
                    bgcolor=ft.Colors.BLACK,
                    left=(x_mm + x_relativo_mm) * escala_visual,
                    top=(alto_total_mm - longitud_cruz_mm) * escala_visual,
                )
                marks_controls.append(line_bottom)

    # Crear Stack y Container final
    stack_marcas = ft.Stack(
        marks_controls,
        width=ancho_corte_px + extension_fuera_px * 2,
        height=alto_corte_px + extension_fuera_px * 2,
        visible=True,
    )

    container_marcas = ft.Container(
        content=stack_marcas,
        width=ancho_corte_px + extension_fuera_px * 2,
        height=alto_corte_px + extension_fuera_px * 2,
        bgcolor=ft.Colors.TRANSPARENT,
        visible=True,
    )

    # Guardar info en dim_celds para crear el PDF
    ancho_total_mm = ancho_corte_px / escala_visual
    alto_total_mm = alto_corte_px / escala_visual

    # ✅ CALCULAR POSICIONES ABSOLUTAS DE CADA LÍNEA INDIVIDUAL
    # Para Fritz necesitamos las posiciones exactas de cada línea, no solo los offsets de las cajas
    # Cada marca tiene 2 líneas (izq/der o arr/aba) que se dibujan por separado
    lineas_marcas = []  # Lista de todas las líneas con su posición, tamaño y grosor

    grosor_mm = GROSOR_CRUZ_PT * PT_TO_MM  # Mismo grosor que las cruces

    # Reconstruir las posiciones exactas de las líneas horizontales
    for i, y_mm in enumerate(h_offsets_mm):
        calle_size_mm = (
            calles_list[len(v_offsets_mm) + i]
            if (len(v_offsets_mm) + i) < len(calles_list)
            else 10.0
        )

        if calle_size_mm == 0:
            # 1 línea simple - 2 instancias (izquierda y derecha)
            # Línea IZQUIERDA
            lineas_marcas.append(
                {
                    "tipo": "horizontal",
                    "lado": "izquierda",
                    "x_mm": 0.0,
                    "y_mm": y_mm - (grosor_mm / 2.0),
                    "width_mm": longitud_cruz_mm,
                    "height_mm": grosor_mm,
                    "calle_idx": i,
                }
            )
            # Línea DERECHA
            lineas_marcas.append(
                {
                    "tipo": "horizontal",
                    "lado": "derecha",
                    "x_mm": ancho_total_mm - longitud_cruz_mm,
                    "y_mm": y_mm - (grosor_mm / 2.0),
                    "width_mm": longitud_cruz_mm,
                    "height_mm": grosor_mm,
                    "calle_idx": i,
                }
            )
        else:
            # 3 líneas distribuidas - cada una tiene 2 instancias (izquierda y derecha)
            caja_h = crear_caja_marcas(calle_size_mm, longitud_cruz_mm, invertir=False)
            for marca_spec in caja_h.get("marks", []):
                y_relativo_mm = marca_spec.get("y", 0.0)
                # Línea IZQUIERDA
                lineas_marcas.append(
                    {
                        "tipo": "horizontal",
                        "lado": "izquierda",
                        "x_mm": 0.0,
                        "y_mm": y_mm + y_relativo_mm,
                        "width_mm": longitud_cruz_mm,
                        "height_mm": grosor_mm,
                        "calle_idx": i,
                    }
                )
                # Línea DERECHA
                lineas_marcas.append(
                    {
                        "tipo": "horizontal",
                        "lado": "derecha",
                        "x_mm": ancho_total_mm - longitud_cruz_mm,
                        "y_mm": y_mm + y_relativo_mm,
                        "width_mm": longitud_cruz_mm,
                        "height_mm": grosor_mm,
                        "calle_idx": i,
                    }
                )

    # Reconstruir las posiciones exactas de las líneas verticales
    for i, x_mm in enumerate(v_offsets_mm):
        calle_size_mm = calles_list[i] if i < len(calles_list) else 10.0

        if calle_size_mm == 0:
            # 1 línea simple - 2 instancias (arriba y abajo)
            # Línea ARRIBA
            lineas_marcas.append(
                {
                    "tipo": "vertical",
                    "lado": "arriba",
                    "x_mm": x_mm - (grosor_mm / 2.0),
                    "y_mm": 0.0,
                    "width_mm": grosor_mm,
                    "height_mm": longitud_cruz_mm,
                    "calle_idx": i,
                }
            )
            # Línea ABAJO
            lineas_marcas.append(
                {
                    "tipo": "vertical",
                    "lado": "abajo",
                    "x_mm": x_mm - (grosor_mm / 2.0),
                    "y_mm": alto_total_mm - longitud_cruz_mm,
                    "width_mm": grosor_mm,
                    "height_mm": longitud_cruz_mm,
                    "calle_idx": i,
                }
            )
        else:
            # 3 líneas distribuidas - cada una tiene 2 instancias (arriba y abajo)
            caja_v = crear_caja_marcas(calle_size_mm, longitud_cruz_mm, invertir=False)
            for marca_spec in caja_v.get("marks", []):
                x_relativo_mm = marca_spec.get(
                    "y", 0.0
                )  # Nota: 'y' porque la caja se rota
                # Línea ARRIBA
                lineas_marcas.append(
                    {
                        "tipo": "vertical",
                        "lado": "arriba",
                        "x_mm": x_mm + x_relativo_mm,
                        "y_mm": 0.0,
                        "width_mm": grosor_mm,
                        "height_mm": longitud_cruz_mm,
                        "calle_idx": i,
                    }
                )
                # Línea ABAJO
                lineas_marcas.append(
                    {
                        "tipo": "vertical",
                        "lado": "abajo",
                        "x_mm": x_mm + x_relativo_mm,
                        "y_mm": alto_total_mm - longitud_cruz_mm,
                        "width_mm": grosor_mm,
                        "height_mm": longitud_cruz_mm,
                        "calle_idx": i,
                    }
                )

    dim_celds["marcas_corte"] = {
        "lineas_marcas": lineas_marcas,  # ✅ Lista completa de líneas individuales
        "ancho_total_mm": ancho_total_mm,
        "alto_total_mm": alto_total_mm,
        "longitud_marca_mm": longitud_cruz_mm,
        "grosor_marca_mm": grosor_mm,
        "grosor_marca_pt": GROSOR_CRUZ_PT,
        "escala_visual": escala_visual,
        "num_lineas": len(lineas_marcas),
    }
    print("\n✅ DATOS DE MARCAS GUARDADOS EN dim_celds['marcas_corte'] para PDF")
    print(f"   • {len(lineas_marcas)} líneas individuales calculadas")

    print(f"✅ [MARCAS DE CORTE] CAPA completada con {len(marks_controls)} marcas")
    print(f"{'='*80}\n")

    return (
        container_marcas,
        extension_fuera_px,
        {
            "h_offsets_mm": h_offsets_mm,
            "v_offsets_mm": v_offsets_mm,
            "calles_h": calles_h,
            "calles_v": calles_v,
        },
    )


def crear_capa_cruces(
    sangre,
    dim_celds,
    longitud_cruz_config,
    grosor_cruz,
    offset_cruz,
    escala_visual,
):
    """
    Crea la capa de cruces cantoneras (ángulos en L de esquina).

    Solo genera las 4 cruces de esquina. Las marcas de corte exteriores
    se crean de forma separada con crear_capa_marcas_corte_exteriores().

    Returns:
        Tupla (ft.Container con cruces, margen_exterior)
    """
    print(f"\n{'='*80}")
    print(f"✂️  CREANDO CAPA DE CRUCES CANTONERAS")
    print(f"{'='*80}")

    longitud_cruz_mm = longitud_cruz_config

    elementos = []

    # Obtener tamaño total del pliego desde DATOS_CELDAS
    ancho_pliego_mm = dim_celds.get("tamano_total_w", 636)
    alto_pliego_mm = dim_celds.get("tamano_total_h", 306)

    # ✅ Obtener sangre del ARGUMENTO sangre (que viene de la UI)
    # dim_celds["sangre_mm"] puede no estar seteado aun.
    try:
        sangre_mm = float(sangre)
    except (ValueError, TypeError):
        sangre_mm = 0.0

    ancho_pliego_px = ancho_pliego_mm * escala_visual
    alto_pliego_px = alto_pliego_mm * escala_visual

    print(f"📦 Tamaño del pliego obtenido de DATOS_CELDAS:")
    print(f"   {ancho_pliego_mm:.2f}mm × {alto_pliego_mm:.2f}mm")
    print(f"   Sangre: {sangre_mm}mm")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CÁLCULO DE POSICIONES
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    # ✅ CORRECCIÓN FINAL (Step 396): Las cruces deben alinearse al CORTE (TrimBox), no al Pliego (BleedBox).
    # Restamos la sangre al tamaño del pliego para obtener el tamaño de corte real.
    ancho_corte_mm = ancho_pliego_mm - (2 * sangre_mm)
    alto_corte_mm = alto_pliego_mm - (2 * sangre_mm)

    print(f"   Tamaño CORTE (TrimBox): {ancho_corte_mm:.2f}mm × {alto_corte_mm:.2f}mm")

    # Las esquinas ahora son las del TrimBox (relativas a 0,0)
    esquinas_mm = [
        (0, 0),  # TOP-LEFT
        (ancho_corte_mm, 0),  # TOP-RIGHT
        (0, alto_corte_mm),  # BOTTOM-LEFT
        (ancho_corte_mm, alto_corte_mm),  # BOTTOM-RIGHT
    ]

    # ✅ Extensión estándar: Línea + Offset
    extension_base_mm = longitud_cruz_mm
    extension_total_mm = extension_base_mm + offset_cruz

    extension_fuera_mm = extension_total_mm
    extension_fuera_px = extension_fuera_mm * escala_visual

    print(f"\n✚ Creando 4 cruces cantoneras en esquinas del CORTE...")
    print(f"   Líneas de cruz: {extension_base_mm:.2f}mm")
    print(f"   Offset usuario: {offset_cruz:.2f}mm")
    print(f"   Total (líneas + offset): {extension_total_mm:.2f}mm")

    esquinas_tipos = [
        (esquinas_mm[0], "tl"),  # TOP-LEFT
        (esquinas_mm[1], "tr"),  # TOP-RIGHT
        (esquinas_mm[2], "bl"),  # BOTTOM-LEFT
        (esquinas_mm[3], "br"),  # BOTTOM-RIGHT
    ]

    # ... (omitir prints intermedios si no cambiaron) ...

    # EN EL BUCLE FOR POSTERIOR (que no se ve aquí pero se asume abajo):
    # Asegurar que punto_x_mm use la fórmula estándar

    extension_fuera_px = extension_fuera_mm * escala_visual

    esquinas_tipos = [
        (esquinas_mm[0], "tl"),  # TOP-LEFT
        (esquinas_mm[1], "tr"),  # TOP-RIGHT
        (esquinas_mm[2], "bl"),  # BOTTOM-LEFT
        (esquinas_mm[3], "br"),  # BOTTOM-RIGHT
    ]

    print(f"\n   📐 DEBUG POSICIONES DE CRUCES:")
    # ===== Ajustar grosor de cruces y borde azul para que coincidan con la
    # línea exterior negra del stack (mismo grosor en px, sin escalar)
    # exterior_grosor_px = mm_a_px(GROSOR_LINEA_EXTERIOR_MM, escala=escala_visual)

    # Calcular grosor en puntos equivalente para pasar a crear_cruz_esquina()
    # fórmula inversa de crear_cruz_esquina: grosor_px = grosor_pt / 72 * 96 * escala_visual
    # por tanto: grosor_pt = grosor_px / (96/72 * escala_visual)
    # # factor_pt_to_px = (
    # #     (96.0 / 72.0) * escala_visual if escala_visual != 0 else (96.0 / 72.0)
    # # )
    # grosor_cruz_pt_final = (
    #     exterior_grosor_px / factor_pt_to_px if factor_pt_to_px != 0 else 0.5
    # )

    # grosor_cruz = grosor_cruz * 0.3528
    # grosor_cruz = grosor_cruz * escala_visual
    for (x_mm, y_mm), esquina_tipo in esquinas_tipos:
        # ✅ CENTRAR las cruces dentro del margen
        # x_mm es coordenada de Corte. extension_fuera_mm es margen externo desde Corte.
        # En el container, (0,0) de Corte está en (ext, ext).
        x_px = (x_mm + extension_fuera_mm) * escala_visual
        y_px = (y_mm + extension_fuera_mm) * escala_visual

        if _PRINT_DEBUG:
            print(
                f"      Esquina {esquina_tipo}: ({x_mm:.2f}mm, {y_mm:.2f}mm) + margen({extension_fuera_mm:.2f}mm) → ({x_px:.1f}px, {y_px:.1f}px)"
            )

        elementos.extend(
            crear_cruz_esquina(
                x_px,
                y_px,
                longitud_cruz_config,
                grosor_cruz,
                offset_cruz,
                escala_visual,
                esquina_tipo,
            )
        )

    print(f"   ✅ 4 cruces cantoneras creadas")
    print(f"   ✅ Total elementos cruces: {len(elementos)} elementos\n")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # CÁLCULO DEL TAMAÑO FINAL
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("=" * 80)
    print("📐 CAPA DE CRUCES - DIMENSIONES FINALES")
    print(f"   Tamaño de Corte: {ancho_corte_mm:.2f}mm × {alto_corte_mm:.2f}mm")
    print(
        f"   Extensión de cruces: {extension_fuera_mm:.2f}mm (línea {longitud_cruz_mm:.2f}mm + offset {offset_cruz:.2f}mm)"
    )

    # ✅ NUEVO: Tamaño de cruces calculado sobre el TAMAÑO DE CORTE
    cruces_solo_w_mm = ancho_corte_mm + 2 * extension_fuera_mm
    cruces_solo_h_mm = alto_corte_mm + 2 * extension_fuera_mm

    # ✅ NUEVO: Tamaño del trazado (sin modificar, es el pliego con sangre)
    trazado_w_mm = ancho_pliego_mm
    trazado_h_mm = alto_pliego_mm

    # ✅ NUEVO: El tamaño final del GRUPO
    tamano_final_w_mm = cruces_solo_w_mm
    tamano_final_h_mm = cruces_solo_h_mm

    # ✅ CÁLCULO DE OFFSETS DE TRAZADO
    # Trazado (Pliego) debe centrarse en el Grupo (Corte + 2Ext).
    # Diferencia = (Grupo - Trazado) / 2
    # Diferencia = ((Corte + 2Ext) - (Corte + 2Sangre)) / 2 = Ext - Sangre
    offset_trazado_x_mm = extension_fuera_mm - sangre_mm
    offset_trazado_y_mm = extension_fuera_mm - sangre_mm

    # Las cruces ocupan todo el espacio, su offset es 0
    offset_cruces_x_mm = 0.0
    offset_cruces_y_mm = 0.0

    print(f"\n   📊 DIMENSIONES:")
    print(
        f"      Grupo (Cruces): {tamano_final_w_mm:.2f}mm × {tamano_final_h_mm:.2f}mm"
    )
    print(f"      Trazado:        {trazado_w_mm:.2f}mm × {trazado_h_mm:.2f}mm")
    print(f"      Extensión:      {extension_fuera_mm:.2f}mm")

    print(f"\n   ✅ Offsets finales:")
    print(f"      Trazado: ({offset_trazado_x_mm:.2f}mm, {offset_trazado_y_mm:.2f}mm)")
    print(f"      Cruces:  ({offset_cruces_x_mm:.2f}mm, {offset_cruces_y_mm:.2f}mm)")
    print("=" * 80 + "\n")

    margen_exterior = extension_fuera_mm * escala_visual

    # ✅ CALCULAR POSICIONES EXACTAS DE LAS 8 LÍNEAS (4 cruces × 2 brazos)
    # Para Fritz necesitamos la posición, longitud y orientación de cada línea
    # IMPORTANTE: Las coordenadas son relativas al área de corte (sin margen)
    lineas_cruces = []
    grosor_mm = grosor_cruz * 0.3528  # pt a mm

    for (x_mm, y_mm), esquina_tipo in esquinas_tipos:
        # Posición del punto de corte (esquina del área de corte)
        # x_mm, y_mm son coordenadas del área de corte (0,0), (636,0), etc.
        punto_x_mm = x_mm + longitud_cruz_mm + offset_cruz
        punto_y_mm = y_mm + longitud_cruz_mm + offset_cruz

        longitud_cruz_mm_val = longitud_cruz_mm

        if esquina_tipo == "tl":  # Superior izquierda
            # Brazo vertical (arriba) - hacia borde superior
            lineas_cruces.append(
                {
                    "tipo": "vertical",
                    "esquina": "tl",
                    "x_mm": punto_x_mm - grosor_mm / 2,
                    "y_mm": punto_y_mm
                    - longitud_cruz_mm_val
                    - offset_cruz,  # ✅ Desplazar hacia arriba (arranca en gap, termina en 0)
                    "width_mm": grosor_mm,
                    "height_mm": longitud_cruz_mm_val,
                }
            )
            # Brazo horizontal (izquierda) - hacia borde izquierdo
            lineas_cruces.append(
                {
                    "tipo": "horizontal",
                    "esquina": "tl",
                    "x_mm": punto_x_mm
                    - longitud_cruz_mm_val
                    - offset_cruz,  # ✅ Desplazar hacia izquierda
                    "y_mm": punto_y_mm - grosor_mm / 2,
                    "width_mm": longitud_cruz_mm_val,
                    "height_mm": grosor_mm,
                }
            )

        elif esquina_tipo == "tr":  # Superior derecha
            # Brazo vertical (arriba)
            lineas_cruces.append(
                {
                    "tipo": "vertical",
                    "esquina": "tr",
                    "x_mm": punto_x_mm - grosor_mm / 2,
                    "y_mm": punto_y_mm
                    - longitud_cruz_mm_val
                    - offset_cruz,  # ✅ Desplazar hacia arriba
                    "width_mm": grosor_mm,
                    "height_mm": longitud_cruz_mm_val,
                }
            )
            # Brazo horizontal (derecha)
            lineas_cruces.append(
                {
                    "tipo": "horizontal",
                    "esquina": "tr",
                    "x_mm": punto_x_mm
                    + offset_cruz,  # ✅ Desplazar hacia derecha (+ offset)
                    "y_mm": punto_y_mm - grosor_mm / 2,
                    "width_mm": longitud_cruz_mm_val,
                    "height_mm": grosor_mm,
                }
            )

        elif esquina_tipo == "bl":  # Inferior izquierda
            # Brazo vertical (abajo)
            lineas_cruces.append(
                {
                    "tipo": "vertical",
                    "esquina": "bl",
                    "x_mm": punto_x_mm - grosor_mm / 2,
                    "y_mm": punto_y_mm
                    + offset_cruz,  # ✅ Desplazar hacia abajo (+ offset)
                    "width_mm": grosor_mm,
                    "height_mm": longitud_cruz_mm_val,
                }
            )
            # Brazo horizontal (izquierda)
            lineas_cruces.append(
                {
                    "tipo": "horizontal",
                    "esquina": "bl",
                    "x_mm": punto_x_mm
                    - longitud_cruz_mm_val
                    - offset_cruz,  # ✅ Desplazar hacia izquierda
                    "y_mm": punto_y_mm - grosor_mm / 2,
                    "width_mm": longitud_cruz_mm_val,
                    "height_mm": grosor_mm,
                }
            )

        elif esquina_tipo == "br":  # Inferior derecha
            # Brazo vertical (abajo)
            lineas_cruces.append(
                {
                    "tipo": "vertical",
                    "esquina": "br",
                    "x_mm": punto_x_mm - grosor_mm / 2,
                    "y_mm": punto_y_mm + offset_cruz,  # ✅ Desplazar hacia abajo
                    "width_mm": grosor_mm,
                    "height_mm": longitud_cruz_mm_val,
                }
            )
            # Brazo horizontal (derecha)
            lineas_cruces.append(
                {
                    "tipo": "horizontal",
                    "esquina": "br",
                    "x_mm": punto_x_mm + offset_cruz,  # ✅ Desplazar hacia derecha
                    "y_mm": punto_y_mm - grosor_mm / 2,
                    "width_mm": longitud_cruz_mm_val,
                    "height_mm": grosor_mm,
                }
            )

    dim_celds["cruces_corte"] = {
        "tamano_final_w_mm": tamano_final_w_mm,
        "tamano_final_h_mm": tamano_final_h_mm,
        "cruces_solo_w_mm": cruces_solo_w_mm,
        "cruces_solo_h_mm": cruces_solo_h_mm,
        "trazado_w_mm": trazado_w_mm,
        "trazado_h_mm": trazado_h_mm,
        # ✅ OFFSETS RESTAURADOS: Necesarios para posicionar capas en el Stack
        "offset_trazado_x_mm": offset_trazado_x_mm,
        "offset_trazado_y_mm": offset_trazado_y_mm,
        "margen_exterior_mm": extension_fuera_mm,
        "extension_fuera_mm": extension_fuera_mm,
        "longitud_cruz_mm": longitud_cruz_mm,
        "offset_cruz_mm": offset_cruz,
        "grosor_cruz_pt": grosor_cruz,
        "grosor_cruz_mm": grosor_mm,  # ✅ NUEVO: Grosor en mm para Fritz
        "sangre_mm": sangre_mm,
        "escala_visual": escala_visual,
        "esquinas_mm": esquinas_mm,
        "lineas_cruces": lineas_cruces,  # ✅ NUEVO: Posiciones exactas de las 8 líneas
        "num_lineas": len(lineas_cruces),
    }
    print("\n✅ DATOS DE CRUCES GUARDADOS EN DATOS_CELDAS['cruces_corte'] para PDF")
    print(f"   • {len(lineas_cruces)} líneas individuales calculadas")

    ancho_corte_px = ancho_corte_mm * escala_visual
    alto_corte_px = alto_corte_mm * escala_visual

    print(f"\n🔍 DEBUG crear_capa_cruces - RETORNANDO:")
    print(f"   • Número de cruces: {len(elementos)}")
    print(
        f"   • Tamaño del Stack: {ancho_corte_px + margen_exterior * 2:.1f}px × {alto_corte_px + margen_exterior * 2:.1f}px"
    )
    print(
        f"   • Margen exterior: {extension_fuera_mm:.2f}mm ({margen_exterior:.1f}px)\n"
    )

    # ✅ TODO Stack solo con cruces (SIN líneas externas)
    stack_cruces = ft.Stack(
        elementos,
        width=ancho_corte_px + margen_exterior * 2,
        height=alto_corte_px + margen_exterior * 2,
        visible=True,
    )

    # TODO container cruces
    container_cruces = ft.Container(
        content=stack_cruces,
        width=ancho_corte_px + margen_exterior * 2,
        height=alto_corte_px + margen_exterior * 2,
        bgcolor=ft.Colors.TRANSPARENT,
        visible=True,
        # borde removido (antes había un borde transparente que podía añadir grosor)
    )

    print(f"✅ [CRUCES] CAPA CRUCES CANTONERAS completada con:")
    print(f"   • Cruces de esquina: {len(elementos)} cruces")
    print(f"   • Tamaño: {container_cruces.width}px × {container_cruces.height}px")

    return (
        container_cruces,
        margen_exterior,
    )


def crear_trazado_con_rows_from_widgets(
    celdas_matriz: List[List],
    calles_h: List[float],
    calles_v: List[float],
    escala: float = 1.0,
    datos_celdas: Optional[Dict] = None,
) -> Tuple[ft.Column, Dict]:
    """
    Versión de crear_trazado_con_rows() que acepta widgets YA CREADOS (matriz 2D de Containers).

    Útil cuando los widgets ya tienen imágenes, bordes, etc.

    ✨ NUEVA VERSIÓN: Calcula espaciadores usando sangre de celdas para NO duplicar calles.

    Estructura:
    - Column (contenedor principal)
      ├─ Row (fila 0)
      │  ├─ Container (celda 0,0) [WIDGET REAL]
      │  ├─ Container (sep V calculado) ← TAMAÑO CORRECTO
      │  └─ ...
      ├─ Container (sep H calculado) ← TAMAÑO CORRECTO
      └─ Row (fila 1)
         ├─ ...

    Args:
        celdas_matriz: Lista[Lista[ft.Widget]] - matriz de widgets (rows x cols)
        calles_h: Lista de alturas de calles horizontales (ROWS-1 elementos)
        calles_v: Lista de anchos de calles verticales (COLS-1 elementos)
        escala: Factor de escala visual (para convertir mm a px)
        datos_celdas: Dict con info de sangres por celda (formato "row_col: R,C": {...})

    Returns:
        Tupla (Column_trazado, info_debug) donde:
        - Column_trazado: El trazado completo listo para insertar en viewer
        - info_debug: Dict con información de construcción
    """

    if not celdas_matriz or not celdas_matriz[0]:
        print("⚠️  [TRAZADO] Matriz de celdas vacía")
        return ft.Column([]), {}

    grid_rows = len(celdas_matriz)
    grid_cols = len(celdas_matriz[0])

    print(f"\n🔍 [DEBUG] crear_trazado_con_rows_from_widgets LLAMADA")
    print(
        f"🔍 [DEBUG] grid: {grid_cols}×{grid_rows}, calles_v={calles_v}, calles_h={calles_h}"
    )
    print(f"🔍 [DEBUG] datos_celdas is None: {datos_celdas is None}")
    if datos_celdas:
        print(
            f"🔍 [DEBUG] datos_celdas keys: {list(datos_celdas.keys())[:10]}..."
        )  # Primeras 10 keys
    print(f"🔍 [DEBUG] Llamando a calcular_espaciadores_visuales...\n")

    # Calcular espaciadores correctos considerando sangre
    # ✅ CORREGIDO: YA NO invertir porque ahora calles_v y calles_h llegan correctamente:
    #    - calles_v = calles verticales (entre columnas) - afectan ancho
    #    - calles_h = calles horizontales (entre filas) - afectan alto
    espaciadores = calcular_espaciadores_visuales(
        datos_celdas=datos_celdas,
        grid_cols=grid_cols,
        grid_rows=grid_rows,
        calles_v=calles_v,  # ✅ Pasar calles_v directamente (entre columnas)
        calles_h=calles_h,  # ✅ Pasar calles_h directamente (entre filas)
        escala=escala,
    )

    filas_elementos = []  # Elementos del Column: Row, Sep H, Row, Sep H, ...
    info_construccion = {
        "num_filas_creadas": 0,
        "num_separadores_h": 0,
        "num_celdas_usadas": 0,
        "tamaño_total_w_mm": 0,
        "tamaño_total_h_mm": 0,
    }

    # ✅ IMPORTANTE: Si se pasa datos_celdas con tamaño precomputado, usarlo
    # (es más preciso que calcular desde los widgets)
    if (
        datos_celdas
        and isinstance(datos_celdas, dict)
        and "tamano_total_w" in datos_celdas
        and "tamano_total_h" in datos_celdas
    ):
        info_construccion["tamaño_total_w_mm"] = datos_celdas["tamano_total_w"]
        info_construccion["tamaño_total_h_mm"] = datos_celdas["tamano_total_h"]
        print(
            "[✅ USAR TAMAÑO PRECOMPUTADO] tamaño_total=%.1f×%.1fmm (desde datos_celdas)",
            info_construccion["tamaño_total_w_mm"],
            info_construccion["tamaño_total_h_mm"],
        )

    # ─────────────────────────────────────────────────────────────────────────
    # CONSTRUCCIÓN DEL TRAZADO DESDE WIDGETS REALES
    # ─────────────────────────────────────────────────────────────────────────

    print("\n" + ("=" * 100))
    print("🔳 CONSTRUCCIÓN DEL TRAZADO - ENSAMBLAJE DE CELDAS Y SEPARADORES")
    print("=" * 100)

    for row in range(grid_rows):
        # ───────────────────────────────────────────────────────────────────
        # PASO 1: Crear Row con celdas (ya creadas) y separadores verticales
        # ───────────────────────────────────────────────────────────────────

        celdas_row = []  # Elementos del Row: Container, Sep V, Container, ...
        ancho_total_row_px = 0
        alto_fila_px = 0

        for col in range(grid_cols):
            # Obtener el widget real
            if row >= len(celdas_matriz) or col >= len(celdas_matriz[row]):
                if _PRINT_DEBUG:
                    print("⚠️  [TRAZADO] Widget no encontrado: [%s,%s]", row, col)
                continue

            widget_celda = celdas_matriz[row][col]
            info_construccion["num_celdas_usadas"] += 1

            # El widget ya tiene ancho/alto definido
            celda_w_px = (
                widget_celda.width
                if hasattr(widget_celda, "width") and widget_celda.width
                else 100
            )
            celda_h_px = (
                widget_celda.height
                if hasattr(widget_celda, "height") and widget_celda.height
                else 100
            )

            alto_fila_px = (
                celda_h_px  # Todas las celdas de la fila tienen el mismo alto
            )

            celdas_row.append(widget_celda)
            ancho_total_row_px += celda_w_px
            if _PRINT_DEBUG:
                print(f"    [Celda {row},{col}] w={celda_w_px:.1f}px h={celda_h_px:.1f}px")

            # SEPARADOR VERTICAL (si no es la última columna)
            if col < grid_cols - 1:
                # Usar espaciador precalculado
                sep_v_width_px = espaciadores["espaciadores_v"].get((row, col), 0)

                sep_v = ft.Container(
                    width=sep_v_width_px,
                    height=celda_h_px,
                    # TODO: bgcolor=ft.Colors.GREY_100,  # ← DESACTIVADO para ver trazado
                )
                celdas_row.append(sep_v)
                ancho_total_row_px += sep_v_width_px
                if _PRINT_DEBUG:
                    print(
                        f"      ➜ [Sep V {row},{col}→{col+1}] w={sep_v_width_px:.1f}px h={celda_h_px:.1f}px"
                    )

        # Crear el Row con spacing=0 (sin espacios entre elementos)
        # ✅ IMPORTANTE: Fijar el ancho del Row al tamaño total correcto para evitar distorsión
        # Si no fijamos el ancho, Flet intenta ajustar el contenido dinámicamente
        row_width_px = (
            info_construccion["tamaño_total_w_mm"] * escala
            if info_construccion["tamaño_total_w_mm"] > 0
            else ancho_total_row_px
        )

        row_element = ft.Row(
            celdas_row,
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.START,
            width=row_width_px,  # ✅ Ancho fijo para alinear con separadores H
        )
        filas_elementos.append(row_element)
        info_construccion["num_filas_creadas"] += 1
        # ⚠️  IMPORTANTE: NO usar max() - el ancho debe ser CONSTANTE y ser el mismo en todas las filas
        # (todas las filas de un grid deben tener el mismo ancho)
        # Si es la primera fila, establece el ancho; si no, verifica que sea consistente
        if info_construccion["tamaño_total_w_mm"] == 0:
            # Primera fila: establecer el ancho
            info_construccion["tamaño_total_w_mm"] = (
                ancho_total_row_px / escala if escala > 0 else ancho_total_row_px
            )
        else:
            # Verificar consistencia pero usar siempre el valor establecido
            ancho_actual = (
                ancho_total_row_px / escala if escala > 0 else ancho_total_row_px
            )
            if abs(ancho_actual - info_construccion["tamaño_total_w_mm"]) > 0.1:
                if _PRINT_DEBUG:
                    print(
                        f"⚠️  [TRAZADO] Inconsistencia de ancho en fila {row}: {ancho_actual:.1f}mm vs {info_construccion['tamaño_total_w_mm']:.1f}mm"
                    )

        # ───────────────────────────────────────────────────────────────────
        # PASO 2: Crear separador horizontal (si no es la última fila)
        # ───────────────────────────────────────────────────────────────────

        if row < grid_rows - 1:
            # Usar espaciador precalculado para la primera columna (altura)
            sep_h_height_px = espaciadores["espaciadores_h"].get((row, 0), 0)

            # ✅ IMPORTANTE: El ancho del separador H debe ser el TAMAÑO TOTAL CORRECTO (670px)
            # NO el ancho de la fila individual (665px que es solo celdas + separadores V)
            # Esto evita que Flet distorsione el layout para llenar espacios
            if info_construccion["tamaño_total_w_mm"] > 0:
                sep_h_width_px = info_construccion["tamaño_total_w_mm"] * escala
            else:
                sep_h_width_px = (
                    ancho_total_row_px  # Fallback si no hay tamaño precomputado
                )

            sep_h = ft.Container(
                width=sep_h_width_px,
                height=sep_h_height_px,
                # TODO: bgcolor=ft.Colors.GREY_100,  # ← DESACTIVADO para ver trazado
            )
            filas_elementos.append(sep_h)
            info_construccion["num_separadores_h"] += 1
            if _PRINT_DEBUG:
                print(
                    f"    [Sep H {row}→{row+1}] w={sep_h_width_px:.1f}px h={sep_h_height_px:.1f}px"
                )

        # Acumular altura (solo si no fue establecida desde datos_celdas)
        if info_construccion["tamaño_total_h_mm"] == 0 or not (
            datos_celdas
            and isinstance(datos_celdas, dict)
            and "tamano_total_h" in datos_celdas
        ):
            info_construccion["tamaño_total_h_mm"] += (
                alto_fila_px / escala if escala > 0 else alto_fila_px
            ) + (calles_h[row] if row < len(calles_h) else 0)

    # ─────────────────────────────────────────────────────────────────────────
    # PASO 3: Crear Column con todas las filas y separadores
    # ─────────────────────────────────────────────────────────────────────────

    trazado_column = ft.Column(
        filas_elementos,
        spacing=0,
        wrap=False,
        run_spacing=0,
    )

    print(f"{'='*100}")
    print(f"✅ TRAZADO CREADO CON ROW/COLUMN - ARQUITECTURA NUEVA")
    print(f"{'='*100}")
    print(f"  • Filas creadas: {info_construccion['num_filas_creadas']}")
    print(f"  • Celdas usadas: {info_construccion['num_celdas_usadas']}")
    print(f"  • Separadores H: {info_construccion['num_separadores_h']}")
    print(
        f"  • Tamaño total: {info_construccion['tamaño_total_w_mm']:.1f} x "
        f"{info_construccion['tamaño_total_h_mm']:.1f} mm"
    )
    print(f"{'='*100}\n")

    # ✅ Envolver el Column en un Container con bgcolor
    trazado_container = ft.Container(
        content=trazado_column,
        # TODO: bgcolor=ft.Colors.GREY_100,  # ← DESACTIVADO para ver trazado
    )

    return trazado_container, info_construccion


def calcular_espaciadores_visuales(
    datos_celdas: Optional[Dict],
    grid_cols: int,
    grid_rows: int,
    calles_v: List[float],
    calles_h: List[float],
    escala: float = 1.0,
) -> Dict:
    """
    Calcula los espaciadores visuales correctos considerando la sangre de las celdas.

    Fórmula:
    - espaciador_vertical = calle_margen_w(col) - sangre_izq(col+1)
    - espaciador_horizontal = calle_margen_h(row) - sangre_sup(row+1)

    Args:
        datos_celdas: Dict con info de sangres (formato "row_col: R,C": {...})
        grid_cols: Número de columnas
        grid_rows: Número de filas
        calles_v: Lista de anchos de calles verticales
        calles_h: Lista de alturas de calles horizontales
        escala: Factor de escala visual (mm a px)

    Returns:
        Dict con estructura:
        {
            "espaciadores_v": {(row, col): ancho_px, ...},  # espaciadores entre columnas
            "espaciadores_h": {(row, col): alto_px, ...},   # espaciadores entre filas
        }
    """

    espaciadores = {
        "espaciadores_v": {},  # (row, col) → ancho_px
        "espaciadores_h": {},  # (row, col) → alto_px
    }

    print(f"\n{'='*100}")
    print(f"🔲 CÁLCULO DE ESPACIADORES VISUALES - GRID Y SEPARADORES")
    print(f"{'='*100}")
    print(f"    • datos_celdas is None: {datos_celdas is None}")
    if datos_celdas:
        print(f"    • num keys en datos_celdas: {len(datos_celdas)}")
        print(f"    • grid: {grid_cols}×{grid_rows}")

    if not datos_celdas:
        # Fallback: usar calles directas sin ajuste de sangre
        print(f"    → FALLBACK: sin datos_celdas, usando calles directas")
        for row in range(grid_rows):
            for col in range(grid_cols - 1):
                ancho_mm = calles_v[col] if col < len(calles_v) else 0
                espaciadores["espaciadores_v"][(row, col)] = max(0, ancho_mm * escala)

        for row in range(grid_rows - 1):
            for col in range(grid_cols):
                alto_mm = calles_h[row] if row < len(calles_h) else 0
                espaciadores["espaciadores_h"][(row, col)] = max(0, alto_mm * escala)

        return espaciadores

    # ───────────────────────────────────────────────────────────────────────
    # CALCULAR ESPACIADORES VERTICALES (entre columnas)
    # ───────────────────────────────────────────────────────────────────────
    # ✅ calles_v contiene las calles verticales (entre columnas)

    print(f"\n    Espaciadores verticales (entre columnas):")

    for row in range(grid_rows):
        for col in range(grid_cols - 1):
            celda_key_actual = f"row_col: {row},{col}"
            celda_key_siguiente = f"row_col: {row},{col+1}"

            if celda_key_actual in datos_celdas and celda_key_siguiente in datos_celdas:
                # ✅ FÓRMULA CORRECTA: espaciador = calle(col) - sangre_derecha(col) - sangre_izquierda(col+1)
                # Usar CALLE COMPLETA, restando sangres de ambas celdas
                calle_col = calles_v[col] if col < len(calles_v) else 0
                sangre_der_col = datos_celdas[celda_key_actual].get(
                    "sangre_der_deseada", 0
                )
                sangre_izq_col_siguiente = datos_celdas[celda_key_siguiente].get(
                    "sangre_izq_deseada", 0
                )

                # Fórmula: espaciador = calle - sangre_derecha(col) - sangre_izquierda(col+1)
                espaciador_mm = calle_col - sangre_der_col - sangre_izq_col_siguiente
                if _PRINT_DEBUG:
                    print(
                        f"  [Sep V {row},{col}→{col+1}] calle={calle_col}, sangre_der={sangre_der_col}, sangre_izq_sig={sangre_izq_col_siguiente} → espaciador={espaciador_mm}mm"
                    )
            else:
                # Fallback: usar calle completa
                espaciador_mm = calles_v[col] if col < len(calles_v) else 0
                if _PRINT_DEBUG:
                    print(
                        f"  [Sep V {row},{col}→{col+1}] FALLBACK: calle_v[{col}]={espaciador_mm}mm"
                    )

            espaciadores["espaciadores_v"][(row, col)] = max(0, espaciador_mm * escala)

    # ───────────────────────────────────────────────────────────────────────
    # CALCULAR ESPACIADORES HORIZONTALES (entre filas)
    # ───────────────────────────────────────────────────────────────────────
    # ✅ calles_h contiene las calles horizontales (entre filas)

    print(f"\n    Espaciadores horizontales (entre filas):")

    for row in range(grid_rows - 1):
        for col in range(grid_cols):
            celda_key_actual = f"row_col: {row},{col}"
            celda_key_siguiente = f"row_col: {row+1},{col}"

            if celda_key_actual in datos_celdas and celda_key_siguiente in datos_celdas:
                # ✅ FÓRMULA CORRECTA: espaciador = calle(row) - sangre_abajo(row) - sangre_arriba(row+1)
                # Usar CALLE COMPLETA, restando sangres de ambas filas
                calle_row = calles_h[row] if row < len(calles_h) else 0
                sangre_inf_row = datos_celdas[celda_key_actual].get(
                    "sangre_inf_deseada", 0
                )
                sangre_sup_row_siguiente = datos_celdas[celda_key_siguiente].get(
                    "sangre_sup_deseada", 0
                )

                # Fórmula: espaciador = calle - sangre_abajo(row) - sangre_arriba(row+1)
                espaciador_mm = calle_row - sangre_inf_row - sangre_sup_row_siguiente
                if _PRINT_DEBUG:
                    print(
                        f"  [Sep H {row},{col}] calle={calle_row}, sangre_inf={sangre_inf_row}, sangre_sup_sig={sangre_sup_row_siguiente} → espaciador={espaciador_mm}mm"
                    )
            else:
                # Fallback: usar calle completa
                espaciador_mm = calles_h[row] if row < len(calles_h) else 0
                if _PRINT_DEBUG:
                    print(
                        f"  [Sep H {row},{col}] FALLBACK: calle_h[{row}]={espaciador_mm}mm"
                    )

            espaciadores["espaciadores_h"][(row, col)] = max(0, espaciador_mm * escala)

    print(f"{'='*100}\n")

    return espaciadores


# ═══════════════════════════════════════════════════════════════════════════════
# CALCULAR OFFSETS DE CELDAS (Posiciones absolutas en mm)
# ═══════════════════════════════════════════════════════════════════════════════


def calcular_offsets_celdas(
    datos_celdas: Dict,
    grid_cols: int,
    grid_rows: int,
    calles_v: List[float],
    calles_h: List[float],
    escala: float = 1.0,
    origin: Optional[str] = None,
    force: bool = False,
) -> Dict:
    """
    Calcula los offsets (posiciones absolutas en mm) de cada celda del trazado.

    Fórmula:
    - offset_x = celda_w × col + suma(calles_v[0:col])
    - offset_y = celda_h × row + suma(calles_h[0:row])

    Las calles anteriores "empujan" el offset a su posición correcta.

    Args:
        datos_celdas: Dict con info de celdas (formato "row_col: R,C": {...})
                     Debe contener al menos: celda_w, celda_h para cada celda
        grid_cols: Número de columnas
        grid_rows: Número de filas
        calles_v: Lista de anchos de calles verticales (entre columnas)
        calles_h: Lista de alturas de calles horizontales (entre filas)

    Returns:
        Dict con estructura:
        {
            "offsets_celdas": {
                0: {"x_mm": 0.0, "y_mm": 0.0},
                1: {"x_mm": 220.0, "y_mm": 0.0},
                ...
            },
            "grid_info": {
                "grid_cols": cols,
                "grid_rows": rows,
                "calles_v": calles_v,
                "calles_h": calles_h,
            }
        }
    """

    # Si ya existen offsets guardados en `datos_celdas` y no forzamos
    # la recomputación, reusar y evitar imprimir todo de nuevo.
    if not force and datos_celdas and "offsets_celdas" in datos_celdas:
        stored = {
            "offsets_celdas": datos_celdas["offsets_celdas"],
            "grid_info": datos_celdas.get("offsets_grid_info", {}),
        }
        label = origin or "datos_celdas (almacenado)"
        print("\n" + ("=" * 100))
        print("📍 OFFSETS USADOS (NO RECALCULADOS) - origen: %s", label)
        print("=" * 100)
        print("  • Total offsets: %s", len(stored["offsets_celdas"]))
        print("\n" + ("=" * 100) + "\n")
        return stored

    offsets_celdas = {}
    idx = 0

    header = origin or "calcular_offsets_celdas"
    # TÍTULO Y SEPARADOR
    print("\n" + ("=" * 100))
    print("📍 CÁLCULO DE OFFSETS - POSICIÓN DE CELDAS EN TRAZADO (origen: %s)", header)
    print("=" * 100)
    print(
        "    • Grid: %s × %s (%s celdas)", grid_cols, grid_rows, grid_cols * grid_rows
    )
    print("    • Calles V: %s", calles_v)
    print("    • Calles H: %s", calles_h)
    print("\n    Offsets calculados:")

    # Precomputar sumas acumuladas de calles para eficiencia
    suma_calles_v = [0.0]  # suma_calles_v[i] = suma de calles verticales hasta i
    for calle in calles_v:
        suma_calles_v.append(suma_calles_v[-1] + calle)

    suma_calles_h = [0.0]  # suma_calles_h[i] = suma de calles horizontales hasta i
    for calle in calles_h:
        suma_calles_h.append(suma_calles_h[-1] + calle)

    # Iterar sobre todas las celdas
    for row in range(grid_rows):
        for col in range(grid_cols):
            celda_key = f"row_col: {row},{col}"

            if celda_key not in datos_celdas:
                if _PRINT_DEBUG:
                    print(f"      ⚠️  Celda {celda_key} no encontrada en datos_celdas")
                continue

            celda_data = datos_celdas[celda_key]
            celda_w_mm = float(celda_data.get("celda_w", 0))
            celda_h_mm = float(celda_data.get("celda_h", 0))

            # ✅ CORREGIDO: Usar tamaño del USUARIO (sin sangres) en lugar del ancho de celda
            # Cuando hay calles, las sangres se solapan con ellas, por lo que usar celda_w
            # (que incluye sangres) duplicaría el espacio ocupado por las sangres.

            # Original formula:
            # offset_x = celda_w × col + suma(calles_v[0:col])
            offset_x_mm = (celda_w_mm * col) + (
                suma_calles_v[col] if col < len(suma_calles_v) else suma_calles_v[-1]
            )

            # offset_y = celda_h × row + suma(calles_h[0:row])
            offset_y_mm = (celda_h_mm * row) + (
                suma_calles_h[row] if row < len(suma_calles_h) else suma_calles_h[-1]
            )

            # Guardar offset por índice (0, 1, 2, ...)
            offsets_celdas[idx] = {
                "x_mm": round(offset_x_mm, 2),
                "y_mm": round(offset_y_mm, 2),
                "row": row,
                "col": col,
            }

            if _PRINT_DEBUG:
                print(
                    f"      [{idx:2d}] row_col({row},{col}): x={offset_x_mm:7.2f}mm, y={offset_y_mm:7.2f}mm  (celda_w={celda_w_mm:.2f}, col_calle_sum={suma_calles_v[col] if col < len(suma_calles_v) else suma_calles_v[-1]:.2f})"
                )

            idx += 1

    print(f"{'='*100}")
    print(f"✅ Total offsets calculados: {len(offsets_celdas)}")
    print(f"{'='*100}\n")

    # DEBUG: Verificar qué se va a retornar
    print(f"[DBG calcular_offsets_celdas] RETORNANDO grid_info:")
    print(f"      calles_v (entre columnas): {calles_v}")
    print(f"      calles_h (entre filas): {calles_h}")

    return {
        "offsets_celdas": offsets_celdas,
        "grid_info": {
            "grid_cols": grid_cols,
            "grid_rows": grid_rows,
            "calles_v": calles_v,
            "calles_h": calles_h,
        },
    }
