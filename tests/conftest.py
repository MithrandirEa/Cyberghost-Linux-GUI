"""conftest.py — Configuration pytest pour le projet CyberGhost-GUI."""
import sys
from pathlib import Path

# Ajoute src/ au PYTHONPATH pour rendre les modules backend et ui importables
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
