// Aplica el tema antes del primer pintado (evita parpadeo). Archivo externo para cumplir la CSP (sin scripts en línea).
(function () {
  try {
    var saved = localStorage.getItem("tf-theme");
    var theme = saved || (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    document.documentElement.setAttribute("data-theme", theme);
    if (localStorage.getItem("tf-sidebar") === "collapsed") document.documentElement.setAttribute("data-sidebar", "collapsed");
  } catch (e) { /* almacenamiento no disponible */ }
})();
