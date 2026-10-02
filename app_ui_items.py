import flet as ft
from types import SimpleNamespace
import sys
import os
import platform
import threading
import asyncio
import logging
from pdf_manipulator import contar_paginas_pdf, reorganizar_pdf_real
from fiery_export import generar_listas_fiery, generar_archivo_xerox_manual
from grafico import grafico_datos, generar_ordenamiento_pdf_montaje
from color_design import *

# Preferencias reutilizando el sistema de PageNumber

try:
    from talnum_preferences import get_preference, save_preference
except Exception:
    # En entornos donde PageNumber no esté disponible, definir stubs
    def get_preference(k, d=None):
        return d

    def save_preference(k, v):
        return False


from lang import set_language
import pathlib
import subprocess

try:
    from error_logger import get_log_path
except Exception:
    get_log_path = None

# internacionalización
from lang import t, LANG, get_language_options

# Unidades de medida (interfaz de usuario)
from importlib import import_module

_unit_mod = None
try:
    _unit_mod = import_module("utils.unit_utils")
except Exception:
    try:
        # Fallback: try importing from top-level if package layout differs
        _unit_mod = import_module("unit_utils")
    except Exception:
        _unit_mod = None

if _unit_mod:
    get_units_list = getattr(_unit_mod, "get_units_list")
    get_unit_label = getattr(_unit_mod, "get_unit_label")
    UNIT_MM = getattr(_unit_mod, "UNIT_MM", "mm")
    # Desactivado: print de inicialización de unidades para evitar spam en consola
    # print(f"[INIT] Unidades cargadas desde module: {get_units_list()}")
else:

    def get_units_list():
        return ["mm"]

    def get_unit_label(u, t_func=None):
        return u

    UNIT_MM = "mm"


_PRINT_DEBUG = False
if not _PRINT_DEBUG:

    def _no_print(*args, **kwargs):
        return None

    print = _no_print

# Importar nuevo módulo de PDF ordenado
try:
    from pdf_ordenado_ui import crear_ventana_pdf_ordenado

    print("✅ PDF ordenado importado correctamente")
except Exception as ex:
    print(f"❌ ERROR importando pdf_ordenado_ui: {ex}")
    import traceback

    traceback.print_exc()
    crear_ventana_pdf_ordenado = None


# --- Función utilitaria para mostrar SnackBar ---
def mostrar_snackbar(page, texto, _bgcolor=SNACKBAR_COLOR_FONDO, duracion=3000):
    page.show_dialog(
        ft.SnackBar(
            ft.Text(texto, color=SNACKBAR_COLOR_TEXTO),
            bgcolor=_bgcolor,
            duration=duracion,
        )
    )
    page.update()


# --- Función utilitaria para mostrar AlertDialog de confirmación o error PDF ---
def mostrar_alert_dialog(page, exito, ruta_pdf=None, error_msg=None):

    def abrir_pdf(e):
        if ruta_pdf:
            try:
                if os.name == "nt":
                    subprocess.Popen(
                        ["cmd", "/c", "start", "", ruta_pdf],
                        shell=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                else:
                    os.system(f"open '{ruta_pdf}'")
            except Exception:
                pass

    def abrir_carpeta(e):
        if ruta_pdf:
            try:
                carpeta = str(pathlib.Path(ruta_pdf).parent)
                if os.name == "nt":
                    import subprocess

                    subprocess.Popen(
                        f'explorer "{carpeta}"',
                        shell=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                else:
                    os.system(f"open '{carpeta}'")
            except Exception:
                pass

    def volver(e):
        page.pop_dialog()

    if exito:
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Container(
                content=ft.Text(
                    t("PDF guardado correctamente"),
                    weight=ft.FontWeight.BOLD,
                    size=20,
                    text_align=ft.TextAlign.CENTER,
                ),
                alignment=ft.Alignment.CENTER,
            ),
            content=ft.Text(t("El PDF se ha guardado en:\n{0}").format(ruta_pdf)),
            bgcolor=FONDO_ALERT_DIALOG,
            actions=[
                ft.Button(
                    content=t("Abrir PDF"),
                    width=120,
                    bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                    on_click=abrir_pdf,
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
                    content=t("Abrir carpeta"),
                    width=120,
                    bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                    on_click=abrir_carpeta,
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
                    content=t("Volver"),
                    width=80,
                    bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                    on_click=volver,
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
        )
    else:
        # Mensaje de error detallado si se proporciona
        mensaje_error = "No se pudo guardar el PDF."
        if error_msg:
            mensaje_error += f"\n\nDetalle del error:\n{error_msg}"

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                t("Error al guardar PDF"), weight=ft.FontWeight.BOLD, size=20
            ),
            content=ft.Text(mensaje_error),
            bgcolor=FONDO_ALERT_DIALOG,
            actions=[
                ft.TextButton(t("Volver"), on_click=volver),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
    page.show_dialog(dialog)


# Stub defensivo: notificar_actualizacion_tamanos puede estar implementado en `impo_ui.py`.
if "notificar_actualizacion_tamanos" not in globals():

    def notificar_actualizacion_tamanos(tamanos):
        # Implementación vacía por defecto; `impo_ui` registra listeners propios si es necesario.
        return None


# icono del engranaje del menú de ajustes
icono_menu_settings = ft.Icon(
    ft.Icons.SETTINGS,
    size=30,
    color=TEXTO_COLOR_GENERICO,
)

# Variable global para el icono del botón de tema
icono_tema_button = None


# Función para manejar el hover del icono de ajustes 'e' devuelve true/false
def on_hover_menu_settings(e):
    print(f"[DEBUG] on_hover_menu_settings: hover state {e.data}")
    icono_menu_settings.color = (
        ICONO_PREF_HOVER_COLOR if e.data == "true" else ICONO_PREF_COLOR
    )
    icono_menu_settings.update()


# Función para manejar el hover del botón de tema (misma lógica que menu_settings)
def on_hover_tema_button(e):
    print(f"[DEBUG] on_hover_tema_button: hover state {e.data}")
    if icono_tema_button:
        # Aplicar la misma lógica: HOVER_COLOR cuando mouse entra, PREF_COLOR cuando sale
        icono_tema_button.icon_color = (
            ICONO_PREF_HOVER_COLOR if e.data == "true" else ICONO_PREF_COLOR
        )
        icono_tema_button.selected_icon_color = (
            ICONO_PREF_HOVER_COLOR if e.data == "true" else DROPDOWN_TRAILING_ICON_COLOR
        )
        icono_tema_button.update()


# Menú superior con tres puntos (sin icono de engranaje)
def crear_menu_ajuste_popup(on_ajuste_pliego_modo_change, color_menu_text: str):
    return ft.MenuBar(
        expand=True,
        style=ft.MenuStyle(
            alignment=ft.Alignment.CENTER,
            bgcolor=ft.Colors.TRANSPARENT,  # Fondo del MenuBar transparente (hereda del padre)
            shadow_color=ft.Colors.TRANSPARENT,  # Sin sombra alrededor del menú
        ),
        controls=[
            ft.SubmenuButton(
                content=icono_menu_settings,
                on_hover=on_hover_menu_settings,
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.TRANSPARENT,  # Fondo del botón transparente
                    overlay_color=ft.Colors.TRANSPARENT,  # Sin color de overlay al hacer hover/click
                    shadow_color=ft.Colors.TRANSPARENT,  # Sin sombra del botón
                    shape=ft.RoundedRectangleBorder(
                        radius=0
                    ),  # Bordes cuadrados (sin redondear)
                ),
                controls=[
                    ft.SubmenuButton(
                        content=ft.Text(t("Ajuste por pliego"), color=color_menu_text),
                        expand=True,
                        style=ft.ButtonStyle(
                            bgcolor=FONDO_MENU_AJUSTES,
                            shape=ft.RoundedRectangleBorder(radius=0),
                        ),
                        controls=[
                            ft.MenuItemButton(
                                height=30,
                                content=ft.Text(t("Auto"), color=color_menu_text),
                                on_click=lambda e: on_ajuste_pliego_modo_change(
                                    e, "Auto"
                                ),
                                style=ft.ButtonStyle(
                                    bgcolor=FONDO_MENU_AJUSTES,
                                    shape=ft.RoundedRectangleBorder(radius=0),
                                ),
                            ),
                            ft.MenuItemButton(
                                height=30,
                                content=ft.Text(t("Manual"), color=color_menu_text),
                                on_click=lambda e: on_ajuste_pliego_modo_change(
                                    e, "Manual"
                                ),
                                style=ft.ButtonStyle(
                                    bgcolor=FONDO_MENU_AJUSTES,
                                    shape=ft.RoundedRectangleBorder(radius=0),
                                ),
                            ),
                        ],
                    ),
                    # Opción para abrir el diálogo de ordenamiento PDF (vacío por ahora)
                    ft.MenuItemButton(
                        height=36,
                        content=ft.Text(t("Crear PDF ordenado"), color=color_menu_text),
                        on_click=lambda e: e.page.show_dialog(
                            crear_ventana_ordenar_pdfs(e.page)
                        ),
                        style=ft.ButtonStyle(
                            bgcolor=FONDO_MENU_AJUSTES,
                            shape=ft.RoundedRectangleBorder(radius=0),
                        ),
                    ),
                    ft.MenuItemButton(
                        height=36,
                        content=ft.Text(t("Imponer páginas"), color=color_menu_text),
                        # Abrir el nuevo diálogo de PDF ordenado con vista previa
                        on_click=lambda e: (
                            print(
                                "[BOTÓN IMPONER] ========================================"
                            ),
                            print("[BOTÓN IMPONER] Botón 'Imponer páginas' clickeado"),
                            print(
                                "[BOTÓN IMPONER] ========================================"
                            ),
                            (
                                mostrar_snackbar(
                                    e.page,
                                    t("Genere un gráfico antes de imponer páginas."),
                                    SNACKBAR_COLOR_ERROR,
                                    3500,
                                )
                                if not (
                                    isinstance(globals().get("grafico_datos"), dict)
                                    and "orden_grafico_visual"
                                    in globals().get("grafico_datos")
                                )
                                else abrir_pdf_ordenado_y_luego_imposicion(e.page)
                            ),
                        ),
                        style=ft.ButtonStyle(
                            bgcolor=FONDO_MENU_AJUSTES,
                            shape=ft.RoundedRectangleBorder(radius=0),
                        ),
                    ),
                    ft.MenuItemButton(
                        height=36,
                        content=ft.Text(t("Info"), color=color_menu_text),
                        on_click=lambda e: e.page.show_dialog(crear_dialogo_info(e.page)),
                        style=ft.ButtonStyle(
                            bgcolor=FONDO_MENU_AJUSTES,
                            shape=ft.RoundedRectangleBorder(radius=0),
                        ),
                    ),
                ],
            )
        ],
    )


# Función para crear iconos individuales que reemplazan el menú del engranaje
def crear_iconos_menu(
    on_ajuste_pliego_modo_change, page, on_guardar_trabajo=None, get_project_state=None
):
    """
    Crea iconos individuales para las opciones que antes estaban en el menú:
    1. Ajuste por pliego (Auto/Manual) - Engranaje con toggle
    2. Crear PDF ordenado - Icon
    3. Imponer páginas - Icon
    4. Info - Icon

    get_project_state: función que retorna (project_modified, current_project_path, project_name)
    """

    # El estado actual del modo debe ser gestionado en app.py y pasado aquí como argumento (por ejemplo, ajuste_pliego_modo_valor)
    # Se espera que app.py cree el handler adecuado y lo pase aquí
    # Handler wrapper: calcula el modo y llama al handler real
    def on_toggle_ajuste_pliego(e):
        # Se asume que existe ajuste_pliego_modo en el scope global (de app.py)
        try:
            from app import ajuste_pliego_modo

            nuevo_modo = "Manual" if ajuste_pliego_modo["valor"] == "Auto" else "Auto"
        except Exception:
            # fallback: si no se puede importar, alternar por defecto
            nuevo_modo = "Manual"
        on_ajuste_pliego_modo_change(e, nuevo_modo)

    icono_ajuste_pliego = ft.IconButton(
        icon=ft.Icons.AUTO_FIX_NORMAL_OUTLINED,
        tooltip=t("Ajuste por pliego (Auto/Manual)"),
        icon_size=24,
        on_click=on_toggle_ajuste_pliego,
        icon_color=ICONO_PREF_COLOR,
        hover_color=ICONO_PREF_HOVER_COLOR,
        disabled=False,  # Controlar desde app.py si es necesario
        visible=False,
        opacity=1.0,
    )

    # Icono para Crear PDF ordenado
    icono_pdf_ordenado = ft.IconButton(
        icon=ft.Icons.FILTER_NONE,
        tooltip=t("Crear PDF ordenado"),
        icon_size=24,
        on_click=lambda e: e.page.show_dialog(crear_ventana_ordenar_pdfs(e.page)),
        icon_color=ICONO_PREF_COLOR,
        hover_color=ICONO_PREF_HOVER_COLOR,
        disabled=True,  # Inicialmente deshabilitado
        opacity=0.4,  # Atenuado cuando está deshabilitado
    )

    # Icono para Imponer páginas
    def on_imponer_click(e):
        if not (
            isinstance(globals().get("grafico_datos"), dict)
            and "orden_grafico_visual" in globals().get("grafico_datos")
        ):
            mostrar_snackbar(
                e.page,
                t("Genere un gráfico antes de imponer páginas."),
                SNACKBAR_COLOR_ERROR,
                3500,
            )
        else:
            # Obtener estado actual del proyecto
            if get_project_state:
                modified, path, name = get_project_state()
                abrir_pdf_ordenado_y_luego_imposicion(
                    e.page, on_guardar_trabajo, modified, path, name
                )
            else:
                abrir_pdf_ordenado_y_luego_imposicion(e.page, on_guardar_trabajo)

    icono_imponer = ft.IconButton(
        icon=ft.Icons.GRID_ON,
        tooltip=t("Imponer páginas"),
        icon_size=24,
        on_click=on_imponer_click,
        icon_color=ICONO_PREF_COLOR,
        hover_color=ICONO_PREF_HOVER_COLOR,
        disabled=True,  # Inicialmente deshabilitado
        opacity=0.4,  # Atenuado cuando está deshabilitado
    )

    # Icono para Info
    icono_info = ft.IconButton(
        icon=ft.Icons.INFO_OUTLINE,
        tooltip=t("Información"),
        icon_size=24,
        on_click=lambda e: e.page.show_dialog(crear_dialogo_info(e.page)),
        icon_color=ICONO_PREF_COLOR,
        hover_color=ICONO_PREF_HOVER_COLOR,
    )

    return (
        icono_ajuste_pliego,
        icono_pdf_ordenado,
        icono_imponer,
        icono_info,
    )


# Función para crear el menú toggle de tema
def crear_boton_toggle_tema(on_tema_toggle):
    """Crear un botón toggle para alternar entre tema claro y oscuro"""
    global icono_tema_button

    # Determinar el estado inicial basado en el tema actual
    es_oscuro = tema_flet == ft.ThemeMode.DARK

    # Crear el botón y asignarlo a la variable global
    icono_tema_button = ft.IconButton(
        icon=ft.Icons.DARK_MODE,
        selected_icon=ft.Icons.LIGHT_MODE,
        selected=es_oscuro,
        on_click=on_tema_toggle,
        icon_color=ICONO_PREF_COLOR,
        focus_color=ft.Colors.TRANSPARENT,
        highlight_color=ft.Colors.TRANSPARENT,
        splash_color=ft.Colors.TRANSPARENT,
        tooltip=t("Alternar tema"),
        icon_size=30,
        style=ft.ButtonStyle(
            overlay_color=ft.Colors.TRANSPARENT,
            shadow_color=ft.Colors.TRANSPARENT,
            alignment=ft.Alignment.CENTER,
            padding=ft.Padding(0, 0, 0, 0),
            shape=ft.RoundedRectangleBorder(radius=6),
        ),
    )

    return icono_tema_button


# Función para crear un diálogo de información sobre el software
def crear_dialogo_info(page):

    # Hacemos el contenido del diálogo más grande y desplazable para evitar
    # que el texto quede debajo del botón de acciones en pantallas pequeñas.
    # Calcular tamaño dinámico en función de la ventana para mostrar el diálogo
    try:
        w = int(page.width * 0.95) if getattr(page, "width", None) else 1200
    except Exception:
        w = 1200
    try:
        h = int(page.height * 0.92) if getattr(page, "height", None) else 800
    except Exception:
        h = 800
    # Asegurar mínimos razonables
    w = max(700, w)
    h = max(400, h)

    contenido = ft.Container(
        ft.Column(
            [
                ft.Text(
                    t("Juan Antonio Picornell Richarte"),
                    size=18,
                    weight=ft.FontWeight.BOLD,
                ),
                ft.Text(t("TALNUMSTACK_VERSION"), size=16),
                ft.Row(
                    [
                        ft.Container(
                            content=ft.Icon(
                                ft.Icons.COFFEE, size=18, color=ICONO_PREF_COLOR
                            ),
                            margin=ft.Margin.only(top=2),
                        ),
                        ft.Text(
                            spans=[
                                ft.TextSpan(
                                    t("INVITE_COFFEE"),
                                    url="https://paypal.me/japr99",
                                    style=ft.TextStyle(
                                        color=TEXTO_COLOR_GENERICO,
                                        decoration=ft.TextDecoration.UNDERLINE,
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                )
                            ],
                            size=14,
                        ),
                    ],
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(height=10),
                ft.Text(
                    t("INFO_TALNUMSTACK"),
                    size=14,
                ),
                ft.Text(
                    t(
                        "Tanto 'Crear PDF ordenado' como 'Imponer páginas' incluyen la opción de generar un archivo para Fiery Command WorkStation, que facilita la distribución de copias por cajón de papel.\n"
                    ),
                    size=14,
                ),
                ft.Text(
                    spans=[
                        ft.TextSpan(
                            t("LICENSE_NOTICE").rsplit(
                                "gnu.org/licenses/agpl-3.0.html", 1
                            )[0]
                        ),
                        ft.TextSpan(
                            "gnu.org/licenses/agpl-3.0.html",
                            url="https://www.gnu.org/licenses/agpl-3.0.html",
                            style=ft.TextStyle(
                                color=TEXTO_COLOR_GENERICO,
                                decoration=ft.TextDecoration.UNDERLINE,
                                weight=ft.FontWeight.BOLD,
                            ),
                        ),
                    ],
                    size=12,
                ),
            ],
            spacing=8,
            scroll="auto",
        ),
        # Ajustar ancho/alto para abarcar pantallas; el scroll se aplica en la Column.
        width=w,
        height=h,
        padding=ft.Padding(12, 8, 12, 8),
    )

    dialogo = ft.AlertDialog(
        modal=True,
        title=ft.Text(
            t("Información"),
            weight=ft.FontWeight.BOLD,
            size=24,
            text_align=ft.TextAlign.CENTER,
        ),
        content=contenido,
        actions=[
            ft.Button(
                content=t("Volver"),
                width=80,
                bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                on_click=lambda e: e.page.pop_dialog(),
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
        bgcolor=FONDO_ALERT_DIALOG,
        actions_alignment=ft.MainAxisAlignment.END,
    )

    return dialogo


def crear_dialogo_preferencias(page, on_salir_app=None):
    """Dialogo de Preferencias simples: selector de idioma y persistencia.
    Cambio de idioma solicita reinicio (igual comportamiento que PageNumber).
    """
    language_options = get_language_options()

    current = get_preference("language", None)

    # Crear dropdown con estilo consistente con el resto de la UI
    language_dropdown = ft.Dropdown(
        width=220,
        options=[ft.dropdown.Option(code, label) for code, label in language_options],
        value=current if current is not None else LANG,
        label=t("Idioma"),
        text_size=14,
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

    def _on_language_change(e):
        selected_code = e.control.value
        if not selected_code:
            return
        if selected_code == current:
            return

        # Dialogo que avisa que debe reiniciar para aplicar idioma
        def _do_restart(ev):
            try:
                save_preference("language", selected_code)
            except Exception:
                pass
            # NO llamar set_language() aquí: el idioma nuevo se aplica al arranque
            # siguiente para que el diálogo de "cambios sin guardar" salga en el
            # idioma activo de la sesión, no en el idioma recién seleccionado.
            # Usar el handler de salida existente para cerrar la app limpiamente
            try:
                if on_salir_app:
                    on_salir_app(None)
                else:
                    page.run_task(page.window.destroy)
            except Exception:
                try:
                    page.run_task(page.window.destroy)
                except Exception:
                    pass

        def _do_later(ev):
            try:
                save_preference("language", selected_code)
            except Exception:
                pass
            try:
                page.pop_dialog()
            except Exception:
                try:
                    restart_dialog.open = False
                    page.update()
                except Exception:
                    pass

        restart_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Container(
                content=ft.Text(
                    t("Restart Required"), size=16, weight=ft.FontWeight.BOLD
                ),
                alignment=ft.Alignment.CENTER,
            ),
            content=ft.Container(
                content=ft.Text(t("Please close the app to apply the language change")),
                width=520,
                height=160,
                alignment=ft.Alignment.CENTER,
            ),
            actions=[
                ft.Button(
                    t("Más tarde"),
                    on_click=_do_later,
                    width=140,
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
                    t("Cerrar app"),
                    on_click=_do_restart,
                    width=140,
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
            actions_alignment=ft.MainAxisAlignment.CENTER,
            bgcolor=FONDO_ALERT_DIALOG,
        )

        try:
            page.show_dialog(restart_dialog)
        except Exception:
            pass

    language_dropdown.on_select = _on_language_change

    # Dropdown de unidad (global)
    current_unit = get_preference("unit", None)
    unit_options = get_units_list()
    unit_dropdown = ft.Dropdown(
        width=220,
        options=[ft.dropdown.Option(u, get_unit_label(u, t)) for u in unit_options],
        value=current_unit if current_unit is not None else UNIT_MM,
        label=t("Unidad:"),
        text_size=14,
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

    def _on_unit_change(e):
        selected_code = e.control.value
        if not selected_code:
            return
        try:
            save_preference("unit", selected_code)
        except Exception:
            pass
        try:
            mostrar_snackbar(page, t("Preferencias guardadas"))
            # Intentar notificar a impo_ui para actualizar controles en caliente
            try:
                import impo_ui

                if hasattr(impo_ui, "update_units_in_impo"):
                    impo_ui.update_units_in_impo(selected_code)
            except Exception:
                pass
        except Exception:
            pass

    unit_dropdown.on_select = _on_unit_change

    def _abrir_log(e):
        try:
            log_path = get_log_path() if get_log_path else None
            if log_path and log_path.exists():
                if sys.platform == "darwin":
                    subprocess.Popen(["open", str(log_path)])
                elif sys.platform == "win32":
                    os.startfile(str(log_path))
                else:
                    subprocess.Popen(["xdg-open", str(log_path)])
            else:
                mostrar_snackbar(page, t("No hay log de errores todavía"))
        except Exception as _ex:
            logging.exception("Error al abrir el log de errores desde Preferencias")
            mostrar_snackbar(page, str(_ex))

    btn_log = ft.Button(
        content=t("Abrir log de errores"),
        icon=ft.Icons.BUG_REPORT_OUTLINED,
        on_click=_abrir_log,
        bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
        style=ft.ButtonStyle(
            color={
                ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                ft.ControlState.HOVERED: BOTONES_GENERICOS_HOVER_COLOR,
            },
            overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
            padding=ft.Padding(10, 6, 10, 6),
            shape=ft.RoundedRectangleBorder(radius=10),
        ),
    )

    cb_reset_app = ft.Checkbox(
        label=t("Resetear app, elimina todas las preferencias."),
        value=False,
        active_color=BORDE_TEXTFIELDS_COLOR,
        check_color=TEXTOS_FASE_1_COLOR,
        label_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
        fill_color=BOTONES_GENERICOS_FONDO_COLOR,
    )

    contenido = ft.Column(
        [
            ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text(t("Idioma de la aplicación"), size=14),
                            language_dropdown,
                        ],
                        spacing=4,
                        expand=True,
                    ),
                    ft.Column(
                        [
                            ft.Text(t("Unidad:"), size=14),
                            unit_dropdown,
                        ],
                        spacing=4,
                        expand=True,
                    ),
                ],
                spacing=16,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            ft.Divider(
                height=18, color=ft.Colors.with_opacity(0.2, ft.Colors.ON_SURFACE)
            ),
            ft.Row(
                [
                    ft.Text(
                        t("Registro de errores"),
                        size=14,
                        text_align=ft.TextAlign.CENTER,
                    )
                ],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            ft.Row(
                [btn_log],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            ft.Divider(
                height=18, color=ft.Colors.with_opacity(0.2, ft.Colors.ON_SURFACE)
            ),
            ft.Row(
                [cb_reset_app],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
        ],
        spacing=8,
    )

    def _on_preferences_close(e):
        # Si el check de reset está marcado, confirmar y cerrar app
        if cb_reset_app.value:
            def _confirm_reset(ev):
                try:
                    page.pop_dialog()
                except Exception:
                    try:
                        confirm_dialog.open = False
                        page.update()
                    except Exception:
                        pass
                # Eliminar carpeta de config
                import shutil
                from talnum_preferences import get_config_dir
                config_dir = get_config_dir()
                try:
                    if config_dir.exists():
                        shutil.rmtree(config_dir)
                        print(f"[PREFERENCES] ⚠️ Removed TalNumStack config dir: {config_dir}")
                except Exception as ex:
                    print(f"[PREFERENCES] Error removing config dir: {ex}")
                # Cerrar la app
                if on_salir_app:
                    on_salir_app(None)
                else:
                    page.run_task(page.window.destroy)

            def _cancel_reset(ev):
                try:
                    page.pop_dialog()
                except Exception:
                    try:
                        confirm_dialog.open = False
                        page.update()
                    except Exception:
                        pass

            confirm_dialog = ft.AlertDialog(
                modal=True,
                inset_padding=0,
                title_padding=ft.Padding(10, 20, 10, 8),
                title=ft.Text(t("Resetear app, elimina todas las preferencias."), size=16, weight=ft.FontWeight.BOLD),
                content=ft.Container(
                    content=ft.Text(
                        t("Esta acción borrará todos los datos guardados de la aplicación.\nLa aplicación se cerrará.\n¿Desea continuar?"),
                        text_align=ft.TextAlign.CENTER,
                    ),
                    width=480,
                    height=120,
                    alignment=ft.Alignment.CENTER,
                ),
                actions=[
                    ft.Button(
                        t("Cancelar"),
                        on_click=_cancel_reset,
                        width=110,
                        bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                    ),
                    ft.Button(
                        t("Aceptar"),
                        on_click=_confirm_reset,
                        width=110,
                        bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                    ),
                ],
                actions_alignment=ft.MainAxisAlignment.CENTER,
                bgcolor=FONDO_ALERT_DIALOG,
            )
            try:
                page.show_dialog(confirm_dialog)
            except Exception:
                pass
            return

        # Guardar explícitamente los valores actuales al cerrar el diálogo
        try:
            sel_unit = unit_dropdown.value
            if sel_unit is not None:
                try:
                    save_preference("unit", sel_unit)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            sel_lang = language_dropdown.value
            if sel_lang is not None:
                try:
                    save_preference("language", sel_lang)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            e.page.pop_dialog()
        except Exception:
            try:
                dialog.open = False
                page.update()
            except Exception:
                pass

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Container(
            content=ft.Text(
                t("Preferencias"),
                weight=ft.FontWeight.BOLD,
                size=18,
                text_align=ft.TextAlign.CENTER,
            ),
            alignment=ft.Alignment.CENTER,
        ),
        # Añadido margen inferior para separar el contenido de los botones
        content=ft.Container(
            content=contenido,
            width=560,
            height=290,
            padding=ft.Padding(12, 10, 12, 10),
            margin=ft.Margin(0, 0, 0, 4),
        ),
        actions=[
            ft.Button(
                content=t("Volver"),
                on_click=_on_preferences_close,
                width=140,
                bgcolor=BOTONES_GENERICOS_FONDO_COLOR,
                style=ft.ButtonStyle(
                    color={
                        ft.ControlState.DEFAULT: BOTONES_GENERICOS_COLOR,
                        ft.ControlState.HOVERED: BOTONES_GENERICOS_HOVER_COLOR,
                    },
                    overlay_color=BOTONES_GENERICOS_OVERLAY_COLOR,
                    padding=ft.Padding(8, 6, 8, 6),
                    shape=ft.RoundedRectangleBorder(radius=10),
                ),
            )
        ],
        actions_alignment=ft.MainAxisAlignment.CENTER,
        bgcolor=FONDO_ALERT_DIALOG,
    )

    return dialog


def generar_filas_opciones_montaje(opciones, total):
    filas = [
        ft.Row(
            [
                ft.Text(
                    t("Hojas x Pliego"),
                    size=18,
                    width=131,
                    text_align=ft.TextAlign.RIGHT,
                    weight=ft.FontWeight.BOLD,
                    color=TEXTOS_FASE_2_COLOR,
                ),
                ft.Text(
                    " ",
                    size=18,
                    width=20,
                    text_align=ft.TextAlign.CENTER,
                    weight=ft.FontWeight.BOLD,
                    color=TEXTOS_FASE_2_COLOR,
                ),
                ft.Text(
                    t("Tiradas"),
                    size=18,
                    width=70,
                    text_align=ft.TextAlign.LEFT,
                    weight=ft.FontWeight.BOLD,
                    color=TEXTOS_FASE_2_COLOR,
                ),
            ],
            spacing=2,
            width=380,
        )
    ]
    for x in opciones:
        filas.append(
            ft.Row(
                [
                    ft.Text(
                        str(x),
                        size=18,
                        width=131,
                        text_align=ft.TextAlign.RIGHT,
                        color=TEXTOS_FASE_2_COLOR,
                    ),
                    ft.Text(
                        "=",
                        size=18,
                        width=20,
                        text_align=ft.TextAlign.CENTER,
                        color=TEXTOS_FASE_2_COLOR,
                    ),
                    ft.Text(
                        str(int(total) // x),
                        size=18,
                        width=60,
                        text_align=ft.TextAlign.LEFT,
                        color=TEXTOS_FASE_2_COLOR,
                    ),
                ],
                spacing=2,
                width=380,
            )
        )
    return filas


def generar_filas_opciones_montaje_pro(montajes):
    """
    Montajes: lista de tuplas (hxP, total_hojas, tiradas, talonarios)
    Devuelve filas para mostrar la tabla completa (HxP | T.H.C. | T.C. | Tal.C.)
    """
    # Nota: la cabecera se muestra como un contenedor fijo en la UI;
    # aquí solo devolvemos las filas de datos (para que la cabecera no se duplique).
    filas = []

    for m in montajes:
        try:
            hxp, total_h, tc, tal = m
        except Exception:
            # si la tupla no tiene la forma esperada, saltarla
            continue
        filas.append(
            ft.Row(
                [
                    ft.Text(
                        str(hxp),
                        size=15,
                        width=60,
                        text_align=ft.TextAlign.CENTER,
                        color=TEXTO_COLOR_GENERICO,
                    ),
                    ft.Text(
                        str(total_h),
                        size=15,
                        width=90,
                        text_align=ft.TextAlign.CENTER,
                        color=TEXTO_COLOR_GENERICO,
                    ),
                    ft.Text(
                        str(tc),
                        size=15,
                        width=70,
                        text_align=ft.TextAlign.CENTER,
                        color=TEXTO_COLOR_GENERICO,
                    ),
                    ft.Text(
                        str(tal),
                        size=15,
                        width=70,
                        text_align=ft.TextAlign.CENTER,
                        color=TEXTO_COLOR_GENERICO,
                    ),
                ],
                spacing=2,
                width=360,
                alignment=ft.MainAxisAlignment.CENTER,
            )
        )
    return filas


def crear_textfield_cantidad(on_focus_campos):
    return ft.TextField(
        label=None,
        width=85,
        height=32,
        text_size=16,
        autofocus=True,
        text_align=ft.TextAlign.LEFT,
        text_vertical_align=ft.VerticalAlignment.CENTER,
        content_padding=ft.Padding(8, 0, 0, 0),
        color=TEXTOS_FASE_1_COLOR,
        bgcolor=FONDO_TEXTFIELDS_COLOR,
        border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)),
        focused_color=None,
        focused_bgcolor=None,
        label_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
        on_blur=lambda e: on_focus_campos(e, "cantidad"),
    )


def crear_textfield_can_hojas_tal(on_focus_campos):

    return ft.TextField(
        label=None,
        width=85,
        height=32,
        text_size=16,
        text_align=ft.TextAlign.LEFT,
        text_vertical_align=ft.VerticalAlignment.CENTER,
        content_padding=ft.Padding(8, 0, 0, 0),
        color=TEXTOS_FASE_1_COLOR,
        bgcolor=FONDO_TEXTFIELDS_COLOR,
        border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)),
        focused_color=None,
        focused_bgcolor=None,
        label_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
        on_blur=lambda e: on_focus_campos(e, "can_hojas_tal"),
    )


def crear_textfield_tirada():
    return ft.TextField(
        label=None,
        width=85,
        height=32,
        text_size=16,
        read_only=True,
        text_align=ft.TextAlign.LEFT,
        text_vertical_align=ft.VerticalAlignment.CENTER,
        content_padding=ft.Padding(8, 0, 0, 0),
        color=TEXTOS_FASE_1_COLOR,
        bgcolor=FONDO_TEXTFIELDS_COLOR,
        border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)),
        focused_color=None,
        focused_bgcolor=None,
        label_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
    )


def crear_textfield_hojas_x_pliego(on_focus_campos):
    return ft.TextField(
        label=None,
        width=70,
        height=32,
        text_size=16,
        text_align=ft.TextAlign.LEFT,
        text_vertical_align=ft.VerticalAlignment.CENTER,
        content_padding=ft.Padding(8, 0, 0, 0),
        color=TEXTOS_FASE_1_COLOR,
        bgcolor=FONDO_TEXTFIELDS_COLOR,
        border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)),
        focused_color=None,
        focused_bgcolor=None,
        label_style=ft.TextStyle(color=TEXTOS_FASE_1_COLOR),
        on_blur=lambda e: on_focus_campos(e, "hojas_x_pliego"),
    )


def crear_textfield_tirada_calculada():
    return ft.TextField(
        label=None,
        width=80,
        height=32,
        text_size=16,
        read_only=True,
        text_align=ft.TextAlign.LEFT,
        text_vertical_align=ft.VerticalAlignment.CENTER,
        content_padding=ft.Padding(8, 0, 0, 0),
        color=TEXTOS_FASE_1_COLOR,
        bgcolor=FONDO_TEXTFIELDS_COLOR,
        border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR)),
        focused_color=None,
        focused_bgcolor=None,
        label_style=ft.TextStyle(color=TEXTO_COLOR_GENERICO),
    )


def crear_column_opciones_montaje():
    return ft.Column(
        [],
        width=360,
        alignment=ft.Alignment.TOP_CENTER,
        scroll="auto",
        spacing=0,
    )


def crear_text_resumen_ajuste():
    return ft.Text(
        "", size=18, weight=ft.FontWeight.BOLD, color=TEXTO_BLOQUE_RESUMEN_COLOR
    )


def crear_boton_pdf(on_click):
    return ft.IconButton(
        icon=ft.Icons.DESCRIPTION_OUTLINED,
        tooltip=t("Crear informe PDF"),
        icon_size=24,
        on_click=on_click,
        icon_color=ICONO_PREF_COLOR,
        hover_color=ICONO_PREF_HOVER_COLOR,
        disabled=True,  # Inicialmente deshabilitado
        opacity=0.4,  # Atenuado cuando está deshabilitado
    )


def crear_bloque_resumen(resumen_ajuste):
    return ft.Container(
        ft.Row(
            [
                ft.Container(
                    resumen_ajuste,
                    expand=True,
                    alignment=ft.Alignment.CENTER_LEFT,
                    padding=ft.Padding(10, 0, 0, 0),
                ),
            ],
            spacing=0,
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        margin=ft.Margin(0, 0, 0, 0),
        height=40,
        bgcolor=FONDO_BLOQUE_RESUMEN_COLOR,
        border_radius=10,
        alignment=ft.Alignment.CENTER,
        visible=False,
    )


def crear_columna_fase1(cantidad, can_hojas_tal, tirada, opciones_montaje, page):
    # --- FASE 1: Bloque izquierdo ---
    # La lista de opciones se muestra automáticamente si los valores son válidos
    # Fase 1 dividida en dos partes: superior (inputs) e inferior (resultados con scroll)
    return ft.Container(
        width=360,
        bgcolor=FONDO_FASE_1,
        padding=0,
        border_radius=10,
        margin=ft.Margin(10, 10, 0, 10),
        content=ft.Column(
            [
                ft.Text(
                    t("FASE 1: Datos originales"),
                    size=20,
                    weight=ft.FontWeight.BOLD,
                    color=TEXTOS_FASE_1_COLOR,
                ),
                # Parte superior: inputs y tirada
                ft.Container(
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text(
                                        t("Talonarios"),
                                        size=18,
                                        width=190,
                                        text_align=ft.TextAlign.RIGHT,
                                        color=TEXTOS_FASE_1_COLOR,
                                    ),
                                    cantidad,
                                ]
                            ),
                            ft.Row(
                                [
                                    ft.Text(
                                        t("Hojas por talonario"),
                                        size=18,
                                        width=190,
                                        text_align=ft.TextAlign.RIGHT,
                                        color=TEXTOS_FASE_1_COLOR,
                                    ),
                                    can_hojas_tal,
                                ]
                            ),
                            ft.Row(
                                [
                                    ft.Text(
                                        t("Total hojas"),
                                        size=18,
                                        width=190,
                                        text_align=ft.TextAlign.RIGHT,
                                        color=TEXTOS_FASE_1_COLOR,
                                    ),
                                    tirada,
                                ]
                            ),
                        ],
                        spacing=10,
                        alignment=ft.MainAxisAlignment.CENTER,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=0,
                    margin=ft.Margin(0, 8, 0, 10),
                    alignment=ft.Alignment.CENTER,
                    # expand=True,
                ),
                # Contenedor que incluye la cabecera fija y debajo la lista desplazable
                ft.Container(
                    ft.Column(
                        [
                            # Header fijo
                            ft.Container(
                                ft.Row(
                                    [
                                        ft.Text(
                                            t("H. x P."),
                                            size=16,
                                            width=60,
                                            text_align=ft.TextAlign.CENTER,
                                            weight=ft.FontWeight.BOLD,
                                            color=TEXTO_COLOR_GENERICO,
                                            tooltip=t("Hojas x pliego"),
                                        ),
                                        ft.Text(
                                            t("H.C."),
                                            size=16,
                                            width=90,
                                            text_align=ft.TextAlign.CENTER,
                                            weight=ft.FontWeight.BOLD,
                                            color=TEXTO_COLOR_GENERICO,
                                            tooltip=t("hojas calculadas"),
                                        ),
                                        ft.Text(
                                            t("T.C."),
                                            size=16,
                                            width=70,
                                            text_align=ft.TextAlign.CENTER,
                                            weight=ft.FontWeight.BOLD,
                                            color=TEXTO_COLOR_GENERICO,
                                            tooltip=t("Tirada calculada"),
                                        ),
                                        ft.Text(
                                            t("Tal.C."),
                                            size=16,
                                            width=70,
                                            text_align=ft.TextAlign.CENTER,
                                            weight=ft.FontWeight.BOLD,
                                            color=TEXTO_COLOR_GENERICO,
                                            tooltip=t("Talonarios calculados"),
                                        ),
                                    ],
                                    spacing=2,
                                    width=360,
                                    alignment=ft.MainAxisAlignment.CENTER,
                                ),
                                padding=ft.Padding(6, 6, 6, 6),
                                width=360,
                                bgcolor=FONDO_BLOQUE_RESUMEN_COLOR,
                            ),
                            # Lista desplazable (la variable opciones_montaje ya es ft.Column con scroll)
                            ft.Container(
                                opciones_montaje,
                                padding=0,
                                width=360,
                                alignment=ft.Alignment.TOP_CENTER,
                                margin=ft.Margin(0, 0, 0, 0),
                                bgcolor=FONDO_CALCULO_FASE_1,
                                border_radius=0,
                                expand=True,  # Expandir para usar espacio restante
                            ),
                        ],
                        spacing=0,
                    ),
                    # bgcolor=ft.Colors.RED,
                    border_radius=6,
                    padding=0,
                    width=360,
                    alignment=ft.Alignment.TOP_CENTER,
                    margin=ft.Margin(8, 0, 8, 8),
                    expand=True,  # Expandir para usar espacio restante
                ),
            ],
            spacing=0,
            alignment=ft.MainAxisAlignment.START,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            expand=True,
        ),
    )


# Función para crear la columna de la Fase 2
def crear_columna_fase2(hojas_x_pliego_container, tirada_calculada):
    # --- FASE 2: Bloque derecho ---
    return ft.Column(
        [
            ft.Text(
                t("FASE 2: Ajuste por pliego"),
                size=20,
                weight=ft.FontWeight.BOLD,
                color=TEXTOS_FASE_2_COLOR,
            ),
            ft.Row(
                [
                    ft.Text(
                        t("Hojas x pliego"),
                        size=18,
                        width=165,
                        text_align=ft.TextAlign.RIGHT,
                        color=TEXTOS_FASE_2_COLOR,
                    ),
                    hojas_x_pliego_container,
                ],
                alignment=ft.MainAxisAlignment.START,
                spacing=10,
            ),
            ft.Container(height=0),  # Espaciador vertical
            ft.Row(
                [
                    ft.Text(
                        t("Tirada Calculada"),
                        size=18,
                        width=165,
                        text_align=ft.TextAlign.RIGHT,
                        color=TEXTOS_FASE_2_COLOR,
                    ),
                    tirada_calculada,
                ],
                alignment=ft.MainAxisAlignment.START,
                spacing=10,
            ),
        ],
        spacing=10,
        # alignment=ft.MainAxisAlignment.CENTER,
        horizontal_alignment=ft.CrossAxisAlignment.START,
        visible=False,
    )


# Función para crear un campo de texto para el comienzo de la numeración
def crear_textfield_comienzo_numeracion():
    # No necesitamos acceder al módulo app, usamos directamente las variables de color_design
    # que ya están importadas con "from color_design import *"
    print(
        f"[DEBUG] crear_textfield_comienzo_numeracion: usando colores directos desde color_design"
    )

    return ft.TextField(
        label=t("Comienzo Numeración"),
        value="1",
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


# Bloque para la Fase 3: Numeración
# Este bloque organiza los campos relacionados con la numeración en una fila horizontal.
def crear_bloque_fase3(
    comienzo_numeracion, horizontal_dropdown, vertical_value, orientacion_dropdown
):
    return ft.Row(
        [
            horizontal_dropdown,  # Dropdown para seleccionar el valor horizontal
            vertical_value,  # Campo de texto para mostrar el valor vertical calculado
            orientacion_dropdown,  # Dropdown para seleccionar la orientación
            comienzo_numeracion,  # Campo para el comienzo de la numeración
        ],
        spacing=12,
    )


# Función para crear la columna de la Fase 3
# grafico_viewer NO va aquí: ya vive en crear_contenedor_principal (expand=True).
# meterlo en dos sitios = doble padre → el trazado no se monta bien.
def crear_columna_fase3(bloque_fase3):
    return ft.Column(
        [
            ft.Text(
                t("FASE 3: Trazado y Numeración"),
                size=20,
                weight=ft.FontWeight.BOLD,
                color=TEXTOS_FASE_2_COLOR,
            ),  # Título de la sección
            bloque_fase3,  # Bloque con los campos de la Fase 3
        ],
        spacing=10,
        alignment=ft.MainAxisAlignment.START,
        visible=False,
        expand=True,
    )


# Función para crear un contenedor que envuelve el botón PDF
def crear_container_boton_pdf(boton_pdf):
    # Ahora que es IconButton, solo necesitamos devolverlo directamente
    return boton_pdf


# Función para crear el contenedor lateral izquierdo con iconos
# Desactivado 'icono_ajuste_pliego'
def crear_barra_lateral_izquierda(
    page,
    boton_informe_pdf,
    boton_toggle_tema,
    icono_ajuste_pliego,
    icono_pdf_ordenado,
    icono_imponer,
    icono_info,
    on_guardar_trabajo=None,
    on_abrir_trabajo=None,
    on_nuevo_trabajo=None,
    on_salir_app=None,
):
    # Botón nuevo trabajo con diseño de PageNumber (Container + Icon)
    boton_nuevo_trabajo = ft.Container(
        content=ft.Icon(ft.Icons.NOTE_ADD_OUTLINED, size=24, color=TEXTOS_FASE_1_COLOR),
        width=40,
        height=40,
        border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
        border_radius=4,
        bgcolor=FONDO_TEXTFIELDS_COLOR,
        alignment=ft.Alignment.CENTER,
        on_click=(
            on_nuevo_trabajo
            if on_nuevo_trabajo
            else lambda e: print(t("[TODO] Nuevo trabajo"))
        ),
        tooltip=t("Nuevo trabajo"),
    )

    # Botones de archivo con diseño de PageNumber (Container + Icon)
    boton_abrir_trabajo = ft.Container(
        content=ft.Icon(
            ft.Icons.FILE_OPEN_OUTLINED, size=24, color=TEXTOS_FASE_1_COLOR
        ),
        width=40,
        height=40,
        border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
        border_radius=4,
        bgcolor=FONDO_TEXTFIELDS_COLOR,
        alignment=ft.Alignment.CENTER,
        on_click=(
            on_abrir_trabajo
            if on_abrir_trabajo
            else lambda e: print(t("[TODO] Abrir trabajo"))
        ),
        tooltip=t("Cargar trabajo"),
    )

    boton_guardar_trabajo = ft.Container(
        content=ft.Icon(ft.Icons.SAVE_OUTLINED, size=24, color=TEXTOS_FASE_1_COLOR),
        width=40,
        height=40,
        border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
        border_radius=4,
        bgcolor=FONDO_TEXTFIELDS_COLOR,
        alignment=ft.Alignment.CENTER,
        on_click=(
            on_guardar_trabajo
            if on_guardar_trabajo
            else lambda e: print(t("[TODO] Guardar trabajo"))
        ),
        tooltip=t("Guardar trabajo"),
    )

    # Convertir boton_toggle_tema a Container si es IconButton
    # Estilizar igual que el resto de botones (borde, fondo y radio)
    boton_tema_container = ft.Container(
        content=boton_toggle_tema,
        width=40,
        height=40,
        border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
        border_radius=4,
        bgcolor=FONDO_TEXTFIELDS_COLOR,
        alignment=ft.Alignment.CENTER,
        tooltip=t("Alternar tema"),
    )

    # Convertir iconos de menú a Container con diseño PageNumber
    icono_ajuste_container = ft.Container(
        content=ft.Icon(
            ft.Icons.AUTO_FIX_NORMAL_OUTLINED, size=24, color=TEXTOS_FASE_1_COLOR
        ),
        width=40,
        height=40,
        border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
        border_radius=4,
        bgcolor=FONDO_TEXTFIELDS_COLOR,
        alignment=ft.Alignment.CENTER,
        on_click=icono_ajuste_pliego.on_click,
        tooltip=t("Ajuste por pliego"),
        disabled=True,
        opacity=0.4,
        visible=False,
    )

    icono_pdf_ordenado_container = ft.Container(
        content=ft.Icon(ft.Icons.FILTER_NONE, size=24, color=TEXTOS_FASE_1_COLOR),
        width=40,
        height=40,
        border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
        border_radius=4,
        bgcolor=FONDO_TEXTFIELDS_COLOR,
        alignment=ft.Alignment.CENTER,
        on_click=icono_pdf_ordenado.on_click,
        tooltip=t("Crear PDF ordenado"),
        disabled=True,
        opacity=0.4,
    )

    icono_imponer_container = ft.Container(
        content=ft.Icon(ft.Icons.GRID_ON, size=24, color=TEXTOS_FASE_1_COLOR),
        width=40,
        height=40,
        border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
        border_radius=4,
        bgcolor=FONDO_TEXTFIELDS_COLOR,
        alignment=ft.Alignment.CENTER,
        on_click=icono_imponer.on_click,
        tooltip=t("Imponer páginas"),
        disabled=True,
        opacity=0.4,
    )

    icono_info_container = ft.Container(
        content=ft.Icon(ft.Icons.INFO_OUTLINE, size=24, color=TEXTOS_FASE_1_COLOR),
        width=40,
        height=40,
        border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
        border_radius=4,
        bgcolor=FONDO_TEXTFIELDS_COLOR,
        alignment=ft.Alignment.CENTER,
        on_click=icono_info.on_click,
        tooltip=t("Información"),
    )

    boton_informe_container = ft.Container(
        content=ft.Icon(
            ft.Icons.DESCRIPTION_OUTLINED, size=24, color=TEXTOS_FASE_1_COLOR
        ),
        width=40,
        height=40,
        border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
        border_radius=4,
        bgcolor=FONDO_TEXTFIELDS_COLOR,
        alignment=ft.Alignment.CENTER,
        on_click=boton_informe_pdf.on_click,
        tooltip=t("Crear informe PDF"),
        disabled=True,
        opacity=0.4,
    )

    boton_salir = ft.Container(
        content=ft.Icon(ft.Icons.EXIT_TO_APP, size=24, color=TEXTOS_FASE_1_COLOR),
        width=40,
        height=40,
        border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
        border_radius=4,
        bgcolor=FONDO_TEXTFIELDS_COLOR,
        alignment=ft.Alignment.CENTER,
        on_click=on_salir_app if on_salir_app else (lambda e: page.run_task(page.window.destroy)),
        tooltip=t("Salir"),
    )

    # Icono de Preferencias (engranaje) situado encima del icono de salir
    icono_preferencias_container = ft.Container(
        content=ft.Icon(ft.Icons.SETTINGS, size=24, color=TEXTOS_FASE_1_COLOR),
        width=40,
        height=40,
        border=ft.Border.all(1, BORDE_TEXTFIELDS_COLOR),
        border_radius=4,
        bgcolor=FONDO_TEXTFIELDS_COLOR,
        alignment=ft.Alignment.CENTER,
        on_click=lambda e: e.page.show_dialog(
            crear_dialogo_preferencias(e.page, on_salir_app)
        ),
        tooltip=t("Preferencias"),
    )

    # Crear Column vertical con los iconos reorganizados (solo cambia el orden)
    return (
        ft.Container(
            content=ft.Column(
                [
                    boton_nuevo_trabajo,
                    boton_abrir_trabajo,
                    boton_guardar_trabajo,
                    ft.Divider(height=1),
                    ft.Container(height=8),  # Espaciador entre secciones
                    icono_pdf_ordenado_container,
                    boton_informe_container,
                    ft.Container(height=8),
                    ft.Divider(height=1),
                    ft.Container(height=8),  # Espaciador entre secciones
                    icono_imponer_container,
                    ft.Container(height=8),  # Espaciador entre secciones
                    ft.Divider(height=1),
                    ft.Container(expand=True),  # Spacer
                    boton_tema_container,  # Alternar tema debajo
                    icono_info_container,  # Información debajo
                    icono_preferencias_container,  # Preferencias encima de salir
                    boton_salir,
                ],
                spacing=8,
                alignment=ft.MainAxisAlignment.START,
                expand=True,
            ),
            width=50,
            bgcolor=FONDO_FASE_1,
            padding=ft.Padding(5, 10, 5, 10),
            border_radius=ft.BorderRadius(10, 10, 10, 10),
            margin=ft.Margin(10, 10, 0, 10),
        ),
        icono_ajuste_container,
        icono_pdf_ordenado_container,
        icono_imponer_container,
        boton_informe_container,
        boton_nuevo_trabajo,
        boton_abrir_trabajo,
        boton_guardar_trabajo,
    )


# Función para crear el contenedor superior que incluye los iconos de menú y botón PDF (DEPRECATED - usar crear_barra_lateral_izquierda)
def crear_contenedor_superior(
    page,
    boton_informe_pdf,
    boton_toggle_tema,
    icono_ajuste_pliego,
    icono_pdf_ordenado,
    icono_imponer,
    icono_info,
):
    # Botones de archivo (abrir/guardar)
    boton_abrir_trabajo = ft.IconButton(
        icon=ft.Icons.FILE_OPEN_OUTLINED,
        tooltip=t("Cargar trabajo"),
        icon_size=24,
        on_click=lambda e: print(t("[TODO] Abrir trabajo")),
        icon_color=ICONO_PREF_COLOR,
        hover_color=ICONO_PREF_HOVER_COLOR,
    )

    boton_guardar_trabajo = ft.IconButton(
        icon=ft.Icons.SAVE_OUTLINED,
        tooltip=t("Guardar trabajo"),
        icon_size=24,
        on_click=lambda e: print(t("[TODO] Guardar trabajo")),
        icon_color=ICONO_PREF_COLOR,
        hover_color=ICONO_PREF_HOVER_COLOR,
    )

    boton_salir = ft.IconButton(
        icon=ft.Icons.EXIT_TO_APP,
        tooltip=t("Salir"),
        icon_size=24,
        on_click=lambda e: page.run_task(page.window.destroy),
        icon_color=ICONO_PREF_COLOR,
        hover_color=ICONO_PREF_HOVER_COLOR,
    )

    # Crear lista de controles para el Row
    # Orden: [Abrir][Guardar][Día/Noche][Ajuste Pliego][PDF Ordenado][Imponer][Info][Spacer][Informe PDF][Salir]
    controles_row = [
        ft.Container(boton_abrir_trabajo, width=40, alignment=ft.Alignment.CENTER_LEFT),
        ft.Container(
            boton_guardar_trabajo, width=40, alignment=ft.Alignment.CENTER_LEFT
        ),
        ft.Container(
            boton_toggle_tema,
            width=40,
            alignment=ft.Alignment.CENTER_LEFT,
            margin=ft.Margin(5, 0, 0, 0),
        ),
        ft.Container(icono_ajuste_pliego, width=40, alignment=ft.Alignment.CENTER_LEFT),
        ft.Container(icono_pdf_ordenado, width=40, alignment=ft.Alignment.CENTER_LEFT),
        ft.Container(icono_imponer, width=40, alignment=ft.Alignment.CENTER_LEFT),
        ft.Container(icono_info, width=40, alignment=ft.Alignment.CENTER_LEFT),
        ft.Container(expand=True),  # Espaciador flexible
        ft.Container(boton_informe_pdf, width=40, alignment=ft.Alignment.CENTER_RIGHT),
        ft.Container(boton_salir, width=40, alignment=ft.Alignment.CENTER_RIGHT),
    ]

    return ft.Container(
        ft.Row(
            controles_row,
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=FONDO_BARRA_SUPERIOR,  # Fondo azul claro
        padding=ft.Padding(0, 2, 5, 2),  # Espaciado interno
        border_radius=ft.BorderRadius(
            top_left=10, top_right=10, bottom_left=10, bottom_right=10
        ),  # Bordes redondeados uniformes
        margin=(
            ft.Margin(8, 10, 10, 0)
            if platform.system() == "Darwin"
            else ft.Margin(8, 10, 5, 0)
        ),  # Margen externo
        height=38,  # Altura del contenedor reducida
    )


# Función para crear el contenedor principal que agrupa las fases y el gráfico
def crear_contenedor_principal(
    columna_fase1, columna_fase2, columna_fase3, bloque_resumen_, grafico_viewer
):
    return ft.Container(
        bgcolor=FONDO_APP,
        expand=True,
        padding=0,
        margin=0,
        content=ft.Row(
            [
                # Columna de la Fase 1 (izquierda)
                columna_fase1,
                # Columna derecha: Fase 2+3 (arriba), resumen, y gráfico (expandido)
                ft.Container(
                    ft.Column(
                        [
                            # Row superior con Fase 2 y Fase 3 (textfields y dropdowns)
                            ft.Container(
                                ft.Row(
                                    [
                                        ft.Container(
                                            columna_fase2,
                                            width=325,
                                            padding=0,
                                            margin=0,
                                            height=150,
                                        ),
                                        ft.Container(
                                            columna_fase3,
                                            padding=0,
                                            margin=0,
                                            height=150,
                                            expand=True,
                                        ),
                                    ],
                                    spacing=10,
                                    alignment=ft.MainAxisAlignment.START,
                                    vertical_alignment=ft.CrossAxisAlignment.START,
                                ),
                                bgcolor=FONDO_FASE_2,
                                border_radius=10,
                                padding=ft.Padding(10, 1, 0, 0),
                                margin=ft.Margin(0, 0, 0, 10),
                                height=160,
                            ),
                            # Bloque resumen
                            ft.Container(
                                bloque_resumen_,
                                margin=ft.Margin(0, 0, 0, 10),
                            ),
                            # Gráfico (expande para ocupar TODO el resto)
                            ft.Container(
                                grafico_viewer,
                                expand=True,
                                padding=0,
                                margin=0,
                            ),
                        ],
                        spacing=0,
                        expand=True,
                    ),
                    padding=ft.Padding(10, 10, 10, 10),
                    expand=True,
                ),
            ],
            spacing=0,
        ),
    )


# Variable global para recordar la última carpeta usada para guardar PDF
_ultima_carpeta_pdf = [os.path.expanduser("~/Documents")]


def crear_filepicker_guardar_pdf(page, on_result_callback):
    """
    Muestra un FilePicker para guardar PDF. Llama a on_result_callback(ruta) si el usuario confirma.
    La ruta por defecto es la carpeta Documentos del usuario, pero recuerda la última carpeta usada durante la sesión.
    """
    # Limpiar cualquier FilePicker existente del overlay antes de crear uno nuevo
    page.overlay[:] = [
        control for control in page.overlay if not isinstance(control, ft.FilePicker)
    ]

    file_picker = ft.FilePicker()

    def on_result(e):
        try:
            if e.path:
                ruta = e.path
                if not ruta.lower().endswith(".pdf"):
                    ruta += ".pdf"
                # Actualizar la última carpeta usada
                import os

                _ultima_carpeta_pdf[0] = os.path.dirname(ruta)
                on_result_callback(ruta)
            else:
                on_result_callback(None)
        except Exception as ex:
            print(f"[ERROR on_result] {ex}")
            on_result_callback(None)
        finally:
            # Asegurar limpieza del FilePicker del overlay
            try:
                if file_picker in page.overlay:
                    page.overlay.remove(file_picker)
                page.update()
            except Exception:
                print(t("[ERROR] No se pudo limpiar FilePicker del overlay"))
                pass

    # Flet 1.0: Service auto-registra; on_result no se dispara con await → llamada manual
    page.update()

    async def _do_save():
        try:
            path = await file_picker.save_file(
                dialog_title=t("Guardar PDF"),
                file_name=t("informe_talonarios_filename"),
                initial_directory=_ultima_carpeta_pdf[0],
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["pdf"],
            )
        except Exception as ex:
            print(f"[ERROR save_file] {ex}")
            path = None
        # Flet 1.0: handlers en el loop → generar PDF fuera del loop
        await asyncio.to_thread(on_result, SimpleNamespace(path=path, files=[]))

    page.run_task(_do_save)


def crear_filepicker_seleccionar_pdf(
    page, on_result_callback, dialog_title=None, allowed_extensions=["pdf"]
):
    if dialog_title is None:
        dialog_title = t("Seleccionar PDF")
    """
    Muestra un FilePicker para seleccionar un PDF existente.
    Llama a `on_result_callback(ruta)` con la ruta seleccionada, o `None` si se cancela o hay error.
    """
    # Limpiar cualquier FilePicker existente del overlay antes de crear uno nuevo
    page.overlay[:] = [
        control for control in page.overlay if not isinstance(control, ft.FilePicker)
    ]

    file_picker = ft.FilePicker()

    def _on_result(e: ft.FilePickerResultEvent):
        try:
            if e.files and len(e.files) > 0:
                seleccion = e.files[0]
                ruta = getattr(seleccion, "path", None) or getattr(
                    seleccion, "uri", None
                )
                # Validar extensión si se pidió
                if ruta and allowed_extensions:
                    ok_ext = any(
                        ruta.lower().endswith(ext) for ext in allowed_extensions
                    )
                    if not ok_ext:
                        print(
                            f"[crear_filepicker_seleccionar_pdf] {t('Archivo seleccionado con extensión no válida:')} {ruta}"
                        )
                        on_result_callback(None)
                        return
                print(
                    f"[crear_filepicker_seleccionar_pdf] {t('Archivo seleccionado:')} {ruta}"
                )
                on_result_callback(ruta)
            else:
                print(f"[crear_filepicker_seleccionar_pdf] {t('Selección cancelada')}")
                on_result_callback(None)
        except Exception as ex:
            print(f"[crear_filepicker_seleccionar_pdf] {t('Error en on_result:')} {ex}")
            on_result_callback(None)
        finally:
            try:
                if file_picker in page.overlay:
                    page.overlay.remove(file_picker)
                page.update()
            except Exception:
                pass

    # Flet 1.0: Service auto-registra; await + shim → _on_result manual
    page.update()

    async def _do_pick():
        try:
            files = await file_picker.pick_files(
                dialog_title=dialog_title,
                allow_multiple=False,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=allowed_extensions,
            )
        except Exception as ex:
            print(
                f"[crear_filepicker_seleccionar_pdf] {t('Error al abrir selector:')} {ex}"
            )
            files = []
        # Flet 1.0: handlers en el loop → callback con fitz fuera del loop
        await asyncio.to_thread(
            _on_result,
            SimpleNamespace(
                files=files or [],
                path=(files[0].path if files else None),
            ),
        )

    page.run_task(_do_pick)


def crear_ventana_ordenar_pdfs(page):
    """AlertDialog para Ordenamiento PDF con flujo correcto."""

    # Variables para mantener el estado
    archivo_seleccionado = {"ruta": "", "nombre": "", "paginas": 0}
    ordenamiento_calculado = {"ordenamiento": None, "paginas_requeridas": 0}

    # Controles de la interfaz
    texto_archivo = ft.Text(
        t("Ningún archivo seleccionado"), size=16, color=TEXTO_COLOR_GENERICO
    )
    texto_paginas = ft.Text(t("Páginas: -"), size=16, color=TEXTO_COLOR_GENERICO)
    texto_paginas_requeridas = ft.Text(
        "", size=16, color=TEXTO_COLOR_GENERICO, visible=False
    )

    # Dropdown para número de copias
    dropdown_copias = ft.Dropdown(
        label=t("Número de copias"),
        width=150,
        value="1",
        options=[ft.dropdown.Option(str(i)) for i in range(1, 11)],
        filled=True,
        fill_color=FONDO_TEXTFIELDS_COLOR,
        color=DROPDOWN_TEXT_STYLE_COLOR,
        bgcolor=DROPDOWN_FONDO_MENU_COLOR,
        text_size=16,
        content_padding=ft.Padding(8, 0, 0, 0),
        border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR), border_radius=6),
        trailing_icon=ft.Icon(
            ft.Icons.ARROW_DROP_DOWN, color=DROPDOWN_TRAILING_ICON_COLOR
        ),
        selected_trailing_icon=ft.Icon(
            ft.Icons.ARROW_DROP_UP, color=DROPDOWN_TRAILING_ICON_COLOR
        ),
        label_style=ft.TextStyle(color=DROPDOWN_TEXT_STYLE_COLOR),
        on_select=lambda e: [recalcular_ordenamiento(), actualizar_checkbox_xerox()],
    )

    # Checkbox para generar archivo Xerox (solo visible con múltiples copias)
    checkbox_xerox = ft.Checkbox(
        label=t("Generar archivo de texto para Xerox/Fiery"),
        value=True,
        visible=False,
        fill_color=FONDO_TEXTFIELDS_COLOR,
    )

    # Dropdown para doble cara
    dropdown_doble_cara = ft.Dropdown(
        label=t("Tipo de impresión"),
        width=150,
        value="cara",
        options=[
            ft.dropdown.Option("cara", t("Una cara")),
            ft.dropdown.Option("dorso", t("Doble cara")),
        ],
        color=DROPDOWN_TEXT_STYLE_COLOR,
        bgcolor=DROPDOWN_FONDO_MENU_COLOR,
        text_size=16,
        filled=True,
        fill_color=FONDO_TEXTFIELDS_COLOR,
        content_padding=ft.Padding(8, 0, 0, 0),
        border=ft.OutlineInputBorder(side=ft.BorderSide(color=BORDE_TEXTFIELDS_COLOR), border_radius=6),
        trailing_icon=ft.Icon(
            ft.Icons.ARROW_DROP_DOWN, color=DROPDOWN_TRAILING_ICON_COLOR
        ),
        selected_trailing_icon=ft.Icon(
            ft.Icons.ARROW_DROP_UP, color=DROPDOWN_TRAILING_ICON_COLOR
        ),
        label_style=ft.TextStyle(color=DROPDOWN_TEXT_STYLE_COLOR),
        on_select=lambda e: recalcular_ordenamiento(),
    )

    # Función para actualizar la visibilidad del checkbox Xerox
    def actualizar_checkbox_xerox():
        try:
            num_copias = int(dropdown_copias.value)
            checkbox_xerox.visible = num_copias > 1
            print(
                f"[DEBUG] {t('Checkbox Xerox - Copias:')} {num_copias}, {t('Visible:')} {checkbox_xerox.visible}, {t('Marcado:')} {checkbox_xerox.value}"
            )
            checkbox_xerox.update()
        except Exception as e:
            print(f"[DEBUG] {t('Error en actualizar_checkbox_xerox:')} {e}")
            pass

    def revalidar_pdf_cargado():
        """Revalida el PDF cargado cuando cambian los parámetros."""
        if (
            not archivo_seleccionado["ruta"]
            or not ordenamiento_calculado["paginas_requeridas"]
        ):
            print(
                f"[DEBUG revalidar_pdf_cargado] {t('No hay archivo seleccionado o no hay paginas requeridas calculadas')}"
            )
            return

        paginas_pdf = archivo_seleccionado["paginas"]
        paginas_requeridas = ordenamiento_calculado["paginas_requeridas"]

        print(
            f"[DEBUG revalidar_pdf_cargado] {t('archivo=')}{archivo_seleccionado['ruta']}, {t('paginas_pdf=')}{paginas_pdf}, {t('paginas_requeridas=')}{paginas_requeridas}"
        )

        if paginas_pdf == paginas_requeridas:
            texto_validacion.value = f"✅ {t('Correcto:')} {paginas_pdf} {t('páginas')}"
            texto_validacion.color = SUCCESS_COLOR
            boton_procesar.disabled = False
            print(f"[DEBUG revalidar_pdf_cargado] {t('Botón PROCESAR habilitado')}")
        else:
            texto_validacion.value = f"❌ {t('Error: tiene')} {paginas_pdf}, {t('necesita')} {paginas_requeridas}"
            texto_validacion.color = ERROR_COLOR
            boton_procesar.disabled = True
            print(
                f"[DEBUG revalidar_pdf_cargado] {t('Botón PROCESAR deshabilitado - páginas no coinciden')}"
            )

        texto_validacion.visible = True

        try:
            texto_validacion.update()
            boton_procesar.update()
        except Exception:
            # Los controles aún no están en la página
            pass

    def recalcular_ordenamiento():
        """Recalcula el ordenamiento cuando cambian los parámetros."""
        try:
            # Verificar que tenemos los datos del gráfico
            if "orden_grafico_visual" not in grafico_datos:
                print(
                    f"[DEBUG] {t('No hay datos de orden_grafico_visual disponibles')}"
                )
                texto_paginas_requeridas.value = t(
                    "Error: Debe generar un gráfico primero"
                )
                texto_paginas_requeridas.color = ERROR_COLOR
                texto_paginas_requeridas.visible = True
                boton_cargar_pdf.visible = False
                try:
                    boton_cargar_pdf.update()
                    texto_paginas_requeridas.update()
                except Exception:
                    # Los controles aún no están en la página
                    pass
                return

            # Obtener parámetros
            num_copias = int(dropdown_copias.value)
            doble_cara = dropdown_doble_cara.value == "dorso"
            orden_grafico_visual = grafico_datos["orden_grafico_visual"]
            comienzo_numeracion = int(grafico_datos["entrada"].get("comienzo", 1))

            print(
                f"[DEBUG] {t('Recalculando ordenamiento - Copias:')} {num_copias}, {t('Doble cara:')} {doble_cara}"
            )
            print(f"[DEBUG] {t('Comienzo numeración obtenido:')} {comienzo_numeracion}")
            print(
                f"[DEBUG] {t('grafico_datos entrada completa:')} {grafico_datos.get('entrada', {})}"
            )
            print(
                f"[DEBUG] {t('orden_grafico_visual tiene')} {len(orden_grafico_visual)} {t('elementos')}"
            )

            # Generar ordenamiento para calcular páginas requeridas
            ordenamiento_pdf = generar_ordenamiento_pdf_montaje(
                orden_grafico_visual=orden_grafico_visual,
                doble_cara=doble_cara,
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
                    # Los controles aún no están en la página
                    pass
                return

            # Calcular páginas requeridas del PDF original
            # Extraer metadata y calcular resumen real (excluyendo '_metadata' como pliego)
            paginas_requeridas = None
            paginas_pdf_original = None
            if "_metadata" in ordenamiento_pdf and isinstance(
                ordenamiento_pdf["_metadata"], dict
            ):
                paginas_pdf_original = ordenamiento_pdf["_metadata"].get(
                    "paginas_pdf_original"
                )
                paginas_requeridas = paginas_pdf_original

            # Calcular número de pliegos y páginas reales generadas (excluyendo _metadata)
            num_pliegos = len(
                [k for k in ordenamiento_pdf.keys() if isinstance(k, int)]
            )
            total_paginas_generadas = sum(
                len(v.get("datos", []))
                for k, v in ordenamiento_pdf.items()
                if isinstance(k, int) and isinstance(v, dict)
            )

            # Fallback si no había metadata: páginas requeridas = máxima página referenciada en datos
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

            # Mostrar información al usuario
            texto_paginas_requeridas.value = f"📄 {t('Necesita un PDF de exactamente')} {paginas_requeridas} {t('páginas')}"
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

            # Debug/logs claros y correctos (num pliegos y páginas reales)
            print(f"[DEBUG] {t('Ordenamiento recalculado:')}")
            print(f"  - {t('Copias:')} {num_copias}, {t('Doble cara:')} {doble_cara}")
            print(f"  - {t('Páginas requeridas (orig/meta):')} {paginas_pdf_original}")
            print(f"  - {t('Pliegos generados (entradas numéricas):')} {num_pliegos}")
            print(
                f"  - {t('Páginas reales generadas (sum len(datos)):')} {total_paginas_generadas}"
            )
            print(f"  - {t('Metadata presente:')} {'_metadata' in ordenamiento_pdf}")

        except Exception as ex:
            print(f"[ERROR] {t('Error al recalcular ordenamiento:')} {ex}")
            texto_paginas_requeridas.value = f"{t('Error:')} {str(ex)}"
            texto_paginas_requeridas.color = ERROR_COLOR
            texto_paginas_requeridas.visible = True
            boton_cargar_pdf.visible = False
            try:
                boton_cargar_pdf.update()
                texto_paginas_requeridas.update()
            except Exception:
                # Los controles aún no están en la página
                pass

    # Función para manejar selección de archivo
    def on_file_picker_result(e):
        if e.files and len(e.files) > 0:
            archivo = e.files[0]
            archivo_seleccionado["ruta"] = archivo.path
            archivo_seleccionado["nombre"] = archivo.name

            # Corregido: desempaquetar correctamente el resultado
            paginas_pdf, error_pdf = contar_paginas_pdf(archivo.path)
            archivo_seleccionado["paginas"] = paginas_pdf

            # Debug adicional
            print(
                f"[DEBUG on_file_picker_result] {t('Archivo seleccionado:')} {archivo_seleccionado['ruta']} ({paginas_pdf} {t('páginas')})"
            )

            # Asegurar que cualquier FilePicker activo se retire del overlay para no bloquear eventos
            try:
                if file_picker in page.overlay:
                    page.overlay.remove(file_picker)
                    print(
                        f"[DEBUG on_file_picker_result] {t('FilePicker removido de page.overlay')}"
                    )
                page.update()
            except Exception as _ex:
                print(
                    f"[DEBUG on_file_picker_result] {t('Error al remover file_picker del overlay:')} {_ex}"
                )
                pass

            # Actualizar UI
            texto_archivo.value = f"{t('Archivo:')} {archivo.name}"
            texto_paginas.value = f"{t('Páginas en archivo:')} {paginas_pdf}"

            # Validar páginas
            paginas_requeridas = ordenamiento_calculado["paginas_requeridas"]
            print(
                f"[DEBUG on_file_picker_result] {t('paginas_requeridas (desde ordenamiento_calculado) =')} {paginas_requeridas}"
            )
            if paginas_requeridas and paginas_pdf == paginas_requeridas:
                texto_validacion.value = (
                    f"✅ {t('Correcto:')} {paginas_pdf} {t('páginas')}"
                )
                texto_validacion.color = SUCCESS_COLOR
                boton_procesar.disabled = False
                print(
                    f"[DEBUG on_file_picker_result] {t('Coinciden páginas -> habilitado procesar')}"
                )
            else:
                texto_validacion.value = f"❌ {t('Error: tiene')} {paginas_pdf}, {t('necesita')} {paginas_requeridas}"
                texto_validacion.color = ERROR_COLOR
                boton_procesar.disabled = True
                print(
                    f"[DEBUG on_file_picker_result] {t('NO coinciden páginas -> procesar sigue deshabilitado')}"
                )

            texto_validacion.visible = True

            # Actualizar todos los controles
            texto_archivo.update()
            texto_paginas.update()
            texto_validacion.update()
            boton_procesar.update()

        else:
            # Limpiar selección
            archivo_seleccionado["ruta"] = ""
            archivo_seleccionado["nombre"] = ""
            archivo_seleccionado["paginas"] = 0

            # Si viene de cancelar, también asegurar remover file_picker del overlay
            try:
                if file_picker in page.overlay:
                    page.overlay.remove(file_picker)
                    print(
                        f"[DEBUG on_file_picker_result] {t('FilePicker removido del overlay (cancelado)')}"
                    )
                page.update()
            except Exception as _ex:
                print(
                    f"[DEBUG on_file_picker_result] {t('Error al remover file_picker del overlay (cancelado):')} {_ex}"
                )
                pass

            texto_archivo.value = t("Ningún archivo seleccionado")
            texto_paginas.value = t("Páginas en archivo: ")
            texto_validacion.visible = False
            boton_procesar.disabled = True

            texto_archivo.update()
            texto_paginas.update()
            texto_validacion.update()
            boton_procesar.update()

    # FilePicker - limpiar cualquier FilePicker existente antes de crear uno nuevo
    page.overlay[:] = [
        control for control in page.overlay if not isinstance(control, ft.FilePicker)
    ]
    file_picker = ft.FilePicker()

    # Botón para cargar PDF (inicialmente oculto) — Flet 1.0: async on_click + await
    async def safe_pick_files(e):
        nonlocal file_picker
        try:
            files = await file_picker.pick_files(
                dialog_title=t("Seleccionar PDF para ordenar"),
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["pdf"],
            )
        except Exception as ex:
            print(f"[ERROR safe_pick_files] {ex}")
            try:
                file_picker = ft.FilePicker()
                files = await file_picker.pick_files(
                    dialog_title=t("Seleccionar PDF para ordenar"),
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
        # Flet 1.0: handlers en el loop → contar_paginas/leer_cajas fuera del loop
        await asyncio.to_thread(
            on_file_picker_result,
            SimpleNamespace(
                files=files or [],
                path=(files[0].path if files else None),
            ),
        )

    boton_cargar_pdf = ft.Button(
        t("Cargar PDF"),
        icon=ft.Icons.PICTURE_AS_PDF,
        width=120,
        height=35,
        visible=False,
        on_click=safe_pick_files,
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

    # Texto de validación de páginas
    texto_validacion = ft.Text("", size=16, visible=False)

    # Función para procesar el ordenamiento final
    async def procesar_ordenamiento_final(e):
        # LOG inicial para depuración
        print(
            f"[DEBUG procesar_ordenamiento_final] click recibido. archivo_seleccionado={archivo_seleccionado['ruta']}, paginas_seleccionadas={archivo_seleccionado['paginas']}, ordenamiento_presente={bool(ordenamiento_calculado['ordenamiento'])}"
        )
        if (
            not archivo_seleccionado["ruta"]
            or not ordenamiento_calculado["ordenamiento"]
        ):
            # Mensaje más explicito al usuario
            mostrar_snackbar(
                page,
                t(
                    "Debe cargar el PDF original con el número de páginas requerido antes de generar el PDF ordenado. Pulse 'Cargar PDF'."
                ),
                SNACKBAR_COLOR_ERROR,
                5000,
            )
            print(
                "[DEBUG procesar_ordenamiento_final] Abortado: falta archivo o ordenamiento"
            )
            return

        try:
            # Mostrar ProgressBar y deshabilitar botón
            progress_bar.visible = True
            texto_progreso.visible = True
            boton_procesar.disabled = True
            progress_bar.value = 0
            texto_progreso.value = t("Iniciando procesamiento...")
            progress_bar.update()
            texto_progreso.update()
            boton_procesar.update()

            num_copias = int(dropdown_copias.value)
            ordenamiento_pdf = ordenamiento_calculado["ordenamiento"]

            print(f"[SUCCESS] Procesando PDF final:")
            print(f"  - Archivo: {archivo_seleccionado['nombre']}")
            print(f"  - Ruta completa: {archivo_seleccionado['ruta']}")
            print(
                f"  - Archivo existe antes: {os.path.exists(archivo_seleccionado['ruta'])}"
            )
            print(f"  - Ordenamiento con {len(ordenamiento_pdf)} páginas")

            # Generar PDF reorganizado
            ruta_directorio = os.path.dirname(archivo_seleccionado["ruta"])
            nombre_base = os.path.splitext(archivo_seleccionado["nombre"])[0]
            ruta_pdf_reorganizado = os.path.join(
                ruta_directorio, f"{nombre_base}{t('_ordenado.pdf')}"
            )

            print(f"[DEBUG] Directorio destino: {ruta_directorio}")
            print(f"[DEBUG] Nombre base: {nombre_base}")
            print(f"[DEBUG] PDF reorganizado: {ruta_pdf_reorganizado}")

            # Función callback para actualizar el progreso
            # Flet 1.0: reorganizar_pdf_real corre en to_thread → marshal UI al loop
            def actualizar_progreso(pagina_actual, total_paginas):
                if total_paginas == 0:
                    return

                progreso = pagina_actual / total_paginas

                # Throttling: solo actualizar cada 1% o en la última página
                if not hasattr(actualizar_progreso, "_ultimo_progreso"):
                    actualizar_progreso._ultimo_progreso = 0

                diferencia = progreso - actualizar_progreso._ultimo_progreso
                if diferencia >= 0.01 or pagina_actual == total_paginas:
                    actualizar_progreso._ultimo_progreso = progreso
                    page.run_task(
                        pintar_progreso, progreso, pagina_actual, total_paginas
                    )

            async def pintar_progreso(progreso, pagina_actual, total_paginas):
                progress_bar.value = progreso
                texto_progreso.value = t("Procesando página {0} de {1}").format(
                    pagina_actual, total_paginas
                )
                progress_bar.update()
                texto_progreso.update()

            # Reorganizar el PDF usando PyPDF2 con callback de progreso
            exito_pdf = await asyncio.to_thread(
                reorganizar_pdf_real,
                pdf_origen=archivo_seleccionado["ruta"],
                pdf_destino=ruta_pdf_reorganizado,
                ordenamiento_pdf=ordenamiento_pdf,
                callback_progreso=actualizar_progreso,
            )

            print(
                f"[DEBUG] Archivo original existe después: {os.path.exists(archivo_seleccionado['ruta'])}"
            )

            if not exito_pdf:
                # Ocultar ProgressBar en caso de error
                progress_bar.visible = False
                texto_progreso.visible = False
                boton_procesar.disabled = False
                progress_bar.update()
                texto_progreso.update()
                boton_procesar.update()
                mostrar_snackbar(
                    page, t("Error al reorganizar el PDF"), SNACKBAR_COLOR_ERROR, 3000
                )
                return

            # Completar ProgressBar
            progress_bar.value = 1.0
            texto_progreso.value = t("PDF generado exitosamente")
            progress_bar.update()
            texto_progreso.update()

            print(f"[SUCCESS] PDF reorganizado: {ruta_pdf_reorganizado}")

            # Debug: estado del checkbox y decisión de archivo Xerox
            print(
                f"[DEBUG] Procesamiento Xerox - Copias: {num_copias}, Checkbox visible: {checkbox_xerox.visible}, Checkbox marcado: {checkbox_xerox.value}"
            )

            # Si hay múltiples copias y el checkbox está marcado, generar archivo para Xerox
            if num_copias > 1 and checkbox_xerox.value:
                print(f"[DEBUG] Generando archivo Xerox - condiciones cumplidas")
                texto_progreso.value = t("Generando archivo Fiery - Xerox...")
                texto_progreso.update()

                ruta_xerox = os.path.join(
                    ruta_directorio,
                    f"{nombre_base}{t('_fiery-xerox.txt')}",
                )

                # Intentar obtener las listas Fiery que generó reorganizar_pdf_real
                try:
                    import pdf_manipulator as pm

                    listas_fiery = getattr(pm, "fiery_data", None)
                    print(
                        f"[DEBUG] listas_fiery obtenidas desde pdf_manipulator: {bool(listas_fiery)}"
                    )
                except Exception:
                    listas_fiery = None

                # Fallback: si no existen, generar con la función clásica
                if not listas_fiery:
                    print(
                        f"[DEBUG] No hay listas desde pdf_manipulator, generando con generar_listas_fiery(...)"
                    )
                    listas_fiery = generar_listas_fiery(ordenamiento_pdf)

                # Continuar con generación de archivo Xerox/Fiery usando listas_fiery
                if listas_fiery:
                    exito_xerox = generar_archivo_xerox_manual(listas_fiery, ruta_xerox)
                    if exito_xerox:
                        print(f"[SUCCESS] Archivo Xerox generado: {ruta_xerox}")
                        mostrar_snackbar(
                            page,
                            t("PDF generado en: {0}").format(ruta_pdf_reorganizado),
                            SNACKBAR_COLOR_FONDO,
                            4000,
                        )
                    else:
                        print(f"[ERROR] Falló la generación del archivo Xerox")
                        mostrar_snackbar(
                            page,
                            t("PDF ordenado generado, pero falló el archivo Xerox"),
                            SNACKBAR_COLOR_ERROR,
                            4000,
                        )
                else:
                    print(f"[ERROR] No se generaron listas Fiery")
                    mostrar_snackbar(
                        page,
                        t(
                            "PDF ordenado generado, pero no se pudieron generar las listas Xerox"
                        ),
                        SNACKBAR_COLOR_ERROR,
                        4000,
                    )
            elif num_copias > 1:
                print(
                    f"[DEBUG] Múltiples copias pero checkbox no marcado - solo mostrando listas en consola"
                )
                # Solo mostrar el mensaje sobre las listas disponibles
                listas_fiery = generar_listas_fiery(ordenamiento_pdf)

                # Mostrar las listas disponibles en debug
                print(f"[DEBUG] === LISTAS FIERY DISPONIBLES ===")
                for copia, paginas in sorted(listas_fiery.items()):
                    paginas_str = ",".join(map(str, paginas))
                    if _PRINT_DEBUG:
                        print(f"[DEBUG] Copia {copia}: {paginas_str}")
                print(f"[DEBUG] === FIN LISTAS FIERY ===")

                mostrar_snackbar(
                    page,
                    t("PDF generado en: {0}").format(ruta_pdf_reorganizado),
                    SNACKBAR_COLOR_FONDO,
                    4000,
                )
            else:
                print(f"[DEBUG] Una sola copia - no se generan listas Xerox")
                mostrar_snackbar(
                    page,
                    t("PDF generado en: {0}").format(ruta_pdf_reorganizado),
                    SNACKBAR_COLOR_FONDO,
                    4000,
                )

            # Ocultar ProgressBar y cerrar el diálogo con delay
            async def cerrar_dialog_async():
                await asyncio.sleep(1.5)
                page.pop_dialog()

            page.run_task(cerrar_dialog_async)

        except Exception as ex:
            print(f"[ERROR] Error al procesar ordenamiento final: {ex}")
            # Ocultar ProgressBar y reactivar botón en caso de error
            progress_bar.visible = False
            texto_progreso.visible = False
            boton_procesar.disabled = False
            progress_bar.update()
            texto_progreso.update()
            boton_procesar.update()
            mostrar_snackbar(
                page,
                t("Error al procesar: {0}").format(str(ex)),
                SNACKBAR_COLOR_ERROR,
                3000,
            )

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

    # Botón para procesar (inicialmente deshabilitado)
    boton_procesar = ft.Button(
        t("Generar PDF Ordenado"),
        expand=True,  # Hacer que el botón expanda para ocupar todo el espacio
        icon=ft.Icons.PICTURE_AS_PDF,
        width=200,
        height=40,
        # Flet 1.0: procesar_ordenamiento_final es async → correr en el loop
        on_click=lambda e: page.run_task(procesar_ordenamiento_final, e),
        disabled=True,
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

    # Crear el diálogo (colores adaptados según tema)
    dialog = ft.AlertDialog(
        modal=True,
        bgcolor=FONDO_ALERT_DIALOG,
        title=ft.Text(
            t("Ordenamiento y duplicado de páginas PDF"),
            weight=ft.FontWeight.BOLD,
            size=18,
            text_align=ft.TextAlign.CENTER,
            color=TEXTO_COLOR_GENERICO,
        ),
        content=ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        t("Configure los parámetros de ordenamiento.\n\n")
                        + t(
                            "Número de copias: genera copias adicionales de cada pliego.\n"
                        )
                        + t("Tipo de impresión: 'una cara' o 'doble cara'.\n")
                        + t(
                            "El 'tipo de impresión' tiene que coincidir con el PDF a cargar."
                        ),
                        size=16,
                        color=TEXTO_COLOR_GENERICO,
                    ),
                    # Sección de opciones (PRIMERA) - Contenedor fijo
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Row(
                                    [dropdown_copias, dropdown_doble_cara],
                                    alignment=ft.MainAxisAlignment.START,
                                ),
                                # Checkbox para archivo Xerox (siempre presente pero visible solo cuando necesario)
                                checkbox_xerox,
                            ],
                            spacing=8,
                        ),
                        height=80,  # Altura fija para evitar movimiento
                        alignment=ft.Alignment.TOP_LEFT,
                    ),
                    # Información de páginas requeridas - Contenedor fijo
                    ft.Container(
                        content=texto_paginas_requeridas,
                        height=30,  # Altura fija
                        alignment=ft.Alignment.CENTER_LEFT,
                    ),
                    ft.Divider(color=TEXTO_COLOR_GENERICO),
                    # Sección de carga de PDF (SEGUNDA, después de configurar) - Contenedor fijo
                    ft.Container(
                        content=ft.Column(
                            [
                                boton_cargar_pdf,
                                ft.Container(height=5),
                                texto_archivo,
                                texto_paginas,
                                texto_validacion,
                                ft.Container(height=10),
                                ft.Divider(color=TEXTO_COLOR_GENERICO),
                            ],
                            spacing=8,
                        ),
                        height=120,  # Altura fija para evitar movimiento
                        alignment=ft.Alignment.TOP_LEFT,
                    ),
                    # Espacio reservado para el botón (ahora está en actions)
                    ft.Container(height=20),
                ],
                spacing=12,
            ),
            width=500,
            height=420,  # Reducir altura ya que quitamos el botón del contenido
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
                            height=60,  # Altura fija para evitar movimiento
                            alignment=ft.Alignment.CENTER,
                        ),
                        # Botones
                        boton_procesar,
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
    async def on_dialog_open():
        await asyncio.sleep(0.1)
        recalcular_ordenamiento()
        actualizar_checkbox_xerox()

    # Flet 1.0: correr en el loop para que los updates sean seguros
    page.run_task(on_dialog_open)

    return dialog


def abrir_pdf_ordenado_y_luego_imposicion(
    page,
    on_guardar_trabajo=None,
    initial_project_modified=False,
    initial_project_path=None,
    initial_project_name="Sin título",
):
    """
    Abre el diálogo de PDF ordenado.
    Por ahora, solo abre el diálogo nuevo.
    En el futuro, cuando el usuario confirme, abrirá la ventana de imposición.
    """
    print("[FUNCIÓN] abrir_pdf_ordenado_y_luego_imposicion() llamada")
    if crear_ventana_pdf_ordenado:
        print("[FUNCIÓN] Llamando a crear_ventana_pdf_ordenado()...")
        try:
            crear_ventana_pdf_ordenado(
                page,
                on_guardar_trabajo,
                initial_project_modified,
                initial_project_path,
                initial_project_name,
            )
            print("[FUNCIÓN] ✅ crear_ventana_pdf_ordenado() completada exitosamente")
        except Exception as ex:
            print(f"[FUNCIÓN] ❌ ERROR en crear_ventana_pdf_ordenado(): {ex}")
            import traceback

            traceback.print_exc()
    else:
        print("[FUNCIÓN] ❌ crear_ventana_pdf_ordenado no está disponible")
        mostrar_snackbar(
            page, t("Módulo PDF ordenado no disponible"), SNACKBAR_COLOR_ERROR, 3000
        )
