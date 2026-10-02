"""
Sistema de gestión de archivos de trabajo para TalNumStack
Maneja guardar/cargar proyectos con timestamp para control de modificaciones
"""
import json
import gzip
import os
from datetime import datetime
from typing import Optional, Dict, Any
import copy
from lang import t

_PRINT_DEBUG = False
if not _PRINT_DEBUG:
    def _no_print(*args, **kwargs):
        return None

    print = _no_print
    
# Control de prints de depuración en este módulo
_PRINT_DEBUG = False

# Guard interno para evitar reentradas en la restauración de imposición
_RESTORING = False

# Control para escribir o no la copia JSON de depuración junto al .tns
# Ponlo a True si quieres volver a generar la copia JSON para debugging.
WRITE_DEBUG_JSON = False

def crear_datos_trabajo(
    # Fase 1
    cantidad: str,
    can_hojas_tal: str,
    # Fase 2
    hojas_x_pliego: str,
    # Fase 3
    comienzo_numeracion: str,
    horizontal: str,
    vertical: str,
    orientacion: str,
    # Gráfico
    grafico_datos: Dict[Any, Any],
    # Ajustes activos
    ajuste_activo: Dict[str, Any],
    # Datos de imposición (opcional - None si no hay imposición activa)
    imposicion_data: Optional[Dict[str, Any]] = None,
    ajuste_pliego_modo: str = "Auto",
) -> Dict[str, Any]:
    """
    Crea un diccionario con todos los datos del trabajo actual.
    
    Args:
        imposicion_data: Dict completo con TODOS los datos de impo_ui si hay imposición activa.
                        Estructura esperada (ver obtener_datos_imposicion_activa en impo_ui):
                        {
                            'pdf_path': str,                    # Ruta del PDF cargado
                            'tipo_impresion': str,              # "Una cara" / "Doble cara"
                            'TAMANO_USUARIO_W': float,          # Ancho usuario (mm)
                            'TAMANO_USUARIO_H': float,          # Alto usuario (mm)
                            'SANGRE': float,                    # Sangre (mm)
                            'GRID_COLS': int,                   # Columnas del grid
                            'GRID_ROWS': int,                   # Filas del grid
                            'CALLES_L': list,                   # Lista de calles
                            'USER_OFFSET_IMAGEN_X_MM': float,   # Offset imagen X
                            'USER_OFFSET_IMAGEN_Y_MM': float,   # Offset imagen Y
                            'TAMANO_TRAZADO': dict,             # {'w_mm': float, 'h_mm': float}
                            'TAMANO_FINAL_PLIEGO': dict,        # {'w_mm': float, 'h_mm': float}
                            'USER_OFFSET_TRAZADO_X_MM': float,  # Offset trazado X
                            'USER_OFFSET_TRAZADO_Y_MM': float,  # Offset trazado Y
                            'PLIEGO_CONGELADO': bool,           # Si pliego está congelado
                            'LONGITUD_CRUZ_MM': float,          # Longitud cruces
                            'GROSOR_CRUZ_PT': float,            # Grosor cruces
                            'OFFSET_CRUZ_MM': float,            # Offset cruces
                            'OFFSET_SEGURIDAD_MM': float,       # Offset seguridad
                            'LONGITUD_BRAZO_MAX_MM': float,     # Longitud brazo max
                            'MARCA_TEXTO_CONTENIDO': str,       # Contenido marca texto
                            'MARCA_TEXTO_POS_*': bool,          # 8 posiciones diferentes
                            'MARCA_TEXTO_ROTACION': int,        # Rotación texto
                            'MARCA_TEXTO_FAMILIA': str,         # Fuente
                            'MARCA_TEXTO_TIPO': str,            # Tipo fuente
                            'MARCA_TEXTO_CUERPO': int,          # Tamaño fuente
                            'MARCA_TEXTO_OFFSET_H_MM': float,   # Offset horizontal
                            'MARCA_TEXTO_OFFSET_V_MM': float,   # Offset vertical
                        }
    
    Returns:
        Diccionario con estructura completa del trabajo
    """
    trabajo_data = {
        "version": "1.1",  # Incrementado para soportar datos completos de imposición
        "timestamp": datetime.now().isoformat(),
        
        # Fase 1: Datos básicos
        "fase1": {
            "cantidad": cantidad,
            "can_hojas_tal": can_hojas_tal,
        },
        
        # Fase 2: Configuración de pliego
        "fase2": {
            "hojas_x_pliego": hojas_x_pliego,
        },
        
        # Fase 3: Trazado
        "fase3": {
            "comienzo_numeracion": comienzo_numeracion,
            "horizontal": horizontal,
            "vertical": vertical,
            "orientacion": orientacion,
        },
        
        # Datos del gráfico
        "grafico": grafico_datos,
        
        # Ajustes activos (recálculos)
        "ajustes": ajuste_activo,
        
        # Datos de imposición (TODOS los datos de impo_ui si hay imposición activa)
        "imposicion": imposicion_data if imposicion_data else None,
        # Estado del modo de ajuste por pliego
        "ajuste_pliego_modo": ajuste_pliego_modo,
    }
    
    return trabajo_data


def guardar_trabajo_json(trabajo_data: Dict[str, Any], file_path: str) -> bool:
    """
    Guarda el trabajo en formato JSON (sin comprimir - para depuración).
    NOTA: El método principal es guardar_trabajo_tns que usa compresión.
    
    Args:
        trabajo_data: Diccionario con los datos del trabajo
        file_path: Ruta completa del archivo
    
    Returns:
        True si se guardó correctamente, False si hubo error
    """
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(trabajo_data, f, indent=2, ensure_ascii=False)
        
        print(f"[SAVE] Trabajo guardado (JSON) en: {file_path}")
        return True
        
    except Exception as ex:
        print(f"[ERROR] Error al guardar trabajo: {ex}")
        import traceback
        traceback.print_exc()
        return False


def guardar_trabajo_tns(trabajo_data: Dict[str, Any], file_path: str) -> bool:
    """
    Guarda el trabajo en formato binario comprimido (.tns).
    Similar al formato .pnb de PageNumber.
    Este es el método principal de guardado.
    
    Args:
        trabajo_data: Diccionario con los datos del trabajo
        file_path: Ruta completa del archivo (debe terminar en .tns)
    
    Returns:
        True si se guardó correctamente, False si hubo error
    """
    try:
        # Asegurar extensión correcta
        if not file_path.endswith('.tns'):
            file_path += '.tns'
        
        # Antes de serializar, sanitizar datos de imposición para eliminar
        # rutas y recursos temporales que no deben persistir en el .tns
        trabajo_copy = copy.deepcopy(trabajo_data)
        try:
            # Sanitizar imposición
            if trabajo_copy.get('imposicion'):
                trabajo_copy['imposicion'] = _sanitize_imposicion_data(trabajo_copy['imposicion'])
                print("[SAVE] Sanitizado datos de imposición antes de guardar (.tns)")
        except Exception as ex:
            print(f"[WARN] Error sanitizando imposición antes de guardar: {ex}")

        # No persistir datos generados automáticamente (p. ej. 'grafico')
        if 'grafico' in trabajo_copy:
            try:
                trabajo_copy.pop('grafico', None)
                print("[SAVE] Eliminada clave 'grafico' del archivo guardado (se regenerará al abrir)")
            except Exception:
                pass

        # Construir una versión minimal del trabajo para persistir (solo claves requeridas, en orden)
        def _build_minimal_trabajo(tdata: Dict[str, Any]) -> Dict[str, Any]:
            # Mantener el orden de inserción para que el JSON de depuración siga el orden solicitado
            minimal = {}
            minimal["version"] = tdata.get("version", "1.1")
            minimal["timestamp"] = tdata.get("timestamp", "")
            # Fases
            minimal["fase1"] = tdata.get("fase1", {})
            minimal["fase2"] = tdata.get("fase2", {})
            minimal["fase3"] = tdata.get("fase3", {})
            # Estado del modo de ajuste por pliego
            if "ajuste_pliego_modo" in tdata:
                minimal["ajuste_pliego_modo"] = tdata["ajuste_pliego_modo"]

            # Generar imposición minimal
            impos = tdata.get("imposicion") or {}
            gen = {}
            # tipo_impresion
            if impos.get("tipo_impresion") is not None:
                gen["tipo_impresion"] = impos.get("tipo_impresion")
            # paginas_requeridas
            if impos.get("paginas_requeridas") is not None:
                gen["paginas_requeridas"] = impos.get("paginas_requeridas")

            # Archivo seleccionado (metadata + boxes page 0)
            archivo = impos.get("archivo_seleccionado") or {}
            arch_min = {
                "nombre_archivo": archivo.get("nombre_archivo", archivo.get("nombre", "")),
                "ruta_original": archivo.get("ruta_original", ""),
                "num_paginas": archivo.get("num_paginas", archivo.get("paginas", 0)),
                "mediabox": None,
                "cropbox": None,
                "bleedbox": None,
            }
            try:
                boxes = archivo.get("boxes_by_page") or {}
                if isinstance(boxes, dict) and 0 in boxes:
                    p0 = boxes[0] if 0 in boxes else boxes.get("0")
                    if p0:
                        arch_min["mediabox"] = p0.get("mediabox")
                        arch_min["cropbox"] = p0.get("cropbox")
                        arch_min["bleedbox"] = p0.get("bleedbox")
            except Exception:
                pass

            gen["archivo_seleccionado"] = arch_min

            # Lista de campos adicionales en el orden deseado (si existen en impos)
            ordered_fields = [
                "TAMANO_USUARIO_W",
                "TAMANO_USUARIO_H",
                "SANGRE",
                "CALLES_L",
                "USER_OFFSET_IMAGEN_X_MM",
                "USER_OFFSET_IMAGEN_Y_MM",
                "USER_OFFSET_TRAZADO_X_MM",
                "USER_OFFSET_TRAZADO_Y_MM",
                "LONGITUD_CRUZ_MM",
                "GROSOR_CRUZ_PT",
                "OFFSET_CRUZ_MM",
                "AUTO_SANGRE_OFFSET_CRUZ",
                "OFFSET_SEGURIDAD_MM",
                "LONGITUD_BRAZO_MAX_MM",
            ]

            # TAMANO_FINAL_PLIEGO con PLIEGO_CONGELADO incluido
            if "TAMANO_FINAL_PLIEGO" in impos:
                tfp = impos.get("TAMANO_FINAL_PLIEGO") or {}
                gen["TAMANO_FINAL_PLIEGO"] = {
                    "w_mm": tfp.get("w_mm"),
                    "h_mm": tfp.get("h_mm"),
                    "PLIEGO_CONGELADO": impos.get("PLIEGO_CONGELADO", tfp.get("PLIEGO_CONGELADO", False)),
                }

            for f in ordered_fields:
                if f in impos:
                    gen[f] = impos.get(f)

            # Marcas de texto y checkboxes (agregar si existen)
            marca_keys = [
                "MARCA_TEXTO_POS_SUP_IZQ", "MARCA_TEXTO_POS_SUP_DER", "MARCA_TEXTO_POS_INF_IZQ", "MARCA_TEXTO_POS_INF_DER",
                "MARCA_TEXTO_POS_CENTRO_SUP", "MARCA_TEXTO_POS_CENTRO_INF", "MARCA_TEXTO_POS_CENTRO_LAT_IZQ", "MARCA_TEXTO_POS_CENTRO_LAT_DER",
                "MARCA_TEXTO_ROTACION", "MARCA_TEXTO_FAMILIA", "MARCA_TEXTO_TIPO", "MARCA_TEXTO_CUERPO", "MARCA_TEXTO_COLOR",
                "MARCA_TEXTO_OFFSET_H_MM", "MARCA_TEXTO_OFFSET_V_MM",
            ]
            for k in marca_keys:
                if k in impos:
                    gen[k] = impos.get(k)

            # Buscar valores de checkbox en 'impos' y, si no están allí,
            # buscar recursivamente en todo el dict de trabajo (por ejemplo en el stamp).
            # Usamos un sentinel para distinguir "no encontrado" de "encontrado con valor False".
            _NOT_FOUND = object()

            def _find_key_recursive(obj, target_key):
                if isinstance(obj, dict):
                    if target_key in obj:
                        return obj[target_key]
                    for v in obj.values():
                        res = _find_key_recursive(v, target_key)
                        if res is not _NOT_FOUND:
                            return res
                elif isinstance(obj, list):
                    for item in obj:
                        res = _find_key_recursive(item, target_key)
                        if res is not _NOT_FOUND:
                            return res
                return _NOT_FOUND

            checkbox_map = [
                ("CHECK_BOX_CRUCES_Y_MARCAS", "checkbox_cruces"),
                ("CHECK_BOX_LINEAS_DE_CORTE", "checkbox_lineas_corte"),
                ("CHECK_BOX_MARCAS_DE_TEXTO", "checkbox_marcas_texto"),
                ("CHECK_BOX_LINEA_EXTERIOR", "checkbox_linea_exterior"),
            ]
            for out_key, in_key in checkbox_map:
                # Preferir el valor explícito en 'impos'
                if in_key in impos:
                    gen[out_key] = impos[in_key]
                elif out_key in impos:
                    gen[out_key] = impos[out_key]
                else:
                    # Buscar en todo el trabajo (p. ej. dentro del stamp)
                    found = _find_key_recursive(tdata, in_key)
                    if found is not _NOT_FOUND:
                        gen[out_key] = found

            minimal["generar_imposicion"] = gen
            return minimal

        # Convertir a JSON y comprimir usando la versión minimal
        minimal_trabajo = _build_minimal_trabajo(trabajo_copy)
        json_data = json.dumps(minimal_trabajo, ensure_ascii=False, indent=2)

        # Además, guardar una copia JSON sin comprimir al lado del .tns para depuración
        try:
            if WRITE_DEBUG_JSON:
                json_path = file_path if not file_path.endswith('.tns') else file_path[:-4] + '.json'
                with open(json_path, 'w', encoding='utf-8') as jf:
                    jf.write(json_data)
                print(f"[SAVE] Copia JSON sin comprimir escrita en: {json_path}")
        except Exception as ex_json:
            print(f"[WARN] No se pudo escribir copia JSON: {ex_json}")

        compressed_data = gzip.compress(json_data.encode('utf-8'))
        
        with open(file_path, 'wb') as f:
            f.write(compressed_data)
        
        print(f"[SAVE] Trabajo guardado (comprimido) en: {file_path}")
        # Intentar notificar a listeners globales y a la UI de imposición
        try:
            import builtins, threading
            print("[TRAB_MANAGER SYNC] notificando listeners globales y actualizando impo_ui")
            cb = getattr(builtins, '_on_trabajo_modificado_change', None)
            if callable(cb):
                try:
                    cb()
                except Exception:
                    pass
            upd = getattr(builtins, '_update_project_state_ui', None)
            if callable(upd):
                try:
                    upd()
                except Exception:
                    pass

            # Intentar llamar a la actualización de impo directamente (inmediato + retrasos)
            try:
                from importlib import import_module
                import builtins
                # Intentar localizar la función en el módulo impo_ui
                try:
                    impo_ui = import_module('impo_ui')
                    fn = getattr(impo_ui, 'update_project_state_ui', None)
                    if not callable(fn):
                        fn = getattr(impo_ui, '_impo_update_project_state_ui', None)
                except Exception:
                    fn = None

                # Llamadas si tenemos la función
                if callable(fn):
                    try:
                        fn()
                    except Exception:
                        pass
                    # No programar llamadas en background threads; solo llamada inmediata
                else:
                    # Fallback: intentar forzar update sobre builtins._impo_page si existe
                    try:
                        p = getattr(builtins, '_impo_page', None)
                        if p is not None:
                            try:
                                p.update()
                            except Exception:
                                pass
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception:
            pass
        return True
        
    except Exception as ex:
        print(f"[ERROR] Error al guardar trabajo: {ex}")
        import traceback
        traceback.print_exc()
        return False


def cargar_trabajo_json(file_path: str) -> Optional[Dict[str, Any]]:
    """
    Carga un trabajo desde archivo JSON.
    
    Args:
        file_path: Ruta completa del archivo
    
    Returns:
        Diccionario con los datos del trabajo, o None si hubo error
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            trabajo_data = json.load(f)
        
        print(f"[LOAD] Trabajo cargado desde: {file_path}")
        print(f"[LOAD] Versión: {trabajo_data.get('version', 'N/A')}")
        print(f"[LOAD] Timestamp: {trabajo_data.get('timestamp', 'N/A')}")
        
        return trabajo_data
        
    except Exception as ex:
        print(f"[ERROR] Error al cargar trabajo: {ex}")
        import traceback
        traceback.print_exc()
        return None


def cargar_trabajo_tns(file_path: str) -> Optional[Dict[str, Any]]:
    """
    Carga un trabajo desde archivo binario comprimido (.tns).
    
    Args:
        file_path: Ruta completa del archivo
    
    Returns:
        Diccionario con los datos del trabajo, o None si hubo error
    """
    try:
        with open(file_path, 'rb') as f:
            compressed_data = f.read()
        
        # Descomprimir y parsear JSON
        json_data = gzip.decompress(compressed_data).decode('utf-8')
        trabajo_data = json.loads(json_data)
        
        print(f"[LOAD] Trabajo cargado (comprimido) desde: {file_path}")
        print(f"[LOAD] Versión: {trabajo_data.get('version', 'N/A')}")
        print(f"[LOAD] Timestamp: {trabajo_data.get('timestamp', 'N/A')}")
        
        if _PRINT_DEBUG:
            # IMPRIMIR CONTENIDO COMPLETO DEL ARCHIVO CARGADO
            print("="*80)
            print("[LOAD] >>>>>> CONTENIDO COMPLETO DEL ARCHIVO CARGADO <<<<<<")
            print("="*80)
            import json as json_module
            print(json_module.dumps(trabajo_data, indent=2, ensure_ascii=False))
            print("="*80)
            print("[LOAD] >>>>>> FIN CONTENIDO ARCHIVO <<<<<<")
            print("="*80)
            
        return trabajo_data
        
    except Exception as ex:
        print(f"[ERROR] Error al cargar trabajo comprimido: {ex}")
        import traceback
        traceback.print_exc()
        return None


def cargar_trabajo_auto(file_path: str) -> Optional[Dict[str, Any]]:
    """
    Carga un trabajo detectando automáticamente el formato.
    Primero intenta formato comprimido (.tns), si falla intenta JSON plano.
    
    Args:
        file_path: Ruta completa del archivo
    
    Returns:
        Diccionario con los datos del trabajo, o None si hubo error
    """
    # Intentar primero como archivo comprimido
    try:
        return cargar_trabajo_tns(file_path)
    except:
        # Si falla, intentar como JSON plano (retrocompatibilidad)
        print(f"[LOAD] No es formato comprimido, intentando JSON plano...")
        # return cargar_trabajo_json(file_path)
        return


def crear_snapshot_estado(
    cantidad: str,
    can_hojas_tal: str,
    hojas_x_pliego: str,
    comienzo_numeracion: str,
    horizontal: str,
    vertical: str,
    orientacion: str,
) -> str:
    """
    Crea un hash del estado actual para detectar modificaciones.
    Similar al sistema de PageNumber.
    
    Returns:
        String hash del estado actual
    """
    import hashlib
    
    estado_str = f"{cantidad}|{can_hojas_tal}|{hojas_x_pliego}|{comienzo_numeracion}|{horizontal}|{vertical}|{orientacion}"
    return hashlib.md5(estado_str.encode()).hexdigest()


def _sanitize_imposicion_data(imposicion: Dict[str, Any]) -> Dict[str, Any]:
    """
    Elimina claves temporales y rutas absolutas de los datos de imposición
    para que el .tns no contenga paths específicos del equipo.

    - Quita: 'ruta', 'imagenes_secuenciales', 'pdf_ordenado_ruta', 'pdf_ruta'
    - Normaliza nombres con sufijos '_temp' o '_ordenado_temp'
    - Mantiene metadata necesaria: nombre_archivo, paginas, boxes_by_page, ruta_original
    """
    try:
        imp = copy.deepcopy(imposicion)

        # Si viene anidado bajo clave distinta, trabajar sobre el dict principal
        # Archivo seleccionado: puede estar bajo 'archivo_seleccionado'
        archivo = imp.get('archivo_seleccionado') or imp.get('archivo') or {}
        if isinstance(archivo, dict):
            # Eliminar claves temporales
            for k in ['ruta', 'imagenes_secuenciales', 'pdf_ordenado_ruta', 'pdf_ruta', 'imagenes']:
                if k in archivo:
                    archivo.pop(k, None)

            # Normalizar nombre de archivo si contiene sufijos temporales
            nombre = archivo.get('nombre_archivo', archivo.get('nombre', ''))
            if isinstance(nombre, str):
                if nombre.endswith('_ordenado_temp.pdf'):
                    nombre = nombre[:-len('_ordenado_temp.pdf')] + '.pdf'
                elif nombre.endswith('_temp.pdf'):
                    nombre = nombre[:-len('_temp.pdf')] + '.pdf'
                archivo['nombre_archivo'] = nombre
                archivo['nombre'] = nombre

            # Reconstruir archivo persistible limpio
            archivo_clean = {
                'nombre_archivo': archivo.get('nombre_archivo', ''),
                'nombre': archivo.get('nombre', ''),
                'num_paginas': archivo.get('num_paginas', archivo.get('paginas', 0)),
                'paginas': archivo.get('paginas', archivo.get('num_paginas', 0)),
                'boxes_by_page': archivo.get('boxes_by_page', {}),
                'ruta_original': archivo.get('ruta_original', '')
            }
            imp['archivo_seleccionado'] = archivo_clean

        # Eliminar cualquier path que apunte a la carpeta de temporales de la app
        def _remove_temp_paths(obj):
            if isinstance(obj, dict):
                for key in list(obj.keys()):
                    val = obj[key]
                    if isinstance(val, str):
                        if 'Library/Application Support/TalNumStack' in val or val.endswith('.png') or val.endswith('_temp.pdf'):
                            obj.pop(key, None)
                    else:
                        _remove_temp_paths(val)
            elif isinstance(obj, list):
                for i, v in enumerate(list(obj)):
                    if isinstance(v, str) and ('Library/Application Support/TalNumStack' in v or v.endswith('.png') or v.endswith('_temp.pdf')):
                        try:
                            obj.pop(i)
                        except Exception:
                            pass
                    else:
                        _remove_temp_paths(v)

        _remove_temp_paths(imp)

        return imp
    except Exception as ex:
        print(f"[WARN] _sanitize_imposicion_data fallo: {ex}")
        return imposicion


def validar_trabajo_data(trabajo_data: Dict[str, Any]) -> bool:
    """
    Valida que los datos del trabajo tengan la estructura correcta.
    
    Returns:
        True si la estructura es válida, False si hay errores
    """
    try:
        # Verificar claves principales
        if "version" not in trabajo_data:
            print("[WARN] Falta versión en datos del trabajo")
            return False
        
        if "fase1" not in trabajo_data or "fase2" not in trabajo_data or "fase3" not in trabajo_data:
            print("[ERROR] Faltan fases en datos del trabajo")
            return False
        
        # Verificar campos obligatorios fase 1
        fase1 = trabajo_data["fase1"]
        if "cantidad" not in fase1 or "can_hojas_tal" not in fase1:
            print("[ERROR] Faltan campos en fase1")
            return False
        
        # Verificar campos obligatorios fase 2
        fase2 = trabajo_data["fase2"]
        if "hojas_x_pliego" not in fase2:
            print("[ERROR] Falta hojas_x_pliego en fase2")
            return False
        
        # Verificar campos obligatorios fase 3
        fase3 = trabajo_data["fase3"]
        campos_fase3 = ["comienzo_numeracion", "horizontal", "vertical", "orientacion"]
        for campo in campos_fase3:
            if campo not in fase3:
                if _PRINT_DEBUG:
                    print(f"[ERROR] Falta {campo} en fase3")
                return False
        
        print("[VALID] Datos del trabajo validados correctamente")
        return True
        
    except Exception as ex:
        print(f"[ERROR] Error validando trabajo: {ex}")
        return False


# ═══════════════════════════════════════════════════════════════════════════
# FUNCIONES PARA CAPTURAR/RESTAURAR DATOS DE IMPOSICIÓN
# ═══════════════════════════════════════════════════════════════════════════

def obtener_datos_imposicion_activa() -> Optional[Dict[str, Any]]:
    """
    Captura TODOS los datos actuales de impo_ui si hay una imposición activa.
    
    Esta función se debe llamar desde app.py antes de guardar el trabajo.
    Lee las variables globales de impo_ui y las empaqueta en un diccionario.
    
    Returns:
        Dict con todos los datos de imposición, o None si no hay imposición activa
    """
    try:
        import impo_ui
        
        # Verificar si hay PDF cargado (indicador de imposición activa)
        # Usamos _archivo_seleccionado en vez de _pdf_ordenado_actual (que es temporal)
        archivo_info = impo_ui._archivo_seleccionado if impo_ui._archivo_seleccionado else {}
        if not archivo_info or not archivo_info.get('nombre', ''):
            print("[INFO] No hay imposición activa, no se guardan datos de imposición")
            return None
        
        # Capturar TODAS las variables globales de imposición
        # IMPORTANTE: NO guardar rutas temporales, solo metadata del PDF original
        
        # DEBUG: Imprimir estructura de _archivo_seleccionado (activar poniendo _PRINT_DEBUG = True)
        if _PRINT_DEBUG:
            # print(f"[DEBUG GUARDAR] _archivo_seleccionado completo: {archivo_info}")  # desactivado
            print(f"[DEBUG GUARDAR] ruta_original = '{archivo_info.get('ruta_original', 'NO EXISTE')}'")
            print(f"[DEBUG GUARDAR] nombre = '{archivo_info.get('nombre', 'NO EXISTE')}'")
            print(f"[DEBUG GUARDAR] nombre_archivo = '{archivo_info.get('nombre_archivo', 'NO EXISTE')}'")
        
        # Extraer solo información persistible
        # CRÍTICO: 'nombre' puede no existir, usar 'nombre_archivo' como fallback
        nombre_pdf = archivo_info.get('nombre_archivo', archivo_info.get('nombre', ''))
        # Normalizar nombre (eliminar sufijos temporales si existen)
        try:
            if nombre_pdf.endswith('_ordenado_temp.pdf'):
                nombre_pdf = nombre_pdf[:-len('_ordenado_temp.pdf')] + '.pdf'
            elif nombre_pdf.endswith('_temp.pdf'):
                nombre_pdf = nombre_pdf[:-len('_temp.pdf')] + '.pdf'
        except Exception:
            pass
        archivo_persistible = {
            'nombre': nombre_pdf,  # Usar nombre_archivo si nombre no existe
            'nombre_archivo': nombre_pdf,  
            'num_paginas': archivo_info.get('num_paginas', archivo_info.get('paginas', 0)),
            'boxes_by_page': archivo_info.get('boxes_by_page', {}),
            'ruta_original': archivo_info.get('ruta_original', ''),  # Ruta del PDF original (no temporal)
        }
        
        imposicion_data = {
            # PDF y tipo de impresión - solo metadata, no paths
            'archivo_seleccionado': archivo_persistible,
            'tipo_impresion': impo_ui.dropdown_doble_cara.value if impo_ui.dropdown_doble_cara else "cara",
            'paginas_requeridas': impo_ui._ordenamiento_calculado.get("paginas_requeridas", 0),
            
            # Tamaño usuario y grid
            'TAMANO_USUARIO_W': float(impo_ui.TAMANO_USUARIO_W),
            'TAMANO_USUARIO_H': float(impo_ui.TAMANO_USUARIO_H),
            'SANGRE': float(impo_ui.SANGRE),
            'GRID_COLS': int(impo_ui.GRID_COLS),
            'GRID_ROWS': int(impo_ui.GRID_ROWS),
            
            # Calles
            'CALLES_L': list(impo_ui.CALLES_L),
            
            # Offsets de imagen
            'USER_OFFSET_IMAGEN_X_MM': float(impo_ui.USER_OFFSET_IMAGEN_X_MM),
            'USER_OFFSET_IMAGEN_Y_MM': float(impo_ui.USER_OFFSET_IMAGEN_Y_MM),
            
            # Tamaños de trazado y pliego
            'TAMANO_TRAZADO': dict(impo_ui.TAMANO_TRAZADO),
            'TAMANO_TRAZADO_CRUCES': dict(impo_ui.TAMANO_TRAZADO_CRUCES),
            'TAMANO_FINAL_PLIEGO': dict(impo_ui.TAMANO_FINAL_PLIEGO),
            
            # Offsets de trazado
            'USER_OFFSET_TRAZADO_X_MM': float(impo_ui.USER_OFFSET_TRAZADO_X_MM),
            'USER_OFFSET_TRAZADO_Y_MM': float(impo_ui.USER_OFFSET_TRAZADO_Y_MM),
            
            # Estado de congelado
            'PLIEGO_CONGELADO': bool(impo_ui.PLIEGO_CONGELADO),
            
            # Configuración de cruces
            'LONGITUD_CRUZ_MM': float(impo_ui.LONGITUD_CRUZ_MM),
            'GROSOR_CRUZ_PT': float(impo_ui.GROSOR_CRUZ_PT),
            'OFFSET_CRUZ_MM': float(impo_ui.OFFSET_CRUZ_MM),
            'AUTO_SANGRE_OFFSET_CRUZ': bool(impo_ui.AUTO_SANGRE_OFFSET_CRUZ),
            'OFFSET_CRUZ_PREF': float(impo_ui.OFFSET_CRUZ_PREF),
            'OFFSET_SEGURIDAD_MM': float(impo_ui.OFFSET_SEGURIDAD_MM),
            'LONGITUD_BRAZO_MAX_MM': float(impo_ui.LONGITUD_BRAZO_MAX_MM),
            
            # Marca de texto
            'MARCA_TEXTO_CONTENIDO': str(impo_ui.MARCA_TEXTO_CONTENIDO),
            'MARCA_TEXTO_POS_SUP_IZQ': bool(impo_ui.MARCA_TEXTO_POS_SUP_IZQ),
            'MARCA_TEXTO_POS_SUP_DER': bool(impo_ui.MARCA_TEXTO_POS_SUP_DER),
            'MARCA_TEXTO_POS_INF_IZQ': bool(impo_ui.MARCA_TEXTO_POS_INF_IZQ),
            'MARCA_TEXTO_POS_INF_DER': bool(impo_ui.MARCA_TEXTO_POS_INF_DER),
            'MARCA_TEXTO_POS_CENTRO_SUP': bool(impo_ui.MARCA_TEXTO_POS_CENTRO_SUP),
            'MARCA_TEXTO_POS_CENTRO_INF': bool(impo_ui.MARCA_TEXTO_POS_CENTRO_INF),
            'MARCA_TEXTO_POS_CENTRO_LAT_IZQ': bool(impo_ui.MARCA_TEXTO_POS_CENTRO_LAT_IZQ),
            'MARCA_TEXTO_POS_CENTRO_LAT_DER': bool(impo_ui.MARCA_TEXTO_POS_CENTRO_LAT_DER),
            'MARCA_TEXTO_ROTACION': int(impo_ui.MARCA_TEXTO_ROTACION),
            'MARCA_TEXTO_FAMILIA': str(impo_ui.MARCA_TEXTO_FAMILIA),
            'MARCA_TEXTO_TIPO': str(impo_ui.MARCA_TEXTO_TIPO),
            'MARCA_TEXTO_CUERPO': int(impo_ui.MARCA_TEXTO_CUERPO),
            'MARCA_TEXTO_OFFSET_H_MM': float(impo_ui.MARCA_TEXTO_OFFSET_H_MM),
            'MARCA_TEXTO_OFFSET_V_MM': float(impo_ui.MARCA_TEXTO_OFFSET_V_MM),
            
            # Valores de controles UI (para restaurar campos)
            'textfield_ancho_value': impo_ui.textfield_ancho.value if impo_ui.textfield_ancho else str(impo_ui.TAMANO_USUARIO_W),
            'textfield_alto_value': impo_ui.textfield_alto.value if impo_ui.textfield_alto else str(impo_ui.TAMANO_USUARIO_H),
            'textfield_sangre_value': impo_ui.textfield_sangre.value if impo_ui.textfield_sangre else str(impo_ui.SANGRE),
            'textfield_medianil_value': impo_ui.textfield_medianil.value if impo_ui.textfield_medianil else "0",
            
            # Estado de checkboxes de imposición
            'checkbox_cruces': bool(impo_ui.checkbox_cruces.value) if impo_ui.checkbox_cruces else False,
            'checkbox_lineas_corte': bool(impo_ui.checkbox_lineas_corte.value) if impo_ui.checkbox_lineas_corte else False,
            'checkbox_marcas_texto': bool(impo_ui.checkbox_marcas_texto.value) if impo_ui.checkbox_marcas_texto else False,
            'checkbox_linea_exterior': bool(impo_ui.checkbox_linea_exterior.value) if impo_ui.checkbox_linea_exterior else False,
        }
        
        nombre_pdf = archivo_persistible.get('nombre_archivo', archivo_persistible.get('nombre', 'N/A'))
        print(f"[INFO] Datos de imposición capturados: PDF={nombre_pdf}, Grid={impo_ui.GRID_COLS}x{impo_ui.GRID_ROWS}")
        print(f"[INFO] NOTA: Rutas temporales NO guardadas - se regenerarán al cargar el trabajo")
        return imposicion_data
        
    except Exception as ex:
        print(f"[ERROR] Error capturando datos de imposición: {ex}")
        import traceback
        traceback.print_exc()
        return None


def restaurar_datos_imposicion(imposicion_data: Dict[str, Any], trabajo_path: str = None) -> bool:
    """
    Restaura TODOS los datos de imposición en impo_ui.
    
    Esta función se debe llamar desde app.py después de cargar un trabajo.
    Actualiza las variables globales de impo_ui con los valores guardados.
    
    Args:
        imposicion_data: Dict con todos los datos de imposición
    
    Returns:
        True si se restauró correctamente, False si hubo error
    """
    try:
        import impo_ui

        if not imposicion_data:
            print("[INFO] No hay datos de imposición para restaurar")
            return True

        # Evitar reentrada/ejecución doble desde distintos hilos/llamadores
        global _RESTORING
        if globals().get('_RESTORING', False):
            print("[RESTAURAR] Restauración ya en curso, omitiendo segunda invocación")
            return True
        globals()['_RESTORING'] = True
        
        # Chivato: marcar si hay imposición o no
        try:
            import impo_ui
            if imposicion_data:
                impo_ui._estado_impo_ui["impo_creada"] = True
            else:
                impo_ui._estado_impo_ui["impo_creada"] = False
        except Exception:
            pass

        # Restaurar metadata del PDF (sin rutas temporales)
        if imposicion_data.get('archivo_seleccionado'):
            archivo_guardado = imposicion_data.get('archivo_seleccionado')
            
            # Restaurar solo los campos de metadata que se guardaron
            impo_ui._archivo_seleccionado = {
                'ruta': '',  # No restaurar ruta temporal (se regenera)
                'ruta_original': archivo_guardado.get('ruta_original', ''),  # Restaurar ruta del PDF original
                'nombre': archivo_guardado.get('nombre', ''),
                'nombre_archivo': archivo_guardado.get('nombre_archivo', ''),
                'paginas': archivo_guardado.get('num_paginas', 0),
                'num_paginas': archivo_guardado.get('num_paginas', 0),
                'boxes_by_page': archivo_guardado.get('boxes_by_page', {}),
            }
            
            print(f"[RESTAURAR] Metadata del PDF restaurada: {archivo_guardado.get('nombre_archivo', 'N/A')}, {archivo_guardado.get('num_paginas', 0)} págs")
            
            # Si hay ruta_original, crear PDF temporal inmediatamente
            ruta_original = archivo_guardado.get('ruta_original', '')
            # Si la ruta original no existe, intentar buscar el PDF junto al archivo de trabajo
            if not ruta_original or not os.path.exists(ruta_original):
                if trabajo_path:
                    try:
                        trabajo_dir = os.path.dirname(trabajo_path)
                        nombre_pdf = archivo_guardado.get('nombre_archivo') or archivo_guardado.get('nombre')
                        if nombre_pdf:
                            # Probar varias variantes (con y sin extensión .pdf)
                            candidates = [nombre_pdf]
                            if not nombre_pdf.lower().endswith('.pdf'):
                                candidates.append(f"{nombre_pdf}.pdf")
                            
                            for cand in candidates:
                                posible = os.path.join(trabajo_dir, cand)
                                if os.path.exists(posible):
                                    if _PRINT_DEBUG:
                                        print(f"[RESTAURAR] Ruta original no encontrada. Usando PDF desde carpeta del trabajo: {posible}")
                                    ruta_original = posible
                                    # *** ACTUALIZAR TAMBIÉN impo_ui._archivo_seleccionado con la nueva ruta ***
                                    impo_ui._archivo_seleccionado['ruta_original'] = posible
                                    
                                    # *** SINCRONIZAR con pdf_ordenado_ui para que use la nueva ruta ***
                                    try:
                                        import pdf_ordenado_ui
                                        try:
                                            pdf_ordenado_ui.guardar_ruta_pdf_original(posible)
                                        except Exception:
                                            try:
                                                pdf_ordenado_ui._RUTA_PDF_ORIGINAL = posible
                                            except Exception:
                                                pass
                                        try:
                                            pdf_ordenado_ui._archivo_seleccionado_pdf["ruta_original"] = posible
                                            pdf_ordenado_ui._archivo_seleccionado_pdf["nombre"] = os.path.basename(posible)
                                        except Exception:
                                            pass
                                        if _PRINT_DEBUG:
                                            print(f"[RESTAURAR] pdf_ordenado_ui sincronizado con ruta alternativa: {posible}")
                                    except Exception as _ex_sync:
                                        if _PRINT_DEBUG:
                                            print(f"[RESTAURAR] Error sincronizando pdf_ordenado_ui: {_ex_sync}")
                                    break
                    except Exception:
                        pass

            if ruta_original and os.path.exists(ruta_original):
                print(f"[RESTAURAR] Creando PDF temporal desde: {ruta_original}")
                try:
                    from pdf_ordenado_ui import copiar_pdf_a_temporal
                    pdf_temp = copiar_pdf_a_temporal(ruta_original)
                    if pdf_temp:
                        impo_ui._archivo_seleccionado['ruta'] = pdf_temp
                        
                        # Extraer nombre del archivo original (no temporal)
                        nombre_archivo = os.path.basename(ruta_original)
                        impo_ui._archivo_seleccionado['nombre'] = nombre_archivo
                        impo_ui._archivo_seleccionado['nombre_archivo'] = nombre_archivo
                        
                        # Inicializar imagenes_secuenciales vacío (se llenarán al presionar "Generar vista previa")
                        impo_ui._archivo_seleccionado['imagenes_secuenciales'] = {}
                        
                        # Contar páginas del PDF y extraer boxes (CRÍTICO para navegador y tamaño PDF)
                        try:
                            from pdf_manipulator import contar_paginas_pdf, leer_cajas_por_pagina
                            num_paginas, _ = contar_paginas_pdf(ruta_original)
                            if num_paginas:
                                impo_ui._archivo_seleccionado['paginas'] = num_paginas
                                impo_ui._archivo_seleccionado['num_paginas'] = num_paginas
                                print(f"[RESTAURAR] ✅ PDF temporal creado: {pdf_temp}")
                                print(f"[RESTAURAR]    Nombre: {nombre_archivo}, Páginas: {num_paginas}")
                            
                            # Extraer boxes_by_page (necesario para container "Tamaño del PDF" y navegador)
                            boxes_by_page = leer_cajas_por_pagina(ruta_original)
                            if boxes_by_page:
                                impo_ui._archivo_seleccionado['boxes_by_page'] = boxes_by_page
                                print(f"[RESTAURAR] ✅ Boxes extraídas: {len(boxes_by_page)} páginas")
                            else:
                                impo_ui._archivo_seleccionado['boxes_by_page'] = {}
                                print(f"[RESTAURAR] ⚠️ No se pudieron extraer boxes")
                        except Exception as ex_pages:
                            print(f"[RESTAURAR] ⚠️ Error procesando PDF: {ex_pages}")
                            impo_ui._archivo_seleccionado['boxes_by_page'] = {}
                        # Registrar temporal como pdf ordenado actual para que la UI lo detecte
                        try:
                            impo_ui._pdf_ordenado_actual = pdf_temp
                        except Exception:
                            pass

                        # POBLAR _estado_impo_ui mínimo para que crear_ventana_ordenar_imposicion
                        # detecte que hay estado previo y actualice los controles visuales.
                        try:
                            if not hasattr(impo_ui, '_estado_impo_ui') or impo_ui._estado_impo_ui is None or not isinstance(impo_ui._estado_impo_ui, dict):
                                impo_ui._estado_impo_ui = {}
                            estado = impo_ui._estado_impo_ui
                            # Mapeo básico desde imposicion_data a claves que usa actualizar_controles_desde_estado
                            # NO sobrescribir grid_cols/grid_rows si ya vienen de fase3
                            grid_cols_actual = estado.get('grid_cols')
                            grid_rows_actual = estado.get('grid_rows')
                            
                            estado.update({
                                'pliego_ancho': imposicion_data.get('TAMANO_FINAL_PLIEGO', {}).get('w_mm'),
                                'pliego_alto': imposicion_data.get('TAMANO_FINAL_PLIEGO', {}).get('h_mm'),
                                'sangre': imposicion_data.get('SANGRE', 3.0),
                                'tamano_usuario_w': imposicion_data.get('TAMANO_USUARIO_W', 0.0),
                                'tamano_usuario_h': imposicion_data.get('TAMANO_USUARIO_H', 0.0),
                                'offset_img_x': imposicion_data.get('USER_OFFSET_IMAGEN_X_MM', 0.0),
                                'offset_img_y': imposicion_data.get('USER_OFFSET_IMAGEN_Y_MM', 0.0),
                                'offset_trazado_x': imposicion_data.get('USER_OFFSET_TRAZADO_X_MM', 0.0),
                                'offset_trazado_y': imposicion_data.get('USER_OFFSET_TRAZADO_Y_MM', 0.0),
                                'dropdown_doble_cara': imposicion_data.get('tipo_impresion', 'cara'),
                                'dropdown_copias': imposicion_data.get('export_copies', '1'),
                            })
                            
                            # Restaurar grid solo si ya estaba en el stamp (de fase3)
                            if grid_cols_actual is not None:
                                estado['grid_cols'] = grid_cols_actual
                            if grid_rows_actual is not None:
                                estado['grid_rows'] = grid_rows_actual
                        except Exception as ex_state:
                            print(f"[RESTAURAR] ⚠️ No se pudo poblar _estado_impo_ui: {ex_state}")
                    else:
                        print(f"[RESTAURAR] ❌ Error creando PDF temporal")
                except Exception as ex:
                    print(f"[RESTAURAR] ❌ Error copiando PDF a temporal: {ex}")
            else:
                print(f"[RESTAURAR] NOTA: Ruta original no existe o está vacía - se creará al cargar PDF")
        
        # Restaurar tamaño usuario (NO sobrescribir grid, ya viene de fase3)
        impo_ui.TAMANO_USUARIO_W = imposicion_data.get('TAMANO_USUARIO_W', 210)
        impo_ui.TAMANO_USUARIO_H = imposicion_data.get('TAMANO_USUARIO_H', 100)
        impo_ui.SANGRE = imposicion_data.get('SANGRE', 3)
        # GRID_COLS y GRID_ROWS ya se actualizaron desde fase3, NO sobrescribir
        
        # Restaurar calles
        impo_ui.CALLES_L = imposicion_data.get('CALLES_L', [])
        
        # Restaurar offsets de imagen
        impo_ui.USER_OFFSET_IMAGEN_X_MM = imposicion_data.get('USER_OFFSET_IMAGEN_X_MM', 0.0)
        impo_ui.USER_OFFSET_IMAGEN_Y_MM = imposicion_data.get('USER_OFFSET_IMAGEN_Y_MM', 0.0)
        
        # Restaurar tamaños de trazado y pliego
        impo_ui.TAMANO_TRAZADO = imposicion_data.get('TAMANO_TRAZADO', {"w_mm": None, "h_mm": None})
        impo_ui.TAMANO_TRAZADO_CRUCES = imposicion_data.get('TAMANO_TRAZADO_CRUCES', {"w_mm": None, "h_mm": None})
        impo_ui.TAMANO_FINAL_PLIEGO = imposicion_data.get('TAMANO_FINAL_PLIEGO', {"w_mm": None, "h_mm": None})
        
        # Restaurar offsets de trazado
        impo_ui.USER_OFFSET_TRAZADO_X_MM = imposicion_data.get('USER_OFFSET_TRAZADO_X_MM', 0.0)
        impo_ui.USER_OFFSET_TRAZADO_Y_MM = imposicion_data.get('USER_OFFSET_TRAZADO_Y_MM', 0.0)
        
        # Restaurar estado de congelado (puede estar en TAMANO_FINAL_PLIEGO o como campo separado)
        tfp = imposicion_data.get('TAMANO_FINAL_PLIEGO', {})
        impo_ui.PLIEGO_CONGELADO = tfp.get('PLIEGO_CONGELADO', imposicion_data.get('PLIEGO_CONGELADO', False))
        
        # Restaurar configuración de cruces
        impo_ui.LONGITUD_CRUZ_MM = imposicion_data.get('LONGITUD_CRUZ_MM', 10.0)
        impo_ui.GROSOR_CRUZ_PT = imposicion_data.get('GROSOR_CRUZ_PT', 0.5)
        impo_ui.OFFSET_CRUZ_MM = imposicion_data.get('OFFSET_CRUZ_MM', 5.0)
        impo_ui.AUTO_SANGRE_OFFSET_CRUZ = imposicion_data.get('AUTO_SANGRE_OFFSET_CRUZ', False)
        impo_ui.OFFSET_CRUZ_PREF = imposicion_data.get('OFFSET_CRUZ_PREF', 0.0)
        impo_ui.OFFSET_SEGURIDAD_MM = imposicion_data.get('OFFSET_SEGURIDAD_MM', 1.0)
        impo_ui.LONGITUD_BRAZO_MAX_MM = imposicion_data.get('LONGITUD_BRAZO_MAX_MM', 5.0)
        
        # Restaurar marca de texto
        impo_ui.MARCA_TEXTO_CONTENIDO = imposicion_data.get('MARCA_TEXTO_CONTENIDO', "NumStack - Imposición")
        impo_ui.MARCA_TEXTO_POS_SUP_IZQ = imposicion_data.get('MARCA_TEXTO_POS_SUP_IZQ', True)
        impo_ui.MARCA_TEXTO_POS_SUP_DER = imposicion_data.get('MARCA_TEXTO_POS_SUP_DER', False)
        impo_ui.MARCA_TEXTO_POS_INF_IZQ = imposicion_data.get('MARCA_TEXTO_POS_INF_IZQ', False)
        impo_ui.MARCA_TEXTO_POS_INF_DER = imposicion_data.get('MARCA_TEXTO_POS_INF_DER', False)
        impo_ui.MARCA_TEXTO_POS_CENTRO_SUP = imposicion_data.get('MARCA_TEXTO_POS_CENTRO_SUP', False)
        impo_ui.MARCA_TEXTO_POS_CENTRO_INF = imposicion_data.get('MARCA_TEXTO_POS_CENTRO_INF', False)
        impo_ui.MARCA_TEXTO_POS_CENTRO_LAT_IZQ = imposicion_data.get('MARCA_TEXTO_POS_CENTRO_LAT_IZQ', False)
        impo_ui.MARCA_TEXTO_POS_CENTRO_LAT_DER = imposicion_data.get('MARCA_TEXTO_POS_CENTRO_LAT_DER', False)
        impo_ui.MARCA_TEXTO_ROTACION = imposicion_data.get('MARCA_TEXTO_ROTACION', 0)
        impo_ui.MARCA_TEXTO_FAMILIA = imposicion_data.get('MARCA_TEXTO_FAMILIA', "Arial")
        impo_ui.MARCA_TEXTO_TIPO = imposicion_data.get('MARCA_TEXTO_TIPO', "Regular")
        impo_ui.MARCA_TEXTO_CUERPO = imposicion_data.get('MARCA_TEXTO_CUERPO', 12)
        impo_ui.MARCA_TEXTO_OFFSET_H_MM = imposicion_data.get('MARCA_TEXTO_OFFSET_H_MM', 0.0)
        impo_ui.MARCA_TEXTO_OFFSET_V_MM = imposicion_data.get('MARCA_TEXTO_OFFSET_V_MM', 0.0)
        
        # Restaurar checkboxes desde el JSON (mapeo CHECK_BOX_* -> checkbox_*)
        # Actualizar tanto las variables globales como el estado
        if not hasattr(impo_ui, '_estado_impo_ui') or impo_ui._estado_impo_ui is None or not isinstance(impo_ui._estado_impo_ui, dict):
            impo_ui._estado_impo_ui = {}
        
        checkbox_cruces_val = imposicion_data.get('CHECK_BOX_CRUCES_Y_MARCAS', True)
        checkbox_lineas_val = imposicion_data.get('CHECK_BOX_LINEAS_DE_CORTE', False)
        checkbox_marcas_val = imposicion_data.get('CHECK_BOX_MARCAS_DE_TEXTO', False)
        checkbox_exterior_val = imposicion_data.get('CHECK_BOX_LINEA_EXTERIOR', True)
        
        # Actualizar estado (CRÍTICO - estos valores deben estar en el estado ANTES de crear widgets)
        impo_ui._estado_impo_ui['checkbox_cruces'] = checkbox_cruces_val
        impo_ui._estado_impo_ui['checkbox_lineas_corte'] = checkbox_lineas_val
        impo_ui._estado_impo_ui['checkbox_marcas_texto'] = checkbox_marcas_val
        impo_ui._estado_impo_ui['checkbox_linea_exterior'] = checkbox_exterior_val
        # Mantener también las claves en MAYÚSCULAS para compatibilidad
        try:
            impo_ui._estado_impo_ui['CHECK_BOX_CRUCES_Y_MARCAS'] = bool(checkbox_cruces_val)
            impo_ui._estado_impo_ui['CHECK_BOX_LINEAS_DE_CORTE'] = bool(checkbox_lineas_val)
            impo_ui._estado_impo_ui['CHECK_BOX_MARCAS_DE_TEXTO'] = bool(checkbox_marcas_val)
            impo_ui._estado_impo_ui['CHECK_BOX_LINEA_EXTERIOR'] = bool(checkbox_exterior_val)
        except Exception:
            pass
        print(f"[TRAB_MANAGER RESTORE] checkbox values set -> CRUCES={checkbox_cruces_val} LINEA_EXTERIOR={checkbox_exterior_val} (uppercase synced)")
        
        # También actualizar TODOS los demás valores en el estado para que estén disponibles
        impo_ui._estado_impo_ui.update({
            'tamano_usuario_w': imposicion_data.get('TAMANO_USUARIO_W', 0.0),
            'tamano_usuario_h': imposicion_data.get('TAMANO_USUARIO_H', 0.0),
            'sangre': imposicion_data.get('SANGRE', 3.0),
            'offset_img_x': imposicion_data.get('USER_OFFSET_IMAGEN_X_MM', 0.0),
            'offset_img_y': imposicion_data.get('USER_OFFSET_IMAGEN_Y_MM', 0.0),
            'offset_trazado_x': imposicion_data.get('USER_OFFSET_TRAZADO_X_MM', 0.0),
            'offset_trazado_y': imposicion_data.get('USER_OFFSET_TRAZADO_Y_MM', 0.0),
            'pliego_ancho': imposicion_data.get('TAMANO_FINAL_PLIEGO', {}).get('w_mm'),
            'pliego_alto': imposicion_data.get('TAMANO_FINAL_PLIEGO', {}).get('h_mm'),
            'pliego_congelado': imposicion_data.get('TAMANO_FINAL_PLIEGO', {}).get('PLIEGO_CONGELADO', imposicion_data.get('PLIEGO_CONGELADO', False)),
            'calles_list': imposicion_data.get('CALLES_L', []),
            # Configuración de cruces (CRÍTICO - deben estar en el estado para guardar correctamente)
            'longitud_cruz_mm': imposicion_data.get('LONGITUD_CRUZ_MM', 10.0),
            'grosor_cruz_pt': imposicion_data.get('GROSOR_CRUZ_PT', 0.5),
            'offset_cruz_mm': imposicion_data.get('OFFSET_CRUZ_MM', 5.0),
            'auto_sangre_offset_cruz': imposicion_data.get('AUTO_SANGRE_OFFSET_CRUZ', False),
            'offset_seguridad_mm': imposicion_data.get('OFFSET_SEGURIDAD_MM', 1.0),
            'longitud_brazo_max_mm': imposicion_data.get('LONGITUD_BRAZO_MAX_MM', 5.0),
            # Configuración de marca de texto (CRÍTICO - deben estar en el estado para guardar correctamente)
            'marca_texto_contenido': imposicion_data.get('MARCA_TEXTO_CONTENIDO', 'NumStack - Imposición'),
            'marca_texto_pos_sup_izq': imposicion_data.get('MARCA_TEXTO_POS_SUP_IZQ', False),
            'marca_texto_pos_sup_der': imposicion_data.get('MARCA_TEXTO_POS_SUP_DER', False),
            'marca_texto_pos_inf_izq': imposicion_data.get('MARCA_TEXTO_POS_INF_IZQ', False),
            'marca_texto_pos_inf_der': imposicion_data.get('MARCA_TEXTO_POS_INF_DER', False),
            'marca_texto_pos_centro_sup': imposicion_data.get('MARCA_TEXTO_POS_CENTRO_SUP', False),
            'marca_texto_pos_centro_inf': imposicion_data.get('MARCA_TEXTO_POS_CENTRO_INF', False),
            'marca_texto_pos_centro_lat_izq': imposicion_data.get('MARCA_TEXTO_POS_CENTRO_LAT_IZQ', False),
            'marca_texto_pos_centro_lat_der': imposicion_data.get('MARCA_TEXTO_POS_CENTRO_LAT_DER', False),
            'marca_texto_rotacion': imposicion_data.get('MARCA_TEXTO_ROTACION', 0),
            'marca_texto_familia': imposicion_data.get('MARCA_TEXTO_FAMILIA', 'Arial'),
            'marca_texto_tipo': imposicion_data.get('MARCA_TEXTO_TIPO', 'Regular'),
            'marca_texto_cuerpo': imposicion_data.get('MARCA_TEXTO_CUERPO', 12),
            'marca_texto_color': imposicion_data.get('MARCA_TEXTO_COLOR', 'black'),
            'marca_texto_offset_h_mm': imposicion_data.get('MARCA_TEXTO_OFFSET_H_MM', 0.0),
            'marca_texto_offset_v_mm': imposicion_data.get('MARCA_TEXTO_OFFSET_V_MM', 0.0),
        })
        
        print(f"[RESTAURAR] ✅ Estado completo actualizado con todos los datos del archivo")
        print(f"[RESTAURAR] Checkboxes en estado:")
        print(f"   checkbox_cruces: {checkbox_cruces_val}")
        print(f"   checkbox_lineas_corte: {checkbox_lineas_val}")
        print(f"   checkbox_marcas_texto: {checkbox_marcas_val}")
        print(f"   checkbox_linea_exterior: {checkbox_exterior_val}")
        
        # Restaurar valores de controles UI (si existen los controles)
        if impo_ui.textfield_ancho:
            # CRÍTICO: Deshabilitar on_change antes de restaurar
            ancho_on_change_original = impo_ui.textfield_ancho.on_change
            impo_ui.textfield_ancho.on_change = None
            impo_ui.textfield_ancho.value = imposicion_data.get('textfield_ancho_value', "297")
            try:
                impo_ui.textfield_ancho.update()
            except: pass
            # Restaurar on_change
            impo_ui.textfield_ancho.on_change = ancho_on_change_original
        if impo_ui.textfield_alto:
            # CRÍTICO: Deshabilitar on_change antes de restaurar
            alto_on_change_original = impo_ui.textfield_alto.on_change
            impo_ui.textfield_alto.on_change = None
            impo_ui.textfield_alto.value = imposicion_data.get('textfield_alto_value', "210")
            try:
                impo_ui.textfield_alto.update()
            except: pass
            # Restaurar on_change
            impo_ui.textfield_alto.on_change = alto_on_change_original
        if impo_ui.textfield_sangre:
            # CRÍTICO: Deshabilitar on_change antes de restaurar para evitar que se sobrescriba
            sangre_on_change_original = impo_ui.textfield_sangre.on_change
            impo_ui.textfield_sangre.on_change = None
            impo_ui.textfield_sangre.value = imposicion_data.get('textfield_sangre_value', str(impo_ui.SANGRE))
            try:
                impo_ui.textfield_sangre.update()
            except: pass
            # Restaurar on_change
            impo_ui.textfield_sangre.on_change = sangre_on_change_original
        if impo_ui.textfield_medianil:
            impo_ui.textfield_medianil.value = imposicion_data.get('textfield_medianil_value', "0")
            try:
                impo_ui.textfield_medianil.update()
            except: pass
        if impo_ui.dropdown_doble_cara:
            impo_ui.dropdown_doble_cara.value = imposicion_data.get('tipo_impresion', "cara")
            try:
                impo_ui.dropdown_doble_cara.update()
            except: pass
        
        # Restaurar checkboxes en los widgets (si existen)
        if hasattr(impo_ui, 'checkbox_cruces') and impo_ui.checkbox_cruces:
            impo_ui.checkbox_cruces.value = checkbox_cruces_val
            try:
                impo_ui.checkbox_cruces.update()
            except: pass
        if hasattr(impo_ui, 'checkbox_lineas_corte') and impo_ui.checkbox_lineas_corte:
            impo_ui.checkbox_lineas_corte.value = checkbox_lineas_val
            try:
                impo_ui.checkbox_lineas_corte.update()
            except: pass
        if hasattr(impo_ui, 'checkbox_marcas_texto') and impo_ui.checkbox_marcas_texto:
            impo_ui.checkbox_marcas_texto.value = checkbox_marcas_val
            try:
                impo_ui.checkbox_marcas_texto.update()
            except: pass
        if hasattr(impo_ui, 'checkbox_linea_exterior') and impo_ui.checkbox_linea_exterior:
            impo_ui.checkbox_linea_exterior.value = checkbox_exterior_val
            try:
                impo_ui.checkbox_linea_exterior.update()
            except: pass
            try:
                print(f"[TRAB_MANAGER RESTORE] Widget checkbox_linea_exterior updated to {checkbox_exterior_val}")
            except Exception:
                pass
        
        # Restaurar botón auto/manual de pliego
        print(f"[RESTORE] Verificando botón pliego...")
        print(f"[RESTORE]   hasattr(impo_ui, 'boton_auto_manual_pliego'): {hasattr(impo_ui, 'boton_auto_manual_pliego')}")
        if hasattr(impo_ui, 'boton_auto_manual_pliego'):
            print(f"[RESTORE]   impo_ui.boton_auto_manual_pliego: {impo_ui.boton_auto_manual_pliego}")
        
        if hasattr(impo_ui, 'boton_auto_manual_pliego') and impo_ui.boton_auto_manual_pliego:
            pliego_congelado = imposicion_data.get('TAMANO_FINAL_PLIEGO', {}).get('PLIEGO_CONGELADO', imposicion_data.get('PLIEGO_CONGELADO', False))
            impo_ui.boton_auto_manual_pliego.text = "Tamaño manual" if pliego_congelado else "Tamaño auto"
            print(f"[RESTORE] Botón pliego actualizado: {impo_ui.boton_auto_manual_pliego.text} (congelado={pliego_congelado})")
            try:
                impo_ui.boton_auto_manual_pliego.update()
            except: pass
        
        # Actualizar estado compartido para pdf_ordenado_ui
        try:
            if not hasattr(impo_ui, '_estado_impo_ui') or impo_ui._estado_impo_ui is None or not isinstance(impo_ui._estado_impo_ui, dict):
                impo_ui._estado_impo_ui = {}
            impo_ui._estado_impo_ui['dropdown_doble_cara'] = imposicion_data.get('tipo_impresion', "cara")
            print(f"[RESTORE] Estado compartido actualizado: dropdown_doble_cara={impo_ui._estado_impo_ui.get('dropdown_doble_cara')}")
        except Exception as ex:
            print(f"[WARN] No se pudo actualizar estado compartido: {ex}")
        
        # Restaurar información del archivo PDF (nombre y páginas) si existe archivo_seleccionado
        if impo_ui._archivo_seleccionado:
            try:
                # Restaurar nombre del archivo
                nombre_archivo = impo_ui._archivo_seleccionado.get('nombre_archivo', '')
                if nombre_archivo and hasattr(impo_ui, 'texto_archivo') and impo_ui.texto_archivo is not None:
                    impo_ui.texto_archivo.value = nombre_archivo
                    try:
                        impo_ui.texto_archivo.update()
                    except: pass
                
                # Restaurar número de páginas
                num_paginas = impo_ui._archivo_seleccionado.get('num_paginas', 0)
                if num_paginas > 0 and hasattr(impo_ui, 'texto_paginas') and impo_ui.texto_paginas is not None:
                    impo_ui.texto_paginas.value = f"{num_paginas} páginas"
                    try:
                        impo_ui.texto_paginas.update()
                    except: pass
                
                print(f"[RESTORE] Archivo restaurado: {nombre_archivo} ({num_paginas} págs)")
            except Exception as ex:
                print(f"[WARN] Error restaurando info del archivo: {ex}")
        
        # Restaurar información visual del PDF (MediaBox, TrimBox, Sangre)
        if impo_ui._archivo_seleccionado and impo_ui._archivo_seleccionado.get('boxes_by_page'):
            boxes_by_page = impo_ui._archivo_seleccionado.get('boxes_by_page', {})
            if boxes_by_page and 0 in boxes_by_page:
                boxes_p0 = boxes_by_page[0]
                
                def fmt_box(box_tuple):
                    if not box_tuple or len(box_tuple) != 4: return "-"
                    w_pt = box_tuple[2] - box_tuple[0]
                    h_pt = box_tuple[3] - box_tuple[1]
                    return f"{w_pt * 0.352778:.1f} x {h_pt * 0.352778:.1f} mm"
                
                # Restaurar textos informativos
                if hasattr(impo_ui, 'texto_info_pdf_mediabox'):
                    impo_ui.texto_info_pdf_mediabox.value = f"Total: {fmt_box(boxes_p0.get('mediabox'))}"
                if hasattr(impo_ui, 'texto_info_pdf_trimbox'):
                    impo_ui.texto_info_pdf_trimbox.value = f"Corte: {fmt_box(boxes_p0.get('trimbox'))}"
                
                # Calcular y restaurar sangre
                try:
                    mb = boxes_p0.get('mediabox')
                    tb = boxes_p0.get('trimbox')
                    if mb and tb and hasattr(impo_ui, 'texto_info_pdf_bleedbox'):
                        mb_w = mb[2] - mb[0]
                        tb_w = tb[2] - tb[0]
                        sangre_pt = (mb_w - tb_w) / 2
                        impo_ui.texto_info_pdf_bleedbox.value = f"Sangre: {sangre_pt * 0.352778:.1f} mm"
                    elif hasattr(impo_ui, 'texto_info_pdf_bleedbox'):
                        impo_ui.texto_info_pdf_bleedbox.value = "Sangre: -"
                except Exception as ex:
                    print(f"[WARN] Error calculando sangre del PDF: {ex}")
                    if hasattr(impo_ui, 'texto_info_pdf_bleedbox'):
                        impo_ui.texto_info_pdf_bleedbox.value = "Sangre: -"
                
                # Actualizar los controles visualmente y el color del container
                try:
                    if hasattr(impo_ui, 'texto_info_pdf_mediabox'):
                        impo_ui.texto_info_pdf_mediabox.update()
                    if hasattr(impo_ui, 'texto_info_pdf_trimbox'):
                        impo_ui.texto_info_pdf_trimbox.update()
                    if hasattr(impo_ui, 'texto_info_pdf_bleedbox'):
                        impo_ui.texto_info_pdf_bleedbox.update()
                    # Actualizar el color del container según la sangre
                    if hasattr(impo_ui, '_actualizar_bg_container_info_pdf'):
                        impo_ui._actualizar_bg_container_info_pdf()
                except Exception as ex:
                    print(f"[WARN] No se pudieron actualizar controles de info PDF: {ex}")
        
        # NO llamar a guardar_estado_impo_ui() aquí porque sobrescribe el dropdown restaurado
        # El estado ya fue actualizado correctamente en las líneas anteriores (línea 550-555)
        # Si se llama guardar_estado_impo_ui(), lee el widget dropdown que podría no existir
        # o tener valor por defecto "cara", sobrescribiendo el "dorso" restaurado
        
        # impo_ui.guardar_estado_impo_ui()  # ❌ DESHABILITADO - causa sobrescritura del dropdown

        nombre_pdf = impo_ui._archivo_seleccionado.get('nombre_archivo', 'N/A') if impo_ui._archivo_seleccionado else 'N/A'
        tipo_imp = impo_ui._estado_impo_ui.get('dropdown_doble_cara', 'N/A')
        print(f"[INFO] Datos de imposición restaurados: PDF={nombre_pdf}, Grid={impo_ui.GRID_COLS}x{impo_ui.GRID_ROWS}, Tipo={tipo_imp}")
        # Restauración finalizada, liberar flag
        try:
            globals()['_RESTORING'] = False
        except Exception:
            pass
        return True
        
    except Exception as ex:
        # Asegurar liberar el flag en caso de error
        try:
            globals()['_RESTORING'] = False
        except Exception:
            pass
        print(f"[ERROR] Error restaurando datos de imposición: {ex}")
        import traceback
        traceback.print_exc()
        return False
