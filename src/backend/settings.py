"""
settings.py — Gestion des préférences persistantes de CyberGhost-GUI.

Stocke les paramètres dans ~/.config/cyberghost-gui/settings.ini
(ou $XDG_CONFIG_HOME/cyberghost-gui/settings.ini).
"""

import configparser
import logging
import os
import pwd
from pathlib import Path

_logger = logging.getLogger(__name__)

_SECTION = "General"
_KEY_CONFIG_DIR = "cyberghost_config_dir"


def _get_real_user_home() -> str:
    """
    Retourne le répertoire home de l'utilisateur réel.

    Quand l'application est lancée avec des privilèges élevés (sudo ou pkexec),
    $HOME pointe vers /root au lieu du home de l'utilisateur réel.
    Cette fonction consulte SUDO_USER (défini par sudo) et PKEXEC_UID
    (défini par pkexec) pour retrouver le home correct, avant de
    retourner $HOME comme valeur de repli.
    """
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user:
        try:
            home = pwd.getpwnam(sudo_user).pw_dir
            _logger.debug("HOME déduit via SUDO_USER=%r → %r", sudo_user, home)
            return home
        except KeyError:
            _logger.debug("SUDO_USER=%r non trouvé dans /etc/passwd", sudo_user)

    pkexec_uid_str = os.environ.get("PKEXEC_UID")
    if pkexec_uid_str:
        try:
            home = pwd.getpwuid(int(pkexec_uid_str)).pw_dir
            _logger.debug(
                "HOME déduit via PKEXEC_UID=%r → %r", pkexec_uid_str, home
            )
            return home
        except (KeyError, ValueError):
            _logger.debug(
                "PKEXEC_UID=%r invalide ou absent du système", pkexec_uid_str
            )

    home = str(Path.home())
    _logger.debug("HOME via Path.home() (fallback) → %r", home)
    return home


def _settings_file() -> Path:
    """Retourne le chemin vers le fichier de paramètres de l'application."""
    xdg_config = os.environ.get("XDG_CONFIG_HOME", "")
    if xdg_config:
        base = Path(xdg_config)
    else:
        home = _get_real_user_home()
        base = Path(home) / ".config"
    path = base / "cyberghost-gui" / "settings.ini"
    _logger.debug(
        "Fichier de paramètres : %r (existe=%s)", str(path), path.exists()
    )
    return path


def _default_cyberghost_config_dir() -> str:
    """Retourne le répertoire de configuration CyberGhost par défaut : $HOME/.cyberghost."""
    return str(Path(_get_real_user_home()) / ".cyberghost")


def get_cyberghost_config_dir() -> str:
    """
    Retourne le chemin du répertoire de configuration CyberGhost.

    Lit la valeur depuis le fichier de paramètres si disponible,
    sinon retourne la valeur par défaut ($HOME/.cyberghost).
    """
    cfg = configparser.ConfigParser()
    settings_path = _settings_file()
    cfg.read(str(settings_path), encoding="utf-8")
    result = cfg.get(_SECTION, _KEY_CONFIG_DIR, fallback=_default_cyberghost_config_dir())
    _logger.debug("Répertoire CyberGhost retourné : %r", result)
    return result


def set_cyberghost_config_dir(path: str) -> None:
    """
    Définit le chemin du répertoire de configuration CyberGhost et le sauvegarde.

    Crée le répertoire de paramètres s'il n'existe pas.
    """
    settings_path = _settings_file()
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    cfg = configparser.ConfigParser()
    cfg.read(str(settings_path), encoding="utf-8")
    if _SECTION not in cfg:
        cfg[_SECTION] = {}
    cfg[_SECTION][_KEY_CONFIG_DIR] = path
    with open(str(settings_path), "w", encoding="utf-8") as f:
        cfg.write(f)
