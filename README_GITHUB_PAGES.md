# NEW_Martonsky – GitHub Pages

Questa versione sostituisce la parte PHP che leggeva automaticamente la cartella `pdf/`.

## File da aggiungere alla repository

Copia nella root della repo:

- `generate_site.py`
- `site_template.html`
- `.nojekyll`
- `.github/workflows/deploy-pages.yml`

Mantieni inoltre le cartelle già esistenti:

- `pdf/`
- `Icons/`
- eventuali altre risorse

Il vecchio `index.php` può essere conservato come backup, ma GitHub Pages non lo esegue.

## Struttura prevista

Esempio:

```text
NEW_Martonsky/
├── generate_site.py
├── site_template.html
├── index.php              # opzionale, solo backup
├── .nojekyll
├── Icons/
│   ├── icon.png
│   └── favicon.png
├── pdf/
│   ├── home.pdf
│   ├── 01_Illustrations/
│   │   ├── 01_Project A/
│   │   │   └── project-a.pdf
│   │   └── 02_Project B/
│   │       └── project-b.pdf
│   └── 02_Commissioned/
└── .github/
    └── workflows/
        └── deploy-pages.yml
```

## Come funziona

Ad ogni `git push` sulla branch `main`:

1. GitHub Actions esegue `generate_site.py`.
2. Lo script legge ricorsivamente `pdf/`.
3. Genera `index.html` a partire da `site_template.html`.
4. GitHub Pages pubblica il sito statico risultante.

La logica di nomi e ordinamento replica quella del PHP:
- `01_Illustrations` viene mostrato come `Illustrations`;
- PDF/HTML sono supportati;
- cartelle e file vengono ordinati dal prefisso numerico;
- un progetto con un solo file viene mostrato direttamente;
- più elementi generano menu e sottomenu.

## Configurazione GitHub Pages

Dopo aver caricato questi file:

1. Apri `Settings`.
2. Apri `Pages`.
3. In `Build and deployment`, cambia `Source` da **Deploy from a branch** a **GitHub Actions**.
4. Vai nella scheda `Actions`.
5. Attendi il completamento del workflow `Deploy Martonsky to GitHub Pages`.
6. Apri nuovamente l'URL GitHub Pages.

## Test locale facoltativo

Da Prompt dei comandi nella cartella della repo:

```cmd
python generate_site.py
```

Questo genera `index.html` localmente.

Poi puoi fare:

```cmd
git status
```

Nota: il workflow genera `index.html` automaticamente durante il deploy; non è necessario versionarlo se preferisci non farlo.

## Aggiornare un progetto

Aggiungi/rimuovi/rinomina file o cartelle sotto `pdf/`, quindi:

```cmd
git add .
git commit -m "Aggiornamento progetti"
git push
```

Il menu verrà rigenerato automaticamente.
