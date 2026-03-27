"""
vpn_controller.py — Logique métier, parsing du CLI et
orchestration des threads.
Ce module fait le lien entre le wrapper CLI (couche basse)
et l'interface graphique (couche haute).
"""

import re
import threading
from typing import Any, Callable

from backend.cli_wrapper import (
    connect as cli_connect,
    disconnect as cli_disconnect,
    get_countries as cli_get_countries,
    get_status as cli_get_status,
)

# Valeur par défaut retournée lorsque le statut ne peut pas être déterminé.
DEFAULT_STATUS: dict[str, Any] = {
    "connected": False,
    "ip": "N/A",
    "country": "N/A",
    "server": "N/A",
}


def parse_status(raw: str) -> dict[str, Any]:
    """
    Parse le texte brut retourné par `cyberghostvpn --status`.

    Retourne un dictionnaire avec les clés :
        - connected (bool) : True si le VPN est actif
        - ip (str)         : adresse IP actuelle
        - country (str)    : pays du serveur connecté
        - server (str)     : nom d'hôte du serveur
    """
    result: dict[str, Any] = dict(DEFAULT_STATUS)

    # Détection de la connexion : présence de "Connected" mais pas
    # "Not connected" ni "Disconnected"
    is_connected = bool(re.search(r"\bConnected\b", raw, re.IGNORECASE))
    is_disconnected = bool(
        re.search(r"\b(Not\s+connected|Disconnected)\b", raw, re.IGNORECASE)
    )
    result["connected"] = is_connected and not is_disconnected

    # Extraction de l'IP (format : "IP  | 185.x.x.x" ou "IP: 185.x.x.x")
    ip_match = re.search(r"\bIP\b\s*[│|:]\s*([\d.]+)", raw, re.IGNORECASE)
    if ip_match:
        result["ip"] = ip_match.group(1).strip()

    # Extraction du pays du serveur
    country_match = re.search(
        r"\bCountry\b\s*[│|:]\s*([^\n│|]+)", raw, re.IGNORECASE
    )
    if country_match:
        result["country"] = country_match.group(1).strip()

    # Extraction du nom du serveur
    server_match = re.search(
        r"\bServer\b\s*[│|:]\s*([^\n│|]+)", raw, re.IGNORECASE
    )
    if server_match:
        result["server"] = server_match.group(1).strip()

    return result


def parse_countries(raw: str) -> list[tuple[str, str]]:
    """
    Parse le texte brut retourné par `cyberghostvpn --country-code`.

    Retourne une liste de tuples (nom_du_pays, code_pays)
    triée alphabétiquement.
    Gère deux formats de sortie possibles :
      - Tableau ASCII  : "| France     | FR |"
      - Colonnes alignées : "France      FR"
    """
    countries: list[tuple[str, str]] = []
    seen_codes: set[str] = set()

    # Format principal : tableau avec séparateurs "|"
    table_pattern = re.compile(
        r"[|]\s*([A-Za-z][A-Za-z\s\-\'\.]{1,40}?)\s*[|]\s*([A-Z]{2})\s*[|]",
        re.MULTILINE,
    )
    for match in table_pattern.finditer(raw):
        name = match.group(1).strip()
        code = match.group(2).strip()
        # Exclure les lignes d'en-tête du tableau
        if name.lower() in {"country", "country name", "name"}:
            continue
        if code not in seen_codes and name:
            seen_codes.add(code)
            countries.append((name, code))

    # Format de repli : colonnes séparées par deux espaces ou plus
    # (ex: "France      FR")
    if not countries:
        fallback_pattern = re.compile(
            r"^([A-Za-z][A-Za-z\s\-\'\.]{1,40}?)\s{2,}([A-Z]{2})\s*$",
            re.MULTILINE,
        )
        for match in fallback_pattern.finditer(raw):
            name = match.group(1).strip()
            code = match.group(2).strip()
            if code not in seen_codes and name:
                seen_codes.add(code)
                countries.append((name, code))

    return sorted(countries, key=lambda x: x[0])


class VpnController:
    """
    Contrôleur métier principal de CyberGhost-GUI.
    Orchestre les appels au CLI dans des threads daemon pour
    ne jamais bloquer l'UI.
    L'état interne (_status) n'est modifié que depuis les callbacks de threads.
    """

    def __init__(self) -> None:
        # Dernier statut connu du VPN
        self._status: dict[str, Any] = dict(DEFAULT_STATUS)

    @property
    def current_status(self) -> dict[str, Any]:
        """Retourne une copie défensive de l'état VPN actuel."""
        return dict(self._status)

    def refresh_status(
        self, callback: Callable[[dict[str, Any]], None]
    ) -> None:
        """
        Rafraîchit le statut VPN en arrière-plan (thread daemon).
        Appelle `callback(status_dict)` depuis le thread une fois terminé.
        L'appelant est responsable de la mise à jour thread-safe
        de l'UI (ex: .after()).
        """

        def _task() -> None:
            raw = cli_get_status()
            if raw["status"] == "error":
                status = dict(DEFAULT_STATUS)
                status["error"] = raw.get("message", raw["stderr"])
            else:
                status = parse_status(raw["stdout"])
            self._status = status
            callback(status)

        threading.Thread(target=_task, daemon=True).start()

    def load_countries(
        self, callback: Callable[[list[tuple[str, str]]], None]
    ) -> None:
        """
        Charge la liste des pays disponibles en arrière-plan (thread daemon).
        Appelle `callback(countries)` depuis le thread une fois terminé.
        En cas d'erreur, le callback est appelé avec une liste vide.
        """

        def _task() -> None:
            raw = cli_get_countries()
            if raw["status"] == "error":
                callback([])
            else:
                callback(parse_countries(raw["stdout"]))

        threading.Thread(target=_task, daemon=True).start()

    def connect(
        self, country_code: str, callback: Callable[[dict[str, Any]], None]
    ) -> None:
        """
        Lance la connexion VPN en arrière-plan (thread daemon).
        En cas de succès, rafraîchit le statut avant d'appeler le callback.
        En cas d'échec, appelle le callback avec l'état actuel
        enrichi d'une clé "error".
        """

        def _task() -> None:
            result = cli_connect(country_code)
            if result["returncode"] != 0:
                status = dict(self._status)
                status["error"] = result.get(
                    "message",
                    result["stderr"] or result["stdout"] or "Erreur inconnue.",
                )
                callback(status)
            else:
                self.refresh_status(callback)

        threading.Thread(target=_task, daemon=True).start()

    def disconnect(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """
        Lance la déconnexion VPN en arrière-plan (thread daemon).
        En cas de succès, rafraîchit le statut avant d'appeler le callback.
        En cas d'échec, appelle le callback avec l'état actuel
        enrichi d'une clé "error".
        """

        def _task() -> None:
            result = cli_disconnect()
            if result["returncode"] != 0:
                status = dict(self._status)
                status["error"] = result.get(
                    "message",
                    result["stderr"] or result["stdout"] or "Erreur inconnue.",
                )
                callback(status)
            else:
                self.refresh_status(callback)

        threading.Thread(target=_task, daemon=True).start()
