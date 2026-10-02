import fitz
import logging
from lang import t

# Silenciar prints de depuración en este módulo por defecto.
# Para activar, cambiar _PRINT_DEBUG = True durante desarrollo.
_PRINT_DEBUG = False
if not _PRINT_DEBUG:

    def _no_print(*args, **kwargs):
        return None

    print = _no_print

logger = logging.getLogger(__name__)


def leer_cajas_pdf(path_pdf, pagina=0):
    """
    Lee los valores de cropbox, bleedbox y trimbox de la página indicada de un PDF.
    Devuelve un diccionario con los valores (en puntos PDF).
    """
    cajas = {}
    try:
        doc = fitz.open(path_pdf)
        page = doc.load_page(pagina)
        cajas["mediabox"] = tuple(page.rect)
        cajas["cropbox"] = tuple(page.cropbox)
        cajas["bleedbox"] = tuple(page.bleedbox)
        cajas["trimbox"] = tuple(page.trimbox)
        doc.close()
    except Exception as ex:
        cajas["error"] = str(ex)
    return cajas


# TODO leer_cajas_por_pagina
def leer_cajas_por_pagina(path_pdf):
    """
    Lee mediabox/cropbox/bleedbox/trimbox de todas las páginas del PDF.
    Devuelve un diccionario {page_index: {'mediabox':..., 'cropbox':..., 'bleedbox':..., 'trimbox':...}}
    Los valores están en puntos (pt). En caso de error devuelve {'error': msg}.
    """
    resultado = {}
    try:
        doc = fitz.open(path_pdf)
        for i in range(len(doc)):
            page = doc.load_page(i)
            resultado[i] = {
                "mediabox": tuple(page.rect),
                "cropbox": tuple(page.cropbox),
                "bleedbox": tuple(page.bleedbox),
                "trimbox": tuple(page.trimbox),
            }
        doc.close()
    except Exception as ex:
        return {"error": str(ex)}
    # print(resultado)
    return resultado


from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import os

# Import opcional de pypdf
try:
    import pypdf

    PYPDF_DISPONIBLE = True
    # #print("[DEBUG] pypdf importado correctamente")
except ImportError as e:
    pypdf = None
    PYPDF_DISPONIBLE = False
    # #print(f"[DEBUG] Error importando pypdf: {e}")


def contar_paginas_pdf(ruta_pdf: str):
    """
    Devuelve (num_paginas, None) o (0, msg_error) si falla o no está instalado pypdf.
    """
    if not PYPDF_DISPONIBLE:
        return 0, "Dependencia pypdf no instalada. Instalar con: pip install pypdf"
    try:
        with open(ruta_pdf, "rb") as f:
            reader = pypdf.PdfReader(f)
            return len(reader.pages), None
    except Exception as ex:
        return 0, str(ex)


def reorganizar_pdf_segun_ordenamiento(pdf_origen, pdf_destino, ordenamiento_pdf):
    """
    Reorganiza páginas de un PDF según el diccionario de ordenamiento.
    Cada clave del diccionario es la página destino (1-based), y en 'datos' está la lista de páginas origen (1-based).
    """
    if not PYPDF_DISPONIBLE:
        logger.error("Falta pypdf. Ejecuta: pip install pypdf")
        return False
    try:
        with open(pdf_origen, "rb") as f:
            reader = pypdf.PdfReader(f)
            writer = pypdf.PdfWriter()
            for pagina_montaje, datos in ordenamiento_pdf.items():
                # 'datos' es una lista de páginas origen (1-based)
                paginas_origen = datos.get("datos", [])
                for pagina_original in paginas_origen:
                    idx = pagina_original - 1  # pypdf usa 0-based
                    if 0 <= idx < len(reader.pages):
                        writer.add_page(reader.pages[idx])
            with open(pdf_destino, "wb") as out_f:
                writer.write(out_f)
        return True
    except Exception:
        logger.exception("Error en reorganizar_pdf_segun_ordenamiento")
        return False


def crear_pdf_por_copias(pdf_origen, ordenamiento_pdf, directorio_salida):
    """
    Crea PDFs separados por copia según el ordenamiento.
    Retorna dict {copia: PdfWriter}
    """
    if not PYPDF_DISPONIBLE:
        logger.error("Falta pypdf. Ejecuta: pip install pypdf")
        return {}
    try:
        with open(pdf_origen, "rb") as f:
            reader = pypdf.PdfReader(f)
        copias_creadas = {}
        for pagina_montaje, datos in ordenamiento_pdf.items():
            copia = datos.get("numero_copia", 1)
            paginas_origen = datos.get("datos", [])
            if copia not in copias_creadas:
                copias_creadas[copia] = pypdf.PdfWriter()
            for pagina_original in paginas_origen:
                idx = pagina_original - 1
                if 0 <= idx < len(reader.pages):
                    copias_creadas[copia].add_page(reader.pages[idx])
        for copia, writer in copias_creadas.items():
            ruta_copia = os.path.join(directorio_salida, f"copia_{copia}.pdf")
            with open(ruta_copia, "wb") as out_f:
                writer.write(out_f)
        return copias_creadas
    except Exception:
        logger.exception("Error en crear_pdf_por_copias")
        return {}


def reorganizar_pdf_real(
    pdf_origen, pdf_destino, ordenamiento_pdf, callback_progreso=None
):
    """
    Reorganiza las páginas de un PDF real según el diccionario de ordenamiento usando pypdf.
    Además construye:
      - reorganizador_map: {pagina_salida: {'origen': nº_original, 'numero_copia': n, 'doble_cara': 'cara'/'dorso'}}
      - fiery_data: {numero_copia: [paginas_salida,...]}

    Args:
        callback_progreso: función(pagina_actual, total_paginas) para reportar progreso
    """
    if not PYPDF_DISPONIBLE:
        logger.error("Falta pypdf. Ejecuta: pip install pypdf")
        return False
    try:
        if _PRINT_DEBUG:
            print(f"[INFO] Reorganizando PDF real: {pdf_origen} -> {pdf_destino}")
        with open(pdf_origen, "rb") as archivo_origen:
            lector_pdf = pypdf.PdfReader(archivo_origen)
            escritor_pdf = pypdf.PdfWriter()

            if _PRINT_DEBUG:
                print(f"[INFO] PDF original tiene {len(lector_pdf.pages)} páginas")

            # Filtrar metadatos del ordenamiento
            ordenamiento_limpio = {
                k: v for k, v in ordenamiento_pdf.items() if k != "_metadata"
            }

            # Calcular resumen por pliegos/páginas para un mensaje claro:
            num_pliegos = len(ordenamiento_limpio)
            total_paginas = sum(
                len(v.get("datos", [])) for v in ordenamiento_limpio.values()
            )
            paginas_por_pliego = (
                (total_paginas // num_pliegos) if num_pliegos > 0 else 0
            )
            if _PRINT_DEBUG:
                print(
                    f"[INFO] Generando {num_pliegos} pliegos de {paginas_por_pliego} paginas = {total_paginas} paginas (salida real)"
                )

            # Inicializar estructuras para mapear páginas de salida y listas por copia
            reorganizador_map = (
                {}
            )  # {pagina_salida: {'origen': numero_original, 'numero_copia': n, 'doble_cara': ...}}
            listas_fiery = {}  # {numero_copia: [paginas_salida,...]}
            pagina_salida_actual = 0

            # Para cada entrada de ordenamiento (página destino lógica)
            for pagina_destino in sorted(ordenamiento_limpio.keys()):
                datos = ordenamiento_limpio[pagina_destino]
                numeros_pagina = datos.get("datos", [])
                numero_copia = datos.get("numero_copia", 1)
                doble_cara = datos.get("doble_cara", "cara")

                for numero in numeros_pagina:
                    # Añadir la página original al escritor si existe
                    if 1 <= numero <= len(lector_pdf.pages):
                        pagina_original = lector_pdf.pages[numero - 1]
                        escritor_pdf.add_page(pagina_original)
                        pagina_salida_actual += 1

                        # RESTAURADO: print por cada página añadida (debug)
                        if _PRINT_DEBUG:
                            print(
                                f"[DEBUG] Página {pagina_salida_actual}: agregada página original {numero} (copia {numero_copia}, {doble_cara})"
                            )

                        # Actualizar progreso si hay callback
                        if callback_progreso:
                            callback_progreso(pagina_salida_actual, total_paginas)

                        # Registrar en el mapeo de reorganizador
                        reorganizador_map[pagina_salida_actual] = {
                            "origen": numero,
                            "numero_copia": numero_copia,
                            "doble_cara": doble_cara,
                        }

                        # Acumular en listas_fiery por copia (páginas destino reales)
                        listas_fiery.setdefault(numero_copia, []).append(
                            pagina_salida_actual
                        )
                    else:
                        if _PRINT_DEBUG:
                            print(
                                f"[WARNING REORGANIZAR] Número {numero} excede las páginas del PDF original ({len(lector_pdf.pages)})"
                            )

            # Guardar el PDF reorganizado
            with open(pdf_destino, "wb") as archivo_destino:
                escritor_pdf.write(archivo_destino)

            # Ordenar listas_fiery y exponer globalmente para uso posterior (UI / generación Xerox)
            for k in listas_fiery:
                listas_fiery[k].sort()
            global fiery_data
            global reorganizador_map_global
            fiery_data = listas_fiery
            reorganizador_map_global = reorganizador_map

            # Mostrar debug de las listas Fiery (formato esperado)
            if listas_fiery:
                for copia, paginas in sorted(listas_fiery.items()):
                    paginas_str = ",".join(map(str, paginas))

            return True
    except Exception:
        logger.exception("Error al reorganizar PDF real según ordenamiento")
        return False


def crear_pdf_por_copias(
    ordenamiento_pdf,
    directorio_salida,
    pagesize=letter,
    duplicar_por_pliego: bool = False,
    num_copias: int = 1,
):
    """
    Crea PDFs separados por número de copia usando ReportLab.

    Args:
        ordenamiento_pdf (dict): Diccionario de ordenamiento
        directorio_salida (str): Directorio donde guardar los PDFs por copia
        pagesize: Tamaño de página (por defecto letter)

    Returns:
        dict: {numero_copia: ruta_pdf_generado}
    """
    try:
        # Crear directorio si no existe
        os.makedirs(directorio_salida, exist_ok=True)

        # Agrupar páginas por número de copia
        paginas_por_copia = {}
        for pagina, datos in ordenamiento_pdf.items():
            numero_copia = datos["numero_copia"]
            if numero_copia not in paginas_por_copia:
                paginas_por_copia[numero_copia] = []
            paginas_por_copia[numero_copia].append(
                {
                    "pagina": pagina,
                    "datos": datos["datos"],
                    "doble_cara": datos.get("doble_cara", "cara"),
                }
            )

        # Crear PDF por cada copia
        pdfs_generados = {}

        for numero_copia, paginas_datos in paginas_por_copia.items():
            nombre_archivo = f"copia_{numero_copia}.pdf"
            ruta_pdf = os.path.join(directorio_salida, nombre_archivo)

            # Crear PDF para esta copia
            c = canvas.Canvas(ruta_pdf, pagesize=pagesize)

            paginas_creadas = 0

            if duplicar_por_pliego:
                # Interpretar las entradas como pliegos; si es doble cara, agrupar en pares (cara,dorso)
                # paginas_datos es una lista ordenada de entradas [{'pagina', 'datos', 'doble_cara'}, ...]
                i = 0
                n = len(paginas_datos)
                while i < n:
                    # Si hay al menos dos entradas y la combinación parece cara+dorso, tratarlas como un pliego
                    if i + 1 < n and paginas_datos[i].get(
                        "doble_cara"
                    ) != paginas_datos[i + 1].get("doble_cara"):
                        pair = (paginas_datos[i], paginas_datos[i + 1])
                        i += 2
                        for rep in range(max(1, num_copias)):
                            # escribir cara luego dorso
                            for entrada in pair:
                                for numero in entrada["datos"]:
                                    c.showPage()
                                    paginas_creadas += 1
                                    c.drawString(
                                        100,
                                        750,
                                        f"Copia {numero_copia} - Página {paginas_creadas}",
                                    )
                                    c.drawString(100, 730, f"Número: {numero}")
                                    c.drawString(
                                        100, 710, f"Cara: {entrada['doble_cara']}"
                                    )
                                    c.drawString(
                                        100, 690, f"Página montaje: {entrada['pagina']}"
                                    )
                    else:
                        # No hay par claro: tratar la entrada individual como un pliego simple
                        entrada = paginas_datos[i]
                        i += 1
                        for rep in range(max(1, num_copias)):
                            for numero in entrada["datos"]:
                                c.showPage()
                                paginas_creadas += 1
                                c.drawString(
                                    100,
                                    750,
                                    f"Copia {numero_copia} - Página {paginas_creadas}",
                                )
                                c.drawString(100, 730, f"Número: {numero}")
                                c.drawString(100, 710, f"Cara: {entrada['doble_cara']}")
                                c.drawString(
                                    100, 690, f"Página montaje: {entrada['pagina']}"
                                )
            else:
                # Comportamiento por página (histórico)
                for pagina_info in paginas_datos:
                    for numero in pagina_info["datos"]:
                        c.showPage()
                        paginas_creadas += 1
                        c.drawString(
                            100, 750, f"Copia {numero_copia} - Página {paginas_creadas}"
                        )
                        c.drawString(100, 730, f"Número: {numero}")
                        c.drawString(100, 710, f"Cara: {pagina_info['doble_cara']}")
                        c.drawString(
                            100, 690, f"Página montaje: {pagina_info['pagina']}"
                        )

            c.save()
            pdfs_generados[numero_copia] = ruta_pdf
            if _PRINT_DEBUG:
                print(
                    f"[SUCCESS] Copia {numero_copia} guardada en: {ruta_pdf} ({paginas_creadas} páginas)"
                )

        return pdfs_generados

    except Exception:
        logger.exception("Error al crear PDFs por copia")
        return {}


# def crear_pdf_talonarios(ordenamiento_pdf, ruta_pdf_destino, configuracion=None):
#     """
#     Crea un PDF de talonarios usando la estructura de ordenamiento generada.
#
#     Args:
#         ordenamiento_pdf (dict): Diccionario de ordenamiento de páginas
#         ruta_pdf_destino (str): Ruta donde guardar el PDF final
#         configuracion (dict): Configuración adicional (tamaño página, fuentes, etc.)
#
#     Returns:
#         bool: True si fue exitoso, False si hubo error
#     """
#     try:
#         # Configuración por defecto
#         if configuracion is None:
#             configuracion = {
#                 'pagesize': letter,
#                 'font_family': 'Helvetica',
#                 'font_size': 12
#             }
#
#         #print(f"[INFO] Creando PDF de talonarios: {ruta_pdf_destino}")
#
#         # Crear el PDF
#         c = canvas.Canvas(ruta_pdf_destino, pagesize=configuracion['pagesize'])
#
#         total_paginas = 0
#         for pagina_montaje, datos in sorted(ordenamiento_pdf.items()):
#             numeros_pagina = datos['datos']
#             numero_copia = datos['numero_copia']
#             doble_cara = datos.get('doble_cara', 'cara')
#
#             # Crear una página por cada número en los datos
#             for i, numero in enumerate(numeros_pagina):
#                 if total_paginas > 0:  # No showPage() en la primera página
#                     c.showPage()
#
#                 total_paginas += 1
#
#                 # Contenido del talonario
#                 c.setFont(configuracion['font_family'], configuracion['font_size'])
#
#                 # Encabezado
#                 c.drawString(50, 750, f"TALONARIO - Número: {numero}")
#                 c.drawString(50, 730, f"Copia: {numero_copia} | Cara: {doble_cara}")
#                 c.drawString(50, 710, f"Página montaje: {pagina_montaje}")
#
#                 # Líneas de separación
#                 c.line(50, 700, 550, 700)
#
#                 # Aquí puedes añadir el contenido específico del talonario
#                 # Por ejemplo, campos para llenar
#                 y_pos = 680
#                 campos = [
#                     "Fecha: ____________________",
#                     "Cliente: __________________",
#                     "Concepto: _________________",
#                     "Importe: __________________"
#                 ]
#
#                 for campo in campos:
#                     c.drawString(50, y_pos, campo)
#                     y_pos -= 30
#
#                 # Línea de corte (si es doble cara)
#                 if doble_cara == 'reverso':
#                     c.line(50, 400, 550, 400)
#                     c.drawString(50, 380, "--- LÍNEA DE CORTE ---")
#
#         c.save()
#         #print(f"[SUCCESS] PDF de talonarios creado: {ruta_pdf_destino} ({total_paginas} páginas)")
#         return True
#
#     except Exception as e:
#         #print(f"[ERROR] Error al crear PDF de talonarios: {e}")
#         return False
