from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.rag.loaders import load_patient_documents
from app.rag.metadata import enrich_chunk_metadata

DEFAULT_CHUNK_SIZE = 700
DEFAULT_CHUNK_OVERLAP = 120


def chunk_documents(
    documents: list[Document],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", "; ", " ", ""],
    )

    chunks = splitter.split_documents(documents)
    for index, chunk in enumerate(chunks):
        chunk.metadata = enrich_chunk_metadata(chunk.page_content, {
            **chunk.metadata,
            "document_type": "patient_record_chunk",
            "chunk_index": index,
            "chunk_size": len(chunk.page_content),
        })

    return chunks


def load_patient_chunks() -> list[Document]:
    documents = load_patient_documents()
    return chunk_documents(documents)
