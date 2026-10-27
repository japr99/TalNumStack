# TalNumStack - Calculadora de Talonarios

Aplicación multiplataforma para calcular tiradas de impresión para numerar talonarios.

## Características
- Compatible con Windows y MacOS
- Interfaz gráfica intuitiva usando Flet
- Generación de informe PDFs con ReportLab
- Cálculos automáticos de montaje y numeración
- Generacion de copias , ordenacion en Pdf con pypdf

## Requisitos del Sistema

### Dependencias de Python
```bash
pip install -r requirements.txt
```

### Para Desarrollo
- Python 3.8 o superior
- flet
- reportlab
- pillow

### Para Construcción de Ejecutables
- PyInstaller: `pip install pyinstaller`
- O usar flet pack (incluido con flet)

## Construcción de Ejecutables

### Método 1: Script Automático con PyInstaller
```bash
python build_app.py
```

Este script detecta automáticamente tu sistema operativo y usa la configuración apropiada:
- **Windows**: Usa `TalNumStackWin.spec`
- **macOS**: Usa `TalNumStackMac.spec`
- **Linux**: Usa configuración básica de PyInstaller

### Método 2: Script Automático con Flet Pack
```bash
python build_flet.py
```

### Método 3: Manual con PyInstaller

#### Windows
```bash
pyinstaller TalNumStackWin.spec
```

#### macOS
```bash
pyinstaller TalNumStackMac.spec
```

#### Linux
```bash
pyinstaller --onefile --windowed --name TalNumStack --add-data "Arial Unicode.ttf:." app.py
```

### Método 4: Manual con Flet Pack

#### Windows
```bash
flet pack app.py --name TalNumStack --icon TalNumStack.ico --add-data "Arial Unicode.ttf;Arial Unicode.ttf" --product-name TalNumStack --product-version 1.0
```

#### macOS/Linux
```bash
flet pack app.py --name TalNumStack --icon TalNumStack.icns --add-data "Arial Unicode.ttf:Arial Unicode.ttf" --product-name TalNumStack --product-version 1.0
```

## Archivos de Recursos

### Iconos
- **Windows**: `TalNumStack.ico` (opcional)
- **macOS**: `TalNumStack.icns` (opcional)

### Fuentes
- `Arial Unicode.ttf` (requerido para generación de PDFs)

## Características Multiplataforma

### Manejo de Archivos
- Archivos temporales se crean en directorio temporal del sistema
- Rutas de archivos manejadas correctamente en todas las plataformas
- Apertura de archivos y carpetas adaptada por sistema operativo

### Detección de Tema (macOS)
- Detección automática de modo oscuro/claro en macOS
- Adaptación de colores de interfaz según el tema del sistema

### Fuentes
- Búsqueda automática de fuentes en múltiples ubicaciones
- Fallback a fuentes del sistema si Arial Unicode no está disponible
- Compatibilidad con bundles de PyInstaller

## Distribución en macOS

### Creación de DMG
Para crear un DMG listo para distribución:

```bash
# Compilar la aplicación primero
python build_app.py

# Crear DMG interactivo
./scripts_mac/crear_dmg_interactivo.sh
```

El script de DMG:
- Busca automáticamente TalNumStack.app en dist/
- Crea un DMG con icono personalizado
- Establece permisos correctos para todos los archivos
- Incluye el script de firma automáticamente

### Instalación por Usuarios

#### Desde DMG (Recomendado)
1. Descargar y abrir el archivo `.dmg`
2. **Doble clic** en `firmar_app.sh` dentro del DMG
3. Introducir contraseña de administrador cuando se solicite
4. La aplicación se instalará y firmará automáticamente en `/Applications`

#### Instalación Manual
1. Arrastrar `TalNumStack.app` a `/Applications`
2. Ejecutar `firmar_app.sh` desde Terminal o doble clic
3. Introducir contraseña de administrador

### Script de Firma Mejorado

El script `firmar_app.sh` ha sido mejorado con:

#### Características
- ✅ **Detección automática** de dónde se ejecuta (Terminal vs Finder)
- ✅ **Interfaz visual mejorada** con emojis y mensajes claros
- ✅ **Copia automática** desde DMG a /Applications
- ✅ **Limpieza de atributos** de cuarentena y archivos del sistema
- ✅ **Verificación completa** de firma y Gatekeeper
- ✅ **Log detallado** guardado en el Escritorio
- ✅ **Manejo de errores** robusto con mensajes informativos

#### Funcionalidad
1. **Busca TalNumStack.app** en:
   - Directorio del script (DMG)
   - Directorio actual
   - /Applications (si ya está instalada)

2. **Instala la aplicación**:
   - Copia a `/Applications` con permisos de administrador
   - Establece propietario correcto
   - Configura permisos de ejecución

3. **Limpia y prepara**:
   - Elimina archivos `.DS_Store`
   - Limpia atributos extendidos
   - Elimina cuarentena de macOS

4. **Firma y verifica**:
   - Firma con `codesign` (ad-hoc por defecto)
   - Verifica la integridad de la firma
   - Prueba compatibilidad con Gatekeeper

5. **Genera log**:
   - Guarda registro detallado en el Escritorio
   - Incluye información de depuración si hay errores

## Solución de Problemas

### Problemas Comunes en macOS

#### Script se abre como texto en lugar de ejecutarse
**Causa**: El archivo no tiene permisos de ejecución o está marcado como documento de texto.

**Solución**:
```bash
# Dar permisos de ejecución
chmod +x firmar_app.sh

# Si persiste el problema, ejecutar desde Terminal
bash firmar_app.sh
```

#### "No se puede abrir porque es de un desarrollador no identificado"
**Causa**: macOS Gatekeeper bloquea la aplicación.

**Solución automática**: 
- Usar el script `firmar_app.sh` incluido en el DMG
- El script firma la aplicación automáticamente

**Solución manual**:
1. Ir a `Preferencias del Sistema → Seguridad y Privacidad`
2. En la pestaña "General", clic en "Abrir de todas formas"
3. O ejecutar: `sudo spctl --master-disable` (temporalmente)

#### Script pide contraseña repetidamente
**Causa**: Permisos incorrectos o atributos extendidos.

**Solución**: El script automáticamente:
- Limpia atributos de cuarentena
- Establece permisos correctos
- Configura propietario adecuado

#### DMG creado no funciona en otra máquina
**Causa**: Permisos de archivos no establecidos correctamente.

**Solución**: 
- El script `crear_dmg_interactivo.sh` ahora llama automáticamente a `fix_dmg_permissions.sh`
- Esto asegura que todos los archivos tengan permisos correctos

### Problemas Generales

#### Error "read only file system"
- **Causa**: Aplicación empaquetada intenta escribir en directorio de solo lectura
- **Solución**: Ya implementada - usa directorio temporal del sistema

#### Error de fuente faltante
- **Causa**: Arial Unicode.ttf no se encuentra
- **Solución**: Ya implementada - fallback a fuente del sistema

#### Error de dependencias de ReportLab
- **Causa**: Módulos de ReportLab no incluidos en el empaquetado
- **Solución**: Ya implementada - hiddenimports en archivos .spec

### Distribución Windows vs macOS

#### Windows
- Ejecutable único: `dist/TalNumStack.exe`
- Incluye todas las dependencias
- Sin necesidad de scripts adicionales

#### macOS  
- Bundle de aplicación: `dist/TalNumStack.app`
- DMG con script de instalación automática
- Firma automática para evitar problemas de seguridad

#### Linux
- Ejecutable: `dist/TalNumStack`
- AppImage (si se configura)

## Desarrollo

### Ejecutar en modo desarrollo
```bash
python app.py
```

### Estructura del Proyecto
```
TalNumStack/
├── app.py                 # Aplicación principal
├── app_ui_items.py       # Componentes de interfaz
├── informe_talonarios.py # Generación de PDFs
├── grafico.py           # Generación de gráficos
├── requirements.txt     # Dependencias Python
├── TalNumStackMac.spec  # Configuración PyInstaller para macOS
├── TalNumStackWin.spec  # Configuración PyInstaller para Windows
├── build_app.py         # Script de construcción automático
├── build_flet.py        # Script de construcción con flet pack
├── Arial Unicode.ttf    # Fuente requerida
├── TalNumStack.icns     # Icono para macOS
└── TalNumStack.ico      # Icono para Windows
```

## Licencia
GPL v3 - Ver código fuente para detalles completos de la licencia.
