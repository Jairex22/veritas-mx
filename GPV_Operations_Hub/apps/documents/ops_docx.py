"""Word (DOCX) structural operations with python-docx + lxml.

Blocks are top-level body elements (paragraphs and tables). Sections for selection are
groups of blocks starting at each Heading 1 (or the configured heading level). These are
logical structures, not physical pages: page-based cuts are done on a rendered PDF.
"""
import copy
import io
import re

from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml.ns import qn

from apps.core.jobs import UserFacingError

W_P, W_TBL, W_SECTPR = qn("w:p"), qn("w:tbl"), qn("w:sectPr")
R_EMBED, R_ID, R_LINK = qn("r:embed"), qn("r:id"), qn("r:link")


def open_docx(data):
    try:
        return Document(io.BytesIO(data))
    except Exception as exc:
        raise UserFacingError(f"No se pudo abrir el documento (dañado o no es .docx): {exc.__class__.__name__}")


def _style_name(p_el, doc):
    pstyle = p_el.find(qn("w:pPr") + "/" + qn("w:pStyle"))
    if pstyle is None:
        return "Normal"
    sid = pstyle.get(qn("w:val"))
    try:
        return doc.styles.get_by_id(sid, 1).name if sid else "Normal"
    except Exception:
        return sid or "Normal"


def _heading_level(name):
    m = re.match(r"^(Heading|Título|Titulo)\s*(\d)$", name or "", re.I)
    if m:
        return int(m.group(2))
    if (name or "").lower() in ("title", "título"):
        return 0
    return None


def blocks(doc):
    """List top-level blocks with type, text preview, style and features."""
    out = []
    body = doc.element.body
    for i, el in enumerate(body.iterchildren()):
        if el.tag == W_SECTPR:
            continue
        if el.tag == W_P:
            text = "".join(t.text or "" for t in el.iter(qn("w:t")))
            style = _style_name(el, doc)
            feats = []
            if el.findall(".//" + qn("w:drawing")) or el.findall(".//" + qn("w:pict")):
                feats.append("imagen")
            if el.find(qn("w:pPr") + "/" + qn("w:sectPr")) is not None:
                feats.append("salto de sección")
            if any(br.get(qn("w:type")) == "page" for br in el.iter(qn("w:br"))):
                feats.append("salto de página explícito")
            if el.findall(".//" + qn("w:footnoteReference")):
                feats.append("nota al pie")
            if el.findall(".//" + qn("w:commentReference")):
                feats.append("comentario")
            if el.findall(".//" + qn("w:object")) or el.findall(".//" + qn("w:oleObj")):
                feats.append("objeto incrustado")
            if el.findall(".//" + qn("w:fldSimple")) or el.findall(".//" + qn("w:instrText")):
                feats.append("campo")
            out.append({"index": i, "type": "heading" if _heading_level(style) is not None else "paragraph", "style": style,
                        "level": _heading_level(style), "text": text[:200], "features": feats})
        elif el.tag == W_TBL:
            rows = el.findall(qn("w:tr"))
            first = "".join(t.text or "" for t in rows[0].iter(qn("w:t"))) if rows else ""
            out.append({"index": i, "type": "table", "style": "Tabla", "level": None, "text": f"Tabla {len(rows)} filas: {first[:120]}",
                        "features": []})
        else:
            out.append({"index": i, "type": "other", "style": el.tag.split("}")[-1], "level": None, "text": "(elemento no editable)", "features": ["otro"]})
    return out


def sections(doc, level=1):
    """Group block indices into sections starting at headings <= level."""
    bl = blocks(doc)
    secs, cur = [], {"title": "(inicio del documento)", "blocks": []}
    for b in bl:
        if b["type"] == "heading" and b["level"] is not None and b["level"] <= level:
            if cur["blocks"]:
                secs.append(cur)
            cur = {"title": b["text"] or "(título vacío)", "blocks": []}
        cur["blocks"].append(b["index"])
    if cur["blocks"]:
        secs.append(cur)
    return secs


def analyze(data):
    doc = open_docx(data)
    bl = blocks(doc)
    feats = {}
    for b in bl:
        for f in b["features"]:
            feats[f] = feats.get(f, 0) + 1
    return {"blocks": bl, "sections": sections(doc), "features": feats, "headers": sum(1 for s in doc.sections if s.header.paragraphs),
            "section_count": len(doc.sections)}


def _body_children(doc):
    return [el for el in doc.element.body.iterchildren() if el.tag != W_SECTPR]


def rebuild(data, plan):
    """plan: block indices in the new order; repeated = duplicated; omitted = removed.
    Images in duplicated blocks keep pointing to the same image part (valid inside one document)."""
    doc = open_docx(data)
    body = doc.element.body
    children = list(body.iterchildren())
    content = [el for el in children if el.tag != W_SECTPR]
    sectpr = body.find(W_SECTPR)
    if not plan:
        raise UserFacingError("El documento resultante quedaría vacío.")
    by_index = {i: el for i, el in enumerate(children) if el.tag != W_SECTPR}
    for i in plan:
        if i not in by_index:
            raise UserFacingError(f"El bloque {i} no existe.")
    used = set()
    new = []
    for i in plan:
        el = by_index[i]
        if i in used:
            new.append(copy.deepcopy(el))
        else:
            used.add(i)
            new.append(el)
    for el in content:
        body.remove(el)
    for el in new:
        if sectpr is not None:
            sectpr.addprevious(el)
        else:
            body.append(el)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def combine(files):
    """Append the bodies of the other documents to the first one.

    Images and hyperlinks are re-related into the destination; styles missing in the
    destination, numbering, footnotes, comments, headers and embedded objects are reported
    (their content may lose formatting)."""
    if not files:
        raise UserFacingError("Seleccione documentos.")
    base = open_docx(files[0][1])
    warnings = []
    body = base.element.body
    sectpr = body.find(W_SECTPR)
    base_styles = {s.style_id for s in base.styles}
    for label, data in files[1:]:
        src = open_docx(data)
        missing_styles, unsupported = set(), set()
        src_ids = {s.style_id: s.name for s in src.styles}
        numbered_styles = set()
        for st in src.styles:
            el = getattr(st, "element", None)
            if el is not None and el.find(qn("w:pPr") + "/" + qn("w:numPr")) is not None:
                numbered_styles.add(st.style_id)
        for el in _body_children(src):
            new = copy.deepcopy(el)
            for node in new.iter():
                for attr in (R_EMBED, R_LINK, R_ID):
                    rid = node.get(attr)
                    if not rid:
                        continue
                    rel = src.part.rels.get(rid)
                    if rel is None:
                        continue
                    if rel.is_external:
                        node.set(attr, base.part.relate_to(rel.target_ref, rel.reltype, is_external=True))
                    elif rel.reltype == RT.IMAGE:
                        node.set(attr, base.part.get_or_add_image(io.BytesIO(rel.target_part.blob))[0])
                    else:
                        unsupported.add(rel.reltype.rsplit("/", 1)[-1])
                        node.attrib.pop(attr, None)
                sid = node.get(qn("w:val")) if node.tag in (qn("w:pStyle"), qn("w:rStyle"), qn("w:tblStyle")) else None
                if sid and sid not in base_styles:
                    missing_styles.add(src_ids.get(sid, sid))
                if sid and sid in numbered_styles:
                    unsupported.add("numeración/viñetas (puede cambiar el formato de la lista)")
                if node.tag in (qn("w:footnoteReference"), qn("w:endnoteReference"), qn("w:commentReference")):
                    unsupported.add(node.tag.split("}")[-1])
                if node.tag == qn("w:numPr"):
                    unsupported.add("numeración/viñetas (puede cambiar el formato de la lista)")
            if new.tag == W_P and new.find(qn("w:pPr") + "/" + qn("w:sectPr")) is not None:
                new.find(qn("w:pPr")).remove(new.find(qn("w:pPr") + "/" + qn("w:sectPr")))
                unsupported.add("propiedades de sección (márgenes/orientación) del documento añadido")
            if sectpr is not None:
                sectpr.addprevious(new)
            else:
                body.append(new)
        if missing_styles:
            warnings.append(f"{label}: estilos no presentes en el destino ({', '.join(sorted(missing_styles))}); Word aplicará el estilo predeterminado.")
        if unsupported:
            warnings.append(f"{label}: elementos no soportados al combinar: {', '.join(sorted(unsupported))}.")
        if any(s.header.paragraphs and any(p.text for p in s.header.paragraphs) for s in src.sections):
            warnings.append(f"{label}: sus encabezados/pies de página no se copian (se conservan los del primer documento).")
    buf = io.BytesIO()
    base.save(buf)
    return buf.getvalue(), warnings


def _replace_in_paragraph(p, old, new):
    """Replace text across runs, modifying only the runs that contain the match (keeps formatting)."""
    count = 0
    while True:
        runs = list(p.runs)
        full = "".join(r.text for r in runs)
        pos = full.find(old)
        if pos < 0 or not old:
            return count
        count += 1
        # locate runs
        acc, start_run, start_off = 0, None, 0
        spans = []
        for r in runs:
            spans.append((acc, acc + len(r.text)))
            acc += len(r.text)
        end = pos + len(old)
        first = True
        for r, (a, b) in zip(runs, spans):
            if b <= pos or a >= end:
                continue
            s0, s1 = max(pos, a) - a, min(end, b) - a
            if first:
                r.text = r.text[:s0] + new + r.text[s1:]
                first = False
            else:
                r.text = r.text[:s0] + r.text[s1:]
        if count > 1000:
            return count


def _all_paragraphs(doc):
    for p in doc.paragraphs:
        yield p
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    yield p
    for s in doc.sections:
        for part in (s.header, s.footer):
            for p in part.paragraphs:
                yield p


def replace_text(data, pairs):
    doc = open_docx(data)
    total = 0
    for old, new in pairs:
        for p in _all_paragraphs(doc):
            if old in p.text:
                total += _replace_in_paragraph(p, old, new)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue(), total


def fill_template(data, values):
    """Replace {{campo}} placeholders. Returns (bytes, replaced, missing placeholders)."""
    doc = open_docx(data)
    text = "\n".join(p.text for p in _all_paragraphs(doc))
    found = set(re.findall(r"\{\{\s*([\w.]+)\s*\}\}", text))
    pairs = []
    for key in found:
        if key in values:
            for variant in ("{{" + key + "}}", "{{ " + key + " }}"):
                pairs.append((variant, str(values[key])))
    out, n = replace_text(data, pairs) if pairs else (data, 0)
    return out, n, sorted(found - set(values))
