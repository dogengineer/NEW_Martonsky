from pathlib import Path
import base64
import binascii
import hashlib
import html
import re
import json
import shutil
import statistics
import sys
import xml.etree.ElementTree as ET
from io import BytesIO
from urllib.parse import quote, unquote_to_bytes

import pymupdf
from PIL import Image
from fontTools.agl import AGL2UV
from fontTools.cffLib import CFFFontSet
from fontTools.fontBuilder import FontBuilder

BASE_DIR = Path("pdf")
TEMPLATE_FILE = Path("site_template.html")
OUTPUT_FILE = Path("index.html")
SUPPORTED_EXTENSIONS = {".html", ".htm", ".svg"}
PDF_CONVERTER_VERSION = "4"
PDF_PREVIEW_MAX_EDGE = 2200
PDF_PREVIEW_WEBP_QUALITY = 84
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

.pdf-link-hotspot{
    fill:#fff;
    fill-opacity:.001;
    stroke:none;
    cursor:pointer;
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

#svgImageLightbox.magnifying{
    cursor:zoom-in;
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
    transform:translate3d(0,0,0) scale(1);
    transform-origin:center center;
    transition:transform .22s cubic-bezier(.2,.75,.2,1);
    will-change:transform;
}

#svgImageLightbox.touch-zooming .svg-image-lightbox-content img{
    transition:none;
}

.svg-mobile-zoom-hint{
    position:absolute;
    left:50%;
    bottom:24px;
    z-index:3;
    padding:8px 12px;
    border-radius:2px;
    background:rgba(17,17,17,.78);
    color:#fff;
    font:400 12px/1.2 Georgia,serif;
    letter-spacing:.02em;
    opacity:0;
    visibility:hidden;
    pointer-events:none;
    transform:translate(-50%,8px);
    transition:opacity .2s ease,transform .2s ease,visibility 0s linear .2s;
}

.svg-mobile-zoom-hint.visible{
    opacity:1;
    visibility:visible;
    transform:translate(-50%,0);
    transition:opacity .2s ease,transform .2s ease,visibility 0s;
}

.svg-image-magnifier{
    position:fixed;
    z-index:2;
    display:block;
    width:220px;
    height:220px;
    box-sizing:border-box;
    border:2px solid #111;
    background-color:#fff;
    background-repeat:no-repeat;
    box-shadow:0 12px 34px rgba(0,0,0,.24);
    opacity:0;
    visibility:hidden;
    pointer-events:none;
    transition:opacity .12s ease,visibility 0s linear .12s;
}

.svg-image-magnifier.visible{
    opacity:1;
    visibility:visible;
    transition:opacity .12s ease,visibility 0s;
}

.svg-image-lightbox-close{
    position:absolute;
    top:18px;
    right:22px;
    z-index:3;
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

    .svg-image-lightbox-content{
        pointer-events:auto;
    }

    .svg-image-lightbox-content img{
        max-width:96vw;
        max-height:90vh;
        touch-action:none;
        user-select:none;
        -webkit-user-drag:none;
    }

    .svg-image-lightbox-close{
        top:8px;
        right:10px;
    }

    .svg-image-magnifier{
        display:none !important;
    }

    .svg-mobile-zoom-hint{
        bottom:18px;
    }
}

@media(prefers-reduced-motion:reduce){
    #svgImageLightbox,
    .svg-image-lightbox-content,
    .svg-image-magnifier,
    .svg-image-lightbox-content img,
    .svg-mobile-zoom-hint{
        transition:none;
    }
}
"""

SVG_ZOOM_HTML = r"""
<div id="svgImageLightbox" role="dialog" aria-modal="true" aria-label="Enlarged image">
    <button class="svg-image-lightbox-close" type="button" aria-label="Close enlarged image">×</button>
    <div class="svg-image-lightbox-content"></div>
    <div class="svg-mobile-zoom-hint" aria-hidden="true">Pizzica per ingrandire</div>
    <div class="svg-image-magnifier" aria-hidden="true"></div>
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
    const magnifier = lightbox.querySelector(".svg-image-magnifier");
    const mobileZoomHint = lightbox.querySelector(".svg-mobile-zoom-hint");
    const magnifierMedia = window.matchMedia(
        "(min-width:801px) and (hover:hover) and (pointer:fine)"
    );
    const touchZoomMedia = window.matchMedia(
        "(max-width:800px), (hover:none), (pointer:coarse)"
    );
    const magnifierZoom = 2.4;
    const maximumTouchZoom = 4;
    const doubleTapZoom = 2.5;
    let previousOverflow = "";
    let activeLightboxImage = null;
    let touchScale = 1;
    let touchTranslateX = 0;
    let touchTranslateY = 0;
    let pinchStart = null;
    let touchGestureMoved = false;
    let touchGestureWasMulti = false;
    let lastTapTime = 0;
    let mobileHintShown = false;
    let mobileHintTimer = 0;
    const touchPointers = new Map();

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

    function collectLayoutItems(svg){
        return [...svg.querySelectorAll("text, image")]
            .filter(element => !element.closest("mask,defs,clipPath,pattern"))
            .map(element => {
                try{
                    const bounds = elementBoundsInRoot(element,svg);
                    const page = element.closest("g[data-page]");
                    return bounds
                        ? {
                            ...bounds,
                            kind:element.tagName.toLowerCase(),
                            pageKey:page?.getAttribute("data-page") || null
                        }
                        : null;
                }
                catch(error){
                    return null;
                }
            })
            .filter(bounds => bounds && bounds.width > 0 && bounds.height > 0)
            .map(bounds => ({
                ...bounds,
                centerX:bounds.x + bounds.width / 2,
                centerY:bounds.y + bounds.height / 2,
                minY:bounds.y,
                maxY:bounds.y + bounds.height
            }));
    }

    function detectDocumentPageBands(items){
        const pageKeys = [...new Set(
            items.map(item => item.pageKey).filter(Boolean)
        )];

        if(pageKeys.length < 2){
            return null;
        }

        const bands = pageKeys
            .map(pageKey => {
                const pageItems = items.filter(item => item.pageKey === pageKey);

                if(pageItems.length < 1){
                    return null;
                }

                return {
                    minY:Math.min(...pageItems.map(item => item.minY)),
                    maxY:Math.max(...pageItems.map(item => item.maxY)),
                    items:pageItems
                };
            })
            .filter(Boolean)
            .sort((first,second) => first.minY - second.minY);

        return bands.length === pageKeys.length ? bands : null;
    }

    function median(values){
        if(values.length === 0){
            return 0;
        }

        const sorted = [...values].sort((first,second) => first - second);
        const middle = Math.floor(sorted.length / 2);
        return sorted.length % 2
            ? sorted[middle]
            : (sorted[middle - 1] + sorted[middle]) / 2;
    }

    /*
     * Find only substantial horizontal corridors that are empty across the
     * whole project. Small spaces between text lines are intentionally
     * ignored. The resulting bands are ordered from top to bottom.
     */
    function detectHorizontalBands(items,contentBounds){
        const intervals = items
            .map(item => ({min:item.minY,max:item.maxY}))
            .sort((first,second) => first.min - second.min);

        if(intervals.length < 4){
            return null;
        }

        const occupied = [];
        intervals.forEach(interval => {
            const current = occupied[occupied.length - 1];

            if(current && interval.min <= current.max){
                current.max = Math.max(current.max,interval.max);
            }
            else{
                occupied.push({...interval});
            }
        });

        const textHeights = items
            .filter(item => item.kind === "text")
            .map(item => item.height)
            .filter(height => height > 0);
        const typicalItemHeight = median(
            textHeights.length
                ? textHeights
                : items.map(item => item.height).filter(height => height > 0)
        );
        const minimumGap = Math.max(
            contentBounds.height * .012,
            typicalItemHeight * 1.5
        );
        const minimumBandHeight = Math.max(
            contentBounds.height * .06,
            typicalItemHeight * 6
        );
        const candidates = [];

        for(let index = 0;index < occupied.length - 1;index++){
            const start = occupied[index].max;
            const end = occupied[index + 1].min;

            if(end - start >= minimumGap){
                candidates.push({
                    start:start,
                    end:end,
                    boundary:(start + end) / 2
                });
            }
        }

        if(candidates.length === 0){
            return null;
        }

        /*
         * Discard separators that would create a tiny strip. This is the
         * main protection against paragraph spacing being mistaken for a
         * second layout row.
         */
        const boundaries = [];
        let previousBoundary = contentBounds.y;

        candidates.forEach((candidate,index) => {
            const nextBoundary = candidates[index + 1]?.boundary ||
                contentBounds.y + contentBounds.height;

            if(
                candidate.boundary - previousBoundary >= minimumBandHeight &&
                nextBoundary - candidate.boundary >= minimumBandHeight
            ){
                boundaries.push(candidate.boundary);
                previousBoundary = candidate.boundary;
            }
        });

        if(boundaries.length === 0){
            return null;
        }

        const edges = [
            contentBounds.y,
            ...boundaries,
            contentBounds.y + contentBounds.height
        ];
        const bands = [];

        for(let index = 0;index < edges.length - 1;index++){
            const bandItems = items.filter(item =>
                item.centerY >= edges[index] &&
                item.centerY < edges[index + 1]
            );

            if(bandItems.length < 2){
                return null;
            }

            bands.push({
                minY:edges[index],
                maxY:edges[index + 1],
                items:bandItems
            });
        }

        return bands.length > 1 ? bands : null;
    }

    function detectColumnsForItems(items,contentBounds){
        if(items.length < 2){
            return null;
        }

        const sortedItems = [...items]
            .sort((first,second) => first.centerX - second.centerX);
        const minimumGap = contentBounds.width * .105;
        const gaps = [];

        for(let index = 0;index < sortedItems.length - 1;index++){
            const gap = sortedItems[index + 1].centerX -
                sortedItems[index].centerX;

            if(gap >= minimumGap){
                gaps.push({
                    size:gap,
                    boundary:(
                        sortedItems[index].centerX +
                        sortedItems[index + 1].centerX
                    ) / 2
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

        sortedItems.forEach(item => {
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

    function detectMobileColumns(svg){
        if(!window.matchMedia("(max-width:800px)").matches){
            return null;
        }

        const preparedLayout = svg.getAttribute("data-mobile-layout");
        if(preparedLayout){
            try{
                const columns = JSON.parse(preparedLayout);
                if(
                    Array.isArray(columns) &&
                    columns.length &&
                    columns.every(column =>
                        Number.isFinite(column.x) &&
                        Number.isFinite(column.y) &&
                        Number.isFinite(column.width) &&
                        Number.isFinite(column.height) &&
                        column.width > 0 &&
                        column.height > 0
                    )
                ){
                    return columns;
                }
            }
            catch(error){
                console.warn("Invalid prepared mobile SVG layout",error);
            }
        }

        if(!svgHasText(svg)){
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
            contentBounds.height <= 0
        ){
            return null;
        }

        const items = collectLayoutItems(svg);

        if(items.length < 4){
            return null;
        }

        const pageBands = detectDocumentPageBands(items);
        const bands = pageBands || detectHorizontalBands(items,contentBounds);

        if(bands){
            const rows = bands.map((band,rowIndex) => {
                const columns = detectColumnsForItems(
                    band.items,
                    contentBounds
                );

                if(!columns || columns.length < 2){
                    if(!pageBands){
                        return null;
                    }

                    const minX = Math.min(...band.items.map(item => item.x));
                    const maxX = Math.max(
                        ...band.items.map(item => item.x + item.width)
                    );
                    const minY = Math.min(...band.items.map(item => item.minY));
                    const maxY = Math.max(...band.items.map(item => item.maxY));
                    const width = maxX - minX;
                    const height = maxY - minY;
                    const horizontalPadding = Math.max(
                        width * .035,
                        contentBounds.width * .006
                    );
                    const verticalPadding = Math.max(
                        height * .018,
                        contentBounds.height * .006
                    );

                    return [{
                        x:minX - horizontalPadding,
                        y:minY - verticalPadding,
                        width:width + horizontalPadding * 2,
                        height:height + verticalPadding * 2,
                        rowIndex:rowIndex,
                        columnIndex:0
                    }];
                }

                return columns.map((column,columnIndex) => ({
                    ...column,
                    rowIndex:rowIndex,
                    columnIndex:columnIndex
                }));
            });

            /* Every detected row must contain a real column layout. */
            if(rows.every(Boolean)){
                return rows.flat();
            }
        }

        /* A tall SVG is split only when real horizontal bands were found. */
        if(contentBounds.width / contentBounds.height < 1.15){
            return null;
        }

        const columns = detectColumnsForItems(items,contentBounds);
        return columns
            ? columns.map((column,columnIndex) => ({
                ...column,
                rowIndex:0,
                columnIndex:columnIndex
            }))
            : null;
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

    function visibleSvgImages(container){
        return [...container.querySelectorAll("image")]
            .filter(image => !image.closest("mask,defs,clipPath,pattern"));
    }

    function activateDeferredImages(container){
        const images = [
            ...container.querySelectorAll("image[data-deferred-href]")
        ];
        const sources = [...new Set(
            images.map(image => image.getAttribute("data-deferred-href"))
                .filter(Boolean)
        )];

        images.forEach(image => {
            const source = image.getAttribute("data-deferred-href");
            if(!source){
                return;
            }
            image.setAttribute("href",source);
            image.setAttributeNS(
                "http://www.w3.org/1999/xlink",
                "xlink:href",
                source
            );
            image.removeAttribute("data-deferred-href");
        });

        if(sources.length === 0){
            return Promise.resolve();
        }

        return Promise.race([
            Promise.all(sources.map(source => new Promise(resolve => {
                const preload = new Image();
                preload.onload = resolve;
                preload.onerror = resolve;
                preload.src = source;
            }))),
            new Promise(resolve => window.setTimeout(resolve,8000))
        ]);
    }

    let deferredColumnObserver = null;

    function observeDeferredColumn(frame){
        if(!frame.querySelector("image[data-deferred-href]")){
            return;
        }

        if(!("IntersectionObserver" in window)){
            activateDeferredImages(frame);
            return;
        }

        if(!deferredColumnObserver){
            deferredColumnObserver = new IntersectionObserver(entries => {
                entries.forEach(entry => {
                    if(entry.isIntersecting){
                        activateDeferredImages(entry.target);
                        deferredColumnObserver.unobserve(entry.target);
                    }
                });
            },{
                rootMargin:"700px 0px",
                threshold:0
            });
        }
        deferredColumnObserver.observe(frame);
    }

    function boundsIntersectColumn(bounds,column){
        return Boolean(
            bounds &&
            bounds.x < column.x + column.width &&
            bounds.x + bounds.width > column.x &&
            bounds.y < column.y + column.height &&
            bounds.y + bounds.height > column.y
        );
    }

    function createMobileColumns(svg,columns){
        const wrapper = document.createElement("div");
        wrapper.className = "mobile-svg-columns";
        wrapper.dataset.columnLayoutDetected = "true";

        const sourceImageBounds = new Map();
        visibleSvgImages(svg).forEach((image,index) => {
            image.setAttribute("data-mobile-image-index",String(index));
            try{
                sourceImageBounds.set(index,elementBoundsInRoot(image,svg));
            }
            catch(error){
                sourceImageBounds.set(index,null);
            }
        });

        const clones = columns.map((column,index) => {
            const frame = document.createElement("div");
            frame.className = "mobile-svg-column-frame";

            const clone = svg.cloneNode(true);
            clone.removeAttribute("width");
            clone.removeAttribute("height");
            clone.removeAttribute("style");
            clone.removeAttribute("data-zoom-ready");
            clone.querySelectorAll(".svg-zoom-hotspot").forEach(node => node.remove());
            visibleSvgImages(clone).forEach(image => {
                const imageIndex = Number(
                    image.getAttribute("data-mobile-image-index")
                );
                if(
                    Number.isFinite(imageIndex) &&
                    !boundsIntersectColumn(
                        sourceImageBounds.get(imageIndex),
                        column
                    )
                ){
                    image.remove();
                }
            });
            makeIdsUnique(
                clone,
                "mobile-row-" + column.rowIndex +
                "-column-" + column.columnIndex
            );
            clone.setAttribute(
                "viewBox",
                [column.x,column.y,column.width,column.height].join(" ")
            );
            clone.setAttribute("preserveAspectRatio","xMidYMin meet");
            clone.setAttribute(
                "aria-label",
                "Project row " + (column.rowIndex + 1) +
                ", column " + (column.columnIndex + 1)
            );
            frame.appendChild(clone);
            wrapper.appendChild(frame);
            if(index > 0){
                observeDeferredColumn(frame);
            }
            return clone;
        });

        viewer.classList.remove("mobile-svg-scroll");
        viewer.scrollLeft = 0;
        svg.replaceWith(wrapper);
        /* Observe after insertion: some browsers do not dispatch
           IntersectionObserver callbacks for detached elements. */
        [...wrapper.querySelectorAll(".mobile-svg-column-frame")]
            .slice(1)
            .forEach(observeDeferredColumn);
        return clones;
    }

    function clamp(value,minimum,maximum){
        return Math.min(Math.max(value,minimum),maximum);
    }

    function touchPointDistance(first,second){
        return Math.hypot(
            second.x - first.x,
            second.y - first.y
        );
    }

    function touchPointMiddle(first,second){
        return {
            x:(first.x + second.x) / 2,
            y:(first.y + second.y) / 2
        };
    }

    function constrainTouchTranslation(){
        if(!activeLightboxImage || touchScale <= 1){
            touchTranslateX = 0;
            touchTranslateY = 0;
            return;
        }

        const horizontalMargin = 20;
        const verticalMargin = 20;
        const maximumX = Math.max(
            0,
            (activeLightboxImage.clientWidth * touchScale -
                window.innerWidth + horizontalMargin * 2) / 2
        );
        const maximumY = Math.max(
            0,
            (activeLightboxImage.clientHeight * touchScale -
                window.innerHeight + verticalMargin * 2) / 2
        );

        touchTranslateX = clamp(touchTranslateX,-maximumX,maximumX);
        touchTranslateY = clamp(touchTranslateY,-maximumY,maximumY);
    }

    function applyTouchTransform(animated = false){
        if(!activeLightboxImage){
            return;
        }

        constrainTouchTranslation();
        lightbox.classList.toggle("touch-zooming",!animated);
        activeLightboxImage.style.transform =
            "translate3d(" + touchTranslateX + "px," +
            touchTranslateY + "px,0) scale(" + touchScale + ")";
    }

    function resetTouchZoom(){
        touchPointers.clear();
        pinchStart = null;
        touchScale = 1;
        touchTranslateX = 0;
        touchTranslateY = 0;
        touchGestureMoved = false;
        touchGestureWasMulti = false;
        lastTapTime = 0;
        lightbox.classList.remove("touch-zooming");

        if(activeLightboxImage){
            activeLightboxImage.style.transform =
                "translate3d(0,0,0) scale(1)";
        }
    }

    function hideMobileZoomHint(){
        window.clearTimeout(mobileHintTimer);
        mobileZoomHint.classList.remove("visible");
    }

    function showMobileZoomHint(){
        if(!touchZoomMedia.matches || mobileHintShown){
            return;
        }

        mobileHintShown = true;
        mobileZoomHint.classList.add("visible");
        mobileHintTimer = window.setTimeout(hideMobileZoomHint,1800);
    }

    function toggleTouchZoom(clientX,clientY){
        if(!activeLightboxImage || !touchZoomMedia.matches){
            return;
        }

        if(touchScale > 1.05){
            touchScale = 1;
            touchTranslateX = 0;
            touchTranslateY = 0;
        }
        else{
            touchScale = doubleTapZoom;
            touchTranslateX =
                (window.innerWidth / 2 - clientX) * (touchScale - 1);
            touchTranslateY =
                (window.innerHeight / 2 - clientY) * (touchScale - 1);
        }

        applyTouchTransform(true);
    }

    function beginTouchZoom(event){
        if(
            !touchZoomMedia.matches ||
            !activeLightboxImage ||
            event.target !== activeLightboxImage ||
            event.pointerType === "mouse"
        ){
            return;
        }

        event.preventDefault();
        hideMobileZoomHint();
        activeLightboxImage.setPointerCapture?.(event.pointerId);
        touchPointers.set(event.pointerId,{
            x:event.clientX,
            y:event.clientY
        });
        touchGestureMoved = false;
        lightbox.classList.add("touch-zooming");

        if(touchPointers.size === 2){
            touchGestureWasMulti = true;
            const [first,second] = [...touchPointers.values()];
            pinchStart = {
                distance:Math.max(touchPointDistance(first,second),1),
                middle:touchPointMiddle(first,second),
                scale:touchScale,
                translateX:touchTranslateX,
                translateY:touchTranslateY
            };
        }
    }

    function moveTouchZoom(event){
        const previousPoint = touchPointers.get(event.pointerId);
        if(!previousPoint || !activeLightboxImage){
            return;
        }

        event.preventDefault();
        const currentPoint = {x:event.clientX,y:event.clientY};
        touchPointers.set(event.pointerId,currentPoint);

        if(touchPointers.size >= 2 && pinchStart){
            const [first,second] = [...touchPointers.values()];
            const currentMiddle = touchPointMiddle(first,second);
            const distance = Math.max(touchPointDistance(first,second),1);
            const nextScale = clamp(
                pinchStart.scale * distance / pinchStart.distance,
                1,
                maximumTouchZoom
            );
            const scaleRatio = nextScale / pinchStart.scale;
            const viewportCenterX = window.innerWidth / 2;
            const viewportCenterY = window.innerHeight / 2;

            touchScale = nextScale;
            touchTranslateX = currentMiddle.x - viewportCenterX -
                scaleRatio * (
                    pinchStart.middle.x - viewportCenterX -
                    pinchStart.translateX
                );
            touchTranslateY = currentMiddle.y - viewportCenterY -
                scaleRatio * (
                    pinchStart.middle.y - viewportCenterY -
                    pinchStart.translateY
                );
            touchGestureMoved = true;
            applyTouchTransform();
            return;
        }

        if(touchPointers.size === 1 && touchScale > 1){
            const deltaX = currentPoint.x - previousPoint.x;
            const deltaY = currentPoint.y - previousPoint.y;
            touchTranslateX += deltaX;
            touchTranslateY += deltaY;
            touchGestureMoved = touchGestureMoved ||
                Math.abs(deltaX) + Math.abs(deltaY) > 2;
            applyTouchTransform();
        }
    }

    function endTouchZoom(event){
        if(!touchPointers.has(event.pointerId)){
            return;
        }

        event.preventDefault();
        const mayBeTap =
            touchPointers.size === 1 &&
            !touchGestureMoved &&
            !touchGestureWasMulti;
        touchPointers.delete(event.pointerId);

        if(touchPointers.size < 2){
            pinchStart = null;
        }

        if(touchPointers.size === 0){
            lightbox.classList.remove("touch-zooming");
            constrainTouchTranslation();
            applyTouchTransform(true);

            if(mayBeTap){
                const now = performance.now();
                if(now - lastTapTime < 320){
                    toggleTouchZoom(event.clientX,event.clientY);
                    lastTapTime = 0;
                }
                else{
                    lastTapTime = now;
                }
            }

            touchGestureWasMulti = false;
            touchGestureMoved = false;
        }
    }

    function closeLightbox(){
        hideMagnifier();
        hideMobileZoomHint();
        resetTouchZoom();
        lightbox.classList.remove("open");
        document.body.style.overflow = previousOverflow;
        window.setTimeout(() => {
            if(!lightbox.classList.contains("open")){
                lightboxContent.replaceChildren();
                activeLightboxImage = null;
            }
        },230);
    }

    function imageSource(image){
        if(typeof image === "string"){
            return image;
        }

        return (
            image.getAttribute("data-lightbox-href") ||
            image.getAttribute("src") ||
            image.getAttribute("href") ||
            image.getAttributeNS("http://www.w3.org/1999/xlink","href") ||
            ""
        );
    }

    function hideMagnifier(){
        magnifier.classList.remove("visible");
        lightbox.classList.remove("magnifying");
    }

    function updateMagnifier(event){
        if(
            !magnifierMedia.matches ||
            !lightbox.classList.contains("open") ||
            event.target.closest?.(".svg-image-lightbox-close")
        ){
            hideMagnifier();
            return;
        }

        const enlargedImage = lightboxContent.querySelector("img");

        if(!enlargedImage || !enlargedImage.complete){
            hideMagnifier();
            return;
        }

        const imageRect = enlargedImage.getBoundingClientRect();
        const insideImage =
            event.clientX >= imageRect.left &&
            event.clientX <= imageRect.right &&
            event.clientY >= imageRect.top &&
            event.clientY <= imageRect.bottom;

        if(!insideImage || imageRect.width <= 0 || imageRect.height <= 0){
            hideMagnifier();
            return;
        }

        const viewportMargin = 8;
        const maximumLensSide = Math.max(
            220,
            Math.min(window.innerWidth,window.innerHeight) - viewportMargin * 2
        );
        const lensSide = Math.min(
            Math.max(220,imageRect.height * .8),
            maximumLensSide
        );
        const lensWidth = lensSide;
        const lensHeight = lensSide;

        magnifier.style.width = lensSide + "px";
        magnifier.style.height = lensSide + "px";
        const left = Math.min(
            Math.max(event.clientX - lensWidth / 2,viewportMargin),
            window.innerWidth - lensWidth - viewportMargin
        );
        const top = Math.min(
            Math.max(event.clientY - lensHeight / 2,viewportMargin),
            window.innerHeight - lensHeight - viewportMargin
        );
        const imageX = event.clientX - imageRect.left;
        const imageY = event.clientY - imageRect.top;
        const cursorInLensX = event.clientX - left;
        const cursorInLensY = event.clientY - top;
        const source = enlargedImage.currentSrc || enlargedImage.src;

        magnifier.style.left = left + "px";
        magnifier.style.top = top + "px";
        magnifier.style.backgroundImage = "url(" + JSON.stringify(source) + ")";
        magnifier.style.backgroundSize =
            imageRect.width * magnifierZoom + "px " +
            imageRect.height * magnifierZoom + "px";
        magnifier.style.backgroundPosition =
            cursorInLensX - imageX * magnifierZoom + "px " +
            (cursorInLensY - imageY * magnifierZoom) + "px";
        lightbox.classList.add("magnifying");
        magnifier.classList.add("visible");
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
        activeLightboxImage = enlargedImage;
        resetTouchZoom();
        previousOverflow = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        lightbox.classList.add("open");
        showMobileZoomHint();
        closeButton.focus({preventScroll:true});
    }

    window.openProjectImage = openLightbox;

    function promotePdfLinks(svg,hotspots){
        if(!hotspots.length){
            return;
        }

        const namespace = "http://www.w3.org/2000/svg";
        const xlinkNamespace = "http://www.w3.org/1999/xlink";
        const layer = document.createElementNS(namespace,"g");
        layer.setAttribute("class","pdf-link-overlay-layer");
        layer.setAttribute("aria-label","Clickable project links");
        const viewBox = svg.viewBox.baseVal;

        hotspots.forEach((hotspot,index) => {
            const sourceAnchor = hotspot.closest("a");
            const href = sourceAnchor && (
                sourceAnchor.getAttribute("href") ||
                sourceAnchor.getAttributeNS(xlinkNamespace,"href")
            );

            if(!href || !/^(?:https?:|mailto:)/i.test(href)){
                return;
            }

            let bounds;
            try{
                bounds = elementBoundsInRoot(hotspot,svg);
            }
            catch(error){
                console.warn("Unable to prepare PDF link",error);
                return;
            }

            if(!bounds || bounds.width <= 0 || bounds.height <= 0){
                return;
            }

            const intersectsViewBox =
                bounds.x < viewBox.x + viewBox.width &&
                bounds.x + bounds.width > viewBox.x &&
                bounds.y < viewBox.y + viewBox.height &&
                bounds.y + bounds.height > viewBox.y;

            if(!intersectsViewBox){
                return;
            }

            const anchor = document.createElementNS(namespace,"a");
            anchor.setAttribute("href",href);
            anchor.setAttributeNS(xlinkNamespace,"xlink:href",href);
            anchor.setAttribute("target","_blank");
            anchor.setAttribute("rel","noopener noreferrer");
            anchor.setAttribute("aria-label","Open link: " + href);

            const rect = document.createElementNS(namespace,"rect");
            rect.setAttribute("x",bounds.x);
            rect.setAttribute("y",bounds.y);
            rect.setAttribute("width",bounds.width);
            rect.setAttribute("height",bounds.height);
            rect.setAttribute("class","pdf-link-hotspot pdf-link-overlay");
            rect.setAttribute("tabindex","0");
            rect.setAttribute("role","link");
            anchor.appendChild(rect);
            layer.appendChild(anchor);

            /* Only the root-coordinate copy handles pointer input. */
            sourceAnchor.setAttribute("pointer-events","none");
            sourceAnchor.setAttribute("aria-hidden","true");
        });

        if(layer.childElementCount){
            svg.appendChild(layer);
        }
    }

    function prepareSvg(svg){
        if(svg.dataset.zoomReady === "true"){
            return;
        }

        svg.dataset.zoomReady = "true";
        const linkHotspots = [
            ...svg.querySelectorAll(".pdf-link-hotspot")
        ];
        const images = [...svg.querySelectorAll("image")]
            .filter(image => !image.closest("mask,defs,clipPath,pattern"));
        const hasText = svgHasText(svg);

        /* A full-page SVG containing only an image does not need a lightbox. */
        if(!hasText){
            promotePdfLinks(svg,linkHotspots);
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

        /* Image hotspots are appended to the root SVG and would otherwise
           cover PDF annotations. Re-create the links in root coordinates so
           they always remain the uppermost interactive layer. */
        promotePdfLinks(svg,linkHotspots);
    }

    function nextFrame(){
        return new Promise(resolve =>
            window.requestAnimationFrame(resolve)
        );
    }

    async function prepareCurrentSvg(){
        const existingColumns =
            viewer.querySelector(".mobile-svg-columns");

        if(existingColumns){
            const columnSvgs = [
                ...existingColumns.querySelectorAll(
                    ":scope > .mobile-svg-column-frame > svg"
                )
            ];
            if(columnSvgs[0]){
                await activateDeferredImages(columnSvgs[0]);
            }
            await nextFrame();
            columnSvgs.forEach(prepareSvg);
            await nextFrame();
            return;
        }

        const svg = viewer.querySelector("svg");
        if(!svg){
            return;
        }

        await nextFrame();
        const columns = detectMobileColumns(svg);

        if(columns){
            const columnSvgs = createMobileColumns(svg,columns);
            if(columnSvgs[0]){
                await activateDeferredImages(columnSvgs[0]);
            }
            await nextFrame();
            columnSvgs.forEach(prepareSvg);
        }
        else{
            await activateDeferredImages(svg);
            prepareSvg(svg);
        }

        await nextFrame();
    }

    let activePreparation = null;
    let fallbackTimer = 0;

    window.prepareProjectSvgLayout = function(){
        window.clearTimeout(fallbackTimer);

        if(activePreparation){
            return activePreparation;
        }

        activePreparation = prepareCurrentSvg().finally(() => {
            window.clearTimeout(fallbackTimer);
            activePreparation = null;
        });
        return activePreparation;
    };

    /* Compatibility fallback for pages generated with an older template.
       The current template calls prepareProjectSvgLayout() directly and waits
       for it before revealing the project. */
    const observer = new MutationObserver(() => {
        window.clearTimeout(fallbackTimer);
        fallbackTimer = window.setTimeout(() => {
            if(
                viewer.querySelector("svg") &&
                !viewer.classList.contains("content-loading")
            ){
                window.prepareProjectSvgLayout();
            }
        },80);
    });
    observer.observe(viewer,{childList:true,subtree:false});

    closeButton.addEventListener("click",closeLightbox);
    lightboxContent.addEventListener("pointerdown",beginTouchZoom);
    lightboxContent.addEventListener("pointermove",moveTouchZoom);
    lightboxContent.addEventListener("pointerup",endTouchZoom);
    lightboxContent.addEventListener("pointercancel",event => {
        touchGestureMoved = true;
        endTouchZoom(event);
    });
    lightbox.addEventListener("mousemove",updateMagnifier);
    lightbox.addEventListener("mouseleave",hideMagnifier);
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
    window.addEventListener("resize",() => {
        if(lightbox.classList.contains("open") && touchScale > 1){
            applyTouchTransform(true);
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


def svg_content_images(root: ET.Element):
    """Return visible content images, excluding mask/definition resources."""
    parents = {
        child: parent
        for parent in root.iter()
        for child in parent
    }
    technical_ancestors = {"mask", "defs", "clippath", "pattern"}
    result = []
    for element in root.iter():
        if local_tag_name(element.tag) != "image":
            continue
        ancestor = parents.get(element)
        is_technical = False
        while ancestor is not None:
            if local_tag_name(ancestor.tag) in technical_ancestors:
                is_technical = True
                break
            ancestor = parents.get(ancestor)
        if not is_technical:
            result.append(element)
    return result

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
            images = svg_content_images(root)
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


def append_pdf_link_layer(group, page, page_number) -> int:
    """Preserve safe external PDF hyperlinks as clickable SVG regions."""
    layer = ET.SubElement(
        group,
        f"{{{SVG_NS}}}g",
        {
            "id": f"pdf-link-layer-{page_number}",
            "class": "pdf-link-layer",
            "aria-label": f"Links, page {page_number}",
        },
    )

    count = 0
    for link in page.get_links():
        uri = (link.get("uri") or "").strip()
        if not re.match(r"^(?:https?://|mailto:)", uri, flags=re.I):
            continue

        rectangle_value = link.get("from")
        if rectangle_value is None:
            continue
        rectangle = pymupdf.Rect(rectangle_value)
        if rectangle.is_empty or rectangle.is_infinite:
            continue

        anchor = ET.SubElement(
            layer,
            f"{{{SVG_NS}}}a",
            {
                "id": f"pdf-link-{page_number}-{count + 1}",
                "href": uri,
                f"{{{XLINK_NS}}}href": uri,
                "target": "_blank",
                "rel": "noopener noreferrer",
                "aria-label": f"Open link: {uri}",
            },
        )
        title = ET.SubElement(anchor, f"{{{SVG_NS}}}title")
        title.text = uri
        ET.SubElement(
            anchor,
            f"{{{SVG_NS}}}rect",
            {
                "x": f"{float(rectangle.x0):.4f}",
                "y": f"{float(rectangle.y0):.4f}",
                "width": f"{float(rectangle.width):.4f}",
                "height": f"{float(rectangle.height):.4f}",
                "class": "pdf-link-hotspot",
                "fill": "#ffffff",
                "fill-opacity": "0.001",
                "stroke": "none",
                "pointer-events": "all",
                "style": "cursor:pointer",
                "tabindex": "0",
                "role": "link",
            },
        )
        count += 1

    if count == 0:
        group.remove(layer)
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
        assets_directory = root.get("data-assets-directory")
        assets_are_ready = (
            not assets_directory or
            (svg_path.parent / assets_directory).is_dir()
        )
        return (
            root.get("data-source-pdf-sha256") == pdf_hash
            and root.get("data-pdf-converter-version")
            == PDF_CONVERTER_VERSION
            and assets_are_ready
        )
    except (ET.ParseError, OSError, StopIteration):
        return False


def decode_image_data_uri(value: str):
    """Decode an SVG image data URI and return its MIME type and bytes."""
    if not value.startswith("data:image/") or "," not in value:
        return None
    header, payload = value.split(",", 1)
    mime = header[5:].split(";", 1)[0].lower()
    try:
        raw_data = (
            base64.b64decode(payload, validate=False)
            if ";base64" in header.lower()
            else unquote_to_bytes(payload)
        )
    except (ValueError, binascii.Error):
        return None
    return mime, raw_data


def image_extension(mime: str) -> str:
    return {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/tiff": ".tif",
        "image/jp2": ".jp2",
        "image/jpx": ".jp2",
    }.get(mime, ".img")


def asset_url(prefix: str, filename: str) -> str:
    return quote(f"{prefix}/{filename}", safe="/._-")


def save_full_image_asset(
    raw_data: bytes,
    mime: str,
    asset_directory: Path,
    url_prefix: str,
    state,
) -> str:
    digest = hashlib.sha256(raw_data).hexdigest()[:16]
    cache_key = ("full", digest, mime)
    if cache_key in state["cache"]:
        return state["cache"][cache_key]

    filename = f"image_{digest}_full{image_extension(mime)}"
    output_path = asset_directory / filename
    if not output_path.exists():
        output_path.write_bytes(raw_data)
    state["full_bytes"] += len(raw_data)
    url = asset_url(url_prefix, filename)
    state["cache"][cache_key] = url
    return url


def save_preview_image_asset(
    raw_data: bytes,
    mime: str,
    asset_directory: Path,
    url_prefix: str,
    state,
) -> str:
    digest = hashlib.sha256(raw_data).hexdigest()[:16]
    cache_key = ("preview", digest, mime)
    if cache_key in state["cache"]:
        return state["cache"][cache_key]

    filename = f"image_{digest}_preview.webp"
    output_path = asset_directory / filename
    with Image.open(BytesIO(raw_data)) as source_image:
        source_image.load()
        source_image = source_image.copy()
        original_width, original_height = source_image.size
        if max(source_image.size) > PDF_PREVIEW_MAX_EDGE:
            source_image.thumbnail(
                (PDF_PREVIEW_MAX_EDGE, PDF_PREVIEW_MAX_EDGE),
                Image.Resampling.LANCZOS,
            )

        has_alpha = (
            "A" in source_image.getbands() or
            "transparency" in source_image.info
        )
        target_mode = "RGBA" if has_alpha else "RGB"
        converted = source_image.convert(target_mode)

        colour_sample = converted.convert("RGB")
        colour_sample.thumbnail((256, 256), Image.Resampling.BILINEAR)
        colours = colour_sample.getcolors(maxcolors=512)
        looks_like_graphic = colours is not None and len(colours) <= 384

        save_options = {"format": "WEBP", "method": 6}
        if looks_like_graphic:
            save_options["lossless"] = True
        else:
            save_options["quality"] = PDF_PREVIEW_WEBP_QUALITY
        converted.save(output_path, **save_options)

    state["preview_bytes"] += output_path.stat().st_size
    state["original_pixels"] += original_width * original_height
    state["cache"][cache_key] = asset_url(url_prefix, filename)
    return state["cache"][cache_key]


def externalize_svg_images(
    root: ET.Element,
    asset_directory: Path,
    url_prefix: str,
    state,
) -> int:
    """Replace embedded raster payloads with preview and on-demand assets."""
    converted_count = 0
    for image in (
        element for element in root.iter()
        if local_tag_name(element.tag) == "image"
    ):
        href = (
            image.get("href") or
            image.get(f"{{{XLINK_NS}}}href") or
            ""
        )
        decoded = decode_image_data_uri(href)
        if decoded:
            mime, raw_data = decoded
            try:
                preview_url = save_preview_image_asset(
                    raw_data,
                    mime,
                    asset_directory,
                    url_prefix,
                    state,
                )
                full_url = save_full_image_asset(
                    raw_data,
                    mime,
                    asset_directory,
                    url_prefix,
                    state,
                )
            except Exception as error:
                print(
                    f"ATTENZIONE: anteprima immagine non generata: {error}",
                    file=sys.stderr,
                )
            else:
                image.set("href", preview_url)
                image.set(f"{{{XLINK_NS}}}href", preview_url)
                image.set("data-preview-asset", "true")
                if not image.get("data-lightbox-href"):
                    image.set("data-lightbox-href", full_url)
                converted_count += 1

        lightbox_source = image.get("data-lightbox-href", "")
        lightbox_decoded = decode_image_data_uri(lightbox_source)
        if lightbox_decoded:
            mime, raw_data = lightbox_decoded
            try:
                image.set(
                    "data-lightbox-href",
                    save_full_image_asset(
                        raw_data,
                        mime,
                        asset_directory,
                        url_prefix,
                        state,
                    ),
                )
            except OSError as error:
                print(
                    f"ATTENZIONE: sorgente zoom non esportata: {error}",
                    file=sys.stderr,
                )
    return converted_count


def add_pdf_lightbox_sources(
    document: pymupdf.Document,
    page: pymupdf.Page,
    page_root: ET.Element,
) -> tuple[int, int]:
    """Attach flattened sources to masked images used by the lightbox."""
    visible_images = svg_content_images(page_root)
    pdf_images = list(page.get_images(full=True))
    used_pdf_images = set()
    composite_count = 0

    for svg_image in visible_images:
        try:
            svg_width = round(float(svg_image.get("width", "0")))
            svg_height = round(float(svg_image.get("height", "0")))
        except ValueError:
            continue

        match_index = next((
            index
            for index, image in enumerate(pdf_images)
            if index not in used_pdf_images
            and int(image[2]) == svg_width
            and int(image[3]) == svg_height
        ), None)
        if match_index is None:
            continue

        used_pdf_images.add(match_index)
        xref, smask = int(pdf_images[match_index][0]), int(pdf_images[match_index][1])
        if not smask:
            continue

        try:
            mask = pymupdf.Pixmap(document, smask)
            mask_samples = mask.samples
            # Uniform opaque masks do not change the source image and would
            # only duplicate several megabytes inside the generated SVG.
            if not mask_samples or min(mask_samples) == max(mask_samples) == 255:
                continue

            base = pymupdf.Pixmap(document, xref)
            composite = pymupdf.Pixmap(base, mask)
            png_data = composite.tobytes("png")
            svg_image.set(
                "data-lightbox-href",
                "data:image/png;base64,"
                + base64.b64encode(png_data).decode("ascii"),
            )
            svg_image.set("data-lightbox-composite", "true")
            composite_count += 1
        except Exception as error:
            print(
                f"ATTENZIONE: immagine mascherata {xref} non composta: {error}",
                file=sys.stderr,
            )

    return len(visible_images), composite_count


def pdf_page_layout_items(page, offset_x: float, offset_y: float):
    """Collect the same text/image geometry used by the mobile JS fallback."""
    items = []
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            bbox = line.get("bbox")
            if not bbox:
                continue
            x0, y0, x1, y1 = map(float, bbox)
            if x1 <= x0 or y1 <= y0:
                continue
            items.append({
                "x": x0 + offset_x,
                "y": y0 + offset_y,
                "width": x1 - x0,
                "height": y1 - y0,
                "kind": "text",
            })

    for image in page.get_image_info():
        bbox = image.get("bbox")
        if not bbox:
            continue
        x0, y0, x1, y1 = map(float, bbox)
        if x1 <= x0 or y1 <= y0:
            continue
        items.append({
            "x": x0 + offset_x,
            "y": y0 + offset_y,
            "width": x1 - x0,
            "height": y1 - y0,
            "kind": "image",
        })

    for item in items:
        item["center_x"] = item["x"] + item["width"] / 2
        item["center_y"] = item["y"] + item["height"] / 2
        item["min_y"] = item["y"]
        item["max_y"] = item["y"] + item["height"]
    return items


def layout_ranges_overlap(first, second) -> bool:
    overlap = min(first["max_y"], second["max_y"]) - max(
        first["min_y"], second["min_y"]
    )
    smaller_height = min(
        first["max_y"] - first["min_y"],
        second["max_y"] - second["min_y"],
    )
    return smaller_height > 0 and overlap / smaller_height >= 0.18


def detect_layout_columns(items, content_width: float, content_height: float):
    if len(items) < 2:
        return None
    sorted_items = sorted(items, key=lambda item: item["center_x"])
    minimum_gap = content_width * 0.105
    gaps = []
    for first, second in zip(sorted_items, sorted_items[1:]):
        gap = second["center_x"] - first["center_x"]
        if gap >= minimum_gap:
            gaps.append({
                "size": gap,
                "boundary": (first["center_x"] + second["center_x"]) / 2,
            })
    if not gaps:
        return None

    largest_gap = max(gap["size"] for gap in gaps)
    selected = sorted(
        sorted(
            (gap for gap in gaps if gap["size"] >= largest_gap * 0.68),
            key=lambda gap: gap["size"],
            reverse=True,
        )[:3],
        key=lambda gap: gap["boundary"],
    )
    boundaries = [gap["boundary"] for gap in selected]
    groups = [[] for _index in range(len(boundaries) + 1)]
    for item in sorted_items:
        group_index = next(
            (
                index for index, boundary in enumerate(boundaries)
                if item["center_x"] < boundary
            ),
            len(groups) - 1,
        )
        groups[group_index].append(item)
    if any(not group for group in groups):
        return None

    ranges = [
        {
            "min_y": min(item["min_y"] for item in group),
            "max_y": max(item["max_y"] for item in group),
        }
        for group in groups
    ]
    if any(
        not layout_ranges_overlap(first, second)
        for first, second in zip(ranges, ranges[1:])
    ):
        return None

    columns = []
    for group in groups:
        min_x = min(item["x"] for item in group)
        max_x = max(item["x"] + item["width"] for item in group)
        min_y = min(item["min_y"] for item in group)
        max_y = max(item["max_y"] for item in group)
        width = max_x - min_x
        height = max_y - min_y
        horizontal_padding = max(width * 0.035, content_width * 0.006)
        vertical_padding = max(height * 0.018, content_height * 0.006)
        columns.append({
            "x": min_x - horizontal_padding,
            "y": min_y - vertical_padding,
            "width": width + horizontal_padding * 2,
            "height": height + vertical_padding * 2,
        })
    if any(column["width"] < content_width * 0.16 for column in columns):
        return None
    return columns


def detect_layout_horizontal_bands(items, content_height: float):
    if len(items) < 4:
        return None
    intervals = sorted(
        ({"min": item["min_y"], "max": item["max_y"]} for item in items),
        key=lambda interval: interval["min"],
    )
    occupied = []
    for interval in intervals:
        if occupied and interval["min"] <= occupied[-1]["max"]:
            occupied[-1]["max"] = max(occupied[-1]["max"], interval["max"])
        else:
            occupied.append(dict(interval))

    text_heights = [
        item["height"] for item in items
        if item["kind"] == "text" and item["height"] > 0
    ]
    all_heights = [item["height"] for item in items if item["height"] > 0]
    typical_height = statistics.median(text_heights or all_heights)
    minimum_gap = max(content_height * 0.012, typical_height * 1.5)
    minimum_band_height = max(content_height * 0.06, typical_height * 6)
    candidates = []
    for first, second in zip(occupied, occupied[1:]):
        start, end = first["max"], second["min"]
        if end - start >= minimum_gap:
            candidates.append((start + end) / 2)
    if not candidates:
        return None

    boundaries = []
    previous = 0.0
    for index, boundary in enumerate(candidates):
        next_boundary = (
            candidates[index + 1]
            if index + 1 < len(candidates)
            else content_height
        )
        if (
            boundary - previous >= minimum_band_height and
            next_boundary - boundary >= minimum_band_height
        ):
            boundaries.append(boundary)
            previous = boundary
    if not boundaries:
        return None

    edges = [0.0, *boundaries, content_height]
    bands = []
    for start, end in zip(edges, edges[1:]):
        band_items = [
            item for item in items
            if start <= item["center_y"] < end
        ]
        if len(band_items) < 2:
            return None
        bands.append(band_items)
    return bands if len(bands) > 1 else None


def mobile_layout_from_pdf(document, page_sizes, output_width, output_height, page_gap):
    page_items = []
    current_y = 0.0
    for page, (width, height) in zip(document, page_sizes):
        offset_x = (output_width - width) / 2
        items = pdf_page_layout_items(page, offset_x, current_y)
        page_items.append(items)
        current_y += height + page_gap

    all_items = [item for items in page_items for item in items]
    if len(all_items) < 4:
        return None

    rows = page_items if len(page_items) > 1 else (
        detect_layout_horizontal_bands(all_items, output_height)
    )
    result = []
    if rows:
        for row_index, items in enumerate(rows):
            columns = detect_layout_columns(items, output_width, output_height)
            if not columns:
                if len(page_items) == 1:
                    return None
                min_x = min(item["x"] for item in items)
                max_x = max(item["x"] + item["width"] for item in items)
                min_y = min(item["min_y"] for item in items)
                max_y = max(item["max_y"] for item in items)
                width = max_x - min_x
                height = max_y - min_y
                horizontal_padding = max(width * 0.035, output_width * 0.006)
                vertical_padding = max(height * 0.018, output_height * 0.006)
                columns = [{
                    "x": min_x - horizontal_padding,
                    "y": min_y - vertical_padding,
                    "width": width + horizontal_padding * 2,
                    "height": height + vertical_padding * 2,
                }]
            for column_index, column in enumerate(columns):
                result.append({
                    **column,
                    "rowIndex": row_index,
                    "columnIndex": column_index,
                })
        return result

    if output_width / output_height < 1.15:
        return None
    columns = detect_layout_columns(all_items, output_width, output_height)
    if not columns:
        return None
    return [
        {**column, "rowIndex": 0, "columnIndex": index}
        for index, column in enumerate(columns)
    ]


def convert_pdf_to_svg(
    source: Path,
    destination: Path,
    page_gap=32.0,
    source_hash=None,
    asset_directory=None,
    asset_url_prefix=None,
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
    asset_directory = Path(asset_directory) if asset_directory else (
        destination.parent / f"{destination.stem}_assets"
    )
    asset_url_prefix = asset_url_prefix or asset_directory.name
    asset_directory.mkdir(parents=True, exist_ok=True)
    asset_state = {
        "cache": {},
        "preview_bytes": 0,
        "full_bytes": 0,
        "original_pixels": 0,
    }
    outer = ET.Element(
        f"{{{SVG_NS}}}svg",
        {
            "version": "1.1",
            "width": f"{output_width:g}",
            "height": f"{output_height:g}",
            "viewBox": f"0 0 {output_width:g} {output_height:g}",
            "data-source-pdf": source.name,
            "data-source-pdf-sha256": source_hash or file_sha256(source),
            "data-pdf-converter-version": PDF_CONVERTER_VERSION,
            "data-page-count": str(document.page_count),
            "data-assets-directory": asset_url_prefix,
        },
    )
    mobile_layout = mobile_layout_from_pdf(
        document,
        page_sizes,
        output_width,
        output_height,
        page_gap,
    )
    if mobile_layout:
        compact_layout = [
            {
                key:(round(value, 3) if isinstance(value, float) else value)
                for key, value in column.items()
            }
            for column in mobile_layout
        ]
        outer.set(
            "data-mobile-layout",
            json.dumps(compact_layout, separators=(",", ":")),
        )
    embedded_fonts = extract_embedded_fonts(document)
    add_font_styles(outer, embedded_fonts)
    title = ET.SubElement(outer, f"{{{SVG_NS}}}title")
    title.text = source.stem

    current_y = 0.0
    image_count = 0
    external_image_count = 0
    text_count = 0
    link_count = 0
    for page_number, page in enumerate(document, start=1):
        width, height = page_sizes[page_number - 1]
        page_root = ET.fromstring(page.get_svg_image(text_as_path=True))
        page_image_count, _composite_count = add_pdf_lightbox_sources(
            document,
            page,
            page_root,
        )
        external_image_count += externalize_svg_images(
            page_root,
            asset_directory,
            asset_url_prefix,
            asset_state,
        )
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
        link_count += append_pdf_link_layer(group, page, page_number)
        image_count += page_image_count
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
        "external_images": external_image_count,
        "text_elements": text_count,
        "links": link_count,
        "bytes": destination.stat().st_size,
        "preview_bytes": asset_state["preview_bytes"],
        "full_bytes": asset_state["full_bytes"],
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
        asset_path = svg_path.with_name(f"{svg_path.stem}_assets")
        temporary_asset_path = asset_path.with_name(
            asset_path.name + ".tmp"
        )
        try:
            if temporary_asset_path.exists():
                shutil.rmtree(temporary_asset_path)
            info = convert_pdf_to_svg(
                pdf_path,
                temporary_path,
                source_hash=pdf_hash,
                asset_directory=temporary_asset_path,
                asset_url_prefix=asset_path.name,
            )
            if asset_path.exists():
                shutil.rmtree(asset_path)
            temporary_asset_path.replace(asset_path)
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
            if temporary_asset_path.exists():
                shutil.rmtree(temporary_asset_path)
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
