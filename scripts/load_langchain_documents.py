import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from app.rag.loaders import load_patient_documents


def main() -> None:
    documents = load_patient_documents()
    print(f"Loaded {len(documents)} LangChain patient documents")

    for document in documents:
        patient_id = document.metadata["patient_id"]
        patient_name = document.metadata["patient_name"]
        preview = document.page_content[:300].replace("\n", " ")
        print(f"\n[{patient_id}] {patient_name}")
        print(preview + "...")


if __name__ == "__main__":
    main()
