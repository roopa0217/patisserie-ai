"""
Semantic chunker — creates page-level text chunks for the AI assistant's
general knowledge retrieval (separate from the structured recipe chunks).

Each page becomes one chunk. Very long pages (>500 words) are split with
overlap so no context is lost. Stored in the `patisserie-semantic` Pinecone
namespace and never mixed with the structured recipe index.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pdfplumber


def _chunk_id(source_file: str, page: int, offset: int = 0) -> str:
    key = f"sem|{source_file}|{page}|{offset}"
    return "sem_" + hashlib.sha256(key.encode()).hexdigest()[:28]


def create_semantic_chunks(pdf_path: Path) -> list[dict]:
    """
    Return a list of dicts, each with:
      chunk_id, text, source_file, page (1-based)
    """
    pdf_path = Path(pdf_path)
    chunks: list[dict] = []

    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text or len(text.strip()) < 40:
                continue

            words = text.split()

            if len(words) <= 500:
                chunks.append({
                    "chunk_id": _chunk_id(pdf_path.name, i + 1),
                    "text": text.strip(),
                    "source_file": pdf_path.name,
                    "page": i + 1,
                })
            else:
                # Sliding window for very long pages
                chunk_size, overlap = 450, 90
                for start in range(0, len(words), chunk_size - overlap):
                    segment = words[start:start + chunk_size]
                    if len(segment) < 40:
                        continue
                    chunks.append({
                        "chunk_id": _chunk_id(pdf_path.name, i + 1, start),
                        "text": " ".join(segment),
                        "source_file": pdf_path.name,
                        "page": i + 1,
                    })

    return chunks
