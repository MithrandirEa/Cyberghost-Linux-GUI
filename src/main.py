"""
main.py — Point d'entrée de CyberGhost-GUI.
Lance l'interface graphique en initialisant le thème
CustomTkinter et le contrôleur VPN.
Usage : python3 src/main.py
"""

import logging
import sys

try:
    import customtkinter as ctk
except ModuleNotFoundError:
    print(
        "Erreur : le module 'customtkinter' est introuvable.\n"
        "Veuillez installer les dépendances avec :\n"
        "    pip3 install -r requirements.txt",
        file=sys.stderr,
    )
    sys.exit(1)

from backend.vpn_controller import VpnController
from ui.app_window import AppWindow


def main() -> None:
    """Initialise et lance l'application CyberGhost-GUI."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    # Thème adaptatif au système (Light/Dark) avec palette de couleurs bleue
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")

    controller = VpnController()
    app = AppWindow(controller)
    app.mainloop()


if __name__ == "__main__":
    main()
