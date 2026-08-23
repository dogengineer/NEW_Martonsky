from pathlib import Path
import html
import re
import json

BASE_DIR = Path("pdf")
TEMPLATE_FILE = Path("site_template.html")
OUTPUT_FILE = Path("index.html")

SUPPORTED_EXTENSIONS = {".pdf", ".html", ".htm"}

def clean_name(name: str) -> str:
    name = Path(name).name
    name = re.sub(r"^\d+_", "", name)
    name = re.sub(r"(?:\.(?:pdf|html|htm))+$", "", name, flags=re.I)
    return name.strip()

def get_order(name: str) -> int:
    name = Path(name).name
    m = re.match(r"^(\d+)_", name)
    return int(m.group(1)) if m else 999999

def is_supported_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS

def get_folder_items(folder: Path):
    if not folder.is_dir():
        return []

    items = [
        p for p in folder.iterdir()
        if p.is_dir() or is_supported_file(p)
    ]

    items.sort(key=lambda p: (get_order(p.name), clean_name(p.name).lower()))
    return items

def file_link(path: Path, label: str) -> str:
    url = path.as_posix()
    safe_label = html.escape(label)
    js_url = html.escape(json.dumps(url), quote=True)

    if path.suffix.lower() == ".pdf":
        return (
            f'<a href="#" onclick="loadPDF({js_url});return false;">'
            f'{safe_label}</a>'
        )

    return (
        f'<a href="#" onclick="loadHTML({js_url});return false;">'
        f'{safe_label}</a>'
    )

def render_submenu(folder: Path) -> str:
    items = get_folder_items(folder)
    if not items:
        return ""

    out = ['<ul class="submenu">']

    for item in items:
        label = clean_name(item.name)

        if item.is_dir():
            children = get_folder_items(item)
            child_count = len(children)

            if child_count == 0:
                out.append(
                    '<li><span class="empty-item">'
                    + html.escape(label)
                    + '</span></li>'
                )

            elif child_count == 1:
                only_child = children[0]

                if only_child.is_dir():
                    out.append(
                        '<li class="has-submenu">'
                        '<span class="submenu-label">'
                        + html.escape(label)
                        + '<span class="arrow">›</span></span>'
                        + render_submenu(item)
                        + '</li>'
                    )
                else:
                    out.append(
                        '<li>'
                        + file_link(only_child, label)
                        + '</li>'
                    )

            else:
                out.append(
                    '<li class="has-submenu">'
                    '<span class="submenu-label">'
                    + html.escape(label)
                    + '<span class="arrow">›</span></span>'
                    + render_submenu(item)
                    + '</li>'
                )
        else:
            out.append('<li>' + file_link(item, label) + '</li>')

    out.append('</ul>')
    return "\n".join(out)

def render_navigation() -> str:
    if not BASE_DIR.is_dir():
        return ""

    top_folders = [p for p in BASE_DIR.iterdir() if p.is_dir()]
    top_folders.sort(key=lambda p: (get_order(p.name), clean_name(p.name).lower()))

    out = []

    for folder in top_folders:
        folder_label = clean_name(folder.name)
        items = get_folder_items(folder)
        item_count = len(items)

        if item_count == 0:
            out.append(
                '<li><span class="menu-label empty-section">'
                + html.escape(folder_label)
                + '</span></li>'
            )

        elif item_count == 1:
            only_item = items[0]

            if only_item.is_dir():
                out.append(
                    '<li class="top-menu-item">'
                    '<span class="menu-label">'
                    + html.escape(folder_label)
                    + '</span>'
                    + render_submenu(folder)
                    + '</li>'
                )
            else:
                out.append(
                    '<li>'
                    + file_link(only_item, folder_label)
                    + '</li>'
                )

        else:
            out.append(
                '<li class="top-menu-item">'
                '<span class="menu-label">'
                + html.escape(folder_label)
                + '</span>'
                + render_submenu(folder)
                + '</li>'
            )

    return "\n".join(out)

def main():
    template = TEMPLATE_FILE.read_text(encoding="utf-8")
    navigation = render_navigation()

    if "{{NAVIGATION}}" not in template:
        raise RuntimeError("Placeholder {{NAVIGATION}} non trovato in site_template.html")

    output = template.replace("{{NAVIGATION}}", navigation)
    OUTPUT_FILE.write_text(output, encoding="utf-8")

    print(f"Creato {OUTPUT_FILE}")
    print(f"Cartella analizzata: {BASE_DIR.resolve()}")

if __name__ == "__main__":
    main()
