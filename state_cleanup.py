"""
Centraliza las funciones de limpieza del estado de la aplicación.
"""
from lang import t

def limpiar_todo_estado():
    """Llama a las rutinas de limpieza de `pdf_ordenado_ui` e `impo_ui`.
    Esta función intenta restaurar un estado limpio antes de cargar/crear
    un nuevo trabajo.
    """
    # Limpiar estado de PDF ordenado y caches asociados
    try:
        from pdf_ordenado_ui import limpiar_estado_pdf_ordenado, limpiar_temp_sesion
        try:
            limpiar_estado_pdf_ordenado()
        except Exception:
            pass
        try:
            limpiar_temp_sesion()
        except Exception:
            pass
    except Exception:
        # Si no está disponible el módulo, ignorar (se ejecutará en entorno de UI)
        pass

    # Limpiar estado de imposición
    try:
        import impo_ui
        try:
            impo_ui.limpiar_estado_imposicion()
        except Exception:
            pass
        # Intentar forzar reseteo de banderas internas si existen
        try:
            impo_ui._estado_impo_ui["trabajo_modificado"] = False
        except Exception:
            pass
        try:
            impo_ui._pdf_stamp = None
        except Exception:
            pass
        try:
            impo_ui._PDF_VALIDATED = False
        except Exception:
            pass
        try:
            impo_ui._ordenamiento_calculado = {"ordenamiento": None, "paginas_requeridas": 0}
        except Exception:
            pass
        try:
            impo_ui._pdf_ordenado_actual = None
        except Exception:
            pass
        # Asegurar que las globals críticas también se reinicien (defensa en profundidad)
        try:
            impo_ui.TAMANO_USUARIO_W = impo_ui._estado_impo_ui.get("tamano_usuario_w", 210.0)
            impo_ui.TAMANO_USUARIO_H = impo_ui._estado_impo_ui.get("tamano_usuario_h", 100.0)
            impo_ui.SANGRE = impo_ui._estado_impo_ui.get("sangre", 0.0)
        except Exception:
            try:
                impo_ui.TAMANO_USUARIO_W = 210.0
                impo_ui.TAMANO_USUARIO_H = 100.0
                impo_ui.SANGRE = 0.0
            except Exception:
                pass
        # Asegurar limpieza de campos dentro de _estado_impo_ui que puedan
        # inducir a `pdf_ordenado_ui` a restaurar un ordenamiento vacío.
        try:
            estado = impo_ui._estado_impo_ui
            if isinstance(estado, dict):
                estado["pdf_stamp"] = None
                estado["ordenamiento"] = None
                estado["ordenamiento_paginas_requeridas"] = 0
                estado["archivo_seleccionado"] = {"nombre_archivo": "", "ruta_original": "", "num_paginas": 0}
                estado["pdf_nombre_archivo"] = ""
                estado["pdf_ruta_original"] = ""
                estado["pdf_paginas"] = 0
        except Exception:
            pass
        # Reinicializar objeto _archivo_seleccionado usado en impo_ui
        try:
            impo_ui._archivo_seleccionado = {"ruta": "", "nombre": "", "paginas": 0, "ruta_original": ""}
        except Exception:
            pass
    except Exception:
        pass
