import math
import sys
import os
import platform
import flet as ft
import flet.canvas as cv
from PIL import ImageFont
from color_design import *
from lang import t

# Silenciar prints de depuración en este módulo por defecto.
# Para activar, cambiar _PRINT_DEBUG = True durante desarrollo.
_PRINT_DEBUG = False
if not _PRINT_DEBUG:
    def _no_print(*args, **kwargs):
        return None

    print = _no_print

def get_font_path():
    """
    Obtiene la ruta correcta de Arial Unicode.ttf tanto en desarrollo como en EXE empaquetado.
    """
    font_name = "Arial Unicode.ttf"
    if getattr(sys, 'frozen', False):
        # En EXE empaquetado: la fuente está en sys._MEIPASS
        font_path = os.path.join(sys._MEIPASS, font_name)
        return font_path
    else:
        # En desarrollo: la fuente está en el directorio actual
        return font_name


# --- Función para obtener el factor de corrección según plataforma y empaquetado ---
def get_factor_correccion_ancho():
    """
    Devuelve el factor de corrección para el ancho de texto según:
    - macOS: 0.90
    - Windows/PC: 0.80
    - Si está empaquetado (EXE): factor más agresivo (0.70)
    """
    if getattr(sys, 'frozen', False):
        # Ejecutándose desde EXE empaquetado - usar factor más agresivo
        return 0.70
    elif platform.system() == "Darwin":
        # macOS
        return 0.75
    else:
        # Windows/PC u otros
        return 0.75





# Variable global para guardar los datos del gráfico
grafico_datos = {
    "lineas": [],
    "numeros": [],
    "entrada": {},
    "salida": {}
}

# --- Función auxiliar para calcular el total de hojas ajustado ---
def calcular_total_hojas_ajustado(cantidad, can_hojas_tal, hojas_x_pliego):
    talonarios = int(cantidad) if cantidad and str(cantidad).isdigit() else 0
    hojas_por_tal = int(can_hojas_tal) if can_hojas_tal and str(can_hojas_tal).isdigit() else 0
    hojas_x_pliego_val = int(hojas_x_pliego) if hojas_x_pliego and str(hojas_x_pliego).isdigit() else 1
    talonarios_ajustados = talonarios
    while (talonarios_ajustados * hojas_por_tal) % hojas_x_pliego_val != 0:
        talonarios_ajustados += 1
    return talonarios_ajustados * hojas_por_tal

def calcular_cuerpo_texto_pillow(alto_celda, texto, fuente_path=None, min_size=10, max_size=25, shrink_factor=1, correction_factor=1.0):
    if fuente_path is None:
        fuente_path = get_font_path()
    alto_celda_reducido = alto_celda * shrink_factor
    try:
        font = ImageFont.truetype(fuente_path, max_size)
    except Exception:
        font = ImageFont.load_default()
        
    try:
        bbox = font.getbbox(str(texto))
        alto_texto = (bbox[3] - bbox[1]) * correction_factor
        if alto_texto <= alto_celda_reducido:
            return max_size
    except Exception:
        pass

    size = max_size - 1
    while size >= min_size:
        try:
            font = ImageFont.truetype(fuente_path, size)
        except Exception:
            font = ImageFont.load_default()
        try:
            bbox = font.getbbox(str(texto))
            alto_texto = (bbox[3] - bbox[1]) * correction_factor
            if alto_texto <= alto_celda_reducido:
                return size
        except Exception:
            pass
        size -= 1
    return min_size

def texto_cabe_horizontal(ancho_celda, texto, size, margen_seguridad):
    """
    Determina si el texto cabe horizontalmente en la celda usando medidas exactas de PIL.
    Usa el mismo método que el PDF para consistencia.
    """
    FACTOR_CORRECCION_ANCHO =0.80 # mac 0.90
    try:
        font = ImageFont.truetype(get_font_path(), int(size))
        # # # print(f"[# # print] Fuente cargada correctamente en texto_cabe_horizontal: {get_font_path()}, size={size}")
        bbox = font.getbbox(str(texto))
        ancho_texto = (bbox[2] - bbox[0]) * FACTOR_CORRECCION_ANCHO
    except Exception as e:
        # # # print(f"[# # print] No se pudo cargar la fuente '{get_font_path()}' en texto_cabe_horizontal: {e}")
        # # # print(f"[# # print] Usando fuente por defecto (fallback) en texto_cabe_horizontal")
        num_digitos = len(str(texto))
        ancho_texto = num_digitos * size * FACTOR_CORRECCION_ANCHO

    cabe = (ancho_texto + margen_seguridad) <= ancho_celda
    # # # print(f"[DEBUG texto_cabe_horizontal] texto={texto}, size={size}, ancho_celda={ancho_celda:.1f}, ancho_texto={ancho_texto:.1f} (corregido x{FACTOR_CORRECCION_ANCHO}), margen_seguridad={margen_seguridad}, cabe={cabe}")
    return cabe

def agregar_texto_numero(textos, grafico_datos, x, y, inicio, cuerpo, rotar=False):
    if rotar:
        textos.append(cv.Text(x, y, f"{inicio}", ft.TextStyle(size=cuerpo, weight=ft.FontWeight.BOLD, color=TEXTO_NUMEROS_GRAFICO_COLOR), alignment=ft.Alignment.CENTER, rotate=math.pi/2))
    else:
        textos.append(cv.Text(x, y, f"{inicio}", ft.TextStyle(size=cuerpo, weight=ft.FontWeight.BOLD, color=TEXTO_NUMEROS_GRAFICO_COLOR), alignment=ft.Alignment.CENTER))
    # Obtener ancho_celda desde el contexto global si existe
    ancho_celda = grafico_datos.get("ancho_celda", None)
    grafico_datos["numeros"].append({
        "x": x,
        "y": y,
        "texto": f"{inicio}",
        "size": cuerpo,
        "rotar": rotar,
        "color": "black",
        "ancho_celda": ancho_celda
    })

def agregar_marco_exterior(lineas, grafico_datos, ancho, alto):
    lineas.append(cv.Line(0, 0, ancho, 0, paint=ft.Paint(stroke_width=3, color=MARCO_GRAFICO_COLOR, anti_alias=True)))
    lineas.append(cv.Line(ancho, 0, ancho, alto, paint=ft.Paint(stroke_width=3, color=MARCO_GRAFICO_COLOR, anti_alias=True)))
    lineas.append(cv.Line(ancho, alto, 0, alto, paint=ft.Paint(stroke_width=3, color=MARCO_GRAFICO_COLOR, anti_alias=True)))
    lineas.append(cv.Line(0, alto, 0, 0, paint=ft.Paint(stroke_width=3, color=MARCO_GRAFICO_COLOR, anti_alias=True)))
    grafico_datos["lineas"].append({"x1": 0, "y1": 0, "x2": ancho, "y2": 0, "color": "black", "grosor": 3, "discontinua": False})
    grafico_datos["lineas"].append({"x1": ancho, "y1": 0, "x2": ancho, "y2": alto, "color": "black", "grosor": 3, "discontinua": False})
    grafico_datos["lineas"].append({"x1": ancho, "y1": alto, "x2": 0, "y2": alto, "color": "black", "grosor": 3, "discontinua": False})
    grafico_datos["lineas"].append({"x1": 0, "y1": alto, "x2": 0, "y2": 0, "color": "black", "grosor": 3, "discontinua": False})

def agregar_linea_discontinua_vertical(x, alto, lineas, grafico_datos):

    y_actual = 5
    dash = 10
    gap = 10
    while y_actual < alto:
        y_fin = min(y_actual + dash, alto)
        lineas.append(cv.Line(x, y_actual, x, y_fin, paint=ft.Paint(stroke_width=2, color=LINEA_DISCONTINUA_GRAFICO_COLOR, anti_alias=True)))
        grafico_datos["lineas"].append({"x1": x, "y1": y_actual, "x2": x, "y2": y_fin, "color": "black", "grosor": 2, "discontinua": True})
        y_actual += dash + gap

def agregar_linea_discontinua_horizontal(y, ancho, lineas, grafico_datos):
    x_actual = 5
    dash = 10
    gap = 10
    while x_actual < ancho:
        x_fin = min(x_actual + dash, ancho)
        lineas.append(cv.Line(x_actual, y, x_fin, y, paint=ft.Paint(stroke_width=2, color=LINEA_DISCONTINUA_GRAFICO_COLOR, anti_alias=True)))
        grafico_datos["lineas"].append({"x1": x_actual, "y1": y, "x2": x_fin, "y2": y, "color": "black", "grosor": 2, "discontinua": True})
        x_actual += dash + gap

def agregar_linea_continua_vertical(x, alto, lineas, grafico_datos):
    lineas.append(cv.Line(x, 0, x, alto, paint=ft.Paint(stroke_width=2, color=LINEA_CONTINUA_GRAFICO_COLOR, anti_alias=True)))
    grafico_datos["lineas"].append({"x1": x, "y1": 0, "x2": x, "y2": alto, "color": "black", "grosor": 2, "discontinua": False})

def agregar_linea_continua_horizontal(y, ancho, lineas, grafico_datos):
    lineas.append(cv.Line(0, y, ancho, y, paint=ft.Paint(stroke_width=2, color=LINEA_CONTINUA_GRAFICO_COLOR, anti_alias=True)))
    grafico_datos["lineas"].append({"x1": 0, "y1": y, "x2": ancho, "y2": y, "color": "black", "grosor": 2, "discontinua": False})

# --- Función para determinar si la columna de numeros tiene que rotar ---
def debe_rotar_columna(columna, vertical, horizontal, comienzo, hojas_por_bloque, resto, ancho_celda, alto_celda, orientacion):
    """
    Determina si una columna completa debe rotar.
    Simplificada: rota si el ancho de celda es menor que el alto
    """
    return ancho_celda < alto_celda

def debe_rotar_todos(horizontal, vertical, comienzo, hojas_por_bloque, resto, ancho_celda, alto_celda, orientacion):
    """
    Determina si todos los números deben rotar.
    Simplificada: rota si el ancho de celda es menor que el alto
    """
    return ancho_celda < alto_celda, 25


def generar_listas_fiery(ordenamiento_pdf):
    """
    Genera listas de páginas agrupadas por número de copia para configuración en Fiery.
    
    Args:
        ordenamiento_pdf (dict): Diccionario de ordenamiento PDF
    
    Returns:
        dict: Diccionario con listas por copia {1: [páginas], 2: [páginas], ...}
    """
    if not ordenamiento_pdf:
        return {}
    
    # Agrupar páginas por numero_copia
    listas_fiery = {}
    
    for pagina, datos in ordenamiento_pdf.items():
        numero_copia = datos['numero_copia']
        
        if numero_copia not in listas_fiery:
            listas_fiery[numero_copia] = []
        
        listas_fiery[numero_copia].append(pagina)
    
    # Ordenar las páginas dentro de cada lista
    for copia in listas_fiery:
        listas_fiery[copia].sort()
    
    return listas_fiery

def imprimir_listas_fiery(listas_fiery):
    """
    Imprime las listas de Fiery en formato legible para debug.
    """
    # # print("\n[DEBUG] Listas para Fiery:")
    for copia, paginas in sorted(listas_fiery.items()):
        paginas_str = ','.join(map(str, paginas))
        # # print(f"Copia {copia}: {paginas_str}")
    # # print()

def generar_ordenamiento_pdf_montaje(orden_grafico_visual, doble_cara=False, numero_copias=1, comienzo_numeracion=1):
    """
    Genera un diccionario de ordenamiento PDF según el patrón del orden gráfico visual.
    
    Args:
        orden_grafico_visual (list): Lista con el orden del gráfico visual
        doble_cara (bool): Si cada hoja tiene 2 páginas (frente y dorso) - duplica las páginas PDF
        numero_copias (int): Número de copias del conjunto - multiplica las páginas
    
    Returns:
        dict: Diccionario con estructura {pagina: {'datos': [numeros], 'numero_copia': int, 'doble_cara': str}}
    """
    # print(f"[DEBUG generar_ordenamiento_pdf_montaje] Parámetros: doble_cara={doble_cara}, numero_copias={numero_copias}, comienzo_numeracion={comienzo_numeracion}")
    
    if not orden_grafico_visual:
        # # print("[DEBUG generar_ordenamiento_pdf_montaje] No hay datos de orden gráfico visual")
        return {}
    
    # Detectar el patrón basado en el primer elemento
    es_patron_abajo = orden_grafico_visual[0].startswith('col')
    patron_tipo = "Abajo (col0_fila0)" if es_patron_abajo else "Izquierda (fila0_col0)"
    # print(f"[DEBUG generar_ordenamiento_pdf_montaje] Patrón detectado: {patron_tipo}")
    
    # Analizar los datos para extraer rangos de números con sus posiciones
    elementos = []
    for item in orden_grafico_visual:
        # Extraer información completa: posición en grilla y rango
        if "->texto:" in item:
            partes = item.split("->")
            posicion = partes[0]  # ej: "col0_fila0" o "fila0_col0"
            texto_parte = partes[2]  # texto después de "->texto:"
            
            # Extraer solo la parte numérica después de "texto:"
            if "texto:" in texto_parte:
                texto_numerico = texto_parte.split("texto:")[1]
                
                if " - " in texto_numerico:
                    inicio, fin = texto_numerico.split(" - ")
                    try:
                        # Convertir números visuales a números reales del PDF
                        # Si comienzo_numeracion es 1, no restar nada
                        # Si es mayor que 1, restar (comienzo_numeracion - 1)
                        offset = comienzo_numeracion - 1 if comienzo_numeracion > 1 else 0
                        inicio_real = int(inicio) - offset
                        fin_real = int(fin) - offset
                        
                        # print(f"[DEBUG] Conversión - inicio: {inicio} -> {inicio_real}, fin: {fin} -> {fin_real}, offset: {offset}")
                        
                        elementos.append({
                            'posicion': posicion,
                            'inicio': inicio_real,
                            'fin': fin_real
                        })
                    except ValueError:
                        continue
    
    if not elementos:
        # # print("[DEBUG generar_ordenamiento_pdf_montaje] No se encontraron elementos válidos")
        return {}
    
    # Determinar el total de hojas necesarias
    # hojas_por_bloque es para una celda, necesitamos el total de todas las hojas
    hojas_por_bloque = elementos[0]['fin'] - elementos[0]['inicio'] + 1
    numero_celdas = len(elementos)
    total_hojas_necesarias = hojas_por_bloque * numero_celdas
    
    # Calcular páginas del PDF según el tipo de impresión
    if doble_cara:
        # En doble cara: cada hoja física = 2 páginas del PDF (frente + dorso)
        total_paginas_pdf_original = total_hojas_necesarias * 2
    else:
        # En una cara: cada hoja física = 1 página del PDF
        total_paginas_pdf_original = total_hojas_necesarias
    
    # print(f"[DEBUG generar_ordenamiento_pdf_montaje] Hojas por bloque (celda): {hojas_por_bloque}")
    # print(f"[DEBUG generar_ordenamiento_pdf_montaje] Número de celdas: {numero_celdas}")
    # print(f"[DEBUG generar_ordenamiento_pdf_montaje] Total hojas necesarias: {total_hojas_necesarias}")
    # print(f"[DEBUG generar_ordenamiento_pdf_montaje] Doble cara: {doble_cara}")
    # print(f"[DEBUG generar_ordenamiento_pdf_montaje] PDF original debe tener: {total_paginas_pdf_original} páginas")
    # print(f"[DEBUG generar_ordenamiento_pdf_montaje] Número de copias: {numero_copias}")
    
    # Las páginas de salida del PDF reorganizado = páginas del PDF original
    if doble_cara:
        total_paginas_salida = total_paginas_pdf_original * numero_copias
    else:
        total_paginas_salida = total_hojas_necesarias * numero_copias
    # print(f"[DEBUG generar_ordenamiento_pdf_montaje] Total páginas de salida: {total_paginas_salida}")
    
    # Crear el diccionario de ordenamiento según el patrón
    ordenamiento_pdf = {}

    if es_patron_abajo:
        elementos_reordenados = reorganizar_patron_abajo(elementos)
    else:
        elementos_reordenados = elementos

    # Nuevo enfoque: iterar por offset dentro de cada bloque (hojas_por_bloque)
    # para producir secuencias como [1,26,51,76], [2,27,52,77], ...
    numero_pagina_actual = 1

    if doble_cara:
        # Generación por pliego (offset) y dentro de cada pliego por copia.
        # Resultado: para cada offset se generará (cara copia1, dorso copia1, cara copia2, dorso copia2, ...)
        elementos_ordenados = elementos_reordenados  # usar el orden ya calculado (reorganizar_patron_abajo si aplica)
        for offset in range(0, hojas_por_bloque):
            for copia_actual in range(1, numero_copias + 1):
                # CARA: páginas impares por cada elemento en el orden lógico
                datos_cara = []
                for elemento in elementos_ordenados:
                    numero_talonario = elemento['inicio'] + offset
                    if numero_talonario <= elemento['fin']:
                        pagina_pdf_cara = (numero_talonario - 1) * 2 + 1
                        datos_cara.append(pagina_pdf_cara)

                ordenamiento_pdf[numero_pagina_actual] = {
                    'datos': datos_cara,
                    'numero_copia': copia_actual,
                    'doble_cara': 'cara'
                }
                numero_pagina_actual += 1

                # DORSO: construir a partir de datos_cara (intercambiando pares) - mantiene correspondencia cara/dorso por copia
                datos_dorso = []
                for i in range(0, len(datos_cara), 2):
                    if i + 1 < len(datos_cara):
                        datos_dorso.append(datos_cara[i + 1] + 1)
                        datos_dorso.append(datos_cara[i] + 1)
                    else:
                        datos_dorso.append(datos_cara[i] + 1)

                ordenamiento_pdf[numero_pagina_actual] = {
                    'datos': datos_dorso,
                    'numero_copia': copia_actual,
                    'doble_cara': 'dorso'
                }
                numero_pagina_actual += 1
    else:
        # En una cara: iterar por offset (cada offset = 1 pliego con N páginas)
        elementos_ordenados = elementos_reordenados
        for offset in range(0, hojas_por_bloque):
            for copia_actual in range(1, numero_copias + 1):
                datos_cara = []
                for elemento in elementos_ordenados:
                    numero_talonario = elemento['inicio'] + offset
                    if numero_talonario <= elemento['fin']:
                        datos_cara.append(numero_talonario)
                
                ordenamiento_pdf[numero_pagina_actual] = {
                    'datos': datos_cara,
                    'numero_copia': copia_actual,
                    'doble_cara': 'cara'
                }
                numero_pagina_actual += 1

    # Imprimir TODAS las páginas del ordenamiento para debug
    # print(f"[DEBUG generar_ordenamiento_pdf_montaje] TODAS las páginas del ordenamiento:")
    for i in sorted([k for k in ordenamiento_pdf.keys() if k != '_metadata']):
        if i in ordenamiento_pdf and _PRINT_DEBUG:
            print(f"  Página {i}: {ordenamiento_pdf[i]}")

    # print(f"[DEBUG generar_ordenamiento_pdf_montaje] Total pliegos generados: {len(ordenamiento_pdf) - 1}")

    ordenamiento_pdf['_metadata'] = {
        'paginas_pdf_original': total_paginas_pdf_original,
        'paginas_generadas': len(ordenamiento_pdf),
        'numero_copias': numero_copias,
        'doble_cara': doble_cara
    }

    return ordenamiento_pdf


def reorganizar_patron_abajo(elementos):
    """
    Reorganiza los elementos del patrón 'Abajo' (col0_fila0) al orden de llenado por filas.
    
    Entrada: col0_fila0->col0_fila1->col1_fila0->col1_fila1->col2_fila0->col2_fila1->col3_fila0->col3_fila1
    Salida: fila0_col0->fila0_col1->fila0_col2->fila0_col3->fila1_col0->fila1_col1->fila1_col2->fila1_col3
    
    Es decir: primero todos los elementos de fila 0, luego todos los de fila 1
    """
    # Crear un diccionario para mapear por fila y columna
    mapa_elementos = {}
    
    for elemento in elementos:
        posicion = elemento['posicion']
        # Extraer col y fila de "col0_fila0"
        if posicion.startswith('col') and '_fila' in posicion:
            partes = posicion.split('_')
            col = int(partes[0].replace('col', ''))
            fila = int(partes[1].replace('fila', ''))
            
            if fila not in mapa_elementos:
                mapa_elementos[fila] = {}
            mapa_elementos[fila][col] = elemento
    
    # Reorganizar: primero todos de fila 0 (por orden de columna), luego todos de fila 1 (por orden de columna)
    elementos_reordenados = []
    for fila in sorted(mapa_elementos.keys()):
        for col in sorted(mapa_elementos[fila].keys()):
            elementos_reordenados.append(mapa_elementos[fila][col])
    
    return elementos_reordenados


def dibujar_grafico(horizontal, vertical, cantidad, can_hojas_tal, hojas_x_pliego, comienzo_numeracion, orientacion, talonarios_calculados=None, talonarios_fase1=None, ancho=880, alto=620):
    global grafico_datos
    global COLOR_FONDO_GRAFICO
    

    # print(f"[DEBUG dibujar_grafico] horizontal={horizontal}, vertical={vertical}, cantidad={cantidad}, can_hojas_tal={can_hojas_tal}, hojas_x_pliego={hojas_x_pliego}, comienzo_numeracion={comienzo_numeracion}, orientacion={orientacion}")
    # print(f"[DEBUG dibujar_grafico] talonarios_calculados={talonarios_calculados}, talonarios_fase1={talonarios_fase1}")

    # Actualizar datos de entrada en grafico_datos
    grafico_datos["entrada"] = {
        "cantidad": cantidad,
        "hojas_por_tal": can_hojas_tal,
        "hojas_x_pliego": hojas_x_pliego,
        "horizontal": horizontal,
        "vertical": vertical,
        "comienzo": comienzo_numeracion,
        "orientacion": orientacion,
        "talonarios_calculados": talonarios_calculados if talonarios_calculados is not None else cantidad,
        "talonarios_fase1": talonarios_fase1 if talonarios_fase1 is not None else cantidad
    }
    grafico_datos["lineas"] = []
    grafico_datos["numeros"] = []

    ## print(f"[DEBUG grafico.py] Datos de entrada actualizados: {grafico_datos['entrada']}")

    lineas = []
    textos = []
    # Usar el color de fondo configurable
    fondo = cv.Rect(0, 0, ancho, alto, paint=ft.Paint(color=COLOR_FONDO_GRAFICO, anti_alias=False))

    # Agregar marco exterior
    agregar_marco_exterior(lineas, grafico_datos, ancho, alto)

    # Calcular dimensiones de las celdas
    ancho_celda = ancho / horizontal
    grafico_datos["ancho_celda"] = ancho_celda
    alto_celda = alto / vertical

    # print(f"[DEBUG dibujar_grafico] ancho_celda={ancho_celda}, alto_celda={alto_celda}")

    # Líneas verticales (columnas) - Lógica compleja del código original
    # Solo dibujar líneas verticales si NO es el caso especial horizontal>1, vertical==1, orientacion=="Abajo"
    if horizontal > 1 and not (horizontal > 1 and vertical == 1 and orientacion == "Abajo"):
        paso_x = ancho / horizontal
        for i in range(1, horizontal):
            x = int(i * paso_x)
            if orientacion == "Izquierda":
                # Dibujar línea vertical discontinua
                agregar_linea_discontinua_vertical(x, alto, lineas, grafico_datos)
            else:
                agregar_linea_continua_vertical(x, alto, lineas, grafico_datos)
                
    # CASO ESPECIAL: horizontal=1 y vertical>1 y orientacion=="Izquierda"
    if horizontal == 1 and vertical > 1 and orientacion == "Izquierda":
        paso_x = ancho / vertical
        for i in range(1, vertical):
            x = int(i * paso_x)
            agregar_linea_discontinua_horizontal(y, ancho, lineas, grafico_datos)

    # CASO ESPECIAL: horizontal=1 y vertical>1 y orientacion=="Abajo"
    elif horizontal == 1 and vertical > 1 and orientacion == "Abajo":
        paso_y = alto / vertical
        for i in range(1, vertical):
            y = int(i * paso_y)
            agregar_linea_discontinua_horizontal(y, ancho, lineas, grafico_datos)
            
    elif vertical > 1:
        paso_y = alto / vertical
        for i in range(1, vertical):
            y = int(i * paso_y)

            # CASO ESPECIAL: horizontal=1 y vertical>1 y orientacion=="Izquierda"
            if horizontal == 1 and orientacion == "Izquierda":
                # Solo dibujar línea horizontal discontinua
                agregar_linea_discontinua_horizontal(y, ancho, lineas, grafico_datos)
            elif horizontal == 1:
                if orientacion == "Abajo":
                    # Líneas horizontales discontinuas
                    agregar_linea_discontinua_horizontal(y, ancho, lineas, grafico_datos)
            else:
                # Caso normal: orientación afecta solo si vertical>1 y horizontal>1
                if orientacion == "Abajo":
                    agregar_linea_discontinua_horizontal(y, ancho, lineas, grafico_datos)
                else:
                    agregar_linea_continua_horizontal(y, ancho, lineas, grafico_datos)

    # Usar los valores ajustados recibidos directamente
    total_hojas = cantidad * can_hojas_tal
    comienzo = int(comienzo_numeracion) if comienzo_numeracion else 1

    # Calcular números por celda
    n_celdas = horizontal * vertical
    hojas_por_bloque = total_hojas // n_celdas if n_celdas > 0 else 0
    resto = total_hojas % n_celdas if n_celdas > 0 else 0

    # --- ELIMINADO: Cálculo del tamaño de fuente óptimo ---
    # --- ELIMINADO: Generar lista de ordenamiento de páginas PDF para montaje ---

    FACTOR_CORRECCION_ANCHO = 1.17
    margen_seguridad = 3
    fuente_path = get_font_path()
    size_max = 25
    size_min = 10

    # Determinar si todos los números deben rotar (independiente de la orientación)
    rotar_todos, _ = debe_rotar_todos(horizontal, vertical, comienzo, hojas_por_bloque, resto, ancho_celda, alto_celda, orientacion)

    # Usar tamaño fijo por simplicidad
    size_optimo = size_max

    # Usar el size_optimo calculado para todos los textos
    idx = 0
    orden_grafico_visual = []  # Para debug: capturar el orden real del gráfico
    
    if orientacion == "Abajo":
        # Distribuir por filas: recorrer primero columnas, luego filas
        for columna in range(horizontal):
            for fila in range(vertical):
                x = (columna + 0.5) * ancho_celda
                y = (fila + 0.5) * alto_celda
                # Calcular el número de inicio para esta celda
                numero_inicio = comienzo + (idx * hojas_por_bloque)
                numero_fin = numero_inicio + hojas_por_bloque - 1
                texto_rango = f"{numero_inicio} - {numero_fin}"
                cuerpo_texto = size_optimo
                rotar = rotar_todos
                orden_grafico_visual.append(f"col{columna}_fila{fila}->pos({x:.1f},{y:.1f})->texto:{texto_rango}")
                agregar_texto_numero(textos, grafico_datos, x, y, texto_rango, cuerpo_texto, rotar)
                idx += 1
    else:
        # Distribuir por columnas: recorrer primero filas, luego columnas (comportamiento original)
        for fila in range(vertical):
            for columna in range(horizontal):
                x = (columna + 0.5) * ancho_celda
                y = (fila + 0.5) * alto_celda
                # Calcular el número de inicio para esta celda
                numero_inicio = comienzo + (idx * hojas_por_bloque)
                numero_fin = numero_inicio + hojas_por_bloque - 1
                texto_rango = f"{numero_inicio} - {numero_fin}"
                cuerpo_texto = size_optimo
                rotar = rotar_todos
                orden_grafico_visual.append(f"fila{fila}_col{columna}->pos({x:.1f},{y:.1f})->texto:{texto_rango}")
                agregar_texto_numero(textos, grafico_datos, x, y, texto_rango, cuerpo_texto, rotar)
                idx += 1

    # Actualizar salida en grafico_datos
    tirada_fase1 = int(cantidad) * int(can_hojas_tal) if str(cantidad).isdigit() and str(can_hojas_tal).isdigit() else 0
    # print(f"[DEBUG grafico.py] tirada_fase1 (original): {tirada_fase1}, total_hojas (ajustado): {total_hojas}")
    grafico_datos["salida"] = {
        "tirada": total_hojas,
        "tirada_calculada": hojas_por_bloque * n_celdas + resto,
        "total_hojas": total_hojas,
        "tirada_fase1": tirada_fase1  # SIEMPRE el cálculo original, nunca el ajustado
    }


    # Guardar orden_grafico_visual para que la UI de ordenamiento pueda acceder a él
    grafico_datos["orden_grafico_visual"] = orden_grafico_visual

    # print(f"[DEBUG dibujar_grafico] Datos finales en grafico_datos: {grafico_datos}")

    # Retornar el canvas generado
    return cv.Canvas([fondo] + lineas + textos, width=ancho, height=alto)



