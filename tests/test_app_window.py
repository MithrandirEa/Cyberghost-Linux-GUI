"""
test_app_window.py — Tests fonctionnels de la fenêtre principale AppWindow.

Les tests nécessitent un serveur d'affichage (Tk crée une vraie fenêtre).
Ils sont ignorés automatiquement en environnement headless sans Xvfb.
En CI, le workflow utilise `xvfb-run` pour fournir un affichage virtuel.
"""

import os
from typing import Any
from unittest.mock import MagicMock

import pytest

# --- Détection de l'environnement sans affichage (CI headless) ---
_NO_DISPLAY = (
    os.name != "nt"  # Pas Windows
    and not os.environ.get("DISPLAY")
    and not os.environ.get("WAYLAND_DISPLAY")
)
pytestmark = pytest.mark.skipif(
    _NO_DISPLAY,
    reason="Pas de serveur d'affichage disponible (Xvfb requis en CI).",
)

from ui.app_window import (  # noqa: E402  (import conditionnel)
    AppWindow,
    _SettingsDialog,
    _TXT_CONNECTED,
    _TXT_DISCONNECTED,
    _TXT_INVALID_COUNTRY,
    _TXT_SERVER_PREFIX,
    _TXT_SETTINGS_TITLE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_status(
    connected: bool = False,
    ip: str = "N/A",
    country: str = "N/A",
    server: str = "N/A",
    error: str = "",
) -> dict[str, Any]:
    """Construit un dictionnaire de statut VPN pour les tests."""
    d: dict[str, Any] = {
        "connected": connected,
        "ip": ip,
        "country": country,
        "server": server,
    }
    if error:
        d["error"] = error
    return d


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def app() -> "AppWindow":
    """
    Crée une AppWindow avec un contrôleur entièrement mocké.
    Les méthodes du contrôleur ne lancent pas de threads réels.
    La fenêtre est proprement détruite après chaque test.
    """
    controller = MagicMock()
    # Les callbacks ne sont jamais déclenchés automatiquement
    controller.load_countries.return_value = None
    controller.refresh_status.return_value = None
    controller.connect.return_value = None
    controller.disconnect.return_value = None

    try:
        window = AppWindow(controller)
    except Exception as exc:
        pytest.skip(f"Impossible de créer la fenêtre Tk : {exc}")
    yield window
    window._on_close()


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

class TestInit:
    def test_window_title(self, app: AppWindow) -> None:
        """La fenêtre a le bon titre."""
        assert app.title() == "CyberGhost GUI"

    def test_initial_state_is_disconnected(self, app: AppWindow) -> None:
        """L'état initial est déconnecté."""
        assert app._is_connected is False

    def test_load_countries_called_on_init(self, app: AppWindow) -> None:
        """Le contrôleur charge les pays au démarrage."""
        app._controller.load_countries.assert_called_once()

    def test_refresh_status_called_on_init(self, app: AppWindow) -> None:
        """Le contrôleur rafraîchit le statut au démarrage."""
        app._controller.refresh_status.assert_called_once()


# ---------------------------------------------------------------------------
# _on_countries_loaded
# ---------------------------------------------------------------------------

class TestOnCountriesLoaded:
    def test_combobox_populated(self, app: AppWindow) -> None:
        """La combobox est remplie avec les pays reçus."""
        countries = [("France", "FR"), ("Germany", "DE")]
        app._on_countries_loaded(countries)
        values = app._country_combo.cget("values")
        assert "France (FR)" in values
        assert "Germany (DE)" in values

    def test_combobox_enabled_when_countries(self, app: AppWindow) -> None:
        """La combobox est activée quand des pays sont disponibles."""
        app._on_countries_loaded([("France", "FR")])
        assert app._country_combo.cget("state") == "normal"

    def test_combobox_disabled_when_no_countries(self, app: AppWindow) -> None:
        """La combobox est désactivée si aucun pays n'est disponible."""
        app._on_countries_loaded([])
        assert app._country_combo.cget("state") == "disabled"

    def test_first_country_selected_by_default(self, app: AppWindow) -> None:
        """Le premier pays est sélectionné par défaut."""
        countries = [("France", "FR"), ("Germany", "DE")]
        app._on_countries_loaded(countries)
        assert app._country_combo.get() == "France (FR)"

    def test_internal_countries_list_stored(self, app: AppWindow) -> None:
        """La liste interne `_countries` est mise à jour."""
        countries = [("France", "FR")]
        app._on_countries_loaded(countries)
        assert app._countries == countries


# ---------------------------------------------------------------------------
# _update_ui
# ---------------------------------------------------------------------------

class TestUpdateUi:
    def test_connected_status_label(self, app: AppWindow) -> None:
        """Le label de statut affiche 'Connecté' quand VPN actif."""
        app._update_ui(_make_status(connected=True, country="France"))
        assert _TXT_CONNECTED in app._status_label.cget("text")

    def test_disconnected_status_label(self, app: AppWindow) -> None:
        """Le label de statut affiche 'Déconnecté' quand VPN inactif."""
        app._update_ui(_make_status(connected=False))
        assert app._status_label.cget("text") == _TXT_DISCONNECTED

    def test_ip_label_updated(self, app: AppWindow) -> None:
        """L'adresse IP est affichée dans le label IP."""
        app._update_ui(_make_status(ip="185.1.2.3"))
        assert "185.1.2.3" in app._ip_label.cget("text")

    def test_server_label_shown_when_connected(self, app: AppWindow) -> None:
        """Le label serveur affiche le nom du serveur quand connecté."""
        app._update_ui(_make_status(connected=True, server="srv-fr-01.cy"))
        assert f"{_TXT_SERVER_PREFIX}srv-fr-01.cy" == app._server_label.cget("text")

    def test_server_label_hidden_when_disconnected(self, app: AppWindow) -> None:
        """Le label serveur est vide quand déconnecté."""
        app._update_ui(_make_status(connected=False, server="srv-fr-01.cy"))
        assert app._server_label.cget("text") == ""

    def test_server_label_hidden_when_server_na(self, app: AppWindow) -> None:
        """Le label serveur est vide quand la valeur est 'N/A'."""
        app._update_ui(_make_status(connected=True, server="N/A"))
        assert app._server_label.cget("text") == ""

    def test_error_displayed(self, app: AppWindow) -> None:
        """Un message d'erreur est affiché dans le label d'erreur."""
        app._update_ui(_make_status(error="Échec de connexion"))
        assert "Échec de connexion" in app._error_label.cget("text")

    def test_error_cleared_on_success(self, app: AppWindow) -> None:
        """L'erreur précédente est effacée lors d'une mise à jour sans erreur."""
        app._update_ui(_make_status(error="Erreur"))
        app._update_ui(_make_status())
        assert app._error_label.cget("text") == ""

    def test_action_button_reenabled(self, app: AppWindow) -> None:
        """Le bouton est réactivé après une mise à jour de statut."""
        app._action_button.configure(state="disabled")
        app._update_ui(_make_status())
        assert app._action_button.cget("state") == "normal"

    def test_combobox_reenabled_when_countries_available(
        self, app: AppWindow
    ) -> None:
        """La combobox est réactivée si des pays sont disponibles."""
        app._on_countries_loaded([("France", "FR")])
        app._country_combo.configure(state="disabled")
        app._update_ui(_make_status())
        assert app._country_combo.cget("state") == "normal"

    def test_is_connected_updated(self, app: AppWindow) -> None:
        """Le flag `_is_connected` est mis à jour correctement."""
        app._update_ui(_make_status(connected=True))
        assert app._is_connected is True
        app._update_ui(_make_status(connected=False))
        assert app._is_connected is False


# ---------------------------------------------------------------------------
# _on_button_click / _do_connect / _do_disconnect
# ---------------------------------------------------------------------------

class TestButtonClick:
    def test_connect_calls_controller(self, app: AppWindow) -> None:
        """Un clic sur 'Se connecter' appelle controller.connect avec le bon code."""
        app._on_countries_loaded([("France", "FR")])
        app._country_combo.set("France (FR)")
        app._is_connected = False
        app._on_button_click()
        app._controller.connect.assert_called_once()
        called_code = app._controller.connect.call_args[0][0]
        assert called_code == "FR"

    def test_disconnect_calls_controller(self, app: AppWindow) -> None:
        """Un clic sur 'Se déconnecter' appelle controller.disconnect."""
        app._is_connected = True
        app._on_button_click()
        app._controller.disconnect.assert_called_once()

    def test_invalid_selection_shows_error(self, app: AppWindow) -> None:
        """Une sélection invalide affiche un message d'erreur, sans appeler connect."""
        app._country_combo.set("sélection invalide")
        app._is_connected = False
        app._on_button_click()
        assert app._error_label.cget("text") == _TXT_INVALID_COUNTRY
        app._controller.connect.assert_not_called()

    def test_combobox_disabled_during_connect(self, app: AppWindow) -> None:
        """La combobox est désactivée immédiatement lors d'une tentative de connexion."""
        app._on_countries_loaded([("France", "FR")])
        app._country_combo.set("France (FR)")
        app._is_connected = False

        combo_states: list[str] = []

        def _spy(code: str, cb: Any) -> None:
            combo_states.append(app._country_combo.cget("state"))

        app._controller.connect.side_effect = _spy
        app._on_button_click()
        assert combo_states and combo_states[0] == "disabled"

    def test_combobox_disabled_during_disconnect(self, app: AppWindow) -> None:
        """La combobox est désactivée immédiatement lors d'une tentative de déconnexion."""
        app._is_connected = True

        combo_states: list[str] = []

        def _spy(cb: Any) -> None:
            combo_states.append(app._country_combo.cget("state"))

        app._controller.disconnect.side_effect = _spy
        app._on_button_click()
        assert combo_states and combo_states[0] == "disabled"


# ---------------------------------------------------------------------------
# _SettingsDialog
# ---------------------------------------------------------------------------

class TestSettingsDialog:
    def test_dialog_opens_without_crash(self, app: AppWindow) -> None:
        """
        L'ouverture de la fenêtre de paramètres ne doit pas lever TclError.
        Régression : grab_set() appelé trop tôt provoquait
        'grab failed: window not viewable'.
        """
        try:
            dialog = _SettingsDialog(app)
            # Traite les événements en attente (y compris le after(10, grab_set))
            app.update()
            dialog.destroy()
        except Exception as exc:
            pytest.fail(f"_SettingsDialog a levé une exception inattendue : {exc}")

    def test_dialog_title(self, app: AppWindow) -> None:
        """La fenêtre de paramètres a le bon titre."""
        dialog = _SettingsDialog(app)
        app.update()
        assert dialog.title() == _TXT_SETTINGS_TITLE
        dialog.destroy()

    def test_grab_set_deferred_via_after(self, app: AppWindow) -> None:
        """
        grab_set() est planifié via after() et non appelé
        directement dans __init__ (évite TclError sur fenêtre non visible).
        La fenêtre doit être visible après que les événements en attente
        sont traités par app.update().
        """
        dialog = _SettingsDialog(app)
        # Avant update(), la fenêtre n'est pas encore rendue
        assert not dialog.winfo_viewable(), (
            "La fenêtre ne doit pas encore être visible avant update()"
        )
        # Après update(), le after(10, grab_set) est exécuté et la fenêtre est visible
        app.update()
        assert dialog.winfo_viewable(), "La fenêtre doit être visible après update()"
        dialog.destroy()
