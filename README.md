# Trazo

Editor de gráficos vectoriales para Windows, hecho con Python y Qt (PySide6).
Es un programa original, inspirado en el flujo de trabajo de los editores vectoriales de escritorio.
No contiene código ni recursos de CorelDRAW ni de ningún otro producto comercial.

Qt dibuja en C++ y trabaja por eventos: en reposo el consumo de CPU es prácticamente nulo.

## Compilar en GitHub (Windows)

1. Cree un repositorio y suba **todo el contenido de esta carpeta** (incluida `.github/`).
2. En la pestaña **Actions** se ejecuta solo el workflow *Compilar Trazo (Windows)* en cada push
   (también puede lanzarlo a mano con *Run workflow*).
3. Al terminar, abra la ejecución y descargue el artefacto **Trazo-windows** (un `.zip`).
   Descomprímalo y ejecute `Trazo/Trazo.exe`.
4. Para publicar una versión: `git tag v0.1.0 && git push --tags` adjunta el zip a un *Release*.

Las pruebas del workflow son informativas (`continue-on-error`): un fallo de test no impide generar el ejecutable.

## Ejecutar desde el código

```
pip install -r requirements.txt
python run_trazo.py
```

## Funciones

| Área | Qué incluye |
|---|---|
| Dibujo | Rectángulo, elipse, línea, pluma Bézier (clic = recto, arrastrar = curvo), mano alzada, texto |
| Edición de curvas | Herramienta de nodos: mover nodos y manijas; *Convertir a curvas* (Ctrl+Q) |
| Selección | Selección rectangular, escalado/volteo con 8 manijas (Mayús = proporcional), flechas para mover |
| Formas | Soldar (unión), Intersección, Recortar |
| Organización | Agrupar/Desagrupar, orden Z, alinear y distribuir, panel de objetos con visibilidad |
| Transformar | Rotar 90° / ángulo libre, voltear H/V |
| Color | Relleno y contorno (con transparencia), grosor, paleta (clic izq. = relleno, der. = contorno) |
| Página | Formatos A3–A6, Carta, Oficio, horizontal/vertical; cuadrícula y ajuste a cuadrícula |
| Vista | Zoom con rueda, pan con botón central o barra espaciadora, ajustar a página/selección |
| Archivos | Formato propio `.trz`, exportar a SVG, PNG (DPI a elección) y PDF |
| Historial | Deshacer / rehacer (100 pasos) |

Atajos de herramientas: V selección, N nodos, R rectángulo, E elipse, L línea, P pluma, F mano alzada, T texto.

## Limitaciones conocidas (versión 0.1)

- Sin importación de SVG/AI/CDR/PDF; solo se abre el formato `.trz`.
- La herramienta de nodos mueve nodos y manijas; todavía no agrega ni elimina nodos.
- Sin degradados, transparencia por objeto, contornos con guiones, efectos ni modo CMYK.
- Los contornos escalan junto con el objeto (el grosor se deforma si se escala de forma no uniforme).
- El texto es de una sola fuente/estilo por objeto y no tiene texto artístico en curva.
- Un solo documento por ventana y una sola página.

## Estructura

```
trazo/model.py    ítems, estilos y serialización
trazo/ops.py      agrupar, orden, alinear, booleanas, portapapeles
trazo/canvas.py   escena con historial y vista con herramientas
trazo/window.py   ventana, menús, barras, paleta, panel de objetos
trazo/export.py   SVG / PNG / PDF
tests/            pruebas sin pantalla
```
