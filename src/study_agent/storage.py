"""Persistent local SQLite index for source documents and extracted chunks."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import struct
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from study_agent.chunking import Chunk
from study_agent.embeddings import INPUT_VERSION, EmbeddingProfile, input_hash, validate_vector

SCHEMA_VERSION = 2


def default_database_path() -> Path:
    # Optional isolation for developer builds and packaged-helper smoke tests.
    if data_directory := os.environ.get("STUDY_AGENT_DATA_DIR"):
        return Path(data_directory).expanduser() / "index.sqlite3"
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library/Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return base / "Study Agent" / "index.sqlite3"


class IndexStorage:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_database_path()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path.parent.chmod(0o700)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise RuntimeError("Index database was created by a newer Study Agent")
            existing_fts = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='chunks_fts'"
            ).fetchone()
            if version == SCHEMA_VERSION and existing_fts:
                if not self._fts_available(db):
                    # The ordinary chunks remain authoritative while FTS5 is absent.
                    db.execute("BEGIN IMMEDIATE")
                    for trigger in ("chunks_ai", "chunks_ad", "chunks_au"):
                        db.execute(f"DROP TRIGGER IF EXISTS {trigger}")
                    db.commit()
                    self.fts = False
                    return
                triggers = db.execute(
                    "SELECT count(*) FROM sqlite_master WHERE type='trigger' "
                    "AND name IN ('chunks_ai','chunks_ad','chunks_au')"
                ).fetchone()[0]
                if triggers == 3:
                    self.fts = True
                    return
                # FTS5 has returned: recreate triggers and rebuild stale postings.
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                schema = """
                    CREATE TABLE IF NOT EXISTS sources (
                        id TEXT PRIMARY KEY, root TEXT NOT NULL UNIQUE, indexed_at TEXT
                    );
                    CREATE TABLE IF NOT EXISTS documents (
                        id TEXT PRIMARY KEY,
                        source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                        relative_path TEXT NOT NULL, title TEXT NOT NULL, format TEXT NOT NULL,
                        size_bytes INTEGER NOT NULL, modified_ns INTEGER NOT NULL,
                        content_hash TEXT, version TEXT NOT NULL, state TEXT NOT NULL,
                        indexed_at TEXT, warnings TEXT NOT NULL DEFAULT '[]', error_code TEXT,
                        UNIQUE(source_id, relative_path)
                    );
                    CREATE TABLE IF NOT EXISTS chunks (
                        id TEXT PRIMARY KEY,
                        document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                        ordinal INTEGER NOT NULL, text TEXT NOT NULL, page_number INTEGER,
                        heading TEXT, marker TEXT, extraction_type TEXT NOT NULL,
                        UNIQUE(document_id, ordinal)
                    );
                    CREATE INDEX IF NOT EXISTS documents_source ON documents(source_id);
                    CREATE INDEX IF NOT EXISTS chunks_document ON chunks(document_id);
                """
                for statement in schema.split(";"):
                    if statement.strip():
                        db.execute(statement)
            if version < 2:
                db.execute("""
                    CREATE TABLE embedding_profiles (
                        fingerprint TEXT PRIMARY KEY, model TEXT NOT NULL,
                        model_digest TEXT NOT NULL,
                        dimensions INTEGER NOT NULL CHECK(dimensions > 0),
                        document_prefix TEXT NOT NULL, query_prefix TEXT NOT NULL,
                        input_version INTEGER NOT NULL
                    )
                """)
                db.execute("""
                    CREATE TABLE chunk_embeddings (
                        chunk_id TEXT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
                        model_fingerprint TEXT NOT NULL
                            REFERENCES embedding_profiles(fingerprint) ON DELETE CASCADE,
                        input_hash TEXT NOT NULL, dimensions INTEGER NOT NULL CHECK(dimensions > 0),
                        vector BLOB NOT NULL CHECK(length(vector) = dimensions * 4),
                        PRIMARY KEY(chunk_id, model_fingerprint)
                    )
                """)
                db.execute("""
                    CREATE TRIGGER chunk_embeddings_update AFTER UPDATE OF text,heading ON chunks
                    WHEN old.text IS NOT new.text OR old.heading IS NOT new.heading BEGIN
                        DELETE FROM chunk_embeddings WHERE chunk_id=new.id;
                    END
                """)
                db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self.fts = self._ensure_fts(db)
            db.commit()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA busy_timeout=5000")
            yield db
        finally:
            db.close()

    @staticmethod
    def _fts_available(db: sqlite3.Connection) -> bool:
        try:
            db.execute("SELECT count(*) FROM chunks_fts").fetchone()
            return True
        except sqlite3.OperationalError as error:
            if "no such module" not in str(error).lower():
                raise
            return False

    def _ensure_fts(self, db: sqlite3.Connection) -> bool:
        try:
            db.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts "
                "USING fts5(text, content='chunks', content_rowid='rowid', "
                "tokenize='unicode61')"
            )
            triggers_present = (
                db.execute(
                    "SELECT count(*) FROM sqlite_master WHERE type='trigger' "
                    "AND name IN ('chunks_ai','chunks_ad','chunks_au')"
                ).fetchone()[0]
                == 3
            )
            triggers = """
                CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
                    INSERT INTO chunks_fts(rowid, text) VALUES (new.rowid, new.text);
                END;
                CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
                    INSERT INTO chunks_fts(chunks_fts, rowid, text)
                    VALUES ('delete', old.rowid, old.text);
                END;
                CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
                    INSERT INTO chunks_fts(chunks_fts, rowid, text)
                    VALUES ('delete', old.rowid, old.text);
                    INSERT INTO chunks_fts(rowid, text) VALUES (new.rowid, new.text);
                END;
            """
            for statement in triggers.split("END;"):
                if statement.strip():
                    db.execute(statement + "END")
            count = db.execute("SELECT count(*) FROM chunks_fts").fetchone()[0]
            if (
                not triggers_present
                or count != db.execute("SELECT count(*) FROM chunks").fetchone()[0]
            ):
                db.execute("INSERT INTO chunks_fts(chunks_fts) VALUES ('rebuild')")
            return True
        except sqlite3.OperationalError as error:
            if "no such module" not in str(error).lower() and "fts5" not in str(error).lower():
                raise
            return False

    def pending_sources(self, source_ids: list[str]) -> bool:
        """Report roots whose first full indexing pass has not completed."""
        if not source_ids:
            return False
        placeholders = ",".join("?" for _ in source_ids)
        with self.connect() as db:
            ready = db.execute(
                f"SELECT count(*) FROM sources WHERE id IN ({placeholders}) "
                "AND indexed_at IS NOT NULL",
                source_ids,
            ).fetchone()[0]
        return ready < len(set(source_ids))

    def mark_source_indexed(self, source_id: str) -> None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE sources SET indexed_at=datetime('now') WHERE id=?", (source_id,))
            db.commit()

    def list_sources(self) -> list[sqlite3.Row]:
        with self.connect() as db:
            return db.execute("SELECT * FROM sources ORDER BY root").fetchall()

    def register_source(self, source_id: str, root: str) -> None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR IGNORE INTO sources(id,root) VALUES (?,?)", (source_id, root))
            db.commit()

    def get_document(self, source_id: str, relative_path: str) -> sqlite3.Row | None:
        with self.connect() as db:
            return db.execute(
                "SELECT * FROM documents WHERE source_id=? AND relative_path=?",
                (source_id, relative_path),
            ).fetchone()

    def put_document(
        self,
        *,
        source_id: str,
        document_id: str,
        relative_path: str,
        title: str,
        file_format: str,
        size_bytes: int,
        modified_ns: int,
        content_hash: str | None,
        version: str,
        state: str,
        warnings: list[dict],
        chunks: list[Chunk],
    ) -> None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                """
                INSERT INTO documents(id,source_id,relative_path,title,format,
                                      size_bytes,modified_ns,
                                      content_hash,version,state,indexed_at,warnings,error_code)
                VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now'),?,NULL)
                ON CONFLICT(id) DO UPDATE SET title=excluded.title,format=excluded.format,
                    size_bytes=excluded.size_bytes,modified_ns=excluded.modified_ns,
                    content_hash=excluded.content_hash,version=excluded.version,state=excluded.state,
                    indexed_at=excluded.indexed_at,warnings=excluded.warnings,error_code=NULL
            """,
                (
                    document_id,
                    source_id,
                    relative_path,
                    title,
                    file_format,
                    size_bytes,
                    modified_ns,
                    content_hash,
                    version,
                    state,
                    json.dumps(warnings, ensure_ascii=False),
                ),
            )
            # Keep unchanged ordinals and their embeddings; remove obsolete tail chunks.
            if len({chunk.ordinal for chunk in chunks}) != len(chunks):
                raise sqlite3.IntegrityError("Duplicate chunk ordinal")
            existing = db.execute(
                "SELECT id,ordinal FROM chunks WHERE document_id=?", (document_id,)
            ).fetchall()
            ordinals = {chunk.ordinal for chunk in chunks}
            db.executemany(
                "DELETE FROM chunks WHERE id=?",
                [(row["id"],) for row in existing if row["ordinal"] not in ordinals],
            )
            for chunk in chunks:
                db.execute(
                    """
                    INSERT INTO chunks(id,document_id,ordinal,text,page_number,
                                       heading,marker,extraction_type)
                    VALUES (?,?,?,?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET text=excluded.text,
                        page_number=excluded.page_number,heading=excluded.heading,
                        marker=excluded.marker,extraction_type=excluded.extraction_type
                """,
                    (
                        f"{document_id}:{chunk.ordinal}",
                        document_id,
                        chunk.ordinal,
                        chunk.text,
                        chunk.page_number,
                        chunk.heading,
                        chunk.marker,
                        chunk.extraction_type,
                    ),
                )
            db.commit()

    def embedding_chunks(
        self, source_ids: list[str], model_fingerprint: str,
    ) -> list[sqlite3.Row]:
        """Saved chunks and cache state, scoped to explicitly selected sources."""
        if not source_ids:
            return []
        placeholders = ",".join("?" for _ in source_ids)
        with self.connect() as db:
            return db.execute(
                f"""SELECT c.id AS chunk_id,c.text,c.heading,e.input_hash
                    FROM chunks c JOIN documents d ON d.id=c.document_id
                    LEFT JOIN chunk_embeddings e
                      ON e.chunk_id=c.id AND e.model_fingerprint=?
                    WHERE d.source_id IN ({placeholders})
                    ORDER BY d.source_id,d.relative_path,c.ordinal""",
                (model_fingerprint, *source_ids),
            ).fetchall()

    def put_embeddings(
        self, profile: EmbeddingProfile, records: list[tuple[str, str, list[float]]],
    ) -> int:
        """Atomically save a batch, ignoring chunks changed/deleted during inference."""
        encoded = [
            (chunk_id, text, struct.pack(
                f"<{profile.dimensions}f", *validate_vector(vector, profile.dimensions)
            ))
            for chunk_id, text, vector in records
        ]
        written = 0
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT OR IGNORE INTO embedding_profiles VALUES (?,?,?,?,?,?,?)",
                (profile.fingerprint, profile.model, profile.model_digest, profile.dimensions,
                 profile.document_prefix, profile.query_prefix, INPUT_VERSION),
            )
            for chunk_id, text, vector in encoded:
                row = db.execute(
                    "SELECT text,heading FROM chunks WHERE id=?", (chunk_id,)
                ).fetchone()
                if row is None or profile.document_input(row["text"], row["heading"]) != text:
                    continue
                db.execute(
                    """INSERT INTO chunk_embeddings VALUES (?,?,?,?,?)
                       ON CONFLICT(chunk_id,model_fingerprint) DO UPDATE SET
                           input_hash=excluded.input_hash,dimensions=excluded.dimensions,
                           vector=excluded.vector""",
                    (chunk_id, profile.fingerprint, input_hash(text), profile.dimensions, vector),
                )
                written += 1
            db.commit()
        return written

    def load_embeddings(
        self, source_ids: list[str], profile: EmbeddingProfile,
    ) -> list[tuple[str, list[float]]]:
        """Read current float32 vectors; no retrieval or runtime calls."""
        if not source_ids:
            return []
        placeholders = ",".join("?" for _ in source_ids)
        with self.connect() as db:
            rows = db.execute(
                f"""SELECT c.id,c.text,c.heading,e.input_hash,e.vector FROM chunk_embeddings e
                    JOIN chunks c ON c.id=e.chunk_id JOIN documents d ON d.id=c.document_id
                    WHERE e.model_fingerprint=? AND e.dimensions=?
                      AND d.source_id IN ({placeholders}) ORDER BY c.id""",
                (profile.fingerprint, profile.dimensions, *source_ids),
            ).fetchall()
        return [
            (row["id"], list(struct.unpack(f"<{profile.dimensions}f", row["vector"])))
            for row in rows
            if row["input_hash"] == input_hash(profile.document_input(row["text"], row["heading"]))
        ]

    def retrieval_chunks(
        self, source_ids: list[str], profile: EmbeddingProfile,
    ) -> list[sqlite3.Row]:
        """Snapshot text, provenance and cached vectors together to avoid inference races."""
        if not source_ids:
            return []
        placeholders = ",".join("?" for _ in source_ids)
        with self.connect() as db:
            return db.execute(
                f"""SELECT c.id AS chunk_id,c.ordinal,c.text,c.heading,c.page_number,c.marker,
                           c.extraction_type,d.title,d.relative_path,d.source_id,s.root,
                           e.input_hash,e.vector,e.dimensions
                    FROM chunks c JOIN documents d ON d.id=c.document_id
                    JOIN sources s ON s.id=d.source_id LEFT JOIN chunk_embeddings e
                      ON e.chunk_id=c.id AND e.model_fingerprint=?
                    WHERE d.source_id IN ({placeholders}) ORDER BY c.id""",
                (profile.fingerprint, *source_ids),
            ).fetchall()

    def neighboring_chunks(self, chunk_ids: list[str], radius: int = 1) -> dict[str, list[str]]:
        """Return adjacent saved chunks from each matched document, excluding matches."""
        if not chunk_ids or radius < 1:
            return {}
        placeholders = ",".join("?" for _ in chunk_ids)
        with self.connect() as db:
            matches = db.execute(
                f"SELECT id,document_id,ordinal FROM chunks WHERE id IN ({placeholders})",
                chunk_ids,
            ).fetchall()
            result: dict[str, list[str]] = {row["id"]: [] for row in matches}
            for row in matches:
                neighbors = db.execute(
                    "SELECT text FROM chunks WHERE document_id=? AND ordinal BETWEEN ? AND ? "
                    "AND id<>? ORDER BY ABS(ordinal-?),ordinal",
                    (row["document_id"], row["ordinal"] - radius,
                     row["ordinal"] + radius, row["id"], row["ordinal"]),
                ).fetchall()
                result[row["id"]] = [item["text"] for item in neighbors]
        return result

    def record_error(
        self,
        source_id: str,
        document_id: str,
        relative_path: str,
        title: str,
        file_format: str,
        size_bytes: int,
        modified_ns: int,
        version: str,
        code: str,
    ) -> None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                """
                INSERT INTO documents(id,source_id,relative_path,title,format,
                                      size_bytes,modified_ns,
                                      version,state,error_code)
                VALUES (?,?,?,?,?,?,?,?,'error',?)
                ON CONFLICT(id) DO UPDATE SET state='retry', error_code=excluded.error_code
            """,
                (
                    document_id,
                    source_id,
                    relative_path,
                    title,
                    file_format,
                    size_bytes,
                    modified_ns,
                    version,
                    code,
                ),
            )
            db.commit()

    def delete_missing(self, source_id: str, paths: set[str]) -> int:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT id,relative_path FROM documents WHERE source_id=?", (source_id,)
            ).fetchall()
            missing = [row["id"] for row in rows if row["relative_path"] not in paths]
            db.executemany("DELETE FROM documents WHERE id=?", [(item,) for item in missing])
            db.commit()
            return len(missing)

    def remove_source(self, source_id: str) -> None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM sources WHERE id=?", (source_id,))
            db.commit()

    def list_warnings(self, source_ids: list[str]) -> list[dict]:
        if not source_ids:
            return []
        placeholders = ",".join("?" for _ in source_ids)
        with self.connect() as db:
            rows = db.execute(
                f"SELECT relative_path,title,warnings,error_code FROM documents "
                f"WHERE source_id IN ({placeholders})",
                source_ids,
            ).fetchall()
        result = []
        for row in rows:
            result.extend(json.loads(row["warnings"]))
            if row["error_code"]:
                result.append(
                    {
                        "document_id": row["relative_path"],
                        "title": row["title"],
                        "code": row["error_code"],
                        "page_number": None,
                    }
                )
        return result

    def search(self, source_ids: list[str], query: str, limit: int = 8) -> list[sqlite3.Row]:
        terms = re.findall(r"[^\W_]+", query.casefold(), flags=re.UNICODE)
        terms = [term for term in terms if len(term) > 1]
        if not terms or not source_ids or limit < 1:
            return []
        placeholders = ",".join("?" for _ in source_ids)
        with self.connect() as db:
            if self.fts:
                match = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
                return db.execute(
                    f"""
                    SELECT d.title,d.relative_path,d.source_id,s.root,c.id AS chunk_id,
                           c.ordinal,c.text,c.page_number,c.heading,c.marker,c.extraction_type,
                           -bm25(chunks_fts) AS rank
                    FROM chunks_fts JOIN chunks c ON c.rowid=chunks_fts.rowid
                    JOIN documents d ON d.id=c.document_id JOIN sources s ON s.id=d.source_id
                    WHERE chunks_fts MATCH ? AND d.source_id IN ({placeholders})
                    ORDER BY rank DESC,d.relative_path COLLATE NOCASE,c.ordinal LIMIT ?
                """,
                    (match, *source_ids, limit),
                ).fetchall()
            rows = db.execute(
                f"""
                SELECT d.title,d.relative_path,d.source_id,s.root,c.id AS chunk_id,
                       c.ordinal,c.text,c.page_number,c.heading,c.marker,c.extraction_type
                FROM chunks c JOIN documents d ON d.id=c.document_id
                JOIN sources s ON s.id=d.source_id WHERE d.source_id IN ({placeholders})
            """,
                source_ids,
            ).fetchall()
        ranked = [(sum(row["text"].casefold().count(term) for term in terms), row) for row in rows]
        ranked = [(score, row) for score, row in ranked if score]
        ranked.sort(
            key=lambda pair: (-pair[0], pair[1]["relative_path"].casefold(), pair[1]["chunk_id"])
        )
        return [row for _, row in ranked[:limit]]
