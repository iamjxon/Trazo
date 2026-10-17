"""Lanzador (también es el punto de entrada para PyInstaller)."""
import sys

from trazo.main import main

if __name__ == "__main__":
    sys.exit(main())
