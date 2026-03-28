"""
test_settings.py — Tests unitaires du module settings.
Valide get_cyberghost_config_dir() et set_cyberghost_config_dir()
sans accès réel au système de fichiers de l'utilisateur.
"""

import configparser
from pathlib import Path
from unittest.mock import patch

import backend.settings as _settings
from backend.settings import get_cyberghost_config_dir, set_cyberghost_config_dir


# ---------------------------------------------------------------------------
# get_cyberghost_config_dir — valeur par défaut
# ---------------------------------------------------------------------------

class TestGetCyberghostConfigDirDefault:
    def test_default_uses_home_env(self, tmp_path: Path) -> None:
        """Sans fichier de paramètres, retourne $HOME/.cyberghost."""
        with (
            patch.object(_settings, "_settings_file", return_value=tmp_path / "nonexistent.ini"),
            patch.dict(_settings.os.environ, {"HOME": "/home/testuser"}),
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
            patch.dict(_settings.os.environ, {"HOME": "/home/user"}),
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
