import re
from collections import Counter

from app.rag.safety import (
    attach_safety_metadata,
    classify_query_intent,
    is_restricted_intent,
)
from app.rag.vector_store import search_patient_chunks

SENTENCE_PATTERN = re.compile(r"(?<=[.!?])\s+")
WORD_PATTERN = re.compile(r"[a-zA-Z0-9_]+")
STOP_WORDS = {
    "a",
    "about",
    "and",
    "are",
    "find",
    "for",
    "has",
    "have",
    "is",
    "of",
    "patient",
    "patients",
    "show",
    "the",
    "to",
    "what",
    "which",
    "with",
}


def answer_question(query: str, k: int = 3, patient_id: str | None = None) -> dict:
    intent = classify_query_intent(query)
    search_query = _scoped_query(query, patient_id)
    matches = _search_scoped_chunks(search_query, k, patient_id)
    if not matches:
        return attach_safety_metadata({
            "answer": "No relevant patient information was found in the local HIS index.",
            "intent": intent,
            "sources": [],
            "evidence": [],
        }, query)

    top_patient_id = matches[0]["metadata"]["patient_id"]
    top_patient_name = matches[0]["metadata"]["patient_name"]
    patient_matches = [
        match for match in matches if match["metadata"]["patient_id"] == top_patient_id
    ]
    evidence_items = _select_evidence(query, patient_matches)
    evidence_sentences = [item["text"] for item in evidence_items]

    if is_restricted_intent(intent):
        if evidence_sentences:
            answer = (
                f"I cannot provide diagnosis, treatment, triage, dosage, or medication-change advice. "
                f"The most relevant retrieved dummy record is {top_patient_name} ({top_patient_id}). "
                f"Record evidence only: {' '.join(evidence_sentences)}"
            )
        else:
            answer = (
                f"I cannot provide diagnosis, treatment, triage, dosage, or medication-change advice. "
                f"The most relevant retrieved dummy record is {top_patient_name} ({top_patient_id}); "
                "review the source chunks for evidence."
            )
    elif evidence_sentences:
        evidence_text = " ".join(evidence_sentences)
        answer = (
            f"The most relevant patient is {top_patient_name} ({top_patient_id}). "
            f"Relevant record evidence: {evidence_text}"
        )
    else:
        answer = (
            f"The most relevant patient is {top_patient_name} ({top_patient_id}). "
            "The retrieved record chunks should be reviewed in the sources."
        )

    return attach_safety_metadata({
        "answer": answer,
        "intent": intent,
        "scoped_patient_id": patient_id,
        "evidence": evidence_items,
        "sources": matches,
    }, query)


def _select_evidence(query: str, matches: list[dict]) -> list[dict]:
    query_terms = _keywords(query)
    scored_evidence = []

    for match in matches:
        text = _normalize_chunk_text(match["page_content"])
        metadata = match["metadata"]
        for sentence in SENTENCE_PATTERN.split(text):
            sentence = _clean_sentence(sentence)
            if not sentence:
                continue

            sentence_terms = _keywords(sentence)
            score = sum(sentence_terms[term] for term in query_terms)
            if score > 0:
                scored_evidence.append((
                    score,
                    {
                        "patient_id": metadata.get("patient_id"),
                        "patient_name": metadata.get("patient_name"),
                        "chunk_index": metadata.get("chunk_index"),
                        "score": match.get("score"),
                        "text": sentence,
                    },
                ))

    scored_evidence.sort(key=lambda item: item[0], reverse=True)
    return [evidence for _, evidence in scored_evidence[:3]]


def _keywords(text: str) -> Counter:
    words = WORD_PATTERN.findall(text.lower())
    return Counter(word for word in words if word not in STOP_WORDS and len(word) > 2)


def _normalize_chunk_text(text: str) -> str:
    return text.replace("\n", " ")


def _clean_sentence(sentence: str) -> str:
    sentence = sentence.strip()
    sentence = re.sub(r"\s+", " ", sentence)
    if len(sentence) > 320:
        sentence = sentence[:317].rstrip() + "..."
    return sentence


def _scoped_query(query: str, patient_id: str | None) -> str:
    if not patient_id or patient_id.upper() in query.upper():
        return query
    return f"{query} {patient_id}"


def _search_scoped_chunks(query: str, k: int, patient_id: str | None) -> list[dict]:
    if not patient_id:
        return search_patient_chunks(query, k)

    candidates = search_patient_chunks(query, max(k * 5, k))
    scoped_matches = [
        match
        for match in candidates
        if match["metadata"].get("patient_id", "").upper() == patient_id.upper()
    ]
    return scoped_matches[:k]
