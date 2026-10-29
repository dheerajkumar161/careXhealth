// Client-side shapes of API payloads (dates arrive as ISO strings).
export type UserLite = { id: string; name: string; email: string; phone?: string | null; title?: string | null };

export type Patient = {
  id: string; mrn: string; dateOfBirth: string; gender: string; bloodGroup?: string | null; diagnosis: string; procedure?: string | null;
  allergies?: string | null; comorbidities?: string | null; admissionDate: string; dischargeDate?: string | null; status: string; riskLevel: string;
  address?: string | null; emergencyContact?: string | null; user: UserLite; doctor: UserLite; nurse?: UserLite | null;
};

export type PlanItem = { id: string; category: string; action: string; title: string; details: Record<string, unknown>; source: string; rationale?: string | null; included: boolean; sortOrder: number };
export type SafetyFinding = { severity: "BLOCK" | "WARN"; code: string; title: string; message: string; items: string[] };
export type CarePlan = { safety?: SafetyFinding[]; id: string; kind: string; status: string; version: number; rawInstructions: string; summary?: string | null; engine?: string | null; approvedAt?: string | null; createdAt: string; items: PlanItem[] };
export type Task = { id: string; type: string; title: string; status: string; dueDate?: string | null; meta: Record<string, unknown>; carePlanId: string };
export type Dose = { id: string; medication: string; dose?: string | null; scheduledAt: string; status: string; recordedAt?: string | null; taskId: string };
export type Provider = { id: string; name: string; organization: string; type: string; specialties: string; location: string; phone?: string | null; rating: number };
export type Appointment = { id: string; kind: string; title: string; startsAt: string; endsAt: string; status: string; location?: string | null; sequence?: number | null; notes?: string | null; provider: Provider; referralId?: string | null; rescheduledFromId?: string | null; patientId: string };
export type Referral = {
  id: string; referralType: string; reason: string; urgency: string; sessions: number; frequencyPerWeek: number; durationWeeks: number; preferredStartWithinDays: number;
  status: string; provider?: Provider | null; providerNotes?: string | null; packageDocumentId?: string | null; timeline: { status: string; at: string; note?: string }[]; appointments: Appointment[]; createdAt: string;
};
export type Observation = { id: string; type: string; value?: number | null; value2?: number | null; unit?: string | null; text?: string | null; source: string; recordedAt: string; flagged: boolean; recordedBy?: { name: string; role: string } | null };
export type Rule = { id: string; metric: string; operator: string; threshold?: number | null; keywords?: string | null; windowHours?: number | null; action: string; severity: string; description: string; source: string };
export type Alert = {
  id: string; patientId: string; category: string; severity: string; title: string; message: string; status: string; escalationLevel: number; createdAt: string; acknowledgedAt?: string | null;
  escalateAfter?: string | null; resolution?: string | null; history: { at: string; event: string; by?: string }[]; assignedTo?: { name: string; role: string } | null; patient?: { user: { name: string } };
};
export type Doc = { id: string; type: string; title: string; content: string; data: unknown; visibleToPatient: boolean; reviewStatus?: string | null; engine?: string | null; createdAt: string; createdBy?: { name: string } | null; patientId: string; patient?: { user: { name: string } } };
export type AgentEvent = { id: string; agent: string; action: string; detail?: string | null; level: string; createdAt: string; patient?: { user: { name: string } } | null };

export type ReleaseRequest = {
  id: string; patientId: string; fromNurseId: string; suggestedNurseId?: string | null; toNurseId?: string | null; reason: string; status: string; kind: string;
  decisionNote?: string | null; decidedAt?: string | null; createdAt: string; fromNurseName: string | null; toNurseName: string | null; suggestedNurseName: string | null;
  decidedByName: string | null; handoff: { id: string; title: string; content: string; engine?: string | null; createdAt: string } | null;
  patient?: { id: string; user: { name: string } };
};

export type PatientRecord = {
  patient: Patient; viewer: { role: string; id: string }; plans: CarePlan[]; tasks: Task[]; doses: Dose[]; appointments: Appointment[]; referrals: Referral[];
  observations: Observation[]; rules: Rule[]; alerts: Alert[]; documents: Doc[]; events: AgentEvent[]; adherence: number | null; overallAdherence: number | null;
  releaseRequests: ReleaseRequest[];
};
