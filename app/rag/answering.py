import re
from collections import Counter

from app.rag.safety import attach_safety_metadata
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


def answer_question(query: str, k: int = 3) -> dict:
    matches = search_patient_chunks(query, k)
    if not matches:
        return attach_safety_metadata({
            "answer": "No relevant patient information was found in the local HIS index.",
            "sources": [],
        })

    top_patient_id = matches[0]["metadata"]["patient_id"]
    top_patient_name = matches[0]["metadata"]["patient_name"]
    patient_matches = [
        match for match in matches if match["metadata"]["patient_id"] == top_patient_id
    ]
    evidence_sentences = _select_evidence_sentences(query, patient_matches)

    if evidence_sentences:
        evidence = " ".join(evidence_sentences)
        answer = (
            f"The most relevant patient is {top_patient_name} ({top_patient_id}). "
            f"Relevant record evidence: {evidence}"
        )
    else:
        answer = (
            f"The most relevant patient is {top_patient_name} ({top_patient_id}). "
            "The retrieved record chunks should be reviewed in the sources."
        )

    return attach_safety_metadata({
        "answer": answer,
        "sources": matches,
    })


def _select_evidence_sentences(query: str, matches: list[dict]) -> list[str]:
    query_terms = _keywords(query)
    scored_sentences = []

    for match in matches:
        text = _normalize_chunk_text(match["page_content"])
        for sentence in SENTENCE_PATTERN.split(text):
            sentence = _clean_sentence(sentence)
            if not sentence:
                continue

            sentence_terms = _keywords(sentence)
            score = sum(sentence_terms[term] for term in query_terms)
            if score > 0:
                scored_sentences.append((score, sentence))

    scored_sentences.sort(key=lambda item: item[0], reverse=True)
    return [sentence for _, sentence in scored_sentences[:3]]


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
