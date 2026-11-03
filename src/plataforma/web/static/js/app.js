// Comportamiento del frontend. HTMX hace las peticiones; aquí solo hay ajustes de interfaz.
(function () {
  "use strict";

  // ---- tema claro / oscuro (el valor inicial lo fija un script en <head> para evitar parpadeo)
  function guardarTema(tema) {
    document.documentElement.setAttribute("data-theme", tema);
    try { localStorage.setItem("tema", tema); } catch (e) { /* almacenamiento bloqueado */ }
  }
  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest("[data-cambiar-tema]");
    if (!btn) return;
    var actual = document.documentElement.getAttribute("data-theme");
    guardarTema(actual === "dark" ? "light" : "dark");
  });

  // ---- buscador universal: Ctrl+K o "/" lo enfocan; flechas recorren resultados; Esc cierra
  var buscador = document.getElementById("buscador");
  var resultados = document.getElementById("resultados");
  document.addEventListener("keydown", function (ev) {
    var enCampo = /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName);
    if ((ev.key === "k" && (ev.ctrlKey || ev.metaKey)) || (ev.key === "/" && !enCampo)) {
      if (buscador) { ev.preventDefault(); buscador.focus(); buscador.select(); }
    }
    if (ev.key === "Escape" && resultados) { resultados.innerHTML = ""; }
    var esFlecha = ev.key === "ArrowDown" || ev.key === "ArrowUp";
    if (esFlecha && resultados && (resultados.contains(document.activeElement) || document.activeElement === buscador)) {
      var enlaces = Array.prototype.slice.call(resultados.querySelectorAll("a"));
      if (!enlaces.length) return;
      ev.preventDefault();
      var i = enlaces.indexOf(document.activeElement);
      i = ev.key === "ArrowDown" ? Math.min(i + 1, enlaces.length - 1) : i - 1;
      if (i < 0) buscador.focus(); else enlaces[i].focus();
    }
  });
  document.addEventListener("click", function (ev) {
    if (resultados && !ev.target.closest(".buscador")) resultados.innerHTML = "";
    var menu = document.querySelector(".menu-descarga[open]");
    if (menu && !ev.target.closest(".menu-descarga")) menu.removeAttribute("open");
  });

  // ---- copiar al portapapeles, con respaldo si el navegador lo impide
  function avisar(texto) {
    var aviso = document.createElement("div");
    aviso.className = "aviso-copia";
    aviso.setAttribute("role", "status");
    aviso.textContent = texto;
    document.body.appendChild(aviso);
    setTimeout(function () { aviso.remove(); }, 1800);
  }
  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest("[data-copiar]");
    if (!btn) return;
    var origen = document.getElementById(btn.getAttribute("data-copiar"));
    var texto = origen ? origen.textContent : btn.getAttribute("data-texto");
    function respaldo() {
      if (!origen) return;
      var rango = document.createRange();
      rango.selectNodeContents(origen);
      var sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(rango);
      avisar("Texto seleccionado: usa Ctrl+C");
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(texto.trim()).then(function () { avisar("Copiado"); }, respaldo);
    } else { respaldo(); }
  });

  // ---- filtros del explorador: agregar y quitar filas
  document.addEventListener("click", function (ev) {
    var agregar = ev.target.closest("[data-agregar-filtro]");
    if (agregar) {
      var plantilla = document.getElementById("plantilla-filtro");
      var lista = document.getElementById("lista-filtros");
      lista.appendChild(plantilla.content.cloneNode(true));
      var vacio = document.querySelector(".sin-filtros");
      if (vacio) vacio.hidden = true;
      lista.lastElementChild.querySelector("select").focus();
    }
    var quitar = ev.target.closest("[data-quitar-filtro]");
    if (quitar) {
      var form = quitar.closest("form");
      quitar.closest(".filtro").remove();
      if (window.htmx) htmx.trigger(form, "submit");
    }
  });
  document.addEventListener("change", function (ev) {
    var el = ev.target;
    // los operadores "vacío" no usan valor; readonly y no disabled, para que la fila conserve
    // sus tres campos al enviarse y columnas, operadores y valores sigan emparejados
    if (el.matches(".filtro select[name=fo]")) {
      var valor = el.closest(".filtro").querySelector("[name=fv]");
      var sinValor = el.value === "vacio" || el.value === "no_vacio";
      valor.readOnly = sinValor;
      if (sinValor) valor.value = "";
    }
    if (el.matches("select[data-navegar]")) location.href = el.value;
    if (el.matches("[data-enviar-al-cambiar]") && el.form && window.htmx) htmx.trigger(el.form, "submit");
  });

  // ---- pestañas de la ficha: estado seleccionado y enlace directo por #
  document.addEventListener("click", function (ev) {
    var tab = ev.target.closest('.pestanas [role="tab"]');
    if (!tab) return;
    tab.parentElement.querySelectorAll('[role="tab"]').forEach(function (t) {
      t.setAttribute("aria-selected", t === tab ? "true" : "false");
    });
    history.replaceState(null, "", "#" + tab.dataset.pestana);
  });
  document.addEventListener("DOMContentLoaded", function () {
    var hash = location.hash.replace("#", "");
    var tab = hash && document.querySelector('.pestanas [data-pestana="' + hash + '"]');
    if (tab && tab.getAttribute("aria-selected") !== "true") tab.click();
  });
})();
