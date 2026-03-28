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
import types
from typing import Any

try:
    import pwd
except ImportError:  # pragma: no cover — module POSIX uniquement (non-Windows)
    def _getpwuid_stub(uid: int):  # noqa: D103
        raise KeyError(uid)

    pwd = types.SimpleNamespace(getpwuid=_getpwuid_stub)  # type: ignore[assignment]

from backend.settings import get_cyberghost_config_dir

_logger = logging.getLogger(__name__)

# Délai maximum (secondes) accordé à chaque commande CLI.
_CMD_TIMEOUT = 15

# Homes de root couverts en plus de pwd.getpwuid(0). Certaines distributions
# (ex. : Ubuntu avec un compte root personnalisé) utilisent /home/root.
_FIXED_ROOT_HOMES: tuple[str, ...] = ("/root", "/home/root")


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
        if result.returncode != 0:
            _logger.debug("stdout=%r", strip_ansi(result.stdout)[:500])
            _logger.debug("stderr=%r", strip_ansi(result.stderr)[:500])
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


def _ensure_single_symlink(root_cyberghost: str, config_dir: str) -> None:
    """
    Crée ou corrige le lien symbolique root_cyberghost → config_dir.

    Si le répertoire parent n'existe pas, tente de le créer (le processus
    s'exécute en root via pkexec et dispose des droits nécessaires).
    En cas d'échec de création du parent, abandonne silencieusement.
    Silencieux si les chemins coïncident déjà.
    """
    parent = os.path.dirname(root_cyberghost)
    if not os.path.isdir(parent):
        try:
            os.makedirs(parent, mode=0o755, exist_ok=True)
            _logger.debug("Répertoire créé : %r", parent)
        except OSError as exc:
            _logger.warning("Impossible de créer le répertoire %r : %s", parent, exc)
            return

    if os.path.abspath(config_dir) == os.path.abspath(root_cyberghost):
        return  # Les chemins coïncident déjà, rien à faire

    if os.path.islink(root_cyberghost):
        if os.path.realpath(root_cyberghost) == os.path.realpath(config_dir):
            _logger.debug(
                "Lien symbolique déjà correct : %r → %r", root_cyberghost, config_dir
            )
            return
        try:
            os.unlink(root_cyberghost)
            _logger.debug("Ancien lien supprimé : %r", root_cyberghost)
        except OSError as exc:
            _logger.warning(
                "Impossible de supprimer le lien existant %r : %s", root_cyberghost, exc
            )
            return
    elif os.path.exists(root_cyberghost):
        _logger.warning(
            "%r existe et n'est pas un lien symbolique — lien non créé",
            root_cyberghost,
        )
        return

    try:
        os.symlink(config_dir, root_cyberghost)
        _logger.debug("Lien symbolique créé : %r → %r", root_cyberghost, config_dir)
    except OSError as exc:
        _logger.warning(
            "Impossible de créer le lien symbolique %r : %s", root_cyberghost, exc
        )


def _ensure_root_config_symlink() -> None:
    """
    Crée si nécessaire un lien symbolique .cyberghost dans chaque répertoire
    home candidat pour root.

    cyberghostvpn peut utiliser HOME (fixé par pkexec) ou pwd.getpwuid(0)
    pour localiser sa configuration. Sur certains systèmes le home de root
    dans /etc/passwd est /home/root (et non /root). Cette fonction couvre
    les deux cas en tentant de créer le lien dans tous les homes candidats
    dont le répertoire parent existe réellement.

    Candidats : pwd.getpwuid(0).pw_dir, /root, /home/root.
    """
    config_dir = get_cyberghost_config_dir()

    candidates: set[str] = set()
    try:
        candidates.add(os.path.realpath(pwd.getpwuid(0).pw_dir))
    except KeyError:
        _logger.debug("_ensure_root_config_symlink : uid 0 introuvable dans /etc/passwd")

    # Homes fixes fréquents selon les distributions Linux
    for fixed in _FIXED_ROOT_HOMES:
        if os.path.isdir(fixed):
            candidates.add(os.path.realpath(fixed))

    for root_home in candidates:
        _ensure_single_symlink(os.path.join(root_home, ".cyberghost"), config_dir)


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
    dir_exists = os.path.isdir(config_dir)
    file_exists = os.path.isfile(config_path)
    readable = os.access(config_path, os.R_OK) if file_exists else False
    _logger.debug(
        "check_config — répertoire=%r (isdir=%s) | fichier=%r (isfile=%s, readable=%s)",
        config_dir, dir_exists, config_path, file_exists, readable,
    )
    if file_exists:
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


def run_setup() -> dict[str, Any]:
    """
    Exécute `pkexec cyberghostvpn --setup` pour initialiser la configuration.

    Utilise pkexec pour déclencher une boîte de dialogue Polkit native
    (élévation root). Transmet le HOME effectif afin que CyberGhost écrive
    la configuration dans le bon répertoire utilisateur.
    """
    home = _get_effective_home()
    return _run(["pkexec", "env", f"HOME={home}", "cyberghostvpn", "--setup"])


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
    _ensure_root_config_symlink()
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
    _ensure_root_config_symlink()
    return _run(["pkexec", "env", f"HOME={_get_effective_home()}", "cyberghostvpn", "--stop"])
