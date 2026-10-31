// Panel de firma (pointer events + canvas). Lo usa Components/Ui/SignaturePad.razor.
// Exporta PNG como data URL; el prefijo "data:image/png;base64," se quita en C#.

const MAX_RATIO = 2; // limita el tamaño del PNG (la API acepta hasta 400 KB)

export function create(canvas, dotnet) {
  const ctx = canvas.getContext("2d");
  let drawing = false;
  let hasInk = false;
  let last = null;

  function resize() {
    const ratio = Math.min(window.devicePixelRatio || 1, MAX_RATIO);
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(1, Math.round(rect.width * ratio));
    const height = Math.max(1, Math.round(rect.height * ratio));
    if (canvas.width === width && canvas.height === height) return;
    canvas.width = width;
    canvas.height = height;
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.lineWidth = 2.4;
    ctx.strokeStyle = "#111827";
    // Al cambiar el tamaño el lienzo se limpia: se avisa a .NET para exigir la firma de nuevo.
    setInk(false);
  }

  function setInk(value) {
    if (hasInk === value) return;
    hasInk = value;
    dotnet.invokeMethodAsync("OnInkChanged", value);
  }

  function point(e) {
    const rect = canvas.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  }

  function down(e) {
    if (e.button !== undefined && e.button !== 0) return;
    e.preventDefault();
    canvas.setPointerCapture(e.pointerId);
    drawing = true;
    last = point(e);
    ctx.beginPath();
    ctx.arc(last.x, last.y, ctx.lineWidth / 2, 0, Math.PI * 2);
    ctx.fillStyle = ctx.strokeStyle;
    ctx.fill();
    setInk(true);
  }

  function move(e) {
    if (!drawing) return;
    e.preventDefault();
    const p = point(e);
    ctx.beginPath();
    ctx.moveTo(last.x, last.y);
    ctx.lineTo(p.x, p.y);
    ctx.stroke();
    last = p;
  }

  function up(e) {
    if (!drawing) return;
    drawing = false;
    last = null;
    if (canvas.hasPointerCapture(e.pointerId)) canvas.releasePointerCapture(e.pointerId);
  }

  canvas.style.touchAction = "none"; // evita que el gesto desplace la página mientras se firma
  canvas.addEventListener("pointerdown", down);
  canvas.addEventListener("pointermove", move);
  canvas.addEventListener("pointerup", up);
  canvas.addEventListener("pointercancel", up);
  const observer = new ResizeObserver(() => resize());
  observer.observe(canvas);
  resize();

  return {
    clear() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      setInk(false);
    },
    isEmpty() {
      return !hasInk;
    },
    toPng() {
      return hasInk ? canvas.toDataURL("image/png") : null;
    },
    dispose() {
      observer.disconnect();
      canvas.removeEventListener("pointerdown", down);
      canvas.removeEventListener("pointermove", move);
      canvas.removeEventListener("pointerup", up);
      canvas.removeEventListener("pointercancel", up);
    },
  };
}
