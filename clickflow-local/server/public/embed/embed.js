/*
 * ClickFlow Local — script de instalación del widget.
 * Uso en la página del negocio:
 *
 *   <script
 *     src="https://TU-DOMINIO/embed/embed.js"
 *     data-business="barberia-don-cesar"
 *     data-base-url="https://TU-DOMINIO"
 *     defer
 *   ></script>
 *
 * No abre el chat automáticamente ni reproduce sonidos. Aísla sus estilos
 * dentro de un <iframe>, así que no puede chocar con el CSS del sitio que lo
 * aloja ni el sitio puede leer las conversaciones.
 */
(function () {
  var currentScript =
    document.currentScript ||
    (function () {
      var scripts = document.getElementsByTagName("script");
      return scripts[scripts.length - 1];
    })();

  var businessSlug = currentScript.getAttribute("data-business");
  if (!businessSlug) {
    console.error("[ClickFlow Local] Falta data-business en el <script> de instalación.");
    return;
  }
  var baseUrl = (currentScript.getAttribute("data-base-url") || window.location.origin).replace(/\/$/, "");
  var position = currentScript.getAttribute("data-position") || "right"; // "right" | "left"

  var launcher = document.createElement("button");
  launcher.type = "button";
  launcher.setAttribute("aria-label", "Abrir asistente virtual");
  launcher.textContent = "💬";
  launcher.style.cssText = [
    "position:fixed",
    "bottom:20px",
    (position === "left" ? "left:20px" : "right:20px"),
    "width:56px",
    "height:56px",
    "border-radius:9999px",
    "border:none",
    "background:#245C57",
    "color:#F7F4EE",
    "font-size:24px",
    "box-shadow:0 6px 20px rgba(34,43,50,0.25)",
    "cursor:pointer",
    "z-index:2147483000",
  ].join(";");

  var frameWrap = document.createElement("div");
  frameWrap.style.cssText = [
    "position:fixed",
    "bottom:88px",
    (position === "left" ? "left:20px" : "right:20px"),
    "width:min(380px, calc(100vw - 32px))",
    "height:min(640px, calc(100vh - 120px))",
    "border-radius:16px",
    "overflow:hidden",
    "box-shadow:0 12px 40px rgba(34,43,50,0.35)",
    "display:none",
    "z-index:2147483000",
    "background:#F7F4EE",
  ].join(";");

  var iframe = document.createElement("iframe");
  iframe.title = "Asistente virtual";
  iframe.src = baseUrl + "/assistant/" + encodeURIComponent(businessSlug) + "?embed=1";
  iframe.style.cssText = "width:100%;height:100%;border:0;";
  iframe.setAttribute("loading", "lazy");
  frameWrap.appendChild(iframe);

  var open = false;
  launcher.addEventListener("click", function () {
    open = !open;
    frameWrap.style.display = open ? "block" : "none";
    launcher.setAttribute("aria-expanded", String(open));
  });

  document.addEventListener("DOMContentLoaded", function () {
    document.body.appendChild(frameWrap);
    document.body.appendChild(launcher);
  });
  if (document.readyState === "complete" || document.readyState === "interactive") {
    document.body.appendChild(frameWrap);
    document.body.appendChild(launcher);
  }
})();
