import os
import tempfile
import sys
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from PIL import Image, ImageDraw, ImageFont
from lang import t

# Silenciar prints de depuración en este módulo por defecto.
# Para activar, cambiar _PRINT_DEBUG = True durante desarrollo.
_PRINT_DEBUG = False
if not _PRINT_DEBUG:
    def _no_print(*args, **kwargs):
        return None

    print = _no_print


def obtener_font_path():
    """
    Obtiene la ruta correcta de la fuente Arial Unicode para la plataforma actual.
    """
    # Primero intentar con la fuente incluida en el bundle
    font_paths = [
        "Arial Unicode.ttf",  # En el directorio de la aplicación
        "./Arial Unicode.ttf",  # Ruta relativa
        os.path.join(os.path.dirname(__file__), "Arial Unicode.ttf"),  # Junto al script
    ]
    
    # Si estamos en un bundle de PyInstaller, buscar en el directorio temporal
    if hasattr(sys, '_MEIPASS'):
        font_paths.insert(0, os.path.join(sys._MEIPASS, "Arial Unicode.ttf"))
    
    for font_path in font_paths:
        if os.path.exists(font_path):
            return font_path
    
    # Si no encontramos Arial Unicode, usar fuentes del sistema
    return None

def crear_fuente_segura(size=24):
    """
    Crea una fuente de forma segura, probando primero Arial Unicode y fallback a fuente por defecto.
    """
    font_path = obtener_font_path()
    
    if font_path:
        try:
            return ImageFont.truetype(font_path, size)
        except Exception:
            pass
    
    # Fallback a fuente por defecto
    try:
        return ImageFont.load_default()
    except Exception:
        # Último recurso - crear una fuente muy básica
        return None

def generar_grafico_optimizado(grafico_datos):
    """
    Genera un gráfico a partir de los datos recibidos, sin aplicar escalado previo.
    Esta función trabaja con los datos originales y genera una imagen completa.
    
    Args:
        grafico_datos: Diccionario con los datos del gráfico
        
    Returns:
        Una imagen PIL con el gráfico y la ruta temporal donde se guardó
    """
    entrada = grafico_datos.get("entrada", {})
    #print(f"[DEBUG] Entrada para gráfico: {entrada}")
    
    # Usar las dimensiones originales del gráfico
    img_w = max(int(entrada.get("ancho", 1200)), 1200)
    img_h = max(int(entrada.get("alto", 900)), 900)
        # print(f"[DEPURACIÓN] Creando gráfico con dimensiones: {img_w}x{img_h}")
    
    # Crear la imagen con el tamaño correcto
    img = Image.new("RGBA", (img_w, img_h), "white")
    draw = ImageDraw.Draw(img, 'RGBA')
    
    # Dibujar líneas - trabajamos con las coordenadas originales
    for linea in grafico_datos["lineas"]:
        x1, y1, x2, y2 = linea["x1"], linea["y1"], linea["x2"], linea["y2"]
        color = linea.get("color", "black")
        grosor = linea.get("grosor", 2)
        
        if linea.get("discontinua", False):
            dash = 10
            gap = 10
            if x1 == x2:  # vertical
                y_actual = y1
                while y_actual < y2:
                    y_fin = min(y_actual + dash, y2)
                    draw.line([(x1, y_actual), (x2, y_fin)], fill=color, width=grosor)
                    y_actual += dash + gap
            elif y1 == y2:  # horizontal
                x_actual = x1
                while x_actual < x2:
                    x_fin = min(x_actual + dash, x2)
                    draw.line([(x_actual, y1), (x_fin, y2)], fill=color, width=grosor)
                    x_actual += dash + gap
        else:
            draw.line([(x1, y1), (x2, y2)], fill=color, width=grosor)
    
    # Dibujar números - también con coordenadas originales
    for num in grafico_datos["numeros"]:
        x, y = num["x"], num["y"]
        texto = str(num["texto"])
        size = int(num.get("size", 24))
        rotar = num.get("rotar", False)
        color = num.get("color", "black")
        try:
            font_num = crear_fuente_segura(size)
        except Exception:
            font_num = ImageFont.load_default()
        
        
        if rotar:
            # Crear una imagen temporal para el texto rotado con margen suficiente
            # Usamos un contenedor más grande para evitar recortes
            # Añadir padding para dejar espacio entre líneas
            padding_vertical = 8  # Ajusta este valor según necesites más o menos espacio
            padding_horizontal = 6  # Ajusta este valor según necesites más o menos espacio
            bbox = font_num.getbbox(texto)
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            
            ancho_contenedor = max(w, h) + 40 + padding_horizontal*2  # Margen más amplio con padding
            alto_contenedor = max(w, h) + 40 + padding_vertical*2  # Margen más amplio con padding
            txt_img = Image.new("RGBA", (ancho_contenedor, alto_contenedor), (255, 255, 255, 0))
            txt_draw = ImageDraw.Draw(txt_img)
            
            # Centrar el texto en su contenedor utilizando textbbox para precisión
            bbox = font_num.getbbox(texto)
            w_actual, h_actual = bbox[2] - bbox[0], bbox[3] - bbox[1]
            
            # Posicionar texto exactamente en el centro del contenedor
            x_text = (ancho_contenedor - w_actual) / 2
            y_text = (alto_contenedor - h_actual) / 2 - bbox[1]
            
                # print(f"[DEBUG CENTRADO ROTADO] '{texto}', Contenedor: {ancho_contenedor}x{alto_contenedor}, Texto: {w_actual}x{h_actual}")
                # print(f"[DEBUG CENTRADO ROTADO] Posición en contenedor: ({x_text}, {y_text})")
            
            txt_draw.text((x_text, y_text), texto, font=font_num, fill=color)
            
            # Rotar 90 grados
            txt_img = txt_img.rotate(-90, expand=1)
            
            # Centrar el texto rotado en su posición original
            x_ajustado = x - txt_img.size[0] / 2
            y_ajustado = y - txt_img.size[1] / 2
            
                # print(f"[DEBUG POSICIÓN FINAL] Posición final texto rotado: ({int(x_ajustado)}, {int(y_ajustado)})")
            
            img.paste(txt_img, (int(x_ajustado), int(y_ajustado)), txt_img)
        else:
            # Texto sin rotar - usar método directo para centrado
            # Las coordenadas y que recibimos ya son los centros de las celdas
            bbox = font_num.getbbox(texto)
            length = font_num.getlength(texto)
                # print   (f"[DEBUG] Texto: '{texto}', Ancho: {length}, Alto: {bbox[3] - bbox[1]}")

                # print(f"[DEBUG] bbox: left (X inicial)={bbox[0]}, top (Y inicial)={bbox[1]}, right (X final)={bbox[2]}, bottom (Y final)={bbox[3]}")
            text_width = bbox[2] - bbox[0]
                # print(f"[DEBUG] ancho={text_width}")
            text_height = bbox[3] - bbox[1]
                # print(f"[DEBUG] alto={text_height}")


            # Offset manual para ajustar el centrado vertical
            offset_vertical = 0  # Cambia este valor para probar el rango
                # print(f"[DEBUG] offset_vertical: {offset_vertical}")

            # Ajustar la posición para centrar el texto en las coordenadas proporcionadas
            x_ajustado = x - text_width / 2
                # print(f"[DEBUG] x_ajustado: {x_ajustado}")
            y_ajustado = y - text_height / 2 - offset_vertical - bbox[1]
                # print(f"[DEBUG] y_ajustado: {y_ajustado}")

            # Ahora dibujamos el texto en la posición ajustada
            draw.text((x_ajustado, y_ajustado), texto, font=font_num, fill=color)
    
    # Guardar la imagen con antialiasing en un directorio temporal del sistema
    # Usar tempfile para asegurar permisos correctos y nombres únicos
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
        img_path = temp_file.name
    img.save(img_path)
    
    return img, img_path

def generar_pdf_informe_mejorado(
    nombre_archivo=None,
    grafico_datos=None
):
    """
    Genera un PDF con información de talonarios y un gráfico escalado correctamente.
    Esta función usa generar_grafico_optimizado para crear el gráfico y luego 
    lo inserta en el PDF aplicando el escalado adecuado.
    
    Args:
        nombre_archivo: Nombre del archivo PDF a generar
        grafico_datos: Diccionario con los datos para el gráfico y la información
    """
    if grafico_datos is None:
            # print("Error: No se proporcionaron datos para el gráfico")
        return

    # Valor por defecto centralizado en i18n
    if nombre_archivo is None:
        nombre_archivo = t("informe_talonarios_filename")

    entrada = grafico_datos.get("entrada", {})
    salida = grafico_datos.get("salida", {})
        # print(f"[PDF DEBUG] entrada: {entrada}")
        # print(f"[PDF DEBUG] salida: {salida}")
        # print(f"[PDF DEBUG] Total hojas (tirada_fase1): {salida.get('tirada_fase1', '')}")

    # Crear el canvas del PDF
    c = canvas.Canvas(nombre_archivo, pagesize=A4)
    width, height = A4
    margen = 20 * mm

    # --- Layout manual con y_actual ---
    c.setFont("Helvetica-Bold", 20)
    y_actual = height - margen
    # Centrar el texto en la página
    titulo = t("Informe de Talonarios")
    ancho_texto = c.stringWidth(titulo, "Helvetica-Bold", 20)
    x_centro = (width - ancho_texto) / 2
    c.drawString(x_centro, y_actual, titulo)
    y_actual -= 60  # Espacio después del título (ajustado para tamaño 20)
    c.setFont("Helvetica", 12)
    line_height = 20

    # Calcular tirada para fase 1 (conversión robusta y mínima)
    try:
        talonarios_f1 = int(float(str(entrada.get('talonarios_fase1', entrada.get('cantidad', 0))).strip()))
    except Exception:
        talonarios_f1 = 0

    try:
        hojas_por_tal = int(float(str(entrada.get('hojas_por_tal', 0)).strip()))
    except Exception:
        hojas_por_tal = 0

    tirada_calculada_fase1 = talonarios_f1 * hojas_por_tal

    #print(f"[DEBUG] Tirada calculada fase 1: {tirada_calculada_fase1} (talonarios_fase1={talonarios_f1}, hojas_por_tal={hojas_por_tal})")


    datos1 = [
        t("Cantidad de talonarios: {0}").format(entrada.get('talonarios_fase1','')),
        t("Hojas por talonario: {0}").format(entrada.get('hojas_por_tal','')),
        t("Total hojas: {0}").format(tirada_calculada_fase1),
    ]

    #print(f"[DEBUG] Datos originales: {datos1}")



    # Crear texto para cantidad de talonarios
    talonarios_calculados = entrada.get('talonarios_calculados', entrada.get('cantidad', ''))
    talonarios_fase1 = entrada.get('talonarios_fase1', entrada.get('cantidad', ''))
    texto_cantidad = t("Talonarios calculados: {0}").format(talonarios_calculados)
    if (talonarios_calculados and talonarios_fase1 and 
        str(talonarios_calculados).isdigit() and str(talonarios_fase1).isdigit() and
        int(talonarios_calculados) > int(talonarios_fase1)):
        incremento = int(talonarios_calculados) - int(talonarios_fase1)
        texto_cantidad += t(" (+{0} Talonarios)").format(incremento)

    # Calcular tirada calculada como hojas_calculadas / (horizontal x vertical)
    hojas_calculadas = int(salida.get('tirada_calculada', 0))
    hojas_x_pliego_val = int(entrada.get('hojas_x_pliego', 1)) if str(entrada.get('hojas_x_pliego', '')).isdigit() else 1
    tirada_calculada_final = hojas_calculadas // hojas_x_pliego_val if hojas_x_pliego_val > 0 else ''

    datos2 = [
        t("Datos calculados"),
        t("Horizontal: {0}").format(entrada.get('horizontal','')),
        t("Vertical: {0}").format(entrada.get('vertical','')),
        t("Montando el corte: {0}").format(entrada.get('orientacion','')),
        t("Salen por pliego: {0} hojas").format(hojas_x_pliego_val),
        texto_cantidad,
        t("Hojas calculadas: {0}").format(hojas_calculadas),
        t("Tirada calculada: {0} / {1} = {2} Tiradas").format(hojas_x_pliego_val, hojas_calculadas, tirada_calculada_final),
        t("Comienzo numeración: {0}").format(entrada.get('comienzo','')),
    ]

    # Encabezado bloque 1
    c.setFont("Helvetica-Bold", 16)
    c.drawString(margen, y_actual, t("Datos Originales"))
    y_actual -= line_height
    y_actual -= 8 # margen
    # Bloque 1
    c.setFont("Helvetica", 12)
    for texto in datos1:
        c.drawString(margen, y_actual, texto)
        y_actual -= line_height

    # Separador visual
    c.setFont("Helvetica-Bold", 12)
    c.drawString(margen, y_actual, "--------------------------------------------")
    y_actual -= 40 # margen entre separador y bloque calculado

    # Bloque 2
    margen_entre_calculado_y_datos = 8  # Espaciador después de 'Datos calculados'
    for j, texto in enumerate(datos2):
        if j == 0:
            c.setFont("Helvetica-Bold", 16)
            c.drawString(margen, y_actual, texto)
            y_actual -= line_height + margen_entre_calculado_y_datos
        else:
            c.setFont("Helvetica", 12)
            c.drawString(margen, y_actual, texto)
            y_actual -= line_height

    # Línea separadora justo debajo del último texto
    c.setFont("Helvetica-Bold", 12)
    c.drawString(margen, y_actual, "--------------------------------------------")
    y_actual -= 60  # margen manual solo para el gráfico

    # Generar el gráfico usando la nueva función optimizada
    img, img_path = generar_grafico_optimizado(grafico_datos)

    img_w, img_h = img.size
        # print(f"[DEPURACIÓN] Dimensiones finales del gráfico: {img_w}x{img_h}")

    factor_escala = 0.54 # <-- Cambia este valor a mano según lo que quieras
    grafico_w = img_w * factor_escala
    grafico_h = img_h * factor_escala
        # print(f"[ESCALA MANUAL] factor_escala={factor_escala}, tamaño final=({grafico_w}, {grafico_h})")

    x_grafico = margen
    y_grafico = y_actual - grafico_h
        # print(f"[ESCALA MANUAL] drawImage en ({x_grafico}, {y_grafico}), tamaño=({grafico_w}, {grafico_h})")

    c.drawImage(img_path, x_grafico, y_grafico, width=grafico_w, height=grafico_h)
    
    # Eliminar el archivo temporal de forma segura
    try:
        os.remove(img_path)
    except (OSError, PermissionError):
        # Si no se puede eliminar, no es crítico - el sistema lo limpiará eventualmente
        pass

    c.showPage()
    c.save()
        # print(f"PDF generado: {nombre_archivo}")


