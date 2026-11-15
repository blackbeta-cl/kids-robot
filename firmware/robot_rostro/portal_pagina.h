/*
  portal_pagina.h — la página del portal cautivo (una sola, sin librerías externas, pensada para el móvil).
  Es HTML puro en una cadena: pruebas_pc/vista_portal.py la extrae y la sirve en el PC con datos de ejemplo.
  Seguridad: los nombres de red (los controla quien tenga un router cerca) se muestran SIEMPRE con textContent,
  nunca con innerHTML. El único valor que el robot inserta en la página es __TOKEN__ (hexadecimal).
*/
#pragma once

const char PORTAL_HTML[] PROGMEM = R"PORTALHTML(<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Wi-Fi del robot</title>
<style>
:root{--fondo:#f4f6f8;--tarjeta:#fff;--texto:#14202b;--suave:#5b6b7a;--borde:#cfd8e0;--marca:#1565c0;--error:#b3261e;--ok:#1b6e3c}
@media (prefers-color-scheme:dark){:root{--fondo:#10161c;--tarjeta:#1a232c;--texto:#e8eef3;--suave:#9aabba;--borde:#33424f;--marca:#64a8ff;--error:#ff8a80;--ok:#6fd99a}}
*{box-sizing:border-box}
body{margin:0;background:var(--fondo);color:var(--texto);font:17px/1.4 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;padding:16px}
main{max-width:30rem;margin:0 auto}
h1{font-size:1.4rem;margin:.2rem 0 1rem}
h2{font-size:1.05rem;margin:1.6rem 0 .5rem}
.tarjeta{background:var(--tarjeta);border:1px solid var(--borde);border-radius:14px;padding:16px}
label{display:block;font-weight:600;margin:.9rem 0 .3rem}
label:first-child{margin-top:0}
select,input[type=text],input[type=password]{width:100%;min-height:48px;font:inherit;color:inherit;background:var(--fondo);border:1px solid var(--borde);border-radius:10px;padding:10px 12px}
.ver{display:flex;gap:.6rem;align-items:center;font-weight:400;margin:.6rem 0 0}
.ver input{width:22px;height:22px}
button{font:inherit;font-weight:600;min-height:48px;border-radius:10px;border:0;cursor:pointer}
.principal{width:100%;margin-top:1.2rem;background:var(--marca);color:#fff}
@media (prefers-color-scheme:dark){.principal{color:#06121f}}
.principal:disabled{opacity:.5}
.aviso{border-left:4px solid var(--error);background:var(--tarjeta);padding:10px 12px;border-radius:8px;margin:0 0 1rem;color:var(--error)}
#msg{min-height:1.5rem;margin:.9rem 0 0;font-weight:600}
#msg.ok{color:var(--ok)}#msg.error{color:var(--error)}
ul{list-style:none;margin:0;padding:0}
li{display:flex;justify-content:space-between;align-items:center;gap:.6rem;padding:8px 0;border-top:1px solid var(--borde)}
li:first-child{border-top:0}
li span{overflow-wrap:anywhere}
.olvidar{background:transparent;color:var(--error);border:1px solid var(--borde);padding:0 14px;min-height:40px}
.nota{color:var(--suave);font-size:.9rem;margin:1rem 0 0}
[hidden]{display:none!important}
</style></head><body><main>
<h1>Wi-Fi del robot</h1>
<p id="motivo" class="aviso" hidden></p>
<form id="f" class="tarjeta" autocomplete="off">
<label for="sel">Red</label>
<select id="sel"></select>
<div id="manual" hidden>
<label for="man">Nombre de la red</label>
<input id="man" type="text" autocapitalize="off" autocorrect="off" spellcheck="false" maxlength="32">
</div>
<label for="clave">Clave</label>
<input id="clave" type="password" autocapitalize="off" autocorrect="off" spellcheck="false" maxlength="63">
<label class="ver"><input id="ver" type="checkbox"> Mostrar la clave</label>
<button id="ok" class="principal" type="submit">Guardar y conectar</button>
<p id="msg" role="status"></p>
</form>
<p class="nota">Solo redes de 2,4&nbsp;GHz. Si tu red es de 5&nbsp;GHz exclusivamente, el robot no la ve.</p>
<div id="gbox" hidden>
<h2>Redes guardadas</h2>
<ul id="gs" class="tarjeta"></ul>
</div>
</main>
<script>
"use strict";
var T="__TOKEN__";
var $=function(i){return document.getElementById(i)};
var sel=$("sel"),man=$("man"),msg=$("msg");
function decir(t,c){msg.textContent=t;msg.className=c||""}
function barras(r){return r>-60?"▂▄▆█":r>-70?"▂▄▆":r>-80?"▂▄":"▂"}
function opcion(v,t){var o=document.createElement("option");o.value=v;o.textContent=t;sel.appendChild(o)}
function cargar(){
  fetch("/redes?t="+T,{cache:"no-store"}).then(function(r){return r.json()}).then(function(d){
    sel.textContent="";
    (d.redes||[]).forEach(function(n){opcion("r:"+n.s,n.s+"  "+barras(n.r)+(n.a?"":"  🔒"))});
    opcion("*","Mi red no aparece…");
    manual();
    if(d.motivo){$("motivo").textContent=d.motivo;$("motivo").hidden=false}
    var ul=$("gs");ul.textContent="";
    (d.guardadas||[]).forEach(function(s){
      var li=document.createElement("li"),sp=document.createElement("span"),b=document.createElement("button");
      sp.textContent=s;b.textContent="Olvidar";b.className="olvidar";b.type="button";
      b.onclick=function(){olvidar(s)};
      li.appendChild(sp);li.appendChild(b);ul.appendChild(li)});
    $("gbox").hidden=!(d.guardadas&&d.guardadas.length);
  }).catch(function(){decir("No pude leer las redes. ¿Sigues conectado al robot?","error")});
}
function manual(){var m=sel.value==="*";$("manual").hidden=!m;if(m)man.focus()}
sel.onchange=manual;
$("ver").onchange=function(){$("clave").type=this.checked?"text":"password"};
function enviar(ruta,datos){
  datos.t=T;
  return fetch(ruta,{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body:new URLSearchParams(datos)}).then(function(r){return r.json()});
}
function olvidar(s){
  if(!confirm("¿Olvidar la red «"+s+"»?"))return;
  enviar("/olvidar",{ssid:s}).then(function(d){if(d.ok)cargar();else decir(d.error||"No pude olvidarla","error")}).catch(function(){decir("Sin respuesta del robot","error")});
}
$("f").onsubmit=function(e){
  e.preventDefault();
  var ssid=sel.value==="*"?man.value:sel.value.slice(2);
  if(!ssid){decir("Escribe el nombre de la red","error");return}
  $("ok").disabled=true;decir("Guardando…");
  enviar("/guardar",{ssid:ssid,clave:$("clave").value}).then(function(d){
    if(d.ok){decir("Guardada. Mira la pantalla del robot: se reinicia y prueba la red.","ok");$("f").querySelectorAll("select,input").forEach(function(x){x.disabled=true})}
    else{decir(d.error||"No pude guardarla","error");$("ok").disabled=false}
  }).catch(function(){decir("Sin respuesta del robot","error");$("ok").disabled=false});
};
cargar();
</script></body></html>)PORTALHTML";
