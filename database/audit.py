"""
SEPLE Tender Database — Audit Search
Query interface for the audit log.
"""
import logging
from typing import List, Optional
from datetime import datetime
from uuid import UUID

from .db import get_connection

logger = logging.getLogger(__name__)

class AuditLogger:
    
    @staticmethod
    async def get_audit_trail(entity_id: UUID) -> List[dict]:
        """Get the full audit history for a specific entity (like a tender)."""
        async with get_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM audit_log
                WHERE entity_id = $1
                ORDER BY created_at DESC
                """,
                entity_id
            )
            return [dict(r) for r in rows]
            
    @staticmethod
    async def get_recent_actions(limit: int = 100) -> List[dict]:
        """Get recent system actions."""
        async with get_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM audit_log
                ORDER BY created_at DESC
                LIMIT $1
                """,
                limit
            )
            return [dict(r) for r in rows]
