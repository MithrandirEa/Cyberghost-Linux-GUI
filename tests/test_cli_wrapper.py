"""
test_cli_wrapper.py — Tests fonctionnels de la couche CLI wrapper.
Valide le comportement de strip_ansi(), _run() et des fonctions publiques,
entièrement via des mocks (subprocess jamais appelé réellement).
"""
from typing import Any
from unittest.mock import MagicMock, patch

import subprocess

import backend.cli_wrapper as _wrapper
from backend.cli_wrapper import (
    check_config,
    connect,
    disconnect,
    get_countries,
    get_status,
    strip_ansi,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_proc(
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
) -> MagicMock:
    """Fabrique un objet CompletedProcess simulé."""
    m = MagicMock()
    m.stdout = stdout
    m.stderr = stderr
    m.returncode = returncode
    return m


def _ok_result(stdout: str = "") -> dict[str, Any]:
    return {
        "status": "ok",
        "stdout": stdout,
        "stderr": "",
        "returncode": 0,
    }


# ---------------------------------------------------------------------------
# strip_ansi
# ---------------------------------------------------------------------------

class TestStripAnsi:
    def test_removes_basic_color_code(self) -> None:
        """Supprime un code de couleur ANSI simple."""
        assert strip_ansi("\x1b[32mConnected\x1b[0m") == "Connected"

    def test_removes_bold_and_reset(self) -> None:
        """Supprime les codes bold et reset."""
        assert strip_ansi("\x1b[1;33mWarning\x1b[0m") == "Warning"

    def test_multiple_codes_in_sentence(self) -> None:
        """Supprime plusieurs codes dans une même chaîne."""
        raw = "\x1b[32mStatus:\x1b[0m \x1b[1mConnected\x1b[0m"
        assert strip_ansi(raw) == "Status: Connected"

    def test_empty_string(self) -> None:
        """Retourne une chaîne vide inchangée."""
        assert strip_ansi("") == ""

    def test_string_without_codes(self) -> None:
        """Retourne une chaîne sans codes ANSI inchangée."""
        plain = "No ANSI codes here"
        assert strip_ansi(plain) == plain

    def test_only_ansi_code(self) -> None:
        """Retourne une chaîne vide quand le contenu est uniquement ANSI."""
        assert strip_ansi("\x1b[0m") == ""

    def test_preserves_surrounding_whitespace(self) -> None:
        """Les espaces autour du texte sont conservés."""
        assert strip_ansi("  \x1b[32mOK\x1b[0m  ") == "  OK  "


# ---------------------------------------------------------------------------
# _run — comportement interne via mock de subprocess.run
# ---------------------------------------------------------------------------

class TestRun:
    def test_success_returns_ok_status(self) -> None:
        """Retourne status='ok' quand subprocess réussit."""
        with patch("subprocess.run", return_value=_make_proc(stdout="ok")):
            result = _wrapper._run(["cyberghostvpn"])
        assert result["status"] == "ok"
        assert result["returncode"] == 0
        assert result["stdout"] == "ok"

    def test_strips_ansi_from_stdout(self) -> None:
        """Le stdout est nettoyé des codes ANSI."""
        ansi_out = "\x1b[32mConnected\x1b[0m"
        with patch("subprocess.run", return_value=_make_proc(stdout=ansi_out)):
            result = _wrapper._run(["cyberghostvpn"])
        assert result["stdout"] == "Connected"

    def test_strips_ansi_from_stderr(self) -> None:
        """Le stderr est nettoyé des codes ANSI."""
        ansi_err = "\x1b[31mError\x1b[0m"
        with patch("subprocess.run",
                   return_value=_make_proc(stderr=ansi_err, returncode=1)):
            result = _wrapper._run(["cyberghostvpn"])
        assert result["stderr"] == "Error"

    def test_nonzero_returncode_keeps_ok_status(self) -> None:
        """Un code retour non nul ne passe pas status à 'error' (check=False)."""
        with patch("subprocess.run", return_value=_make_proc(returncode=1)):
            result = _wrapper._run(["cyberghostvpn"])
        assert result["status"] == "ok"
        assert result["returncode"] == 1

    def test_uses_capture_output_and_text(self) -> None:
        """subprocess.run est appelé avec capture_output=True et text=True."""
        with patch("subprocess.run", return_value=_make_proc()) as mock_run:
            _wrapper._run(["cyberghostvpn"])
        _, kwargs = mock_run.call_args
        assert kwargs.get("capture_output") is True
        assert kwargs.get("text") is True

    def test_file_not_found_returns_error(self) -> None:
        """Retourne status='error' quand la commande est introuvable."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = _wrapper._run(["commande_inexistante"])
        assert result["status"] == "error"
        assert result["returncode"] == -1
        assert "message" in result
        assert "commande_inexistante" in result["message"]

    def test_file_not_found_stdout_empty(self) -> None:
        """En cas de FileNotFoundError, stdout et stderr sont des chaînes vides."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = _wrapper._run(["inexistant"])
        assert result["stdout"] == ""
        assert result["stderr"] == ""

    def test_generic_exception_returns_error(self) -> None:
        """Retourne status='error' pour toute exception inattendue."""
        with patch("subprocess.run", side_effect=OSError("disk full")):
            result = _wrapper._run(["cyberghostvpn"])
        assert result["status"] == "error"
        assert "disk full" in result["message"]

    def test_check_is_false(self) -> None:
        """subprocess.run est appelé avec check=False."""
        with patch("subprocess.run", return_value=_make_proc()) as mock_run:
            _wrapper._run(["cyberghostvpn"])
        _, kwargs = mock_run.call_args
        assert kwargs.get("check") is False

    def test_timeout_expired_returns_error(self) -> None:
        """Retourne status='error' quand subprocess dépasse le délai imparti."""
        exc = subprocess.TimeoutExpired(cmd="cyberghostvpn", timeout=15)
        with patch("subprocess.run", side_effect=exc):
            result = _wrapper._run(["cyberghostvpn", "--status"])
        assert result["status"] == "error"
        assert result["returncode"] == -1
        assert "Délai" in result["message"]


# ---------------------------------------------------------------------------
# Fonctions publiques : vérification des commandes construites
# ---------------------------------------------------------------------------

class TestGetStatus:
    def test_calls_correct_command(self) -> None:
        """get_status() appelle cyberghostvpn --status."""
        with patch.object(_wrapper, "_run", return_value=_ok_result()) as mock:
            get_status()
        mock.assert_called_once_with(["cyberghostvpn", "--status"])

    def test_returns_run_result(self) -> None:
        """get_status() retourne exactement ce que _run() retourne."""
        expected = _ok_result("some output")
        with patch.object(_wrapper, "_run", return_value=expected):
            result = get_status()
        assert result is expected


class TestGetCountries:
    def test_calls_correct_command(self) -> None:
        """get_countries() appelle cyberghostvpn --country-code."""
        with patch.object(_wrapper, "_run", return_value=_ok_result()) as mock:
            get_countries()
        mock.assert_called_once_with(["cyberghostvpn", "--country-code"])

    def test_returns_run_result(self) -> None:
        """get_countries() retourne exactement ce que _run() retourne."""
        expected = _ok_result("country list")
        with patch.object(_wrapper, "_run", return_value=expected):
            result = get_countries()
        assert result is expected


class TestConnect:
    def test_includes_pkexec(self) -> None:
        """connect() utilise pkexec comme premier argument."""
        with patch.object(_wrapper, "_run", return_value=_ok_result()) as mock:
            connect("FR")
        args = mock.call_args[0][0]
        assert args[0] == "pkexec"

    def test_includes_env_command(self) -> None:
        """connect() utilise 'env' après pkexec pour transmettre HOME."""
        with patch.object(_wrapper, "_run", return_value=_ok_result()) as mock:
            connect("FR")
        args = mock.call_args[0][0]
        assert "env" in args

    def test_includes_home_variable(self) -> None:
        """connect() transmet HOME= comme argument d'env."""
        with patch.object(_wrapper, "_run", return_value=_ok_result()) as mock:
            connect("FR")
        args = mock.call_args[0][0]
        assert any(a.startswith("HOME=") for a in args)

    def test_includes_country_code(self) -> None:
        """connect() transmet le code pays à la commande."""
        with patch.object(_wrapper, "_run", return_value=_ok_result()) as mock:
            connect("DE")
        args = mock.call_args[0][0]
        assert "DE" in args

    def test_includes_connect_flag(self) -> None:
        """connect() inclut le flag --connect."""
        with patch.object(_wrapper, "_run", return_value=_ok_result()) as mock:
            connect("ES")
        args = mock.call_args[0][0]
        assert "--connect" in args

    def test_includes_country_code_flag(self) -> None:
        """connect() inclut le flag --country-code."""
        with patch.object(_wrapper, "_run", return_value=_ok_result()) as mock:
            connect("US")
        args = mock.call_args[0][0]
        assert "--country-code" in args

    def test_different_codes_produce_different_calls(self) -> None:
        """Des codes pays différents produisent des commandes différentes."""
        calls: list[list[str]] = []
        with patch.object(
            _wrapper, "_run",
            side_effect=lambda cmd: (calls.append(cmd), _ok_result())[1],
        ):
            connect("FR")
            connect("DE")
        assert "FR" in calls[0]
        assert "DE" in calls[1]

    def test_invalid_country_code_raises_value_error(self) -> None:
        """connect() lève ValueError si le code pays n'est pas 2 majuscules."""
        import pytest
        with pytest.raises(ValueError, match="Code pays invalide"):
            connect("france")

    def test_lowercase_code_raises_value_error(self) -> None:
        """Un code en minuscules lève ValueError."""
        import pytest
        with pytest.raises(ValueError):
            connect("fr")

    def test_too_long_code_raises_value_error(self) -> None:
        """Un code de plus de 2 lettres lève ValueError."""
        import pytest
        with pytest.raises(ValueError):
            connect("FRA")


class TestDisconnect:
    def test_includes_pkexec(self) -> None:
        """disconnect() utilise pkexec comme premier argument."""
        with patch.object(_wrapper, "_run", return_value=_ok_result()) as mock:
            disconnect()
        args = mock.call_args[0][0]
        assert args[0] == "pkexec"

    def test_includes_env_command(self) -> None:
        """disconnect() utilise 'env' après pkexec pour transmettre HOME."""
        with patch.object(_wrapper, "_run", return_value=_ok_result()) as mock:
            disconnect()
        args = mock.call_args[0][0]
        assert "env" in args

    def test_includes_home_variable(self) -> None:
        """disconnect() transmet HOME= comme argument d'env."""
        with patch.object(_wrapper, "_run", return_value=_ok_result()) as mock:
            disconnect()
        args = mock.call_args[0][0]
        assert any(a.startswith("HOME=") for a in args)

    def test_includes_stop_flag(self) -> None:
        """disconnect() inclut le flag --stop."""
        with patch.object(_wrapper, "_run", return_value=_ok_result()) as mock:
            disconnect()
        args = mock.call_args[0][0]
        assert "--stop" in args

    def test_returns_run_result(self) -> None:
        """disconnect() retourne exactement ce que _run() retourne."""
        expected = _ok_result()
        with patch.object(_wrapper, "_run", return_value=expected):
            result = disconnect()
        assert result is expected


# ---------------------------------------------------------------------------
# check_config
# ---------------------------------------------------------------------------

class TestCheckConfig:
    def test_returns_ok_when_config_exists(self, tmp_path: Any) -> None:
        """Retourne status='ok' si le fichier config.ini existe."""
        config_dir = tmp_path / ".cyberghost"
        config_dir.mkdir()
        (config_dir / "config.ini").write_text("[General]")
        with patch(
            "backend.cli_wrapper.get_cyberghost_config_dir",
            return_value=str(config_dir),
        ):
            result = _wrapper.check_config()
        assert result["status"] == "ok"
        assert result["returncode"] == 0

    def test_returns_error_when_config_missing(self, tmp_path: Any) -> None:
        """Retourne status='error' si le fichier config.ini est absent."""
        config_dir = tmp_path / ".cyberghost"
        with patch(
            "backend.cli_wrapper.get_cyberghost_config_dir",
            return_value=str(config_dir),
        ):
            result = _wrapper.check_config()
        assert result["status"] == "error"
        assert result["returncode"] == -1
        assert "message" in result

    def test_error_message_contains_config_path(self, tmp_path: Any) -> None:
        """Le message d'erreur mentionne le chemin du fichier manquant."""
        config_dir = tmp_path / ".cyberghost"
        with patch(
            "backend.cli_wrapper.get_cyberghost_config_dir",
            return_value=str(config_dir),
        ):
            result = _wrapper.check_config()
        assert ".cyberghost" in result["message"]
        assert "config.ini" in result["message"]

    def test_error_message_contains_setup_hint(self, tmp_path: Any) -> None:
        """Le message d'erreur inclut une indication pour lancer --setup."""
        config_dir = tmp_path / ".cyberghost"
        with patch(
            "backend.cli_wrapper.get_cyberghost_config_dir",
            return_value=str(config_dir),
        ):
            result = _wrapper.check_config()
        assert "--setup" in result["message"]

    def test_uses_configured_dir(self, tmp_path: Any) -> None:
        """check_config() utilise le répertoire configuré dans les paramètres."""
        custom_dir = tmp_path / "custom_cyberghost"
        custom_dir.mkdir()
        (custom_dir / "config.ini").write_text("[General]")
        with patch(
            "backend.cli_wrapper.get_cyberghost_config_dir",
            return_value=str(custom_dir),
        ):
            result = _wrapper.check_config()
        assert result["status"] == "ok"
