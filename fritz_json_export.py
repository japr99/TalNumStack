"""
Módulo para generación de JSON de imposición para Fritz PDF
Soporta generación de datos para CARA y DORSO
"""

import json
from lang import t

# Silenciar prints de depuración en este módulo por defecto.
# Para activar, cambiar _PRINT_DEBUG = True durante desarrollo.
_PRINT_DEBUG = False
if not _PRINT_DEBUG:
    def _no_print(*args, **kwargs):
        return None

    print = _no_print

# Variables globales para almacenar los JSONs de CARA y DORSO
_IMPO_EXPORT_DATA_CARA = None
_IMPO_EXPORT_DATA_DORSO = None

def generar_impo_export_data(dims, tipo_cara="CARA", tamano_pliego_w_mm=None, tamano_pliego_h_mm=None, grid_cols=None, grid_rows=None, mediabox_pts=None, sangre_mm=6.0):
    """
    Genera y devuelve el diccionario `impo_export_data` a partir de `dims`.
    
    Args:
        dims: Diccionario con los datos de celdas e imposición
        tipo_cara: "CARA" o "DORSO" para distinguir el tipo de JSON
        tamano_pliego_w_mm: Ancho del pliego en mm (opcional)
        tamano_pliego_h_mm: Alto del pliego en mm (opcional)
        grid_cols: Número de columnas del grid (opcional)
        grid_rows: Número de filas del grid (opcional)
        mediabox_pts: Tuple (x0, y0, x1, y1) del mediabox en puntos PDF (opcional)
        sangre_mm: Sangre total en mm (por defecto 6.0)
    
    Returns:
        dict: Diccionario serializable con todos los datos de imposición para Fritz
    """
    # Debug: imprimir valores de `dims` de forma legible (DESACTIVADO para limpieza)
    # try:
    #     print(f"[DEBUG generar_impo_export_data] dims keys={list(dims.keys())}")
    #     print("[DEBUG generar_impo_export_data] dims values:")
    #     for k, v in dims.items():
    #         try:
    #             print(f"  • {k}: {json.dumps(v, indent=2, ensure_ascii=False)}")
    #         except (TypeError, ValueError):
    #             print(f"  • {k}: {v!r}")
    # except Exception as ex:
    #     print(f"[DEBUG generar_impo_export_data] Error imprimiendo dims: {ex}")
    try:
        # Obtener valores del grid desde dims o parámetros
        grid_info = dims.get("offsets_grid_info", {})
        cols = grid_cols or grid_info.get("grid_cols", 1)
        rows = grid_rows or grid_info.get("grid_rows", 1)
        
        # Obtener tamaño del pliego desde dims o parámetros
        pliego_w = tamano_pliego_w_mm or dims.get("cruces_corte", {}).get("tamano_final_w_mm", 0.0)
        pliego_h = tamano_pliego_h_mm or dims.get("cruces_corte", {}).get("tamano_final_h_mm", 0.0)
        
        # 1️⃣ GENERAL
        impo_export_data = {
            "tipo_cara": tipo_cara,  # ← Identificador CARA/DORSO
            "general": {
                "grid_cols": cols,
                "grid_rows": rows,
                "tamano_pliego_w_mm": round(pliego_w, 2),
                "tamano_pliego_h_mm": round(pliego_h, 2),
            },
            "trazado": {},
            "cruces": {},
            "marcas_exteriores": {},
            "marcas_medianales": {},
            "marca_texto": {},
            "capas": {},
        }

        # 2️⃣ TRAZADO: Recalcular posiciones exactas para corregir errores de offsets (sangres/calles)
        # Ignoramos los offsets x_mm/y_mm de 'impo_ui' porque a veces suman calles sin restar sangres.
        # Reconstruimos la posición basada en: Grid de Corte (Trim) y Calles.
        trazado = {}
        
        # Recuperar calles del grid_info
        calles_v = grid_info.get("calles_v", [])
        calles_h = grid_info.get("calles_h", [])
        
        # Mapa auxiliar para acceder por fila/columna rápidamente
        celdas_map = {}
        for key, cel in dims.items():
            if key.startswith("row_col:"):
                # Parsear "row_col: r,c"
                try:
                    parts = key.split(": ")[1].split(",")
                    r, c = int(parts[0]), int(parts[1])
                    celdas_map[(r, c)] = (key, cel)
                except:
                    pass
        
        # Obtener sangres iniciales para normalización (Celda 0,0 empieza en 0.0)
        # Si 0,0 tiene sangre izq 3mm, su Trim empieza en 3.0mm.
        cel_00_data = celdas_map.get((0,0), (None, {}))[1]
        sangre_izq_global = cel_00_data.get("sangre_izq_deseada", 0.0)
        sangre_sup_global = cel_00_data.get("sangre_sup_deseada", 0.0)

        # Variables acumuladoras para las posiciones del GRID DE CORTE (Trim Lines)
        # current_trim_y inicia en 'sangre_sup_global' para que al restar la sangre de la celda 0, quede en 0.0
        # (Efecto: Normalización)
        current_trim_y = sangre_sup_global 

        for r in range(rows):
            # Obtener alto de corte de esta fila (asumiendo altura uniforme o max de la fila)
            # Usamos la primera celda de la fila para determinar altura del trim
            ref_cel = celdas_map.get((r, 0), (None, {}))[1]
            h_celda_total = ref_cel.get("celda_h", 0.0)
            s_top = ref_cel.get("sangre_sup_deseada", 0.0)
            s_bot = ref_cel.get("sangre_inf_deseada", 0.0)
            h_trim = h_celda_total - s_top - s_bot
            if h_trim <= 0: h_trim = 100.0 # Fallback

            current_trim_x = sangre_izq_global # Inicia en offset para normalizar

            for c in range(cols):
                if (r, c) in celdas_map:
                    key, cel = celdas_map[(r, c)]
                    
                    # Datos de la celda actual
                    w_celda_total = cel.get("celda_w", 0.0)
                    s_izq = cel.get("sangre_izq_deseada", 0.0)
                    s_der = cel.get("sangre_der_deseada", 0.0)
                    s_sup = cel.get("sangre_sup_deseada", 0.0)    
                    
                    w_trim = w_celda_total - s_izq - s_der
                    
                    # La Posición de la Imagen (Bleed Box) es: Posición Corte - Sangre Izquierda
                    final_x_mm = current_trim_x - s_izq
                    final_y_mm = current_trim_y - s_sup
                    
                    # Guardar en trazado
                    trazado[key] = {
                        "pos_x_mm": round(final_x_mm, 2),
                        "pos_y_mm": round(final_y_mm, 2),
                        "celda_w_mm": round(w_celda_total, 2),
                        "celda_h_mm": round(cel.get("celda_h", 0.0), 2),
                        "sangre_izq_mm": round(s_izq, 2),
                        "sangre_sup_mm": round(s_sup, 2),
                        "offset_imagen_fritz_x_mm": round(cel.get("offset_imagen_x_left", 0.0), 2),
                        "offset_imagen_fritz_y_mm": round(cel.get("offset_imagen_y_top", 0.0), 2),
                    }
                    
                    # print(f"[DEBUG JSON RECALC] {key}: TrimX={current_trim_x:.2f}, SangreIzq={s_izq} -> PosX={final_x_mm:.2f}")
                    
                    # Avanzar X con el ancho de corte de ESTA celda + calle correspondiente
                    calle_v = calles_v[c] if c < len(calles_v) else 0.0
                    current_trim_x += w_trim + calle_v
            
            # Avanzar Y al terminar la fila
            calle_h = calles_h[r] if r < len(calles_h) else 0.0
            current_trim_y += h_trim + calle_h

        impo_export_data["trazado"] = {
            "celdas": trazado,
            "ancho_total_mm": round(dims.get("tamano_total_w", 0.0), 2),
            "alto_total_mm": round(dims.get("tamano_total_h", 0.0), 2),
        }

        # 3️⃣ CRUCES DE CORTE: solo tamaño final, parámetros y líneas
        cruces_data = dims.get("cruces_corte", {})
        if cruces_data:
            # Calcular el offset de transformación:
            # Las coordenadas en impo_stack se calculan sobre área de corte (636x196)
            # pero deben transformarse al espacio de cruces (676x236)
            cruces_solo_w = cruces_data.get("cruces_solo_w_mm", 0.0)
            cruces_solo_h = cruces_data.get("cruces_solo_h_mm", 0.0)
            trazado_w = cruces_data.get("trazado_w_mm", 0.0)
            trazado_h = cruces_data.get("trazado_h_mm", 0.0)
            
            # Offset para centrar el área de cálculo dentro del espacio de cruces
            offset_transformacion_x = (cruces_solo_w - trazado_w) / 2.0
            offset_transformacion_y = (cruces_solo_h - trazado_h) / 2.0
            
            # Aplicar transformación a todas las líneas de cruces
            lineas_originales = cruces_data.get("lineas_cruces", [])
            lineas_transformadas = []
            for linea in lineas_originales:
                linea_nueva = linea.copy()
                # ✅ CORRECCIÓN: NO aplicar offsets adicionales.
                # Las coordenadas ya vienen absolutas desde impo_stack.py
                linea_nueva["x_mm"] = round(linea["x_mm"], 4)
                linea_nueva["y_mm"] = round(linea["y_mm"], 4)
                # linea_nueva["x_mm"] = round(linea["x_mm"] + offset_transformacion_x, 4)
                # linea_nueva["y_mm"] = round(linea["y_mm"] + offset_transformacion_y, 4)
                lineas_transformadas.append(linea_nueva)
            
            impo_export_data["cruces"] = {
                "tamano_final_w_mm": round(cruces_data.get("tamano_final_w_mm", 0.0), 2),
                "tamano_final_h_mm": round(cruces_data.get("tamano_final_h_mm", 0.0), 2),
                "cruces_solo_w_mm": round(cruces_solo_w, 2),
                "cruces_solo_h_mm": round(cruces_solo_h, 2),
                "trazado_w_mm": round(trazado_w, 2),
                "trazado_h_mm": round(trazado_h, 2),
                "offset_trazado_x_mm": round(cruces_data.get("offset_trazado_x_mm", 0.0), 4),
                "offset_trazado_y_mm": round(cruces_data.get("offset_trazado_y_mm", 0.0), 4),
                # ✨ NUEVO: Offsets de cruces para Fritz PDF
                "offset_cruces_x_mm": round(cruces_data.get("offset_cruces_x_mm", 0.0), 4),
                "offset_cruces_y_mm": round(cruces_data.get("offset_cruces_y_mm", 0.0), 4),
                "extension_fuera_mm": round(cruces_data.get("extension_fuera_mm", 0.0), 2),
                "longitud_cruz_mm": round(cruces_data.get("longitud_cruz_mm", 0.0), 2),
                "offset_cruz_mm": round(cruces_data.get("offset_cruz_mm", 0.0), 2),
                "grosor_cruz_pt": round(cruces_data.get("grosor_cruz_pt", 0.0), 2),
                "grosor_cruz_mm": round(cruces_data.get("grosor_cruz_mm", 0.0), 4),
                "lineas_cruces": lineas_transformadas,  # ✅ Líneas con coordenadas transformadas
            }

        # 4️⃣ MARCAS EXTERIORES: tamaño, parámetros y líneas
        marcas_ext = dims.get("marcas_corte", {})
        if marcas_ext:
            impo_export_data["marcas_exteriores"] = {
                "ancho_total_mm": round(marcas_ext.get("ancho_total_mm", 0.0), 2),
                "alto_total_mm": round(marcas_ext.get("alto_total_mm", 0.0), 2),
                "longitud_marca_mm": round(marcas_ext.get("longitud_marca_mm", 0.0), 2),
                "grosor_marca_pt": round(marcas_ext.get("grosor_marca_pt", 0.0), 2),
                "grosor_marca_mm": round(marcas_ext.get("grosor_marca_mm", 0.0), 4),
                "num_lineas": marcas_ext.get("num_lineas", 0),
                "lineas_marcas": marcas_ext.get("lineas_marcas", []),
            }

        # 5️⃣ MARCAS MEDIANALES: parámetros y líneas
        marcas_med = dims.get("marcas_medianales", {})
        if marcas_med:
            impo_export_data["marcas_medianales"] = {
                "longitud_cruz_mm": marcas_med.get("longitud_cruz_mm", 0),
                "grosor_pt": round(marcas_med.get("grosor_pt", 0.0), 2),
                "grosor_mm": round(marcas_med.get("grosor_mm", 0.0), 4),
                "num_cruces": marcas_med.get("num_cruces", 0),
                "num_lineas": marcas_med.get("num_lineas", 0),
                "lineas_medianales": marcas_med.get("lineas_medianales", []),
            }

        # 6️⃣ MARCA TEXTO
        marca_txt = dims.get("marca_texto", {})
        if marca_txt:
            impo_export_data["marca_texto"] = {
                "contenido": marca_txt.get("contenido", ""),
                "posicion": marca_txt.get("posicion", ""),
                "offset_h_mm": marca_txt.get("offset_h_mm", 0),
                "offset_v_mm": marca_txt.get("offset_v_mm", 0.0),
                "rotacion": marca_txt.get("rotacion", 0),
                "familia": marca_txt.get("familia", ""),
                "tipo": marca_txt.get("tipo", ""),
                "cuerpo": marca_txt.get("cuerpo", 0),
                "color": marca_txt.get("color", ""),
            }

        # 7️⃣ CAPAS (offset + tamaño)
        orden_capas = [
            'capa_0_texto',
            'capa_1_marcas_med',
            'capa_2_marcas_ext',
            'capa_3_cruces',
            'capa_4_trazado',
            'capa_5_pliego',
        ]

        capas_raw = dims.get("capas")
        capas_export = {}
        if capas_raw:
            for capa in orden_capas:
                if capa in capas_raw:
                    c = capas_raw[capa]
                    
                    # ✅ CORRECCIÓN ESPECIAL PARA CAPA_3_CRUCES:
                    # La UI guarda el tamaño del pliego para mantener compatibilidad visual,
                    # pero el JSON debe exportar el tamaño real de cruces desde cruces_corte
                    # Y calcular el offset correcto para centrar respecto al pliego
                    if capa == "capa_3_cruces":
                        cruces_data = dims.get("cruces_corte", {})
                        pliego_data = capas_raw.get("capa_5_pliego", {})
                        
                        if cruces_data and pliego_data:
                            # Calcular offset para centrar cruces dentro del pliego
                            cruces_w = cruces_data.get("cruces_solo_w_mm", 0.0)
                            cruces_h = cruces_data.get("cruces_solo_h_mm", 0.0)
                            pliego_w = pliego_data.get("w_mm", 0.0)
                            pliego_h = pliego_data.get("h_mm", 0.0)
                            
                            # Offset de centrado automático
                            offset_x = (pliego_w - cruces_w) / 2.0
                            offset_y = (pliego_h - cruces_h) / 2.0
                            
                            # ✅ Sumar offset de usuario (ya invertido si es DORSO)
                            offset_usuario_x = dims.get("offset_usuario_x_mm", 0.0)
                            offset_usuario_y = dims.get("offset_usuario_y_mm", 0.0)
                            
                            offset_x += offset_usuario_x
                            offset_y += offset_usuario_y
                            
                            # Usar dimensiones reales de cruces con offset calculado
                            capas_export[capa] = {
                                "x_mm": round(offset_x, 2),
                                "y_mm": round(offset_y, 2),
                                "w_mm": round(cruces_w, 2),
                                "h_mm": round(cruces_h, 2),
                            }
                            # print(f"[DEBUG JSON EXPORT] capa_3_cruces corregida:")
                            # print(f"  • Pliego: {pliego_w:.2f} × {pliego_h:.2f} mm")
                            # print(f"  • Cruces: {cruces_w:.2f} × {cruces_h:.2f} mm")
                            # print(f"  • Offset centrado: ({(pliego_w - cruces_w) / 2.0:.2f}, {(pliego_h - cruces_h) / 2.0:.2f}) mm")
                            # print(f"  • Offset usuario: ({offset_usuario_x:.2f}, {offset_usuario_y:.2f}) mm")
                            # print(f"  • Offset final: ({offset_x:.2f}, {offset_y:.2f}) mm")
                        else:
                            # Fallback si no hay datos de cruces
                            capas_export[capa] = {
                                "x_mm": round(c.get("x_mm", 0.0), 2),
                                "y_mm": round(c.get("y_mm", 0.0), 2),
                                "w_mm": round(c.get("w_mm", 0.0), 2),
                                "h_mm": round(c.get("h_mm", 0.0), 2),
                            }
                    else:
                        # Para todas las demás capas, exportar tal cual, excepto
                        # capa_5_pliego: forzamos x_mm/y_mm = 0.0 para que el
                        # origen del pliego sea siempre (0,0) y el desplazamiento
                        # del trazado se lea exclusivamente desde capa_4_trazado.
                        if capa == "capa_5_pliego":
                            capas_export[capa] = {
                                "x_mm": 0.0,
                                "y_mm": 0.0,
                                "w_mm": round(c.get("w_mm", 0.0), 2),
                                "h_mm": round(c.get("h_mm", 0.0), 2),
                            }
                        else:
                            capas_export[capa] = {
                                "x_mm": round(c.get("x_mm", 0.0), 2),
                                "y_mm": round(c.get("y_mm", 0.0), 2),
                                "w_mm": round(c.get("w_mm", 0.0), 2),
                                "h_mm": round(c.get("h_mm", 0.0), 2),
                            }
        else:
            # Compatibilidad: construir `capas` a partir de offsets_capas + tamanos_capas
            offsets_raw = dims.get("offsets_capas", {})
            tamanos_raw = dims.get("tamanos_capas", {})
            for capa in orden_capas:
                if capa in offsets_raw or capa in tamanos_raw:
                    # Compatibilidad: forzar origen del pliego a 0,0
                    if capa == "capa_5_pliego":
                        capas_export[capa] = {
                            "x_mm": 0.0,
                            "y_mm": 0.0,
                            "w_mm": round(tamanos_raw.get(capa, {}).get("w_mm", 0.0), 2),
                            "h_mm": round(tamanos_raw.get(capa, {}).get("h_mm", 0.0), 2),
                        }
                    else:
                        capas_export[capa] = {
                            "x_mm": round(offsets_raw.get(capa, {}).get("x_mm", 0.0), 2),
                            "y_mm": round(offsets_raw.get(capa, {}).get("y_mm", 0.0), 2),
                            "w_mm": round(tamanos_raw.get(capa, {}).get("w_mm", 0.0), 2),
                            "h_mm": round(tamanos_raw.get(capa, {}).get("h_mm", 0.0), 2),
                        }

        impo_export_data["capas"] = capas_export

        # 8️⃣ IMAGEN (mediabox del PDF procesado)
        if mediabox_pts and isinstance(mediabox_pts, (list, tuple)) and len(mediabox_pts) == 4:
            try:
                x0, y0, x1, y1 = mediabox_pts
                mediabox_w_pts = abs(x1 - x0)
                mediabox_h_pts = abs(y1 - y0)
                
                # Conversión PT a MM (1 pt = 25.4/72 mm)
                PT_TO_MM = 25.4 / 72.0
                mediabox_w_mm = mediabox_w_pts * PT_TO_MM
                mediabox_h_mm = mediabox_h_pts * PT_TO_MM
                
                # Obtener offsets del usuario para páginas dentro de celdas
                offset_x = dims.get("offset_imagen_x_mm", 0.0)
                offset_y = dims.get("offset_imagen_y_mm", 0.0)
                
                impo_export_data["imagen"] = {
                    "mediabox_pts": {
                        "x0": round(x0, 2),
                        "y0": round(y0, 2),
                        "x1": round(x1, 2),
                        "y1": round(y1, 2),
                        "w_pts": round(mediabox_w_pts, 2),
                        "h_pts": round(mediabox_h_pts, 2),
                    },
                    "mediabox_mm": {
                        "x0": round(x0 * PT_TO_MM, 2),
                        "y0": round(y0 * PT_TO_MM, 2),
                        "x1": round(x1 * PT_TO_MM, 2),
                        "y1": round(y1 * PT_TO_MM, 2),
                        "w_mm": round(mediabox_w_mm, 2),
                        "h_mm": round(mediabox_h_mm, 2),
                    },
                    "offset_usuario_x_mm": round(offset_x, 2),
                    "offset_usuario_y_mm": round(offset_y, 2),
                }
            except Exception as ex:
                print(f"[WARNING] Error procesando mediabox: {ex}")

        return impo_export_data
    except Exception as e:
        print(f"[ERROR generar_impo_export_data] {e}")
        return None

def guardar_impo_export_data(impo_export_data, tipo_cara="CARA"):
    """
    Guarda el JSON de imposición en la variable global correspondiente.
    
    Args:
        impo_export_data: Diccionario con los datos de imposición
        tipo_cara: "CARA" o "DORSO"
    """
    global _IMPO_EXPORT_DATA_CARA, _IMPO_EXPORT_DATA_DORSO
    
    if tipo_cara == "CARA":
        _IMPO_EXPORT_DATA_CARA = impo_export_data
        print(f"[INFO] JSON de imposición CARA guardado ({len(json.dumps(impo_export_data))} bytes)")
    elif tipo_cara == "DORSO":
        _IMPO_EXPORT_DATA_DORSO = impo_export_data
        print(f"[INFO] JSON de imposición DORSO guardado ({len(json.dumps(impo_export_data))} bytes)")
    else:
        print(f"[WARNING] Tipo de cara desconocido: {tipo_cara}")

def obtener_impo_export_data(tipo_cara="CARA"):
    """
    Obtiene el JSON de imposición guardado.
    
    Args:
        tipo_cara: "CARA" o "DORSO"
    
    Returns:
        dict: JSON de imposición o None si no existe
    """
    global _IMPO_EXPORT_DATA_CARA, _IMPO_EXPORT_DATA_DORSO
    
    if tipo_cara == "CARA":
        return _IMPO_EXPORT_DATA_CARA
    elif tipo_cara == "DORSO":
        return _IMPO_EXPORT_DATA_DORSO
    else:
        print(f"[WARNING] Tipo de cara desconocido: {tipo_cara}")
        return None

def imprimir_impo_export_data(impo_export_data, enabled=True):
    """
    Imprime el JSON de `impo_export_data` si `enabled` es True.
    
    Args:
        impo_export_data: Diccionario con los datos de imposición
        enabled: Si True, imprime el JSON
    """
    if not enabled or not impo_export_data:
        return
    try:
        tipo_cara = impo_export_data.get("tipo_cara", "DESCONOCIDO")
        print("\n" + "=" * 100)
        print(f"[RAW JSON impo_export_data - {tipo_cara}]")
        print("=" * 100)
        print(json.dumps(impo_export_data, indent=2, ensure_ascii=False))
        print("=" * 100 + "\n")
    except Exception as e:
        print(f"[ERROR imprimir_impo_export_data] {e}")
