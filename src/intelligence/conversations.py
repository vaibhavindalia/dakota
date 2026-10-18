"""Thread-safe Conversation History & Session Management for Dakota Intelligence Core."""
from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH = BASE_DIR / "data" / "dakota.db"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_conversation_tables() -> None:
    """Ensure conversation and message tables exist in SQLite."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS intelligence_conversations (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        active_context TEXT
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS intelligence_messages (
        id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        citations TEXT,
        evidence TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (conversation_id) REFERENCES intelligence_conversations(id) ON DELETE CASCADE
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS intelligence_feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        answer_id TEXT NOT NULL,
        query TEXT NOT NULL,
        feedback_type TEXT NOT NULL,
        notes TEXT,
        created_at TEXT NOT NULL
    );
    """)
    conn.commit()
    conn.close()


def create_conversation(title: str = "New Investigation Session", context: dict[str, Any] | None = None) -> dict[str, Any]:
    init_conversation_tables()
    cid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO intelligence_conversations (id, title, created_at, updated_at, active_context)
        VALUES (?, ?, ?, ?, ?)
        """,
        (cid, title, now, now, json.dumps(context or {})),
    )
    conn.commit()
    conn.close()
    return {"id": cid, "title": title, "created_at": now, "updated_at": now, "active_context": context or {}}


def list_conversations(limit: int = 30) -> list[dict[str, Any]]:
    init_conversation_tables()
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, title, created_at, updated_at, active_context
        FROM intelligence_conversations
        ORDER BY updated_at DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = cur.fetchall()
    out = []
    for r in rows:
        out.append({
            "id": r["id"],
            "title": r["title"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
            "active_context": json.loads(r["active_context"] or "{}"),
        })
    conn.close()
    return out


def get_conversation_history(conversation_id: str, limit: int = 50) -> list[dict[str, Any]]:
    init_conversation_tables()
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, role, content, citations, evidence, created_at
        FROM intelligence_messages
        WHERE conversation_id = ?
        ORDER BY created_at ASC
        LIMIT ?
        """,
        (conversation_id, limit),
    )
    rows = cur.fetchall()
    out = []
    for r in rows:
        out.append({
            "id": r["id"],
            "role": r["role"],
            "content": r["content"],
            "citations": json.loads(r["citations"] or "[]"),
            "evidence": json.loads(r["evidence"] or "[]"),
            "created_at": r["created_at"],
        })
    conn.close()
    return out


def add_message(
    conversation_id: str,
    role: str,
    content: str,
    citations: list[dict[str, Any]] | None = None,
    evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    init_conversation_tables()
    mid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()
    cur = conn.cursor()

    # Verify or auto-create conversation
    cur.execute("SELECT id FROM intelligence_conversations WHERE id = ?", (conversation_id,))
    if not cur.fetchone():
        cur.execute(
            """
            INSERT INTO intelligence_conversations (id, title, created_at, updated_at, active_context)
            VALUES (?, ?, ?, ?, ?)
            """,
            (conversation_id, (content[:35] + "...") if len(content) > 35 else content, now, now, "{}"),
        )

    cur.execute(
        """
        INSERT INTO intelligence_messages (id, conversation_id, role, content, citations, evidence, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            mid,
            conversation_id,
            role,
            content,
            json.dumps(citations or []),
            json.dumps(evidence or []),
            now,
        ),
    )
    cur.execute(
        "UPDATE intelligence_conversations SET updated_at = ? WHERE id = ?",
        (now, conversation_id),
    )
    conn.commit()
    conn.close()
    return {
        "id": mid,
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
        "citations": citations or [],
        "evidence": evidence or [],
        "created_at": now,
    }


def delete_conversation(conversation_id: str) -> bool:
    init_conversation_tables()
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM intelligence_messages WHERE conversation_id = ?", (conversation_id,))
    cur.execute("DELETE FROM intelligence_conversations WHERE id = ?", (conversation_id,))
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def record_feedback(answer_id: str, query: str, feedback_type: str, notes: str) -> None:
    init_conversation_tables()
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO intelligence_feedback (answer_id, query, feedback_type, notes, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (answer_id, query, feedback_type, notes, now),
    )
    conn.commit()
    conn.close()
