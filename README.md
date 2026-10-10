# El Pulso: periódico automatizado

Una página con pestañas (mercados, República Dominicana, internacional, tecnología, política y medio ambiente) que se actualiza sola cada 2 horas.

## Cómo funciona

1. `scripts/build_news.py` lee los RSS de `scripts/sources.json`.
2. Claude escribe un titular y un resumen nuevos para cada nota, con las palabras de la IA y usando solo lo que trae el RSS.
3. Se guarda todo en `data/news.json`.
4. `index.html` lee ese archivo y muestra las pestañas. Cada nota enlaza al medio original.
5. GitHub Actions repite los pasos 1 a 3 cada 2 horas, gratis.

## Ponerlo en línea (gratis)

1. Crea un repositorio en GitHub y sube esta carpeta.
2. En el repo: Settings, Secrets and variables, Actions, New repository secret. Nombre: `ANTHROPIC_API_KEY`. Valor: tu clave de la API de Anthropic (se saca en console.anthropic.com).
3. En Settings, Pages: elige la rama `main` y la carpeta raíz.
4. En la pestaña Actions, corre "Actualizar noticias" con el botón Run workflow para llenar la página por primera vez.

## Probarlo en tu computadora

```bash
pip install -r scripts/requirements.txt
export ANTHROPIC_API_KEY=tu_clave
python scripts/build_news.py
python -m http.server 8000   # abre http://localhost:8000
```

Sin clave, el script igual funciona: muestra solo titulares y enlaces.

## Personalizar

- Medios y secciones: edita `scripts/sources.json`. Si un medio no tiene RSS o cambió la dirección, el script lo salta y avisa en la consola.
- Nombre del sitio: cambia "El Pulso" en `index.html` (dos lugares: `<title>` y el `<h1>`).
- Cantidad de notas por pestaña: variable `MAX_PER_SECTION` (por defecto 8).
- Costo: usa un modelo pequeño y no vuelve a reescribir notas que ya procesó, así que el gasto es bajo.

## Por qué resumen y no copia

El script no copia ni reescribe artículos completos: arma un resumen corto con la información del RSS y siempre enlaza al medio. Es lo más seguro con los derechos de autor y le devuelve visitas a los periódicos.
