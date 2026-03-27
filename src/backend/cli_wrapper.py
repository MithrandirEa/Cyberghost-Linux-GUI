"""
cli_wrapper.py — Couche d'accès pure au CLI cyberghostvpn.
Toutes les fonctions de ce module sont sans état et sans concurrence.
Chaque fonction exécute une commande shell et retourne un dictionnaire
standardisé.
"""

import re
import subprocess
from typing import Any


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
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        return {
            "status": "ok",
            "stdout": strip_ansi(result.stdout),
            "stderr": strip_ansi(result.stderr),
            "returncode": result.returncode,
        }
    except FileNotFoundError:
        return {
            "status": "error",
            "stdout": "",
            "stderr": "",
            "returncode": -1,
            "message": (
                f"Commande introuvable : « {cmd[0]} » "
                "n'est pas installé ou absent du PATH."
            ),
        }
    except Exception as exc:
        return {
            "status": "error",
            "stdout": "",
            "stderr": str(exc),
            "returncode": -1,
            "message": str(exc),
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
    """
    return _run(
        ["pkexec", "cyberghostvpn", "--country-code", country_code,
         "--connect"]
    )


def disconnect() -> dict[str, Any]:
    """
    Stoppe le VPN via `pkexec cyberghostvpn --stop`.
    Utilise pkexec pour déclencher une boîte de dialogue
    Polkit native (élévation root).
    """
    return _run(["pkexec", "cyberghostvpn", "--stop"])
