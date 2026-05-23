import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from app.rag.chunking import load_patient_chunks


def main() -> None:
    chunks = load_patient_chunks()
    print(f"Created {len(chunks)} LangChain chunks")

    for chunk in chunks:
        patient_id = chunk.metadata["patient_id"]
        patient_name = chunk.metadata["patient_name"]
        chunk_index = chunk.metadata["chunk_index"]
        chunk_size = chunk.metadata["chunk_size"]
        preview = chunk.page_content[:180].replace("\n", " ")
        print(f"\n[{chunk_index}] {patient_id} - {patient_name} ({chunk_size} chars)")
        print(preview + "...")


if __name__ == "__main__":
    main()

