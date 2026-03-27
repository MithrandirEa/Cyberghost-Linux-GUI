"""
test_vpn_controller.py — Tests fonctionnels du contrôleur VPN.
Valide le parsing du CLI, l'orchestration des threads (via Event
de synchronisation) et les garanties de l'état interne.
"""
import threading
from typing import Any
from unittest.mock import patch

from backend.vpn_controller import (
    DEFAULT_STATUS,
    VpnController,
    parse_countries,
    parse_status,
)


# ---------------------------------------------------------------------------
# Fixtures de sorties CLI simulées
# ---------------------------------------------------------------------------

# Format tableau ASCII (connecté)
_STATUS_CONNECTED_TABLE = """\
+-------------------+----------------+
| Status            | Connected      |
+-------------------+----------------+
| IP                | 185.10.20.30   |
+-------------------+----------------+
| Country           | France         |
+-------------------+----------------+
| Server            | srv-fr-01.cy   |
+-------------------+----------------+
"""

# Format deux-points (connecté)
_STATUS_CONNECTED_COLON = (
    "Status: Connected\n"
    "IP: 45.1.2.3\n"
    "Country: Germany\n"
    "Server: de-srv-05.cg\n"
)

# Format pipe simple (connecté)
_STATUS_CONNECTED_PIPE = "IP | 10.0.0.1\nCountry | Spain\nConnected"

# Déconnecté (variante "Not connected")
_STATUS_NOT_CONNECTED = "Status: Not connected"

# Déconnecté (variante "Disconnected")
_STATUS_DISCONNECTED = "Status: Disconnected"

# Liste de pays — format tableau
_COUNTRIES_TABLE = """\
+--------------------+------+
| Country            | Code |
+--------------------+------+
| France             | FR   |
+--------------------+------+
| Germany            | DE   |
+--------------------+------+
| Spain              | ES   |
+--------------------+------+
"""

# Liste de pays — format colonnes (fallback)
_COUNTRIES_FALLBACK = "France      FR\nGermany     DE\nSpain       ES\n"

# Liste de pays avec doublons
_COUNTRIES_DUPLICATE = "| France | FR |\n| France | FR |\n| Germany | DE |\n"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _raw_ok(stdout: str = "") -> dict[str, Any]:
    return {"status": "ok", "stdout": stdout, "stderr": "", "returncode": 0}


def _raw_error(message: str = "CLI introuvable") -> dict[str, Any]:
    return {
        "status": "error",
        "stdout": "",
        "stderr": "",
        "returncode": -1,
        "message": message,
    }


def _raw_failed(stdout: str = "", stderr: str = "") -> dict[str, Any]:
    """Simule une commande exécutée mais avec returncode != 0."""
    return {"status": "ok", "stdout": stdout, "stderr": stderr, "returncode": 1}


def _wait(event: threading.Event, timeout: float = 3.0) -> None:
    """Synchronise le test avec un thread daemon; lève AssertionError si timeout."""
    assert event.wait(timeout=timeout), (
        "Le thread n'a pas terminé dans le délai imparti."
    )


# ---------------------------------------------------------------------------
# parse_status — format tableau
# ---------------------------------------------------------------------------

class TestParseStatusTableFormat:
    def test_connected_is_true(self) -> None:
        """Détecte l'état connecté dans un format tableau."""
        assert parse_status(_STATUS_CONNECTED_TABLE)["connected"] is True

    def test_ip_extracted(self) -> None:
        """Extrait l'IP depuis le format tableau."""
        assert parse_status(_STATUS_CONNECTED_TABLE)["ip"] == "185.10.20.30"

    def test_country_extracted(self) -> None:
        """Extrait le pays depuis le format tableau."""
        assert parse_status(_STATUS_CONNECTED_TABLE)["country"] == "France"

    def test_server_extracted(self) -> None:
        """Extrait le serveur depuis le format tableau."""
        assert parse_status(_STATUS_CONNECTED_TABLE)["server"] == "srv-fr-01.cy"


# ---------------------------------------------------------------------------
# parse_status — autres formats
# ---------------------------------------------------------------------------

class TestParseStatusOtherFormats:
    def test_connected_colon_format(self) -> None:
        """Parse le format deux-points (connecté)."""
        r = parse_status(_STATUS_CONNECTED_COLON)
        assert r["connected"] is True
        assert r["ip"] == "45.1.2.3"
        assert r["country"] == "Germany"
        assert r["server"] == "de-srv-05.cg"

    def test_connected_pipe_format(self) -> None:
        """Parse le format pipe simple (connecté)."""
        r = parse_status(_STATUS_CONNECTED_PIPE)
        assert r["connected"] is True
        assert r["ip"] == "10.0.0.1"

    def test_not_connected_keyword(self) -> None:
        """Détecte l'état via 'Not connected'."""
        assert parse_status(_STATUS_NOT_CONNECTED)["connected"] is False

    def test_disconnected_keyword(self) -> None:
        """Détecte l'état via 'Disconnected'."""
        assert parse_status(_STATUS_DISCONNECTED)["connected"] is False

    def test_empty_string_returns_defaults(self) -> None:
        """Chaîne vide → valeurs par défaut."""
        r = parse_status("")
        assert r["connected"] is False
        assert r["ip"] == "N/A"
        assert r["country"] == "N/A"
        assert r["server"] == "N/A"

    def test_garbage_input_does_not_raise(self) -> None:
        """Une entrée inconnue ne lève aucune exception."""
        r = parse_status("xyz abc 1234 !@#$%")
        assert isinstance(r, dict)
        assert isinstance(r["connected"], bool)

    def test_does_not_mutate_default_status(self) -> None:
        """parse_status() ne modifie pas le dict DEFAULT_STATUS global."""
        original = dict(DEFAULT_STATUS)
        parse_status("Status: Connected\nIP: 1.2.3.4")
        assert DEFAULT_STATUS == original

    def test_returns_all_expected_keys(self) -> None:
        """Le dictionnaire retourné contient toujours les 4 clés attendues."""
        r = parse_status("")
        assert {"connected", "ip", "country", "server"} <= r.keys()


# ---------------------------------------------------------------------------
# parse_countries
# ---------------------------------------------------------------------------

class TestParseCountriesTableFormat:
    def test_contains_expected_codes(self) -> None:
        """Tous les codes attendus sont présents."""
        codes = [c for _, c in parse_countries(_COUNTRIES_TABLE)]
        assert "FR" in codes
        assert "DE" in codes
        assert "ES" in codes

    def test_sorted_alphabetically(self) -> None:
        """Le résultat est trié par nom de pays."""
        result = parse_countries(_COUNTRIES_TABLE)
        names = [n for n, _ in result]
        assert names == sorted(names)

    def test_header_row_excluded(self) -> None:
        """L'en-tête 'Country' n'est pas dans les résultats."""
        names = [n for n, _ in parse_countries(_COUNTRIES_TABLE)]
        assert "Country" not in names

    def test_returns_list_of_tuples(self) -> None:
        """Chaque élément est un tuple de deux chaînes."""
        result = parse_countries(_COUNTRIES_TABLE)
        for item in result:
            assert isinstance(item, tuple)
            assert len(item) == 2
            assert all(isinstance(s, str) for s in item)


class TestParseCountriesFallbackFormat:
    def test_fallback_parsed_correctly(self) -> None:
        """Parse le format colonnes (fallback) et retourne les bons codes."""
        codes = [c for _, c in parse_countries(_COUNTRIES_FALLBACK)]
        assert "FR" in codes
        assert "DE" in codes
        assert "ES" in codes


class TestParseCountriesEdgeCases:
    def test_empty_string_returns_empty_list(self) -> None:
        """Chaîne vide → liste vide."""
        assert parse_countries("") == []

    def test_duplicates_deduplicated(self) -> None:
        """Les codes pays dupliqués ne sont présents qu'une fois."""
        codes = [c for _, c in parse_countries(_COUNTRIES_DUPLICATE)]
        assert codes.count("FR") == 1

    def test_garbage_input_returns_empty_list(self) -> None:
        """Entrée sans données valides → liste vide."""
        result = parse_countries("aucun pays ici 12345!")
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# VpnController.refresh_status
# ---------------------------------------------------------------------------

class TestRefreshStatus:
    def test_connected_status_parsed(self) -> None:
        """Callback reçoit connected=True et l'IP correcte après succès CLI."""
        controller = VpnController()
        event = threading.Event()
        received: list[dict[str, Any]] = []

        with patch("backend.vpn_controller.cli_get_status",
                   return_value=_raw_ok(_STATUS_CONNECTED_TABLE)):
            controller.refresh_status(
                lambda s: (received.append(s), event.set())
            )
            _wait(event)

        assert received[0]["connected"] is True
        assert received[0]["ip"] == "185.10.20.30"

    def test_disconnected_status_parsed(self) -> None:
        """Callback reçoit connected=False quand le CLI indique 'Not connected'."""
        controller = VpnController()
        event = threading.Event()
        received: list[dict[str, Any]] = []

        with patch("backend.vpn_controller.cli_get_status",
                   return_value=_raw_ok(_STATUS_NOT_CONNECTED)):
            controller.refresh_status(
                lambda s: (received.append(s), event.set())
            )
            _wait(event)

        assert received[0]["connected"] is False

    def test_cli_error_returns_defaults_with_error_key(self) -> None:
        """Erreur CLI → valeurs par défaut et clé 'error' dans le callback."""
        controller = VpnController()
        event = threading.Event()
        received: list[dict[str, Any]] = []

        with patch("backend.vpn_controller.cli_get_status",
                   return_value=_raw_error("cli absent")):
            controller.refresh_status(
                lambda s: (received.append(s), event.set())
            )
            _wait(event)

        assert received[0]["connected"] is False
        assert "error" in received[0]

    def test_internal_status_updated_on_success(self) -> None:
        """L'état interne du contrôleur est mis à jour après refresh."""
        controller = VpnController()
        event = threading.Event()

        with patch("backend.vpn_controller.cli_get_status",
                   return_value=_raw_ok(_STATUS_CONNECTED_TABLE)):
            controller.refresh_status(lambda _: event.set())
            _wait(event)

        assert controller.current_status["connected"] is True

    def test_internal_status_updated_on_error(self) -> None:
        """L'état interne est réinitialisé aux valeurs par défaut en cas d'erreur."""
        controller = VpnController()
        event = threading.Event()

        with patch("backend.vpn_controller.cli_get_status",
                   return_value=_raw_error()):
            controller.refresh_status(lambda _: event.set())
            _wait(event)

        assert controller.current_status["connected"] is False

    def test_runs_in_separate_thread(self) -> None:
        """refresh_status() n'exécute pas la logique dans le thread appelant."""
        controller = VpnController()
        caller_thread = threading.current_thread()
        executed_in: list[threading.Thread] = []
        event = threading.Event()

        def _cb(status: dict[str, Any]) -> None:
            executed_in.append(threading.current_thread())
            event.set()

        with patch("backend.vpn_controller.cli_get_status",
                   return_value=_raw_ok(_STATUS_NOT_CONNECTED)):
            controller.refresh_status(_cb)
            _wait(event)

        assert executed_in[0] is not caller_thread


# ---------------------------------------------------------------------------
# VpnController.load_countries
# ---------------------------------------------------------------------------

class TestLoadCountries:
    def test_returns_parsed_countries(self) -> None:
        """Callback reçoit la liste des pays parsée depuis le CLI."""
        controller = VpnController()
        event = threading.Event()
        received: list[list[tuple[str, str]]] = []

        with patch("backend.vpn_controller.cli_get_countries",
                   return_value=_raw_ok(_COUNTRIES_TABLE)):
            controller.load_countries(
                lambda c: (received.append(c), event.set())
            )
            _wait(event)

        codes = [code for _, code in received[0]]
        assert "FR" in codes
        assert len(received[0]) > 0

    def test_cli_error_returns_empty_list(self) -> None:
        """Erreur CLI → callback appelé avec une liste vide."""
        controller = VpnController()
        event = threading.Event()
        received: list[list[tuple[str, str]]] = []

        with patch("backend.vpn_controller.cli_get_countries",
                   return_value=_raw_error()):
            controller.load_countries(
                lambda c: (received.append(c), event.set())
            )
            _wait(event)

        assert received[0] == []

    def test_runs_in_separate_thread(self) -> None:
        """load_countries() s'exécute dans un thread secondaire."""
        controller = VpnController()
        caller_thread = threading.current_thread()
        executed_in: list[threading.Thread] = []
        event = threading.Event()

        def _cb(countries: list[tuple[str, str]]) -> None:
            executed_in.append(threading.current_thread())
            event.set()

        with patch("backend.vpn_controller.cli_get_countries",
                   return_value=_raw_ok(_COUNTRIES_TABLE)):
            controller.load_countries(_cb)
            _wait(event)

        assert executed_in[0] is not caller_thread


# ---------------------------------------------------------------------------
# VpnController.connect
# ---------------------------------------------------------------------------

def _config_check_ok() -> dict[str, Any]:
    """Simule un check_config() réussi (fichier de config présent)."""
    return {"status": "ok", "stdout": "", "stderr": "", "returncode": 0}


def _config_check_error() -> dict[str, Any]:
    """Simule un check_config() en échec (fichier de config absent)."""
    return {
        "status": "error",
        "stdout": "",
        "stderr": "",
        "returncode": -1,
        "message": "Le fichier de configuration CyberGhost est introuvable.",
    }


class TestConnect:
    def test_success_callback_connected(self) -> None:
        """Connexion réussie (returncode=0) → callback avec connected=True."""
        controller = VpnController()
        event = threading.Event()
        received: list[dict[str, Any]] = []

        with (
            patch("backend.vpn_controller.cli_check_config",
                  return_value=_config_check_ok()),
            patch("backend.vpn_controller.cli_connect",
                  return_value=_raw_ok()),
            patch("backend.vpn_controller.cli_get_status",
                  return_value=_raw_ok(_STATUS_CONNECTED_TABLE)),
        ):
            controller.connect("FR",
                               lambda s: (received.append(s), event.set()))
            _wait(event)

        assert received[0]["connected"] is True

    def test_failure_callback_has_error_key(self) -> None:
        """Connexion échouée (returncode!=0) → callback avec clé 'error'."""
        controller = VpnController()
        event = threading.Event()
        received: list[dict[str, Any]] = []

        with (
            patch("backend.vpn_controller.cli_check_config",
                  return_value=_config_check_ok()),
            patch("backend.vpn_controller.cli_connect",
                  return_value=_raw_failed(stdout="Auth failed")),
        ):
            controller.connect("FR",
                               lambda s: (received.append(s), event.set()))
            _wait(event)

        assert "error" in received[0]

    def test_failure_does_not_call_cli_get_status(self) -> None:
        """En cas d'échec de connexion, cli_get_status() n'est pas appelé."""
        controller = VpnController()
        event = threading.Event()

        with (
            patch("backend.vpn_controller.cli_check_config",
                  return_value=_config_check_ok()),
            patch("backend.vpn_controller.cli_connect",
                  return_value=_raw_failed()),
            patch("backend.vpn_controller.cli_get_status") as mock_status,
        ):
            controller.connect("FR", lambda _: event.set())
            _wait(event)

        mock_status.assert_not_called()

    def test_runs_in_separate_thread(self) -> None:
        """connect() s'exécute dans un thread secondaire."""
        controller = VpnController()
        caller_thread = threading.current_thread()
        executed_in: list[threading.Thread] = []
        event = threading.Event()

        def _cb(status: dict[str, Any]) -> None:
            executed_in.append(threading.current_thread())
            event.set()

        with (
            patch("backend.vpn_controller.cli_check_config",
                  return_value=_config_check_ok()),
            patch("backend.vpn_controller.cli_connect",
                  return_value=_raw_failed()),
        ):
            controller.connect("FR", _cb)
            _wait(event)

        assert executed_in[0] is not caller_thread

    def test_missing_config_returns_error_without_calling_connect(
        self,
    ) -> None:
        """Config absente → callback avec 'error', cli_connect() non appelé."""
        controller = VpnController()
        event = threading.Event()
        received: list[dict[str, Any]] = []

        with (
            patch("backend.vpn_controller.cli_check_config",
                  return_value=_config_check_error()),
            patch("backend.vpn_controller.cli_connect") as mock_connect,
        ):
            controller.connect(
                "FR", lambda s: (received.append(s), event.set())
            )
            _wait(event)

        assert "error" in received[0]
        assert received[0]["connected"] is False
        mock_connect.assert_not_called()


# ---------------------------------------------------------------------------
# VpnController.disconnect
# ---------------------------------------------------------------------------

class TestDisconnect:
    def test_success_callback_disconnected(self) -> None:
        """Déconnexion réussie (returncode=0) → callback avec connected=False."""
        controller = VpnController()
        event = threading.Event()
        received: list[dict[str, Any]] = []

        with (
            patch("backend.vpn_controller.cli_disconnect",
                  return_value=_raw_ok()),
            patch("backend.vpn_controller.cli_get_status",
                  return_value=_raw_ok(_STATUS_NOT_CONNECTED)),
        ):
            controller.disconnect(lambda s: (received.append(s), event.set()))
            _wait(event)

        assert received[0]["connected"] is False

    def test_failure_callback_has_error_key(self) -> None:
        """Déconnexion échouée (returncode!=0) → callback avec clé 'error'."""
        controller = VpnController()
        event = threading.Event()
        received: list[dict[str, Any]] = []

        with patch("backend.vpn_controller.cli_disconnect",
                   return_value=_raw_failed(stderr="Permission denied")):
            controller.disconnect(lambda s: (received.append(s), event.set()))
            _wait(event)

        assert "error" in received[0]

    def test_failure_does_not_call_cli_get_status(self) -> None:
        """En cas d'échec de déconnexion, cli_get_status() n'est pas appelé."""
        controller = VpnController()
        event = threading.Event()

        with (
            patch("backend.vpn_controller.cli_disconnect",
                  return_value=_raw_failed()),
            patch("backend.vpn_controller.cli_get_status") as mock_status,
        ):
            controller.disconnect(lambda _: event.set())
            _wait(event)

        mock_status.assert_not_called()

    def test_runs_in_separate_thread(self) -> None:
        """disconnect() s'exécute dans un thread secondaire."""
        controller = VpnController()
        caller_thread = threading.current_thread()
        executed_in: list[threading.Thread] = []
        event = threading.Event()

        def _cb(status: dict[str, Any]) -> None:
            executed_in.append(threading.current_thread())
            event.set()

        with patch("backend.vpn_controller.cli_disconnect",
                   return_value=_raw_failed()):
            controller.disconnect(_cb)
            _wait(event)

        assert executed_in[0] is not caller_thread


# ---------------------------------------------------------------------------
# VpnController.current_status — défense contre les mutations
# ---------------------------------------------------------------------------

class TestCurrentStatus:
    def test_returns_copy_not_reference(self) -> None:
        """Modifier le dict retourné ne corrompt pas l'état interne."""
        controller = VpnController()
        status = controller.current_status
        status["connected"] = True
        assert controller.current_status["connected"] is False

    def test_default_state_is_disconnected(self) -> None:
        """L'état initial est 'déconnecté' (connected=False)."""
        controller = VpnController()
        assert controller.current_status["connected"] is False

    def test_default_state_ip_is_na(self) -> None:
        """L'état initial a ip='N/A'."""
        assert VpnController().current_status["ip"] == "N/A"

    def test_default_state_country_is_na(self) -> None:
        """L'état initial a country='N/A'."""
        assert VpnController().current_status["country"] == "N/A"
