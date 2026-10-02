# TalNumStack

TalNumStack es un software de **imposición y paginación para impresión**: genera PDF de
imposición a partir de PDFs de trabajo, permite paginar y montar pliegos con **ajuste
automático o manual**, generar listados de exportación para **Fiery** y llevar el control de
trabajos (cada proyecto se guarda en un fichero `.tns`).

Interfaz gráfica con **Flet 1.0.1** (Flutter embebido) y Python **3.14**.

🌐 **Web y descargas**: <https://japr.my.canva.site/talnumstack-pagenumber-es>

## Requisitos

- Python 3.14
- Un `venv` propio en la raíz del repo

## Dependencias

```bash
pip install -r requirements.txt            # Windows y macOS
```

## Ejecutar

```bash
python app.py
```

En la aplicación se editan los trabajos, se eligen las hojas por pliego, se genera la
imposición y se exporta el resultado a PDF. Las preferencias se guardan en el sistema y los
proyectos en ficheros `.tns` (JSON comprimido con gzip).

## Estructura

| Ruta | Contenido |
| --- | --- |
| `app.py` | Punto de entrada y lógica principal de la interfaz |
| `app_ui_items.py` | Iconos, barra lateral y diálogos de la app |
| `impo_ui.py`, `impo_stack.py` | Motor de imposición y de pliegos |
| `pdf_manipulator.py`, `pdf_ordenado_ui.py` | Manipulación y ordenación de PDF |
| `grafico.py`, `informe_talonarios.py` | Gráficos y генера de informes PDF |
| `fiery_export.py`, `fritz_json_export.py`, `fritz_pdf_generator.py` | Exportación a Fiery |
| `trabajo_manager.py`, `talnum_preferences.py`, `state_cleanup.py` | Proyectos, preferencias y limpieza de estado |
| `utils/` | Utilidades compartidas |
| `assets/` | Iconos de la interfaz |

## Licencia

Copyright © 2026 japr99

AGPL-3.0 — GNU Affero General Public License versión 3. Ver el fichero `LICENSE`.

Este programa es software libre: puedes redistribuirlo y/o modificarlo bajo los términos de la
Licencia Pública General Affero de GNU (AGPL), versión 3. Se distribuye **SIN NINGUNA GARANTÍA**;
consulta la licencia en <https://www.gnu.org/licenses/agpl-3.0.html>.