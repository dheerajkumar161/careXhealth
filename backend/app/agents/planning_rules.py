"""Deterministic fallback parser for the Care Planning agent (line-for-line port of planningRules.ts).

Used when Ollama is unavailable (or returns unusable output). Handles common discharge phrasing.
The test catalogue is passed in (fetched by the agent from the Test Center MCP server).
"""
from __future__ import annotations

import copy
import json
import math
import re
from typing import Any

DraftItem = dict[str, Any]  # {category, action?, title, source, rationale?, details}

I = re.I  # noqa: E741

WORD_NUM = {"once": 1, "one": 1, "twice": 2, "two": 2, "thrice": 3, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "ten": 10, "twelve": 12}


def num(s: str | None) -> float:
    """JS: WORD_NUM[s] ?? Number(s) — NaN when unparseable."""
    if not s:
        return math.nan
    if s.lower() in WORD_NUM:
        return WORD_NUM[s.lower()]
    try:
        return float(s)
    except ValueError:
        return math.nan


def clean(n: float) -> int | float:
    """101.0 → 101 (JSON/titles match the JS output)."""
    return int(n) if isinstance(n, float) and not math.isnan(n) and n.is_integer() else n


def truthy(n: float) -> bool:
    return bool(n) and not (isinstance(n, float) and math.isnan(n))


def js_round(x: float) -> int:
    return math.floor(x + 0.5)


def to_days(n: float, unit: str) -> float:
    return n * 7 if re.search(r"week", unit, I) else n * 30 if re.search(r"month", unit, I) else n


def upper_first(s: str) -> str:
    return s[:1].upper() + s[1:]


REFERRAL_TYPES: list[tuple[str, str]] = [
    (r"physio(therapy)?|physical therap", "Physiotherapy"),
    (r"occupational therap", "Occupational Therapy"),
    (r"speech therap", "Speech Therapy"),
    (r"diet(itian|ician)|nutrition", "Dietetics"),
    (r"psycholog|counsel|mental health", "Psychology"),
    (r"cardiolog", "Cardiology"),
    (r"home (nursing|care|visit)", "Home Nursing"),
    (r"wound (care|dressing)|dressing change", "Wound Care"),
    (r"endocrinolog|diabet(es|ic) (clinic|educator)", "Endocrinology"),
    (r"pulmonolog|pulmonary rehab", "Pulmonology"),
]

METRIC_WORDS: list[tuple[str, str, str]] = [
    (r"temperature|fever|temp\b", "TEMPERATURE", "°F"),
    (r"systolic|blood pressure|\bbp\b", "SYSTOLIC_BP", "mmHg"),
    (r"diastolic", "DIASTOLIC_BP", "mmHg"),
    (r"heart rate|pulse|\bhr\b", "HEART_RATE", "bpm"),
    (r"spo2|oxygen|saturation", "SPO2", "%"),
    (r"pain", "PAIN", "/10"),
    (r"sugar|glucose", "BLOOD_GLUCOSE", "mg/dL"),
    (r"weight (gain|increase)|gains? weight|gain (of|in) weight", "WEIGHT_GAIN", "kg"),
    (r"weight", "WEIGHT", "kg"),
]


def _metric(text: str) -> tuple[str, str, str] | None:
    return next((m for m in METRIC_WORDS if re.search(m[0], text, I)), None)


def red_flag_action(s: str) -> str:
    # "\bER\b" is case-sensitive on purpose: a case-insensitive "er" would match words like "fever"
    if re.search(r"emergency|ambulance|casualty|\b(911|108|112)\b", s, I) or re.search(r"\bER\b", s):
        return "EMERGENCY"
    if re.search(r"doctor|physician|surgeon|consultant", s, I):
        return "NOTIFY_DOCTOR"
    return "NOTIFY_NURSE"


def _action_label(action: str) -> str:
    return action.replace("_", " ", 1).lower()


def expand_shorthand(text: str) -> str:
    """Expands common prescription shorthand so typed notes like "Tab X 500mg 1-0-1 x 7d" parse like prose."""
    t = text
    t = re.sub(r"\b1\s*-\s*1\s*-\s*1\s*-\s*1\b", "four times daily", t)
    t = re.sub(r"\b1\s*-\s*1\s*-\s*1\b", "three times daily", t)
    t = re.sub(r"\b(1\s*-\s*0\s*-\s*1|1\s*-\s*1\s*-\s*0|0\s*-\s*1\s*-\s*1)\b", "twice daily", t)
    t = re.sub(r"\b(1\s*-\s*0\s*-\s*0|0\s*-\s*0\s*-\s*1|0\s*-\s*1\s*-\s*0)\b", "once daily", t)
    t = re.sub(r"\b(QID|q\.i\.d\.?)\b", "four times daily", t, flags=I)
    t = re.sub(r"\b(TDS|TID|t\.i\.d\.?)\b", "three times daily", t)
    t = re.sub(r"\b(BD|BID|b\.i\.d\.?)\b", "twice daily", t)
    t = re.sub(r"\b(OD|QD)\b", "once daily", t)
    t = re.sub(r"\bx\s*(\d+)\s*d(ays?)?\b", r"for \1 days", t, flags=I)
    t = re.sub(r"\bx\s*(\d+)\s*w(ee)?ks?\b", r"for \1 weeks", t, flags=I)
    t = re.sub(r"\b(\d)\s*x\s*/\s*w(ee)?k\b", r"\1 times a week", t, flags=I)
    t = re.sub(r"\breview\s+(in\s+)?(OPD|clinic)?\s*(after|in)\b", "follow up after", t, flags=I)
    t = re.sub(r"\bphysio\b", "physiotherapy", t, flags=I)
    return t


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.;\n])\s+|\n+", expand_shorthand(text).replace("\r", ""))
    out = [re.sub(r"^[-•*\d.)\s]+", "", p).strip() for p in parts if p]
    return [p for p in out if p]


def resolve_test_code(name: str, catalogue: list[dict[str, Any]]) -> str:
    s = name.lower()
    return next((t["code"] for t in catalogue if any(a in s for a in t["aliases"])), "CUSTOM")


def parse_sentence(s: str, diagnosis: str = "", catalogue: list[dict[str, Any]] | None = None) -> list[DraftItem]:
    catalogue = catalogue or []
    out: list[DraftItem] = []
    lower = s.lower()

    # Discontinue (amendments)
    stop = re.search(r"\b(?:stop|discontinue|hold)\s+(?:the\s+)?(?:medication\s+|medicine\s+|tab(?:let)?\.?\s+)?([A-Za-z][\w-]*(?:\s+[A-Za-z][\w-]*)?)", s, I)
    if stop:
        name = re.sub(r"\s+(now|immediately|today)$", "", stop.group(1), flags=I)
        return [{"category": "MEDICATION", "action": "DISCONTINUE", "title": f"Discontinue {stop.group(1)}", "source": "DOCTOR", "details": {"name": name}}]

    # Red flag: "... notify nurse if temperature exceeds 101°F" / "if temp > 101 call doctor"
    rf = re.search(
        r"(?:if|when)\s+([a-z0-9 ₂]+?)\s*(exceeds|is above|above|over|greater than|more than|>|>=|goes above|rises above|below|under|less than|<|<=|drops below|falls below)\s*(\d+(?:\.\d+)?)",
        s,
        I,
    )
    if rf and re.search(r"notify|call|inform|alert|report|contact|seek|emergency", s, I):
        metric = _metric(rf.group(1))
        if metric:
            op = "<" if re.search(r"below|under|less|<", rf.group(2), I) else ">"
            action = red_flag_action(s)
            return [
                {
                    "category": "RED_FLAG",
                    "title": f"{upper_first(rf.group(1).strip())} {op} {rf.group(3)}{metric[2]} → {_action_label(action)}",
                    "source": "DOCTOR",
                    "details": {"metric": metric[1], "operator": op, "threshold": clean(float(rf.group(3))), "unit": metric[2], "action": action, "severity": "CRITICAL" if action == "EMERGENCY" else "HIGH"},
                }
            ]
    # Symptom red flag: "report any chest pain or breathlessness immediately"
    if re.search(r"(notify|call|report|inform|seek|contact).*(if|any|immediately)|(if|in case of).*(notify|call|report)", s, I) and not rf:
        kw = re.search(r"(?:of|any|if|with)\s+([a-z ,/]+?)(?:\s+(?:immediately|occurs|develops|appear|is noted|notify|call|report)|[.,]|$)", s, I)
        if kw:
            keywords = [k.strip() for k in re.split(r",|\bor\b|\band\b|/", kw.group(1))]
            keywords = [k for k in keywords if len(k) > 2 and not re.fullmatch(r"the|any|patient|has|have", k)]
            if keywords:
                action = red_flag_action(s)
                return [
                    {
                        "category": "RED_FLAG",
                        "title": f"Symptoms: {', '.join(keywords)} → {_action_label(action)}",
                        "source": "DOCTOR",
                        "details": {"metric": "SYMPTOM", "operator": "CONTAINS", "keywords": keywords, "action": action, "severity": "MEDIUM" if action == "NOTIFY_NURSE" else "HIGH"},
                    }
                ]

    # Medication: "Take medication X 500mg twice daily for 7 days"
    med = re.search(
        r"(?:take|give|continue|start|tab(?:let)?\.?|cap(?:sule)?\.?|inj(?:ection)?\.?)\s+(?:the\s+)?(?:medication|medicine|tablet|tab\.?|capsule|cap\.?)?\s*"
        r"([A-Za-z][\w-]*(?:\s+(?!once|twice|thrice|daily|\d)[A-Za-z][\w-]*)?)\s*(\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|iu|units))?\s*(?:,?\s*)"
        r"(once|twice|thrice|one|two|three|four|\d+)\s*(?:times?)?\s*(?:a|per|/)?\s*(?:day|daily)"
        r"(?:.*?for\s+(\d+|one|two|three|four|five|six|seven|ten|twelve)\s*(days?|weeks?|months?))?",
        s,
        I,
    )
    if med and not re.search(r"(physio|therapy|session)", lower, I):
        freq = num(med.group(3))
        duration = clean(to_days(num(med.group(4)), med.group(5))) if med.group(4) else 7
        name = med.group(1).strip()
        dose = re.sub(r"\s+", "", med.group(2)) if med.group(2) else ""
        f_int = clean(freq)
        freq_label = "once" if freq == 1 else "twice" if freq == 2 else f"{f_int} times"
        instructions = ("After food" if re.search(r"after", s, I) else "Before food") if re.search(r"food|meal", s, I) else ""
        return [
            {
                "category": "MEDICATION",
                "title": f"{name}{' ' + dose if dose else ''} — {freq_label} daily for {duration} days",
                "source": "DOCTOR",
                "details": {"name": name, "dose": dose, "timesPerDay": f_int if truthy(freq) else 1, "durationDays": duration, "instructions": instructions},
            }
        ]

    # Referral / rehabilitation
    ref = next((r for r in REFERRAL_TYPES if re.search(r[0], s, I)), None)
    if ref and re.search(r"(refer|required|needs?|session|therapy|consult|schedule|arrange|visit|weekly|week)", s, I):
        pw = re.search(r"(once|twice|thrice|one|two|three|four|five|\d+)\s*(?:times?)?\s*(?:a|per|/)\s*week", s, I)
        per_week = clean(num(pw.group(1))) if pw and truthy(num(pw.group(1))) else 1
        weeks_m = re.search(r"for\s+(\d+|one|two|three|four|five|six|eight|twelve)\s*(weeks?|months?)", s, I)
        weeks = js_round(to_days(num(weeks_m.group(1)), weeks_m.group(2)) / 7) if weeks_m else 1
        sess_m = re.search(r"(\d+)\s*sessions?", s, I)
        explicit = num(sess_m.group(1)) if sess_m else math.nan
        sessions = clean(explicit) if truthy(explicit) else per_week * weeks
        start_m = re.search(r"(?:within|start(?:ing)?\s+in|after)\s+(\d+|one|two|three|four|five|seven)\s*(days?|weeks?)", s, I)
        ctx = f"{s} {diagnosis}"
        if ref[1] == "Physiotherapy":
            if re.search(r"cardiac|heart|pci|cabg|stent|mi\b", ctx, I):
                default_reason = "Phase II cardiac rehabilitation"
            elif re.search(r"pulmonary|lung|copd", ctx, I):
                default_reason = "Pulmonary rehabilitation"
            elif re.search(r"stroke|neuro", ctx, I):
                default_reason = "Neurological rehabilitation"
            else:
                default_reason = "Post-operative mobility rehabilitation"
        else:
            default_reason = f"{ref[1]} evaluation and management"
        reason_m = re.search(r"for\s+([a-z -]*?(?:rehab\w*|mobility|recovery|strength\w*|management|assessment|evaluation|control|support|counsel\w*)[a-z -]*)", s, I)
        reason = reason_m.group(1).strip() if reason_m else None
        plural = "s" if sessions > 1 else ""
        schedule = f", {per_week}/week for {weeks} week{'s' if weeks > 1 else ''}" if per_week > 1 or weeks > 1 else ""
        return [
            {
                "category": "REFERRAL",
                "title": f"{ref[1]} — {sessions} session{plural}{schedule}",
                "source": "DOCTOR",
                "details": {
                    "referralType": ref[1],
                    "reason": reason or ("Phase II cardiac rehabilitation" if re.search(r"cardiac rehab", s, I) else default_reason),
                    "sessions": sessions,
                    "frequencyPerWeek": per_week,
                    "durationWeeks": weeks,
                    "preferredStartWithinDays": clean(to_days(num(start_m.group(1)), start_m.group(2))) if start_m else 3,
                    "urgency": "URGENT" if re.search(r"urgent|asap|immediately", s, I) else "ROUTINE",
                },
            }
        ]
    # Generic "refer to <specialty>"
    generic = re.search(r"refer(?:ral)?\s+(?:to\s+)?(?:a\s+|an\s+)?([a-z ]+?)(?:\s+for\s+([a-z ,-]+))?(?:[.,]|$)", s, I)
    if generic:
        type_ = re.sub(r"\b(specialist|clinic|department)\b", "", generic.group(1).strip(), flags=I).strip()
        label = re.sub(r"\b\w", lambda m: m.group(0).upper(), type_)
        return [
            {
                "category": "REFERRAL",
                "title": f"{label} referral",
                "source": "DOCTOR",
                "details": {
                    "referralType": label,
                    "reason": generic.group(2).strip() if generic.group(2) else f"{label} consultation",
                    "sessions": 1,
                    "frequencyPerWeek": 1,
                    "durationWeeks": 1,
                    "preferredStartWithinDays": 7,
                    "urgency": "URGENT" if re.search(r"urgent", s, I) else "ROUTINE",
                },
            }
        ]

    # Investigation: "Check CBC after 5 days", "Repeat X-ray in 2 weeks"; bare "CBC after 5 days" only for known tests
    inv_verb = re.search(r"(?:check|repeat|do|order|get|perform|test)\s+(?:a\s+)?([A-Za-z0-9/\- ]+?)\s+(?:after|in|on day|on|at)\s+(?:day\s+)?(\d+|one|two|three|four|five|seven|ten)\s*(days?|weeks?)?", s, I)
    inv_bare = re.match(r"^([A-Za-z0-9/\- ]{2,30}?)\s+(?:after|in|on day)\s+(?:day\s+)?(\d+|one|two|three|four|five|seven|ten)\s*(days?|weeks?)?", s, I)
    inv = inv_verb or (inv_bare if inv_bare and resolve_test_code(inv_bare.group(1), catalogue) != "CUSTOM" else None)
    if inv and not re.search(r"follow", lower, I):
        days = clean(to_days(num(inv.group(2)), inv.group(3) or "days"))
        test = inv.group(1).strip()
        return [
            {
                "category": "INVESTIGATION",
                "title": f"{test.upper() if len(test.upper()) <= 6 else test} on day {days}",
                "source": "DOCTOR",
                "details": {"test": test, "dayOffset": days, "instructions": "Fasting required" if re.search(r"fast", s, I) else ""},
            }
        ]

    # Follow-up: "Follow up after 2 weeks (with orthopedics)"
    fu = re.search(r"follow[\s-]?up(?:\s+(?:visit|appointment|consultation))?(?:\s+with\s+([a-z ]+?))?\s+(?:after|in)\s+(\d+|one|two|three|four|six)\s*(days?|weeks?|months?)(?:\s+with\s+([a-z ]+))?", s, I)
    if fu:
        days = clean(to_days(num(fu.group(2)), fu.group(3)))
        who = (fu.group(1) or fu.group(4) or "").strip()
        span = f"{clean(days / 7)} week{'s' if days > 7 else ''}" if days >= 7 and days % 7 == 0 else f"{days} days"
        return [
            {
                "category": "FOLLOW_UP",
                "title": f"Follow-up{' with ' + who if who else ''} in {span}",
                "source": "DOCTOR",
                "details": {"specialty": who or "", "withTreatingDoctor": not who or bool(re.search(r"me|surgeon|treating|same", who, I)), "dayOffset": days, "reason": "Post-discharge review"},
            }
        ]

    # Monitoring: "Check temperature twice daily", "monitor BP daily"
    mon = re.search(r"(?:check|monitor|record|measure|log)\s+(?:the\s+)?([a-z0-9 ₂]+?)\s+(once|twice|thrice|\d+\s*times)?\s*(?:a\s+)?(daily|a day|every day|per day)", s, I)
    if mon:
        metric = _metric(mon.group(1))
        if metric:
            tpd = num(mon.group(2).split()[0]) if mon.group(2) else math.nan
            return [
                {
                    "category": "MONITORING",
                    "title": f"Record {mon.group(1).strip()} {mon.group(2) or 'once'} daily",
                    "source": "DOCTOR",
                    "details": {"metric": metric[1], "timesPerDay": clean(tpd) if truthy(tpd) else 1, "unit": metric[2]},
                }
            ]

    title = re.sub(r"\.$", "", s)
    if re.search(r"\b(avoid|do not|don't|no\s+\w+ing|refrain|restrict|limit|not allowed)\b", s, I):
        out.append({"category": "RESTRICTION", "title": title, "source": "DOCTOR", "details": {"text": s}})
    elif re.search(r"\b(diet|eat|food|meal|salt|sugar|fluid|water|protein|fibre|fiber)\b", s, I):
        out.append({"category": "DIET", "title": title, "source": "DOCTOR", "details": {"text": s}})
    elif re.search(r"\b(walk|exercise|mobili[sz]e|stretch|physical activity|bend|stairs)\b", s, I):
        out.append({"category": "EXERCISE", "title": title, "source": "DOCTOR", "details": {"text": s}})
    elif len(s.split(" ")) >= 3 and not re.search(r"^(patient|pt)\s+(underwent|had|is|was|admitted)", s, I) and not re.search(r"^(post|s/p|status post|diagnosis|dx|k/c/o|known case)\b", s, I):
        out.append({"category": "CARE_INSTRUCTION", "title": title, "source": "DOCTOR", "details": {"text": s}})
    return out


def _ai(category: str, title: str, rationale: str, details: dict[str, Any]) -> DraftItem:
    return {"category": category, "title": title, "source": "AI_SUGGESTED", "rationale": rationale, "details": details}


SUGGESTIONS: list[tuple[str, list[DraftItem]]] = [
    (
        r"wrist|radius|ulna|forearm|elbow|humerus|shoulder|clavicle|hand|finger",
        [
            _ai("EXERCISE", "Finger, thumb and shoulder range-of-motion exercises, 10 reps 4 times daily", "Prevents stiffness of joints not immobilised", {"text": "Gently open and close your fingers, touch thumb to each finger, and move your shoulder through full range — 10 times, 4 times a day"}),
            _ai("CARE_INSTRUCTION", "Keep the cast/splint and dressing clean and dry; cover with a plastic bag while bathing", "Prevents surgical site infection and skin breakdown", {"text": "Keep the cast or dressing dry; cover it while bathing"}),
            _ai("DIET", "Calcium- and protein-rich diet to support bone healing", "Supports fracture union and wound healing", {"text": "Include milk, curd, paneer, eggs or dal daily"}),
            _ai(
                "RED_FLAG",
                "Numbness, tingling, blue/cold fingers or severe swelling → notify doctor",
                "Possible neurovascular compromise or compartment syndrome",
                {"metric": "SYMPTOM", "operator": "CONTAINS", "keywords": ["numb", "tingling", "blue finger", "cold finger", "severe swelling", "pus", "discharge"], "action": "NOTIFY_DOCTOR", "severity": "HIGH"},
            ),
        ],
    ),
    (
        r"knee|hip|ankle|femur|tibia|lower limb|arthroplasty|joint replacement",
        [
            _ai("EXERCISE", "Ankle pumps and quadriceps sets 10 reps, 3 times daily", "Reduces DVT risk and maintains muscle activation after lower-limb surgery", {"text": "Ankle pumps and static quadriceps exercises, 10 repetitions three times a day"}),
            _ai("EXERCISE", "Short assisted walks with walker every 2–3 hours while awake", "Early mobilisation improves recovery and prevents stiffness", {"text": "Short walks with walker support every 2–3 hours during the day"}),
            _ai("DIET", "High-protein diet with adequate calcium and vitamin D", "Supports wound healing and bone recovery", {"text": "Include protein at every meal (dal, eggs, paneer, fish), plus dairy for calcium"}),
            _ai("RESTRICTION", "No kneeling, squatting or twisting on the operated leg for 6 weeks", "Protects the joint during early healing", {"text": "Avoid kneeling, squatting, crossing legs or twisting on the operated leg"}),
            _ai("CARE_INSTRUCTION", "Keep the wound dressing clean and dry; no soaking until sutures are removed", "Prevents surgical site infection", {"text": "Keep dressing clean and dry, sponge bath only"}),
            _ai(
                "RED_FLAG",
                "Calf pain/swelling, wound discharge or breathlessness → notify doctor",
                "Possible DVT, wound infection or pulmonary embolism",
                {"metric": "SYMPTOM", "operator": "CONTAINS", "keywords": ["calf pain", "calf swelling", "wound discharge", "pus", "breathless", "shortness of breath"], "action": "NOTIFY_DOCTOR", "severity": "HIGH"},
            ),
        ],
    ),
    (
        r"cardiac|heart|myocard|angioplasty|cabg|bypass|stent|mi\b|failure",
        [
            _ai("DIET", "Low-salt (< 2 g sodium/day), low saturated-fat diet", "Reduces cardiac workload and fluid retention", {"text": "Limit salt, avoid fried/processed food, prefer fruit, vegetables and whole grains"}),
            _ai("EXERCISE", "Gradual walking programme starting at 5–10 minutes twice daily", "Phase-II cardiac rehabilitation principles", {"text": "Start with 5–10 minute walks twice daily, increase gradually as tolerated"}),
            _ai("MONITORING", "Record blood pressure and heart rate daily", "Early detection of haemodynamic deterioration", {"metric": "SYSTOLIC_BP", "timesPerDay": 1, "unit": "mmHg"}),
            _ai(
                "RED_FLAG",
                "Chest pain, breathlessness or fainting → emergency",
                "Possible acute coronary event",
                {"metric": "SYMPTOM", "operator": "CONTAINS", "keywords": ["chest pain", "breathless", "shortness of breath", "fainting", "palpitations"], "action": "EMERGENCY", "severity": "CRITICAL"},
            ),
        ],
    ),
    (
        r"diabet|glucose|insulin",
        [
            _ai("DIET", "Diabetic diet — avoid refined sugar, regular meal timings", "Glycaemic control", {"text": "Avoid sweets and sugary drinks; eat at regular times; prefer whole grains"}),
            _ai("MONITORING", "Record fasting blood glucose daily", "Track glycaemic control", {"metric": "BLOOD_GLUCOSE", "timesPerDay": 1, "unit": "mg/dL"}),
            _ai("RED_FLAG", "Blood glucose < 70 mg/dL → notify nurse", "Hypoglycaemia risk", {"metric": "BLOOD_GLUCOSE", "operator": "<", "threshold": 70, "unit": "mg/dL", "action": "NOTIFY_NURSE", "severity": "HIGH"}),
        ],
    ),
    (
        r"pneumon|copd|asthma|respir|lung",
        [
            _ai("EXERCISE", "Deep-breathing / incentive spirometry 10 times every hour while awake", "Improves lung expansion", {"text": "Deep breathing exercises hourly while awake"}),
            _ai("RED_FLAG", "SpO₂ < 92% → notify doctor", "Hypoxaemia", {"metric": "SPO2", "operator": "<", "threshold": 92, "unit": "%", "action": "NOTIFY_DOCTOR", "severity": "HIGH"}),
        ],
    ),
]

GENERIC: list[DraftItem] = [
    _ai("DIET", "Stay well hydrated — 2–2.5 L of fluids per day unless restricted", "General post-discharge recovery", {"text": "Drink 8–10 glasses of water daily unless your doctor has restricted fluids"}),
    _ai("CARE_INSTRUCTION", "Rest adequately and keep all scheduled appointments", "General post-discharge recovery", {"text": "Sleep 7–8 hours and attend all appointments"}),
]


def rule_based_plan(instructions: str, diagnosis: str, *, suggestions: bool = True, catalogue: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    items: list[DraftItem] = [i for s in sentences(instructions) for i in parse_sentence(s, diagnosis, catalogue)]
    if suggestions:
        context = f"{diagnosis} {instructions}"
        extra = [copy.deepcopy(i) for pattern, group in SUGGESTIONS if re.search(pattern, context, I) for i in group]
        for sug in extra + copy.deepcopy(GENERIC):
            dup = any(
                i["category"] == sug["category"]
                and (
                    i["title"].lower() == sug["title"].lower()
                    or (sug["category"] == "RED_FLAG" and str(sug["details"].get("metric")) in json.dumps(i["details"]) and sug["details"].get("metric") != "SYMPTOM")
                )
                for i in items
            )
            if not dup:
                items.append(sug)
    counts: dict[str, int] = {}
    for i in items:
        counts[i["category"]] = counts.get(i["category"], 0) + 1
    doctor = len([i for i in items if i["source"] == "DOCTOR"])
    ai = len([i for i in items if i["source"] == "AI_SUGGESTED"])
    summary = f"Structured {doctor} doctor instructions into {len(counts)} care categories and suggested {ai} supportive items for review."
    return {"summary": summary, "items": items}
