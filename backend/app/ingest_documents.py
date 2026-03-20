"""
One-time ingest: load all documents from the project's documents/ folder into the DB and ChromaDB.
Run from backend directory: python -m app.ingest_documents
Ingest a single file:       python -m app.ingest_documents "A+step++by+step+guide+to+setup+SA+App+on+local+machine.doc"

After this, use the application UI to add or update any new cases.
"""
import asyncio
import logging
import sys
import uuid
from pathlib import Path

from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal, DocumentUpload, Service, init_db
from app.document_loader import load_and_chunk_file, SUPPORTED_EXTENSIONS
from app.rag import add_chunks_to_collection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# documents/ folder: sibling of backend/ (oncall-rag-assistant/documents)
DOCUMENTS_DIR = Path(__file__).resolve().parent.parent.parent / "documents"


def _infer_service_from_filename(filename: str) -> str:
    """Infer CRM vs SA from filename. Default CRM."""
    name_upper = filename.upper()
    if "SA" in name_upper and "CRM" not in name_upper:
        return "SA"
    return "CRM"


async def ensure_services(session) -> dict:
    """Get or create CRM and SA services. Returns mapping name -> service id."""
    result = {}
    for name in ("CRM", "SA"):
        r = await session.execute(select(Service).where(Service.name == name))
        s = r.scalar_one_or_none()
        if not s:
            s = Service(name=name, description=f"On-call runbooks for {name}")
            session.add(s)
            await session.flush()
            await session.refresh(s)
            logger.info("Created service: %s (id=%s)", name, s.id)
        result[name] = s.id
    return result


async def ingest_one(session, file_path: Path, service_id: int, filename: str) -> tuple[bool, int, str]:
    """Ingest a single file. Returns (success, chunk_count, error_message)."""
    try:
        chunks = load_and_chunk_file(
            str(file_path),
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
    except Exception as e:
        return False, 0, str(e)
    if not chunks:
        return False, 0, "No text extracted"
    upload_id = str(uuid.uuid4())
    ids = [str(uuid.uuid4()) for _ in chunks]
    metadatas = [
        {
            "type": "upload",
            "service_id": str(service_id),
            "filename": filename,
            "upload_id": upload_id,
            "chunk_id": i,
        }
        for i in ids
    ]
    add_chunks_to_collection(chunks, metadatas=metadatas, ids=ids)
    rec = DocumentUpload(
        service_id=service_id,
        filename=filename,
        upload_id=upload_id,
        chunk_count=len(chunks),
    )
    session.add(rec)
    await session.flush()
    return True, len(chunks), ""


async def run_ingest(single_filename: str | None = None):
    await init_db()
    if not DOCUMENTS_DIR.is_dir():
        logger.error("Documents dir not found: %s", DOCUMENTS_DIR)
        return
    async with AsyncSessionLocal() as session:
        try:
            name_to_id = await ensure_services(session)
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.exception("Failed to ensure services")
            raise
    # Re-open session for ingest (we committed services)
    all_files = [f for f in DOCUMENTS_DIR.iterdir() if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS]
    if single_filename:
        single = single_filename.strip()
        # Allow absolute or relative path to a file outside documents/
        path = Path(single)
        if path.is_file():
            files = [path]
            logger.info("Single-file ingest (by path): %s", path)
        else:
            # Match by name in documents/ (optionally add extension if missing)
            candidate = path.name if path.suffix else single
            if candidate and Path(candidate).suffix.lower() not in SUPPORTED_EXTENSIONS:
                # Try common extensions so "myfile" can match myfile.txt
                for ext in (".txt", ".md", ".pdf", ".doc", ".docx"):
                    p = DOCUMENTS_DIR / (candidate + ext)
                    if p.is_file():
                        candidate = p.name
                        break
            files = [f for f in all_files if f.name == candidate or f.stem == Path(candidate).stem]
            if not files:
                logger.error("File not found: %s (not a path and not in %s)", single, DOCUMENTS_DIR)
                return
            logger.info("Single-file ingest: %s", files[0].name)
    else:
        files = sorted(all_files)
    if not files:
        logger.warning(
            "No supported files in %s. Supported: %s. Copy files there or run with a path: python -m app.ingest_documents /path/to/file",
            DOCUMENTS_DIR,
            ", ".join(SUPPORTED_EXTENSIONS),
        )
        return
    logger.info("Found %s file(s) to ingest in %s", len(files), DOCUMENTS_DIR)
    total_chunks = 0
    async with AsyncSessionLocal() as session:
        try:
            name_to_id = await ensure_services(session)
            for file_path in files:
                filename = file_path.name
                service_name = _infer_service_from_filename(filename)
                service_id = name_to_id[service_name]
                ok, count, err = await ingest_one(session, file_path, service_id, filename)
                if ok:
                    total_chunks += count
                    logger.info("Ingested %s -> %s (%s chunks)", filename, service_name, count)
                else:
                    logger.warning("Skip %s: %s", filename, err)
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.exception("Ingest failed")
            raise
    logger.info("Done. Total chunks indexed: %s. Use the app to search or add new cases.", total_chunks)


def main():
    single = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(run_ingest(single_filename=single))


if __name__ == "__main__":
    main()
