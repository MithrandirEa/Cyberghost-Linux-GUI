"""
settings.py — Gestion des préférences persistantes de CyberGhost-GUI.

Stocke les paramètres dans ~/.config/cyberghost-gui/settings.ini
(ou $XDG_CONFIG_HOME/cyberghost-gui/settings.ini).
"""

import configparser
import os
from pathlib import Path

_SECTION = "General"
_KEY_CONFIG_DIR = "cyberghost_config_dir"


def _settings_file() -> Path:
    """Retourne le chemin vers le fichier de paramètres de l'application."""
    xdg_config = os.environ.get("XDG_CONFIG_HOME", "")
    if xdg_config:
        base = Path(xdg_config)
    else:
        home = os.environ.get("HOME", str(Path.home()))
        base = Path(home) / ".config"
    return base / "cyberghost-gui" / "settings.ini"


def _default_cyberghost_config_dir() -> str:
    """Retourne le répertoire de configuration CyberGhost par défaut : $HOME/.cyberghost."""
    home = os.environ.get("HOME", str(Path.home()))
    return str(Path(home) / ".cyberghost")


def get_cyberghost_config_dir() -> str:
    """
    Retourne le chemin du répertoire de configuration CyberGhost.

    Lit la valeur depuis le fichier de paramètres si disponible,
    sinon retourne la valeur par défaut ($HOME/.cyberghost).
    """
    cfg = configparser.ConfigParser()
    cfg.read(str(_settings_file()))
    return cfg.get(_SECTION, _KEY_CONFIG_DIR, fallback=_default_cyberghost_config_dir())


def set_cyberghost_config_dir(path: str) -> None:
    """
    Définit le chemin du répertoire de configuration CyberGhost et le sauvegarde.

    Crée le répertoire de paramètres s'il n'existe pas.
    """
    settings_path = _settings_file()
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    cfg = configparser.ConfigParser()
    cfg.read(str(settings_path))
    if _SECTION not in cfg:
        cfg[_SECTION] = {}
    cfg[_SECTION][_KEY_CONFIG_DIR] = path
    with open(str(settings_path), "w", encoding="utf-8") as f:
        cfg.write(f)
