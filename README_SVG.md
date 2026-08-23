# NEW_Martonsky — versione SVG

Questa versione aggiunge il supporto `.svg` alla generazione automatica del menu.

## Cosa cambia

- `.svg` è ora un formato supportato insieme a PDF, HTML e HTM.
- Gli SVG vengono visualizzati direttamente dal browser come file SVG, quindi restano vettoriali.
- `icons/favicon.png` e `icons/icon.png` usano la cartella `icons` minuscola.
- I link LinkedIn del footer sono già aggiornati.
- La home predefinita è `pdf/home.svg`.

Se la tua home ha un nome diverso, modifica in `site_template.html`:

```js
loadSVG("pdf/home.svg");
```

## Uso locale

Dalla root della repository:

```cmd
python generate_site.py
python -m http.server 8000
```

Poi apri:

```text
http://localhost:8000/
```

Quando modifichi cartelle o file, rilancia soltanto:

```cmd
python generate_site.py
```

e aggiorna il browser.

## Pubblicazione

```cmd
git add .
git commit -m "Add SVG support"
git push
```

GitHub Actions rigenererà automaticamente `index.html`.
