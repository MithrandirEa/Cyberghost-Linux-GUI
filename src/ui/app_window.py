"""
app_window.py — Fenêtre principale de CyberGhost-GUI (CustomTkinter).
Ce module ne contient aucun appel subprocess ni logique métier.
Il délègue toutes les opérations VPN au VpnController
via des callbacks thread-safe.
"""

import os
import re
from tkinter import filedialog
from typing import Any, Callable

import customtkinter as ctk

from backend.settings import get_cyberghost_config_dir, set_cyberghost_config_dir
from backend.vpn_controller import VpnController

# --- Constantes de texte (UI en Français) ---
_TXT_CONNECTED = "● Connecté"
_TXT_DISCONNECTED = "● Déconnecté"
_TXT_BTN_CONNECT = "Se connecter"
_TXT_BTN_DISCONNECT = "Se déconnecter"
_TXT_BTN_CONNECTING = "Connexion en cours…"
_TXT_BTN_DISCONNECTING = "Déconnexion en cours…"
_TXT_IP_PREFIX = "IP : "
_TXT_SERVER_PREFIX = "Serveur : "
_TXT_LOADING = "Chargement des pays…"
_TXT_NO_COUNTRIES = "Aucun pays disponible"
_TXT_INVALID_COUNTRY = "Veuillez sélectionner un pays valide."
_TXT_SETTINGS_BTN = "⚙ Paramètres"
_TXT_SETTINGS_TITLE = "Paramètres"
_TXT_SETTINGS_DIR_LABEL = "Répertoire de configuration CyberGhost :"
_TXT_SETTINGS_BROWSE = "Parcourir…"
_TXT_SETTINGS_SAVE = "Enregistrer"
_TXT_SETTINGS_CANCEL = "Annuler"
_TXT_SETTINGS_SAVED = "Paramètres enregistrés."

# --- Couleurs sémantiques ---
_COLOR_CONNECTED = "#2fa572"
_COLOR_DISCONNECTED = "#e05c5c"
_COLOR_BTN_DISCONNECT = ("#c0392b", "#a93226")  # (fg, hover)

# Regex pour extraire le code pays depuis "Nom du pays (XX)"
_RE_COUNTRY_CODE = re.compile(r"\(([A-Z]{2})\)$")


class AppWindow(ctk.CTk):
    """
    Fenêtre principale de CyberGhost-GUI.
    Construit l'interface, orchestre les interactions avec le VpnController,
    et garantit que toutes les mises à jour UI sont effectuées
    dans le thread principal.
    """

    def __init__(self, controller: VpnController) -> None:
        super().__init__()
        self._controller = controller
        self._is_connected: bool = False
        self._countries: list[tuple[str, str]] = []
        # Couleurs par défaut du bouton (thème actif),
        # stockées après construction de l'UI
        self._btn_default_fg: Any = None
        self._btn_default_hover: Any = None
        # Identifiant du prochain appel de polling (pour annulation propre)
        self._poll_id: str | None = None

        self.title("CyberGhost GUI")
        self.geometry("440x410")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()

        # Sauvegarde des couleurs du bouton pour pouvoir les restaurer
        self._btn_default_fg = self._action_button.cget("fg_color")
        self._btn_default_hover = self._action_button.cget("hover_color")

        # Chargement initial des données (non bloquants)
        self._load_countries()
        self._refresh_status()
        self._schedule_refresh()

    # -------------------------------------------------------------------------
    # Construction de l'UI
    # -------------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Construit et positionne tous les widgets de la fenêtre."""
        self.grid_columnconfigure(0, weight=1)

        # --- Cadre d'en-tête : statut + IP ---
        header = ctk.CTkFrame(self, corner_radius=12)
        header.grid(row=0, column=0, padx=20, pady=(20, 12), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        self._status_label = ctk.CTkLabel(
            header,
            text=_TXT_DISCONNECTED,
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=_COLOR_DISCONNECTED,
        )
        self._status_label.grid(row=0, column=0, padx=20, pady=(14, 2))

        self._ip_label = ctk.CTkLabel(
            header,
            text=f"{_TXT_IP_PREFIX}N/A",
            font=ctk.CTkFont(size=13),
        )
        self._ip_label.grid(row=1, column=0, padx=20, pady=(0, 2))

        self._server_label = ctk.CTkLabel(
            header,
            text="",
            font=ctk.CTkFont(size=12),
        )
        self._server_label.grid(row=2, column=0, padx=20, pady=(0, 14))

        # --- Sélection du pays ---
        ctk.CTkLabel(
            self,
            text="Pays de connexion :",
            font=ctk.CTkFont(size=13),
            anchor="w",
        ).grid(row=1, column=0, padx=22, pady=(4, 0), sticky="w")

        self._country_combo = ctk.CTkComboBox(
            self,
            values=[_TXT_LOADING],
            state="disabled",
            width=400,
        )
        self._country_combo.set(_TXT_LOADING)
        self._country_combo.grid(row=2, column=0, padx=20, pady=(4, 12))

        # --- Bouton d'action principal ---
        self._action_button = ctk.CTkButton(
            self,
            text=_TXT_BTN_CONNECT,
            command=self._on_button_click,
            font=ctk.CTkFont(size=14, weight="bold"),
            height=44,
            corner_radius=10,
        )
        self._action_button.grid(
            row=3, column=0, padx=20, pady=(0, 8), sticky="ew"
        )

        # --- Zone de message d'erreur ---
        self._error_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=_COLOR_DISCONNECTED,
            wraplength=400,
        )
        self._error_label.grid(row=4, column=0, padx=20, pady=(0, 6))

        # --- Bouton de paramètres ---
        self._settings_button = ctk.CTkButton(
            self,
            text=_TXT_SETTINGS_BTN,
            command=self._open_settings,
            font=ctk.CTkFont(size=11),
            height=28,
            corner_radius=8,
            fg_color="transparent",
            border_width=1,
        )
        self._settings_button.grid(row=5, column=0, padx=20, pady=(0, 14))

    # -------------------------------------------------------------------------
    # Chargement des données (déclenche des threads via le contrôleur)
    # -------------------------------------------------------------------------

    def _load_countries(self) -> None:
        """Lance le chargement de la liste des pays en arrière-plan."""

        def _callback(countries: list[tuple[str, str]]) -> None:
            # Retour dans le thread principal via .after()
            self.after(0, self._on_countries_loaded, countries)

        self._controller.load_countries(_callback)

    def _refresh_status(self) -> None:
        """Lance un rafraîchissement du statut VPN en arrière-plan."""

        def _callback(status: dict[str, Any]) -> None:
            self.after(0, self._update_ui, status)

        self._controller.refresh_status(_callback)

    def _schedule_refresh(self) -> None:
        """
        Planifie un rafraîchissement automatique du statut toutes les 30 s.
        Permet de détecter une déconnexion inattendue sans action utilisateur.
        """
        self._poll_id = self.after(30_000, self._poll)

    def _poll(self) -> None:
        """Callback du polling périodique : rafraîchit le statut puis replanifie."""
        self._refresh_status()
        self._schedule_refresh()

    def _on_close(self) -> None:
        """Annule le polling en cours et ferme la fenêtre proprement."""
        if self._poll_id is not None:
            self.after_cancel(self._poll_id)
            self._poll_id = None
        self.destroy()

    # -------------------------------------------------------------------------
    # Callbacks thread-safe (appelés uniquement depuis le thread principal)
    # -------------------------------------------------------------------------

    def _on_countries_loaded(self, countries: list[tuple[str, str]]) -> None:
        """Peuple le ComboBox avec la liste des pays reçue du thread."""
        self._countries = countries
        if countries:
            display_values = [f"{name} ({code})" for name, code in countries]
            self._country_combo.configure(
                values=display_values, state="normal"
            )
            self._country_combo.set(display_values[0])
        else:
            self._country_combo.configure(
                values=[_TXT_NO_COUNTRIES], state="disabled"
            )
            self._country_combo.set(_TXT_NO_COUNTRIES)

    def _update_ui(self, status: dict[str, Any]) -> None:
        """
        Met à jour l'ensemble des widgets selon le dictionnaire de statut VPN.
        Doit être appelé exclusivement depuis le thread principal.
        """
        self._is_connected = status.get("connected", False)
        ip = status.get("ip", "N/A")
        error = status.get("error", "")

        # Mise à jour du label de statut et du bouton
        if self._is_connected:
            country = status.get("country", "")
            suffix = f" — {country}" if country and country != "N/A" else ""
            self._status_label.configure(
                text=f"{_TXT_CONNECTED}{suffix}",
                text_color=_COLOR_CONNECTED,
            )
            self._action_button.configure(
                text=_TXT_BTN_DISCONNECT,
                fg_color=_COLOR_BTN_DISCONNECT[0],
                hover_color=_COLOR_BTN_DISCONNECT[1],
            )
        else:
            self._status_label.configure(
                text=_TXT_DISCONNECTED,
                text_color=_COLOR_DISCONNECTED,
            )
            self._action_button.configure(
                text=_TXT_BTN_CONNECT,
                fg_color=self._btn_default_fg,
                hover_color=self._btn_default_hover,
            )

        self._ip_label.configure(text=f"{_TXT_IP_PREFIX}{ip}")
        server = status.get("server", "N/A")
        if self._is_connected and server and server != "N/A":
            self._server_label.configure(
                text=f"{_TXT_SERVER_PREFIX}{server}"
            )
        else:
            self._server_label.configure(text="")
        self._error_label.configure(text=error if error else "")
        self._action_button.configure(state="normal")
        # Réactivation de la combobox si des pays sont disponibles
        if self._countries:
            self._country_combo.configure(state="normal")

    # -------------------------------------------------------------------------
    # Gestionnaires d'événements UI
    # -------------------------------------------------------------------------

    def _on_button_click(self) -> None:
        """
        Gère le clic sur le bouton principal et route
        vers connexion ou déconnexion.
        """
        # Désactivation immédiate pour éviter les doubles clics
        self._action_button.configure(state="disabled")
        self._error_label.configure(text="")

        if self._is_connected:
            self._do_disconnect()
        else:
            self._do_connect()

    def _do_connect(self) -> None:
        """
        Valide la sélection du pays et lance la connexion VPN
        via le contrôleur.
        """
        selected = self._country_combo.get()
        match = _RE_COUNTRY_CODE.search(selected)

        if not match:
            self._error_label.configure(text=_TXT_INVALID_COUNTRY)
            self._action_button.configure(state="normal")
            return

        country_code = match.group(1)
        self._action_button.configure(text=_TXT_BTN_CONNECTING)
        self._country_combo.configure(state="disabled")

        def _callback(status: dict[str, Any]) -> None:
            self.after(0, self._update_ui, status)

        self._controller.connect(country_code, _callback)

    def _do_disconnect(self) -> None:
        """Lance la déconnexion VPN via le contrôleur."""
        self._action_button.configure(text=_TXT_BTN_DISCONNECTING)
        self._country_combo.configure(state="disabled")

        def _callback(status: dict[str, Any]) -> None:
            self.after(0, self._update_ui, status)

        self._controller.disconnect(_callback)

    def _open_settings(self) -> None:
        """Ouvre la fenêtre de paramètres de l'application."""
        _SettingsDialog(self, on_save=self._refresh_status)


# ---------------------------------------------------------------------------
# Fenêtre de paramètres
# ---------------------------------------------------------------------------


class _SettingsDialog(ctk.CTkToplevel):
    """
    Fenêtre modale de paramètres permettant à l'utilisateur de configurer
    le chemin du répertoire de configuration CyberGhost.
    """

    def __init__(
        self,
        parent: ctk.CTk,
        on_save: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_save = on_save
        self.title(_TXT_SETTINGS_TITLE)
        self.geometry("500x220")
        self.resizable(False, False)
        # Fenêtre modale : bloque les interactions avec la fenêtre parente
        self.grab_set()
        self._build()

    def _build(self) -> None:
        """Construit les widgets de la fenêtre de paramètres."""
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self,
            text=_TXT_SETTINGS_DIR_LABEL,
            font=ctk.CTkFont(size=13),
            anchor="w",
        ).grid(row=0, column=0, columnspan=2, padx=20, pady=(20, 4), sticky="w")

        self._path_entry = ctk.CTkEntry(self, width=360)
        self._path_entry.insert(0, get_cyberghost_config_dir())
        self._path_entry.grid(
            row=1, column=0, padx=(20, 4), pady=4, sticky="ew"
        )

        ctk.CTkButton(
            self,
            text=_TXT_SETTINGS_BROWSE,
            width=100,
            command=self._browse,
        ).grid(row=1, column=1, padx=(0, 20), pady=4)

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=2, column=0, columnspan=2, pady=(16, 20))

        ctk.CTkButton(
            btn_frame,
            text=_TXT_SETTINGS_SAVE,
            command=self._save,
        ).grid(row=0, column=0, padx=8)

        ctk.CTkButton(
            btn_frame,
            text=_TXT_SETTINGS_CANCEL,
            command=self.destroy,
            fg_color="gray40",
            hover_color="gray30",
        ).grid(row=0, column=1, padx=8)

        self._warning_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=_COLOR_DISCONNECTED,
            wraplength=460,
        )
        self._warning_label.grid(
            row=3, column=0, columnspan=2, padx=20, pady=(0, 8)
        )

    def _browse(self) -> None:
        """Ouvre un sélecteur de dossier natif."""
        current = self._path_entry.get().strip()
        if not current or not os.path.isdir(current):
            current = get_cyberghost_config_dir()
        path = filedialog.askdirectory(
            title="Sélectionner le répertoire .cyberghost",
            initialdir=current,
            parent=self,
        )
        if path:
            self._path_entry.delete(0, "end")
            self._path_entry.insert(0, path)

    def _save(self) -> None:
        """Enregistre le chemin configuré et déclenche un rafraîchissement du statut."""
        path = self._path_entry.get().strip()
        if not path:
            self._warning_label.configure(
                text="Veuillez saisir un chemin valide."
            )
            return
        if not os.path.isdir(path):
            self._warning_label.configure(
                text=f"Attention : le répertoire « {path} » n'existe pas encore. "
                "Assurez-vous d'exécuter cyberghostvpn --setup au préalable."
            )
            # Continue saving — the directory may be created by --setup later
        set_cyberghost_config_dir(path)
        self.destroy()
        if self._on_save is not None:
            self._on_save()
