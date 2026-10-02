def get_stamp_limpio(_estado_impo_ui):
    campos = [
        "mediabox",
        "cropbox",
        "bleedbox",
        "cantidad",
        "can_hojas_tal",
        "hojas_x_pliego",
        "comienzo_numeracion",
        "horizontal",
        "vertical",
        "orientacion",
        "pdf_ruta",
        "pdf_nombre",
        "pdf_paginas",
        "grid_cols",
        "grid_rows",
        "calles_list",
        "tamano_usuario_w",
        "tamano_usuario_h",
        "sangre",
        "pliego_congelado",
        "offset_img_x",
        "offset_img_y",
        "offset_trazado_x",
        "offset_trazado_y",
        "dropdown_copias",
        "dropdown_doble_cara",
        "dropdown_rotacion",
        "checkbox_cruces",
        "checkbox_lineas_corte",
        "checkbox_marcas_texto",
        "checkbox_linea_exterior",
        "checkbox_xerox",
        "pliego_actual_texto",
        "total_pliegos",
        "ultima_modificacion",
        "marca_texto_pos_sup_izq",
        "marca_texto_pos_sup_der",
        "marca_texto_pos_inf_izq",
        "marca_texto_pos_inf_der",
        "marca_texto_pos_centro_sup",
        "marca_texto_pos_centro_inf",
        "marca_texto_pos_centro_lat_izq",
        "marca_texto_pos_centro_lat_der",
        "marca_texto_rotacion",
        "marca_texto_familia",
        "marca_texto_tipo",
        "marca_texto_cuerpo",
        "marca_texto_color",
        "marca_texto_offset_h_mm",
        "marca_texto_offset_v_mm",
        "longitud_cruz_mm",
        "grosor_cruz_pt",
        "offset_cruz_mm",
        "auto_sangre_offset_cruz",
        "offset_seguridad_mm",
        "longitud_brazo_max_mm",
        "trabajo_modificado",
        "ajuste_pliego_modo",
    ]
    return {k: _estado_impo_ui.get(k) for k in campos}


import flet as ft
from types import SimpleNamespace
import platform
import threading
import time
import asyncio
import os
import logging

try:
    import certifi

    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
except Exception:
    # Si certifi no está instalado, continuar; la comprobación SSL puede fallar en máquinas limpias
    pass
from screeninfo import get_monitors
import sys
from color_design import *
from grafico import dibujar_grafico, grafico_datos
from app_ui_items import *
import json
from trabajo_manager import (
    crear_datos_trabajo,
    guardar_trabajo_tns,
    cargar_trabajo_auto,
    validar_trabajo_data,
    crear_snapshot_estado,
    obtener_datos_imposicion_activa,
    restaurar_datos_imposicion,
)

# internacionalización básica
from lang import t, set_language, LANG as _LANG

# El idioma se configura desde LANG en lang.py por defecto.
# Intentar leer la preferencia guardada desde el módulo de preferencias de TalNumStack
try:
    from talnum_preferences import get_preference

    lang_pref = get_preference("language", None)
    if lang_pref:
        set_language(lang_pref)
    else:
        set_language(_LANG)
except Exception:
    # Si falla la lectura de preferencias, usar el valor por defecto
    set_language(_LANG)


def _en_pagina(control):
    # Flet 1.0: .page lanza RuntimeError si el control no está montado; getattr solo atrapa AttributeError
    try:
        return control.page is not None
    except Exception:
        return False

def _focus(control):
    # Flet 1.0: TextField.focus() es async; en handlers sync hay que programar la coroutine
    try:
        coro = control.focus()
        if asyncio.iscoroutine(coro):
            try:
                asyncio.get_running_loop().create_task(coro)
            except RuntimeError:
                coro.close()
    except Exception:
        pass

# Configurar logger de errores para TalNumStack
try:
    from error_logger import setup_error_logger, install_exception_handler

    setup_error_logger()
    install_exception_handler()
    print("[LOGGER] Logger de errores de TalNumStack iniciado correctamente")
except Exception as e:
    print(f"[LOGGER ERROR] No se pudo iniciar el logger: {e}")

# # Silenciar prints de depuración en este módulo por defecto.
# # Para activar, cambiar _PRINT_DEBUG = True durante desarrollo.
_PRINT_DEBUG = False
if not _PRINT_DEBUG:

    def _no_print(*args, **kwargs):
        return None

    print = _no_print

logger = logging.getLogger(__name__)

# Flag para controlar impresión debug de `_estado_impo_ui` (False por defecto)
DEBUG_ESTADO_IMPO_UI = False
# Flag central para silenciar los prints de control relacionados con el "stamp".
# Cambiar a True para activar temporalmente los prints de diagnóstico.
DEBUG_STAMP_APP = False


def boxes_coinciden(box_guardada, box_real, tolerancia=0.1):
    """
    Compara dos boxes (listas de 4 valores) con tolerancia decimal.

    Args:
        box_guardada: [x1, y1, x2, y2] guardada
        box_real: [x1, y1, x2, y2] leída del PDF
        tolerancia: Tolerancia en puntos para diferencias de redondeo

    Returns:
        True si coinciden, False si no
    """
    if not box_guardada or not box_real:
        return False

    if len(box_guardada) != 4 or len(box_real) != 4:
        return False

    for i in range(4):
        if abs(box_guardada[i] - box_real[i]) > tolerancia:
            return False

    return True


# Lógica de cálculo basada en los campos del XML


def calcular_tirada(cantidad, can_hojas_tal):
    try:
        # print(f"[DEBUG calcular_tirada] cantidad={cantidad}, can_hojas_tal={can_hojas_tal}, resultado={int(cantidad) * int(can_hojas_tal)}")
        return int(cantidad) * int(can_hojas_tal)
    except Exception:
        return ""


def calcular_tirada_calculada(can_tal_buscado, can_hojas_tal):
    try:
        return int(can_tal_buscado) * int(can_hojas_tal)
    except Exception:
        return ""


def calcular_opciones_montaje(cantidad, hojas_por_tal):
    try:
        cantidad = int(cantidad)
        hojas_por_tal = int(hojas_por_tal)
        total_hojas = cantidad * hojas_por_tal
        divisores = []
        for divisor in range(1, total_hojas + 1):
            if total_hojas % divisor == 0 and divisor % hojas_por_tal == 0:
                divisores.append(
                    total_hojas // divisor
                )  # El divisor es el número de pliegos (ej: 1,2,5,10)
        return sorted(divisores), total_hojas
    except Exception:
        return [], ""


def obtener_ancho_pantalla():

    return get_monitors()[0].width


def get_resource_path(relative_path):
    """Obtiene la ruta absoluta del recurso, compatible con PyInstaller"""
    try:
        # PyInstaller crea una carpeta temporal y guarda su ruta en _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


def main(page: ft.Page):
    # Inicializar tema y colores correctamente al arrancar
    from color_design import actualizar_colores, definir_constantes_color

    actualizar_colores()  # Actualizar las constantes de color

    # Aplicar tema inicial detectado
    page.theme_mode = tema_flet
    page.theme, page.dark_theme = definir_constantes_color()
    # print(f"[INFO] Tema aplicado al arrancar: {tema} -> {tema_flet}")

    # Bloquear cierre de ventana con botón nativo
    # (El handler se define más adelante después de tener acceso a project_modified)
    page.window.prevent_close = True

    # Diálogo de espera eliminado: no se usa en esta versión

    # --- Función para calcular los valores de montaje para cada hojas_x_pliego ---
    def calcular_montaje_pro(cantidad, hojas_por_tal, hojas_x_pliego):
        """
        Devuelve: (HxP, T.H.C., T.C., Tal.C.)
        HxP = hojas_x_pliego
        T.H.C. = Total hojas calculadas (ajustado)
        T.C. = Tiradas calculadas
        Tal.C. = Talonarios calculados (ajustados)
        """
        try:
            cantidad = int(cantidad)
            hojas_por_tal = int(hojas_por_tal)
            hojas_x_pliego = int(hojas_x_pliego)
            if cantidad <= 0 or hojas_por_tal <= 0 or hojas_x_pliego <= 0:
                return hojas_x_pliego, "", "", ""
            talonarios_ajustados = cantidad
            total_hojas = cantidad * hojas_por_tal
            # Ajuste iterativo para que cuadre la tirada
            while (total_hojas // hojas_x_pliego) * hojas_x_pliego != total_hojas or (
                total_hojas // hojas_x_pliego
            ) % hojas_por_tal != 0:
                talonarios_ajustados += 1
                total_hojas += hojas_por_tal
            tiradas_calculadas = total_hojas // hojas_x_pliego
            return hojas_x_pliego, total_hojas, tiradas_calculadas, talonarios_ajustados
        except Exception:
            return hojas_x_pliego, "", "", ""

    # --- Debug: imprimir las 50 opciones (1..50) usando la lógica de ajuste ---
    def opciones_montaje_pro():
        cantidad_val = (
            cantidad.value
            if getattr(cantidad, "value", None) and str(cantidad.value).isdigit()
            else None
        )
        hojas_por_tal_val = (
            can_hojas_tal.value
            if getattr(can_hojas_tal, "value", None)
            and str(can_hojas_tal.value).isdigit()
            else None
        )
        if not cantidad_val or not hojas_por_tal_val:
            # print("[DEBUG opciones_montaje_pro] Campos vacíos o inválidos")
            return
        # Evitar imprimir la misma tabla repetidamente si los inputs no han cambiado
        key = (str(cantidad_val), str(hojas_por_tal_val))
        if getattr(opciones_montaje_pro, "_last_key", None) == key:
            return
        opciones_montaje_pro._last_key = key

        # print("HxP\tT.H.C.\tT.C.\tTal.C.")
        for hxp in range(1, 51):
            res = calcular_montaje_pro(cantidad_val, hojas_por_tal_val, hxp)
            # print(f"{res[0]}\t{res[1]}\t{res[2]}\t{res[3]}")

    # Hacer que el fondo del gráfico use el color definido
    import grafico as graf

    graf.COLOR_FONDO_GRAFICO = FONDO_GRAFICO_COLOR

    def resumen_ajuste_create(
        _tirada_calculada, _talonarios_calculados, _total_hojas, _talonarios_fase1
    ):
        # Inicializar el atributo de función si no existe
        if not hasattr(resumen_ajuste_create, "_ultimo_resumen_ajuste_valores"):
            resumen_ajuste_create._ultimo_resumen_ajuste_valores = None
        if not hasattr(resumen_ajuste_create, "_ultimo_resumen"):
            resumen_ajuste_create._ultimo_resumen = ""

        valores_actuales = (
            _tirada_calculada,
            _talonarios_calculados,
            _total_hojas,
            _talonarios_fase1,
        )

        # Si los valores no han cambiado, devolver el último resumen
        if valores_actuales == resumen_ajuste_create._ultimo_resumen_ajuste_valores:
            return resumen_ajuste_create._ultimo_resumen

        # Si algún campo está vacío, devolver cadena vacía y guardar los valores
        if (
            not _tirada_calculada
            or not _talonarios_calculados
            or not _total_hojas
            or not _talonarios_fase1
        ):
            resumen_ajuste_create._ultimo_resumen_ajuste_valores = valores_actuales
            resumen_ajuste_create._ultimo_resumen = ""
            return ""

        # print(f"[DEBUG resumen_ajuste_create] _tirada_calculada={_tirada_calculada}, _talonarios_calculados={_talonarios_calculados}, _total_hojas={_total_hojas}, _talonarios_fase1={_talonarios_fase1}")

        _tirada_calculada = int(_tirada_calculada) if _tirada_calculada else 0
        _talonarios_calculados = (
            int(_talonarios_calculados) if _talonarios_calculados else 0
        )
        _total_hojas = int(_total_hojas) if _total_hojas else 0
        _talonarios_fase1 = int(_talonarios_fase1) if _talonarios_fase1 else 0

        _resumen = t(
            "{0} Talonarios de {1} hojas = {2} hojas / {3} Hojas x pliego = {4} Tiradas"
        ).format(
            _talonarios_calculados,
            can_hojas_tal.value,
            _total_hojas,
            hojas_x_pliego.value,
            _tirada_calculada,
        )
        if _talonarios_calculados > int(_talonarios_fase1):
            _incremento = _talonarios_calculados - int(_talonarios_fase1)
            if _incremento > 0:
                _resumen += t(" (+{0} Talonarios)").format(_incremento)

        # print(f"[DEBUG resumen_ajuste_create] Resumen generado: {_resumen}")

        resumen_ajuste_create._ultimo_resumen_ajuste_valores = valores_actuales
        resumen_ajuste_create._ultimo_resumen = _resumen
        return _resumen

    # --- NUEVA FUNCIÓN: Genera opciones válidas para el Dropdown de Hojas x pliego en modo Auto ---
    def crear_lista_hojas_x_pliego_dropdown(tirada_total, hojas_por_tal):
        """
        Devuelve una lista de opciones (1-40) donde:
        - tirada_ajustada = tirada_total / hojas_x_pliego
        - tirada_ajustada % hojas_por_tal == 0
        Solo incluye valores donde la división es exacta y el resultado es múltiplo de hojas_por_tal.
        """
        opciones = []
        """
        Devuelve una lista de opciones del 1 al 100, sin filtrar por compatibilidad.
        """
        return [str(i) for i in range(1, 101)]

    # Estado para el modo de ajuste por pliego
    ajuste_pliego_modo = {"valor": "Auto"}  # 'Auto' por defecto

    # Contenedor dinámico para el control de Hojas x pliego
    hojas_x_pliego_container = ft.Container(width=80, height=40)
    # Inicializa el contenido SIN llamar a update (aún no está en la página)
    hojas_x_pliego_container.content = None

    def get_hojas_x_pliego_control():
        if ajuste_pliego_modo["valor"] == "Manual":
            return hojas_x_pliego
        else:
            opciones_dropdown = []
            cantidad_val = (
                cantidad.value if cantidad.value and cantidad.value.isdigit() else None
            )
            hojas_por_tal_val = (
                can_hojas_tal.value
                if can_hojas_tal.value and can_hojas_tal.value.isdigit()
                else None
            )
            if cantidad_val and hojas_por_tal_val:
                tirada_total = int(cantidad_val) * int(hojas_por_tal_val)
                opciones_validas = crear_lista_hojas_x_pliego_dropdown(
                    tirada_total, hojas_por_tal_val
                )
                opciones_dropdown = [
                    ft.dropdown.Option(str(x)) for x in opciones_validas
                ]

            # CRÍTICO: Usar el valor actual de hojas_x_pliego si existe y está en las opciones
            valor_inicial = None
            if hojas_x_pliego.value and opciones_dropdown:
                opciones_keys = [opt.key for opt in opciones_dropdown]
                if hojas_x_pliego.value in opciones_keys:
                    valor_inicial = hojas_x_pliego.value
                    print(
                        f"[DEBUG get_control] Usando valor existente: {valor_inicial}"
                    )
                else:
                    valor_inicial = opciones_dropdown[0].key
                    print(
                        f"[DEBUG get_control] Valor existente '{hojas_x_pliego.value}' no en opciones, usando primero: {valor_inicial}"
                    )
            elif opciones_dropdown:
                valor_inicial = opciones_dropdown[0].key
                print(
                    f"[DEBUG get_control] Sin valor existente, usando primero: {valor_inicial}"
                )

            # Handler intermedio para el dropdown en modo Auto
            def on_dropdown_hojas_x_pliego_change(e):
                hojas_x_pliego.value = e.control.value
                on_hojas_x_pliego_change(e)
                validar_hojas_x_pliego(e)
                mostrar_trazado()  # Actualiza el gráfico tras el cambio del dropdown

            dropdown = ft.Dropdown(
                width=80,
                options=opciones_dropdown,
                value=valor_inicial,
                on_select=on_dropdown_hojas_x_pliego_change,
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
            return dropdown

    def update_hojas_x_pliego_control():
        """
        Actualiza el contenido del contenedor hojas_x_pliego_container
        según el modo de ajuste (Auto/Manual).

        Si skip_auto_calculation=True, solo actualiza el control visual sin recalcular valores.
        """
        print(
            f"[DEBUG update_control] Iniciando - HojasXPliego:{hojas_x_pliego.value}, Modo:{ajuste_pliego_modo['valor']}"
        )
        control = get_hojas_x_pliego_control()
        hojas_x_pliego_container.content = control
        hojas_x_pliego_container.update()
        page.update()
        print(
            f"[DEBUG update_control] Control actualizado - Tipo:{type(control).__name__}"
        )
        # Si el modo es Auto y el control es Dropdown con opciones válidas, auto-seleccionar y validar el primer valor
        # PERO: No hacerlo si estamos en modo de carga (skip_auto_calculation=True)
        skip_calculation = getattr(
            update_hojas_x_pliego_control, "_skip_calculation", False
        )
        if skip_calculation:
            print(
                "[DEBUG update_hojas_x_pliego_control] Skip calculation activado - no recalcular"
            )
            return

        if (
            ajuste_pliego_modo["valor"] == "Auto"
            and hasattr(control, "options")
            and control.options
        ):
            primer_valor = control.options[0].key
            if primer_valor is None:
                return
            hojas_x_pliego.value = (
                primer_valor  # Solo actualiza el valor interno, NO el TextField
            )
            # Validar y calcular inmediatamente tras asignar el valor
            validar_hojas_x_pliego(None)

            hojas_x_pliego_val = str(primer_valor)

            # Actualizar opciones y valor del dropdown horizontal
            opts = [
                ft.dropdown.Option(str(i)) for i in divisores(int(hojas_x_pliego_val))
            ]

            # Mantener el valor actual si existe en las nuevas opciones, sino usar el primero
            valor_actual = horizontal_dropdown.value
            opciones_disponibles = [opt.key for opt in opts]

            if valor_actual in opciones_disponibles:
                nuevo_valor = valor_actual
            else:
                nuevo_valor = opts[0].key if opts else "1"

            horizontal_dropdown.options = opts
            horizontal_dropdown.value = nuevo_valor
            horizontal_dropdown.update()

            # Calcular y actualizar el campo vertical
            horizontal_val = str(nuevo_valor if nuevo_valor is not None else "1")
            h = int(horizontal_val)
            v = int(hojas_x_pliego.value) // h if h != 0 else 0
            vertical_value.value = str(v)
            vertical_value.update()

            # Recalcular orientación y trazado
            on_horizontal_change(None)

    # --- Resetea la fase 2 y 3 ---
    def reset_fase2_fase3():

        # Si ambos campos están vacíos, salir de la función para evitar errores posteriores
        if not hojas_x_pliego.value and not tirada_calculada.value:
            return

        # Limpiar tirada_calculada
        tirada_calculada.value = ""
        tirada_calculada.update()

        # Ocultar resumen y botón PDF
        resumen_ajuste.value = ""
        resumen_ajuste.update()
        bloque_resumen_.visible = False
        bloque_resumen_.update()
        boton_informe_container.disabled = True
        boton_informe_container.opacity = 0.4
        boton_informe_container.update()
        icono_ajuste_container.disabled = True
        icono_ajuste_container.opacity = 0.4
        if _en_pagina(icono_ajuste_container):
            icono_ajuste_container.update()
        icono_pdf_ordenado_container.disabled = True
        icono_pdf_ordenado_container.opacity = 0.4
        icono_pdf_ordenado_container.update()
        icono_imponer_container.disabled = True
        icono_imponer_container.opacity = 0.4
        icono_imponer_container.update()

        # Ocultar gráfico
        grafico_viewer.visible = False
        grafico_viewer.update()

        # Resetear horizontal/vertical y orientación
        horizontal_dropdown.options = [ft.dropdown.Option("1")]
        horizontal_dropdown.value = ""
        horizontal_dropdown.update()
        vertical_value.value = ""
        vertical_value.update()
        orientacion_dropdown.value = "Izquierda"
        orientacion_dropdown.visible = True
        orientacion_dropdown.update()
        # Limpiar ajuste activo
        try:
            print(
                {
                    "_debug": "reset_fase2_fase3 BEFORE clear",
                    "ajuste_activo": ajuste_activo,
                }
            )
        except Exception:
            pass
        ajuste_activo["talonarios"] = ""
        ajuste_activo["total_hojas"] = ""
        ajuste_activo["cantidad"] = ""
        ajuste_activo["hojas_por_tal"] = ""
        ajuste_activo["hojas_x_pliego"] = ""
        talonarios_ajustados_var["valor"] = ""
        try:
            print(
                {
                    "_debug": "reset_fase2_fase3 AFTER clear",
                    "ajuste_activo": ajuste_activo,
                }
            )
        except Exception:
            pass

    def on_ajuste_pliego_modo_change(e, modo):
        # Si el modo no cambia, no hacer nada
        if ajuste_pliego_modo["valor"] == modo:
            return

        ajuste_pliego_modo["valor"] = modo
        # Actualizar el stamp inmediatamente
        update_impo_field("ajuste_pliego_modo", modo)
        mostrar_snackbar(
            page,
            t("Modo de ajuste por pliego: {0}").format(ajuste_pliego_modo["valor"]),
            SNACKBAR_COLOR_FONDO,
            2000,
        )
        # Solo ejecutar reset si hojas_x_pliego está vacío, no es número o es 0
        if (
            not hojas_x_pliego.value
            or not hojas_x_pliego.value.isdigit()
            or int(hojas_x_pliego.value) == 0
        ):
            reset_fase2_fase3()
        update_hojas_x_pliego_control()
        page.update()

    # Función para manejar el cambio de tema desde el botón toggle
    def on_tema_toggle_change(e):
        """Maneja el cambio de tema desde el botón toggle"""
        from color_design import set_tema_manual

        # Alternar el tema basado en el estado actual de la página
        if page.theme_mode == ft.ThemeMode.DARK:
            nuevo_tema = "claro"
            nuevo_tema_flet = ft.ThemeMode.LIGHT
        else:
            nuevo_tema = "oscuro"
            nuevo_tema_flet = ft.ThemeMode.DARK

        # Actualizar el estado del botón para reflejar el nuevo tema
        e.control.selected = nuevo_tema_flet == ft.ThemeMode.DARK

        # Establecer el tema manualmente
        set_tema_manual(nuevo_tema, nuevo_tema_flet)

        # Aplicar inmediatamente a la página
        page.theme_mode = nuevo_tema_flet
        page.theme, page.dark_theme = definir_constantes_color()

        # Actualizar colores
        try:
            from color_design import actualizar_colores

            actualizar_colores()
        except Exception:
            # print("[ERROR on_tema_toggle_change] No se pudo actualizar colores")
            pass

        page.update()
        # print(f"[INFO] Tema cambiado manualmente a: {nuevo_tema}")

    # Crear iconos individuales que reemplazan el menú del engranaje
    # Handler toggle robusto: alterna el modo y llama al handler real
    def on_toggle_ajuste_pliego(e, modo=None):
        # SIEMPRE alterna el modo actual, sin depender de argumentos externos
        modo_actual = ajuste_pliego_modo["valor"]
        nuevo_modo = "Manual" if modo_actual == "Auto" else "Auto"
        on_ajuste_pliego_modo_change(e, nuevo_modo)

    icono_ajuste_pliego, icono_pdf_ordenado, icono_imponer, icono_info = (
        crear_iconos_menu(on_toggle_ajuste_pliego, page, None, None)
    )  # on_guardar_trabajo y get_project_state se asignarán después

    # Crear botón toggle de tema
    boton_toggle_tema = crear_boton_toggle_tema(on_tema_toggle_change)

    # Variable para controlar la visibilidad del gráfico y botón PDF
    grafico_visible = {"valor": False}
    # Título de la ventana con nombre del proyecto
    page.title = t("TalNumStack - Sin título")

    # Configurar icono de la ventana (especialmente para Windows)
    try:
        # Intentar cargar desde la nueva carpeta assets
        _icon_path = get_resource_path(os.path.join("assets", "icon.ico"))
        if not os.path.exists(_icon_path):
            # Fallback a la ubicación anterior por si acaso
            _icon_path = get_resource_path("TalNumStack.ico")

        if os.path.exists(_icon_path):
            page.window.icon = _icon_path
    except Exception as e:
        print(f"[INIT] Error configurando icono: {e}")
    # Ajustes por plataforma: usar los mismos valores que la versión de referencia
    if platform.system() == "Darwin":
        page.window.width = 1330
        # page.window.max_width = 1330
        page.window.min_width = 1330
        page.window.height = 860
        # page.window.max_height = 845
        page.window.min_height = 860
    else:
        # print("Platform no es macOS, usando valores por defecto para Windows/otros")
        # Valores pensados para Windows/otros
        page.window.width = 1340
        # page.window.max_width = 1340
        page.window.min_width = 1340
        page.window.height = 855
        # page.window.max_height = 855
        page.window.min_height = 855
    # page.window_resizable = False
    if platform.system() == "Darwin":
        page.window.left = (obtener_ancho_pantalla() - page.window.width) / 2
        page.window.top = 0
    else:
        page.window.left = 10
        page.window.top = 0
    page.padding = 0
    page.window.resizable = True
    page.expand = True
    page.update()

    # Cantidad de talonarios
    def validar_cantidad(e):
        # print(f"validar_cantidad: {cantidad.value}")
        val = cantidad.value
        if not val or not val.isdigit() or int(val) <= 0:
            mostrar_snackbar(
                page,
                t("Talonarios debe ser mayor que cero."),
                SNACKBAR_COLOR_ERROR,
                3000,
            )
            tirada.value = ""
            tirada.update()
            _focus(cantidad)
            fase_2_fase_3_visible_off()

        else:
            # Marcar como modificado
            mark_modified()
            try:
                update_impo_field("cantidad", cantidad.value)
            except Exception:
                pass
            # Si ambos campos son válidos
            if (
                can_hojas_tal.value
                and can_hojas_tal.value.isdigit()
                and int(can_hojas_tal.value) > 0
            ):

                if ajuste_pliego_modo["valor"] == "Auto":
                    # Forzar validación/cálculo tras asignar el valor al dropdown (como en la app antigua)
                    # Asegurarse de que el control `hojas_x_pliego` esté en 1
                    # (el gráfico inicial asume 1 en modo Auto).
                    try:
                        hojas_x_pliego.value = "1"
                        hojas_x_pliego.update()
                    except Exception:
                        pass

                    update_hojas_x_pliego_control()
                    on_hojas_x_pliego_change(None)
                    validar_hojas_x_pliego(None)

                else:
                    actualizar_campos()
                    mostrar_trazado()
                    if _en_pagina(hojas_x_pliego):
                        _focus(hojas_x_pliego)
                vertical_value.value = "1"
                vertical_value.update()
            _focus(can_hojas_tal)

    def on_focus_campos(e, campo):
        global tecla_capturada
        # print(f"Campo con foco: {campo} - tecla capturada {tecla_capturada}")
        if campo == "cantidad" and (
            tecla_capturada == "Enter"
            or tecla_capturada == "Numpad Enter"
            or tecla_capturada == "Tab"
        ):
            # print(f"Validando cantidad: {cantidad.value}")
            tecla_capturada = None  # Limpiar tecla capturada después de validar
            validar_cantidad(e)

        if campo == "can_hojas_tal" and (
            tecla_capturada == "Enter"
            or tecla_capturada == "Numpad Enter"
            or tecla_capturada == "Tab"
        ):
            # print(f"Validando {campo}: {can_hojas_tal.value} con tecla {tecla_capturada}")
            validar_can_hojas_tal(e)

        if campo == "hojas_x_pliego" and (
            tecla_capturada == "Enter"
            or tecla_capturada == "Numpad Enter"
            or tecla_capturada == "Tab"
        ):
            # print(f"Validando {campo}: {hojas_x_pliego.value} con tecla {tecla_capturada}")
            tecla_capturada = None  # Limpiar tecla capturada después de validar
            validar_hojas_x_pliego(e)

    # campo de cantidad de talonarios textfield
    cantidad = crear_textfield_cantidad(on_focus_campos)

    def _on_cantidad_change(e):
        mark_modified()
        try:
            update_impo_field("cantidad", cantidad.value)
        except Exception:
            pass

    try:
        cantidad.on_change = _on_cantidad_change
    except Exception:
        pass

    # Campo de Tirada calculada por talonario
    def validar_can_hojas_tal(e) -> None:
        global tecla_capturada
        # Si cantidad está vacía, mostrar mensaje y poner foco
        if (
            not cantidad.value
            or not cantidad.value.isdigit()
            or int(cantidad.value) <= 0
        ):
            mostrar_snackbar(
                page,
                t("Talonarios debe ser mayor que cero."),
                SNACKBAR_COLOR_ERROR,
                3000,
            )
            _focus(cantidad)
            return

        val = str(can_hojas_tal.value or "")
        if (val == "" or (val.isdigit() and int(val) <= 0)) and tecla_capturada in (
            "Tab",
            "Enter",
            "Numpad Enter",
        ):
            # print("campo 'can_hojas_tal' vacio")
            mostrar_snackbar(
                page,
                t("Hojas por talonario debe ser mayor que cero."),
                SNACKBAR_COLOR_ERROR,
                3000,
            )
            tirada.value = ""
            tirada.update()
            fase_2_fase_3_visible_off()
            _focus(can_hojas_tal)
            return
        else:
            tecla_capturada = None  # Limpiar tecla capturada después de validar
            # Marcar como modificado
            mark_modified()
            try:
                update_impo_field("horizontal", horizontal_dropdown.value)
                update_impo_field("vertical", vertical_value.value)
                update_impo_field("orientacion", orientacion_dropdown.value)
            except Exception:
                pass
            if ajuste_pliego_modo["valor"] == "Auto":
                # Forzar `hojas_x_pliego` a 1 para mantener coherencia con el gráfico
                try:
                    hojas_x_pliego.value = "1"
                    hojas_x_pliego.update()
                except Exception:
                    pass

                # Recalcular y actualizar el dropdown SIEMPRE antes de cualquier otra acción
                update_hojas_x_pliego_control()
                on_hojas_x_pliego_change(None)
                validar_hojas_x_pliego(None)
            else:
                # MODO MANUAL: Si el campo está vacío, ponerlo en "1" y actualizar
                if (
                    not hojas_x_pliego.value
                    or not hojas_x_pliego.value.isdigit()
                    or int(hojas_x_pliego.value) == 0
                ):
                    hojas_x_pliego.value = "1"
                    hojas_x_pliego.update()
                validar_hojas_x_pliego(None)
                actualizar_campos()
                mostrar_trazado()
                if _en_pagina(hojas_x_pliego):
                    _focus(hojas_x_pliego)
            # Siempre inicializar vertical_value a '1' tras validar correctamente ambos campos
            vertical_value.value = "1"
            vertical_value.update()

    # Campo de hojas por talonario textfield
    can_hojas_tal = crear_textfield_can_hojas_tal(on_focus_campos)

    def _on_can_hojas_tal_change(e):
        mark_modified()
        try:
            update_impo_field("can_hojas_tal", can_hojas_tal.value)
        except Exception:
            pass

    try:
        can_hojas_tal.on_change = _on_can_hojas_tal_change
    except Exception:
        pass

    # Campo de tirada calculada textfield
    tirada = crear_textfield_tirada()

    # Campo de hojas por pliego
    def validar_hojas_x_pliego(e):
        try:
            print(
                {
                    "_debug": "validar_hojas_x_pliego ENTER",
                    "e": str(getattr(e, "control", e)),
                    "hojas_x_pliego.value": getattr(hojas_x_pliego, "value", None),
                    "cantidad.value": getattr(cantidad, "value", None),
                    "can_hojas_tal.value": getattr(can_hojas_tal, "value", None),
                }
            )
        except Exception:
            pass
        # print(f"[DEBUG] validar_hojas_x_pliego: e={e}, value={getattr(e, 'control', None)} | hojas_x_pliego.value={hojas_x_pliego.value}")
        # IF 1: Sincronización desde dropdown
        if (
            e
            and hasattr(e, "control")
            and getattr(e.control, "value", None) is not None
        ):
            # print('[IF 1] Evento viene de dropdown')
            hojas_x_pliego.value = e.control.value
            # print(f"[DEBUG] Sincronizado hojas_x_pliego.value = {hojas_x_pliego.value} desde dropdown")
        val1 = cantidad.value
        val2 = can_hojas_tal.value
        # IF 2: Validación de campos principales
        if (
            not val1
            or not val1.isdigit()
            or int(val1) <= 0
            or not val2
            or not val2.isdigit()
            or int(val2) <= 0
        ):
            # print('[IF 2] Campos Talonarios/Hojas por talonario inválidos')
            hojas_x_pliego.value = ""
            columna_fase2.visible = False
            hojas_x_pliego.update()
        if (not val1 or not val1.isdigit() or int(val1) <= 0) and (
            not val2 or not val2.isdigit() or int(val2) <= 0
        ):
            mensaje = t(
                "Los campos Talonarios y Hojas por talonario no pueden estar vacíos ni ser cero."
            )
        elif not val1 or not val1.isdigit() or int(val1) <= 0:
            mensaje = t("El campo Talonarios no puede estar vacío ni ser cero.")
        elif not val2 or not val2.isdigit() or int(val2) <= 0:
            mensaje = t(
                "El campo Hojas por talonario no puede estar vacío ni ser cero."
            )
            try:
                print(
                    {
                        "_debug": "validar_hojas_x_pliego SHOW SNACKBAR",
                        "mensaje": mensaje,
                        "val1(cantidad)": val1,
                        "val2(can_hojas_tal)": val2,
                        "hojas_x_pliego.value": getattr(hojas_x_pliego, "value", None),
                        "e": str(getattr(e, "control", e)),
                    }
                )
            except Exception:
                pass
            mostrar_snackbar(page, mensaje, SNACKBAR_COLOR_ERROR, 3000)
            if not val1 or not val1.isdigit() or int(val1) <= 0:
                _focus(cantidad)
            elif not val2 or not val2.isdigit() or int(val2) <= 0:
                _focus(can_hojas_tal)
            # Ocultar gráfico y botón PDF
            grafico_viewer.visible = False
            grafico_viewer.update()
            grafico_visible["valor"] = False
            return
        # IF 3: Campo hojas_x_pliego vacío
        if not hojas_x_pliego.value:
            # print('[IF 3] Campo hojas_x_pliego vacío')
            # Si está vacío, solo bloquear cálculos y ocultar elementos, sin mostrar mensaje
            grafico_viewer.visible = False
            grafico_viewer.update()
            grafico_visible["valor"] = False
            return
        # IF 4: Campo hojas_x_pliego no es número válido
        if not hojas_x_pliego.value.isdigit() or int(hojas_x_pliego.value) <= 0:
            # print('[IF 4] Campo hojas_x_pliego no es número válido')
            mostrar_snackbar(
                page,
                t("El campo Hojas x pliego no puede ser cero ni texto."),
                SNACKBAR_COLOR_ERROR,
                3000,
            )
            grafico_viewer.visible = False
            grafico_viewer.update()
            grafico_visible["valor"] = False
            return
        # IF 5: División por cero
        if int(hojas_x_pliego.value) == 0:
            # print('[IF 5] División por cero en hojas_x_pliego')
            mostrar_snackbar(
                page,
                t("No se puede dividir por cero en Hojas x pliego."),
                SNACKBAR_COLOR_ERROR,
                3000,
            )
            _focus(hojas_x_pliego)
            grafico_viewer.visible = False
            grafico_viewer.update()
            grafico_visible["valor"] = False
            resumen_ajuste.value = ""
            bloque_resumen_.visible = False
            bloque_resumen_.update()
            resumen_ajuste.update()
            boton_informe_container.disabled = True
            boton_informe_container.opacity = 0.4
            boton_informe_container.update()
            icono_ajuste_container.disabled = True
            icono_ajuste_container.opacity = 0.4
            if _en_pagina(icono_ajuste_container):
                icono_ajuste_container.update()
            icono_pdf_ordenado_container.disabled = True
            icono_pdf_ordenado_container.opacity = 0.4
            icono_pdf_ordenado_container.update()
            icono_imponer_container.disabled = True
            icono_imponer_container.opacity = 0.4
            icono_imponer_container.update()
            return
        # Si todo es válido, mostrar gráfico y botón PDF
        # print('[IF OK] Todos los campos válidos, actualizando gráfico y resumen')
        # Marcar como modificado
        mark_modified()
        actualizar_campos()
        mostrar_trazado()
        fase_2_fase_3_visible_on()
        grafico_viewer.visible = True
        grafico_viewer.update()
        grafico_visible["valor"] = True
        _focus(comienzo_numeracion)

    # Campo de hojas x pliego textfield
    hojas_x_pliego = crear_textfield_hojas_x_pliego(on_focus_campos)

    def _on_hojas_x_pliego_change(e):
        mark_modified()
        try:
            update_impo_field("hojas_x_pliego", hojas_x_pliego.value)
        except Exception:
            pass

    try:
        hojas_x_pliego.on_change = _on_hojas_x_pliego_change
    except Exception:
        pass

    # Campo de tirada calculada (calculado) textfield
    tirada_calculada = crear_textfield_tirada_calculada()

    # Crear columna para opciones de montaje Column
    opciones_montaje = crear_column_opciones_montaje()

    # Campo de resumen para la Fase 2
    resumen_ajuste = crear_text_resumen_ajuste()
    boton_pdf = crear_boton_pdf(lambda e: crear_pdf_desde_app())

    # Crear el bloque de resumen usando la función
    bloque_resumen_ = crear_bloque_resumen(resumen_ajuste)

    # Variable para guardar el número de talonarios ajustado
    talonarios_ajustados_var = {"valor": ""}

    # Variables para guardar el ajuste de talonarios y total de hojas y los valores de entrada usados en el ajuste
    ajuste_activo = {
        "talonarios": "",
        "total_hojas": "",
        "cantidad": "",
        "hojas_por_tal": "",
        "hojas_x_pliego": "",
    }

    # Lógica de cálculo automática
    def actualizar_campos(e=None):
        # Guard: evitar recomputar si los valores de entrada no han cambiado
        try:
            current_values = (
                (
                    str(cantidad.value)
                    if getattr(cantidad, "value", None) is not None
                    else ""
                ),
                (
                    str(can_hojas_tal.value)
                    if getattr(can_hojas_tal, "value", None) is not None
                    else ""
                ),
                (
                    str(hojas_x_pliego.value)
                    if getattr(hojas_x_pliego, "value", None) is not None
                    else ""
                ),
            )
        except Exception:
            current_values = ("", "", "")

        # Si los valores son iguales a la última llamada, no hacemos nada
        if getattr(actualizar_campos, "_last_values", None) == current_values:
            return

        # Guardar valores actuales para la próxima invocación
        actualizar_campos._last_values = current_values

        # FASE 1: Solo requiere cantidad y can_hojas_tal válidos
        if not (
            cantidad.value
            and cantidad.value.isdigit()
            and int(cantidad.value) > 0
            and can_hojas_tal.value
            and can_hojas_tal.value.isdigit()
            and int(can_hojas_tal.value) > 0
        ):
            tirada_calculada.value = ""
            tirada_calculada.update()
            tirada.value = ""
            tirada.update()
            fase_2_fase_3_visible_off()
            return
        # Si cantidad y can_hojas_tal son válidos, mostrar Fase 1
        tirada.value = calcular_tirada(cantidad.value, can_hojas_tal.value)
        opciones, total = calcular_opciones_montaje(cantidad.value, can_hojas_tal.value)
        # Mantener la lista de opciones compatibles (no usada en la UI pro)
        filas = generar_filas_opciones_montaje(opciones, total)

        # Generar lista PRO completa (HxP 1..50) y mostrarla en la parte inferior de Fase 1
        montajes = []
        try:
            for hxp in range(1, 51):
                montajes.append(
                    calcular_montaje_pro(cantidad.value, can_hojas_tal.value, hxp)
                )
        except Exception:
            montajes = []

        try:
            filas_pro = generar_filas_opciones_montaje_pro(montajes)
            opciones_montaje.controls = filas_pro
        except Exception as ex:
            # Fallback: usar la lista clásica si falla la generación PRO
            # print(f"[DEBUG] fallo al generar filas PRO: {ex}")
            opciones_montaje.controls = filas
        fase_2_fase_3_visible_on()
        tirada.update()
        # FASE 2 y 3: Usar la función nueva para el cálculo y resumen
        aplicar_ajuste_hojas_x_pliego()

    # Al iniciar la app, poner el foco (on_connect no sirve: el cliente ya está
    # conectado al entrar en main → se llama tras page.add abajo)
    def set_focus_inicial(e=None):
        _focus(cantidad)

    # --- Captura eventos de teclado globales ---
    # Variable global para guardar la última tecla capturada

    global tecla_capturada
    tecla_capturada = None

    def captura_teclado(e):
        global tecla_capturada
        tecla_capturada = e.key
        # print(f"Tecla capturada: {tecla_capturada}")

    page.on_keyboard_event = captura_teclado

    # --- Nueva función para aplicar el ajuste al seleccionar hojas_x_pliego ---
    def aplicar_ajuste_hojas_x_pliego():
        try:
            if not (
                cantidad.value and cantidad.value.isdigit() and int(cantidad.value) > 0
            ):
                # print("[ERROR aplicar_ajuste_hojas_x_pliego] Cantidad inválida.")
                return
            if not (
                can_hojas_tal.value
                and can_hojas_tal.value.isdigit()
                and int(can_hojas_tal.value) > 0
            ):
                # print("[ERROR aplicar_ajuste_hojas_x_pliego] Hojas por talonario inválidas.")
                return
            if (
                not hojas_x_pliego.value
                or not hojas_x_pliego.value.isdigit()
                or int(hojas_x_pliego.value) <= 0
            ):
                # print("[INFO aplicar_ajuste_hojas_x_pliego] hojas_x_pliego vacío o inválido, se asigna 1 automáticamente.")
                hojas_x_pliego.value = "1"
                hojas_x_pliego.update()

            cantidad_tal_val = int(cantidad.value)
            hojas_por_tal_val = int(can_hojas_tal.value)
            total_hojas_val = cantidad_tal_val * hojas_por_tal_val
            hojas_x_pliego_val = int(hojas_x_pliego.value)

            # Ajuste iterativo según la lógica propuesta
            while (
                total_hojas_val // hojas_x_pliego_val
            ) * hojas_x_pliego_val != total_hojas_val or (
                total_hojas_val // hojas_x_pliego_val
            ) % hojas_por_tal_val != 0:
                cantidad_tal_val += 1
                total_hojas_val += hojas_por_tal_val

            tirada_ajustada = total_hojas_val // hojas_x_pliego_val
            talonarios_ajustados = cantidad_tal_val
            total_hojas_ajustado = total_hojas_val

            resumen = t(
                "{0} Talonarios de {1} hojas = {2} hojas / {3} Hojas x pliego = {4} Tiradas"
            ).format(
                talonarios_ajustados,
                hojas_por_tal_val,
                total_hojas_ajustado,
                hojas_x_pliego_val,
                tirada_ajustada,
            )
            # print(f"[DEBUG aplicar_ajuste_hojas_x_pliego] cantidad: {cantidad_tal_val}, hojas_por_tal: {hojas_por_tal_val}, hojas_x_pliego: {hojas_x_pliego_val}, total_hojas: {total_hojas_ajustado}, tirada_ajustada: {tirada_ajustada}")
            tirada_calculada.value = str(tirada_ajustada)
            tirada_calculada.update()
            resumen_ajuste.value = resumen
            resumen_ajuste.update()
            bloque_resumen_.visible = True
            bloque_resumen_.update()
            # Guardar los valores ajustados en el diccionario global
            try:
                print(
                    {
                        "_debug": "aplicar_ajuste_hojas_x_pliego BEFORE assign",
                        "ajuste_activo": ajuste_activo,
                        "computed": {
                            "talonarios_ajustados": talonarios_ajustados,
                            "total_hojas_ajustado": total_hojas_ajustado,
                            "hojas_x_pliego_val": hojas_x_pliego_val,
                            "hojas_por_tal_val": hojas_por_tal_val,
                        },
                    }
                )
            except Exception:
                pass
            ajuste_activo["talonarios"] = str(talonarios_ajustados)
            ajuste_activo["total_hojas"] = str(total_hojas_ajustado)
            ajuste_activo["cantidad"] = str(talonarios_ajustados)
            ajuste_activo["hojas_por_tal"] = str(hojas_por_tal_val)
            ajuste_activo["hojas_x_pliego"] = str(hojas_x_pliego_val)
            try:
                print(
                    {
                        "_debug": "aplicar_ajuste_hojas_x_pliego AFTER assign",
                        "ajuste_activo": ajuste_activo,
                    }
                )
            except Exception:
                pass

            # También actualizar el campo UI 'tirada' (Total hojas) para que muestre el total ajustado
            try:
                tirada.value = str(total_hojas_ajustado)
                tirada.update()
            except Exception:
                pass
        except Exception as ex:
            # print(f"[ERROR aplicar_ajuste_hojas_x_pliego] {ex}")
            pass

    def on_hojas_x_pliego_change(e):
        # Validación estricta de Talonarios y Hojas por talonario antes de procesar cualquier dato
        val1 = cantidad.value
        val2 = can_hojas_tal.value
        if (
            not val1
            or not val1.isdigit()
            or int(val1) <= 0
            or not val2
            or not val2.isdigit()
            or int(val2) <= 0
        ):
            # Limpiar hojas_x_pliego
            hojas_x_pliego.value = ""
            hojas_x_pliego.update()
            # Detectar el campo inválido y poner el foco
            if (not val1 or not val1.isdigit() or int(val1) <= 0) and (
                not val2 or not val2.isdigit() or int(val2) <= 0
            ):
                mensaje = t(
                    "Los campos Talonarios y Hojas por talonario no pueden estar vacíos ni ser cero en on_hojas_x_pliego_change"
                )
            elif not val1 or not val1.isdigit() or int(val1) <= 0:
                mensaje = t("El campo Talonarios no puede estar vacío ni ser cero.")
            else:
                mensaje = t(
                    "El campo Hojas por talonario no puede estar vacío ni ser cero."
                )
            mostrar_snackbar(page, mensaje, SNACKBAR_COLOR_ERROR, 3000)
            if not val1 or not val1.isdigit() or int(val1) <= 0:
                _focus(cantidad)
            elif not val2 or not val2.isdigit() or int(val2) <= 0:
                _focus(can_hojas_tal)
            # Bloquear cualquier cálculo o actualización
            # Limpiar dropdowns y resumen
            horizontal_dropdown.options = [ft.dropdown.Option("")]
            horizontal_dropdown.value = ""
            horizontal_dropdown.update()
            vertical_value.value = ""
            vertical_value.update()
            tirada_calculada.value = ""
            tirada_calculada.update()
            resumen_ajuste.value = ""
            resumen_ajuste.update()
            grafico_viewer.visible = False
            grafico_viewer.update()
            return
        # Si los campos son válidos, procesar normalmente
        if (
            hojas_x_pliego.value
            and hojas_x_pliego.value.isdigit()
            and int(hojas_x_pliego.value) > 0
        ):
            opts = [
                ft.dropdown.Option(str(i)) for i in divisores(int(hojas_x_pliego.value))
            ]

            # Mantener el valor actual si existe en las nuevas opciones, sino usar el primero
            valor_actual = horizontal_dropdown.value
            opciones_disponibles = [opt.key for opt in opts]

            if valor_actual in opciones_disponibles:
                nuevo_valor = valor_actual
            else:
                nuevo_valor = opts[0].key if opts else "1"

            horizontal_dropdown.options = opts
            horizontal_dropdown.value = nuevo_valor
            horizontal_dropdown.update()
            horizontal_val = str(horizontal_dropdown.value or "1")
            hojas_x_pliego_val = str(hojas_x_pliego.value or "1")
            h = int(horizontal_val)
            v = int(hojas_x_pliego_val) // h if h != 0 else 0
            # print(f"[DEBUG on_hojas_x_pliego_change] h={h}, v={v}, hojas_x_pliego={hojas_x_pliego.value}, cantidad={cantidad.value}, can_hojas_tal={can_hojas_tal.value}")

            if h == 1 and v > 1:
                orientacion_dropdown.visible = False
                orientacion_dropdown.value = "Abajo"
                # print("primer if")

            elif h > 1 and v == 1:
                orientacion_dropdown.visible = False
                orientacion_dropdown.value = "Izquierda"
                # print("segundo if")

            elif h == 1 and v == 1:
                orientacion_dropdown.visible = False
                orientacion_dropdown.value = "Izquierda"
                # print("tercer if")

            elif h == v and h > 1:
                orientacion_dropdown.visible = True
                orientacion_dropdown.value = "Izquierda"
                # print("cuarto if")

            elif v > h or v < h and h or v != 1:
                orientacion_dropdown.visible = True
                orientacion_dropdown.value = "Izquierda"
                # print("quinto if")

            orientacion_dropdown.update()
            on_horizontal_change(None)

            # --- Mostrar resumen, botón PDF y trazado automáticamente ---
            aplicar_ajuste_hojas_x_pliego()
            # Marcar como modificado
            mark_modified()
            fase_2_fase_3_visible_on()
            bloque_resumen_.visible = True
            bloque_resumen_.update()
            boton_informe_container.disabled = False
            boton_informe_container.opacity = 1.0
            boton_informe_container.update()
            icono_ajuste_container.disabled = False
            icono_ajuste_container.opacity = 1.0
            if _en_pagina(icono_ajuste_container):
                icono_ajuste_container.update()
            icono_pdf_ordenado_container.disabled = False
            icono_pdf_ordenado_container.opacity = 1.0
            icono_pdf_ordenado_container.update()
            icono_imponer_container.disabled = False
            icono_imponer_container.opacity = 1.0
            icono_imponer_container.update()
            grafico_viewer.visible = True
            grafico_viewer.update()
            mostrar_trazado()
        else:
            # Si el valor es cero o inválido, ocultar el trazado, el botón PDF y resetear horizontal/vertical
            grafico_viewer.visible = False
            grafico_viewer.update()
            horizontal_dropdown.options = [ft.dropdown.Option("1")]
            horizontal_dropdown.value = "1"
            horizontal_dropdown.update()
            vertical_value.value = ""
            vertical_value.update()
            tirada_calculada.value = ""
            tirada_calculada.update()
            resumen_ajuste.value = ""
            resumen_ajuste.update()
            bloque_resumen_.visible = False
            bloque_resumen_.update()
            boton_informe_container.disabled = True
            boton_informe_container.opacity = 0.4
            boton_informe_container.update()
            icono_ajuste_container.disabled = True
            icono_ajuste_container.opacity = 0.4
            if _en_pagina(icono_ajuste_container):
                icono_ajuste_container.update()
            icono_pdf_ordenado_container.disabled = True
            icono_pdf_ordenado_container.opacity = 0.4
            icono_pdf_ordenado_container.update()
            icono_imponer_container.disabled = True
            icono_imponer_container.opacity = 0.4
            icono_imponer_container.update()
            fase_3_visible_off()

    hojas_x_pliego.on_change = on_hojas_x_pliego_change

    # --- FASE 1: Bloque izquierdo ---
    # La lista de opciones se muestra automáticamente si los valores son válidos
    # Fase 1 dividida en dos partes: superior (inputs) e inferior (resultados con scroll)
    columna_fase1 = crear_columna_fase1(
        cantidad, can_hojas_tal, tirada, opciones_montaje, page
    )

    opciones_montaje.visible = True

    # --- FASE 2: Bloque derecho ---
    columna_fase2 = crear_columna_fase2(hojas_x_pliego_container, tirada_calculada)

    # --- FASE 3: Bloque derecha de Fase 2 ---
    comienzo_numeracion = crear_textfield_comienzo_numeracion()

    # Evento para mostrar trazado al perder el foco en comienzo_numeracion si el botón ha sido pulsado y los campos están completos
    def on_comienzo_numeracion_blur(e):
        # Mostrar trazado automáticamente solo si los campos son válidos
        if cantidad.value and can_hojas_tal.value and hojas_x_pliego.value:
            # No marcar como modificado al perder foco; sólo mostrar trazado.
            # El estado 'modificado' lo actualiza el handler `on_change`.
            try:
                mostrar_trazado()
            except Exception:
                try:
                    mostrar_trazado()
                except Exception:
                    pass

    comienzo_numeracion.on_blur = on_comienzo_numeracion_blur

    def _on_comienzo_numeracion_change(e):
        mark_modified()
        try:
            update_impo_field("comienzo_numeracion", comienzo_numeracion.value)
        except Exception:
            pass
        # Actualizar el valor conocido tras un cambio real
        try:
            comienzo_numeracion._last_known_value = comienzo_numeracion.value
        except Exception:
            pass

    try:
        comienzo_numeracion.on_change = _on_comienzo_numeracion_change
    except Exception:
        pass

    def divisores(n):
        return [i for i in range(1, n + 1) if n % i == 0]

    def on_horizontal_change(e):
        # Lógica de orientación explicada:
        # 1. Si horizontal < vertical → orientación = "Abajo" (dropdown oculto)
        # 2. Si horizontal > vertical → orientación = "Izquierda" (dropdown oculto)
        # 3. Si horizontal == vertical → mostrar dropdown, valor inicial "Izquierda"
        if (
            hojas_x_pliego.value
            and hojas_x_pliego.value.isdigit()
            and horizontal_dropdown.value
        ):
            total = int(hojas_x_pliego.value)
            h = int(horizontal_dropdown.value)
            v = total // h if h != 0 else 0

            # Determinar si el dropdown de orientación debe ser visible
            if h == 1 and v > 1:
                orientacion_dropdown.visible = False
                orientacion_dropdown.value = "Abajo"
                # print("primer if")
            elif h > 1 and v == 1:
                orientacion_dropdown.visible = False
                orientacion_dropdown.value = "Izquierda"
                # print("segundo if")

            elif h == 1 and v == 1:
                orientacion_dropdown.visible = False
                orientacion_dropdown.value = "Izquierda"
                # print("tercer if")

            elif h == v and h > 1:
                orientacion_dropdown.visible = True
                orientacion_dropdown.value = "Izquierda"
                # print("cuarto if")

            elif v > h or v < h and h or v != 1:
                orientacion_dropdown.visible = True
                orientacion_dropdown.value = "Izquierda"
                # print("quinto if")

            orientacion_dropdown.update()
            vertical_value.value = str(v)
            vertical_value.update()
            # Marcar como modificado y persistir campos clave inmediatamente
            mark_modified()
            try:
                update_impo_field("horizontal", horizontal_dropdown.value)
                update_impo_field("vertical", vertical_value.value)
                update_impo_field("orientacion", orientacion_dropdown.value)
            except Exception:
                pass
            # print(f"[DEBUG VALORES] horizontal={h}, vertical={v}, orientacion={orientacion_dropdown.value}")
            # print(f"[DEBUG ORIENTACION DROPDOWN] Cambio a: {orientacion_dropdown.value}")
            mostrar_trazado()

    vertical_value = ft.TextField(
        label=t("Vertical"),
        value="",
        width=90,
        height=48,
        text_size=16,
        read_only=True,
        text_align=ft.TextAlign.LEFT,
        text_vertical_align=ft.VerticalAlignment.CENTER,
        content_padding=ft.Padding(8, 0, 0, 0),
        color=TEXTOS_FASE_2_COLOR,
        bgcolor=FONDO_TEXTFIELDS_COLOR,
        border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)),
        focused_color=None,
        focused_bgcolor=None,
        label_style=ft.TextStyle(color=TEXTOS_FASE_2_COLOR),
    )

    # Crear opciones iniciales y asegurar que value esté en las opciones
    hojas_x_pliego_text = str(hojas_x_pliego.value or "")
    hojas_x_pliego_base = (
        int(hojas_x_pliego_text)
        if hojas_x_pliego_text.isdigit() and int(hojas_x_pliego_text) > 0
        else 1
    )
    opciones_iniciales = [
        ft.dropdown.Option(str(i)) for i in divisores(hojas_x_pliego_base)
    ]
    valor_inicial = opciones_iniciales[0].key if opciones_iniciales else "1"

    horizontal_dropdown = ft.Dropdown(
        width=115,
        options=opciones_iniciales,
        value=valor_inicial,
        label=t("Horizontal"),
        filled=True,
        fill_color=FONDO_TEXTFIELDS_COLOR,
        color=DROPDOWN_TEXT_STYLE_COLOR,
        bgcolor=DROPDOWN_FONDO_MENU_COLOR,
        border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)),
        label_style=ft.TextStyle(color=DROPDOWN_TEXT_STYLE_COLOR),
        trailing_icon=ft.Icon(
            ft.Icons.ARROW_DROP_DOWN, color=DROPDOWN_TRAILING_ICON_COLOR
        ),
        selected_trailing_icon=ft.Icon(
            ft.Icons.ARROW_DROP_UP, color=DROPDOWN_TRAILING_ICON_COLOR
        ),
        on_select=lambda e: (
            on_horizontal_change(e),
            (
                mostrar_trazado()
                if (
                    cantidad.value
                    and hojas_x_pliego.value
                    and can_hojas_tal.value
                    and comienzo_numeracion.value
                )
                else None
            ),
        ),
    )

    orientacion_dropdown = ft.Dropdown(
        width=170,
        options=[
            ft.dropdown.Option("Izquierda", t("Izquierda")),
            ft.dropdown.Option("Abajo", t("Abajo")),
        ],
        value="Izquierda",
        label=t("Cortar y apilar"),
        filled=True,
        fill_color=FONDO_TEXTFIELDS_COLOR,
        color=DROPDOWN_TEXT_STYLE_COLOR,
        bgcolor=DROPDOWN_FONDO_MENU_COLOR,
        border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)),
        label_style=ft.TextStyle(color=DROPDOWN_TEXT_STYLE_COLOR),
        trailing_icon=ft.Icon(
            ft.Icons.ARROW_DROP_DOWN, color=DROPDOWN_TRAILING_ICON_COLOR
        ),
        selected_trailing_icon=ft.Icon(
            ft.Icons.ARROW_DROP_UP, color=DROPDOWN_TRAILING_ICON_COLOR
        ),
        on_select=lambda e: (
            # print(f"[DEBUG ORIENTACION on_select] Nuevo valor: {orientacion_dropdown.value}"),
            mark_modified(),
            mostrar_trazado(),
        ),
    )

    grafico_container = ft.Container(
        bgcolor=FONDO_GRAFICO_COLOR,
        alignment=ft.Alignment.CENTER,
    )

    # Sin InteractiveViewer: pan/zoom estaban deshabilitados y en Flet 1.0
    # no renderizaba el Canvas (solo se veía el bgcolor gris).
    grafico_viewer = ft.Container(
        visible=False,
        bgcolor=FONDO_APP,
        alignment=ft.Alignment.CENTER,
    )

    def mostrar_trazado():
        try:
            # VALIDACIÓN: Verificar que todos los campos obligatorios tengan valores válidos
            if not (
                cantidad.value and cantidad.value.isdigit() and int(cantidad.value) > 0
            ):
                print(
                    f"[TRAZADO] skip: cantidad={cantidad.value!r}"
                )
                return
            if not (
                can_hojas_tal.value
                and can_hojas_tal.value.isdigit()
                and int(can_hojas_tal.value) > 0
            ):
                print(
                    f"[TRAZADO] skip: can_hojas_tal={can_hojas_tal.value!r}"
                )
                return
            if not (
                hojas_x_pliego.value
                and hojas_x_pliego.value.isdigit()
                and int(hojas_x_pliego.value) > 0
            ):
                print(
                    f"[TRAZADO] skip: hojas_x_pliego={hojas_x_pliego.value!r}"
                )
                return
            if not (comienzo_numeracion.value and comienzo_numeracion.value.isdigit()):
                print(
                    f"[TRAZADO] skip: comienzo={comienzo_numeracion.value!r}"
                )
                return

            # Calcular dimensiones del viewport disponible
            ancho_ocupado_izquierda = 430
            alto_ocupado_superior = 220  # Aumentado para dar más espacio vertical

            viewport_width = max(
                600, int(page.width - ancho_ocupado_izquierda) if page.width else 800
            )
            viewport_height = max(
                400, int(page.height - alto_ocupado_superior) if page.height else 620
            )

            # Margen para que los bordes sean visibles - stroke_width=3 necesita espacio
            margen = 20  # 20px total para que se vean claramente los bordes rojos
            grafico_ancho = viewport_width - margen
            grafico_alto = viewport_height - margen

            if _PRINT_DEBUG:
                print(
                    f"[GRAFICO] Viewport: {viewport_width}x{viewport_height}px, Canvas: {grafico_ancho}x{grafico_alto}px"
                )

            # Obtener el estado actual
            estado_actual = {
                "cantidad": cantidad.value,
                "can_hojas_tal": can_hojas_tal.value,
                "hojas_x_pliego": hojas_x_pliego.value,
                "horizontal": horizontal_dropdown.value,
                "vertical": vertical_value.value,
                "orientacion": orientacion_dropdown.value,
                "comienzo_numeracion": comienzo_numeracion.value,
                # Añadir los valores ajustados para forzar el redibujo si cambian
                "ajuste_talonarios": ajuste_activo.get("talonarios", None),
                "ajuste_total_hojas": ajuste_activo.get("total_hojas", None),
                "ajuste_cantidad": ajuste_activo.get("cantidad", None),
                "ajuste_hojas_por_tal": ajuste_activo.get("hojas_por_tal", None),
                "ajuste_hojas_x_pliego": ajuste_activo.get("hojas_x_pliego", None),
                # AÑADIR DIMENSIONES DE PÁGINA PARA RESPONDER AL RESIZE
                "page_width": page.width,
                "page_height": page.height,
            }

            # Inicializar el estado anterior si no existe
            if not hasattr(mostrar_trazado, "_ultimo_estado"):
                mostrar_trazado._ultimo_estado = {}

            # Comparar el estado actual con el estado anterior
            # Solo saltar si el estado es igual Y el gráfico ya está visible
            if (
                estado_actual == mostrar_trazado._ultimo_estado
                and grafico_viewer.visible
            ):
                print("[TRAZADO] skip: estado sin cambios y ya visible")
                return

            # Actualizar el estado anterior
            mostrar_trazado._ultimo_estado = estado_actual.copy()

            # Usar los valores ajustados para el gráfico y la numeración
            h = int(horizontal_dropdown.value) if horizontal_dropdown.value else 1
            v = int(vertical_value.value) if vertical_value.value else 1
            if _PRINT_DEBUG:
                try:
                    print(
                        {
                            "_debug": "mostrar_trazado BEFORE safe conversions",
                            "ajuste_activo": ajuste_activo,
                            "cantidad.value": getattr(cantidad, "value", None),
                            "can_hojas_tal.value": getattr(
                                can_hojas_tal, "value", None
                            ),
                            "hojas_x_pliego.value": getattr(
                                hojas_x_pliego, "value", None
                            ),
                        }
                    )
                except Exception:
                    pass

            def _get_int_from_adjust(key, fallback_value):
                raw = ajuste_activo.get(key)
                if raw is None or (isinstance(raw, str) and str(raw).strip() == ""):
                    raw = fallback_value
                try:
                    return int(raw)
                except Exception:
                    try:
                        return int(fallback_value)
                    except Exception:
                        return 0

            cantidad_graf = _get_int_from_adjust("cantidad", cantidad.value)
            hojas_por_tal_graf = _get_int_from_adjust(
                "hojas_por_tal", can_hojas_tal.value
            )
            hojas_x_pliego_graf = _get_int_from_adjust(
                "hojas_x_pliego", hojas_x_pliego.value
            )
            total_hojas_graf = _get_int_from_adjust(
                "total_hojas", cantidad_graf * hojas_por_tal_graf
            )
# Para la numeración y el gráfico, usar los valores ajustados
            grafico = dibujar_grafico(
                horizontal=h,
                vertical=v,
                cantidad=cantidad_graf,
                can_hojas_tal=hojas_por_tal_graf,
                hojas_x_pliego=hojas_x_pliego_graf,
                comienzo_numeracion=int(comienzo_numeracion.value),
                orientacion=orientacion_dropdown.value,
                talonarios_calculados=cantidad_graf,
                talonarios_fase1=int(cantidad.value),
                ancho=grafico_ancho,
                alto=grafico_alto,
            )
            # Actualizar contenedor del gráfico
            import random

            grafico.key = f"canvas_{random.randint(0, 999999)}"

            # Canvas directo en el viewer (sin InteractiveViewer intermedio)
            grafico_container.content = grafico
            grafico_container.width = grafico_ancho
            grafico_container.height = grafico_alto
            grafico_viewer.content = grafico_container
            grafico_viewer.width = viewport_width
            grafico_viewer.height = viewport_height
            grafico_viewer.visible = True
            # page.update para asegurar que el subtree nuevo llegue al cliente
            try:
                page.update()
            except Exception:
                grafico_viewer.update()

            print(
                f"[TRAZADO] drawn: shapes={len(grafico.shapes)} "
                f"canvas={grafico_ancho}x{grafico_alto} "
                f"viewer={viewport_width}x{viewport_height} "
                f"visible={grafico_viewer.visible}"
            )

            if _PRINT_DEBUG:
                print(
                    f"[GRAFICO] Actualizado - Canvas: {grafico_ancho}x{grafico_alto}, Viewer: {viewport_width}x{viewport_height}"
                )
            # print(f"[DEBUG mostrar_trazado] Gráfico redibujado con estado: {estado_actual}")
        except Exception:
            logger.exception("Error en mostrar_trazado")
            grafico_viewer.visible = False
            grafico_viewer.update()

    def crear_pdf_desde_app():
        global grafico_datos
        # # print("\n================ [INICIO PROCESO PDF] Se ha pulsado el botón PDF ================\n")

        # Mostrar los datos que se enviarán a generar_pdf_informe
        print(
            f"[DEBUG crear_pdf_desde_app] Datos enviados a generar_pdf_informe: {grafico_datos}"
        )

        # Usar FilePicker para elegir la ruta y nombre del PDF
        from app_ui_items import crear_filepicker_guardar_pdf
        from informe_talonarios import generar_pdf_informe_mejorado

        def on_filepicker_result(ruta_pdf):
            # importar aquí para evitar dependencias circulares y usar funciones UI
            from app_ui_items import mostrar_alert_dialog, mostrar_snackbar

            # Si ruta_pdf tiene valor, intentar generar el PDF
            if ruta_pdf:
                try:
                    # <-- ADICIÓN: Validación de consistencia entre ordenamiento y metadata -->
                    try:
                        orden = grafico_datos.get("ordenamiento_pdf")
                        if isinstance(orden, dict):
                            meta = orden.get("_metadata", {})
                            esperado = meta.get("paginas_generadas")
                            # calcular páginas reales como suma de len(datos) para claves numéricas
                            reales = sum(
                                len(v.get("datos", []))
                                for k, v in orden.items()
                                if isinstance(k, int) and isinstance(v, dict)
                            )
                            print(
                                f"[DEBUG crear_pdf_desde_app] ordenamiento: entradas={len([k for k in orden.keys() if isinstance(k,int)])}, esperado={esperado}, reales={reales}"
                            )
                            if esperado is not None and reales != esperado:
                                msg = t(
                                    "Discrepancia en páginas: esperado={0}, reales={1}. Abortando generación."
                                ).format(esperado, reales)
                                # print(f"[ERROR] {msg}")
                                mostrar_snackbar(page, msg, SNACKBAR_COLOR_ERROR, 5000)
                                return
                    except Exception as _exval:
                        # print(f"[DEBUG crear_pdf_desde_app] fallo validación ordenamiento: {_exval}")
                        pass
                    # <-- FIN ADICIÓN -->

                    generar_pdf_informe_mejorado(
                        nombre_archivo=ruta_pdf, grafico_datos=grafico_datos
                    )
                    mostrar_alert_dialog(page, True, ruta_pdf)
                except Exception as ex:
                    # Si ocurre un error real al guardar, mostrar diálogo de error con detalles
                    mostrar_alert_dialog(page, False, error_msg=str(ex))
            else:
                # El usuario canceló la selección: no es un error, mostrar aviso breve
                mostrar_snackbar(
                    page, t("Creación de PDF cancelada."), SNACKBAR_COLOR_FONDO, 2000
                )

        crear_filepicker_guardar_pdf(page, on_filepicker_result)

    # ═══════════════════════════════════════════════════════════════════════════
    # SISTEMA DE GUARDAR/CARGAR ARCHIVOS DE TRABAJO
    # ═══════════════════════════════════════════════════════════════════════════

    # Variables de estado del proyecto
    project_name = t("Sin título")  # Nombre del proyecto actual
    current_project_path = None
    current_project_root = None
    project_modified = False
    # Bandera para suspender temporalmente mark_modified en el scope de la app
    _SUSPEND_MARK_MODIFIED_APP = False
    saved_state_snapshot = None
    pending_exit_after_save = False  # Bandera para cerrar app después de guardar
    closing_in_progress = False
    _close_watchdog_timer = None

    def _cerrar_app_con_dialogo():
        """Muestra el aviso final, limpia el estado temporal y cierra la ventana."""
        nonlocal closing_in_progress, _close_watchdog_timer
        if closing_in_progress:
            return
        closing_in_progress = True

        try:
            from shutdown_dialog import cerrar_dialogos_abiertos, mostrar_dialogo_cierre

            cerrar_dialogos_abiertos(page)
            mostrar_dialogo_cierre(page, t)
        except Exception:
            pass

        def _cancelar_watchdog_cierre():
            nonlocal _close_watchdog_timer
            try:
                if _close_watchdog_timer is not None:
                    _close_watchdog_timer.cancel()
            except Exception:
                pass
            _close_watchdog_timer = None

        def _activar_watchdog_cierre_windows(timeout_seg=2.0):
            nonlocal _close_watchdog_timer
            if not sys.platform.startswith("win"):
                return

            def _forzar_salida_por_timeout():
                try:
                    logger.warning(
                        "[WINDOW CLOSE] Timeout de cierre agotado, forzando salida del proceso en Windows"
                    )
                except Exception:
                    pass
                try:
                    os._exit(0)
                except Exception:
                    pass

            _cancelar_watchdog_cierre()
            try:
                timer = threading.Timer(timeout_seg, _forzar_salida_por_timeout)
                timer.daemon = True
                _close_watchdog_timer = timer
                timer.start()
            except Exception:
                pass

        async def _finalizar_cierre_async():
            try:
                # Ocultar la ventana primero evita la percepción de "No responde".
                page.window.visible = False
                page.update()
            except Exception:
                pass

            _activar_watchdog_cierre_windows(timeout_seg=2.0)

            try:
                # Ceder un ciclo al loop para que Flet procese el último update.
                await asyncio.sleep(0.05)
            except Exception:
                pass

            try:
                from state_cleanup import limpiar_todo_estado

                limpiar_todo_estado()
            except Exception:
                pass

            try:
                # Flet 1.0: Window.destroy() es async
                await page.window.destroy()
            except Exception:
                pass
            finally:
                _cancelar_watchdog_cierre()

        try:
            page.run_task(_finalizar_cierre_async)
        except Exception:
            # Fallback defensivo: si run_task fallara, mantener comportamiento de cierre.
            def _fallback_cierre():
                _activar_watchdog_cierre_windows(timeout_seg=2.0)
                try:
                    from state_cleanup import limpiar_todo_estado

                    limpiar_todo_estado()
                except Exception:
                    pass
                try:
                    # Flet 1.0: Window.destroy() es async → despachar al loop
                    page.run_task(page.window.destroy)
                except Exception:
                    pass
                finally:
                    _cancelar_watchdog_cierre()

            t_fallback = threading.Timer(0.05, _fallback_cierre)
            t_fallback.daemon = True
            t_fallback.start()

    def mark_modified():
        """Marca rápidamente que hubo un cambio (flag simple para eventos)"""
        nonlocal project_modified
        nonlocal _SUSPEND_MARK_MODIFIED_APP
        # Si la marcación está suspendida (p. ej. durante carga), evitar cambios.
        if _SUSPEND_MARK_MODIFIED_APP:
            print("[ESTADO_MODIFICACO] mark_modified ignorado (suspendido en app)")
            return
        if not project_modified:
            project_modified = True
            update_project_state_ui()
            try:
                import inspect

                caller = inspect.stack()[1]
                print(
                    f"[ESTADO_MODIFICACO] Proyecto marcado como modificado by {caller.filename}:{caller.lineno} in {caller.function}"
                )
            except Exception:
                print("[ESTADO_MODIFICACO] Proyecto marcado como modificado")
        # También marcar el flag persistente en el estado de imposición
        try:
            from impo_ui import (
                _estado_impo_ui as _estado_impo_ui_mod,
                guardar_estado_impo_ui,
            )

            try:
                _estado_impo_ui_mod["trabajo_modificado"] = True
                guardar_estado_impo_ui()
            except Exception:
                pass
        except Exception:
            pass

    def print_and_save_stamp():
        """Imprime el 'stamp' filtrado y, si es posible, fuerza guardar el estado
        llamando a `guardar_estado_impo_ui()` del módulo `impo_ui`.
        Diseñado para debugging "old-school": imprime y persiste inmediatamente.
        """
        # Intentar salvar el estado vía impo_ui (si está disponible) y mezclar
        stamp = None
        try:
            from impo_ui import (
                guardar_estado_impo_ui,
                _estado_impo_ui as _estado_impo_ui_mod,
            )

            try:
                # Al guardar, marcar trabajo_modificado=False
                try:
                    import inspect

                    caller = inspect.stack()[1]
                    print(
                        f"[APP TRACE WRITE] print_and_save_stamp called by {caller.filename}:{caller.lineno} -> setting trabajo_modificado=False"
                    )
                except Exception:
                    pass
                _estado_impo_ui_mod["trabajo_modificado"] = False
                guardar_estado_impo_ui()
            except Exception as e_save:
                print(f"[STAMP SAVE ERROR] {e_save}")
            try:
                stamp = dict(get_stamp_limpio(_estado_impo_ui_mod))
            except Exception:
                stamp = {}
            # Merge values from this UI (app.py) into the stamp for immediate visibility
            try:
                local_fields = {
                    "cantidad": getattr(cantidad, "value", ""),
                    "can_hojas_tal": getattr(can_hojas_tal, "value", ""),
                    "hojas_x_pliego": getattr(hojas_x_pliego, "value", ""),
                    "comienzo_numeracion": getattr(comienzo_numeracion, "value", ""),
                    "horizontal": getattr(horizontal_dropdown, "value", ""),
                    "vertical": getattr(vertical_value, "value", ""),
                    "orientacion": getattr(orientacion_dropdown, "value", ""),
                }
                # Update in-memory stamp and also try to persist into impo_ui's state
                stamp.update(local_fields)
                try:
                    import inspect

                    try:
                        caller = inspect.stack()[1]
                        print(
                            f"[APP TRACE WRITE] print_and_save_stamp merging local_fields from {caller.filename}:{caller.lineno} -> {local_fields}"
                        )
                    except Exception:
                        pass
                    _estado_impo_ui_mod.update(local_fields)
                except Exception:
                    pass
            except Exception:
                pass
        except Exception as e:
            # Si no se puede importar/guardar, generar stamp local desde globals
            try:
                base = globals().get("_estado_impo_ui", {}) or {}
                stamp = dict(get_stamp_limpio(base))
            except Exception:
                stamp = {}
            try:
                stamp.update(
                    {
                        "cantidad": getattr(cantidad, "value", ""),
                        "can_hojas_tal": getattr(can_hojas_tal, "value", ""),
                        "hojas_x_pliego": getattr(hojas_x_pliego, "value", ""),
                        "comienzo_numeracion": getattr(
                            comienzo_numeracion, "value", ""
                        ),
                        "horizontal": getattr(horizontal_dropdown, "value", ""),
                        "vertical": getattr(vertical_value, "value", ""),
                        "orientacion": getattr(orientacion_dropdown, "value", ""),
                    }
                )
            except Exception:
                pass
            print(f"[STAMP IMPORT ERROR] {e}")

        print("[STAMP]", stamp)

    def update_impo_field(key, value, persist=True):
        """Actualizar un campo en `_estado_impo_ui` y opcionalmente persistir inmediatamente.
        Diseñado para vigilar los textfields/dropdowns clave y mantener el stamp consistente.
        """
        try:
            from impo_ui import (
                _estado_impo_ui as _estado_impo_ui_mod,
                guardar_estado_impo_ui,
            )

            try:
                _estado_impo_ui_mod[key] = value
            except Exception:
                pass
            if persist:
                try:
                    guardar_estado_impo_ui()
                except Exception as e:
                    print(f"[UPDATE FIELD SAVE ERROR] {e}")
        except Exception:
            # Fallback: actualizar un estado local si existe
            try:
                globals().setdefault("_estado_impo_ui", {})
                globals()["_estado_impo_ui"][key] = value
            except Exception:
                pass
        # Imprimir el stamp actualizado para depuración
        try:
            print_and_save_stamp()
        except Exception:
            pass

    def has_unsaved_changes() -> bool:
        """Devuelve True si hay cambios pendientes de guardar en app o en impo_ui."""
        try:
            from impo_ui import _estado_impo_ui as _estado_impo_ui_mod

            return bool(
                project_modified or _estado_impo_ui_mod.get("trabajo_modificado", False)
            )
        except Exception:
            return bool(project_modified)

    # Redefinir el handler de ventana DESPUÉS de tener acceso a project_modified
    def _on_window_event_with_state(e):
        """Maneja eventos de ventana - verifica cambios antes de cerrar"""
        # Flet 1.0: el cierre llega en e.type (WindowEventType.CLOSE="close"), e.data es None
        _ev_type = getattr(getattr(e, "type", None), "value", getattr(e, "type", None))
        print(f"[WINDOW EVENT] type={_ev_type!r} data={getattr(e, 'data', None)!r}")
        if _ev_type == "close" or getattr(e, "data", None) == "close":
            nonlocal project_modified, current_project_path, pending_exit_after_save
            if closing_in_progress:
                return
            from color_design import (
                BOTONES_GENERICOS_FONDO_COLOR,
                BOTONES_GENERICOS_COLOR,
                BOTONES_GENERICOS_HOVER_COLOR,
                BOTONES_GENERICOS_OVERLAY_COLOR,
                FONDO_ALERT_DIALOG,
                TEXTOS_FASE_1_COLOR,
            )

            unsaved_changes = has_unsaved_changes()
            print(
                f"[WINDOW] Intento de cierre - project_modified={project_modified} unsaved_changes={unsaved_changes}"
            )

            if unsaved_changes:
                # Hay cambios sin guardar - mostrar diálogo completo
                def save_and_exit(e_btn):
                    """Guardar proyecto y cerrar aplicación"""
                    close_dialog()

                    if current_project_path:
                        # Ya tiene ruta, guardar directamente
                        try:
                            guardar_trabajo_app(None)
                            print("[WINDOW] Proyecto guardado, cerrando aplicación")
                            _cerrar_app_con_dialogo()
                        except Exception as ex:
                            print(f"[ERROR] Error al guardar: {ex}")
                            from app_ui_items import mostrar_snackbar

                            mostrar_snackbar(
                                page,
                                t("Error al guardar: {0}").format(str(ex)),
                                ft.Colors.RED,
                            )
                            return
                    else:
                        # No tiene ruta, abrir diálogo de guardar
                        print("[WINDOW] Abriendo diálogo para guardar antes de salir")
                        pending_exit_after_save = True
                        guardar_trabajo_app(None)

                def exit_without_saving(e_btn):
                    """Cerrar sin guardar cambios"""
                    close_dialog()
                    print("[WINDOW] Saliendo sin guardar cambios")
                    _cerrar_app_con_dialogo()

                def cancel_exit(e_btn):
                    """Cancelar salida, volver a la app"""
                    close_dialog()
                    print("[WINDOW] Salida cancelada")

                def close_dialog():
                    """Helper para cerrar el diálogo"""
                    try:
                        page.pop_dialog()
                    except Exception:
                        unsaved_dialog.open = False
                        page.update()

                # Crear diálogo
                unsaved_dialog = ft.AlertDialog(
                    modal=True,
                    title=ft.Container(
                        content=ft.Text(
                            t("⚠️ Cambios sin guardar"),
                            size=18,
                            weight=ft.FontWeight.BOLD,
                            color=ft.Colors.ORANGE,
                            text_align=ft.TextAlign.CENTER,
                        ),
                        alignment=ft.Alignment.CENTER,
                    ),
                    content=ft.Container(
                        content=ft.Column(
                            [
                                ft.Text(
                                    t("Tienes cambios sin guardar en el proyecto."),
                                    size=14,
                                    color=TEXTOS_FASE_1_COLOR,
                                    text_align=ft.TextAlign.CENTER,
                                ),
                                ft.Container(height=10),
                                ft.Text(
                                    t("¿Qué deseas hacer?"),
                                    size=13,
                                    color=TEXTOS_FASE_1_COLOR,
                                    text_align=ft.TextAlign.CENTER,
                                    weight=ft.FontWeight.BOLD,
                                ),
                            ],
                            spacing=5,
                            tight=True,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        width=400,
                        padding=20,
                    ),
                    actions=[
                        ft.Button(
                            t("Cancelar"),
                            on_click=cancel_exit,
                            width=120,
                            bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                            style=ft.ButtonStyle(
                                color={
                                    ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                                    ft.ControlState.HOVERED: BOTONES_GENERICOS_HOVER_COLOR,
                                },
                                overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                                padding=ft.Padding(0, 0, 0, 0),
                                shape=ft.RoundedRectangleBorder(radius=10),
                            ),
                        ),
                        ft.Button(
                            t("Salir sin guardar"),
                            on_click=exit_without_saving,
                            width=150,
                            bgcolor=ft.Colors.RED_700,
                            style=ft.ButtonStyle(
                                color={ft.ControlState.DEFAULT: ft.Colors.WHITE},
                                padding=ft.Padding(0, 0, 0, 0),
                                shape=ft.RoundedRectangleBorder(radius=10),
                            ),
                        ),
                        ft.Button(
                            t("Guardar y salir"),
                            on_click=save_and_exit,
                            width=140,
                            bgcolor=ft.Colors.GREEN_700,
                            style=ft.ButtonStyle(
                                color={ft.ControlState.DEFAULT: ft.Colors.WHITE},
                                padding=ft.Padding(0, 0, 0, 0),
                                shape=ft.RoundedRectangleBorder(radius=10),
                            ),
                        ),
                    ],
                    actions_alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    bgcolor=FONDO_ALERT_DIALOG,
                )

                page.show_dialog(unsaved_dialog)
            else:
                # No hay cambios - salir directamente
                print("[WINDOW] No hay cambios - cerrando directamente")
                _cerrar_app_con_dialogo()

    page.window.on_event = _on_window_event_with_state
    print("[WINDOW] Cierre con verificación de cambios activado.")

    def update_project_state_ui():
        """Actualiza el estado visual de iconos según estado del proyecto"""
        # Botón Guardar: preferir la bandera `trabajo_modificado` proveniente
        # del estado de imposición si existe, sino caer a `project_modified`.
        try:
            from impo_ui import _estado_impo_ui as _estado_impo_ui_mod

            # Considerar modificado si cualquiera de las dos banderas está a True
            trabajo_mod = bool(
                project_modified or _estado_impo_ui_mod.get("trabajo_modificado", False)
            )
        except Exception:
            trabajo_mod = project_modified

        # Debug: mostrar valores observados
        try:
            print(
                f"[APP UI ESTADO_MODIFICACO] update_project_state_ui called. project_modified={project_modified} impo_trabajo_modificado={_estado_impo_ui_mod.get('trabajo_modificado', False)} -> trabajo_mod={trabajo_mod}"
            )
        except Exception:
            print(
                f"[APP UI ESTADO_MODIFICACO] update_project_state_ui called. project_modified={project_modified} -> trabajo_mod={trabajo_mod}"
            )

        # Exponer el estado global del proyecto para otros módulos (p. ej. impo_ui)
        try:
            import builtins

            try:
                builtins._project_modified = bool(project_modified)
            except Exception:
                pass
        except Exception:
            pass

        # Aplicar color según la bandera calculada
        if trabajo_mod:
            print("[APP UI BUTTON COLOR] set ORANGE (trabajo_mod=True)")
            boton_guardar_trabajo.bgcolor = ft.Colors.ORANGE_700
            contenido_boton = getattr(boton_guardar_trabajo, "content", None)
            if contenido_boton is not None:
                contenido_boton.color = ft.Colors.WHITE
        else:
            from color_design import FONDO_TEXTFIELDS_COLOR, TEXTOS_FASE_1_COLOR

            print("[APP UI BUTTON COLOR] set NORMAL (trabajo_mod=False)")
            boton_guardar_trabajo.bgcolor = FONDO_TEXTFIELDS_COLOR
            contenido_boton = getattr(boton_guardar_trabajo, "content", None)
            if contenido_boton is not None:
                contenido_boton.color = TEXTOS_FASE_1_COLOR

        boton_guardar_trabajo.update()
        # Intentar forzar un redraw completo de la página por si el update
        # del control individual no fuera suficiente en algunos contextos.
        try:
            print(
                f"[APP UI DEBUG] boton_guardar_trabajo id={id(boton_guardar_trabajo)} page_exists={_en_pagina(boton_guardar_trabajo)}"
            )
            page.update()
        except Exception:
            pass

    # Registrar callback para que `impo_ui` pueda notificar cambios en
    # `trabajo_modificado` (siempre que la función exista en este scope).
    try:
        import builtins

        builtins._on_trabajo_modificado_change = update_project_state_ui
    except Exception:
        pass

    def salir_app(e):
        """Maneja el botón de salir - verifica cambios antes de cerrar"""
        nonlocal project_modified, current_project_path
        from color_design import (
            BOTONES_GENERICOS_FONDO_COLOR,
            BOTONES_GENERICOS_COLOR,
            BOTONES_GENERICOS_HOVER_COLOR,
            BOTONES_GENERICOS_OVERLAY_COLOR,
            FONDO_ALERT_DIALOG,
            TEXTOS_FASE_1_COLOR,
        )

        unsaved_changes = has_unsaved_changes()
        print(
            f"[EXIT] Botón salir presionado - project_modified={project_modified} unsaved_changes={unsaved_changes}"
        )

        if unsaved_changes:
            # Hay cambios sin guardar - mostrar diálogo completo
            def save_and_exit(e_btn):
                """Guardar proyecto y cerrar aplicación"""
                close_dialog()

                if current_project_path:
                    # Ya tiene ruta, guardar directamente
                    try:
                        guardar_trabajo_app(None)
                        print("[EXIT] Proyecto guardado, cerrando aplicación")
                        _cerrar_app_con_dialogo()
                    except Exception as ex:
                        print(f"[ERROR] Error al guardar: {ex}")
                        from app_ui_items import mostrar_snackbar

                        mostrar_snackbar(
                            page,
                            t("Error al guardar: {0}").format(str(ex)),
                            ft.Colors.RED,
                        )
                        return
                else:
                    # No tiene ruta, abrir diálogo de guardar
                    print("[EXIT] Abriendo diálogo para guardar antes de salir")
                    # Marcar que después de guardar hay que cerrar
                    nonlocal pending_exit_after_save
                    pending_exit_after_save = True
                    guardar_trabajo_app(None)

            def exit_without_saving(e_btn):
                """Cerrar sin guardar cambios"""
                close_dialog()
                print("[EXIT] Saliendo sin guardar cambios")
                _cerrar_app_con_dialogo()

            def cancel_exit(e_btn):
                """Cancelar salida, volver a la app"""
                close_dialog()
                print("[EXIT] Salida cancelada")

            def close_dialog():
                """Helper para cerrar el diálogo"""
                try:
                    page.pop_dialog()
                except Exception:
                    unsaved_dialog.open = False
                    page.update()

            # Crear diálogo
            unsaved_dialog = ft.AlertDialog(
                modal=True,
                title=ft.Container(
                    content=ft.Text(
                        t("⚠️ Cambios sin guardar"),
                        size=18,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.ORANGE,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    alignment=ft.Alignment.CENTER,
                ),
                content=ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(
                                t("Tienes cambios sin guardar en el proyecto."),
                                size=14,
                                color=TEXTOS_FASE_1_COLOR,
                                text_align=ft.TextAlign.CENTER,
                            ),
                            ft.Container(height=10),
                            ft.Text(
                                t("¿Qué deseas hacer?"),
                                size=13,
                                color=TEXTOS_FASE_1_COLOR,
                                text_align=ft.TextAlign.CENTER,
                                weight=ft.FontWeight.BOLD,
                            ),
                        ],
                        spacing=5,
                        tight=True,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    width=400,
                    padding=20,
                ),
                actions=[
                    ft.Button(
                        t("Cancelar"),
                        on_click=cancel_exit,
                        width=120,
                        bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                        style=ft.ButtonStyle(
                            color={
                                ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                                ft.ControlState.HOVERED: BOTONES_GENERICOS_HOVER_COLOR,
                            },
                            overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                            padding=ft.Padding(0, 0, 0, 0),
                            shape=ft.RoundedRectangleBorder(radius=10),
                        ),
                    ),
                    ft.Button(
                        t("Salir sin guardar"),
                        on_click=exit_without_saving,
                        width=150,
                        bgcolor=ft.Colors.RED_700,
                        style=ft.ButtonStyle(
                            color={ft.ControlState.DEFAULT: ft.Colors.WHITE},
                            padding=ft.Padding(0, 0, 0, 0),
                            shape=ft.RoundedRectangleBorder(radius=10),
                        ),
                    ),
                    ft.Button(
                        t("Guardar y salir"),
                        on_click=save_and_exit,
                        width=140,
                        bgcolor=ft.Colors.GREEN_700,
                        style=ft.ButtonStyle(
                            color={ft.ControlState.DEFAULT: ft.Colors.WHITE},
                            padding=ft.Padding(0, 0, 0, 0),
                            shape=ft.RoundedRectangleBorder(radius=10),
                        ),
                    ),
                ],
                actions_alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                bgcolor=FONDO_ALERT_DIALOG,
            )

            page.show_dialog(unsaved_dialog)
        else:
            # No hay cambios - salir directamente
            print("[EXIT] No hay cambios - cerrando directamente")
            _cerrar_app_con_dialogo()

    def nuevo_trabajo_app(e):
        """Crea un nuevo proyecto vacío 'Sin título'"""
        from app_ui_items import mostrar_snackbar

        print("[NEW] Creando proyecto nuevo 'Sin título'")

        # Limpiar todos los campos
        cantidad.value = ""
        can_hojas_tal.value = ""
        hojas_x_pliego.value = ""
        comienzo_numeracion.value = "1"
        tirada.value = ""
        tirada_calculada.value = ""

        # Resetear dropdowns
        horizontal_dropdown.value = ""
        vertical_value.value = ""
        orientacion_dropdown.value = "Izquierda"

        # Ocultar elementos de fases
        fase_2_fase_3_visible_off()

        # Limpiar contenido del gráfico para evitar mostrar datos antiguos
        grafico_container.content = None
        grafico_viewer.visible = False

        # Limpiar ajuste activo
        try:
            print(
                {
                    "_debug": "global_clear BEFORE",
                    "ajuste_activo": ajuste_activo,
                }
            )
        except Exception:
            pass
        ajuste_activo["talonarios"] = ""
        ajuste_activo["total_hojas"] = ""
        ajuste_activo["cantidad"] = ""
        ajuste_activo["hojas_por_tal"] = ""
        ajuste_activo["hojas_x_pliego"] = ""
        talonarios_ajustados_var["valor"] = ""
        try:
            print(
                {
                    "_debug": "global_clear AFTER",
                    "ajuste_activo": ajuste_activo,
                }
            )
        except Exception:
            pass

        # Limpiar todo el estado (PDF ordenado + imposición)
        try:
            from state_cleanup import limpiar_todo_estado

            limpiar_todo_estado()
            print("[NEW] Estado completo limpiado (wrapper)")
        except Exception as ex:
            print(f"[NEW] No se pudo ejecutar limpieza completa: {ex}")

        # Resetear estado del proyecto SOLO si realmente es un nuevo trabajo
        nonlocal project_name, current_project_path, project_modified, saved_state_snapshot
        project_name = t("Sin título")
        current_project_path = None
        project_modified = False  # Solo aquí, nunca al cerrar impo
        saved_state_snapshot = None

        # Actualizar título de ventana
        page.title = "TalNumStack - Sin título"

        # Actualizar color del botón guardar según nuevo estado
        update_project_state_ui()

        # Actualizar toda la página
        page.update()

        # Poner foco en primer campo
        _focus(cantidad)

        mostrar_snackbar(page, t("✓ Nuevo proyecto creado"), ft.Colors.GREEN_700, 2000)
        print("[NEW] Proyecto nuevo creado: 'Sin título'")

    def guardar_trabajo_app(e):
        """Guarda el trabajo actual en un archivo .tns (comprimido)"""
        from app_ui_items import mostrar_snackbar

        # Si ya tiene ruta guardada, guardar directamente
        if current_project_path:
            try:
                # Capturar datos de imposición si hay una activa
                imposicion_data = obtener_datos_imposicion_activa()

                trabajo_data = crear_datos_trabajo(
                    cantidad=cantidad.value or "",
                    can_hojas_tal=can_hojas_tal.value or "",
                    hojas_x_pliego=hojas_x_pliego.value or "",
                    comienzo_numeracion=comienzo_numeracion.value or "",
                    horizontal=horizontal_dropdown.value or "",
                    vertical=vertical_value.value or "",
                    orientacion=orientacion_dropdown.value or "",
                    grafico_datos=grafico_datos,
                    ajuste_activo=ajuste_activo,
                    imposicion_data=imposicion_data,
                    ajuste_pliego_modo=ajuste_pliego_modo["valor"],
                )

                success = guardar_trabajo_tns(trabajo_data, current_project_path)

                if success:
                    nonlocal saved_state_snapshot, project_modified, pending_exit_after_save
                    saved_state_snapshot = crear_snapshot_estado(
                        cantidad.value or "",
                        can_hojas_tal.value or "",
                        hojas_x_pliego.value or "",
                        comienzo_numeracion.value or "",
                        horizontal_dropdown.value or "",
                        vertical_value.value or "",
                        orientacion_dropdown.value or "",
                    )
                    project_modified = False
                    # También resetear la bandera de impo (`trabajo_modificado`) si existe
                    try:
                        from impo_ui import _estado_impo_ui as _estado_impo_ui_mod

                        _estado_impo_ui_mod["trabajo_modificado"] = False
                    except Exception:
                        pass

                    update_project_state_ui()
                    # Forzar notificación global a listeners (si existen)
                    try:
                        import builtins

                        cb = getattr(builtins, "_on_trabajo_modificado_change", None)
                        if callable(cb):
                            cb()
                        upd = getattr(builtins, "_update_project_state_ui", None)
                        if callable(upd):
                            upd()
                    except Exception:
                        pass

                    # Actualizar explícitamente la UI de impo usando la función expuesta en builtins
                    try:
                        import builtins

                        impo_upd = getattr(
                            builtins, "_impo_update_project_state_ui", None
                        )
                        if callable(impo_upd):
                            print(
                                "[SYNC IMPO UI] Llamando _impo_update_project_state_ui desde builtins"
                            )
                            impo_upd()
                        else:
                            print(
                                "[SYNC IMPO UI] _impo_update_project_state_ui no disponible en builtins"
                            )
                    except Exception as ex:
                        print(f"[SYNC IMPO UI] Error: {ex}")

                    mostrar_snackbar(
                        page,
                        t("✓ Trabajo guardado correctamente"),
                        ft.Colors.GREEN_700,
                        2000,
                    )

                    # Si se solicitó cerrar después de guardar
                    if pending_exit_after_save:
                        print("[EXIT] Guardado completo, cerrando aplicación")
                        _cerrar_app_con_dialogo()
                else:
                    mostrar_snackbar(
                        page,
                        t("Error al guardar el trabajo"),
                        SNACKBAR_COLOR_ERROR,
                        3000,
                    )
            except Exception as ex:
                print(f"[ERROR] Error al guardar: {ex}")
                mostrar_snackbar(
                    page, t("Error: {0}").format(str(ex)), SNACKBAR_COLOR_ERROR, 3000
                )
            return

        # Si no tiene ruta, abrir diálogo para elegir ubicación
        def on_save_file_result(e: ft.FilePickerResultEvent):
            from app_ui_items import mostrar_snackbar

            nonlocal current_project_path, saved_state_snapshot, project_modified, project_name, pending_exit_after_save, current_project_root

            if e.path:
                try:
                    # Capturar datos de imposición si hay una activa
                    imposicion_data = obtener_datos_imposicion_activa()

                    trabajo_data = crear_datos_trabajo(
                        cantidad=cantidad.value or "",
                        can_hojas_tal=can_hojas_tal.value or "",
                        hojas_x_pliego=hojas_x_pliego.value or "",
                        comienzo_numeracion=comienzo_numeracion.value or "",
                        horizontal=horizontal_dropdown.value or "",
                        vertical=vertical_value.value or "",
                        orientacion=orientacion_dropdown.value or "",
                        grafico_datos=grafico_datos,
                        ajuste_activo=ajuste_activo,
                        imposicion_data=imposicion_data,
                    )

                    # Sanear la ruta elegida: evitar nombres con doble extensión (.tns.tns)
                    chosen_path = e.path
                    try:
                        # Colapsar repeticiones como '.tns.tns' -> '.tns'
                        while chosen_path.lower().endswith(".tns.tns"):
                            chosen_path = chosen_path[:-4]
                        # Asegurar que termine en '.tns'
                        if not chosen_path.lower().endswith(".tns"):
                            chosen_path = chosen_path + ".tns"
                    except Exception:
                        pass

                    success = guardar_trabajo_tns(trabajo_data, chosen_path)

                    if success:
                        current_project_path = chosen_path
                        try:
                            current_project_root = os.path.dirname(chosen_path)
                        except Exception:
                            current_project_root = None
                        project_name = os.path.basename(chosen_path)

                        # Actualizar título de ventana (sin extensión)
                        name_without_ext = os.path.splitext(project_name)[0]
                        page.title = f"TalNumStack - {name_without_ext}"

                        saved_state_snapshot = crear_snapshot_estado(
                            cantidad.value or "",
                            can_hojas_tal.value or "",
                            hojas_x_pliego.value or "",
                            comienzo_numeracion.value or "",
                            horizontal_dropdown.value or "",
                            vertical_value.value or "",
                            orientacion_dropdown.value or "",
                        )
                        project_modified = False
                        # Resetear bandera de impo si existe
                        try:
                            from impo_ui import _estado_impo_ui as _estado_impo_ui_mod

                            _estado_impo_ui_mod["trabajo_modificado"] = False
                        except Exception:
                            pass

                        # Actualizar UI del estado del proyecto ahora que guardamos
                        try:
                            update_project_state_ui()
                        except Exception:
                            pass

                        # Re-aplicar preferencias de la aplicación al finalizar la carga.
                        # Algunos pasos de limpieza/restauración pueden haber reseteado
                        # controles UI; forzamos la relectura y aplicación de prefs.
                        try:
                            from talnum_preferences import get_preference

                            # Idioma
                            try:
                                lang_pref = get_preference("language", None)
                                if lang_pref:
                                    try:
                                        set_language(lang_pref)
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                            # Unidad de medida (solo presentación)
                            try:
                                unit_pref = get_preference("unit", None)
                                if unit_pref:
                                    try:
                                        import impo_ui

                                        if hasattr(impo_ui, "update_units_in_impo"):
                                            impo_ui.update_units_in_impo(unit_pref)
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                            # Tema (si aplica)
                            try:
                                theme_pref = get_preference(
                                    "theme", None
                                ) or get_preference("tema", None)
                                if theme_pref:
                                    try:
                                        from color_design import set_tema_manual

                                        # set_tema_manual espera dos argumentos (nombre y tema_flet opcional),
                                        # llamar con nombre y dejar que set_tema_manual calcule el modo.
                                        set_tema_manual(theme_pref, page.theme_mode)
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                        except Exception:
                            pass
                        # Forzar notificación global a listeners (si existen)
                        try:
                            import builtins

                            cb = getattr(
                                builtins, "_on_trabajo_modificado_change", None
                            )
                            if callable(cb):
                                cb()
                            upd = getattr(builtins, "_update_project_state_ui", None)
                            if callable(upd):
                                upd()
                        except Exception:
                            pass

                        # Actualizar explícitamente la UI de impo usando la función expuesta en builtins
                        try:
                            import builtins

                            impo_upd = getattr(
                                builtins, "_impo_update_project_state_ui", None
                            )
                            if callable(impo_upd):
                                print(
                                    "[SYNC IMPO UI] Llamando _impo_update_project_state_ui desde builtins"
                                )
                                impo_upd()
                            else:
                                print(
                                    "[SYNC IMPO UI] _impo_update_project_state_ui no disponible en builtins"
                                )
                        except Exception as ex:
                            print(f"[SYNC IMPO UI] Error: {ex}")

                        mostrar_snackbar(
                            page,
                            t("✓ Trabajo guardado correctamente"),
                            ft.Colors.GREEN_700,
                            2000,
                        )

                        # Si se solicitó cerrar después de guardar
                        if pending_exit_after_save:
                            print("[EXIT] Guardado completo, cerrando aplicación")
                            _cerrar_app_con_dialogo()
                    else:
                        mostrar_snackbar(
                            page,
                            t("Error al guardar el trabajo"),
                            SNACKBAR_COLOR_ERROR,
                            3000,
                        )
                except Exception as ex:
                    print(f"[ERROR] Error al guardar: {ex}")
                    mostrar_snackbar(
                        page,
                        t("Error: {0}").format(str(ex)),
                        SNACKBAR_COLOR_ERROR,
                        3000,
                    )
            else:
                print("[SAVE] Guardado cancelado por usuario")
                # Si el guardado venía de "Guardar y salir", cancelar el cierre pendiente
                pending_exit_after_save = False

        # Crear FilePicker para guardar (Flet 1.0: Service auto-registra; await + shim)
        save_picker = ft.FilePicker()
        update_project_state_ui()
        print("[SAVE] Abriendo diálogo para guardar trabajo")
        page.update()

        async def _do_save():
            try:
                path = await save_picker.save_file(
                    dialog_title=t("Guardar trabajo"),
                    file_name="sin titulo.tns",
                    allowed_extensions=["tns"],
                )
            except Exception as ex:
                print(f"[SAVE] Error save_file: {ex}")
                path = None
            on_save_file_result(SimpleNamespace(path=path, files=[]))

        page.run_task(_do_save)

    # --- Guardar Como: siempre abre el FilePicker para elegir ruta ---
    def guardar_como_app(e):
        from app_ui_items import mostrar_snackbar

        def on_save_file_result(e: ft.FilePickerResultEvent):
            if e.path:
                try:
                    # Capturar datos de imposición si hay una activa
                    imposicion_data = obtener_datos_imposicion_activa()

                    trabajo_data = crear_datos_trabajo(
                        cantidad=cantidad.value or "",
                        can_hojas_tal=can_hojas_tal.value or "",
                        hojas_x_pliego=hojas_x_pliego.value or "",
                        comienzo_numeracion=comienzo_numeracion.value or "",
                        horizontal=horizontal_dropdown.value or "",
                        vertical=vertical_value.value or "",
                        orientacion=orientacion_dropdown.value or "",
                        grafico_datos=grafico_datos,
                        ajuste_activo=ajuste_activo,
                        imposicion_data=imposicion_data,
                    )

                    success = guardar_trabajo_tns(trabajo_data, e.path)

                    if success:
                        nonlocal current_project_path, saved_state_snapshot, project_modified, project_name, current_project_root
                        current_project_path = e.path
                        try:
                            current_project_root = os.path.dirname(e.path)
                        except Exception:
                            current_project_root = None
                        project_name = os.path.basename(e.path)
                        # Actualizar título de ventana (sin extensión)
                        name_without_ext = os.path.splitext(project_name)[0]
                        page.title = f"TalNumStack - {name_without_ext}"

                        saved_state_snapshot = crear_snapshot_estado(
                            cantidad.value or "",
                            can_hojas_tal.value or "",
                            hojas_x_pliego.value or "",
                            comienzo_numeracion.value or "",
                            horizontal_dropdown.value or "",
                            vertical_value.value or "",
                            orientacion_dropdown.value or "",
                        )
                        project_modified = False
                        # Resetear bandera de impo si existe
                        try:
                            from impo_ui import _estado_impo_ui as _estado_impo_ui_mod

                            _estado_impo_ui_mod["trabajo_modificado"] = False
                        except Exception:
                            pass

                        try:
                            update_project_state_ui()
                        except Exception:
                            pass

                        mostrar_snackbar(
                            page,
                            t("✓ Trabajo guardado correctamente (Guardar como)"),
                            ft.Colors.GREEN_700,
                            2000,
                        )
                    else:
                        mostrar_snackbar(
                            page,
                            t("Error al guardar el trabajo"),
                            SNACKBAR_COLOR_ERROR,
                            3000,
                        )
                except Exception as ex:
                    print(f"[ERROR guardar_como_app] Error al guardar: {ex}")
                    mostrar_snackbar(
                        page,
                        t("Error: {0}").format(str(ex)),
                        SNACKBAR_COLOR_ERROR,
                        3000,
                    )
            else:
                print("[SAVE AS] Guardado cancelado por usuario")

        # Crear FilePicker para guardar (siempre; Flet 1.0: Service + await)
        save_picker = ft.FilePicker()
        update_project_state_ui()
        print("[SAVE AS] Abriendo diálogo Guardar como")
        page.update()

        # Construir nombre por defecto sin duplicar extensiones
        try:
            base_name = (
                os.path.splitext(project_name or "")[0]
                if project_name
                else "sin titulo"
            )
        except Exception:
            base_name = project_name or "sin titulo"

        async def _do_save_as():
            try:
                path = await save_picker.save_file(
                    dialog_title=t("Guardar trabajo como"),
                    file_name=(base_name or "sin titulo") + ".tns",
                    allowed_extensions=["tns"],
                )
            except Exception as ex:
                print(f"[SAVE AS] Error save_file: {ex}")
                path = None
            on_save_file_result(SimpleNamespace(path=path, files=[]))

        page.run_task(_do_save_as)

    # Actualizar icono_imponer para pasar guardar_trabajo_app
    from app_ui_items import mostrar_snackbar, abrir_pdf_ordenado_y_luego_imposicion

    def get_project_state():
        """Retorna el estado actual del proyecto"""
        return (project_modified, current_project_path, project_name)

    def on_imponer_click(e):
        grafico_datos_local = globals().get("grafico_datos")
        if not (
            isinstance(grafico_datos_local, dict)
            and "orden_grafico_visual" in grafico_datos_local
        ):
            mostrar_snackbar(
                e.page,
                t("Genere un gráfico antes de imponer páginas."),
                SNACKBAR_COLOR_ERROR,
                3500,
            )
        else:
            # PUNTO DE CONTROL: Imprimir estado del stamp (_estado_impo_ui) antes de imponer
            from impo_ui import _estado_impo_ui

            # if DEBUG_STAMP_APP:
            #     print("\n" + "=" * 60)
            #     print("[PUNTO DE CONTROL] Estado COMPLETO del stamp (_estado_impo_ui):")
            #     print("=" * 60)
            #     try:
            #         print(
            #             json.dumps(
            #                 get_stamp_limpio(_estado_impo_ui),
            #                 indent=2,
            #                 ensure_ascii=False,
            #                 default=str,
            #             )
            #         )
            #     except Exception:
            #         print(
            #             json.dumps(
            #                 _estado_impo_ui, indent=2, ensure_ascii=False, default=str
            #             )
            #         )
            #     print("=" * 60 + "\n")

            # COMPROBACIÓN: Si pdf_stamp es null, abrir diálogo normalmente (imposición nueva)
            if _estado_impo_ui.get("pdf_stamp") is None:
                print(
                    "[IMPONER] pdf_stamp es null → Abriendo diálogo para imposición NUEVA"
                )
            else:
                print(
                    f"[IMPONER] pdf_stamp existe: {_estado_impo_ui.get('pdf_stamp')} → Hay imposición previa"
                )

            modified, path, name = get_project_state()
            abrir_pdf_ordenado_y_luego_imposicion(
                e.page, guardar_trabajo_app, modified, path, name
            )

    icono_imponer.on_click = on_imponer_click

    def cargar_trabajo_app(e, _ruta_argv=None):
        """Carga un trabajo desde un archivo .tns (comprimido)"""
        from app_ui_items import mostrar_snackbar

        def on_load_file_result(e: ft.FilePickerResultEvent):
            nonlocal _SUSPEND_MARK_MODIFIED_APP
            if e.files and len(e.files) > 0:
                try:
                    file_path = e.files[0].path
                    # Limpiar estados previos antes de aplicar el trabajo cargado
                    try:
                        # Suspender marcación de cambios tanto en `impo_ui` como en `app` mientras aplicamos valores
                        try:
                            import impo_ui

                            impo_ui._SUSPEND_MARK_MODIFIED = True
                        except Exception:
                            pass
                        try:
                            _SUSPEND_MARK_MODIFIED_APP = True
                        except Exception:
                            pass

                        from state_cleanup import limpiar_todo_estado

                        limpiar_todo_estado()
                        try:
                            update_project_state_ui()
                        except Exception:
                            pass
                        print(
                            f"[LOAD] Estado previo limpiado antes de cargar: {file_path}"
                        )
                    except Exception as _ex:
                        print(f"[LOAD] No se pudo limpiar estado previo: {_ex}")

                    trabajo_data = cargar_trabajo_auto(file_path)

                    if trabajo_data and validar_trabajo_data(trabajo_data):
                        # Antes de aplicar los valores del archivo, leer y aplicar
                        # las preferencias de la aplicación para evitar que el
                        # archivo sobrescriba la configuración global.
                        try:
                            from talnum_preferences import get_preference

                            # Aplicar idioma (si existe)
                            lang_pref = get_preference("language", None)
                            if lang_pref:
                                try:
                                    set_language(lang_pref)
                                except Exception:
                                    pass
                            # Aplicar unidad de medida (si existe) — esto actualiza
                            # sólo la presentación; los cálculos internos siguen en mm.
                            unit_pref = get_preference("unit", None)
                            if unit_pref:
                                try:
                                    import impo_ui

                                    if hasattr(impo_ui, "update_units_in_impo"):
                                        impo_ui.update_units_in_impo(unit_pref)
                                except Exception:
                                    pass
                        except Exception:
                            pass

                        # Cargar datos en los controles (sin llamar a update todavía)
                        fase1 = trabajo_data.get("fase1", {})
                        fase2 = trabajo_data.get("fase2", {})
                        fase3 = trabajo_data.get("fase3", {})

                        # PUNTO DE CONTROL: Confirmar extracción de fases
                        # if DEBUG_STAMP_APP:
                        #     print("\n" + "=" * 80)
                        #     print("[PUNTO DE CONTROL] Datos extraídos del archivo:")
                        #     print("=" * 80)
                        #     print(
                        #         "FASE1:",
                        #         json.dumps(fase1, indent=2, ensure_ascii=False),
                        #     )
                        #     print(
                        #         "FASE2:",
                        #         json.dumps(fase2, indent=2, ensure_ascii=False),
                        #     )
                        #     print(
                        #         "FASE3:",
                        #         json.dumps(fase3, indent=2, ensure_ascii=False),
                        #     )
                        #     print(
                        #         "¿Existe 'generar_imposicion'?:",
                        #         "generar_imposicion" in trabajo_data,
                        #     )
                        #     print("=" * 80 + "\n")

                        # PASO 0: Restaurar modo de ajuste por pliego si existe en el archivo
                        modo_guardado = trabajo_data.get("ajuste_pliego_modo")
                        if modo_guardado in ("Auto", "Manual"):
                            ajuste_pliego_modo["valor"] = modo_guardado
                            print(
                                f"[LOAD PASO 0] Modo de ajuste restaurado: {modo_guardado}"
                            )
                            update_hojas_x_pliego_control()

                        # PASO 1: Cargar datos base (Fase 1 y Fase 2)
                        cantidad.value = fase1.get("cantidad", "")
                        can_hojas_tal.value = fase1.get("can_hojas_tal", "")
                        tirada.value = (
                            calcular_tirada(cantidad.value, can_hojas_tal.value)
                            if cantidad.value and can_hojas_tal.value
                            else ""
                        )
                        hojas_x_pliego.value = fase2.get("hojas_x_pliego", "")
                        print(
                            f"[LOAD PASO 1] Valores cargados - Cantidad:{cantidad.value}, CanHojasTal:{can_hojas_tal.value}, HojasXPliego:{hojas_x_pliego.value}"
                        )

                        # PASO 2: Sincronizar el dropdown de hojas_x_pliego ANTES de cargar horizontal/vertical
                        # CRÍTICO: Activar flag para evitar que update_hojas_x_pliego_control recalcule valores
                        update_hojas_x_pliego_control._skip_calculation = True
                        print(
                            f"[LOAD PASO 2] Antes de update_hojas_x_pliego_control - HojasXPliego:{hojas_x_pliego.value}"
                        )
                        update_hojas_x_pliego_control()
                        print(
                            f"[LOAD PASO 2] Después de update_hojas_x_pliego_control - HojasXPliego:{hojas_x_pliego.value}"
                        )
                        # Desactivar flag
                        update_hojas_x_pliego_control._skip_calculation = False

                        # PASO 3: Cargar valores de Fase 3 (horizontal, vertical, orientacion, comienzo_numeracion)
                        # Estos valores NO deben ser recalculados automáticamente
                        horizontal_guardado = fase3.get("horizontal", "")
                        vertical_guardado = fase3.get("vertical", "")

                        # CRÍTICO: Deshabilitar eventos on_change temporalmente para evitar recálculos
                        horizontal_on_select_original = horizontal_dropdown.on_select
                        orientacion_on_select_original = orientacion_dropdown.on_select
                        # También desactivar handlers de `comienzo_numeracion` para evitar mark_modified por blur/change
                        try:
                            comienzo_on_blur_original = comienzo_numeracion.on_blur
                        except Exception:
                            comienzo_on_blur_original = None
                        try:
                            comienzo_on_change_original = comienzo_numeracion.on_change
                        except Exception:
                            comienzo_on_change_original = None

                        horizontal_dropdown.on_select = None
                        orientacion_dropdown.on_select = None
                        try:
                            comienzo_numeracion.on_blur = None
                        except Exception:
                            pass
                        try:
                            comienzo_numeracion.on_change = None
                        except Exception:
                            pass
                        print(
                            f"[LOAD PASO 3] Eventos on_change deshabilitados - H_guardado:{horizontal_guardado}, V_guardado:{vertical_guardado}"
                        )

                        # Actualizar opciones de horizontal_dropdown basadas en hojas_x_pliego
                        if (
                            hojas_x_pliego.value
                            and hojas_x_pliego.value.isdigit()
                            and int(hojas_x_pliego.value) > 0
                        ):
                            print(
                                f"[LOAD PASO 3] HojasXPliego válido: {hojas_x_pliego.value}"
                            )
                            opts = [
                                ft.dropdown.Option(str(i))
                                for i in divisores(int(hojas_x_pliego.value))
                            ]
                            horizontal_dropdown.options = opts
                            opciones_disponibles = [opt.key for opt in opts]
                            print(
                                f"[LOAD PASO 3] Opciones H disponibles: {opciones_disponibles}"
                            )
                            # Usar el valor guardado si está en las opciones, sino usar el primero
                            if horizontal_guardado in opciones_disponibles:
                                horizontal_dropdown.value = horizontal_guardado
                                print(
                                    f"[LOAD PASO 3] H guardado '{horizontal_guardado}' está en opciones - asignado"
                                )
                            else:
                                horizontal_dropdown.value = opts[0].key if opts else "1"
                                print(
                                    f"[LOAD PASO 3] H guardado '{horizontal_guardado}' NO está en opciones - usando primero: {horizontal_dropdown.value}"
                                )
                        else:
                            horizontal_dropdown.value = horizontal_guardado
                            print(
                                f"[LOAD PASO 3] HojasXPliego NO válido - H asignado directamente: {horizontal_guardado}"
                            )

                        # Establecer vertical con el valor guardado (no recalcular)
                        vertical_value.value = vertical_guardado
                        print(
                            f"[LOAD PASO 3] Valores asignados - H:{horizontal_dropdown.value}, V:{vertical_value.value}"
                        )

                        # Establecer orientación y comienzo_numeracion
                        orientacion_dropdown.value = fase3.get(
                            "orientacion", "Izquierda"
                        )
                        comienzo_numeracion.value = fase3.get("comienzo_numeracion", "")
                        try:
                            comienzo_numeracion._last_known_value = (
                                comienzo_numeracion.value
                            )
                        except Exception:
                            pass
                        print(
                            f"[LOAD PASO 3] Orient:{orientacion_dropdown.value}, Comienzo:{comienzo_numeracion.value}"
                        )

                        # PASO 3.5: Aplicar lógica de visibilidad del dropdown de orientación
                        # Esta lógica determina si el dropdown debe mostrarse u ocultarse según los valores de H y V
                        if horizontal_dropdown.value and vertical_value.value:
                            try:
                                h = int(horizontal_dropdown.value)
                                v = int(vertical_value.value)

                                # Aplicar la misma lógica que en on_horizontal_change()
                                if h == 1 and v > 1:
                                    orientacion_dropdown.visible = False
                                    orientacion_dropdown.value = "Abajo"
                                    print(
                                        f"[LOAD PASO 3.5] H=1, V>1 → Orientación oculta, valor='Abajo'"
                                    )
                                elif h > 1 and v == 1:
                                    orientacion_dropdown.visible = False
                                    orientacion_dropdown.value = "Izquierda"
                                    print(
                                        f"[LOAD PASO 3.5] H>1, V=1 → Orientación oculta, valor='Izquierda'"
                                    )
                                elif h == 1 and v == 1:
                                    orientacion_dropdown.visible = False
                                    orientacion_dropdown.value = "Izquierda"
                                    print(
                                        f"[LOAD PASO 3.5] H=1, V=1 → Orientación oculta, valor='Izquierda'"
                                    )
                                elif h == v and h > 1:
                                    orientacion_dropdown.visible = True
                                    print(
                                        f"[LOAD PASO 3.5] H=V>1 → Orientación visible, mantener valor guardado"
                                    )
                                elif v > h or v < h and h or v != 1:
                                    orientacion_dropdown.visible = True
                                    print(
                                        f"[LOAD PASO 3.5] H≠V → Orientación visible, mantener valor guardado"
                                    )
                                else:
                                    orientacion_dropdown.visible = True
                                    print(
                                        f"[LOAD PASO 3.5] Caso por defecto → Orientación visible"
                                    )
                            except (ValueError, TypeError) as ex:
                                print(
                                    f"[LOAD PASO 3.5] Error al calcular visibilidad: {ex}"
                                )
                                orientacion_dropdown.visible = True
                        else:
                            print(
                                f"[LOAD PASO 3.5] H o V vacíos, orientación visible por defecto"
                            )
                            orientacion_dropdown.visible = True

                        # Restaurar eventos on_select y handlers de comienzo_numeracion
                        horizontal_dropdown.on_select = horizontal_on_select_original
                        orientacion_dropdown.on_select = orientacion_on_select_original
                        try:
                            comienzo_numeracion.on_blur = comienzo_on_blur_original
                        except Exception:
                            pass
                        try:
                            comienzo_numeracion.on_change = comienzo_on_change_original
                        except Exception:
                            pass
                        print(f"[LOAD PASO 3] Eventos on_select restaurados")
                        horizontal_dropdown.on_select = horizontal_on_select_original
                        orientacion_dropdown.on_select = orientacion_on_select_original

                        # PASO 4: Actualizar ajuste_activo si existe en los datos
                        if "ajustes" in trabajo_data:
                            try:
                                print(
                                    {
                                        "_debug": "load_trabajo BEFORE update",
                                        "ajuste_activo_before": ajuste_activo,
                                        "trabajo_data_ajustes": trabajo_data.get(
                                            "ajustes"
                                        ),
                                    }
                                )
                            except Exception:
                                pass
                            ajuste_activo.update(trabajo_data["ajustes"])
                            try:
                                print(
                                    {
                                        "_debug": "load_trabajo AFTER update",
                                        "ajuste_activo_after": ajuste_activo,
                                    }
                                )
                            except Exception:
                                pass

                        # PASO 5: Actualizar estado del proyecto
                        nonlocal current_project_path, saved_state_snapshot, project_modified, project_name, current_project_root
                        current_project_path = file_path
                        try:
                            current_project_root = os.path.dirname(file_path)
                        except Exception:
                            current_project_root = None
                        project_name = os.path.basename(file_path)

                        # Actualizar título de ventana (sin extensión)
                        name_without_ext = os.path.splitext(project_name)[0]
                        page.title = f"TalNumStack - {name_without_ext}"

                        saved_state_snapshot = crear_snapshot_estado(
                            cantidad.value or "",
                            can_hojas_tal.value or "",
                            hojas_x_pliego.value or "",
                            comienzo_numeracion.value or "",
                            horizontal_dropdown.value or "",
                            vertical_value.value or "",
                            orientacion_dropdown.value or "",
                        )
                        project_modified = False
                        update_project_state_ui()

                        # PASO 6: Aplicar ajuste y calcular tirada_calculada SIN recalcular horizontal/vertical
                        aplicar_ajuste_hojas_x_pliego()

                        # PASO 7: Actualizar lista de opciones de montaje (Fase 1)
                        opciones, total = calcular_opciones_montaje(
                            cantidad.value, can_hojas_tal.value
                        )
                        montajes = []
                        try:
                            for hxp in range(1, 51):
                                montajes.append(
                                    calcular_montaje_pro(
                                        cantidad.value, can_hojas_tal.value, hxp
                                    )
                                )
                        except Exception:
                            montajes = []
                        try:
                            filas_pro = generar_filas_opciones_montaje_pro(montajes)
                            opciones_montaje.controls = filas_pro
                        except Exception:
                            filas = generar_filas_opciones_montaje(opciones, total)
                            opciones_montaje.controls = filas

                        # PASO 8: Mostrar gráfico con los valores cargados - ESTO GENERA grafico_datos
                        mostrar_trazado()

                        # PASO 8.5: Actualizar stamp con valores de fase1/2/3
                        from impo_ui import _estado_impo_ui

                        _estado_impo_ui["cantidad"] = cantidad.value or ""
                        _estado_impo_ui["can_hojas_tal"] = can_hojas_tal.value or ""
                        _estado_impo_ui["hojas_x_pliego"] = hojas_x_pliego.value or ""
                        _estado_impo_ui["comienzo_numeracion"] = (
                            comienzo_numeracion.value or ""
                        )
                        _estado_impo_ui["horizontal"] = horizontal_dropdown.value or ""
                        _estado_impo_ui["vertical"] = vertical_value.value or ""
                        _estado_impo_ui["orientacion"] = (
                            orientacion_dropdown.value or "Izquierda"
                        )
                        try:
                            h = (
                                int(horizontal_dropdown.value)
                                if horizontal_dropdown.value
                                else 1
                            )
                            v = int(vertical_value.value) if vertical_value.value else 1
                            _estado_impo_ui["grid_cols"] = h
                            _estado_impo_ui["grid_rows"] = v
                            print(
                                f"[LOAD PASO 8.5] Stamp actualizado con datos de fase1/2/3 y grid: {h}x{v}"
                            )
                        except (ValueError, TypeError) as ex:
                            print(
                                f"[LOAD PASO 8.5] Error actualizando grid en stamp: {ex}"
                            )

                        # Copiar boxes del PDF si existen en el archivo cargado
                        archivo_sel = trabajo_data.get("generar_imposicion", {}).get(
                            "archivo_seleccionado", {}
                        )
                        if archivo_sel:
                            _estado_impo_ui["mediabox"] = archivo_sel.get("mediabox")
                            _estado_impo_ui["cropbox"] = archivo_sel.get("cropbox")
                            _estado_impo_ui["bleedbox"] = archivo_sel.get("bleedbox")

                        # PUNTO DE CONTROL: Imprimir stamp después de cargar fase1/2/3
                        # if DEBUG_STAMP_APP:
                        #     print("\n" + "=" * 80)
                        #     print(
                        #         "[PUNTO DE CONTROL] Estado del stamp DESPUÉS de cargar fase1/2/3:"
                        #     )
                        #     print("=" * 80)
                        #     print(
                        #         json.dumps(
                        #             get_stamp_limpio(_estado_impo_ui),
                        #             indent=2,
                        #             ensure_ascii=False,
                        #             default=str,
                        #         )
                        #     )
                        #     print("=" * 80 + "\n")

                        # PASO 9: VALIDACIÓN Y RESTAURACIÓN DE IMPOSICIÓN
                        imposicion_data = trabajo_data.get("generar_imposicion")

                        if not imposicion_data:
                            print(
                                "[LOAD PASO 9] No existe 'generar_imposicion' → Solo cálculo cargado"
                            )
                        else:
                            # wait dialog removed
                            print(
                                "[LOAD PASO 9] Existe 'generar_imposicion' → Validando PDF..."
                            )

                            # PASO 9.1: VALIDAR PDF ORIGINAL
                            archivo_sel = imposicion_data.get(
                                "archivo_seleccionado", {}
                            )
                            ruta_original = archivo_sel.get("ruta_original", "")
                            nombre_pdf = archivo_sel.get("nombre_archivo", "")
                            num_paginas_guardado = archivo_sel.get("num_paginas", 0)
                            paginas_requeridas_esperadas = imposicion_data.get(
                                "paginas_requeridas", num_paginas_guardado
                            )
                            mediabox_guardada = archivo_sel.get("mediabox")
                            cropbox_guardada = archivo_sel.get("cropbox")
                            bleedbox_guardada = archivo_sel.get("bleedbox")

                            validacion_pdf_ok = False
                            restoration_scheduled = False

                            # Helper: validar PDF en `ruta` y, si es válido, restaurar imposición.
                            def validate_pdf_and_restore(ruta):
                                nonlocal validacion_pdf_ok, restoration_scheduled
                                try:
                                    from pdf_manipulator import (
                                        contar_paginas_pdf,
                                        leer_cajas_pdf,
                                    )

                                    num_paginas_real, _ = contar_paginas_pdf(ruta)
                                    boxes_reales = leer_cajas_pdf(ruta, pagina=0)

                                    if boxes_reales:
                                        mediabox_real = boxes_reales.get("mediabox")
                                        cropbox_real = boxes_reales.get("cropbox")
                                        bleedbox_real = boxes_reales.get("bleedbox")

                                        # Compatibilidad principal: número de páginas requerido
                                        if (
                                            paginas_requeridas_esperadas
                                            and num_paginas_real
                                            != paginas_requeridas_esperadas
                                        ):
                                            print(
                                                f"[LOAD PASO 9.1] ❌ Páginas no coinciden: requeridas={paginas_requeridas_esperadas}, real={num_paginas_real}"
                                            )
                                            mostrar_snackbar(
                                                page,
                                                t(
                                                    "PDF incompatible ({0}→{1} págs). Imposición no cargada."
                                                ).format(
                                                    paginas_requeridas_esperadas,
                                                    num_paginas_real,
                                                ),
                                                SNACKBAR_COLOR_ERROR,
                                                4000,
                                            )
                                        # Si el tamaño cambió, avisar; no bloqueamos la carga si las páginas son compatibles.
                                        elif not boxes_coinciden(
                                            mediabox_guardada, mediabox_real
                                        ):
                                            print(
                                                "[LOAD PASO 9.1] ⚠️ MediaBox no coincide, se permite por compatibilidad de páginas"
                                            )
                                            mostrar_snackbar(
                                                page,
                                                t(
                                                    "PDF alternativo con tamaño diferente. Se mantiene la imposición cargada."
                                                ),
                                                SNACKBAR_COLOR_FONDO,
                                                3200,
                                            )
                                            validacion_pdf_ok = True
                                        else:
                                            print(
                                                f"[LOAD PASO 9.1] ✅ PDF válido: {num_paginas_real} págs, boxes OK"
                                            )
                                            validacion_pdf_ok = True
                                    else:
                                        print(
                                            f"[LOAD PASO 9.1] ❌ No se pudieron leer boxes del PDF"
                                        )
                                        mostrar_snackbar(
                                            page,
                                            t(
                                                "Error leyendo PDF. Imposición no cargada."
                                            ),
                                            SNACKBAR_COLOR_ERROR,
                                            4000,
                                        )
                                except Exception as ex:
                                    print(
                                        f"[LOAD PASO 9.1] ❌ Error validando PDF: {ex}"
                                    )
                                    import traceback

                                    traceback.print_exc()
                                    mostrar_snackbar(
                                        page,
                                        t(
                                            "Error validando PDF. Imposición no cargada."
                                        ),
                                        SNACKBAR_COLOR_ERROR,
                                        4000,
                                    )

                                # Si la validación fue correcta, restaurar imposición ahora.
                                if validacion_pdf_ok:
                                    # Ejecutar restauración en hilo de fondo para no bloquear la UI
                                    # wait dialog removed

                                    def _worker_restore():
                                        try:
                                            try:
                                                restaurar_datos_imposicion(
                                                    imposicion_data, file_path
                                                )
                                            except TypeError:
                                                restaurar_datos_imposicion(
                                                    imposicion_data
                                                )

                                            # Actualizar stamp con datos de imposición cargada
                                            try:
                                                from impo_ui import _estado_impo_ui

                                                _estado_impo_ui["pdf_nombre"] = (
                                                    nombre_pdf
                                                )
                                                _estado_impo_ui["pdf_ruta"] = ruta
                                                _estado_impo_ui["pdf_paginas"] = (
                                                    num_paginas_real
                                                )
                                                _estado_impo_ui[
                                                    "ordenamiento_paginas_requeridas"
                                                ] = imposicion_data.get(
                                                    "paginas_requeridas", 0
                                                )
                                                _estado_impo_ui["calles_list"] = (
                                                    imposicion_data.get("CALLES_L", [])
                                                )
                                                _estado_impo_ui["tamano_usuario_w"] = (
                                                    imposicion_data.get(
                                                        "TAMANO_USUARIO_W", 0.0
                                                    )
                                                )
                                                _estado_impo_ui["tamano_usuario_h"] = (
                                                    imposicion_data.get(
                                                        "TAMANO_USUARIO_H", 0.0
                                                    )
                                                )
                                                _estado_impo_ui["sangre"] = (
                                                    imposicion_data.get("SANGRE", 0.0)
                                                )
                                                _estado_impo_ui["mediabox"] = (
                                                    archivo_sel.get("mediabox")
                                                )
                                                _estado_impo_ui["cropbox"] = (
                                                    archivo_sel.get("cropbox")
                                                )
                                                _estado_impo_ui["bleedbox"] = (
                                                    archivo_sel.get("bleedbox")
                                                )
                                            except Exception:
                                                pass

                                            try:
                                                stat = os.stat(ruta)
                                                try:
                                                    from impo_ui import _estado_impo_ui

                                                    _estado_impo_ui["pdf_stamp"] = (
                                                        f"{stat.st_size}_{stat.st_mtime}"
                                                    )
                                                    print(
                                                        f"[LOAD PASO 9.2] Stamp actualizado con datos de imposición: {nombre_pdf}, stamp={_estado_impo_ui['pdf_stamp']}"
                                                    )
                                                except Exception:
                                                    pass
                                            except Exception as ex:
                                                print(
                                                    f"[LOAD PASO 9.2] ⚠️ No se pudo generar pdf_stamp: {ex}"
                                                )

                                            print(
                                                "[LOAD] Datos de imposición restaurados"
                                            )
                                            try:
                                                page.update()
                                            except Exception:
                                                pass
                                        finally:
                                            pass

                                    # Marcar que la restauración fue programada para evitar duplicados
                                    try:
                                        restoration_scheduled = True
                                    except Exception:
                                        pass
                                    threading.Thread(
                                        target=_worker_restore, daemon=True
                                    ).start()

                            # Intentar localizar el PDF: usar ruta_original si existe,
                            # si no existe intentar buscarlo junto al .tns (file_path).
                            ruta_alternativa = None
                            try:
                                if (
                                    not ruta_original
                                    or not os.path.exists(ruta_original)
                                ) and file_path:
                                    trabajo_dir = os.path.dirname(file_path)
                                    nombre_pdf_guardado = archivo_sel.get(
                                        "nombre_archivo"
                                    ) or archivo_sel.get("nombre")
                                    if nombre_pdf_guardado:
                                        # Probar varias variantes (con y sin extensión .pdf)
                                        candidates = [nombre_pdf_guardado]
                                        if not nombre_pdf_guardado.lower().endswith(
                                            ".pdf"
                                        ):
                                            candidates.append(
                                                f"{nombre_pdf_guardado}.pdf"
                                            )

                                        found = None
                                        for cand in candidates:
                                            posible = os.path.join(trabajo_dir, cand)
                                            if _PRINT_DEBUG:
                                                print(
                                                    f"[LOAD PASO 9.1] Comprobando posible PDF en: {posible}"
                                                )
                                            try:
                                                if os.path.exists(posible):
                                                    found = posible
                                                    break
                                            except Exception:
                                                # continuar con siguiente candidato
                                                pass

                                        if found:
                                            ruta_alternativa = found
                                            ruta_original = found
                                            print(
                                                f"[LOAD PASO 9.1] Ruta original no encontrada. Usando PDF desde carpeta del trabajo: {found}"
                                            )

                                            # *** SINCRONIZAR LA NUEVA RUTA A TODOS LOS MÓDULOS ***
                                            # Actualizar imposicion_data en memoria
                                            try:
                                                archivo_sel["ruta_original"] = found
                                                archivo_sel["nombre_archivo"] = (
                                                    os.path.basename(found)
                                                )
                                            except Exception:
                                                pass

                                            # impo_ui: actualizar estado y archivo_seleccionado
                                            try:
                                                import impo_ui

                                                try:
                                                    impo_ui._estado_impo_ui[
                                                        "pdf_ruta"
                                                    ] = found
                                                    impo_ui._estado_impo_ui[
                                                        "pdf_nombre"
                                                    ] = os.path.basename(found)
                                                except Exception:
                                                    pass
                                                try:
                                                    impo_ui._archivo_seleccionado[
                                                        "ruta"
                                                    ] = found
                                                    impo_ui._archivo_seleccionado[
                                                        "ruta_original"
                                                    ] = found
                                                    impo_ui._archivo_seleccionado[
                                                        "nombre"
                                                    ] = os.path.basename(found)
                                                except Exception:
                                                    pass
                                                print(
                                                    f"[LOAD PASO 9.1] impo_ui sincronizado con ruta alternativa: {found}"
                                                )
                                            except Exception as _ex_impo:
                                                print(
                                                    f"[LOAD PASO 9.1] Error sincronizando impo_ui: {_ex_impo}"
                                                )

                                            # pdf_ordenado_ui: forzar overwrite de sus globals
                                            try:
                                                import pdf_ordenado_ui

                                                try:
                                                    pdf_ordenado_ui.guardar_ruta_pdf_original(
                                                        found
                                                    )
                                                except Exception:
                                                    try:
                                                        pdf_ordenado_ui._RUTA_PDF_ORIGINAL = (
                                                            found
                                                        )
                                                    except Exception:
                                                        pass
                                                try:
                                                    pdf_ordenado_ui._archivo_seleccionado_pdf[
                                                        "ruta"
                                                    ] = found
                                                    pdf_ordenado_ui._archivo_seleccionado_pdf[
                                                        "ruta_original"
                                                    ] = found
                                                    pdf_ordenado_ui._archivo_seleccionado_pdf[
                                                        "nombre"
                                                    ] = os.path.basename(
                                                        found
                                                    )
                                                except Exception:
                                                    pass
                                                print(
                                                    f"[LOAD PASO 9.1] pdf_ordenado_ui sincronizado con ruta alternativa: {found}"
                                                )
                                            except Exception as _ex_pdford:
                                                print(
                                                    f"[LOAD PASO 9.1] Error sincronizando pdf_ordenado_ui: {_ex_pdford}"
                                                )

                                            # app_ui_items: sincronizar archivo_seleccionado
                                            try:
                                                import app_ui_items

                                                try:
                                                    app_ui_items.archivo_seleccionado[
                                                        "ruta"
                                                    ] = found
                                                    app_ui_items.archivo_seleccionado[
                                                        "nombre"
                                                    ] = os.path.basename(found)
                                                except Exception:
                                                    pass
                                                print(
                                                    f"[LOAD PASO 9.1] app_ui_items sincronizado con ruta alternativa: {found}"
                                                )
                                            except Exception:
                                                pass

                                            # Guardar SOLO la ruta_original en .tns y .json
                                            try:
                                                import json, gzip

                                                tns_path = file_path
                                                if (
                                                    tns_path
                                                    and os.path.isfile(tns_path)
                                                    and tns_path.lower().endswith(
                                                        ".tns"
                                                    )
                                                ):
                                                    # Leer .tns comprimido
                                                    with open(tns_path, "rb") as f:
                                                        work_data = json.loads(
                                                            gzip.decompress(
                                                                f.read()
                                                            ).decode("utf-8")
                                                        )

                                                    if (
                                                        "generar_imposicion"
                                                        in work_data
                                                        and "archivo_seleccionado"
                                                        in work_data[
                                                            "generar_imposicion"
                                                        ]
                                                    ):
                                                        work_data["generar_imposicion"][
                                                            "archivo_seleccionado"
                                                        ]["ruta_original"] = found

                                                        # Guardar .tns (comprimido)
                                                        json_str = json.dumps(
                                                            work_data,
                                                            indent=2,
                                                            ensure_ascii=False,
                                                        )
                                                        with open(tns_path, "wb") as f:
                                                            f.write(
                                                                gzip.compress(
                                                                    json_str.encode(
                                                                        "utf-8"
                                                                    )
                                                                )
                                                            )
                                                        print(
                                                            f"[LOAD PASO 9.1] Guardado ruta_original en .tns (auto): {found}"
                                                        )

                                                        # Guardar .json (debug) solo si está habilitado en trabajo_manager
                                                        try:
                                                            import trabajo_manager as tm

                                                            if getattr(
                                                                tm,
                                                                "WRITE_DEBUG_JSON",
                                                                False,
                                                            ):
                                                                json_path = (
                                                                    tns_path[:-4]
                                                                    + ".json"
                                                                )
                                                                with open(
                                                                    json_path,
                                                                    "w",
                                                                    encoding="utf-8",
                                                                ) as f:
                                                                    json.dump(
                                                                        work_data,
                                                                        f,
                                                                        indent=2,
                                                                        ensure_ascii=False,
                                                                    )
                                                                print(
                                                                    f"[LOAD PASO 9.1] Guardado ruta_original en .json (auto): {found}"
                                                                )
                                                        except Exception:
                                                            pass
                                            except Exception as _exj:
                                                print(
                                                    f"[LOAD PASO 9.1] Error guardando ruta en archivo de trabajo: {_exj}"
                                                )
                            except Exception as _ex:
                                print(
                                    f"[LOAD PASO 9.1] Error buscando alternativa en carpeta del trabajo: {_ex}"
                                )

                            # Solo avisar/solicitar el PDF si el trabajo guarda un nombre/ruta esperada
                            if (nombre_pdf or ruta_original) and (
                                not ruta_original or not os.path.exists(ruta_original)
                            ):
                                print(
                                    f"[LOAD PASO 9.1] ❌ PDF no existe en: {archivo_sel.get('ruta_original', '')} (alternativa usada: {ruta_alternativa})"
                                )
                                # Mostrar diálogo que permite al usuario seleccionar el PDF y copiarlo junto al trabajo
                                try:
                                    from impo_ui import mostrar_alert_dialog
                                except Exception:
                                    mostrar_alert_dialog = None

                                # Crear AlertDialog con opción de seleccionar PDF
                                def abrir_selector_pdf(e=None):
                                    nonlocal current_project_path, current_project_root
                                    # Usar helper centralizado para seleccionar un PDF y reenviar la ruta a la verificación
                                    try:
                                        from app_ui_items import (
                                            crear_filepicker_seleccionar_pdf,
                                        )

                                        def _on_selected(ruta_seleccionada):
                                            try:
                                                # Si el usuario canceló
                                                if not ruta_seleccionada:
                                                    print(
                                                        "[LOAD PASO 9.1] No se seleccionó archivo (cancelado)"
                                                    )
                                                    try:
                                                        page.show_dialog(dialog)
                                                    except Exception:
                                                        pass
                                                    return

                                                nombre_seleccionado = os.path.basename(
                                                    ruta_seleccionada
                                                )
                                                base_sel = os.path.splitext(
                                                    nombre_seleccionado or ""
                                                )[0]
                                                base_esperado = os.path.splitext(
                                                    nombre_pdf or ""
                                                )[0]

                                                # Permitimos nombre distinto si el PDF pasa validación técnica.
                                                if base_sel != base_esperado:
                                                    mostrar_snackbar(
                                                        page,
                                                        t(
                                                            "PDF con nombre distinto: {0}. Se validará por páginas y compatibilidad."
                                                        ).format(nombre_seleccionado),
                                                        SNACKBAR_COLOR_FONDO,
                                                        3000,
                                                    )
                                                    print(
                                                        f"[LOAD PASO 9.1] Nombre alternativo aceptado para validación: {nombre_seleccionado} (esperado {nombre_pdf})"
                                                    )

                                                # Determinar carpeta raíz del proyecto
                                                proj_root = current_project_root or (
                                                    os.path.dirname(
                                                        current_project_path
                                                    )
                                                    if current_project_path
                                                    else None
                                                )

                                                # Verificar si el archivo seleccionado está dentro de la carpeta del trabajo
                                                inside = False
                                                try:
                                                    if proj_root:
                                                        inside = os.path.commonpath(
                                                            [
                                                                os.path.abspath(
                                                                    proj_root
                                                                ),
                                                                os.path.abspath(
                                                                    ruta_seleccionada
                                                                ),
                                                            ]
                                                        ) == os.path.abspath(proj_root)
                                                except Exception:
                                                    try:
                                                        inside = (
                                                            os.path.abspath(
                                                                ruta_seleccionada
                                                            ).startswith(
                                                                os.path.abspath(
                                                                    proj_root
                                                                )
                                                            )
                                                            if proj_root
                                                            else False
                                                        )
                                                    except Exception:
                                                        inside = False

                                                def _apply_and_validate(destino_path):
                                                    # Actualizar in-memory imposicion_data
                                                    try:
                                                        if isinstance(
                                                            imposicion_data, dict
                                                        ):
                                                            archivo_p = imposicion_data.get(
                                                                "archivo_seleccionado",
                                                                {},
                                                            )
                                                            archivo_p[
                                                                "ruta_original"
                                                            ] = destino_path
                                                            archivo_p[
                                                                "nombre_archivo"
                                                            ] = os.path.basename(
                                                                destino_path
                                                            )
                                                            imposicion_data[
                                                                "archivo_seleccionado"
                                                            ] = archivo_p
                                                            print(
                                                                f"[LOAD PASO 9.1] imposicion_data actualizado con nueva ruta: {destino_path}"
                                                            )
                                                    except Exception as _exu:
                                                        print(
                                                            f"[LOAD PASO 9.1] Error actualizando imposicion_data: {_exu}"
                                                        )

                                                    # Guardar SOLO la ruta_original en .tns y .json
                                                    try:
                                                        import json, gzip

                                                        tns_path = current_project_path
                                                        if (
                                                            tns_path
                                                            and os.path.isfile(tns_path)
                                                            and tns_path.lower().endswith(
                                                                ".tns"
                                                            )
                                                        ):
                                                            # Leer .tns comprimido
                                                            with open(
                                                                tns_path, "rb"
                                                            ) as f:
                                                                work_data = json.loads(
                                                                    gzip.decompress(
                                                                        f.read()
                                                                    ).decode("utf-8")
                                                                )

                                                            if (
                                                                "generar_imposicion"
                                                                in work_data
                                                                and "archivo_seleccionado"
                                                                in work_data[
                                                                    "generar_imposicion"
                                                                ]
                                                            ):
                                                                work_data[
                                                                    "generar_imposicion"
                                                                ][
                                                                    "archivo_seleccionado"
                                                                ][
                                                                    "ruta_original"
                                                                ] = destino_path

                                                                # Guardar .tns (comprimido)
                                                                json_str = json.dumps(
                                                                    work_data,
                                                                    indent=2,
                                                                    ensure_ascii=False,
                                                                )
                                                                with open(
                                                                    tns_path, "wb"
                                                                ) as f:
                                                                    f.write(
                                                                        gzip.compress(
                                                                            json_str.encode(
                                                                                "utf-8"
                                                                            )
                                                                        )
                                                                    )
                                                                print(
                                                                    f"[LOAD PASO 9.1] Guardado ruta_original en .tns: {destino_path}"
                                                                )

                                                                # Guardar .json (debug) solo si está habilitado en trabajo_manager
                                                                try:
                                                                    import trabajo_manager as tm

                                                                    if getattr(
                                                                        tm,
                                                                        "WRITE_DEBUG_JSON",
                                                                        False,
                                                                    ):
                                                                        json_path = (
                                                                            tns_path[
                                                                                :-4
                                                                            ]
                                                                            + ".json"
                                                                        )
                                                                        with open(
                                                                            json_path,
                                                                            "w",
                                                                            encoding="utf-8",
                                                                        ) as f:
                                                                            json.dump(
                                                                                work_data,
                                                                                f,
                                                                                indent=2,
                                                                                ensure_ascii=False,
                                                                            )
                                                                        print(
                                                                            f"[LOAD PASO 9.1] Guardado ruta_original en .json: {destino_path}"
                                                                        )
                                                                except Exception:
                                                                    pass
                                                    except Exception as _exj:
                                                        print(
                                                            f"[LOAD PASO 9.1] Error guardando ruta en archivo de trabajo: {_exj}"
                                                        )

                                                    # Cerrar diálogo
                                                    try:
                                                        page.pop_dialog()
                                                    except Exception:
                                                        pass

                                                    # Validar y restaurar usando la nueva ruta
                                                    try:
                                                        validate_pdf_and_restore(
                                                            destino_path
                                                        )
                                                    except Exception as _exv:
                                                        print(
                                                            f"[LOAD PASO 9.1] Error validando tras actualizar ruta: {_exv}"
                                                        )

                                                    # Propagar la nueva ruta al estado de imposición y al módulo PDF ordenado
                                                    try:
                                                        # impo_ui: actualizar estado visible y el registro de archivo seleccionado
                                                        try:
                                                            import impo_ui

                                                            try:
                                                                impo_ui._estado_impo_ui[
                                                                    "pdf_ruta"
                                                                ] = destino_path
                                                                impo_ui._estado_impo_ui[
                                                                    "pdf_nombre"
                                                                ] = os.path.basename(
                                                                    destino_path
                                                                )
                                                            except Exception:
                                                                pass
                                                            try:
                                                                # actualizar _archivo_seleccionado mínimo
                                                                paginas_sync = imposicion_data.get(
                                                                    "archivo_seleccionado",
                                                                    {},
                                                                ).get(
                                                                    "num_paginas",
                                                                    imposicion_data.get(
                                                                        "archivo_seleccionado",
                                                                        {},
                                                                    ).get("paginas", 0),
                                                                )
                                                                impo_ui._archivo_seleccionado.clear()
                                                                impo_ui._archivo_seleccionado.update(
                                                                    {
                                                                        "ruta": destino_path,
                                                                        "ruta_original": destino_path,
                                                                        "nombre": os.path.basename(
                                                                            destino_path
                                                                        ),
                                                                        "num_paginas": paginas_sync,
                                                                        "paginas": paginas_sync,
                                                                    }
                                                                )
                                                            except Exception:
                                                                pass
                                                            # intentar llamar al guardado de estado si existe
                                                            try:
                                                                impo_ui.guardar_estado_impo_ui()
                                                            except Exception:
                                                                pass
                                                            print(
                                                                f"[LOAD PASO 9.1] Estado de imposición actualizado (pdf_ruta + _archivo_seleccionado) con: {destino_path}"
                                                            )
                                                        except Exception as _ex_imp:
                                                            print(
                                                                f"[LOAD PASO 9.1] No se pudo actualizar impo_ui: {_ex_imp}"
                                                            )

                                                        # pdf_ordenado_ui: forzar overwrite de sus globals
                                                        try:
                                                            import pdf_ordenado_ui

                                                            try:
                                                                # función preferida
                                                                pdf_ordenado_ui.guardar_ruta_pdf_original(
                                                                    destino_path
                                                                )
                                                            except Exception:
                                                                try:
                                                                    pdf_ordenado_ui._RUTA_PDF_ORIGINAL = (
                                                                        destino_path
                                                                    )
                                                                except Exception:
                                                                    pass
                                                            try:
                                                                # actualizar su estructura interna mínima si existe
                                                                paginas_sync = imposicion_data.get(
                                                                    "archivo_seleccionado",
                                                                    {},
                                                                ).get(
                                                                    "num_paginas",
                                                                    imposicion_data.get(
                                                                        "archivo_seleccionado",
                                                                        {},
                                                                    ).get("paginas", 0),
                                                                )
                                                                pdf_ordenado_ui._archivo_seleccionado_pdf.clear()
                                                                pdf_ordenado_ui._archivo_seleccionado_pdf.update(
                                                                    {
                                                                        "ruta": destino_path,
                                                                        "ruta_original": destino_path,
                                                                        "nombre": os.path.basename(
                                                                            destino_path
                                                                        ),
                                                                        "num_paginas": paginas_sync,
                                                                        "paginas": paginas_sync,
                                                                    }
                                                                )
                                                            except Exception:
                                                                pass
                                                            print(
                                                                f"[LOAD PASO 9.1] pdf_ordenado_ui actualizado con ruta: {destino_path}"
                                                            )
                                                        except Exception as _ex_pdford:
                                                            print(
                                                                f"[LOAD PASO 9.1] No se pudo actualizar pdf_ordenado_ui: {_ex_pdford}"
                                                            )

                                                        # app_ui_items: si existe una copia local de archivo_seleccionado, actualizarla también
                                                        try:
                                                            import app_ui_items

                                                            try:
                                                                paginas_sync = imposicion_data.get(
                                                                    "archivo_seleccionado",
                                                                    {},
                                                                ).get(
                                                                    "num_paginas",
                                                                    imposicion_data.get(
                                                                        "archivo_seleccionado",
                                                                        {},
                                                                    ).get("paginas", 0),
                                                                )
                                                                app_ui_items.archivo_seleccionado[
                                                                    "ruta"
                                                                ] = destino_path
                                                                app_ui_items.archivo_seleccionado[
                                                                    "nombre"
                                                                ] = os.path.basename(
                                                                    destino_path
                                                                )
                                                                app_ui_items.archivo_seleccionado[
                                                                    "paginas"
                                                                ] = paginas_sync
                                                            except Exception:
                                                                pass
                                                            print(
                                                                f"[LOAD PASO 9.1] app_ui_items.archivo_seleccionado sincronizado con: {destino_path}"
                                                            )
                                                        except Exception:
                                                            pass
                                                    except Exception as _exprop:
                                                        print(
                                                            f"[LOAD PASO 9.1] Error propagando ruta a módulos: {_exprop}"
                                                        )

                                                # Si ya está dentro del proyecto, no copiar; usar ruta tal cual
                                                if inside:
                                                    destino = ruta_seleccionada
                                                    print(
                                                        f"[LOAD PASO 9.1] Archivo seleccionado está dentro de la carpeta del trabajo: {destino}"
                                                    )
                                                    mostrar_snackbar(
                                                        page,
                                                        t(
                                                            "Usando PDF en carpeta del trabajo: {0}"
                                                        ).format(destino),
                                                        SNACKBAR_COLOR_FONDO,
                                                        2500,
                                                    )
                                                    _apply_and_validate(destino)
                                                    return

                                                # Si el archivo está fuera del proyecto y tenemos carpeta raíz, ofrecer copiar o usar
                                                if proj_root:
                                                    try:
                                                        # Dialogo de opciones: Copiar / Usar / Cancelar
                                                        def _on_copy(e_copy):
                                                            try:
                                                                page.pop_dialog()
                                                            except Exception:
                                                                pass
                                                            try:
                                                                trabajo_dir_local = (
                                                                    proj_root
                                                                )
                                                                destino = os.path.join(
                                                                    trabajo_dir_local,
                                                                    nombre_seleccionado,
                                                                )
                                                                import shutil

                                                                # Evitar copiar sobre sí mismo
                                                                try:
                                                                    src_norm = os.path.normcase(
                                                                        os.path.abspath(
                                                                            ruta_seleccionada
                                                                        )
                                                                    )
                                                                    dst_norm = os.path.normcase(
                                                                        os.path.abspath(
                                                                            destino
                                                                        )
                                                                    )
                                                                except Exception:
                                                                    src_norm = os.path.abspath(
                                                                        ruta_seleccionada
                                                                    )
                                                                    dst_norm = (
                                                                        os.path.abspath(
                                                                            destino
                                                                        )
                                                                    )

                                                                if src_norm != dst_norm:
                                                                    shutil.copy2(
                                                                        ruta_seleccionada,
                                                                        destino,
                                                                    )
                                                                    print(
                                                                        f"[LOAD PASO 9.1] Copiado PDF seleccionado a: {destino}"
                                                                    )
                                                                else:
                                                                    print(
                                                                        f"[LOAD PASO 9.1] Origen y destino iguales; no se copia: {destino}"
                                                                    )

                                                                _apply_and_validate(
                                                                    destino
                                                                )
                                                            except Exception as _excp:
                                                                print(
                                                                    f"[LOAD PASO 9.1] Error copiando archivo: {_excp}"
                                                                )
                                                                mostrar_snackbar(
                                                                    page,
                                                                    t(
                                                                        "Error copiando PDF seleccionado."
                                                                    ),
                                                                    SNACKBAR_COLOR_ERROR,
                                                                    4000,
                                                                )

                                                        def _on_use(e_use):
                                                            try:
                                                                page.pop_dialog()
                                                            except Exception:
                                                                pass
                                                            try:
                                                                # Usar ubicación externa sin copiar
                                                                destino = (
                                                                    ruta_seleccionada
                                                                )
                                                                _apply_and_validate(
                                                                    destino
                                                                )
                                                            except Exception as _exu2:
                                                                print(
                                                                    f"[LOAD PASO 9.1] Error usando ruta externa: {_exu2}"
                                                                )

                                                        def _on_cancel(e_cancel):
                                                            try:
                                                                page.pop_dialog()
                                                            except Exception:
                                                                pass
                                                            try:
                                                                page.show_dialog(dialog)
                                                            except Exception:
                                                                pass

                                                        opciones_dialog = ft.AlertDialog(
                                                            modal=True,
                                                            title=ft.Container(
                                                                content=ft.Text(
                                                                    t("Copiar PDF"),
                                                                    size=18,
                                                                    weight=ft.FontWeight.BOLD,
                                                                    color=ft.Colors.ORANGE,
                                                                    text_align=ft.TextAlign.CENTER,
                                                                ),
                                                                alignment=ft.Alignment.CENTER,
                                                            ),
                                                            content=ft.Container(
                                                                content=ft.Column(
                                                                    [
                                                                        ft.Text(
                                                                            t(
                                                                                "El PDF seleccionado está fuera de la carpeta del trabajo."
                                                                            ),
                                                                            size=14,
                                                                            color=TEXTOS_FASE_1_COLOR,
                                                                            text_align=ft.TextAlign.CENTER,
                                                                        ),
                                                                        ft.Container(
                                                                            height=8
                                                                        ),
                                                                        ft.Text(
                                                                            t(
                                                                                "¿Desea copiarlo a la carpeta del trabajo?"
                                                                            ),
                                                                            size=13,
                                                                            color=TEXTOS_FASE_1_COLOR,
                                                                            text_align=ft.TextAlign.CENTER,
                                                                            weight=ft.FontWeight.BOLD,
                                                                        ),
                                                                    ],
                                                                    spacing=6,
                                                                    tight=True,
                                                                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                                                ),
                                                                width=420,
                                                                padding=20,
                                                            ),
                                                            actions=[
                                                                ft.Button(
                                                                    t("Copiar"),
                                                                    on_click=_on_copy,
                                                                    width=120,
                                                                    bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                                                                    style=ft.ButtonStyle(
                                                                        color={
                                                                            ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                                                                            ft.ControlState.HOVERED: BOTONES_GENERICOS_HOVER_COLOR,
                                                                        },
                                                                        overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                                                                        padding=ft.Padding(
                                                                            0, 0, 0, 0
                                                                        ),
                                                                        shape=ft.RoundedRectangleBorder(
                                                                            radius=10
                                                                        ),
                                                                    ),
                                                                ),
                                                                ft.Button(
                                                                    t(
                                                                        "Usar ruta externa"
                                                                    ),
                                                                    on_click=_on_use,
                                                                    width=140,
                                                                    bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                                                                    style=ft.ButtonStyle(
                                                                        color={
                                                                            ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                                                                            ft.ControlState.HOVERED: BOTONES_GENERICOS_HOVER_COLOR,
                                                                        },
                                                                        overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                                                                        padding=ft.Padding(
                                                                            0, 0, 0, 0
                                                                        ),
                                                                        shape=ft.RoundedRectangleBorder(
                                                                            radius=10
                                                                        ),
                                                                    ),
                                                                ),
                                                                ft.Button(
                                                                    t("Cancelar"),
                                                                    on_click=_on_cancel,
                                                                    width=120,
                                                                    bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                                                                    style=ft.ButtonStyle(
                                                                        color={
                                                                            ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                                                                            ft.ControlState.HOVERED: BOTONES_GENERICOS_HOVER_COLOR,
                                                                        },
                                                                        overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                                                                        padding=ft.Padding(
                                                                            0, 0, 0, 0
                                                                        ),
                                                                        shape=ft.RoundedRectangleBorder(
                                                                            radius=10
                                                                        ),
                                                                    ),
                                                                ),
                                                            ],
                                                            actions_alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                                            bgcolor=FONDO_ALERT_DIALOG,
                                                        )
                                                        page.show_dialog(opciones_dialog)
                                                    except Exception as _exdlg:
                                                        print(
                                                            f"[LOAD PASO 9.1] Error mostrando diálogo de opciones: {_exdlg}"
                                                        )
                                                        # Como fallback, usar ruta externa
                                                        _apply_and_validate(
                                                            ruta_seleccionada
                                                        )
                                                    return

                                                # Si no hay carpeta raíz (proyecto no guardado), pedir guardar o usar sin copiar
                                                def _on_save_now(e_save):
                                                    nonlocal current_project_root
                                                    try:
                                                        # Llamar al guardado; esto abrirá el diálogo 'Guardar como' si es necesario
                                                        guardar_trabajo_app(None)
                                                        # Después de guardar, si ahora tenemos ruta, establecer root y copiar
                                                        new_path = current_project_path
                                                        if new_path:
                                                            try:
                                                                new_root = (
                                                                    os.path.dirname(
                                                                        new_path
                                                                    )
                                                                )
                                                                current_project_root = (
                                                                    new_root
                                                                )
                                                            except Exception:
                                                                current_project_root = (
                                                                    None
                                                                )
                                                        # Si ahora hay root, realizar copia como en _on_copy
                                                        if current_project_root:
                                                            trabajo_dir_local = (
                                                                current_project_root
                                                            )
                                                            destino = os.path.join(
                                                                trabajo_dir_local,
                                                                nombre_seleccionado,
                                                            )
                                                            import shutil

                                                            try:
                                                                src_norm = os.path.normcase(
                                                                    os.path.abspath(
                                                                        ruta_seleccionada
                                                                    )
                                                                )
                                                                dst_norm = (
                                                                    os.path.normcase(
                                                                        os.path.abspath(
                                                                            destino
                                                                        )
                                                                    )
                                                                )
                                                            except Exception:
                                                                src_norm = os.path.abspath(
                                                                    ruta_seleccionada
                                                                )
                                                                dst_norm = (
                                                                    os.path.abspath(
                                                                        destino
                                                                    )
                                                                )
                                                            try:
                                                                if src_norm != dst_norm:
                                                                    shutil.copy2(
                                                                        ruta_seleccionada,
                                                                        destino,
                                                                    )
                                                            except Exception as _excp2:
                                                                print(
                                                                    f"[LOAD PASO 9.1] Error copiando tras guardar: {_excp2}"
                                                                )
                                                            _apply_and_validate(destino)
                                                        else:
                                                            mostrar_snackbar(
                                                                page,
                                                                t(
                                                                    "No se pudo obtener carpeta del proyecto tras guardar."
                                                                ),
                                                                SNACKBAR_COLOR_ERROR,
                                                                4000,
                                                            )
                                                    except Exception as _ex_save:
                                                        print(
                                                            f"[LOAD PASO 9.1] Error en _on_save_now: {_ex_save}"
                                                        )

                                                def _on_use_nosave(e_usenosave):
                                                    try:
                                                        # Usar ruta externa sin copiar; no se guarda automáticamente porque no hay proyecto en disco
                                                        destino = ruta_seleccionada
                                                        _apply_and_validate(destino)
                                                        mostrar_snackbar(
                                                            page,
                                                            t(
                                                                "Usando PDF desde ubicación externa (no guardado en proyecto)."
                                                            ),
                                                            SNACKBAR_COLOR_FONDO,
                                                            4000,
                                                        )
                                                    except Exception as _exnu:
                                                        print(
                                                            f"[LOAD PASO 9.1] Error en usar sin guardar: {_exnu}"
                                                        )

                                                def _on_cancel_nosave(e_cancel2):
                                                    try:
                                                        page.show_dialog(dialog)
                                                    except Exception:
                                                        pass

                                                save_needed_dialog = ft.AlertDialog(
                                                    modal=True,
                                                    title=ft.Text(
                                                        t("Proyecto no guardado"),
                                                        weight=ft.FontWeight.BOLD,
                                                    ),
                                                    content=ft.Text(
                                                        t(
                                                            "El proyecto no está guardado. Para copiar el PDF necesitamos una carpeta del proyecto. ¿Desea guardar ahora?"
                                                        )
                                                    ),
                                                    actions=[
                                                        ft.Button(
                                                            t("Guardar y copiar"),
                                                            on_click=_on_save_now,
                                                            bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                                                        ),
                                                        ft.Button(
                                                            t("Usar sin copiar"),
                                                            on_click=_on_use_nosave,
                                                            bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                                                        ),
                                                        ft.Button(
                                                            t("Cancelar"),
                                                            on_click=_on_cancel_nosave,
                                                            bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                                                        ),
                                                    ],
                                                    actions_alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                                )
                                                page.show_dialog(save_needed_dialog)
                                            except Exception as ex:
                                                print(
                                                    f"[LOAD PASO 9.1] Error en callback _on_selected: {ex}"
                                                )
                                                try:
                                                    page.show_dialog(dialog)
                                                except Exception:
                                                    pass

                                        crear_filepicker_seleccionar_pdf(
                                            page,
                                            _on_selected,
                                            dialog_title="Seleccionar PDF faltante",
                                            allowed_extensions=["pdf"],
                                        )
                                    except Exception as _exfp:
                                        print(
                                            f"[LOAD PASO 9.1] Error abriendo selector de archivos (helper): {_exfp}"
                                        )
                                        mostrar_snackbar(
                                            page,
                                            t("Error abriendo selector de archivos"),
                                            SNACKBAR_COLOR_ERROR,
                                            3000,
                                        )

                                # Mostrar mensaje y ofrecer selector
                                try:
                                    # Usar diseño consistente de diálogos (mismos colores y estilos)
                                    from color_design import (
                                        BOTONES_GENERICOS_FONDO_COLOR,
                                        BOTONES_GENERICOS_COLOR,
                                        BOTONES_GENERICOS_HOVER_COLOR,
                                        BOTONES_GENERICOS_OVERLAY_COLOR,
                                        FONDO_ALERT_DIALOG,
                                        TEXTOS_FASE_1_COLOR,
                                    )

                                    def _close_and_open_picker(e):
                                        try:
                                            page.pop_dialog()
                                        except Exception:
                                            pass
                                        abrir_selector_pdf(e)

                                    dialog = ft.AlertDialog(
                                        modal=True,
                                        title=ft.Container(
                                            content=ft.Text(
                                                t("PDF no encontrado"),
                                                size=18,
                                                weight=ft.FontWeight.BOLD,
                                                color=ft.Colors.ORANGE,
                                                text_align=ft.TextAlign.CENTER,
                                            ),
                                            alignment=ft.Alignment.CENTER,
                                        ),
                                        content=ft.Container(
                                            content=ft.Column(
                                                [
                                                    ft.Text(
                                                        t(
                                                            "El PDF '{0}' no se encontró en la ruta guardada."
                                                        ).format(nombre_pdf),
                                                        size=14,
                                                        color=TEXTOS_FASE_1_COLOR,
                                                        text_align=ft.TextAlign.CENTER,
                                                    ),
                                                    ft.Container(height=8),
                                                    ft.Text(
                                                        t(
                                                            "¿Desea buscarlo ahora y copiarlo junto al trabajo?"
                                                        ),
                                                        size=13,
                                                        color=TEXTOS_FASE_1_COLOR,
                                                        text_align=ft.TextAlign.CENTER,
                                                        weight=ft.FontWeight.BOLD,
                                                    ),
                                                ],
                                                spacing=6,
                                                tight=True,
                                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                            ),
                                            width=420,
                                            padding=20,
                                        ),
                                        actions=[
                                            ft.Button(
                                                "Buscar PDF",
                                                on_click=_close_and_open_picker,
                                                width=140,
                                                bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                                                style=ft.ButtonStyle(
                                                    color={
                                                        ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                                                        ft.ControlState.HOVERED: BOTONES_GENERICOS_HOVER_COLOR,
                                                    },
                                                    overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                                                    padding=ft.Padding(0, 0, 0, 0),
                                                    shape=ft.RoundedRectangleBorder(
                                                        radius=10
                                                    ),
                                                ),
                                            ),
                                            ft.Button(
                                                t("Cancelar"),
                                                on_click=lambda e: page.pop_dialog(),
                                                width=120,
                                                bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                                                style=ft.ButtonStyle(
                                                    color={
                                                        ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                                                        ft.ControlState.HOVERED: BOTONES_GENERICOS_HOVER_COLOR,
                                                    },
                                                    overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                                                    padding=ft.Padding(0, 0, 0, 0),
                                                    shape=ft.RoundedRectangleBorder(
                                                        radius=10
                                                    ),
                                                ),
                                            ),
                                        ],
                                        actions_alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                        bgcolor=FONDO_ALERT_DIALOG,
                                    )
                                    page.show_dialog(dialog)
                                except Exception:
                                    # Fallback: solo snackbar
                                    mostrar_snackbar(
                                        page,
                                        t(
                                            "PDF '{0}' no encontrado. Imposición no cargada."
                                        ).format(nombre_pdf),
                                        SNACKBAR_COLOR_ERROR,
                                        4000,
                                    )
                            else:
                                print(f"[LOAD PASO 9.1] ✅ PDF existe: {ruta_original}")
                                # Validar y restaurar inmediatamente
                                validate_pdf_and_restore(ruta_original)

                            # PASO 9.2: Si PDF válido, restaurar imposición
                            # Evitar restaurar doble: si ya programamos la restauración en el worker,
                            # no ejecutar la versión síncrona; la restauración asíncrona actualizará el estado.
                            if validacion_pdf_ok and not restoration_scheduled:
                                print(
                                    "[LOAD PASO 9.2] PDF validado → Restaurando imposición..."
                                )
                                # wait dialog removed
                                try:
                                    restaurar_datos_imposicion(
                                        imposicion_data, file_path
                                    )
                                except TypeError:
                                    # Compatibilidad: si la función no acepta trabajo_path
                                    restaurar_datos_imposicion(imposicion_data)

                                # (Eliminado: la actualización de checkboxes se hará tras crear la ventana de imposición)

                                # Actualizar stamp con datos de imposición cargada
                                from impo_ui import _estado_impo_ui

                                _estado_impo_ui["pdf_nombre"] = nombre_pdf
                                _estado_impo_ui["pdf_ruta"] = ruta_original
                                _estado_impo_ui["pdf_paginas"] = num_paginas_guardado
                                _estado_impo_ui["ordenamiento_paginas_requeridas"] = (
                                    imposicion_data.get("paginas_requeridas", 0)
                                )
                                _estado_impo_ui["calles_list"] = imposicion_data.get(
                                    "CALLES_L", []
                                )
                                _estado_impo_ui["tamano_usuario_w"] = (
                                    imposicion_data.get("TAMANO_USUARIO_W", 0.0)
                                )
                                _estado_impo_ui["tamano_usuario_h"] = (
                                    imposicion_data.get("TAMANO_USUARIO_H", 0.0)
                                )
                                _estado_impo_ui["sangre"] = imposicion_data.get(
                                    "SANGRE", 0.0
                                )
                                # Añadir boxes principales al estado
                                _estado_impo_ui["mediabox"] = archivo_sel.get(
                                    "mediabox"
                                )
                                _estado_impo_ui["cropbox"] = archivo_sel.get("cropbox")
                                _estado_impo_ui["bleedbox"] = archivo_sel.get(
                                    "bleedbox"
                                )

                                # Generar pdf_stamp (tamaño + timestamp modificación)
                                try:
                                    stat = os.stat(ruta_original)
                                    _estado_impo_ui["pdf_stamp"] = (
                                        f"{stat.st_size}_{stat.st_mtime}"
                                    )
                                    print(
                                        f"[LOAD PASO 9.2] Stamp actualizado con datos de imposición: {nombre_pdf}, stamp={_estado_impo_ui['pdf_stamp']}"
                                    )
                                except Exception as ex:
                                    print(
                                        f"[LOAD PASO 9.2] ⚠️ No se pudo generar pdf_stamp: {ex}"
                                    )

                                print("[LOAD] Datos de imposición restaurados")
                                # wait dialog removed
                            else:
                                print(
                                    "[LOAD PASO 9.2] PDF inválido → Imposición NO restaurada"
                                )

                        # PUNTO DE CONTROL FINAL: Imprimir stamp después de cargar TODO
                        from impo_ui import _estado_impo_ui

                        # if DEBUG_STAMP_APP:
                        #     print("\n" + "=" * 80)
                        #     print(
                        #         "[PUNTO DE CONTROL FINAL] Estado del stamp DESPUÉS de cargar TODO:"
                        #     )
                        #     print("=" * 80)
                        #     print(
                        #         json.dumps(
                        #             _estado_impo_ui,
                        #             indent=2,
                        #             ensure_ascii=False,
                        #             default=str,
                        #         )
                        #     )
                        #     print("=" * 80 + "\n")
                        # Forzar reseteo de banderas de modificación que pudieron dispararse durante la carga
                        try:
                            _estado_impo_ui["trabajo_modificado"] = False
                        except Exception:
                            pass
                        try:
                            # también resetear el flag del app (nonlocal)
                            project_modified = False
                        except Exception:
                            pass
                        try:
                            # Reactivar mark_modified en impo_ui
                            import impo_ui

                            impo_ui._SUSPEND_MARK_MODIFIED = False
                        except Exception:
                            pass
                        try:
                            _SUSPEND_MARK_MODIFIED_APP = False
                        except Exception:
                            pass
                        try:
                            update_project_state_ui()
                        except Exception:
                            pass

                        # PASO 10: Habilitar iconos de menú y mostrar elementos
                        if (
                            hojas_x_pliego.value
                            and hojas_x_pliego.value.isdigit()
                            and int(hojas_x_pliego.value) > 0
                        ):
                            fase_2_fase_3_visible_on()
                            boton_informe_container.disabled = False
                            boton_informe_container.opacity = 1.0
                            boton_informe_container.update()
                            icono_ajuste_container.disabled = False
                            icono_ajuste_container.opacity = 1.0
                            if _en_pagina(icono_ajuste_container):
                                icono_ajuste_container.update()
                            icono_pdf_ordenado_container.disabled = False
                            icono_pdf_ordenado_container.opacity = 1.0
                            icono_pdf_ordenado_container.update()
                            icono_imponer_container.disabled = False
                            icono_imponer_container.opacity = 1.0
                            icono_imponer_container.update()
                            bloque_resumen_.visible = True
                            bloque_resumen_.update()
                            grafico_viewer.visible = True
                            grafico_viewer.update()

                        # Forzar actualización de la página completa al final
                        page.update()

                        mostrar_snackbar(
                            page,
                            t("✓ Trabajo cargado correctamente"),
                            ft.Colors.GREEN_700,
                            2000,
                        )
                        print(
                            f"[LOAD] Valores cargados - H:{horizontal_dropdown.value}, V:{vertical_value.value}, Orient:{orientacion_dropdown.value}"
                        )
                    else:
                        mostrar_snackbar(
                            page,
                            t("Error: Archivo de trabajo inválido"),
                            SNACKBAR_COLOR_ERROR,
                            3000,
                        )
                except Exception as ex:
                    print(f"[ERROR] Error al cargar: {ex}")
                    import traceback

                    traceback.print_exc()
                    mostrar_snackbar(
                        page,
                        t("Error: {0}").format(str(ex)),
                        SNACKBAR_COLOR_ERROR,
                        3000,
                    )
            else:
                print("[LOAD] Carga cancelada por usuario")

        # Crear FilePicker para cargar (Flet 1.0: Service + await)
        load_picker = ft.FilePicker()
        page.update()

        # Apertura por doble clic (.tns asociado en el SO -> sys.argv[1]): reutiliza
        # el mismo resultado que el picker, sin abrir el diálogo (mismo shim SimpleNamespace)
        if _ruta_argv:
            on_load_file_result(
                SimpleNamespace(
                    files=[SimpleNamespace(path=_ruta_argv)],
                    path=_ruta_argv,
                )
            )
            return

        async def _do_load():
            try:
                files = await load_picker.pick_files(
                    dialog_title="Abrir trabajo",
                    allowed_extensions=["tns"],
                    allow_multiple=False,
                )
            except Exception as ex:
                print(f"[LOAD] Error pick_files: {ex}")
                files = []
            on_load_file_result(
                SimpleNamespace(
                    files=files or [],
                    path=(files[0].path if files else None),
                )
            )

        page.run_task(_do_load)

    bloque_fase3 = crear_bloque_fase3(
        comienzo_numeracion, horizontal_dropdown, vertical_value, orientacion_dropdown
    )

    # aplicar_ajuste_hojas_x_pliego()
    # grafico_viewer vive SOLO en crear_contenedor_principal (expand=True);
    # no meterlo también en columna_fase3 (doble padre → trazado no montado)
    columna_fase3 = crear_columna_fase3(bloque_fase3)

    # Bloque (menú superior + Fase 1 | Fase 2+3 agrupadas)
    # Inicializar el contenido del contenedor ANTES de añadir la UI
    hojas_x_pliego_container.content = get_hojas_x_pliego_control()

    # Crear el botón PDF (ahora es un IconButton directamente)
    boton_informe_pdf = crear_boton_pdf(lambda e: crear_pdf_desde_app())

    # Crear barra lateral izquierda con iconos (diseño PageNumber)
    (
        barra_lateral,
        icono_ajuste_container,
        icono_pdf_ordenado_container,
        icono_imponer_container,
        boton_informe_container,
        boton_nuevo_trabajo,
        boton_abrir_trabajo,
        boton_guardar_trabajo,
    ) = crear_barra_lateral_izquierda(
        page,
        boton_informe_pdf,
        boton_toggle_tema,
        icono_ajuste_pliego,
        icono_pdf_ordenado,
        icono_imponer,
        icono_info,
        on_guardar_trabajo=guardar_trabajo_app,
        on_abrir_trabajo=cargar_trabajo_app,
        on_nuevo_trabajo=nuevo_trabajo_app,
        on_salir_app=salir_app,
    )

    # Crear botón 'Guardar como' y colocarlo debajo de 'Guardar trabajo' en la barra lateral
    boton_guardar_como = ft.Container(
        content=ft.Icon(ft.Icons.SAVE_AS_OUTLINED, size=24, color=TEXTOS_FASE_1_COLOR),
        width=40,
        height=40,
        border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
        border_radius=4,
        bgcolor=FONDO_TEXTFIELDS_COLOR,
        alignment=ft.Alignment.CENTER,
        on_click=guardar_como_app,
        tooltip=t("Guardar como"),
    )

    try:
        # Intentar insertar justo después del contenedor de guardar trabajo
        col = getattr(getattr(barra_lateral, "content", None), "controls", None)
        if col is None:
            raise AttributeError("barra_lateral.content.controls")
        idx = col.index(boton_guardar_trabajo)
        col.insert(idx + 1, boton_guardar_como)
    except Exception:
        # Fallback: colocarlo al inicio junto a los botones de archivo
        try:
            controles_barra = getattr(
                getattr(barra_lateral, "content", None), "controls", None
            )
            if controles_barra is not None:
                controles_barra.insert(3, boton_guardar_como)
        except Exception:
            controles_barra = getattr(
                getattr(barra_lateral, "content", None), "controls", None
            )
            if controles_barra is not None:
                controles_barra.append(boton_guardar_como)

    try:
        barra_lateral.update()
        page.update()
    except Exception:
        pass

    # Crear el contenedor principal que agrupa las columnas de Fase 1, Fase 2 y Fase 3, el bloque de resumen y el gráfico
    contenedor_principal = crear_contenedor_principal(
        columna_fase1, columna_fase2, columna_fase3, bloque_resumen_, grafico_viewer
    )

    # Funciones para controlar la visibilidad de las fases
    def fase_2_fase_3_visible_on():

        opciones_montaje.visible = True
        opciones_montaje.update()
        columna_fase2.visible = True
        columna_fase2.update()
        columna_fase3.visible = True
        columna_fase3.update()

    def fase_2_fase_3_visible_off():

        opciones_montaje.visible = False
        opciones_montaje.update()
        columna_fase2.visible = False
        columna_fase2.update()
        columna_fase3.visible = False
        columna_fase3.update()
        grafico_viewer.visible = False
        grafico_viewer.update()
        bloque_resumen_.visible = False
        bloque_resumen_.update()
        boton_informe_container.disabled = True
        boton_informe_container.opacity = 0.4
        boton_informe_container.update()
        icono_ajuste_container.disabled = True
        icono_ajuste_container.opacity = 0.4
        if _en_pagina(icono_ajuste_container):
            icono_ajuste_container.update()
        icono_pdf_ordenado_container.disabled = True
        icono_pdf_ordenado_container.opacity = 0.4
        icono_pdf_ordenado_container.update()
        icono_imponer_container.disabled = True
        icono_imponer_container.opacity = 0.4
        icono_imponer_container.update()

    def fase_3_visible_on():

        columna_fase3.visible = True
        columna_fase3.update()

    def fase_3_visible_off():

        columna_fase3.visible = False
        columna_fase3.update()

    page.add(
        ft.Container(
            ft.Row(
                [
                    # Barra lateral izquierda con iconos
                    barra_lateral,
                    # Contenedor principal: Fase 1, Fase 2 y Fase 3
                    ft.Container(
                        contenedor_principal,
                        expand=True,
                        alignment=ft.Alignment.TOP_LEFT,
                    ),
                ],
                spacing=0,
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            bgcolor=FONDO_APP,
            expand=True,
        )
    )

    # Inicializar estado visual de botones DESPUÉS de añadir a la página
    update_project_state_ui()

    # Foco inicial (antes era page.on_view, que no existe en Flet 1.0)
    set_focus_inicial()

    # Callback para manejar el resize de la ventana (registrar DESPUÉS de page.add)
    def on_page_resize(e=None):
        try:
            print(
                f"[RESIZE] Callback llamado - page.width={page.width}, page.height={page.height}"
            )
            # Si el gráfico está visible, redibujar con nuevo tamaño
            if grafico_viewer.visible and grafico_container.content:
                print(f"[RESIZE] Redibujando gráfico...")
                mostrar_trazado()
            else:
                print(f"[RESIZE] Gráfico no visible, no se redibuja")
        except Exception as ex:
            print(f"[ERROR] Error en resize: {ex}")

    page.on_resize = on_page_resize

    # Iniciar watcher en background para detectar cambios de tamaño
    def _start_resize_watcher():
        def _watch():
            try:
                prev_w = int(page.width or 0)
                prev_h = int(page.height or 0)
            except Exception:
                prev_w = 0
                prev_h = 0

            while True:
                try:
                    time.sleep(0.3)
                except Exception:
                    pass

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
                        if _PRINT_DEBUG:
                            print(f"[WATCHER] Detectado resize: {cur_w}x{cur_h}")
                        on_page_resize(None)
                    except Exception as e:
                        if _PRINT_DEBUG:
                            print(f"[WATCHER] Error: {e}")

        t = threading.Thread(target=_watch, daemon=True)
        t.start()

    try:
        _start_resize_watcher()
    except Exception:
        pass

    # Doble clic en .tns (Windows, asociación HKCU): abrir el archivo del argv
    try:
        _argv_tns = next(
            (
                a
                for a in sys.argv[1:]
                if a.lower().endswith(".tns") and os.path.exists(a)
            ),
            None,
        )
    except Exception:
        _argv_tns = None
    if _argv_tns:
        print(f"[ARGV] Abriendo trabajo por doble clic: {_argv_tns}")
        try:
            cargar_trabajo_app(None, _ruta_argv=_argv_tns)
        except Exception as _ex_argv:
            print(f"[ARGV] No se pudo abrir: {_ex_argv}")


def _heal_flet_client_cache() -> bool:
    """Garantiza que el cliente cacheado se llama TalNumStack (nunca Flet).

    Flet demone: flet_desktop.ensure_client_cached solo comprueba que exista la
    CARPETA (~/.flet/client/flet-desktop-*) y la devuelve tal cual. Si esa
    carpeta la pobló una sesión dev (cliente vanilla "Flet.app" bajado de
    GitHub), la .app empaquetada la reutiliza y NUNCA extrae el tar branded
    (TalNumStack.app, com.japr.talnumstack) que lleva dentro → el Dock enseña
    "Flet". Aquí se valida por NOMBRE del bundle (sin hash, el hash del tar
    cambia con cada rebuild) y se repara:
      - empaquetada: se borra la caché contaminada → se re-extrae del tar
        embebido (flet pack ya lo deja branded y firmado).
      - dev: no hay tar branded → se renombra el bundle, se parchea el plist
        y se re-firma ad-hoc (mismo gesto de flet pack al ensamblar).
    Devuelve True SOLO si en este arranque hubo que instalar/extraer/renombrar
    el cliente (y por tanto hay que aplicar el icono); False si el cliente ya
    existía y era correcto → _brand_and_set_client_icon no tocará nada.
    """
    try:
        import builtins
        import shutil
        import subprocess
        import plistlib
        import time

        from flet_desktop import ensure_client_cached, find_macos_app_bundle

        cache_dir = ensure_client_cached()
        bundle = find_macos_app_bundle(cache_dir)
        instalado = False

        if bundle is None:
            builtins.print(f"[FLET] Caché hueca sin cliente, regenerando: {cache_dir}")
            shutil.rmtree(cache_dir, ignore_errors=True)
            cache_dir = ensure_client_cached()
            bundle = find_macos_app_bundle(cache_dir)
            instalado = True

        if bundle is not None and bundle.name != "TalNumStack.app":
            if getattr(sys, "frozen", False):
                builtins.print(
                    f"[FLET] Cliente {bundle.name} no es de la app, re-extrayendo del tar: {cache_dir}"
                )
                shutil.rmtree(cache_dir, ignore_errors=True)
                cache_dir = ensure_client_cached()
                bundle = find_macos_app_bundle(cache_dir)
                instalado = True
            elif bundle is not None:
                renombrado = bundle.parent / "TalNumStack.app"
                bundle.rename(renombrado)
                bundle = renombrado
                plist_path = bundle / "Contents" / "Info.plist"
                with open(plist_path, "rb") as f:
                    pl = plistlib.load(f)
                pl["CFBundleName"] = "TalNumStack"
                pl["CFBundleDisplayName"] = "TalNumStack"
                pl["CFBundleIdentifier"] = "com.japr.talnumstack"
                with open(plist_path, "wb") as f:
                    plistlib.dump(pl, f)
                subprocess.run(
                    ["codesign", "--force", "--deep", "-s", "-", str(bundle)],
                    check=False,
                )
                builtins.print(f"[FLET] Cliente renombrado a {bundle.name} (dev)")
                instalado = True

        # Correcto pero acabado de extraer/descargar en ESTE arranque
        # (primera vez en ~/.flet vacío): cuenta como instalado → icono.
        if not instalado and bundle is not None:
            try:
                if time.time() - bundle.stat().st_birthtime < 120:
                    instalado = True
            except OSError:
                pass
        return instalado
    except Exception as e:
        import builtins

        builtins.print(f"[FLET] Aviso saneando caché del cliente: {e}")
        return False


def _brand_and_set_client_icon(instalado: bool = False) -> None:
    """Aplica el icono de TalNumStack al cliente Flet instalado (solo darwin).

    No vale parchear un .icns suelto (el icono de la app Flutter vive en
    Assets.car): se usa NSWorkspace.setIcon, el mismo gesto que "Get Info >
    arrastrar icono", la única vía que macOS acepta. Solo toca el bundle si
    _heal_flet_client_cache devolvió instalado=True (este arranque
    instaló/extrajo/renombró el cliente); si el cliente ya existía y era
    correcto NO se hace nada (ni icono, ni marcador, ni print). El marcador
    `.icon-applied` (fijo y legible, sin hash) evita repetirlo dentro de la
    misma instalación. La carpeta del cliente lleva la versión de Flet en el
    nombre → al subir la versión se instala de cero y el icono se re-aplica.
    De paso borra cachés de versiones viejas de esta app. Nunca revienta la
    app si algo falla.
    """
    try:
        import builtins
        import shutil
        import time

        from flet_desktop import ensure_client_cached, find_macos_app_bundle

        cache_dir = ensure_client_cached()
        bundle = find_macos_app_bundle(cache_dir)

        if bundle is None:
            builtins.print("[FLET] cliente sin bundle, icono no aplicado")
        elif not instalado:
            pass  # cliente correcto y ya existente → no se toca nada
        else:
            try:
                from AppKit import NSImage, NSWorkspace
            except Exception as e:
                builtins.print(f"[FLET] sin AppKit ({e}), icono no aplicado")
            else:
                icns = get_resource_path("TalNumStack.icns")
                # Marcador de nombre FIJO (legible): solo se escribe si en este
                # arranque se instaló el cliente y aún no se le puso el icono.
                # Si algún día cambia el icono real, borrar .icon-applied y se
                # re-aplicará una vez.
                marca = cache_dir / ".icon-applied"
                for old in cache_dir.glob(".icon-*"):
                    if old.name != marca.name:
                        old.unlink()
                if not marca.exists():
                    img = NSImage.alloc().initWithContentsOfFile_(icns)
                    if img is not None:
                        NSWorkspace.sharedWorkspace().setIcon_forFile_options_(
                            img, str(bundle), 0
                        )
                        marca.touch()
                        print(f"[FLET] icono TalNumStack aplicado: {bundle}")

        root = cache_dir.parent
        keep = cache_dir.name
        for entry in root.glob("flet-desktop-full-*_talnumstack"):
            if entry.name == keep or not entry.is_dir():
                continue
            lu = entry / ".last-used"
            try:
                age = time.time() - lu.stat().st_mtime if lu.exists() else None
            except OSError:
                age = None
            # no borrar si otra instancia la usó hoy
            if age is None or age > 86400:
                shutil.rmtree(entry, ignore_errors=True)
                builtins.print(f"[FLET] caché cliente vieja borrada: {entry.name}")
    except Exception as e:
        import builtins

        builtins.print(f"[FLET] Aviso branding del cliente: {e}")


def _ocultar_icono_python_dock() -> None:
    """Quita el wrapper de Python del Dock en dev (el equivalente a LSUIElement).

    En la .app empaquetada ese papel lo hace LSUIElement=True del Info.plist;
    ejecutando `python app.py` no hay bundle, así que hace falta la política de
    activación Accessory para que solo se vea el icono del cliente Flet.
    """
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory

        aplicada = NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyAccessory
        )
        if not aplicada:
            import builtins

            builtins.print("[FLET] Aviso: activation policy de Dock no aplicada")
    except Exception as e:
        import builtins

        builtins.print(f"[FLET] Aviso icono Python en Dock: {e}")


if __name__ == "__main__":
    if sys.platform == "darwin":
        _ocultar_icono_python_dock()
        _brand_and_set_client_icon(_heal_flet_client_cache())
    if sys.platform == "win32":
        try:
            from fileassoc_windows import registrar_tns

            print(registrar_tns())
        except Exception as _ex_assoc:
            print(f"[FILEASSOC] omitido: {_ex_assoc}")
    ft.run(main)
