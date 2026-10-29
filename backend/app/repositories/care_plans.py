"""Care plans & items (Planning agent state)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select, update

from app.core.db import session_scope
from app.core.util import dumps, now
from app.models import CarePlan, CarePlanItem


def get(plan_id: str) -> CarePlan | None:
    with session_scope() as s:
        return s.get(CarePlan, plan_id)


def get_item(item_id: str) -> CarePlanItem | None:
    with session_scope() as s:
        item = s.get(CarePlanItem, item_id)
        if item:
            _ = item.care_plan  # load
        return item


def count_for_patient(patient_id: str) -> int:
    with session_scope() as s:
        return s.scalar(select(func.count()).select_from(CarePlan).where(CarePlan.patient_id == patient_id)) or 0


def create_draft(*, patient_id: str, doctor_id: str, kind: str, raw: str, summary: str, engine: str, items: list[dict[str, Any]]) -> CarePlan:
    version = count_for_patient(patient_id) + 1
    with session_scope() as s:
        plan = CarePlan(patient_id=patient_id, doctor_id=doctor_id, kind=kind, version=version, raw_instructions=raw, summary=summary, engine=engine)
        plan.items = [
            CarePlanItem(
                category=i["category"],
                action=i.get("action") or "ADD",
                title=i["title"],
                source=i["source"],
                rationale=i.get("rationale"),
                details=dumps(i.get("details") or {}),
                sort_order=idx,
            )
            for idx, i in enumerate(items)
        ]
        s.add(plan)
        s.flush()
        s.refresh(plan)
        return plan


def reject_initial_drafts(patient_id: str) -> None:
    with session_scope() as s:
        s.execute(update(CarePlan).where(CarePlan.patient_id == patient_id, CarePlan.status == "DRAFT", CarePlan.kind == "INITIAL").values(status="REJECTED"))


def supersede_active(patient_id: str) -> None:
    with session_scope() as s:
        s.execute(update(CarePlan).where(CarePlan.patient_id == patient_id, CarePlan.status == "ACTIVE").values(status="SUPERSEDED"))


def set_status(plan_id: str, status: str) -> CarePlan:
    with session_scope() as s:
        plan = s.get(CarePlan, plan_id)
        assert plan is not None
        plan.status = status
        if status == "ACTIVE":
            plan.approved_at = now()
        s.flush()
        return plan


def replace_items(plan_id: str, items: list[dict[str, Any]]) -> CarePlan:
    """Doctor edits a DRAFT: keep/update listed items, create new ones, delete the rest (one transaction)."""
    with session_scope() as s:
        plan = s.get(CarePlan, plan_id)
        assert plan is not None
        existing = {i.id: i for i in plan.items}
        keep = {i["id"] for i in items if i.get("id")}
        for item in list(plan.items):
            if item.id not in keep:
                plan.items.remove(item)
        for idx, i in enumerate(items):
            if i.get("id") and i["id"] in existing:
                row = existing[i["id"]]
                row.title, row.category, row.action, row.details, row.included, row.sort_order = i["title"], i["category"], i["action"], dumps(i["details"]), i["included"], idx
            else:
                plan.items.append(CarePlanItem(title=i["title"], category=i["category"], action=i["action"], details=dumps(i["details"]), included=i["included"], source="DOCTOR", sort_order=idx))
        s.flush()
        s.refresh(plan)
        return plan


def update_item(item_id: str, **fields: Any) -> None:
    with session_scope() as s:
        item = s.get(CarePlanItem, item_id)
        if item is None:
            return
        for k, v in fields.items():
            setattr(item, k, dumps(v) if k == "details" else v)
