"""
Sistema de logging de errores para TalNumStack.
Guarda logs en la carpeta de preferencias de la aplicación.
"""

import sys
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
from lang import t


def get_log_path():

    if sys.platform == "darwin":  # macOS
        base_path = Path.home() / "Library" / "Application Support" / "TalNumStack"
    elif sys.platform == "win32":  # Windows: usar AppData
        local_appdata = os.environ.get("APPDATA") or (
            Path.home() / "AppData" / "Roaming"
        )
        base_path = Path(local_appdata) / "TalNumStack"
    else:  # Linux u otros
        base_path = Path.home() / ".config" / "TalNumStack"

    # Crear el directorio si no existe
    base_path.mkdir(parents=True, exist_ok=True)

    return base_path / "talnumstack_errors.log"


def setup_error_logger():
    """Configura el sistema de logging para capturar solo errores"""
    log_path = get_log_path()

    # Crear el directorio padre si no existe
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Configurar el logger raíz para capturar todos los logging.error() del código
    logger = logging.getLogger()
    logger.setLevel(logging.ERROR)

    # Evitar duplicados si ya está configurado
    if logger.handlers:
        # Limpiar handlers existentes para evitar duplicados
        logger.handlers.clear()

    # Crear handler con rotación (2MB máximo, mantener 3 archivos)
    handler = RotatingFileHandler(
        log_path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"  # 2 MB
    )
    handler.setLevel(logging.ERROR)

    # Formato: timestamp | nivel | mensaje
    formatter = logging.Formatter(
        "%(asctime)s | [%(levelname)s] | %(name)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    # Añadir el handler al logger
    logger.addHandler(handler)

    # Escribir línea de inicio para confirmar que el archivo se crea
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[
        :-3
    ]  # Formato con milisegundos
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"TalNumStack iniciado - {timestamp}\n")
            f.write(f"{'='*60}\n")
    except Exception as e:
        pass

    return logger


def install_exception_handler():
    """Instala un manejador global de excepciones no capturadas"""

    def exception_handler(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            # Permitir Ctrl+C sin logging
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        # Loguear la excepción
        logging.error(
            "Excepción no capturada", exc_info=(exc_type, exc_value, exc_traceback)
        )

    def thread_exception_handler(args):
        if issubclass(args.exc_type, KeyboardInterrupt):
            return
        logging.error(
            f"Excepción no capturada en hilo '{args.thread.name}'",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = exception_handler
    try:
        import threading

        threading.excepthook = thread_exception_handler
    except Exception:
        pass


def log_error(message, exception=None):
    """
    Función helper para loguear errores manualmente.

    Args:
        message: Mensaje descriptivo del error
        exception: Excepción opcional para incluir el traceback
    """
    if exception:
        logging.error(f"{message}: {exception}", exc_info=True)
    else:
        logging.error(message)
