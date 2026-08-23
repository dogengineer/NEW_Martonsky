<?php
$baseDir = "pdf";

function cleanName($name){
    $name = basename($name);
    $name = preg_replace('/^\d+_/', '', $name);
    $name = preg_replace('/(?:\.(?:pdf|html|htm))+$/i', '', $name);
    return trim($name);
}

function getOrder($name){
    $name = basename($name);
    if(preg_match('/^(\d+)_/', $name, $matches)){
        return (int)$matches[1];
    }
    return 999999;
}

function isSupportedFile($path){
    if(!is_file($path)){
        return false;
    }
    $extension = strtolower(pathinfo($path, PATHINFO_EXTENSION));
    return in_array($extension, ["pdf", "html", "htm"]);
}

function getFolderItems($folder){
    if(!is_dir($folder)){
        return [];
    }

    $items = scandir($folder);

    $items = array_filter($items, function($item) use ($folder){
        if($item === "." || $item === ".."){
            return false;
        }

        $path = $folder . "/" . $item;

        if(is_dir($path)){
            return true;
        }

        return isSupportedFile($path);
    });

    usort($items, function($a, $b){
        $orderA = getOrder($a);
        $orderB = getOrder($b);

        if($orderA === $orderB){
            return strcasecmp(cleanName($a), cleanName($b));
        }

        return $orderA <=> $orderB;
    });

    return array_values($items);
}

function renderFileLink($path, $label){
    $url = str_replace("\\", "/", $path);
    $extension = strtolower(pathinfo($path, PATHINFO_EXTENSION));

    if($extension === "pdf"){
        echo '<a href="#" onclick=\'loadPDF(' . json_encode($url) . ');return false;\'>';
        echo htmlspecialchars($label);
        echo '</a>';
    }
    elseif($extension === "html" || $extension === "htm"){
        echo '<a href="#" onclick=\'loadHTML(' . json_encode($url) . ');return false;\'>';
        echo htmlspecialchars($label);
        echo '</a>';
    }
}

function renderSubMenu($folder){
    $items = getFolderItems($folder);

    if(count($items) === 0){
        return;
    }

    echo '<ul class="submenu">';

    foreach($items as $item){
        $path = $folder . "/" . $item;
        $label = cleanName($item);

        if(is_dir($path)){
            $children = getFolderItems($path);
            $childCount = count($children);

            if($childCount === 0){
                echo '<li>';
                echo '<span class="empty-item">';
                echo htmlspecialchars($label);
                echo '</span>';
                echo '</li>';
            }
            elseif($childCount === 1){
                $onlyChild = $children[0];
                $onlyChildPath = $path . "/" . $onlyChild;

                if(is_dir($onlyChildPath)){
                    echo '<li class="has-submenu">';
                    echo '<span class="submenu-label">';
                    echo htmlspecialchars($label);
                    echo '<span class="arrow">›</span>';
                    echo '</span>';

                    renderSubMenu($path);

                    echo '</li>';
                }
                else{
                    echo '<li>';
                    renderFileLink($onlyChildPath, $label);
                    echo '</li>';
                }
            }
            else{
                echo '<li class="has-submenu">';
                echo '<span class="submenu-label">';
                echo htmlspecialchars($label);
                echo '<span class="arrow">›</span>';
                echo '</span>';

                renderSubMenu($path);

                echo '</li>';
            }
        }
        else{
            echo '<li>';
            renderFileLink($path, $label);
            echo '</li>';
        }
    }

    echo '</ul>';
}

$topFolders = [];

if(is_dir($baseDir)){
    $items = scandir($baseDir);

    $topFolders = array_filter($items, function($item) use ($baseDir){
        if($item === "." || $item === ".."){
            return false;
        }

        return is_dir($baseDir . "/" . $item);
    });

    usort($topFolders, function($a, $b){
        $orderA = getOrder($a);
        $orderB = getOrder($b);

        if($orderA === $orderB){
            return strcasecmp(cleanName($a), cleanName($b));
        }

        return $orderA <=> $orderB;
    });
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Martonsky</title>
<link rel="icon" type="image/png" href="Icons/favicon.png">

<style>
*{
    margin:0;
    padding:0;
    box-sizing:border-box;
}

html,
body{
    width:100%;
    min-height:100%;
    background:#fff;
    color:#000;
}

body{
    font-family:Arial,Helvetica,sans-serif;
}

header{
    width:100%;
    display:flex;
    align-items:center;
    padding:22px 30px;
    background:#fff;
    position:relative;
    z-index:1000;
}

.logo{
    display:block;
    margin-right:50px;
    text-decoration:none;
    cursor:pointer;
    flex-shrink:0;
}

.logo img{
    display:block;
    width:160px;
    height:auto;
    border:0;
}

nav{
    flex:1;
}

nav>ul{
    display:flex;
    align-items:center;
    gap:30px;
    list-style:none;
}

nav li{
    list-style:none;
}

nav a,
.menu-label,
.submenu-label{
    color:#000;
    text-decoration:none;
    font-size:14px;
    cursor:pointer;
}

nav a:hover,
.menu-label:hover,
.submenu-label:hover{
    opacity:.55;
}

.top-menu-item{
    position:relative;
}

.submenu{
    display:none;
    position:absolute;
    top:100%;
    left:0;
    min-width:220px;
    background:#fff;
    padding:12px 0;
    z-index:2000;
}

.top-menu-item:hover>.submenu{
    display:block;
}

.submenu li{
    position:relative;
    display:block;
}

.submenu a,
.submenu-label,
.empty-item{
    display:flex;
    align-items:center;
    justify-content:space-between;
    width:100%;
    min-width:220px;
    padding:6px 14px;
    white-space:nowrap;
    background:#fff;
}

.submenu li>.submenu{
    display:none;
    position:absolute;
    top:0;
    left:100%;
    padding-left:2px;
}

.submenu li.has-submenu:hover>.submenu{
    display:block;
}

.arrow{
    margin-left:25px;
    font-size:18px;
    line-height:14px;
}

.empty-item{
    font-size:14px;
    opacity:.4;
    cursor:default;
}

.empty-section{
    opacity:.4;
    cursor:default;
}

main{
    width:100%;
    background:#fff;
}

/*
IMPORTANTE:
Il viewer può ora diventare più largo dello schermo
quando l'utente aumenta lo zoom del browser.
*/
#viewer{
    width:100%;
    min-height:calc(100vh - 110px);
    background:#fff;
    overflow-x:auto;
    overflow-y:hidden;
}

/*
NON utilizziamo più width:100%.
Il canvas mantiene la dimensione CSS con cui è stato
renderizzato inizialmente e segue normalmente lo zoom
del browser.
*/
.pdf-page{
    display:block;
    max-width:none;
    margin:0;
    padding:0;
    border:0;
    outline:0;
    background:#fff;
}

#htmlViewer{
    width:100%;
    background:#fff;
    display:none;
}

#loading{
    display:none;
    text-align:center;
    padding:40px;
    font-size:13px;
}

footer{
    width:100%;
    padding:18px 30px;
    background:#fff;
    font-size:11px;
    text-align:center;
}

footer a{
    color:inherit;
    text-decoration:none;
}

footer a:hover{
    text-decoration:underline;
}

.mobile-button{
    display:none;
    background:none;
    border:0;
    font-size:22px;
    cursor:pointer;
}

.video-project{
    width:100%;
    max-width:1200px;
    margin:0 auto;
    padding:20px 20px 60px;
}

.video-item{
    width:100%;
    margin-bottom:50px;
}

.video-item iframe{
    display:block;
    width:100%;
    aspect-ratio:16/9;
    border:0;
}

.video-item p{
    margin-top:8px;
    text-align:center;
    font-size:12px;
    line-height:1.4;
}

.video-item h2{
    font-size:16px;
    font-weight:400;
    margin-bottom:8px;
}

@media(max-width:800px){
    header{
        align-items:flex-start;
        justify-content:space-between;
        padding:18px;
    }

    .logo img{
        width:120px;
    }

    .mobile-button{
        display:block;
    }

    nav{
        display:none;
        position:absolute;
        left:0;
        top:60px;
        width:100%;
        background:#fff;
        padding:20px;
    }

    nav.open{
        display:block;
    }

    nav>ul{
        display:block;
    }

    nav>ul>li{
        margin-bottom:15px;
    }

    .submenu{
        display:block;
        position:static;
        padding:5px 0 5px 15px;
    }

    .submenu li>.submenu{
        display:block;
        position:static;
        padding-left:15px;
    }

    .submenu a,
    .submenu-label,
    .empty-item{
        min-width:0;
        padding:5px 0;
    }

    .arrow{
        display:none;
    }

    .video-project{
        padding:10px 12px 40px;
    }
}
</style>
</head>

<body>

<header>

<a class="logo"
   href="#"
   onclick="loadPDF('pdf/home.pdf');return false;"
   aria-label="Home">
    <img src="Icons/icon.png" alt="Martonsky">
</a>

<nav id="mainMenu">
<ul>

<?php foreach($topFolders as $folder): ?>

<?php
$folderPath = $baseDir . "/" . $folder;
$folderLabel = cleanName($folder);
$items = getFolderItems($folderPath);
$itemCount = count($items);
?>

<?php if($itemCount === 0): ?>

<li>
<span class="menu-label empty-section">
<?= htmlspecialchars($folderLabel) ?>
</span>
</li>

<?php elseif($itemCount === 1): ?>

<?php
$onlyItem = $items[0];
$onlyItemPath = $folderPath . "/" . $onlyItem;
?>

<?php if(is_dir($onlyItemPath)): ?>

<li class="top-menu-item">
<span class="menu-label">
<?= htmlspecialchars($folderLabel) ?>
</span>
<?php renderSubMenu($folderPath); ?>
</li>

<?php else: ?>

<li>
<?php renderFileLink($onlyItemPath, $folderLabel); ?>
</li>

<?php endif; ?>

<?php else: ?>

<li class="top-menu-item">
<span class="menu-label">
<?= htmlspecialchars($folderLabel) ?>
</span>
<?php renderSubMenu($folderPath); ?>
</li>

<?php endif; ?>

<?php endforeach; ?>

</ul>
</nav>

<button
class="mobile-button"
onclick="toggleMenu()"
aria-label="Menu">
☰
</button>

</header>

<main>

<div id="loading">Loading...</div>
<div id="viewer"></div>
<div id="htmlViewer"></div>

</main>

<footer>
Designed by
<a href="https://martonsky.com/"
   target="_blank"
   rel="noopener noreferrer">Martonsky</a>
and Developed by Davide Maieron
</footer>

<script type="module">

import * as pdfjsLib from
"https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.min.mjs";

pdfjsLib.GlobalWorkerOptions.workerSrc =
"https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.worker.min.mjs";

const viewer = document.getElementById("viewer");
const htmlViewer = document.getElementById("htmlViewer");
const loading = document.getElementById("loading");

let currentType = "pdf";
let currentURL = "pdf/home.pdf";
let currentRenderId = 0;

window.loadPDF = async function(url){

    currentType = "pdf";
    currentURL = url;

    const renderId = ++currentRenderId;

    closeMobileMenu();

    viewer.style.display = "block";
    htmlViewer.style.display = "none";

    htmlViewer.innerHTML = "";
    viewer.innerHTML = "";

    loading.style.display = "block";

    try{

        const pdf = await pdfjsLib
            .getDocument(url)
            .promise;

        if(renderId !== currentRenderId){
            return;
        }

        loading.style.display = "none";

        /*
        Memorizziamo la larghezza disponibile nel momento
        in cui il PDF viene aperto.

        Il PDF viene adattato alla finestra UNA SOLA VOLTA.

        Successivamente lo zoom del browser può ingrandire
        normalmente tutto, canvas compreso.
        */
        const initialViewerWidth = viewer.clientWidth;

        for(
            let pageNumber = 1;
            pageNumber <= pdf.numPages;
            pageNumber++
        ){

            if(renderId !== currentRenderId){
                return;
            }

            const page = await pdf.getPage(pageNumber);

            const baseViewport = page.getViewport({
                scale:1
            });

            /*
            Calcoliamo la scala necessaria affinché
            inizialmente il PDF occupi tutta la larghezza.
            */
            const scale =
                initialViewerWidth /
                baseViewport.width;

            const viewport = page.getViewport({
                scale:scale
            });

            const canvas =
                document.createElement("canvas");

            canvas.className = "pdf-page";

            const context =
                canvas.getContext("2d");

            const pixelRatio =
                window.devicePixelRatio || 1;

            /*
            Risoluzione reale del canvas.
            */
            canvas.width =
                Math.floor(
                    viewport.width *
                    pixelRatio
                );

            canvas.height =
                Math.floor(
                    viewport.height *
                    pixelRatio
                );

            /*
            Dimensione CSS iniziale.

            IMPORTANTE:
            non viene poi continuamente riportata
            alla larghezza dello schermo.
            */
            canvas.style.width =
                viewport.width + "px";

            canvas.style.height =
                viewport.height + "px";

            viewer.appendChild(canvas);

            await page.render({
                canvasContext:context,
                viewport:viewport,
                transform:
                    pixelRatio !== 1
                    ? [
                        pixelRatio,
                        0,
                        0,
                        pixelRatio,
                        0,
                        0
                    ]
                    : null
            }).promise;
        }

    }
    catch(error){

        if(renderId !== currentRenderId){
            return;
        }

        loading.style.display = "none";

        viewer.innerHTML =
        "<p style='padding:40px;text-align:center'>Unable to load PDF.</p>";

        console.error(error);
    }
};

window.loadHTML = async function(url){

    currentType = "html";
    currentURL = url;

    currentRenderId++;

    closeMobileMenu();

    /*
    Nascondiamo completamente il viewer PDF.
    In questo modo non lascia lo spazio bianco
    prima delle pagine HTML / Vimeo.
    */
    viewer.style.display = "none";
    htmlViewer.style.display = "block";

    viewer.innerHTML = "";
    htmlViewer.innerHTML = "";

    loading.style.display = "block";

    try{

        const response =
            await fetch(url);

        if(!response.ok){
            throw new Error(
                "HTTP error: " +
                response.status
            );
        }

        const html =
            await response.text();

        loading.style.display = "none";

        htmlViewer.innerHTML = html;

        /*
        Permette l'esecuzione degli eventuali
        script presenti nell'HTML caricato.
        */
        htmlViewer
        .querySelectorAll("script")
        .forEach(oldScript => {

            const newScript =
                document.createElement("script");

            [...oldScript.attributes]
                .forEach(attribute => {
                    newScript.setAttribute(
                        attribute.name,
                        attribute.value
                    );
                });

            newScript.textContent =
                oldScript.textContent;

            oldScript.replaceWith(
                newScript
            );
        });

        window.scrollTo({
            top:0,
            behavior:"smooth"
        });

    }
    catch(error){

        loading.style.display = "none";

        htmlViewer.innerHTML =
        "<p style='padding:40px;text-align:center'>Unable to load HTML page.</p>";

        console.error(error);
    }
};

window.toggleMenu = function(){

    document
        .getElementById("mainMenu")
        .classList
        .toggle("open");

};

window.closeMobileMenu = function(){

    document
        .getElementById("mainMenu")
        .classList
        .remove("open");

};

/*
IMPORTANTE:

NON ricarichiamo più automaticamente il PDF
quando cambia la dimensione della viewport.

Prima avevamo:

window.addEventListener("resize", ...)

che ridisegnava il PDF alla nuova larghezza.

Lo zoom del browser può generare variazioni della viewport,
quindi il PDF veniva continuamente riadattato e sembrava
non ingrandirsi.

Ora lo lasciamo volutamente fermo alla dimensione CSS
calcolata quando viene aperto.
*/

document.addEventListener(
"DOMContentLoaded",
function(){

    loadPDF(
        "pdf/home.pdf"
    );

});

</script>

</body>
</html>