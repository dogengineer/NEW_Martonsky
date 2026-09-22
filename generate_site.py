from pathlib import Path
import html
import re
import json
import xml.etree.ElementTree as ET

BASE_DIR = Path("pdf")
TEMPLATE_FILE = Path("site_template.html")
OUTPUT_FILE = Path("index.html")

SUPPORTED_EXTENSIONS = {".pdf", ".html", ".htm", ".svg"}

SVG_ZOOM_CSS = r"""
/* Automatic SVG image zoom, injected by generate_site.py */
.svg-zoom-hotspot{
    fill:transparent;
    stroke:none;
    cursor:zoom-in;
    pointer-events:all;
}

.mobile-svg-columns{
    display:flex;
    flex-direction:column;
    width:100%;
    gap:28px;
    overflow:hidden;
    background:#fff;
    box-sizing:border-box;
    padding:0 clamp(14px,4vw,24px);
}

.mobile-svg-column-frame{
    display:flex;
    justify-content:center;
    width:100%;
    overflow:hidden;
    contain:paint;
    isolation:isolate;
    background:#fff;
}

.mobile-svg-column-frame svg{
    display:block;
    width:100% !important;
    height:auto !important;
    max-width:none;
    margin:0 !important;
    background:#fff;
    overflow:hidden;
}

#svgImageLightbox{
    position:fixed;
    inset:0;
    z-index:20000;
    display:flex;
    align-items:center;
    justify-content:center;
    padding:34px;
    background:rgba(255,255,255,.91);
    opacity:0;
    visibility:hidden;
    cursor:zoom-out;
    transition:opacity .22s ease,visibility 0s linear .22s;
}

#svgImageLightbox.open{
    opacity:1;
    visibility:visible;
    transition:opacity .22s ease,visibility 0s;
}

.svg-image-lightbox-content{
    display:flex;
    align-items:center;
    justify-content:center;
    width:100%;
    height:100%;
    transform:scale(.96);
    transition:transform .28s cubic-bezier(.2,.75,.2,1);
    pointer-events:none;
}

#svgImageLightbox.open .svg-image-lightbox-content{
    transform:scale(1);
}

.svg-image-lightbox-content img{
    display:block;
    width:auto;
    height:auto;
    max-width:94vw;
    max-height:92vh;
    object-fit:contain;
}

.svg-image-lightbox-close{
    position:absolute;
    top:18px;
    right:22px;
    z-index:1;
    border:0;
    padding:4px 8px;
    background:transparent;
    color:#111;
    font:300 36px/1 Georgia,serif;
    cursor:pointer;
}

@media(max-width:800px){
    .mobile-svg-columns{
        gap:22px;
    }

    #svgImageLightbox{
        padding:20px 12px;
    }

    .svg-image-lightbox-close{
        top:8px;
        right:10px;
    }
}

@media(prefers-reduced-motion:reduce){
    #svgImageLightbox,
    .svg-image-lightbox-content{
        transition:none;
    }
}
"""

SVG_ZOOM_HTML = r"""
<div id="svgImageLightbox" role="dialog" aria-modal="true" aria-label="Enlarged image">
    <button class="svg-image-lightbox-close" type="button" aria-label="Close enlarged image">×</button>
    <div class="svg-image-lightbox-content"></div>
</div>
"""

SVG_ZOOM_JS = r"""
<script>
(function(){
    "use strict";

    const viewer = document.getElementById("svgViewer");
    const lightbox = document.getElementById("svgImageLightbox");
    const lightboxContent = lightbox.querySelector(".svg-image-lightbox-content");
    const closeButton = lightbox.querySelector(".svg-image-lightbox-close");
    let previousOverflow = "";

    function pointInRoot(point,matrix){
        return new DOMPoint(point.x,point.y).matrixTransform(matrix);
    }

    function elementBoundsInRoot(element,svg){
        const box = element.getBBox();
        const elementMatrix = element.getCTM();
        const rootMatrix = svg.getCTM();

        if(!elementMatrix || !rootMatrix){
            return null;
        }

        const relativeMatrix = rootMatrix.inverse().multiply(elementMatrix);
        const corners = [
            pointInRoot({x:box.x,y:box.y},relativeMatrix),
            pointInRoot({x:box.x + box.width,y:box.y},relativeMatrix),
            pointInRoot({x:box.x,y:box.y + box.height},relativeMatrix),
            pointInRoot({x:box.x + box.width,y:box.y + box.height},relativeMatrix)
        ];
        const xs = corners.map(point => point.x);
        const ys = corners.map(point => point.y);
        const x = Math.min(...xs);
        const y = Math.min(...ys);

        return {
            x:x,
            y:y,
            width:Math.max(...xs) - x,
            height:Math.max(...ys) - y
        };
    }

    function svgHasText(svg){
        return [...svg.querySelectorAll("text")]
            .some(element => (element.textContent || "").trim().length > 0);
    }

    function rangesOverlap(first,second){
        const overlap = Math.min(first.maxY,second.maxY) -
            Math.max(first.minY,second.minY);
        const smallerHeight = Math.min(
            first.maxY - first.minY,
            second.maxY - second.minY
        );

        return smallerHeight > 0 && overlap / smallerHeight >= .18;
    }

    function detectMobileColumns(svg){
        if(
            !window.matchMedia("(max-width:800px)").matches ||
            !svgHasText(svg)
        ){
            return null;
        }

        let contentBounds;

        try{
            contentBounds = svg.getBBox();
        }
        catch(error){
            return null;
        }

        if(
            contentBounds.width <= 0 ||
            contentBounds.height <= 0 ||
            contentBounds.width / contentBounds.height < 1.15
        ){
            return null;
        }

        const items = [...svg.querySelectorAll("text, image")]
            .map(element => {
                try{
                    return elementBoundsInRoot(element,svg);
                }
                catch(error){
                    return null;
                }
            })
            .filter(bounds =>
                bounds && bounds.width > 0 && bounds.height > 0
            )
            .map(bounds => ({
                ...bounds,
                centerX:bounds.x + bounds.width / 2,
                minY:bounds.y,
                maxY:bounds.y + bounds.height
            }))
            .sort((first,second) => first.centerX - second.centerX);

        if(items.length < 4){
            return null;
        }

        const minimumGap = contentBounds.width * .105;
        const gaps = [];

        for(let index = 0;index < items.length - 1;index++){
            const gap = items[index + 1].centerX - items[index].centerX;

            if(gap >= minimumGap){
                gaps.push({
                    size:gap,
                    boundary:(items[index].centerX + items[index + 1].centerX) / 2
                });
            }
        }

        const rankedGaps = gaps
            .sort((first,second) => second.size - first.size);
        const largestGap = rankedGaps[0]?.size || 0;
        const selectedGaps = rankedGaps
            .filter(gap => gap.size >= largestGap * .68)
            .slice(0,3)
            .sort((first,second) => first.boundary - second.boundary);

        if(selectedGaps.length === 0){
            return null;
        }

        const boundaries = selectedGaps.map(gap => gap.boundary);
        const groups = Array.from(
            {length:boundaries.length + 1},
            () => []
        );

        items.forEach(item => {
            const groupIndex = boundaries.findIndex(
                boundary => item.centerX < boundary
            );
            groups[groupIndex === -1 ? groups.length - 1 : groupIndex].push(item);
        });

        if(groups.some(group => group.length === 0)){
            return null;
        }

        const groupRanges = groups.map(group => ({
            minY:Math.min(...group.map(item => item.minY)),
            maxY:Math.max(...group.map(item => item.maxY))
        }));

        for(let index = 0;index < groupRanges.length - 1;index++){
            if(!rangesOverlap(groupRanges[index],groupRanges[index + 1])){
                return null;
            }
        }

        /*
         * Crop every column around the elements that actually belong to it.
         * Using the midpoint between columns as a crop edge can include a
         * narrow strip of a wide image from the previous column.
         */
        const columns = groups.map(group => {
            const minX = Math.min(...group.map(item => item.x));
            const maxX = Math.max(
                ...group.map(item => item.x + item.width)
            );
            const minY = Math.min(...group.map(item => item.minY));
            const maxY = Math.max(...group.map(item => item.maxY));
            const naturalWidth = maxX - minX;
            const naturalHeight = maxY - minY;
            const horizontalPadding = Math.max(
                naturalWidth * .035,
                contentBounds.width * .006
            );
            const verticalPadding = Math.max(
                naturalHeight * .018,
                contentBounds.height * .006
            );

            return {
                x:minX - horizontalPadding,
                y:minY - verticalPadding,
                width:naturalWidth + horizontalPadding * 2,
                height:naturalHeight + verticalPadding * 2
            };
        });

        if(columns.some(column => column.width < contentBounds.width * .16)){
            return null;
        }

        return columns;
    }

    function makeIdsUnique(svg,suffix){
        const replacements = [];

        svg.querySelectorAll("[id]").forEach(element => {
            const oldId = element.id;
            const newId = oldId + "-" + suffix;
            replacements.push([oldId,newId]);
            element.id = newId;
        });

        function replaceReferences(value){
            replacements.forEach(([oldId,newId]) => {
                const escapedId = oldId.replace(/[.*+?^${}()|[\]\\]/g,"\\$&");
                value = value.replace(
                    new RegExp("#" + escapedId + "(?![A-Za-z0-9_.:-])","g"),
                    "#" + newId
                );
            });
            return value;
        }

        svg.querySelectorAll("*").forEach(element => {
            [...element.attributes].forEach(attribute => {
                const value = replaceReferences(attribute.value);

                if(value !== attribute.value){
                    if(attribute.namespaceURI){
                        element.setAttributeNS(
                            attribute.namespaceURI,
                            attribute.name,
                            value
                        );
                    }
                    else{
                        element.setAttribute(attribute.name,value);
                    }
                }
            });
        });

        svg.querySelectorAll("style").forEach(style => {
            style.textContent = replaceReferences(style.textContent || "");
        });
    }

    function createMobileColumns(svg,columns){
        const wrapper = document.createElement("div");
        wrapper.className = "mobile-svg-columns";
        wrapper.dataset.columnLayoutDetected = "true";

        const clones = columns.map((column,index) => {
            const frame = document.createElement("div");
            frame.className = "mobile-svg-column-frame";

            const clone = svg.cloneNode(true);
            clone.removeAttribute("width");
            clone.removeAttribute("height");
            clone.removeAttribute("style");
            clone.removeAttribute("data-zoom-ready");
            clone.querySelectorAll(".svg-zoom-hotspot").forEach(node => node.remove());
            makeIdsUnique(clone,"mobile-column-" + index);
            clone.setAttribute(
                "viewBox",
                [column.x,column.y,column.width,column.height].join(" ")
            );
            clone.setAttribute("preserveAspectRatio","xMidYMin meet");
            clone.setAttribute("aria-label","Project column " + (index + 1));
            frame.appendChild(clone);
            wrapper.appendChild(frame);
            return clone;
        });

        viewer.classList.remove("mobile-svg-scroll");
        viewer.scrollLeft = 0;
        svg.replaceWith(wrapper);
        return clones;
    }

    function closeLightbox(){
        lightbox.classList.remove("open");
        document.body.style.overflow = previousOverflow;
        window.setTimeout(() => {
            if(!lightbox.classList.contains("open")){
                lightboxContent.replaceChildren();
            }
        },230);
    }

    function imageSource(image){
        return (
            image.getAttribute("href") ||
            image.getAttributeNS("http://www.w3.org/1999/xlink","href") ||
            ""
        );
    }

    function openLightbox(image){
        const source = imageSource(image);

        if(!source){
            return;
        }

        const enlargedImage = document.createElement("img");
        enlargedImage.src = source;
        enlargedImage.alt = image.getAttribute("aria-label") || "Enlarged project image";
        enlargedImage.decoding = "async";

        lightboxContent.replaceChildren(enlargedImage);
        previousOverflow = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        lightbox.classList.add("open");
        closeButton.focus({preventScroll:true});
    }

    function prepareSvg(svg){
        if(svg.dataset.zoomReady === "true"){
            return;
        }

        svg.dataset.zoomReady = "true";
        const images = [...svg.querySelectorAll("image")];
        const hasText = svgHasText(svg);

        /* A full-page SVG containing only an image does not need a lightbox. */
        if(!hasText){
            return;
        }

        images.forEach((image,index) => {
            let bounds;

            try{
                bounds = elementBoundsInRoot(image,svg);
            }
            catch(error){
                console.warn("Unable to prepare SVG image zoom",error);
                return;
            }

            if(!bounds || bounds.width <= 0 || bounds.height <= 0){
                return;
            }

            const viewBox = svg.viewBox.baseVal;
            const intersectsViewBox =
                bounds.x < viewBox.x + viewBox.width &&
                bounds.x + bounds.width > viewBox.x &&
                bounds.y < viewBox.y + viewBox.height &&
                bounds.y + bounds.height > viewBox.y;

            if(!intersectsViewBox){
                return;
            }

            const hotspot = document.createElementNS(
                "http://www.w3.org/2000/svg",
                "rect"
            );
            hotspot.setAttribute("x",bounds.x);
            hotspot.setAttribute("y",bounds.y);
            hotspot.setAttribute("width",bounds.width);
            hotspot.setAttribute("height",bounds.height);
            hotspot.setAttribute("class","svg-zoom-hotspot");
            hotspot.setAttribute("tabindex","0");
            hotspot.setAttribute("role","button");
            hotspot.setAttribute("aria-label","Enlarge image " + (index + 1));

            const open = event => {
                event.preventDefault();
                event.stopPropagation();
                openLightbox(image);
            };

            hotspot.addEventListener("click",open);
            hotspot.addEventListener("keydown",event => {
                if(event.key === "Enter" || event.key === " "){
                    open(event);
                }
            });
            svg.appendChild(hotspot);
        });
    }

    function prepareCurrentSvg(){
        const existingColumns =
            viewer.querySelector(".mobile-svg-columns");

        if(existingColumns){
            const columnSvgs = [
                ...existingColumns.querySelectorAll(
                    ":scope > .mobile-svg-column-frame > svg"
                )
            ];
            window.requestAnimationFrame(() => {
                columnSvgs.forEach(prepareSvg);
            });
            return;
        }

        const svg = viewer.querySelector("svg");
        if(!svg){
            return;
        }

        window.requestAnimationFrame(() => {
            window.requestAnimationFrame(() => {
                const columns = detectMobileColumns(svg);

                if(columns){
                    createMobileColumns(svg,columns).forEach(prepareSvg);
                }
                else{
                    prepareSvg(svg);
                }
            });
        });
    }

    const observer = new MutationObserver(prepareCurrentSvg);
    observer.observe(viewer,{childList:true,subtree:false});

    closeButton.addEventListener("click",closeLightbox);
    lightbox.addEventListener("click",event => {
        if(event.target === lightbox){
            closeLightbox();
        }
    });
    document.addEventListener("keydown",event => {
        if(event.key === "Escape" && lightbox.classList.contains("open")){
            closeLightbox();
        }
    });
})();
</script>
"""

def clean_name(name: str) -> str:
    name = Path(name).name
    name = re.sub(r"^\d+_", "", name)
    name = re.sub(r"(?:\.(?:pdf|html|htm|svg))+$", "", name, flags=re.I)
    return name.strip()

def get_order(name: str) -> int:
    name = Path(name).name
    match = re.match(r"^(\d+)_", name)
    return int(match.group(1)) if match else 999999

def is_supported_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS

def get_folder_items(folder: Path):
    if not folder.is_dir():
        return []

    items = [
        item for item in folder.iterdir()
        if item.is_dir() or is_supported_file(item)
    ]

    items.sort(
        key=lambda item: (
            get_order(item.name),
            clean_name(item.name).lower()
        )
    )

    return items

def file_link(path: Path, label: str) -> str:
    url = path.as_posix()
    safe_label = html.escape(label)
    js_url = html.escape(json.dumps(url), quote=True)
    extension = path.suffix.lower()

    if extension == ".pdf":
        action = f"loadPDF({js_url})"
    elif extension == ".svg":
        action = f"loadSVG({js_url})"
    else:
        action = f"loadHTML({js_url})"

    return (
        f'<a href="#" onclick="{action};return false;">'
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
            out.append(
                '<li>'
                + file_link(item, label)
                + '</li>'
            )

    out.append('</ul>')
    return "\n".join(out)

def render_navigation() -> str:
    if not BASE_DIR.is_dir():
        return ""

    top_folders = [
        folder for folder in BASE_DIR.iterdir()
        if folder.is_dir()
    ]

    top_folders.sort(
        key=lambda folder: (
            get_order(folder.name),
            clean_name(folder.name).lower()
        )
    )

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

def local_tag_name(tag: str) -> str:
    """Return an XML tag name without its optional namespace."""
    return tag.rsplit("}", 1)[-1].lower()

def analyze_svg_images():
    """Scan every SVG recursively and describe its embedded image elements."""
    manifest = {}

    if not BASE_DIR.is_dir():
        return manifest

    svg_files = sorted(
        BASE_DIR.rglob("*.svg"),
        key=lambda path: path.as_posix().lower()
    )

    for svg_path in svg_files:
        try:
            root = ET.parse(svg_path).getroot()
            images = [
                element for element in root.iter()
                if local_tag_name(element.tag) == "image"
            ]
            text_elements = [
                element for element in root.iter()
                if local_tag_name(element.tag) == "text"
                and "".join(element.itertext()).strip()
            ]

            embedded = 0
            external = 0

            for image in images:
                href = (
                    image.get("href")
                    or image.get("{http://www.w3.org/1999/xlink}href")
                    or ""
                )

                if href.startswith("data:image/"):
                    embedded += 1
                else:
                    external += 1

            manifest[svg_path.as_posix()] = {
                "images": len(images),
                "embedded": embedded,
                "external": external,
                "has_text": bool(text_elements),
                "zoom_enabled": bool(images and text_elements),
            }

        except (ET.ParseError, OSError) as error:
            manifest[svg_path.as_posix()] = {
                "images": 0,
                "embedded": 0,
                "external": 0,
                "has_text": False,
                "zoom_enabled": False,
                "error": str(error),
            }

    return manifest

def inject_svg_zoom(template: str, manifest) -> str:
    """Inject the reusable lightbox without modifying the source SVG files."""
    marker = "Automatic SVG image zoom, injected by generate_site.py"

    if marker in template:
        return template

    if "</style>" not in template:
        raise RuntimeError("Tag </style> non trovato in site_template.html")

    if "</body>" not in template:
        raise RuntimeError("Tag </body> non trovato in site_template.html")

    manifest_script = (
        "<script>window.SVG_IMAGE_MANIFEST = "
        + json.dumps(manifest, ensure_ascii=False)
        + ";</script>"
    )

    template = template.replace(
        "</style>",
        SVG_ZOOM_CSS + "\n</style>",
        1,
    )

    zoom_runtime = (
        SVG_ZOOM_HTML
        + "\n"
        + manifest_script
        + "\n"
        + SVG_ZOOM_JS
    )

    return template.replace(
        "</body>",
        zoom_runtime + "\n</body>",
        1,
    )

def main():
    template = TEMPLATE_FILE.read_text(encoding="utf-8")
    navigation = render_navigation()
    svg_manifest = analyze_svg_images()

    if "{{NAVIGATION}}" not in template:
        raise RuntimeError(
            "Placeholder {{NAVIGATION}} non trovato in site_template.html"
        )

    output = template.replace("{{NAVIGATION}}", navigation)
    output = inject_svg_zoom(output, svg_manifest)
    OUTPUT_FILE.write_text(output, encoding="utf-8")

    print(f"Creato {OUTPUT_FILE}")
    print(f"Cartella analizzata: {BASE_DIR.resolve()}")

    svg_count = len(svg_manifest)
    image_count = sum(item["images"] for item in svg_manifest.values())
    zoomable_image_count = sum(
        item["images"]
        for item in svg_manifest.values()
        if item["zoom_enabled"]
    )
    error_count = sum("error" in item for item in svg_manifest.values())

    print(f"SVG analizzati: {svg_count}")
    print(f"Immagini SVG trovate: {image_count}")
    print(f"Immagini rese ingrandibili: {zoomable_image_count}")

    if error_count:
        print(f"SVG non analizzati per errore: {error_count}")

    for svg_path, info in svg_manifest.items():
        if info["images"]:
            zoom_status = "zoom attivo" if info["zoom_enabled"] else "zoom disattivato: nessun testo"
            print(
                f"  - {svg_path}: {info['images']} immagini "
                f"({info['embedded']} incorporate, "
                f"{info['external']} esterne; {zoom_status})"
            )

if __name__ == "__main__":
    main()
