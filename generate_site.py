from pathlib import Path
import html
import re
import json
import xml.etree.ElementTree as ET

try:
    import pymupdf as fitz  # PDF text, image and layout analysis
except ImportError:
    fitz = None

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

.pdf-page-shell,
.pdf-column-shell{
    position:relative;
    overflow:hidden;
    margin-left:auto;
    margin-right:auto;
    background:#fff;
}

.pdf-column-list{
    display:flex;
    flex-direction:column;
    gap:28px;
    width:100%;
    box-sizing:border-box;
    padding:18px clamp(14px,4vw,24px) 32px;
    background:#fff;
}

.pdf-image-hotspot{
    position:absolute;
    z-index:3;
    display:block;
    border:0;
    padding:0;
    background:transparent;
    cursor:zoom-in;
}

.pdf-link-hotspot{
    position:absolute;
    z-index:4;
    display:block;
    background:transparent;
}

.pdf-link-hotspot:focus-visible{
    outline:2px solid #111;
    outline-offset:2px;
}

.pdf-image-hotspot:focus-visible{
    outline:2px solid #111;
    outline-offset:2px;
}

.pdf-text-clip{
    position:absolute;
    inset:0;
    z-index:2;
    overflow:hidden;
    pointer-events:none;
}

.pdf-text-layer{
    position:absolute;
    margin:0;
    padding:0;
    overflow:hidden;
    line-height:1;
    text-align:initial;
    text-size-adjust:none;
    forced-color-adjust:none;
    transform-origin:0 0;
    pointer-events:auto;
}

.pdf-text-layer span,
.pdf-text-layer br{
    position:absolute;
    color:transparent;
    white-space:pre;
    cursor:text;
    transform-origin:0 0;
}

.pdf-text-layer ::selection{
    color:transparent;
    background:rgba(40,110,255,.28);
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

    #viewer{
        overflow-x:hidden;
    }

    .pdf-column-list{
        gap:24px;
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
        if(typeof image === "string"){
            return image;
        }

        return (
            image.getAttribute("src") ||
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
        enlargedImage.alt =
            typeof image === "string"
            ? "Enlarged project image"
            : image.getAttribute("aria-label") || "Enlarged project image";
        enlargedImage.decoding = "async";

        lightboxContent.replaceChildren(enlargedImage);
        previousOverflow = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        lightbox.classList.add("open");
        closeButton.focus({preventScroll:true});
    }

    window.openProjectImage = openLightbox;

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

def _pdf_rect_values(rect):
    return [
        round(float(rect.x0), 3),
        round(float(rect.y0), 3),
        round(float(rect.x1), 3),
        round(float(rect.y1), 3),
    ]

def detect_pdf_columns(page_width, page_height, rectangles, has_text):
    """Find clear vertical columns from whitespace between PDF elements."""
    if not has_text or page_width / max(page_height, 1) < 1.15:
        return []

    intervals = []
    for rect in rectangles:
        x0 = max(0.0, min(page_width, float(rect.x0)))
        x1 = max(0.0, min(page_width, float(rect.x1)))
        if x1 - x0 >= page_width * 0.025:
            intervals.append([x0, x1])

    intervals.sort(key=lambda item: (item[0], item[1]))
    if len(intervals) < 3:
        return []

    join_tolerance = page_width * 0.006
    groups = []
    for x0, x1 in intervals:
        if not groups or x0 > groups[-1][1] + join_tolerance:
            groups.append([x0, x1])
        else:
            groups[-1][1] = max(groups[-1][1], x1)

    groups = [
        group for group in groups
        if group[1] - group[0] >= page_width * 0.12
    ]

    if not 2 <= len(groups) <= 4:
        return []

    # InDesign spreads often use a narrow but deliberate gutter. 1.2% keeps
    # those columns separate without treating ordinary word/paragraph gaps as
    # independent columns.
    minimum_gap = page_width * 0.012
    if any(
        groups[index + 1][0] - groups[index][1] < minimum_gap
        for index in range(len(groups) - 1)
    ):
        return []

    padding = page_width * 0.012
    columns = []
    for index, (x0, x1) in enumerate(groups):
        left_padding = padding
        right_padding = padding
        if index > 0:
            previous_gap = x0 - groups[index - 1][1]
            left_padding = min(padding, previous_gap * 0.45)
        if index + 1 < len(groups):
            next_gap = groups[index + 1][0] - x1
            right_padding = min(padding, next_gap * 0.45)

        left = max(0.0, x0 - left_padding)
        right = min(page_width, x1 + right_padding)
        columns.append({
            "x": round(left, 3),
            "y": 0.0,
            "width": round(right - left, 3),
            "height": round(page_height, 3),
        })

    return columns

def analyze_pdf_projects():
    """Extract searchable text, image bounds and mobile columns from PDFs."""
    manifest = {}

    if not BASE_DIR.is_dir():
        return manifest

    pdf_files = sorted(
        BASE_DIR.rglob("*.pdf"),
        key=lambda path: path.as_posix().lower(),
    )

    if pdf_files and fitz is None:
        print(
            "ATTENZIONE: PyMuPDF non installato. "
            "Esegui: python3 -m pip install pymupdf"
        )
        return manifest

    for pdf_path in pdf_files:
        url = pdf_path.as_posix()
        try:
            document = fitz.open(pdf_path)
            pages = []
            all_text = []

            for page_index, page in enumerate(document):
                page_width = float(page.rect.width)
                page_height = float(page.rect.height)
                page_text = page.get_text("text").strip()
                if page_text:
                    all_text.append(page_text)

                text_rectangles = []
                for block in page.get_text("blocks"):
                    if len(block) > 6 and block[6] == 0 and str(block[4]).strip():
                        text_rectangles.append(fitz.Rect(block[:4]))

                images = []
                image_rectangles = []
                for image_number, image_info in enumerate(
                    page.get_image_info(xrefs=True),
                    start=1,
                ):
                    bbox = fitz.Rect(image_info["bbox"])
                    if bbox.width <= 1 or bbox.height <= 1:
                        continue

                    image_rectangles.append(bbox)
                    images.append({
                        "bbox": _pdf_rect_values(bbox),
                        "label": f"Enlarge image {image_number}",
                    })

                columns = detect_pdf_columns(
                    page_width,
                    page_height,
                    text_rectangles + image_rectangles,
                    bool(page_text),
                )

                links = []
                for target in sorted(set(re.findall(
                    r"https?://[^\s\]\)>]+",
                    page_text,
                    flags=re.I,
                ))):
                    for link_rect in page.search_for(target):
                        links.append({
                            "bbox": _pdf_rect_values(link_rect),
                            "url": target,
                            "label": f"Open link {target}",
                        })

                pages.append({
                    "page": page_index + 1,
                    "width": round(page_width, 3),
                    "height": round(page_height, 3),
                    "columns": columns,
                    "images": images,
                    "links": links,
                    "text": page_text,
                })

            document.close()
            manifest[url] = {
                "text": "\n".join(all_text),
                "pages": pages,
                "images": sum(len(page["images"]) for page in pages),
                "column_pages": sum(bool(page["columns"]) for page in pages),
            }

        except Exception as error:
            manifest[url] = {
                "text": "",
                "pages": [],
                "images": 0,
                "column_pages": 0,
                "error": str(error),
            }

    return manifest

def inject_project_runtime(template: str, svg_manifest, pdf_manifest) -> str:
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
        + json.dumps(svg_manifest, ensure_ascii=False)
        + ";window.PDF_PROJECT_MANIFEST = "
        + json.dumps(pdf_manifest, ensure_ascii=False)
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
    pdf_manifest = analyze_pdf_projects()

    if "{{NAVIGATION}}" not in template:
        raise RuntimeError(
            "Placeholder {{NAVIGATION}} non trovato in site_template.html"
        )

    output = template.replace("{{NAVIGATION}}", navigation)
    output = inject_project_runtime(output, svg_manifest, pdf_manifest)
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

    pdf_image_count = sum(item["images"] for item in pdf_manifest.values())
    pdf_column_pages = sum(
        item["column_pages"] for item in pdf_manifest.values()
    )
    pdf_error_count = sum("error" in item for item in pdf_manifest.values())

    print(f"PDF analizzati: {len(pdf_manifest)}")
    print(f"Immagini PDF rilevate: {pdf_image_count}")
    print(f"Pagine PDF con colonne mobili: {pdf_column_pages}")

    if pdf_error_count:
        print(f"PDF non analizzati per errore: {pdf_error_count}")

    for pdf_path, info in pdf_manifest.items():
        status = (
            f"{info['column_pages']} pagine a colonne"
            if info["column_pages"]
            else "layout mobile standard"
        )
        print(
            f"  - {pdf_path}: {info['images']} immagini; {status}"
        )

if __name__ == "__main__":
    main()
