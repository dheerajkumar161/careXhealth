"""CareXHealth orchestration layer (Microsoft Agent Framework Workflows).

    Doctor → Planning Agent → DRAFT plan → Doctor approval (hard gate)
           → Monitoring Agent (rules) → Execution Agent (MCP bookings) → Communication Agent (patient plan + notices)
    Active recovery → Monitoring / Communication / Intelligence agents

Multi-agent pipelines are MAF `WorkflowBuilder` graphs whose `Executor`s invoke the CareXHealth agents through
their MAF `run()` entry point. A fresh workflow is built per run (MAF workflows are single-run-at-a-time).
"""
from __future__ import annotations

import logging
from typing import Any

from agent_framework import Executor, Workflow, WorkflowBuilder, WorkflowContext, handler

from app.core.util import iso, now

from .base import CareXHealthAgent
from .communication_agent import CommunicationAgent
from .execution_agent import ExecutionAgent
from .intelligence_agent import IntelligenceAgent
from .mcp_client import HospitalServices, services
from .monitoring_agent import MonitoringAgent
from .planning_agent import PlanningAgent

log = logging.getLogger("carexhealth.orchestrator")


# ─────────────────────────── workflow executors ───────────────────────────


class ApprovalGate(Executor):
    """Records the doctor's approval. Nothing downstream runs unless the plan was a DRAFT approved by the treating doctor."""

    def __init__(self, planning: PlanningAgent) -> None:
        super().__init__(id="approval_gate")
        self.planning = planning

    @handler
    async def handle_approve(self, request: dict, ctx: WorkflowContext[dict]) -> None:
        state = await self.planning.invoke("activate_plan", plan_id=request["plan_id"], doctor_id=request["doctor_id"], doctor_name=request["doctor_name"], base=request.get("base"))
        await ctx.send_message({**request, **state})


class RegisterMonitoring(Executor):
    def __init__(self, monitoring: MonitoringAgent) -> None:
        super().__init__(id="monitoring_rules")
        self.monitoring = monitoring

    @handler
    async def handle_register(self, state: dict, ctx: WorkflowContext[dict]) -> None:
        await self.monitoring.invoke("register_rules", patient_id=state["patientId"], plan_id=state["planId"], include_defaults=state["kind"] == "INITIAL")
        await ctx.send_message(state)


class ExecutePlan(Executor):
    def __init__(self, execution: ExecutionAgent) -> None:
        super().__init__(id="execution")
        self.execution = execution

    @handler
    async def handle_execute(self, state: dict, ctx: WorkflowContext[dict]) -> None:
        await self.execution.invoke("execute_plan", plan_id=state["planId"], base=state.get("base"), not_before=state.get("not_before"))
        await ctx.send_message(state)


class CommunicatePlan(Executor):
    def __init__(self, communication: CommunicationAgent) -> None:
        super().__init__(id="communication")
        self.communication = communication

    @handler
    async def handle_communicate(self, state: dict, ctx: WorkflowContext[dict, dict]) -> None:
        pid, initial = state["patientId"], state["kind"] == "INITIAL"
        await self.communication.invoke("generate_patient_instructions", patient_id=pid)
        await self.communication.notify(
            "PATIENT", pid, "CARE_PLAN", "Your care plan is ready" if initial else "Your care plan was updated",
            "Your doctor approved your recovery plan. Your medicines, appointments and instructions are now in your dashboard.",
        )  # fmt: skip
        patient = (await self.communication.mcp("ehr", "get_patient_records", patient_id=pid))["patient"]
        await self.communication.notify("NURSE", pid, "CARE_PLAN", "Care plan activated", f"{patient['diagnosis']}: plan v{state['version']} is now active.")
        await ctx.yield_output(state)


class CycleStep(Executor):
    """One step of the background agent cycle (reused by the on-demand 'Agents live' run)."""

    def __init__(self, step_id: str, orchestrator: Orchestrator) -> None:
        super().__init__(id=step_id)
        self.orchestrator = orchestrator

    @handler
    async def handle_step(self, state: dict, ctx: WorkflowContext[dict, dict]) -> None:
        fn = getattr(self.orchestrator, self.id)
        # Adherence also covers patients whose doses were just marked missed (legacy cycle semantics)
        result = await (fn(state["at"], state.get("mark_overdue_doses")) if self.id == "check_adherence" else fn(state["at"]))
        state = {**state, self.id: result}
        if self.id == "escalate_unacknowledged_alerts":
            await ctx.yield_output(state)
        else:
            await ctx.send_message(state)


# ─────────────────────────── orchestrator ───────────────────────────


class Orchestrator:
    def __init__(self, hospital: HospitalServices) -> None:
        self.services = hospital
        self.planning = PlanningAgent(services=hospital, name="Care Planning & Coordination Agent", description="Understand → Structure → Plan → Coordinate requirements")
        self.execution = ExecutionAgent(services=hospital, name="Care Execution & Scheduling Agent", description="Execute → Book → Track")
        self.monitoring = MonitoringAgent(services=hospital, name="Monitoring & Escalation Agent", description="Observe → Detect → Alert → Escalate (deterministic)")
        self.communication = CommunicationAgent(services=hospital, name="Communication & Clinical Documentation Agent", description="Communicate → Generate documents → Package → Route")
        self.intelligence = IntelligenceAgent(services=hospital, name="Clinical Intelligence & Handoff Agent", description="Summarize → Contextualize → Handoff")
        self.agents: dict[str, CareXHealthAgent] = {a.key: a for a in (self.planning, self.execution, self.monitoring, self.communication, self.intelligence)}
        for a in self.agents.values():
            a.peers = self.agents

    # ── workflows ──

    def approval_workflow(self) -> Workflow:
        gate, mon, exe, com = ApprovalGate(self.planning), RegisterMonitoring(self.monitoring), ExecutePlan(self.execution), CommunicatePlan(self.communication)
        return WorkflowBuilder(name="care-plan-approval", start_executor=gate).add_chain([gate, mon, exe, com]).build()

    def cycle_workflow(self) -> Workflow:
        steps = [CycleStep(s, self) for s in ("send_due_dose_reminders", "mark_overdue_doses", "check_missed_appointments", "check_adherence", "escalate_unacknowledged_alerts")]
        return WorkflowBuilder(name="agent-cycle", start_executor=steps[0]).add_chain(steps).build()

    async def approve_plan(self, plan_id: str, doctor_id: str, doctor_name: str, base: str | None = None, not_before: str | None = None) -> dict[str, Any]:
        """Doctor approval → Monitoring rules → Execution → patient communication."""
        result = await self.approval_workflow().run({"plan_id": plan_id, "doctor_id": doctor_id, "doctor_name": doctor_name, "base": base, "not_before": not_before})
        outputs = result.get_outputs()
        return outputs[-1] if outputs else {}

    async def run_agent_cycle(self, at: str | None = None) -> dict[str, Any]:
        result = await self.cycle_workflow().run({"at": at or iso(now())})
        out = result.get_outputs()[-1]
        return {"reminders": out["send_due_dose_reminders"], "patientsChecked": out["check_adherence"], "escalated": out["escalate_unacknowledged_alerts"]}

    # ── scheduled job bodies (also the cycle workflow steps) ──

    async def send_due_dose_reminders(self, at: str | None = None) -> int:
        return await self.execution.invoke("dispatch_reminders", at=at)

    async def mark_overdue_doses(self, at: str | None = None) -> list[str]:
        return await self.execution.invoke("sweep_doses", at=at)

    async def check_missed_appointments(self, at: str | None = None) -> int:
        return await self.execution.invoke("sweep_appointments")

    async def check_adherence(self, at: str | None = None, also: list[str] | None = None) -> int:
        from sqlalchemy import select

        from app.core.db import session_scope
        from app.models import Patient

        with session_scope() as s:
            active = list(s.scalars(select(Patient.id).where(Patient.status == "RECOVERING")))
        for pid in dict.fromkeys([*(also or []), *active]):
            await self.monitoring.invoke("evaluate_adherence", patient_id=pid, at=at)
        return len(active)

    async def escalate_unacknowledged_alerts(self, at: str | None = None) -> int:
        return await self.monitoring.invoke("escalation_sweep", at=at)

    # ── referral revision applied by the doctor (amendment approved on their behalf, then resend) ──

    async def apply_referral_revision(
        self, referral_id: str, patient_id: str, doctor_id: str, doctor_name: str, referral: dict[str, Any], changes: list[dict[str, Any]], engine: str, provider_id: str | None
    ) -> dict[str, Any]:
        raw = f"Referral revision for {referral['referralType']}: {referral.get('noteToSpecialist') or ''}".strip()
        draft = await self.planning.invoke("create_amendment", patient_id=patient_id, doctor_id=doctor_id, raw=raw, items=changes, engine=engine)
        if draft:
            await self.approve_plan(draft["planId"], doctor_id, doctor_name)
        routed = await self.execution.invoke("resend_referral", referral_id=referral_id, revision=referral, provider_id=provider_id)
        return {"routed": routed, "amendmentId": draft["planId"] if draft else None}


orchestrator = Orchestrator(services)
