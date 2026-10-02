from datetime import date

from models.domain import ConflictInfo, RetrievedChunk
from rag.confidence import compute_confidence
from rag.conflicts import detect_conflicts
from rag.embeddings import HashingEmbedder
from rag.lexical import BM25


def _hit(doc, text, relevance=0.9, coverage=0.9, source_type="Procedure", demo=False, review="2099-01-01"):
    return RetrievedChunk(chunk_id=f"c-{doc}", document_id=doc, version_id=f"v-{doc}", doc_code=doc, title=doc,
                          version_label="1.0", source_type=source_type, classification="Internal", section="s",
                          page=None, text=text, review_date=review, is_demo=demo, relevance=relevance,
                          coverage=coverage)


def test_hashing_embedder_similarity():
    emb = HashingEmbedder(256)
    v = emb.embed(["revisar estado de work order", "revisar estado de la work order", "calibrar impresora"])
    assert v.shape == (3, 256)
    assert float(v[0] @ v[1]) > float(v[0] @ v[2])


def test_bm25_ranks_relevant_first():
    bm = BM25([("a", "certificación de operador vencida"), ("b", "etiqueta de embarque")])
    assert bm.search(["certificado", "operador"], 5)[0][0] == "a"


def test_numeric_conflict_detected():
    a = _hit("WI", "Una unidad que falla la prueba ICT puede reintentarse un máximo de 3 veces antes de Repair.")
    b = _hit("KB", "Una unidad que falla la prueba ICT puede reintentarse un máximo de 5 veces antes de Repair.")
    conflicts = detect_conflicts([a, b], 0.4)
    assert conflicts and conflicts[0].kind == "numeric"


def test_polarity_conflict_and_no_false_positive():
    a = _hit("A", "El operador debe cerrar la sesión de FactoryLogix al terminar el turno.")
    b = _hit("B", "El operador no debe cerrar la sesión de FactoryLogix al terminar el turno.")
    c = _hit("C", "La etiqueta debe coincidir con el serial y la revisión de la orden.")
    assert detect_conflicts([a, b], 0.4)[0].kind == "polarity"
    assert detect_conflicts([a, c], 0.4) == []


def test_confidence_rules():
    today = date(2026, 1, 1)
    assert compute_confidence([], [], min_relevance=0.4, high=0.75, medium=0.55, today_=today).level == "None"
    strong = [_hit("P1", "x", 0.95), _hit("P2", "y", 0.9)]
    assert compute_confidence(strong, [], min_relevance=0.4, high=0.75, medium=0.55, today_=today).level == "High"
    demo = [_hit("P1", "x", 0.95, demo=True), _hit("P2", "y", 0.9)]
    assert compute_confidence(demo, [], min_relevance=0.4, high=0.75, medium=0.55, today_=today).level == "Medium"
    conflict = [ConflictInfo("a", "b", "x", "y", "numeric")]
    res = compute_confidence(strong, conflict, min_relevance=0.4, high=0.75, medium=0.55, today_=today)
    assert res.level == "Low" and res.score < 0.55
    overdue = [_hit("P1", "x", 0.95, review="2020-01-01")]
    res = compute_confidence(overdue, [], min_relevance=0.4, high=0.75, medium=0.55, today_=today)
    assert "revisión vencida" in res.reasons and res.score <= 0.95


def test_textual_similarity_alone_is_not_high_confidence():
    today = date(2026, 1, 1)
    faq_only = [_hit("F1", "x", 0.75, source_type="FAQ", review="")]
    assert compute_confidence(faq_only, [], min_relevance=0.4, high=0.75, medium=0.55, today_=today).level != "High"
