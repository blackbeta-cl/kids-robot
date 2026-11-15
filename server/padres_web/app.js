"use strict";
// Panel de padres. Todo el texto que viene de la base se pinta con textContent (sale de lo que dice el niño).
const $ = (id) => document.getElementById(id);
let temporizadorAviso;

function avisar(texto) {
  const caja = $("aviso");
  caja.textContent = texto;
  caja.classList.add("visible");
  clearTimeout(temporizadorAviso);
  temporizadorAviso = setTimeout(() => caja.classList.remove("visible"), 4000);
}

async function api(metodo, ruta, cuerpo) {
  const opciones = { method: metodo, headers: { "X-Panel": "1" }, credentials: "same-origin" };
  if (cuerpo !== undefined) {
    opciones.headers["Content-Type"] = "application/json";
    opciones.body = JSON.stringify(cuerpo);
  }
  const r = await fetch("api/" + ruta, opciones);
  let datos = null;
  try { datos = await r.json(); } catch (e) { /* sin cuerpo */ }
  if (r.status === 401 && ruta !== "sesion") { mostrarEntrar(); throw new Error("Hay que entrar de nuevo."); }
  if (!r.ok) {
    const detalle = datos && datos.detail;
    throw new Error(typeof detalle === "string" ? detalle : "Algo salió mal (" + r.status + ").");
  }
  return datos;
}

function mostrarEntrar() {
  $("vista-panel").hidden = true; $("salir").hidden = true; $("vista-entrar").hidden = false;
  $("clave").value = "";
}
function mostrarPanel() {
  $("vista-entrar").hidden = true; $("vista-panel").hidden = false; $("salir").hidden = false;
  cargarTodo().catch((e) => avisar(e.message));
}

function boton(texto, clase, accion) {
  const b = document.createElement("button");
  b.type = "button"; b.textContent = texto; if (clase) b.className = clase;
  b.addEventListener("click", async () => {
    b.disabled = true;
    try { await accion(); } catch (e) { avisar(e.message); } finally { b.disabled = false; }
  });
  return b;
}

function tarjeta(texto, meta, botones) {
  const li = document.createElement("li");
  const p = document.createElement("div"); p.className = "texto"; p.textContent = texto; li.append(p);
  if (meta) { const m = document.createElement("p"); m.className = "meta"; m.textContent = meta; li.append(m); }
  if (botones && botones.length) {
    const acc = document.createElement("div"); acc.className = "acciones"; acc.append(...botones); li.append(acc);
  }
  return li;
}

function pintar(lista, items, vacio) {
  const sinNada = document.createElement("li"); sinNada.className = "vacio"; sinNada.textContent = vacio;
  lista.replaceChildren(...(items.length ? items : [sinNada]));
}

async function cargarTodo() {
  const [pend, aprob, rasgos] = await Promise.all([
    api("GET", "hechos?estado=pendiente"), api("GET", "hechos?estado=aprobado"), api("GET", "rasgos")]);
  const meta = (h) => [h.fuente, h.vence ? "vence " + h.vence : ""].filter(Boolean).join(" · ");
  const recargar = async (peticion) => { await peticion; await cargarTodo(); };
  pintar($("lista-pendientes"), pend.map((h) => tarjeta(h.texto, meta(h), [
    boton("Aprobar", "ok", () => recargar(api("POST", "hechos/" + h.id + "/aprobar"))),
    boton("Editar", "", () => editar(h)),
    boton("Rechazar", "mal", () => recargar(api("POST", "hechos/" + h.id + "/rechazar"))),
  ])), "Nada por aprobar.");
  pintar($("lista-aprobados"), aprob.map((h) => tarjeta(h.texto, meta(h), [
    boton("Editar", "", () => editar(h)),
    boton("Borrar", "mal", async () => {
      if (window.confirm("¿Borrar este hecho para siempre?")) await recargar(api("DELETE", "hechos/" + h.id));
    }),
  ])), "El robot aún no sabe nada aprobado.");
  const rp = rasgos.filter((r) => r.estado === "pendiente"), ra = rasgos.filter((r) => r.estado === "activo");
  pintar($("lista-rasgos-pend"), rp.map((r) => tarjeta(r.texto, "", [
    boton("Aprobar", "ok", () => recargar(api("POST", "rasgos/" + r.id + "/aprobar"))),
    boton("Descartar", "mal", () => recargar(api("DELETE", "rasgos/" + r.id))),
  ])), "Ninguno por ahora.");
  pintar($("lista-rasgos-act"), ra.map((r) => tarjeta(r.texto, "", [
    boton("Retirar", "", () => recargar(api("POST", "rasgos/" + r.id + "/retirar"))),
  ])), "Ninguno activo.");
  const n = pend.length + rp.length;
  $("n-pend").textContent = n; $("n-pend").hidden = n === 0;
}

async function editar(h) {
  const nuevo = window.prompt("Editar hecho", h.texto);
  if (nuevo === null || nuevo.trim() === h.texto) return;
  await api("PATCH", "hechos/" + h.id, { texto: nuevo });
  await cargarTodo();
}

// ---------- Agenda ----------
const DIAS = ["L", "M", "X", "J", "V", "S", "D"];
const DIAS_LARGOS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"];
const TIPOS = { recordatorio: "Recordatorio", alarma: "Alarma", rutina: "Rutina", cumpleanos: "Cumpleaños", temporizador: "Temporizador" };
let editandoEvento = null;

function diasTexto(dias) {
  if (!dias || !dias.length) return "";
  if (dias.length === 7) return "todos los días";
  if (dias.join(",") === "0,1,2,3,4") return "de lunes a viernes";
  return "los " + dias.map((d) => DIAS_LARGOS[d]).join(", ");
}

function cuandoDe(e) {
  if (e.tipo === "cumpleanos") {
    const [m, d] = (e.fecha || "").split("-");
    return d && m ? "el " + d + "/" + m + " de cada año" : "sin fecha";
  }
  if (e.fecha) {
    const [a, m, d] = e.fecha.split("-");
    return "el " + d + "/" + m + "/" + a;
  }
  return diasTexto(e.dias) || "sin día";
}

function bonito(iso) {
  return (iso || "").slice(0, 16).replace("T", " ");
}

function pintarAjustes(a) {
  $("a-desde").value = a.silencio_desde || "";
  $("a-hasta").value = a.silencio_hasta || "";
  $("a-activos").checked = !!a.avisos_activos;
  $("a-alarma-silencio").checked = !!a.permitir_alarma_silencio;
}

function pintarEventos(eventos) {
  const orden = { alarma: 0, rutina: 1, recordatorio: 2, temporizador: 3, cumpleanos: 4 };
  eventos = eventos.slice().sort((x, y) => (orden[x.tipo] - orden[y.tipo]) || x.hora.localeCompare(y.hora));
  pintar($("lista-agenda"), eventos.map((e) => {
    const meta = [TIPOS[e.tipo] || e.tipo, e.hora, cuandoDe(e),
                  e.creado_por === "nino" ? "creado por el niño" : "",
                  e.siguiente ? "próximo: " + bonito(e.siguiente) : "sin próxima vez",
                  e.activo ? "" : "desactivado"].filter(Boolean).join(" · ");
    const botones = [];
    if (e.tipo !== "cumpleanos") {
      // El cumpleaños se arma solo desde el perfil: activarlo o desactivarlo no tendría efecto.
      botones.push(boton(e.activo ? "Desactivar" : "Activar", "", async () => {
        await api("PATCH", "agenda/" + e.id + "/activo", { activo: !e.activo });
        await cargarAgenda();
      }));
      botones.push(boton("Editar", "", () => editarEvento(e)));
    }
    botones.push(boton("Probar", "ok", async () => {
      const r = await api("POST", "agenda/" + e.id + "/probar");
      avisar(r.mensaje || "Prueba creada.");
    }));
    botones.push(boton("Escuchar aquí", "", () => api("POST", "agenda/" + e.id + "/escuchar")));
    if (e.tipo !== "cumpleanos") {
      botones.push(boton("Borrar", "mal", async () => {
        if (window.confirm("¿Borrar «" + e.titulo + "»?")) {
          await api("DELETE", "agenda/" + e.id);
          if (editandoEvento && editandoEvento.id === e.id) cancelarEdicion();
          await cargarAgenda();
        }
      }));
    }
    return tarjeta(e.titulo, meta, botones);
  }), "Todavía no hay eventos. Agrega el primero arriba.");
}

function pintarAvisos(avisos) {
  pintar($("lista-avisos"), avisos.map((a) => tarjeta(a.titulo,
    [TIPOS[a.tipo] || a.tipo, bonito(a.programado), a.estado, a.prueba ? "prueba" : "",
     a.motivo || ""].filter(Boolean).join(" · "), [])), "Todavía no se ha entregado ningún aviso.");
}

async function cargarAgenda() {
  const datos = await api("GET", "agenda");
  pintarAjustes(datos.ajustes);
  pintarEventos(datos.eventos);
  pintarAvisos(datos.avisos);
}

function editarEvento(e) {
  editandoEvento = e;
  $("e-tipo").value = e.tipo;
  $("e-titulo").value = e.titulo;
  $("e-hora").value = e.hora;
  $("e-fecha").value = e.fecha || "";
  marcarDias(e.dias || []);
  $("titulo-evento").textContent = "Editar evento";
  $("e-guardar").textContent = "Guardar cambios";
  $("e-cancelar").hidden = false;
  $("form-evento").scrollIntoView({ block: "start" });
}

function cancelarEdicion() {
  editandoEvento = null;
  $("form-evento").reset();
  marcarDias([]);
  $("titulo-evento").textContent = "Nuevo evento";
  $("e-guardar").textContent = "Agregar evento";
  $("e-cancelar").hidden = true;
}

function marcarDias(dias) {
  const elegidos = new Set(dias);
  document.querySelectorAll("#e-dias input").forEach((c) => { c.checked = elegidos.has(Number(c.value)); });
  $("e-todos").checked = dias.length === 7;
}

function diasElegidos() {
  return Array.from(document.querySelectorAll("#e-dias input:checked")).map((c) => Number(c.value));
}

// Un checkbox por día; se crean una vez.
DIAS.forEach((letra, numero) => {
  const etiqueta = document.createElement("label");
  const casilla = document.createElement("input");
  casilla.type = "checkbox"; casilla.value = String(numero);
  etiqueta.append(casilla, document.createTextNode(letra));
  $("e-dias").append(etiqueta);
});

$("e-todos").addEventListener("change", () => {
  const todos = $("e-todos").checked;
  document.querySelectorAll("#e-dias input").forEach((c) => { c.checked = todos; });
});

$("e-cancelar").addEventListener("click", cancelarEdicion);

async function cargarPerfil() {
  const p = await api("GET", "perfil");
  $("apodo").value = p.apodo; $("nacimiento").value = p.nacimiento; $("gustos").value = p.gustos.join(", ");
  if (p.origen === "archivo") avisar("Perfil leído del archivo: guárdalo para pasarlo a la base.");
}

let personaApi = null;
function pintarPersona(p) {
  personaApi = p;
  $("p-identidad").value = p.identidad; $("p-tono").value = p.tono; $("p-reglas").value = p.reglas_extra.join("\n");
  $("p-identidad").placeholder = p.ejemplo.identidad; $("p-tono").placeholder = p.ejemplo.tono;
  $("p-reglas").placeholder = p.ejemplo.reglas_extra.join("\n");
  $("p-origen").textContent = p.origen === "base" ? "Guardada en el panel."
    : p.origen === "archivo" ? "Leída de un archivo: guárdala para pasarla al panel."
    : "Aún no hay una guardada: el robot usa la de siempre (puedes editarla desde aquí).";
}
async function cargarPersona() { pintarPersona(await api("GET", "persona")); }

document.querySelectorAll("#pestanas button").forEach((b) => b.addEventListener("click", () => {
  document.querySelectorAll("#pestanas button").forEach((x) => x.setAttribute("aria-selected", String(x === b)));
  for (const v of ["pendientes", "agenda", "sabe", "perfil", "persona"]) $("v-" + v).hidden = v !== b.dataset.v;
  if (b.dataset.v === "agenda") cargarAgenda().catch((e) => avisar(e.message));
  if (b.dataset.v === "perfil") cargarPerfil().catch((e) => avisar(e.message));
  if (b.dataset.v === "persona") cargarPersona().catch((e) => avisar(e.message));
}));

$("form-entrar").addEventListener("submit", async (e) => {
  e.preventDefault();
  try { await api("POST", "sesion", { usuario: $("usuario").value, clave: $("clave").value }); mostrarPanel(); }
  catch (err) { avisar(err.message); }
});
$("salir").addEventListener("click", async () => {
  try { await api("DELETE", "sesion"); } catch (e) { /* ya había salido */ }
  mostrarEntrar();
});
$("form-agregar").addEventListener("submit", async (e) => {
  e.preventDefault();
  const texto = $("nuevo-hecho").value.trim(); if (!texto) return;
  try { await api("POST", "hechos", { texto }); $("nuevo-hecho").value = ""; avisar("Agregado."); await cargarTodo(); }
  catch (err) { avisar(err.message); }
});
$("form-perfil").addEventListener("submit", async (e) => {
  e.preventDefault();
  const gustos = $("gustos").value.split(",").map((g) => g.trim()).filter(Boolean);
  try {
    await api("PUT", "perfil", { apodo: $("apodo").value, nacimiento: $("nacimiento").value, gustos });
    avisar("Perfil guardado."); await cargarPerfil();
  } catch (err) { avisar(err.message); }
});
$("form-persona").addEventListener("submit", async (e) => {
  e.preventDefault();
  const reglas = $("p-reglas").value.split("\n").map((r) => r.trim()).filter(Boolean);
  try {
    pintarPersona(await api("PUT", "persona", { identidad: $("p-identidad").value, tono: $("p-tono").value, reglas_extra: reglas }));
    avisar("Personalidad guardada.");
  } catch (err) { avisar(err.message); }
});
$("p-ejemplo").addEventListener("click", () => {
  if (!personaApi) return;
  $("p-identidad").value = personaApi.ejemplo.identidad; $("p-tono").value = personaApi.ejemplo.tono;
  $("p-reglas").value = personaApi.ejemplo.reglas_extra.join("\n");
  avisar("Ejemplo cargado: revísalo y guarda si te gusta.");
});
$("p-restablecer").addEventListener("click", async () => {
  if (!window.confirm("¿Volver a la personalidad de siempre? Se borra la que guardaste.")) return;
  try { pintarPersona(await api("DELETE", "persona")); avisar("Restablecida."); } catch (err) { avisar(err.message); }
});
$("form-clave").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("POST", "clave", { actual: $("clave-actual").value, nueva: $("clave-nueva").value });
    e.target.reset(); avisar("Contraseña cambiada.");
  } catch (err) { avisar(err.message); }
});

$("form-ajustes").addEventListener("submit", async (e) => {
  e.preventDefault();
  const cuerpo = {
    avisos_activos: $("a-activos").checked,
    silencio_desde: $("a-desde").value,
    silencio_hasta: $("a-hasta").value,
    permitir_alarma_silencio: $("a-alarma-silencio").checked,
  };
  try {
    pintarAjustes(await api("PUT", "agenda/ajustes", cuerpo));
    avisar("Avisos guardados.");
  } catch (err) { avisar(err.message); }
});

$("form-evento").addEventListener("submit", async (e) => {
  e.preventDefault();
  const titulo = $("e-titulo").value.trim();
  if (!titulo) return;
  const fecha = $("e-fecha").value;
  const dias = fecha ? [] : diasElegidos();
  if (!fecha && !dias.length) { avisar("Elige un día o marca los días de la semana."); return; }
  const cuerpo = {
    tipo: $("e-tipo").value, titulo, hora: $("e-hora").value, fecha, dias,
    activo: editandoEvento ? editandoEvento.activo : true,
  };
  try {
    if (editandoEvento) await api("PUT", "agenda/" + editandoEvento.id, cuerpo);
    else await api("POST", "agenda", cuerpo);
    avisar(editandoEvento ? "Evento actualizado." : "Evento agregado.");
    cancelarEdicion();
    await cargarAgenda();
  } catch (err) { avisar(err.message); }
});

api("GET", "yo").then(mostrarPanel, mostrarEntrar);
