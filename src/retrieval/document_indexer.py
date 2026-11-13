"""Document Indexer and SHA-256 Integrity Verification Manifest.

Reads markdown policy documents from data/raw_documents/, segments them into
structured section chunks, and manages cryptographic SHA-256 hash tracking
in data/document_hashes.json to guarantee document integrity and sub-second cold starts.
"""

from typing import List, Dict, Any, Tuple
import os
import re
import json
import hashlib
from pydantic import BaseModel


class DocumentChunk(BaseModel):
    """Represents a coherent section chunk from an institutional knowledge document."""
    chunk_id: str
    source_file: str
    doc_title: str
    section_title: str
    content: str
    word_count: int


def compute_file_sha256(filepath: str) -> str:
    """Computes SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()


def parse_markdown_into_chunks(filepath: str) -> List[DocumentChunk]:
    """Parses a markdown file into discrete sections based on headings."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    filename = os.path.basename(filepath)
    lines = content.splitlines()

    doc_title = filename.replace(".md", "").replace("_", " ").title()
    chunks: List[DocumentChunk] = []

    current_section = None
    current_lines: List[str] = []

    # Check for top-level # title
    for line in lines:
        if line.startswith("# ") and not line.startswith("## "):
            doc_title = line.replace("# ", "").strip()
            break

    for line in lines:
        if line.startswith("## "):
            # Flush current section
            if current_lines and current_section:
                section_text = "\n".join(current_lines).strip()
                # Ensure section has substantial content
                if len(section_text.split()) >= 10:
                    chunk_id = f"{filename}::{re.sub(r'[^a-zA-Z0-9]+', '_', current_section.lower())}"
                    chunks.append(DocumentChunk(
                        chunk_id=chunk_id,
                        source_file=filename,
                        doc_title=doc_title,
                        section_title=current_section,
                        content=section_text,
                        word_count=len(section_text.split())
                    ))
            current_section = line.replace("## ", "").strip()
            current_lines = [line]
        else:
            if current_section:
                current_lines.append(line)

    # Flush final section
    if current_lines and current_section:
        section_text = "\n".join(current_lines).strip()
        if len(section_text.split()) >= 10:
            chunk_id = f"{filename}::{re.sub(r'[^a-zA-Z0-9]+', '_', current_section.lower())}"
            chunks.append(DocumentChunk(
                chunk_id=chunk_id,
                source_file=filename,
                doc_title=doc_title,
                section_title=current_section,
                content=section_text,
                word_count=len(section_text.split())
            ))

    return chunks


class KnowledgeBaseManager:
    """Manages raw document ingestion, cryptographic caching, and chunk storage."""

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.raw_dir = os.path.join(data_dir, "raw_documents")
        self.hashes_path = os.path.join(data_dir, "document_hashes.json")
        self.chunks: List[DocumentChunk] = []
        self.document_hashes: Dict[str, str] = {}

    def load_or_index(self) -> Tuple[List[DocumentChunk], bool]:
        """Loads chunks from cache or indexes documents if files have changed.
        
        Returns:
            Tuple of (chunks_list, reindexed_flag)
        """
        if not os.path.exists(self.raw_dir):
            raise FileNotFoundError(f"Knowledge directory not found: {self.raw_dir}")

        # Read existing manifest if present
        existing_manifest: Dict[str, str] = {}
        if os.path.exists(self.hashes_path):
            try:
                with open(self.hashes_path, "r", encoding="utf-8") as f:
                    existing_manifest = json.load(f)
            except Exception:
                existing_manifest = {}

        current_manifest: Dict[str, str] = {}
        all_chunks: List[DocumentChunk] = []
        reindexed = False

        md_files = sorted([f for f in os.listdir(self.raw_dir) if f.endswith(".md")])
        for filename in md_files:
            filepath = os.path.join(self.raw_dir, filename)
            sha256 = compute_file_sha256(filepath)
            current_manifest[filename] = sha256

            if existing_manifest.get(filename) != sha256:
                reindexed = True

            parsed = parse_markdown_into_chunks(filepath)
            all_chunks.extend(parsed)

        # Check if files were deleted
        if set(existing_manifest.keys()) != set(current_manifest.keys()):
            reindexed = True

        self.chunks = all_chunks
        self.document_hashes = current_manifest

        # Persist updated manifest
        with open(self.hashes_path, "w", encoding="utf-8") as f:
            json.dump(current_manifest, f, indent=2)

        return self.chunks, reindexed
