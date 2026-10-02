"""
Preferencias para TalNumStack.

Provee funciones ligeras para almacenar/leer preferencias en JSON
en el directorio de configuración de la aplicación (p. ej. %LocalAppData%/TalNumStack).

Funciones públicas:
- get_config_dir()
- load_preferences()
- save_preferences(prefs)
- get_preference(key, default=None)
- save_preference(key, value)
"""
from __future__ import annotations

import json
import os
import platform
from pathlib import Path
from typing import Any, Dict, Optional

APP_NAME = "TalNumStack"
PREFERENCES_FILENAME = "preferences.json"


def get_config_dir() -> Path:
    """Devuelve la ruta al directorio de configuración para TalNumStack y lo crea si no existe."""
    # Prefer platform-specific config locations.
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or Path.home() / "AppData" / "Local"
    else:
        # On macOS use ~/Library/Application Support/<App>
        try:
            if platform.system() == "Darwin":
                base = Path.home() / "Library" / "Application Support"
            else:
                base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
        except Exception:
            base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    config_dir = Path(base) / APP_NAME
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        # Si falla crear el directorio, intentar usar el home como fallback
        config_dir = Path.home() / f".{APP_NAME}"
        config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def _preferences_file_path() -> Path:
    return get_config_dir() / PREFERENCES_FILENAME


def load_preferences() -> Dict[str, Any]:
    """Carga y devuelve el diccionario de preferencias desde el JSON.

    Si no existe el archivo, devuelve un dict vacío.
    """
    p = _preferences_file_path()
    if not p.exists():
        return {}
    try:
        with p.open("r", encoding="utf-8") as fh:
            return json.load(fh) or {}
    except Exception:
        # Si hay corrupción o error, devolver dict vacío sin lanzar
        return {}


def save_preferences(prefs: Dict[str, Any]) -> None:
    """Guarda el diccionario `prefs` en el archivo de preferencias (atómico simple)."""
    p = _preferences_file_path()
    tmp = p.with_suffix(".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(prefs, fh, ensure_ascii=False, indent=2)
        tmp.replace(p)
    except Exception:
        # Intento directo final si falla el replace
        try:
            with p.open("w", encoding="utf-8") as fh:
                json.dump(prefs, fh, ensure_ascii=False, indent=2)
        except Exception:
            # No podemos hacer más aquí; fallaremos silenciosamente para no romper la app
            pass


def get_preference(key: str, default: Optional[Any] = None) -> Any:
    prefs = load_preferences()
    return prefs.get(key, default)


def save_preference(key: str, value: Any) -> None:
    prefs = load_preferences()
    prefs[key] = value
    save_preferences(prefs)
