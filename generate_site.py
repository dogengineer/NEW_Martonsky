from pathlib import Path
import base64
import hashlib
import html
import re
import json
import sys
import xml.etree.ElementTree as ET
from io import BytesIO

import pymupdf
from fontTools.agl import AGL2UV
from fontTools.cffLib import CFFFontSet
from fontTools.fontBuilder import FontBuilder

BASE_DIR = Path("pdf")
TEMPLATE_FILE = Path("site_template.html")
OUTPUT_FILE = Path("index.html")
SUPPORTED_EXTENSIONS = {".html", ".htm", ".svg"}
SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", XLINK_NS)

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

    #viewer{
        overflow-x:hidden;
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

    if extension == ".svg":
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

def _font_family_and_style(font_name: str) -> tuple[str, str, str]:
    name = font_name.split("+", 1)[-1]
    style = "normal"
    weight = "400"
    if name.endswith("-Italic"):
        name = name[:-7]
        style = "italic"
    if name.endswith("-Bold"):
        name = name[:-5]
        weight = "700"
    if name.endswith("-Regular"):
        name = name[:-8]
    return name, style, weight


def _cff_to_opentype_font(data: bytes, ps_name: str) -> bytes:
    cff = CFFFontSet()
    cff.decompile(BytesIO(data), None)
    top = cff.topDictIndex[0]
    glyph_order = list(top.CharStrings.charStrings.keys())
    cmap = {}
    for glyph_name in glyph_order:
        codepoint = AGL2UV.get(glyph_name)
        if codepoint is not None:
            cmap[codepoint] = glyph_name

    builder = FontBuilder(1000, isTTF=False)
    builder.setupGlyphOrder(glyph_order)
    builder.setupCharacterMap(cmap)
    builder.setupHorizontalMetrics({glyph: (600, 0) for glyph in glyph_order})
    builder.setupHorizontalHeader(ascent=900, descent=-300)
    builder.setupOS2(
        sTypoAscender=900,
        sTypoDescender=-300,
        usWinAscent=1000,
        usWinDescent=300,
    )
    builder.setupNameTable({
        "familyName": ps_name,
        "styleName": "Regular",
        "fullName": ps_name,
        "psName": ps_name,
    })
    builder.setupPost()
    builder.setupCFF(
        ps_name,
        {
            "FontBBox": getattr(top, "FontBBox", [-200, -300, 1200, 1000]),
            "Weight": getattr(top, "Weight", "Regular"),
        },
        {
            glyph_name: top.CharStrings[glyph_name]
            for glyph_name in glyph_order
        },
        dict(top.Private.rawDict),
    )
    output = BytesIO()
    builder.save(output)
    return output.getvalue()


def extract_embedded_fonts(document: pymupdf.Document):
    faces = {}
    seen_xrefs = set()
    for page in document:
        for font in page.get_fonts(full=True):
            xref = int(font[0])
            if not xref or xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)
            try:
                original_name, extension, _font_type, raw_data = (
                    document.extract_font(xref)
                )
                family, style, weight = _font_family_and_style(original_name)
                if extension.lower() == "ttf":
                    font_data = raw_data
                    mime = "font/ttf"
                    format_name = "truetype"
                elif extension.lower() == "cff":
                    font_data = _cff_to_opentype_font(raw_data, family)
                    mime = "font/otf"
                    format_name = "opentype"
                else:
                    continue
                faces[original_name.split("+", 1)[-1]] = {
                    "family": family,
                    "style": style,
                    "weight": weight,
                    "src": (
                        f"data:{mime};base64,"
                        f"{base64.b64encode(font_data).decode('ascii')}"
                    ),
                    "format": format_name,
                }
            except Exception as error:
                print(
                    f"ATTENZIONE: font PDF {xref} non incorporato: {error}",
                    file=sys.stderr,
                )
    return faces


def add_font_styles(root: ET.Element, faces) -> None:
    if not faces:
        return
    style = ET.Element(f"{{{SVG_NS}}}style", {"type": "text/css"})
    rules = []
    for face in faces.values():
        rules.append(
            "@font-face{"
            f"font-family:'{face['family']}';"
            f"font-style:{face['style']};"
            f"font-weight:{face['weight']};"
            f"src:url({face['src']}) format('{face['format']}');"
            "}"
        )
    style.text = "".join(rules)
    root.insert(0, style)


def prefix_svg_references(root: ET.Element, prefix: str) -> None:
    replacements = {}
    for element in root.iter():
        old_id = element.get("id")
        if old_id:
            new_id = f"{prefix}{old_id}"
            replacements[old_id] = new_id
            element.set("id", new_id)

    if not replacements:
        return

    url_pattern = re.compile(r"url\(#([^)]+)\)")
    for element in root.iter():
        for attribute, value in list(element.attrib.items()):
            if value.startswith("#") and value[1:] in replacements:
                element.set(attribute, f"#{replacements[value[1:]]}")
                continue

            def replace_url(match):
                identifier = match.group(1)
                return f"url(#{replacements.get(identifier, identifier)})"

            element.set(attribute, url_pattern.sub(replace_url, value))


def append_searchable_text_layer(group, page, page_number, faces) -> int:
    layer = ET.SubElement(
        group,
        f"{{{SVG_NS}}}g",
        {
            "id": f"pdf-searchable-text-{page_number}",
            "class": "pdf-searchable-text",
            "fill": "#000000",
            "fill-opacity": "0.001",
            "stroke": "none",
            "pointer-events": "all",
            "style": "user-select:text;-webkit-user-select:text",
            "aria-label": f"Selectable text, page {page_number}",
        },
    )

    count = 0
    for block in page.get_text("rawdict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            line_element = ET.SubElement(
                layer,
                f"{{{SVG_NS}}}text",
                {
                    "xml:space": "preserve",
                    "aria-label": "".join(
                        character.get("c", "")
                        for span in line.get("spans", [])
                        for character in span.get("chars", [])
                    ),
                },
            )
            line_has_text = False
            for span in line.get("spans", []):
                characters = [
                    character
                    for character in span.get("chars", [])
                    if character.get("c")
                    and character.get("origin")
                    and character.get("bbox")
                ]
                if not characters:
                    continue

                content = "".join(character["c"] for character in characters)
                first_origin = characters[0]["origin"]
                first_bbox = characters[0]["bbox"]
                last_bbox = characters[-1]["bbox"]
                width = max(0.01, float(last_bbox[2]) - float(first_bbox[0]))
                font_size = float(span.get("size", 12))
                face = faces.get(span.get("font", ""))
                span_element = ET.SubElement(
                    line_element,
                    f"{{{SVG_NS}}}tspan",
                    {
                        "x": f"{float(first_origin[0]):.4f}",
                        "y": f"{float(first_origin[1]):.4f}",
                        "font-size": f"{font_size:.4f}",
                        "font-family": (
                            f"'{face['family']}'" if face else "sans-serif"
                        ),
                        "font-style": face["style"] if face else "normal",
                        "font-weight": face["weight"] if face else "400",
                        "textLength": f"{width:.4f}",
                        "lengthAdjust": "spacingAndGlyphs",
                        "xml:space": "preserve",
                    },
                )
                span_element.text = content
                line_has_text = True

            if line_has_text:
                line_element.tail = "\n"
                count += 1
            else:
                layer.remove(line_element)
    return count


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def converted_svg_matches(svg_path: Path, pdf_hash: str) -> bool:
    try:
        _event, root = next(ET.iterparse(svg_path, events=("start",)))
        return root.get("data-source-pdf-sha256") == pdf_hash
    except (ET.ParseError, OSError, StopIteration):
        return False


def convert_pdf_to_svg(
    source: Path,
    destination: Path,
    page_gap=32.0,
    source_hash=None,
):
    document = pymupdf.open(source)
    if document.page_count == 0:
        document.close()
        raise ValueError(f"Il PDF non contiene pagine: {source}")

    page_sizes = [
        (float(page.rect.width), float(page.rect.height))
        for page in document
    ]
    output_width = max(width for width, _height in page_sizes)
    output_height = (
        sum(height for _width, height in page_sizes)
        + page_gap * (document.page_count - 1)
    )
    outer = ET.Element(
        f"{{{SVG_NS}}}svg",
        {
            "version": "1.1",
            "width": f"{output_width:g}",
            "height": f"{output_height:g}",
            "viewBox": f"0 0 {output_width:g} {output_height:g}",
            "data-source-pdf": source.name,
            "data-source-pdf-sha256": source_hash or file_sha256(source),
            "data-page-count": str(document.page_count),
        },
    )
    embedded_fonts = extract_embedded_fonts(document)
    add_font_styles(outer, embedded_fonts)
    title = ET.SubElement(outer, f"{{{SVG_NS}}}title")
    title.text = source.stem

    current_y = 0.0
    image_count = 0
    text_count = 0
    for page_number, page in enumerate(document, start=1):
        width, height = page_sizes[page_number - 1]
        page_root = ET.fromstring(page.get_svg_image(text_as_path=True))
        prefix_svg_references(page_root, f"p{page_number}_")
        group = ET.SubElement(
            outer,
            f"{{{SVG_NS}}}g",
            {
                "id": f"pdf-page-{page_number}",
                "data-page": str(page_number),
                "transform": f"translate({(output_width - width) / 2:g} {current_y:g})",
            },
        )
        ET.SubElement(
            group,
            f"{{{SVG_NS}}}rect",
            {
                "x": "0",
                "y": "0",
                "width": f"{width:g}",
                "height": f"{height:g}",
                "fill": "white",
            },
        )
        for child in list(page_root):
            group.append(child)

        text_count += append_searchable_text_layer(
            group, page, page_number, embedded_fonts
        )
        image_count += sum(
            1 for element in page_root.iter()
            if local_tag_name(element.tag) == "image"
        )
        current_y += height + page_gap

    document.close()
    destination.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(outer).write(
        destination,
        encoding="utf-8",
        xml_declaration=True,
    )
    return {
        "pages": len(page_sizes),
        "images": image_count,
        "text_elements": text_count,
        "bytes": destination.stat().st_size,
    }


def convert_project_pdfs(force=False):
    """Convert PDFs beside their source; the website itself only sees SVGs."""
    results = []
    if not BASE_DIR.is_dir():
        return results

    pdf_files = sorted(
        (
            path for path in BASE_DIR.rglob("*")
            if path.is_file() and path.suffix.lower() == ".pdf"
        ),
        key=lambda path: path.as_posix().lower(),
    )
    for pdf_path in pdf_files:
        svg_path = pdf_path.with_suffix(".svg")
        pdf_hash = file_sha256(pdf_path)
        if (
            not force
            and svg_path.exists()
            and converted_svg_matches(svg_path, pdf_hash)
        ):
            results.append({
                "pdf": pdf_path,
                "svg": svg_path,
                "status": "aggiornato",
            })
            continue

        temporary_path = svg_path.with_name(svg_path.name + ".tmp")
        try:
            info = convert_pdf_to_svg(
                pdf_path,
                temporary_path,
                source_hash=pdf_hash,
            )
            temporary_path.replace(svg_path)
            results.append({
                "pdf": pdf_path,
                "svg": svg_path,
                "status": "convertito",
                **info,
            })
        except Exception as error:
            if temporary_path.exists():
                temporary_path.unlink()
            results.append({
                "pdf": pdf_path,
                "svg": svg_path,
                "status": "errore",
                "error": str(error),
            })
    return results

def inject_project_runtime(template: str, svg_manifest) -> str:
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
    force_conversion = "--force-pdf-conversion" in sys.argv[1:]
    conversion_results = convert_project_pdfs(force=force_conversion)
    converted_count = sum(
        item["status"] == "convertito" for item in conversion_results
    )
    skipped_count = sum(
        item["status"] == "aggiornato" for item in conversion_results
    )
    conversion_error_count = sum(
        item["status"] == "errore" for item in conversion_results
    )
    print(f"PDF convertiti in SVG: {converted_count}")
    print(f"SVG già aggiornati: {skipped_count}")
    for item in conversion_results:
        if item["status"] == "convertito":
            print(f"  - {item['pdf']} -> {item['svg']}")
        elif item["status"] == "errore":
            print(
                f"  - ERRORE {item['pdf']}: {item['error']}",
                file=sys.stderr,
            )
    if conversion_error_count:
        raise RuntimeError(
            f"Conversione fallita per {conversion_error_count} PDF"
        )

    template = TEMPLATE_FILE.read_text(encoding="utf-8")
    navigation = render_navigation()
    svg_manifest = analyze_svg_images()

    if "{{NAVIGATION}}" not in template:
        raise RuntimeError(
            "Placeholder {{NAVIGATION}} non trovato in site_template.html"
        )

    output = template.replace("{{NAVIGATION}}", navigation)
    output = inject_project_runtime(output, svg_manifest)
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
