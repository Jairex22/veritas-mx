// Aplica el tema guardado antes de pintar para evitar parpadeo.
(function () {
  try {
    var t = localStorage.getItem("gpv.theme");
    if (!t) t = window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", t);
  } catch (e) { /* almacenamiento bloqueado: usar tema por defecto */ }
})();
