"""PowerPoint operations working at the OPC package level (python-pptx internals).

* Reorder / extract / delete keep the original slide parts untouched.
* Duplicate clones the slide part and its private parts (charts with embedded workbooks,
  diagrams, tags); images, media and the slide layout are shared inside the package.
* Merge copies each foreign slide with its layout, master and theme (one copy per source),
  registering the master in the destination presentation, so themes are preserved.
* Speaker notes and comments are not copied when duplicating/merging; this is reported
  before transforming. Slides are never replaced by images.
"""
import copy
import io
import re

from pptx import Presentation
from pptx.opc.constants import RELATIONSHIP_TARGET_MODE as RTM
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.opc.package import PartFactory, _Relationship
from pptx.opc.packuri import PackURI

from apps.core.jobs import UserFacingError

SHARE_IN_SAME_PACKAGE = {RT.IMAGE, RT.MEDIA, RT.VIDEO, RT.AUDIO, RT.SLIDE_LAYOUT, RT.SLIDE}
SKIP = {RT.NOTES_SLIDE, RT.COMMENTS}
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def open_pptx(data):
    try:
        return Presentation(io.BytesIO(data))
    except Exception as exc:
        raise UserFacingError(f"No se pudo abrir la presentación (dañada o no es .pptx): {exc.__class__.__name__}")


def analyze(data):
    prs = open_pptx(data)
    slides = []
    for i, s in enumerate(prs.slides):
        rels = [r for r in s.part.rels.values()]
        types = [r.reltype.rsplit("/", 1)[-1] for r in rels]
        title = ""
        try:
            if s.shapes.title is not None:
                title = s.shapes.title.text_frame.text[:120]
        except Exception:
            title = ""
        if not title:
            for sh in s.shapes:
                if sh.has_text_frame and sh.text_frame.text.strip():
                    title = sh.text_frame.text.strip()[:120]
                    break
        slides.append({
            "index": i, "title": title or f"Diapositiva {i + 1}", "layout": s.slide_layout.name,
            "shapes": len(s.shapes), "pictures": types.count("image"), "charts": types.count("chart"),
            "tables": sum(1 for sh in s.shapes if sh.has_table), "notes": s.has_notes_slide,
            "comments": "comments" in types, "ole": types.count("oleObject") + types.count("package"),
            "media": types.count("video") + types.count("audio") + types.count("media"),
            "smartart": types.count("diagramData"),
            "external_links": sum(1 for r in rels if r.is_external),
            "slide_links": types.count("slide"),
        })
    masters = [m.name if hasattr(m, "name") else "" for m in prs.slide_masters]
    return {"slides": slides, "count": len(slides), "masters": len(masters),
            "size_in": [round(prs.slide_width / 914400, 2), round(prs.slide_height / 914400, 2)]}


def preservation_warnings(analysis, op, indices=None):
    warn = []
    sl = [s for s in analysis["slides"] if indices is None or s["index"] in indices]
    if op in ("duplicate", "merge"):
        n = sum(1 for s in sl if s["notes"])
        if n:
            warn.append(f"{n} diapositiva(s) tienen notas del orador: las copias (duplicadas o combinadas) no incluyen las notas.")
        n = sum(1 for s in sl if s["comments"])
        if n:
            warn.append(f"{n} diapositiva(s) tienen comentarios: no se copian.")
    if op == "merge":
        n = sum(1 for s in sl if s["slide_links"])
        if n:
            warn.append(f"{n} diapositiva(s) tienen vínculos a otras diapositivas: esos vínculos se eliminan en la combinación.")
    n = sum(1 for s in sl if s["ole"])
    if n:
        warn.append(f"{n} diapositiva(s) tienen objetos incrustados (OLE): se copian como partes del paquete, pero su edición depende de la aplicación de origen.")
    n = sum(1 for s in sl if s["external_links"])
    if n:
        warn.append(f"{n} diapositiva(s) tienen vínculos externos: se conservan como enlaces, no se descargan.")
    return warn


class _Cloner:
    def __init__(self, package, share_types):
        self.package = package
        self.share = share_types
        self.memo = {}
        self.used = {str(p.partname) for p in package.iter_parts()}
        self.dropped = []

    def partname(self, src_name):
        s = str(src_name)
        m = re.match(r"^(.*?)(\d+)(\.\w+)$", s)
        tmpl = (m.group(1) + "%d" + m.group(3)) if m else s.rsplit(".", 1)[0] + "%d." + s.rsplit(".", 1)[1]
        n = 1
        while tmpl % n in self.used:
            n += 1
        name = tmpl % n
        self.used.add(name)
        return PackURI(name)

    def clone(self, part):
        if part in self.memo:
            return self.memo[part]
        new = PartFactory(self.partname(part.partname), part.content_type, self.package, part.blob)
        self.memo[part] = new
        rels = new.rels._rels
        for rId, rel in part.rels.items():
            if rel.is_external:
                rels[rId] = _Relationship(new.partname.baseURI, rId, rel.reltype, RTM.EXTERNAL, rel.target_ref)
                continue
            if rel.reltype in SKIP:
                continue
            tgt = rel.target_part
            if rel.reltype in self.share and tgt.package is self.package:
                new_tgt = tgt
            elif rel.reltype == RT.SLIDE and tgt.package is not self.package:
                self.dropped.append((new, rId))
                continue
            else:
                new_tgt = self.clone(tgt)
            rels[rId] = _Relationship(new.partname.baseURI, rId, rel.reltype, RTM.INTERNAL, new_tgt)
        return new

    def strip_dropped_links(self):
        for part, rId in self.dropped:
            el = getattr(part, "_element", None)
            if el is None:
                continue
            for node in el.xpath(f'//*[@r:id="{rId}"]'):
                node.getparent().remove(node)


def _sld_id_lst(prs):
    return prs.slides._sldIdLst


def _next_slide_id(prs):
    ids = [int(s.get("id")) for s in _sld_id_lst(prs)]
    return max(ids + [255]) + 1


def _add_slide_part(prs, slide_part):
    rId = prs.part.relate_to(slide_part, RT.SLIDE)
    lst = _sld_id_lst(prs)
    el = lst.makeelement("{http://schemas.openxmlformats.org/presentationml/2006/main}sldId", {})
    el.set("id", str(_next_slide_id(prs)))
    el.set(f"{{{NS_R}}}id", rId)
    lst.append(el)
    return el


def rebuild(data, plan):
    """plan: list of slide indices (0-based) in the desired order; repeated index = duplicate."""
    prs = open_pptx(data)
    lst = _sld_id_lst(prs)
    original = list(lst)
    n = len(original)
    if not plan:
        raise UserFacingError("La presentación resultante no tendría diapositivas.")
    for i in plan:
        if i < 0 or i >= n:
            raise UserFacingError(f"La diapositiva {i + 1} no existe.")
    used = set()
    new_order = []
    cloner = _Cloner(prs.part.package, SHARE_IN_SAME_PACKAGE)
    for i in plan:
        el = original[i]
        if i not in used:
            used.add(i)
            new_order.append(el)
        else:
            src_part = prs.part.related_part(el.get(f"{{{NS_R}}}id"))
            cloner.memo = {}
            new_part = cloner.clone(src_part)
            dup = _add_slide_part(prs, new_part)
            lst.remove(dup)
            new_order.append(dup)
    for idx, el in enumerate(original):
        if idx not in used:
            prs.part.drop_rel(el.get(f"{{{NS_R}}}id"))
    for el in list(lst):
        lst.remove(el)
    for el in new_order:
        lst.append(el)
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def merge(files):
    """files: list of (data, [indices] or None). The first file is the base (keeps its slide size)."""
    if not files:
        raise UserFacingError("Seleccione presentaciones para combinar.")
    base_data, base_sel = files[0]
    base = open_pptx(rebuild(base_data, base_sel) if base_sel is not None else base_data)
    warnings = []
    pkg = base.part.package
    pres_el = base.part._element
    ns_p = "http://schemas.openxmlformats.org/presentationml/2006/main"
    master_lst = pres_el.find(f"{{{ns_p}}}sldMasterIdLst")
    for data, sel in files[1:]:
        src = open_pptx(data)
        if (src.slide_width, src.slide_height) != (base.slide_width, base.slide_height):
            warnings.append("Una presentación tiene distinto tamaño de diapositiva; su contenido conserva coordenadas originales y puede verse desplazado.")
        cloner = _Cloner(pkg, set())
        src_slides = list(src.slides)
        indices = sel if sel is not None else list(range(len(src_slides)))
        for i in indices:
            if i < 0 or i >= len(src_slides):
                raise UserFacingError(f"La diapositiva {i + 1} no existe en una de las presentaciones.")
            new_slide = cloner.clone(src_slides[i].part)
            _add_slide_part(base, new_slide)
        # register the cloned masters
        all_ids = [int(e.get("id")) for e in master_lst] if master_lst is not None else []
        for m in base.slide_masters:
            all_ids += [int(e.get("id")) for e in m._element.findall(f".//{{{ns_p}}}sldLayoutId")]
        next_id = max(all_ids + [2147483647]) + 1
        for src_part, new_part in cloner.memo.items():
            if new_part.content_type.endswith("slideMaster+xml"):
                for lid in new_part._element.findall(f".//{{{ns_p}}}sldLayoutId"):
                    lid.set("id", str(next_id))
                    next_id += 1
                rId = base.part.relate_to(new_part, RT.SLIDE_MASTER)
                el = master_lst.makeelement(f"{{{ns_p}}}sldMasterId", {})
                el.set("id", str(next_id))
                next_id += 1
                el.set(f"{{{NS_R}}}id", rId)
                master_lst.append(el)
        cloner.strip_dropped_links()
    buf = io.BytesIO()
    base.save(buf)
    return buf.getvalue(), warnings


def verify(data):
    """Re-open the result and check every relationship target exists (used by tests and after ops)."""
    prs = open_pptx(data)
    problems = []
    for i, s in enumerate(prs.slides):
        for rId in s.part._element.xpath("//@r:id | //@r:embed | //@r:link"):
            if rId not in s.part.rels:
                problems.append(f"Diapositiva {i + 1}: referencia {rId} sin relación")
    return problems
