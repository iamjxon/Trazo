import os

# Las pruebas corren sin pantalla (también en GitHub Actions).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
