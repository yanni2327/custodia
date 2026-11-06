# -*- coding: utf-8 -*-
r"""
Lanzador de la interfaz.

    python scripts\custodia_gui.py

Debe ejecutarse desde una consola como administrador.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from custodia.gui.app import main   # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
