"""Deterministic prescribing-safety checks for a care plan (no LLM): allergies, interactions, duplicate therapy, dose ceilings.

Run on every DRAFT plan. BLOCK findings must be explicitly overridden by the treating doctor (with a reason, audited) before the
plan can be approved; WARN findings are shown to the doctor but do not stop approval. This is a curated, conservative rule set —
it supplements, never replaces, clinical judgement.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# ── drug knowledge (generic names, lower-case; brand names mapped where common in India) ─────────────────────────────
CLASSES: dict[str, set[str]] = {
    "penicillin": {"penicillin", "amoxicillin", "amoxycillin", "ampicillin", "piperacillin", "cloxacillin", "flucloxacillin", "dicloxacillin", "augmentin", "co-amoxiclav", "amoxiclav", "mox", "novamox"},
    "cephalosporin": {"cefuroxime", "cefixime", "cefpodoxime", "cefazolin", "ceftriaxone", "cefotaxime", "ceftazidime", "cefepime", "cephalexin", "cefalexin", "cefadroxil", "cefdinir", "cefoperazone", "taxim", "monocef"},
    "sulfonamide": {"sulfamethoxazole", "cotrimoxazole", "co-trimoxazole", "bactrim", "sulfasalazine", "sulfadiazine", "septran"},
    "nsaid": {"ibuprofen", "diclofenac", "naproxen", "aspirin", "ketorolac", "etoricoxib", "aceclofenac", "indomethacin", "piroxicam", "celecoxib", "nimesulide", "mefenamic", "brufen", "voveran"},
    "opioid": {"tramadol", "morphine", "codeine", "tapentadol", "fentanyl", "oxycodone", "pethidine"},
    "macrolide": {"azithromycin", "clarithromycin", "erythromycin", "roxithromycin"},
    "fluoroquinolone": {"ciprofloxacin", "levofloxacin", "ofloxacin", "moxifloxacin", "norfloxacin"},
    "statin": {"atorvastatin", "simvastatin", "rosuvastatin", "pravastatin", "lovastatin"},
    "ppi": {"omeprazole", "pantoprazole", "esomeprazole", "rabeprazole", "lansoprazole", "pan"},
    "ssri": {"fluoxetine", "sertraline", "paroxetine", "citalopram", "escitalopram", "fluvoxamine"},
    "ace_arb": {"enalapril", "lisinopril", "ramipril", "perindopril", "captopril", "losartan", "telmisartan", "valsartan", "olmesartan", "irbesartan"},
    "nitrate": {"isosorbide", "nitroglycerin", "glyceryl trinitrate", "gtn", "nitroglycerine"},
    "anticoagulant": {"warfarin", "acenocoumarol", "rivaroxaban", "apixaban", "dabigatran", "enoxaparin", "heparin"},
    "antiplatelet": {"clopidogrel", "prasugrel", "ticagrelor"},
    "beta_blocker": {"metoprolol", "atenolol", "propranolol", "bisoprolol", "carvedilol", "nebivolol"},
}
ALLERGY_ALIASES = {
    "penicillin": "penicillin", "penicillins": "penicillin", "amoxicillin": "penicillin", "sulfa": "sulfonamide", "sulpha": "sulfonamide", "sulfonamide": "sulfonamide", "sulfonamides": "sulfonamide",
    "nsaid": "nsaid", "nsaids": "nsaid", "aspirin": "nsaid", "ibuprofen": "nsaid", "diclofenac": "nsaid", "cephalosporin": "cephalosporin", "cephalosporins": "cephalosporin",
    "codeine": "opioid", "morphine": "opioid", "opioid": "opioid", "opioids": "opioid", "tramadol": "opioid", "macrolide": "macrolide", "erythromycin": "macrolide", "azithromycin": "macrolide",
    "quinolone": "fluoroquinolone", "fluoroquinolone": "fluoroquinolone", "ciprofloxacin": "fluoroquinolone", "statin": "statin",
}
CROSS_REACTIVE = {"penicillin": {"cephalosporin"}, "cephalosporin": {"penicillin"}}  # ~1–10 % cross-sensitivity → warning, not block
ANTIBIOTIC_FOR_WARFARIN = {"ciprofloxacin", "levofloxacin", "metronidazole", "azithromycin", "clarithromycin", "erythromycin", "cotrimoxazole", "co-trimoxazole", "fluconazole"}
FILLER = {"drug", "drugs", "allergy", "allergic", "to", "medicine", "medicines", "antibiotic", "antibiotics", "class", "reaction", "hypersensitivity"}
PARACETAMOL = {"paracetamol", "acetaminophen", "crocin", "dolo", "calpol"}


@dataclass
class Finding:
    severity: str  # "BLOCK" | "WARN"
    code: str  # stable id used for overrides, e.g. "ALLERGY:penicillin:amoxicillin"
    title: str
    message: str
    items: list[str] = field(default_factory=list)  # titles of the plan items involved

    def to_dict(self) -> dict[str, Any]:
        return {"severity": self.severity, "code": self.code, "title": self.title, "message": self.message, "items": self.items}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 \-]", " ", (s or "").lower()).strip()


def _tokens(name: str) -> set[str]:
    n = _norm(name)
    return {t for t in re.split(r"[ \-/]+", n) if t} | {n}


def _drug_classes(name: str) -> set[str]:
    toks = _tokens(name)
    return {c for c, members in CLASSES.items() if toks & members or any(m in _norm(name) for m in members if len(m) > 5)}


def _generic(name: str) -> str:
    """Drug identity for duplicate detection: first alphabetic token that is not a dose-form word."""
    for t in re.split(r"[ /,]+", _norm(name)):
        if t and t not in {"tab", "tablet", "cap", "capsule", "syp", "syrup", "inj", "injection", "oral", "iv", "im"} and not t[0].isdigit():
            return t
    return _norm(name)


def _mg(dose: Any) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*(mg|g)\b", str(dose or "").lower())
    if not m:
        return None
    return float(m.group(1)) * (1000 if m.group(2) == "g" else 1)


def _times(d: dict[str, Any]) -> float:
    try:
        return float(d.get("timesPerDay") or 1)
    except (TypeError, ValueError):
        return 1.0


def check_plan(items: list[dict[str, Any]], *, allergies: str | None, comorbidities: str | None, current_meds: list[str] | None = None) -> list[Finding]:
    """`items`: plan items (dicts with category/title/action/details/included); `current_meds`: names already active for the patient."""
    out: list[Finding] = []
    meds = [i for i in items if i.get("category") == "MEDICATION" and i.get("included", True) and i.get("action") != "DISCONTINUE"]
    named = [(((i.get("details") or {}).get("name")) or i.get("title") or "", i) for i in meds]
    allergy_classes: dict[str, str] = {}
    for raw in re.split(r"[,;/\n]+| and ", allergies or ""):
        words = [w for w in _norm(raw).split() if w not in FILLER]
        a = " ".join(words)
        if not a or a in {"none", "nil", "no known", "nkda", "na", "n a", "known"}:
            continue
        key = ALLERGY_ALIASES.get(a) or next((ALLERGY_ALIASES[w] for w in words if w in ALLERGY_ALIASES), a)
        allergy_classes[key] = raw.strip()

    # 1 · allergies (direct → BLOCK, cross-reactive class → WARN)
    for name, it in named:
        classes = _drug_classes(name) | {_generic(name)}
        for allergen, label in allergy_classes.items():
            if allergen in classes or allergen in _tokens(name):
                out.append(Finding("BLOCK", f"ALLERGY:{allergen}:{_generic(name)}", "Documented allergy", f"{name} conflicts with the patient's documented allergy to {label}.", [it["title"]]))
            elif any(allergen in CROSS_REACTIVE.get(c, set()) or c in CROSS_REACTIVE.get(allergen, set()) for c in classes):
                out.append(Finding("WARN", f"CROSS:{allergen}:{_generic(name)}", "Possible cross-reactivity", f"{name} may cross-react with the documented {label} allergy — confirm tolerance or choose an alternative.", [it["title"]]))

    # 2 · interactions among plan drugs and the patient's current medicines
    pool = [(n, _drug_classes(n), _generic(n), it["title"]) for n, it in named] + [(m, _drug_classes(m), _generic(m), m) for m in (current_meds or [])]
    seen: set[str] = set()

    def pair(code: str, sev: str, title: str, msg: str, a: tuple, b: tuple) -> None:
        key = f"{code}:{min(a[2], b[2])}:{max(a[2], b[2])}"
        if key not in seen and a is not b and a[2] != b[2]:
            seen.add(key)
            out.append(Finding(sev, key, title, msg, [x for x in dict.fromkeys([a[3], b[3]]) if x]))

    for i, a in enumerate(pool):
        for b in pool[i + 1 :]:
            for x, y in ((a, b), (b, a)):
                cx, cy = x[1], y[1]
                if "anticoagulant" in cx and "nsaid" in cy:
                    pair("INT-ANTICOAG-NSAID", "BLOCK", "Bleeding risk", f"{x[0]} (anticoagulant) with {y[0]} (NSAID) greatly increases bleeding risk.", x, y)
                if "anticoagulant" in cx and (y[2] in ANTIBIOTIC_FOR_WARFARIN or "macrolide" in cy or "fluoroquinolone" in cy):
                    pair("INT-ANTICOAG-ABX", "WARN", "Raised INR / bleeding risk", f"{y[0]} can potentiate {x[0]}; monitor INR closely.", x, y)
                if "nitrate" in cx and y[2] in {"sildenafil", "tadalafil", "vardenafil"}:
                    pair("INT-NITRATE-PDE5", "BLOCK", "Severe hypotension", f"{x[0]} with {y[0]} can cause profound hypotension — contraindicated.", x, y)
                if "ssri" in cx and (y[2] in {"tramadol", "linezolid"} or "opioid" in cy and y[2] == "tramadol"):
                    pair("INT-SEROTONIN", "WARN", "Serotonin syndrome risk", f"{x[0]} with {y[0]} raises the risk of serotonin syndrome and seizures.", x, y)
                if x[2] == "methotrexate" and (y[2] in {"cotrimoxazole", "co-trimoxazole", "trimethoprim", "bactrim"} or "sulfonamide" in cy):
                    pair("INT-MTX-TMP", "BLOCK", "Marrow toxicity", f"{y[0]} with methotrexate can cause severe bone-marrow suppression.", x, y)
                if "statin" in cx and ("macrolide" in cy and y[2] in {"clarithromycin", "erythromycin"}) and x[2] in {"simvastatin", "lovastatin", "atorvastatin"}:
                    pair("INT-STATIN-MACROLIDE", "WARN", "Myopathy risk", f"{y[0]} raises {x[0]} levels — risk of myopathy/rhabdomyolysis.", x, y)
                if "ace_arb" in cx and "nsaid" in cy:
                    pair("INT-ACE-NSAID", "WARN", "Kidney injury risk", f"{y[0]} with {x[0]} can reduce kidney function and blunt the blood-pressure effect.", x, y)
                if x[2] == "clopidogrel" and y[2] in {"omeprazole", "esomeprazole"}:
                    pair("INT-CLOPI-PPI", "WARN", "Reduced antiplatelet effect", f"{y[0]} can reduce the effect of clopidogrel; consider pantoprazole.", x, y)
                if "anticoagulant" in cx and "antiplatelet" in cy:
                    pair("INT-ANTICOAG-ANTIPLATELET", "WARN", "Bleeding risk", f"{x[0]} with {y[0]} raises bleeding risk.", x, y)

    # 3 · duplicate therapy
    by_generic: dict[str, list[str]] = {}
    for n, it in named:
        by_generic.setdefault(_generic(n), []).append(it["title"])
    for g, titles in by_generic.items():
        if len(titles) > 1:
            out.append(Finding("WARN", f"DUP:{g}", "Duplicate medicine", f"{g.title()} appears {len(titles)} times in this plan.", titles))
    for cls in ("nsaid", "ppi", "opioid", "statin"):
        members = [(n, it) for n, it in named if cls in _drug_classes(n)]
        if len({_generic(n) for n, _ in members}) > 1:
            out.append(Finding("WARN", f"DUPCLASS:{cls}", "Duplicate drug class", f"More than one {cls.upper() if cls in {'nsaid', 'ppi'} else cls} medicine is prescribed: " + ", ".join(n for n, _ in members) + ".", [it["title"] for _, it in members]))

    # 4 · dose ceilings
    for name, it in named:
        d = it.get("details") or {}
        mg, times = _mg(d.get("dose")), _times(d)
        if mg and (_generic(name) in PARACETAMOL):
            daily = mg * times
            if daily > 4000:
                out.append(Finding("BLOCK", f"DOSE:paracetamol:{_generic(name)}", "Above maximum daily dose", f"{name}: {daily:.0f} mg/day exceeds the 4 g/day adult maximum.", [it["title"]]))
            elif daily > 3000 and "liver" in (comorbidities or "").lower():
                out.append(Finding("WARN", "DOSE:paracetamol:liver", "High paracetamol dose with liver disease", f"{name}: {daily:.0f} mg/day in a patient with liver disease — consider ≤2–3 g/day.", [it["title"]]))

    # 5 · comorbidities
    co = (comorbidities or "").lower()
    for name, it in named:
        cl = _drug_classes(name)
        if "nsaid" in cl and re.search(r"kidney|renal|ckd|ulcer|gastric|gerd|bleed", co):
            out.append(Finding("WARN", f"CO:nsaid:{_generic(name)}", "NSAID with renal/GI history", f"{name}: NSAIDs are best avoided with kidney disease, ulcers or GI bleeding.", [it["title"]]))
        if _generic(name) == "metformin" and re.search(r"kidney|renal|ckd", co):
            out.append(Finding("WARN", "CO:metformin:renal", "Metformin with renal impairment", "Check eGFR before prescribing metformin.", [it["title"]]))
        if "beta_blocker" in cl and re.search(r"asthma|copd", co):
            out.append(Finding("WARN", f"CO:bb:{_generic(name)}", "Beta-blocker with airway disease", f"{name}: beta-blockers can trigger bronchospasm in asthma/COPD.", [it["title"]]))
    return out


def unresolved_blocks(findings: list[dict[str, Any]], overrides: dict[str, str] | None) -> list[dict[str, Any]]:
    ov = {k: v for k, v in (overrides or {}).items() if v and len(v.strip()) >= 5}
    return [f for f in findings if f["severity"] == "BLOCK" and f["code"] not in ov]
