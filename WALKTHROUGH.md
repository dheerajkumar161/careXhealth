# End-to-end walkthrough: trigger every agent action

The database starts clean: one referring doctor, one nurse, one **admitted** patient (no plan, no history), one specialist doctor who receives referrals (physiotherapy) and one test center. Every record you see afterwards is created live by the agents as you go.

**Setup**

```powershell
# terminal 1 — API, agents, MCP servers, scheduler
cd backend
.venv\Scripts\python scripts\seed.py   # back to the clean state at any time
.venv\Scripts\python main.py            # http://127.0.0.1:8000

# terminal 2 — UI
cd frontend
npm run dev                              # http://localhost:5173
```

All passwords are `Password@123`. Use separate browser profiles (or one normal and one private window) to stay logged in as two roles at once.

| Role | Login |
|---|---|
| Doctor | ananya.rao@carexhealth.health |
| Nurse | priya.nair@carexhealth.health |
| Second nurse (takes over on handover) | rahul.verma@carexhealth.health |
| Patient | arjun.sharma@example.com |
| Specialist doctor (receives referrals) | kavya.menon@carexhealth.health |
| Test center | reports@citydiagnostics.in |
| Admin (audit log, users) | admin@carexhealth.health |

`backend/.env` is set up for a fast walkthrough:
- `DEMO_MODE=true` lets you record doses, sessions and results before their scheduled time.
- `ESCALATION_MINUTES=2` and `AGENT_CYCLE_SECONDS=30` make escalation happen in minutes (APScheduler jobs run every 30 s).

Set these back to `false`, `15` and `60` for real use.

**New accounts.** The login page has **Create an account** for doctors (with a specialty; they can receive referrals), nurses and test centers. Patients are registered by their doctor (**Register patient**). Set `SIGNUP_INVITE_CODE` in `backend/.env` to require a code.

**Where to watch the agents.** Open the patient as the doctor and go to the **Agent activity** tab. Every action is logged there with its agent: Care Planning, Execution & Scheduling, Monitoring & Escalation, Communication & Docs, Clinical Intelligence, Hospital Service or Clinician. The bell icon shows the notifications each role receives.

---

## Phase 1: Discharge (Care Planning agent)

**Doctor →** Patients → Arjun Sharma → **Care plan** tab. Paste this note and click **Generate care plan**:

> Patient underwent right total knee replacement. Take Tab Cefuroxime 500mg twice daily for 7 days. Take Tab Paracetamol 650mg three times daily for 5 days. Check CBC after 5 days. Follow up after 2 weeks. Physiotherapy required three times a week for 4 weeks. Avoid strenuous activity. Notify nurse if temperature exceeds 101°F.

**Or attach the note as an image.** Click **Attach a photo or scan**, drag & drop, or paste (Ctrl+V) up to 4 photos of a handwritten or printed discharge note or prescription. You can attach images with or without typed text. The agent:
- reads each image with the Groq vision model (`GROQ_VISION_MODEL`; `OLLAMA_VISION_MODEL` is the optional local fallback);
- expands shorthand (`1-0-1` = twice daily, `BD`/`TDS`, `x 7d`, `SOS` = as needed, "Review in OPD after 2 weeks" = follow-up);
- merges it with any typed text;
- flags anything it couldn't read, and **warns if the patient name on the paper doesn't match**.

In the draft, open **Original instructions & source images** and click a thumbnail to compare the image with the transcript line by line. The images are kept in the patient's **Documents** (clinicians only). As-needed medicines (PRN/SOS) get no fixed schedule or reminders.

What happens:
- **Planning:** structures the note into medication, investigation, follow-up, referral, restriction and red-flag items. It adds diet, exercise and care suggestions, each marked **AI suggested** with a rationale.
- The draft waits for the doctor. Expand any item to edit its fields, untick one to exclude it, or use **+ Add an item…**.

## Phase 2–3: Approve → Execution

Click **Approve & activate**.

What happens:
- **Planning:** hands requirements to Execution and red-flag rules to Monitoring.
- **Execution:** creates the medication schedules (dose times and reminders).
- **Test Center service:** books the CBC; the patient is notified.
- **Scheduling service:** books the 2-week follow-up with Dr. Rao; patient and doctor are notified.
- **Provider Directory:** matches MoveWell Physiotherapy and holds 12 slots.
- **Clinical Intelligence:** writes the referral clinical summary.
- **Communication & Docs:** builds the referral package and routes it to the physiotherapist.
- **Monitoring:** registers the doctor's rules plus system safety nets (missed doses, missed sessions, abnormal labs, emergency symptoms).
- **Communication:** writes a plain-language **My Recovery Plan** for the patient.

Check it in **Schedule & tasks** (tasks, doses, appointments, referral tracker at "Sent"), **Monitoring → Active monitoring rules**, and **Documents**.

## Phase 4: Doctor-to-doctor referral

**Specialist (Dr. Kavya Menon) →** Referrals → **Requests to me**. Open **View patient details** to read the referral package (patient info, diagnosis, clinical summary, care plan, reports).

### 4a. Reject with a reason
Click **Reject**. A reason is required, for example:

> Need a recent X-ray report before starting. Can only offer 2 sessions per week.

What happens:
- **Execution:** releases the held slots and returns the referral to the referring doctor. Nothing is silently re-routed.
- **Referring doctor:** gets a notification. The referral shows in **Needs your decision** on the Overview, and as a red **Rejected by…** card in Referrals → **Sent by me**.

### 4b. Revise and resend (referring doctor)
**Dr. Ananya Rao →** Referrals → **Sent by me** → **Auto-revise with agent** (or **Edit & resend** to change it by hand).

What happens:
- **Planning:** reads the rejection reason and proposes a revised referral (e.g. 2 sessions/week, longer duration) plus care-plan changes (e.g. *Knee X-ray*). It also drafts a note to the specialist.
- Review or edit everything, optionally pick a specialist under **Send to**, then click **Apply changes & resend**.
- The ticked care-plan changes become an approved amendment and are executed (the X-ray is booked with the test center). The referral item in the care plan is updated.
- **Execution:** holds new slots and routes the revised request. **Communication** rebuilds the package with a *Resubmission* section showing the earlier reason and what changed.

### 4c. Accept
**Specialist →** Requests to me → the revised request (marked **Revised v2**) → **Accept patient**.

What happens:
- **Execution:** converts held slots into bookings. The referral moves to Accepted → Scheduled. Patient and doctor are notified.
- The patient now appears under **Patients in your care**, where the specialist marks sessions **Attended** or **Missed**.

Hover any card in the Overview **Referral pipeline** for details; click it to open the referral.

## Phase 5: Recovery and Monitoring

| Action (who → where) | Agents triggered |
|---|---|
| **Specialist →** Referrals → Requests to me → Patients in your care → session 1 **Attended** | Execution: referral moves to **In treatment** |
| **Specialist →** session 2 **Missed** | Execution finds a replacement slot and notifies patient and specialist; Monitoring alerts the nurse ("Missed: Physiotherapy session 2") |
| **Patient →** Today → mark one dose **Taken** | Execution records adherence |
| **Patient →** **Skip** 2 doses | Monitoring: a single miss is only recorded; 2+ is a pattern, which alerts the nurse ("Repeated medication non-adherence") |
| **Patient →** How are you feeling? → Temperature `102` → **Record & check** | Monitoring: doctor's red flag (>101°F) alerts the nurse |
| **Patient →** Temperature `99` | Monitoring: within thresholds, logged only |
| **Patient →** Care assistant: *"What medicines do I take today?"* | Communication answers from the approved plan only |
| **Patient →** Care assistant: *"I have chest pain and feel breathless"* | Communication forwards it to Monitoring as an emergency symptom (critical, level 3); doctor and nurse alerted |

If only one dose is left today, skip the second one as the **Nurse →** patient → Schedule & tasks → **±7 days**.

## Phase 6: Test report

**Test center →** Tests → CBC → **Upload results**. Enter e.g. Hb `10.8`, WBC `14.2`, Platelets `300`, Neutrophils `80` → **Submit report**.

What happens:
- **Communication & Docs:** matches the patient and the investigation, flags values against reference ranges, stores the report and notifies the doctor and patient.
- **Monitoring:** raises an "Abnormal Complete Blood Count" alert to the doctor (level 2).

## Phase 7: Doctor decision (closed loop)

**Doctor →** Overview → *Needs your decision* → open the report → **Mark as reviewed**.

Then go to **Care plan** → *Clinical decision / order change*, enter:

> Stop Cefuroxime. Start Tab Amoxiclav 625mg twice daily for 5 days. Repeat CBC in 3 days.

Click **Draft amendment**, then **Approve & activate**.

What happens:
- **Planning:** creates a versioned amendment (DISCONTINUE Cefuroxime, ADD Amoxiclav, ADD CBC).
- **Execution:** cancels the remaining Cefuroxime doses, schedules Amoxiclav and books a new CBC.
- The **Plan history** shows v1 → amendment.

## Removing an item from an active plan

**Doctor →** patient → **Care plan** → hover any item in *Active care plan* → bin icon → enter a reason → **Remove & cancel activity**.

What happens:
- **Execution:** cancels what that item set in motion: pending doses (medication), bookings (test/follow-up), the referral and its sessions, or the monitoring rule (red flag).
- **Communication:** refreshes the patient's plan and notifies them.

The doctor's **Tests** page lists every ordered test with its booking, result and review status.

## Escalation

Leave any alert unacknowledged for about **2 minutes**. The background loop runs every 30 seconds, or click **Agents live** in the header (doctor or nurse) to run it immediately.

What happens:
- **Monitoring:** escalates nurse (L1) → doctor (L2) → emergency (L3). The alert card's **Show history** lists each step.

Then, as the **Nurse →** Alert queue: **Acknowledge** (this stops auto-escalation) → **Resolve** with a note. **Escalate to Doctor** escalates manually.

## Phase 8: Clinical Intelligence

| Action | Result |
|---|---|
| **Nurse →** Shift overview → **Generate shift handoff** | Handoff for each patient: status, active concern, vitals, adherence, report, upcoming, pending, alerts, action required |
| **Doctor/Nurse →** patient → **Generate nurse handoff** / **Recovery summary** | Longitudinal summary with an AI narrative over the actual facts |

## Nurse handover (release from a patient)

1. **Nurse (Priya) →** patient → **Request release** (top right of the patient card). Give a reason and optionally suggest a colleague.
   - **Clinical Intelligence:** generates a handoff summary and attaches it to the request.
   - The treating doctor is notified. Priya **stays responsible** (alerts keep routing to her) and sees a "Release requested" banner, where she can **Withdraw** it.
2. **Doctor →** Overview → *Needs your decision* → the release request (or open the patient). Read **View handoff summary**, choose the next nurse (each shows their current patient count), then **Approve & reassign**.
   - The patient moves to the new nurse.
   - **Monitoring:** open nurse-level alerts are re-routed with a fresh acknowledgement window.
   - The new nurse is notified and sees the handoff in Documents. Priya is notified and loses access.
3. **Or Decline** with a reason. The nurse is told why and stays assigned.
4. The doctor **cannot** take a nurse off a patient on their own: removal always starts with the nurse's request. The doctor only sees **Assign nurse** for a patient who has no nurse at all.

All of it shows under **Nurse assignment history** (patient Overview) and in **Agent activity**.

## Role-based access checks

- Patient opening `/doctor` is redirected to `/patient`.
- A specialist sees only patients referred to them, through the referral package. They cannot edit another doctor's care plan.
- Rejecting a referral requires a reason, and only the receiving specialist can accept or reject it.
- Patient's Documents shows only their recovery plan and lab reports.
- The nurse cannot approve plans; only the treating doctor can.
- Only the assigned nurse can request release, only the treating doctor can approve or decline it, and a released nurse can no longer open the patient.
