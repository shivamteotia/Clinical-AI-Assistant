import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

os.environ["VECTOR_STORE_PROVIDER"] = "qdrant"

from app.rag.vector_store import search_patient_chunks


def main() -> None:
    query = " ".join(sys.argv[1:]) or "Which patient has diabetes and high HbA1c?"
    matches = search_patient_chunks(query)

    print(f"Query: {query}")
    print(f"Matches: {len(matches)}")

    for index, match in enumerate(matches, start=1):
        metadata = match["metadata"]
        preview = match["page_content"][:220].replace("\n", " ")
        print(
            f"\n{index}. {metadata['patient_id']} - {metadata['patient_name']} "
            f"(score: {match['score']:.3f})"
        )
        print(preview + "...")


if __name__ == "__main__":
    main()
