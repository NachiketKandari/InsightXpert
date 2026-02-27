from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from insightxpert.auth.models import (
    Automation,
    AutomationRun,
    Notification,
    _record_delete,
    _uuid,
    _utcnow,
)

logger = logging.getLogger("insightxpert.automations")


class AutomationService:
    """CRUD and query methods for automations, runs, and notifications."""

    def __init__(self, engine) -> None:
        self._engine = engine

    # ------------------------------------------------------------------
    # Automations
    # ------------------------------------------------------------------

    def create_automation(self, user_id: str, **fields) -> dict:
        with Session(self._engine) as session:
            trigger_conditions = fields.get("trigger_conditions", [])
            if isinstance(trigger_conditions, list):
                trigger_conditions = json.dumps(trigger_conditions)

            # sql_queries is stored as JSON array in the sql_query column
            sql_queries = fields.get("sql_queries", [])
            if not sql_queries and fields.get("sql_query"):
                sql_queries = [fields["sql_query"]]
            sql_query_json = json.dumps(sql_queries)

            # Serialize workflow graph if provided
            workflow_json = None
            if fields.get("workflow_graph"):
                workflow_json = json.dumps(fields["workflow_graph"])

            auto = Automation(
                id=_uuid(),
                name=fields["name"],
                description=fields.get("description"),
                nl_query=fields["nl_query"],
                sql_query=sql_query_json,
                cron_expression=fields["cron_expression"],
                trigger_conditions=trigger_conditions,
                is_active=True,
                created_by=user_id,
                source_conversation_id=fields.get("source_conversation_id"),
                source_message_id=fields.get("source_message_id"),
                workflow_json=workflow_json,
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
            session.add(auto)
            session.commit()
            session.refresh(auto)
            return self._auto_to_dict(auto)

    def get_automation(self, automation_id: str) -> dict | None:
        with Session(self._engine) as session:
            auto = session.get(Automation, automation_id)
            if not auto:
                return None
            return self._auto_to_dict(auto)

    def list_automations(self, user_id: str | None = None) -> list[dict]:
        with Session(self._engine) as session:
            q = session.query(Automation)
            if user_id:
                q = q.filter(Automation.created_by == user_id)
            rows = q.order_by(Automation.created_at.desc()).all()
            return [self._auto_to_dict(a) for a in rows]

    def update_automation(self, automation_id: str, **fields) -> dict | None:
        with Session(self._engine) as session:
            auto = session.get(Automation, automation_id)
            if not auto:
                return None
            for key, value in fields.items():
                if key == "trigger_conditions":
                    if isinstance(value, list):
                        value = json.dumps(value)
                if key == "workflow_graph":
                    # Map workflow_graph dict to workflow_json column
                    auto.workflow_json = json.dumps(value) if value else None
                    continue
                if hasattr(auto, key) and key not in ("id", "created_by", "created_at"):
                    setattr(auto, key, value)
            auto.updated_at = _utcnow()
            session.commit()
            session.refresh(auto)
            return self._auto_to_dict(auto)

    def delete_automation(self, automation_id: str) -> bool:
        with Session(self._engine) as session:
            auto = session.get(Automation, automation_id)
            if not auto:
                return False

            # Record cascading deletes for Turso sync
            run_ids = [
                r.id for r in
                session.query(AutomationRun.id)
                .filter(AutomationRun.automation_id == automation_id)
                .all()
            ]
            notif_ids = [
                n.id for n in
                session.query(Notification.id)
                .filter(Notification.automation_id == automation_id)
                .all()
            ]
            _record_delete(session, "automation_runs", run_ids)
            _record_delete(session, "notifications", notif_ids)
            _record_delete(session, "automations", [automation_id])

            session.delete(auto)
            session.commit()
            return True

    def toggle_automation(self, automation_id: str) -> dict | None:
        with Session(self._engine) as session:
            auto = session.get(Automation, automation_id)
            if not auto:
                return None
            auto.is_active = not auto.is_active
            auto.updated_at = _utcnow()
            session.commit()
            session.refresh(auto)
            return self._auto_to_dict(auto)

    def get_active_automations(self) -> list[dict]:
        with Session(self._engine) as session:
            rows = session.query(Automation).filter(Automation.is_active.is_(True)).all()
            return [self._auto_to_dict(a) for a in rows]

    def update_run_timestamps(self, automation_id: str, last_run_at, next_run_at) -> None:
        with Session(self._engine) as session:
            auto = session.get(Automation, automation_id)
            if auto:
                auto.last_run_at = last_run_at
                auto.next_run_at = next_run_at
                session.commit()

    # ------------------------------------------------------------------
    # Automation Runs
    # ------------------------------------------------------------------

    def create_run(
        self,
        automation_id: str,
        status: str,
        result_json: str | None = None,
        row_count: int | None = None,
        execution_time_ms: int | None = None,
        triggers_fired: str | None = None,
        error_message: str | None = None,
    ) -> dict:
        with Session(self._engine) as session:
            run = AutomationRun(
                id=_uuid(),
                automation_id=automation_id,
                status=status,
                result_json=result_json,
                row_count=row_count,
                execution_time_ms=execution_time_ms,
                triggers_fired=triggers_fired,
                error_message=error_message,
                created_at=_utcnow(),
            )
            session.add(run)
            session.commit()
            session.refresh(run)
            return self._run_to_dict(run)

    def get_runs(self, automation_id: str, limit: int = 20) -> list[dict]:
        with Session(self._engine) as session:
            rows = (
                session.query(AutomationRun)
                .filter(AutomationRun.automation_id == automation_id)
                .order_by(AutomationRun.created_at.desc())
                .limit(limit)
                .all()
            )
            return [self._run_to_dict(r) for r in rows]

    def get_run(self, run_id: str) -> dict | None:
        with Session(self._engine) as session:
            run = session.get(AutomationRun, run_id)
            if not run:
                return None
            return self._run_to_dict(run)

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------

    def create_notification(
        self,
        user_id: str,
        automation_id: str | None,
        run_id: str | None,
        title: str,
        message: str,
        severity: str = "info",
    ) -> dict:
        with Session(self._engine) as session:
            notif = Notification(
                id=_uuid(),
                user_id=user_id,
                automation_id=automation_id,
                run_id=run_id,
                title=title,
                message=message,
                severity=severity,
                is_read=False,
                created_at=_utcnow(),
            )
            session.add(notif)
            session.commit()
            session.refresh(notif)
            return self._notif_to_dict(notif)

    def get_notifications(self, user_id: str, unread_only: bool = False, limit: int = 50) -> list[dict]:
        with Session(self._engine) as session:
            q = (
                session.query(Notification, Automation.name.label("automation_name"))
                .outerjoin(Automation, Notification.automation_id == Automation.id)
                .filter(Notification.user_id == user_id)
            )
            if unread_only:
                q = q.filter(Notification.is_read.is_(False))
            rows = q.order_by(Notification.created_at.desc()).limit(limit).all()
            result = []
            for notif, auto_name in rows:
                d = self._notif_to_dict(notif)
                d["automation_name"] = auto_name
                result.append(d)
            return result

    def get_unread_count(self, user_id: str) -> int:
        with Session(self._engine) as session:
            return (
                session.query(Notification)
                .filter(Notification.user_id == user_id, Notification.is_read.is_(False))
                .count()
            )

    def mark_notification_read(self, notification_id: str, user_id: str) -> bool:
        with Session(self._engine) as session:
            notif = session.get(Notification, notification_id)
            if not notif or notif.user_id != user_id:
                return False
            notif.is_read = True
            session.commit()
            return True

    def mark_all_notifications_read(self, user_id: str) -> int:
        with Session(self._engine) as session:
            count = (
                session.query(Notification)
                .filter(Notification.user_id == user_id, Notification.is_read.is_(False))
                .update({Notification.is_read: True})
            )
            session.commit()
            return count

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_sql_queries(raw: str | None) -> list[str]:
        """Parse the sql_query column into a list of SQL strings.

        Handles both legacy single-query strings and JSON arrays.
        """
        if not raw:
            return []
        raw = raw.strip()
        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [s for s in parsed if isinstance(s, str) and s.strip()]
            except json.JSONDecodeError:
                pass
        # Legacy: plain SQL string
        return [raw] if raw else []

    @staticmethod
    def _auto_to_dict(auto: Automation) -> dict:
        trigger_conditions = auto.trigger_conditions
        if isinstance(trigger_conditions, str):
            try:
                trigger_conditions = json.loads(trigger_conditions)
            except json.JSONDecodeError:
                trigger_conditions = []
        elif trigger_conditions is None:
            trigger_conditions = []

        sql_queries = AutomationService._parse_sql_queries(auto.sql_query)

        # Deserialize workflow_json
        workflow_graph = None
        if auto.workflow_json:
            try:
                workflow_graph = json.loads(auto.workflow_json)
            except json.JSONDecodeError:
                pass

        return {
            "id": auto.id,
            "name": auto.name,
            "description": auto.description,
            "nl_query": auto.nl_query,
            "sql_query": sql_queries[0] if sql_queries else "",
            "sql_queries": sql_queries,
            "cron_expression": auto.cron_expression,
            "trigger_conditions": trigger_conditions,
            "is_active": auto.is_active,
            "last_run_at": str(auto.last_run_at) if auto.last_run_at else None,
            "next_run_at": str(auto.next_run_at) if auto.next_run_at else None,
            "created_by": auto.created_by,
            "source_conversation_id": auto.source_conversation_id,
            "source_message_id": auto.source_message_id,
            "workflow_graph": workflow_graph,
            "created_at": str(auto.created_at),
            "updated_at": str(auto.updated_at),
        }

    @staticmethod
    def _run_to_dict(run: AutomationRun) -> dict:
        result_json = run.result_json
        if isinstance(result_json, str):
            try:
                result_json = json.loads(result_json)
            except json.JSONDecodeError:
                result_json = None

        triggers_fired = run.triggers_fired
        if isinstance(triggers_fired, str):
            try:
                triggers_fired = json.loads(triggers_fired)
            except json.JSONDecodeError:
                triggers_fired = None

        return {
            "id": run.id,
            "automation_id": run.automation_id,
            "status": run.status,
            "result_json": result_json,
            "row_count": run.row_count,
            "execution_time_ms": run.execution_time_ms,
            "triggers_fired": triggers_fired,
            "error_message": run.error_message,
            "created_at": str(run.created_at),
        }

    @staticmethod
    def _notif_to_dict(notif: Notification) -> dict:
        return {
            "id": notif.id,
            "user_id": notif.user_id,
            "automation_id": notif.automation_id,
            "run_id": notif.run_id,
            "title": notif.title,
            "message": notif.message,
            "severity": notif.severity,
            "is_read": notif.is_read,
            "created_at": str(notif.created_at),
        }
