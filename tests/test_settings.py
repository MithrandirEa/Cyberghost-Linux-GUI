"""
test_settings.py — Tests unitaires du module settings.
Valide get_cyberghost_config_dir() et set_cyberghost_config_dir()
sans accès réel au système de fichiers de l'utilisateur.
"""

import configparser
import types
from pathlib import Path
from unittest.mock import patch

import backend.settings as _settings
from backend.settings import get_cyberghost_config_dir, set_cyberghost_config_dir


# ---------------------------------------------------------------------------
# _get_real_user_home — détection de l'utilisateur réel sous sudo/pkexec
# ---------------------------------------------------------------------------

class TestGetRealUserHome:
    def test_returns_home_env_by_default(self) -> None:
        """Sans SUDO_USER ni PKEXEC_UID, retourne $HOME."""
        env = {"HOME": "/home/testuser"}
        with patch.dict(_settings.os.environ, env, clear=False):
            _settings.os.environ.pop("SUDO_USER", None)
            _settings.os.environ.pop("PKEXEC_UID", None)
            result = _settings._get_real_user_home()
        assert result == "/home/testuser"

    def test_sudo_user_takes_precedence_over_home(self) -> None:
        """SUDO_USER est utilisé pour trouver le vrai home quand l'app est lancée via sudo."""
        fake_entry = types.SimpleNamespace(pw_dir="/home/sudouser")
        env = {"SUDO_USER": "sudouser", "HOME": "/root"}
        with (
            patch.dict(_settings.os.environ, env, clear=False),
            patch.object(_settings.pwd, "getpwnam", return_value=fake_entry) as mock_pw,
        ):
            _settings.os.environ.pop("PKEXEC_UID", None)
            result = _settings._get_real_user_home()
        mock_pw.assert_called_once_with("sudouser")
        assert result == "/home/sudouser"

    def test_pkexec_uid_used_when_no_sudo_user(self) -> None:
        """PKEXEC_UID est utilisé pour trouver le vrai home quand l'app est lancée via pkexec."""
        fake_entry = types.SimpleNamespace(pw_dir="/home/pkexecuser")
        env = {"PKEXEC_UID": "1001", "HOME": "/root"}
        with (
            patch.dict(_settings.os.environ, env, clear=False),
            patch.object(_settings.pwd, "getpwuid", return_value=fake_entry) as mock_pw,
        ):
            _settings.os.environ.pop("SUDO_USER", None)
            result = _settings._get_real_user_home()
        mock_pw.assert_called_once_with(1001)
        assert result == "/home/pkexecuser"

    def test_falls_back_to_home_if_sudo_user_unknown(self) -> None:
        """Si SUDO_USER n'existe pas dans la base passwd, $HOME est utilisé comme repli."""
        env = {"SUDO_USER": "unknownuser", "HOME": "/root"}
        with (
            patch.dict(_settings.os.environ, env, clear=False),
            patch.object(_settings.pwd, "getpwnam", side_effect=KeyError),
        ):
            _settings.os.environ.pop("PKEXEC_UID", None)
            result = _settings._get_real_user_home()
        assert result == "/root"

    def test_falls_back_to_home_if_pkexec_uid_invalid(self) -> None:
        """Si PKEXEC_UID est invalide, $HOME est utilisé comme repli."""
        env = {"PKEXEC_UID": "not_a_number", "HOME": "/root"}
        with (
            patch.dict(_settings.os.environ, env, clear=False),
        ):
            _settings.os.environ.pop("SUDO_USER", None)
            result = _settings._get_real_user_home()
        assert result == "/root"


# ---------------------------------------------------------------------------
# get_cyberghost_config_dir — valeur par défaut
# ---------------------------------------------------------------------------

class TestGetCyberghostConfigDirDefault:
    def test_default_uses_home_env(self, tmp_path: Path) -> None:
        """Sans fichier de paramètres, retourne $HOME/.cyberghost."""
        with (
            patch.object(_settings, "_settings_file", return_value=tmp_path / "nonexistent.ini"),
            patch.object(_settings, "_get_real_user_home", return_value="/home/testuser"),
        ):
            result = get_cyberghost_config_dir()
        assert result == "/home/testuser/.cyberghost"

    def test_default_ends_with_cyberghost(self, tmp_path: Path) -> None:
        """La valeur par défaut se termine par .cyberghost."""
        with patch.object(_settings, "_settings_file", return_value=tmp_path / "nonexistent.ini"):
            result = get_cyberghost_config_dir()
        assert result.endswith(".cyberghost")


# ---------------------------------------------------------------------------
# get_cyberghost_config_dir — fichier de paramètres existant
# ---------------------------------------------------------------------------

class TestGetCyberghostConfigDirFromFile:
    def test_reads_configured_path(self, tmp_path: Path) -> None:
        """Retourne le chemin stocké dans le fichier de paramètres."""
        settings_file = tmp_path / "settings.ini"
        cfg = configparser.ConfigParser()
        cfg["General"] = {"cyberghost_config_dir": "/custom/path/.cyberghost"}
        with open(str(settings_file), "w") as f:
            cfg.write(f)
        with patch.object(_settings, "_settings_file", return_value=settings_file):
            result = get_cyberghost_config_dir()
        assert result == "/custom/path/.cyberghost"

    def test_falls_back_to_default_when_key_missing(self, tmp_path: Path) -> None:
        """Retourne la valeur par défaut si la clé est absente du fichier."""
        settings_file = tmp_path / "settings.ini"
        cfg = configparser.ConfigParser()
        cfg["General"] = {}
        with open(str(settings_file), "w") as f:
            cfg.write(f)
        with (
            patch.object(_settings, "_settings_file", return_value=settings_file),
            patch.object(_settings, "_get_real_user_home", return_value="/home/user"),
        ):
            result = get_cyberghost_config_dir()
        assert result == "/home/user/.cyberghost"


# ---------------------------------------------------------------------------
# set_cyberghost_config_dir
# ---------------------------------------------------------------------------

class TestSetCyberghostConfigDir:
    def test_creates_settings_file(self, tmp_path: Path) -> None:
        """Crée le fichier de paramètres s'il n'existe pas encore."""
        settings_file = tmp_path / "subdir" / "settings.ini"
        with patch.object(_settings, "_settings_file", return_value=settings_file):
            set_cyberghost_config_dir("/my/.cyberghost")
        assert settings_file.exists()

    def test_saves_configured_path(self, tmp_path: Path) -> None:
        """Le chemin fourni est correctement écrit dans le fichier."""
        settings_file = tmp_path / "settings.ini"
        with patch.object(_settings, "_settings_file", return_value=settings_file):
            set_cyberghost_config_dir("/my/custom/.cyberghost")
        cfg = configparser.ConfigParser()
        cfg.read(str(settings_file))
        assert cfg.get("General", "cyberghost_config_dir") == "/my/custom/.cyberghost"

    def test_overrides_existing_value(self, tmp_path: Path) -> None:
        """Une nouvelle sauvegarde remplace la valeur précédente."""
        settings_file = tmp_path / "settings.ini"
        with patch.object(_settings, "_settings_file", return_value=settings_file):
            set_cyberghost_config_dir("/first/.cyberghost")
            set_cyberghost_config_dir("/second/.cyberghost")
        cfg = configparser.ConfigParser()
        cfg.read(str(settings_file))
        assert cfg.get("General", "cyberghost_config_dir") == "/second/.cyberghost"

    def test_roundtrip(self, tmp_path: Path) -> None:
        """Un chemin enregistré est identique au chemin relu."""
        settings_file = tmp_path / "settings.ini"
        with patch.object(_settings, "_settings_file", return_value=settings_file):
            set_cyberghost_config_dir("/home/clement/.cyberghost")
            result = get_cyberghost_config_dir()
        assert result == "/home/clement/.cyberghost"
