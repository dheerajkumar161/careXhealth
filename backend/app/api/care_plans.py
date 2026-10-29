"""/api/care-plans and /api/care-plan-items — doctor review, the approval gate, and item removal."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from app.agents.orchestrator import orchestrator
from app.auth.deps import require_patient_access, require_role
from app.auth.security import SessionUser
from app.core.db import session_scope
from app.models import CarePlanItem, Patient
from app.repositories import care_plans
from app.services.audit import audit
from fastapi.responses import JSONResponse

from app.agents.safety_rules import unresolved_blocks
from app.schemas.api import ApproveIn, CarePlanUpdate, ItemRemoval
from app.services.records import plan_dict, safety_findings

router = APIRouter(tags=["care-plans"])


@router.patch("/api/care-plans/{plan_id}")
async def edit_draft(plan_id: str, body: CarePlanUpdate, user: SessionUser = Depends(require_role("DOCTOR"))) -> dict:
    """Doctor edits a DRAFT plan (edit / include / exclude / add / remove items) or discards it."""
    plan = care_plans.get(plan_id)
    if plan is None:
        raise HTTPException(404, "Care plan not found")
    require_patient_access(user, plan.patient_id)
    if plan.status != "DRAFT":
        raise HTTPException(409, "Only draft plans can be edited")
    if body.status == "REJECTED":
        care_plans.set_status(plan_id, "REJECTED")
        audit("PLAN_REJECT", user, entity_type="CarePlan", entity_id=plan_id, patient_id=plan.patient_id)
        await orchestrator.services.call("ehr", "create_audit_event", agent="HUMAN", action="Doctor discarded draft plan", patient_id=plan.patient_id)
        return {"ok": True}
    if body.items is not None:
        plan = care_plans.replace_items(plan_id, [i.model_dump() for i in body.items])
    return {"plan": plan_dict(plan)}


@router.post("/api/care-plans/{plan_id}/approve")
async def approve(plan_id: str, body: ApproveIn | None = None, user: SessionUser = Depends(require_role("DOCTOR"))):  # noqa: ANN201
    """Doctor approval is the gate: only now do the Execution, Monitoring and Communication agents act."""
    plan = care_plans.get(plan_id)
    if plan is None:
        raise HTTPException(404, "Care plan not found")
    require_patient_access(user, plan.patient_id)
    if plan.status != "DRAFT":
        raise HTTPException(409, "This plan has already been processed")
    # Safety gate: BLOCK findings (documented allergy, contraindicated pair, over-maximum dose) need a written override reason.
    overrides = (body.overrides if body else None) or {}
    findings = safety_findings(plan)
    unresolved = unresolved_blocks(findings, overrides)
    if unresolved:
        return JSONResponse({"error": "Resolve or override the safety alerts before approving", "findings": findings, "unresolved": [f["code"] for f in unresolved]}, status_code=409)
    for f in findings:
        if f["severity"] == "BLOCK":
            audit("SAFETY_OVERRIDE", user, entity_type="CarePlan", entity_id=plan_id, patient_id=plan.patient_id, detail=f"{f['code']}: {overrides[f['code']].strip()}")
    await orchestrator.approve_plan(plan_id, user.id, user.name)
    audit("PLAN_APPROVE", user, entity_type="CarePlan", entity_id=plan_id, patient_id=plan.patient_id)
    return {"plan": plan_dict(care_plans.get(plan_id))}  # type: ignore[arg-type]


@router.delete("/api/care-plan-items/{item_id}")
async def remove_item(item_id: str, body: dict | None = None, user: SessionUser = Depends(require_role("DOCTOR"))) -> dict:
    """Treating doctor removes an item from an ACTIVE care plan; the Execution agent cancels what it had set in motion."""
    with session_scope() as s:
        item = s.get(CarePlanItem, item_id)
        doctor_id = s.get(Patient, item.care_plan.patient_id).doctor_id if item else None  # type: ignore[union-attr]
        status, included = (item.care_plan.status, item.included) if item else (None, None)
    if item is None or doctor_id != user.id:
        raise HTTPException(404, "Care plan item not found")
    if status != "ACTIVE":
        raise HTTPException(409, "Only items in an active plan can be removed — edit drafts directly")
    if not included:
        raise HTTPException(409, "This item has already been removed")
    try:
        reason = ItemRemoval.model_validate(body or {}).reason.strip()
    except ValidationError as e:
        raise HTTPException(400, "Please give a short reason") from e
    return await orchestrator.execution.invoke("cancel_plan_item", item_id=item_id, reason=reason, doctor_name=user.name)
