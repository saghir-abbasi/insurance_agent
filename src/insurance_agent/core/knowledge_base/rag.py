"""Retrieval-augmented knowledge base over the Final Expense insurance FAQ.

Chunks the source document (Markdown/text split per Q&A block or heading, or
PDF split per page), embeds with fastembed `BAAI/bge-base-en-v1.5`, and
stores vectors in a persistent Chroma collection. Exposes a small `query`
API used by the `search_knowledge_base` tool that the realtime agent calls
when the customer asks something outside the scripted qualification.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, cast

import chromadb
import pypdf
from fastembed import TextEmbedding

from insurance_agent.core.utils.logger import logger_config

logger = logger_config(__name__)

EMBEDDING_MODEL_NAME = "BAAI/bge-base-en-v1.5"
COLLECTION_NAME = "final_expense_kb"

# Project root: src/insurance_agent/core/knowledge_base/rag.py -> 4 levels up.
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_SOURCE_PATH = _PROJECT_ROOT / "data" / "final_expense_faq.md"
DEFAULT_PERSIST_DIR = _PROJECT_ROOT / "data" / "chroma"

# Chunk roughly 800 characters with a 120-character overlap. The source is a
# Q&A document, so we want chunks large enough to keep a question and its
# answer together but small enough that retrieval stays focused.
CHUNK_SIZE = 800
CHUNK_OVERLAP = 120

_TEXT_SUFFIXES = {".md", ".markdown", ".txt"}

# A new section starts at a "Q<n>:" line or a Markdown heading.
_SECTION_START = re.compile(r"^(?:Q\d+\s*[:.)]|#{1,6}\s)", re.IGNORECASE)


@dataclass
class RetrievedChunk:
    text: str
    score: float
    source_page: int | None
    """Page (PDF) or section number (Markdown/text) the chunk came from."""


def _clean(text: str) -> str:
    text = text.replace(" ", " ")
    # Strip Word's private-use bullet glyphs and other PUA characters so the
    # output is safe for any non-UTF-8 console and adds no noise for the LLM.
    text = re.sub(r"[-]", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _chunk(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        # Prefer to break at a paragraph or sentence boundary near the end.
        if end < len(text):
            window = text[start:end]
            for sep in ("\n\n", "\n", ". ", "? ", "! "):
                idx = window.rfind(sep)
                if idx != -1 and idx > size // 2:
                    end = start + idx + len(sep)
                    break
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def _load_pdf_pages(pdf_path: Path) -> list[tuple[int, str]]:
    reader = pypdf.PdfReader(str(pdf_path))
    pages: list[tuple[int, str]] = []
    for i, page in enumerate(reader.pages):
        raw = page.extract_text() or ""
        cleaned = _clean(raw)
        if cleaned:
            pages.append((i + 1, cleaned))
    return pages


def _load_text_sections(text_path: Path) -> list[tuple[int, str]]:
    """Split a Markdown/text Q&A file so each question stays with its answer."""
    sections: list[list[str]] = []
    for line in text_path.read_text(encoding="utf-8").splitlines():
        if _SECTION_START.match(line.strip()) or not sections:
            sections.append([])
        sections[-1].append(line)
    out: list[tuple[int, str]] = []
    for lines in sections:
        cleaned = _clean("\n".join(lines))
        if cleaned:
            out.append((len(out) + 1, cleaned))
    return out


def _load_source_sections(source_path: Path) -> list[tuple[int, str]]:
    if source_path.suffix.lower() in _TEXT_SUFFIXES:
        return _load_text_sections(source_path)
    return _load_pdf_pages(source_path)


def _file_fingerprint(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


class KnowledgeBase:
    """Persistent Chroma + fastembed wrapper for the Final Expense FAQ corpus."""

    def __init__(
        self,
        source_path: Path = DEFAULT_SOURCE_PATH,
        persist_dir: Path = DEFAULT_PERSIST_DIR,
        embedding_model_name: str = EMBEDDING_MODEL_NAME,
        collection_name: str = COLLECTION_NAME,
    ) -> None:
        self.source_path = Path(source_path)
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.embedding_model_name = embedding_model_name
        self.collection_name = collection_name

        self._embedder: TextEmbedding | None = None
        self._client = chromadb.PersistentClient(path=str(self.persist_dir))
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    @property
    def embedder(self) -> TextEmbedding:
        if self._embedder is None:
            logger.info(f"Loading fastembed model: {self.embedding_model_name}")
            self._embedder = TextEmbedding(model_name=self.embedding_model_name)
        return self._embedder

    def _embed(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in self.embedder.embed(texts)]

    def ingest(self, force: bool = False) -> int:
        """Chunk the source document and (re)populate the Chroma collection.

        Re-ingests only when the source's content fingerprint differs from the
        one stored in the collection metadata, unless `force=True`.

        Returns the number of chunks now indexed.
        """
        if not self.source_path.exists():
            raise FileNotFoundError(
                f"Knowledge base source not found: {self.source_path}"
            )

        fingerprint = _file_fingerprint(self.source_path)
        existing_meta = self._collection.metadata or {}
        if (
            not force
            and existing_meta.get("source_fingerprint") == fingerprint
            and self._collection.count() > 0
        ):
            logger.info(
                f"Knowledge base already up to date "
                f"({self._collection.count()} chunks)."
            )
            return self._collection.count()

        logger.info(f"Ingesting knowledge base from {self.source_path}")
        pages = _load_source_sections(self.source_path)
        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict] = []
        for page_num, page_text in pages:
            for j, chunk in enumerate(_chunk(page_text)):
                ids.append(f"p{page_num}-c{j}")
                documents.append(chunk)
                metadatas.append({"page": page_num, "chunk": j})

        if not documents:
            logger.warning(
                "No text extracted from the source; knowledge base will be empty."
            )
            return 0

        # Recreate the collection so stale chunks from a previous version are
        # dropped. Cosine distance + the new fingerprint go in metadata.
        self._client.delete_collection(self.collection_name)
        self._collection = self._client.create_collection(
            name=self.collection_name,
            metadata={
                "hnsw:space": "cosine",
                "source_fingerprint": fingerprint,
            },
        )

        # Embed in batches to keep memory bounded.
        batch_size = 64
        for start in range(0, len(documents), batch_size):
            batch_docs = documents[start : start + batch_size]
            batch_ids = ids[start : start + batch_size]
            batch_meta = metadatas[start : start + batch_size]
            batch_emb = self._embed(batch_docs)
            self._collection.add(
                ids=batch_ids,
                documents=batch_docs,
                metadatas=cast(Any, batch_meta),
                embeddings=cast(Any, batch_emb),
            )

        logger.info(f"Indexed {len(documents)} chunks into {self.collection_name}.")
        return len(documents)

    def query(self, question: str, k: int = 4) -> list[RetrievedChunk]:
        if not question.strip():
            return []
        if self._collection.count() == 0:
            return []
        embedding = self._embed([question])[0]
        result = self._collection.query(
            query_embeddings=cast(Any, [embedding]),
            n_results=k,
            include=cast(Any, ["documents", "metadatas", "distances"]),
        )
        docs = (result.get("documents") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        dists = (result.get("distances") or [[]])[0]
        out: list[RetrievedChunk] = []
        for doc, meta, dist in zip(docs, metas, dists):
            score = 1.0 - float(dist) if dist is not None else 0.0
            raw_page = meta.get("page") if meta else None
            page = (
                int(raw_page)
                if isinstance(raw_page, (int, float, str)) and str(raw_page).strip()
                else None
            )
            out.append(RetrievedChunk(text=doc, score=score, source_page=page))
        return out


_kb_singleton: KnowledgeBase | None = None
_kb_lock = Lock()


def get_knowledge_base() -> KnowledgeBase:
    global _kb_singleton
    with _kb_lock:
        if _kb_singleton is None:
            _kb_singleton = KnowledgeBase()
        return _kb_singleton


def main() -> None:
    """`uv run ingest`: build/refresh the vector store (pass --force to rebuild)."""
    import sys

    count = get_knowledge_base().ingest(force="--force" in sys.argv)
    print(f"Knowledge base ready: {count} chunks.")
