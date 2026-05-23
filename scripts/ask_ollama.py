import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from app.rag.llm import answer_with_local_llm


def main() -> None:
    query = " ".join(sys.argv[1:]) or "Which patient has diabetes and high HbA1c?"
    result = answer_with_local_llm(query)

    print(f"Question: {query}")
    print(f"Model: {result['model']}")
    print(f"Answer: {result['answer']}")
    print("\nSources:")

    for index, source in enumerate(result["sources"], start=1):
        metadata = source["metadata"]
        print(
            f"{index}. {metadata['patient_id']} - {metadata['patient_name']} "
            f"(score: {source['score']:.3f})"
        )


if __name__ == "__main__":
    main()

