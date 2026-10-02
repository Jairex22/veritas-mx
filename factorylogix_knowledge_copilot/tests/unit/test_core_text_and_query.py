from core.text import content_terms, detect_language, normalize, term_key
from rag.query import Glossary, analyze, coverage


def test_normalize_and_language():
    assert normalize("Genealogía ÁRBOL") == "genealogia arbol"
    assert detect_language("¿Cómo reviso el estado de una Work Order?") == "es"
    assert detect_language("How do I check the status of a work order?") == "en"


def test_term_key_groups_variants():
    assert term_key("certificado") == term_key("certification") == "certif"
    assert term_key("unidades") == "unidad"
    assert "como" not in content_terms("¿Cómo reviso la orden?")


def test_glossary_expansion_bilingual_coverage():
    glossary = Glossary([["work order", "orden de trabajo"], ["status", "estado"]])
    q = analyze("How do I check the status of a work order?", glossary)
    assert len(q.concepts) == 2
    assert coverage(q, "Revisa el estado de la orden de trabajo") == 1.0
    assert coverage(q, "Texto sin relación alguna") == 0.0


def test_out_of_domain_has_no_coverage():
    q = analyze("¿Cuál es la capital de Francia?", Glossary([]))
    assert coverage(q, "Revisa el estado de la Work Order en FactoryLogix") == 0.0
