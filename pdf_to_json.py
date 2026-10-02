import fitz  # PyMuPDF
import json
import math
import os


def _dir_a_grados(dir_vec):
    """Convierte vector director [cos, sin] a grados (0-360, sentido horario)."""
    cos, sin = dir_vec
    deg = math.degrees(math.atan2(sin, cos))
    if deg < 0:
        deg += 360
    return round(deg, 1)


def _color_int_a_hex(color_int):
    """Convierte entero de color PyMuPDF a hex #RRGGBB."""
    if color_int is None:
        return None
    r = (color_int >> 16) & 0xFF
    g = (color_int >> 8) & 0xFF
    b = color_int & 0xFF
    return f"#{r:02X}{g:02X}{b:02X}"


def analizar_componentes_pdf(ruta_pdf, ruta_json):
    doc = fitz.open(ruta_pdf)
    resultado = {"documento": ruta_pdf, "paginas": []}

    for num_pag, pagina in enumerate(doc, start=1):
        rect_pag = pagina.rect
        datos_pag = {
            "pagina": num_pag,
            "dimensiones_pt": {"ancho": rect_pag.width, "alto": rect_pag.height},
            "componentes": [],
        }

        # 1. Dibujos (rectángulos, líneas, etc.)
        dibujos = pagina.get_drawings()
        for idx, dibujo in enumerate(dibujos):
            bbox = dibujo["rect"]
            ancho = bbox[2] - bbox[0]
            alto = bbox[3] - bbox[1]
            if ancho <= 0 or alto <= 0:
                continue

            tipo_comp = "contenedor_forma"
            if dibujo["type"] == "re" and dibujo["fill"]:
                tipo_comp = "fondo_contenedor"
            elif dibujo["type"] == "l":
                tipo_comp = "linea_divisoria"

            datos_pag["componentes"].append(
                {
                    "id": f"pag_{num_pag}_g_{idx}",
                    "tipo": tipo_comp,
                    "propiedades": {
                        "grosor_borde": dibujo["width"],
                        "color_borde": dibujo["color"],
                        "color_relleno": dibujo["fill"],
                    },
                    "geometria": {
                        "x": round(bbox[0], 2),
                        "y": round(bbox[1], 2),
                        "w": round(ancho, 2),
                        "h": round(alto, 2),
                    },
                }
            )

        # 2. Texto — a nivel de span (cada fragmento con misma fuente/tamaño/color)
        contenido_texto = pagina.get_text("dict")
        span_idx = 0
        for bloque in contenido_texto["blocks"]:
            if bloque["type"] != 0:
                continue
            for linea in bloque["lines"]:
                for span in linea["spans"]:
                    texto = span["text"].strip()
                    if not texto:
                        continue
                    bbox = span["bbox"]
                    ancho = bbox[2] - bbox[0]
                    alto = bbox[3] - bbox[1]

                    dir_vec = span.get("dir", [1, 0])
                    rot_deg = _dir_a_grados(dir_vec)

                    datos_pag["componentes"].append(
                        {
                            "id": f"pag_{num_pag}_s_{span_idx}",
                            "tipo": "texto",
                            "contenido": texto,
                            "propiedades": {
                                "fuente": span["font"],
                                "tamano_pt": round(span["size"], 1),
                                "color": _color_int_a_hex(span.get("color")),
                                "rotacion": rot_deg,
                            },
                            "geometria": {
                                "x": round(bbox[0], 2),
                                "y": round(bbox[1], 2),
                                "w": round(ancho, 2),
                                "h": round(alto, 2),
                            },
                        }
                    )
                    span_idx += 1

        # Ordenar arriba→abajo, izquierda→derecha
        datos_pag["componentes"].sort(
            key=lambda c: (c["geometria"]["y"], c["geometria"]["x"])
        )
        resultado["paginas"].append(datos_pag)

    with open(ruta_json, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)

    return resultado


if __name__ == "__main__":
    ruta_pdf = input("Ruta del PDF: ").strip().strip("'\"")
    ruta_json = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "PageNumber", "depurar_pdf.json",
    )
    analizar_componentes_pdf(ruta_pdf, ruta_json)
    print(f"Guardado: {ruta_json}")
