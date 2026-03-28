"""
cli_wrapper.py — Couche d'accès pure au CLI cyberghostvpn.
Toutes les fonctions de ce module sont sans état et sans concurrence.
Chaque fonction exécute une commande shell et retourne un dictionnaire
standardisé.
"""

import logging
import os
import re
import subprocess
from typing import Any

from backend.settings import get_cyberghost_config_dir

_logger = logging.getLogger(__name__)

# Délai maximum (secondes) accordé à chaque commande CLI.
_CMD_TIMEOUT = 15


def strip_ansi(text: str) -> str:
    """Supprime les codes de couleur et d'échappement ANSI d'une chaîne."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _run(cmd: list[str]) -> dict[str, Any]:
    """
    Exécute une commande via subprocess et retourne un résultat standardisé.
    Tous les codes ANSI sont nettoyés depuis stdout et stderr
    avant d'être retournés.

    Retourne un dictionnaire contenant :
        - status (str)   : "ok" ou "error"
        - stdout (str)   : sortie standard nettoyée
        - stderr (str)   : sortie d'erreur nettoyée
        - returncode (int): code de retour du processus
        - message (str)  : message d'erreur lisible (présent
          uniquement si status == "error")
    """
    _logger.debug("Exécution : %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=_CMD_TIMEOUT,
        )
        _logger.debug("returncode=%d", result.returncode)
        return {
            "status": "ok",
            "stdout": strip_ansi(result.stdout),
            "stderr": strip_ansi(result.stderr),
            "returncode": result.returncode,
        }
    except FileNotFoundError:
        msg = (
            f"Commande introuvable : « {cmd[0]} » "
            "n'est pas installé ou absent du PATH."
        )
        _logger.error(msg)
        return {
            "status": "error",
            "stdout": "",
            "stderr": "",
            "returncode": -1,
            "message": msg,
        }
    except subprocess.TimeoutExpired:
        msg = (
            f"Délai dépassé ({_CMD_TIMEOUT}s) pour la commande"
            f" « {cmd[0]} »."
        )
        _logger.error(msg)
        return {
            "status": "error",
            "stdout": "",
            "stderr": "",
            "returncode": -1,
            "message": msg,
        }
    except Exception as exc:
        _logger.error("Erreur inattendue : %s", exc)
        return {
            "status": "error",
            "stdout": "",
            "stderr": str(exc),
            "returncode": -1,
            "message": str(exc),
        }


def _get_home() -> str:
    """Retourne le répertoire HOME de l'utilisateur courant."""
    return os.environ.get("HOME", os.path.expanduser("~"))


def _get_effective_home() -> str:
    """
    Retourne le HOME effectif déduit du répertoire de configuration CyberGhost.

    Permet de passer le bon HOME à pkexec même quand l'application est
    lancée en root mais que la configuration CyberGhost appartient à
    l'utilisateur réel (ex: /home/user/.cyberghost → HOME=/home/user).
    Si le chemin configuré n'a pas de répertoire parent valide,
    retourne le HOME courant comme valeur de repli.
    """
    parent = os.path.dirname(get_cyberghost_config_dir())
    return parent if parent else _get_home()


def check_config() -> dict[str, Any]:
    """
    Vérifie si le fichier de configuration de CyberGhost existe.

    Retourne un dictionnaire standardisé avec status='ok' si le fichier est
    présent, status='error' sinon (avec un message explicite).
    Le chemin vérifié est le répertoire configuré dans les paramètres
    de l'application (par défaut $HOME/.cyberghost/config.ini).
    """
    config_dir = get_cyberghost_config_dir()
    config_path = os.path.join(config_dir, "config.ini")
    if os.path.isfile(config_path):
        return {"status": "ok", "stdout": "", "stderr": "", "returncode": 0}
    msg = (
        f"Le fichier de configuration CyberGhost est introuvable : "
        f"« {config_path} ».\n"
        "Veuillez d'abord vous authentifier avec : cyberghostvpn --setup"
    )
    _logger.warning(msg)
    return {
        "status": "error",
        "stdout": "",
        "stderr": "",
        "returncode": -1,
        "message": msg,
    }


def get_status() -> dict[str, Any]:
    """
    Exécute `cyberghostvpn --status` et retourne le résultat brut.
    Ne nécessite pas les droits root.
    """
    return _run(["cyberghostvpn", "--status"])


def get_countries() -> dict[str, Any]:
    """
    Exécute `cyberghostvpn --country-code` et retourne la liste brute des pays.
    Ne nécessite pas les droits root.
    """
    return _run(["cyberghostvpn", "--country-code"])


def connect(country_code: str) -> dict[str, Any]:
    """
    Lance la connexion VPN via
    `pkexec cyberghostvpn --country-code CODE --connect`.
    Utilise pkexec pour déclencher une boîte de dialogue
    Polkit native (élévation root).
    Lève ValueError si country_code n'est pas un code ISO-3166 valide
    (exactement 2 lettres majuscules).
    """
    if not re.fullmatch(r"[A-Z]{2}", country_code):
        raise ValueError(
            f"Code pays invalide : « {country_code} »."
            " Attendu : 2 lettres majuscules (ex : FR, DE)."
        )
    return _run(
        [
            "pkexec", "env", f"HOME={_get_effective_home()}",
            "cyberghostvpn", "--country-code", country_code, "--connect",
        ]
    )


def disconnect() -> dict[str, Any]:
    """
    Stoppe le VPN via `pkexec cyberghostvpn --stop`.
    Utilise pkexec pour déclencher une boîte de dialogue
    Polkit native (élévation root).
    """
    return _run(["pkexec", "env", f"HOME={_get_effective_home()}", "cyberghostvpn", "--stop"])
