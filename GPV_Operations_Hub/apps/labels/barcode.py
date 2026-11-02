"""Code 128 encoder (own implementation, ISO/IEC 15417 patterns) and QR matrix via segno.

The encoder returns the symbol value sequence so that SVG/PDF rendering and the ZPL
invocation codes describe exactly the same symbol.
"""
PATTERNS = [
    "212222", "222122", "222221", "121223", "121322", "131222", "122213", "122312", "132212", "221213",
    "221312", "231212", "112232", "122132", "122231", "113222", "123122", "123221", "223211", "221132",
    "221231", "213212", "223112", "312131", "311222", "321122", "321221", "312212", "322112", "322211",
    "212123", "212321", "232121", "111323", "131123", "131321", "112313", "132113", "132311", "211313",
    "231113", "231311", "112133", "112331", "132131", "113123", "113321", "133121", "313121", "211331",
    "231131", "213113", "213311", "213131", "311123", "311321", "331121", "312113", "312311", "332111",
    "314111", "221411", "431111", "111224", "111422", "121124", "121421", "141122", "141221", "112214",
    "112412", "122114", "122411", "142112", "142211", "241211", "221114", "413111", "241112", "134111",
    "111242", "121142", "121241", "114212", "124112", "124211", "411212", "421112", "421211", "212141",
    "214121", "412121", "111143", "111341", "131141", "114113", "114311", "411113", "411311", "113141",
    "114131", "311141", "411131", "211412", "211214", "211232", "2331112",
]
START_A, START_B, START_C, STOP = 103, 104, 105, 106
CODE_A, CODE_B, CODE_C = 101, 100, 99


class BarcodeError(ValueError):
    pass


def _b_value(ch):
    o = ord(ch)
    if 32 <= o <= 127:
        return o - 32
    raise BarcodeError(f"Carácter no codificable en Code 128 B: {ch!r}")


def _a_value(ch):
    o = ord(ch)
    if 32 <= o <= 95:
        return o - 32
    if 0 <= o < 32:
        return o + 64
    raise BarcodeError(f"Carácter no codificable: {ch!r}")


def _digit_run(text, i):
    j = i
    while j < len(text) and text[j].isdigit():
        j += 1
    return j - i


def encode(text):
    """Return (values, segments) where segments is [(set, substring)] for ZPL invocation codes."""
    if not text:
        raise BarcodeError("El contenido del código está vacío.")
    if len(text) > 80:
        raise BarcodeError("Contenido demasiado largo para Code 128 en etiqueta (máx. 80).")
    for ch in text:
        if ord(ch) > 127:
            raise BarcodeError(f"Code 128 solo admite ASCII; «{ch}» no es válido (use QR para acentos).")
    values, segments = [], []
    i = 0
    cur = None

    def use(code_set):
        nonlocal cur
        if cur is None:
            values.append({"A": START_A, "B": START_B, "C": START_C}[code_set])
        elif cur != code_set:
            values.append({"A": CODE_A, "B": CODE_B, "C": CODE_C}[code_set])
        if cur != code_set:
            segments.append([code_set, ""])
        cur = code_set

    while i < len(text):
        run = _digit_run(text, i)
        start_or_end = i == 0 or i + run == len(text)
        if run >= (4 if start_or_end else 6) or (run >= 2 and run == len(text) - i and cur == "C"):
            if run % 2:  # odd run: emit first digit in current set (B) to keep pairs aligned
                if cur is None or cur == "C":
                    use("B")
                values.append(_b_value(text[i]) if cur == "B" else _a_value(text[i]))
                segments[-1][1] += text[i]
                i += 1
                run -= 1
            use("C")
            while run >= 2:
                values.append(int(text[i:i + 2]))
                segments[-1][1] += text[i:i + 2]
                i += 2
                run -= 2
            continue
        ch = text[i]
        if ord(ch) < 32:
            use("A")
            values.append(_a_value(ch))
        else:
            if cur not in ("B", "A") or (cur == "A" and not (32 <= ord(ch) <= 95)):
                use("B")
            values.append(_b_value(ch) if cur == "B" else _a_value(ch))
        segments[-1][1] += ch
        i += 1
    checksum = values[0]
    for pos, v in enumerate(values[1:], start=1):
        checksum += pos * v
    values.append(checksum % 103)
    values.append(STOP)
    return values, [tuple(s) for s in segments]


def modules(text):
    """Bar/space widths (in modules) starting with a bar."""
    values, _ = encode(text)
    widths = []
    for v in values:
        widths.extend(int(x) for x in PATTERNS[v])
    return widths


def total_modules(text):
    return sum(modules(text))


def zpl_data(text):
    """ZPL ^BC field data with explicit invocation codes so the printer builds the same symbol."""
    _values, segments = encode(text)
    out = []
    first = True
    for code_set, chunk in segments:
        if first:
            out.append({"A": ">9", "B": ">:", "C": ">;"}[code_set])
            first = False
        else:
            out.append({"A": ">7", "B": ">6", "C": ">5"}[code_set])
        out.append(chunk.replace(">", "><"))
    return "".join(out)


def qr_matrix(text, error="M"):
    import segno

    if not text:
        raise BarcodeError("El contenido del QR está vacío.")
    try:
        q = segno.make_qr(text, error=error.lower(), boost_error=False)
    except Exception as exc:
        raise BarcodeError(f"No se pudo generar el QR: {exc}")
    return [list(row) for row in q.matrix], q.version
