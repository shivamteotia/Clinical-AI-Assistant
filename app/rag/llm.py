import ollama

from app.rag.safety import attach_safety_metadata
from app.rag.vector_store import search_patient_chunks

DEFAULT_MODEL = "phi3"


def answer_with_local_llm(query: str, k: int = 3, model: str = DEFAULT_MODEL) -> dict:
    sources = search_patient_chunks(query, k)
    context = _format_context(sources)
    prompt = _build_prompt(query, context)

    response = ollama.chat(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a clinical AI prototype assistant. Use only the provided "
                    "local HIS context. Do not invent facts. If the context does not "
                    "contain enough evidence, say that clearly. Do not provide medical "
                    "advice, diagnosis, or treatment instructions beyond summarizing "
                    "what is present in the dummy patient record. Avoid clinical severity "
                    "judgments or lab interpretation unless they are explicitly stated "
                    "in the context."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    )

    return attach_safety_metadata({
        "answer": response["message"]["content"],
        "model": model,
        "sources": sources,
    }, query)


def _format_context(sources: list[dict]) -> str:
    if not sources:
        return "No context was retrieved."

    sections = []
    for index, source in enumerate(sources, start=1):
        metadata = source["metadata"]
        sections.append(
            "\n".join(
                [
                    f"Source {index}",
                    f"patient_id: {metadata['patient_id']}",
                    f"patient_name: {metadata['patient_name']}",
                    f"score: {source['score']:.3f}",
                    "content:",
                    source["page_content"],
                ]
            )
        )

    return "\n\n".join(sections)


def _build_prompt(query: str, context: str) -> str:
    return f"""
Question:
{query}

Retrieved local HIS context:
{context}

Answer requirements:
- Answer in 3 to 5 concise sentences.
- Mention the relevant patient ID and name when available.
- Base the answer only on the retrieved context.
- Include a short "Evidence:" sentence.
- Do not discuss other patients unless the question asks for comparison.
- Do not add missing-evidence speculation unless the retrieved context is insufficient.
- For lab values, state the value and reference range without interpreting severity.
""".strip()
