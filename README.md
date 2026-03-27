# CyberGhost GUI — Interface graphique Linux pour CyberGhost VPN

Interface graphique desktop (Linux / Ubuntu) construite avec CustomTkinter pour piloter le client VPN officiel **CyberGhost** en ligne de commande (`cyberghostvpn`).

> **Ce projet est un wrapper.** Il n'implémente aucun protocole réseau. Il exécute les commandes du CLI officiel CyberGhost en arrière-plan et parse leurs sorties pour mettre à jour l'interface graphique.

---

## Prérequis

| Dépendance | Version minimale | Rôle |
|---|---|---|
| Python | 3.10 | Langage principal |
| `cyberghostvpn` | — | CLI officiel CyberGhost (doit être installé séparément) |
| `customtkinter` | 5.2.0 | Bibliothèque UI |
| `pkexec` (Polkit) | — | Élévation de privilèges (natif Ubuntu) |

### Installer le CLI CyberGhost

Suivre les instructions officielles sur [support.cyberghostvpn.com](https://support.cyberghostvpn.com/hc/en-us/articles/213808885).

---

## Installation

```bash
# Cloner le dépôt
git clone https://github.com/MithrandirEa/Cyberghost-Linux-GUI.git
cd Cyberghost-Linux-GUI

# Créer et activer un environnement virtuel
python3 -m venv .venv
source .venv/bin/activate

# Installer les dépendances
pip install -r requirements.txt
```

---

## Lancement

```bash
python src/main.py
```

L'interface s'ouvre automatiquement en mode clair ou sombre selon les préférences système. Une popup système (Polkit) demande les droits administrateur lors de la connexion ou de la déconnexion.

---

## Fonctionnalités

- **Statut en temps réel** — Affiche l'état de la connexion (connecté / déconnecté), l'adresse IP publique, le pays et le serveur VPN actifs.
- **Sélection du pays** — Liste déroulante peuplée dynamiquement depuis la commande `cyberghostvpn --country-code`.
- **Connexion / Déconnexion** — Bouton unique dont l'action s'adapte à l'état courant.
- **Thread-safe** — Les appels CLI bloquants s'exécutent dans des threads démons séparés ; l'interface ne se bloque jamais.
- **Thème adaptatif** — Supporte les modes Light et Dark via CustomTkinter.

---

## Architecture

```
src/
├── main.py                  # Point d'entrée
├── backend/
│   ├── cli_wrapper.py       # Couche subprocess pure (sans état, sans thread)
│   └── vpn_controller.py   # Parsing CLI + orchestration des threads
└── ui/
    └── app_window.py        # Fenêtre principale CustomTkinter

tests/
├── conftest.py              # Configuration pytest (chemin src/)
├── test_cli_wrapper.py      # Tests unitaires de la couche CLI (28 tests)
└── test_vpn_controller.py  # Tests fonctionnels du contrôleur (41 tests)
```

### Flux de données

```
AppWindow  →  VpnController  →  cli_wrapper  →  subprocess (cyberghostvpn)
   ↑               |
   └── .after() ←─┘  (callback thread-safe)
```

### Élévation de privilèges

Les commandes `--connect` et `--stop` requièrent les droits root. L'application utilise `pkexec` (Polkit) plutôt que `sudo` afin de déclencher une popup graphique native sans passer par un terminal.

---

## Tests

```bash
# Lancer la suite complète
python -m pytest tests/ -v
```

**69 tests — 0 échec** sur la suite complète.

| Fichier | Tests | Couverture |
|---|---|---|
| `test_cli_wrapper.py` | 28 | `strip_ansi`, `_run`, `get_status`, `get_countries`, `connect`, `disconnect` |
| `test_vpn_controller.py` | 41 | `parse_status`, `parse_countries`, `VpnController` (threads, callbacks, état) |

Les appels au CLI sont entièrement mockés via `unittest.mock.patch` — aucune connexion VPN réelle n'est nécessaire pour faire tourner les tests.

---

## Conventions de code

- **Variables / fonctions / classes** : anglais
- **Commentaires / docstrings** : français
- **Textes UI** : français
- **Style** : PEP 8, limite de 79 caractères par ligne
- **Typage** : Type hints systématiques (`def get_status() -> dict[str, Any]:`)

---

## Licence

Ce projet est distribué sous licence MIT. Voir le fichier `LICENSE` pour plus de détails.

---

> CyberGhost est une marque déposée de Kape Technologies. Ce projet n'est pas affilié à CyberGhost ni à Kape Technologies.
