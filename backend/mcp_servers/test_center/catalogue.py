"""Test catalogue, reference ranges and deterministic flagging (port of lib/services/testCenter.ts)."""
from __future__ import annotations

from typing import Any

TEST_CATALOGUE: list[dict[str, Any]] = [
    {
        "code": "CBC",
        "name": "Complete Blood Count",
        "aliases": ["cbc", "complete blood count", "blood count", "hemogram", "haemogram"],
        "params": [
            {"key": "hb", "label": "Hemoglobin", "unit": "g/dL", "low": 12, "high": 17, "criticalLow": 7},
            {"key": "wbc", "label": "WBC count", "unit": "×10³/µL", "low": 4, "high": 11, "criticalHigh": 20},
            {"key": "platelets", "label": "Platelets", "unit": "×10³/µL", "low": 150, "high": 450, "criticalLow": 50},
            {"key": "neutrophils", "label": "Neutrophils", "unit": "%", "low": 40, "high": 75},
        ],
    },
    {"code": "CRP", "name": "C-Reactive Protein", "aliases": ["crp", "c-reactive", "c reactive"], "params": [{"key": "crp", "label": "CRP", "unit": "mg/L", "high": 10, "criticalHigh": 100}]},
    {"code": "ESR", "name": "Erythrocyte Sedimentation Rate", "aliases": ["esr", "sedimentation"], "params": [{"key": "esr", "label": "ESR", "unit": "mm/hr", "high": 20}]},
    {
        "code": "RFT",
        "name": "Renal Function Test",
        "aliases": ["rft", "kft", "renal function", "kidney function", "creatinine", "urea"],
        "params": [
            {"key": "creatinine", "label": "Creatinine", "unit": "mg/dL", "low": 0.6, "high": 1.3, "criticalHigh": 4},
            {"key": "urea", "label": "Blood urea", "unit": "mg/dL", "low": 15, "high": 45},
            {"key": "potassium", "label": "Potassium", "unit": "mmol/L", "low": 3.5, "high": 5.1, "criticalLow": 2.8, "criticalHigh": 6.2},
            {"key": "sodium", "label": "Sodium", "unit": "mmol/L", "low": 135, "high": 145, "criticalLow": 125, "criticalHigh": 155},
        ],
    },
    {
        "code": "LFT",
        "name": "Liver Function Test",
        "aliases": ["lft", "liver function"],
        "params": [
            {"key": "alt", "label": "ALT (SGPT)", "unit": "U/L", "high": 45},
            {"key": "ast", "label": "AST (SGOT)", "unit": "U/L", "high": 40},
            {"key": "bilirubin", "label": "Total bilirubin", "unit": "mg/dL", "high": 1.2},
        ],
    },
    {
        "code": "LIPID",
        "name": "Lipid Profile",
        "aliases": ["lipid", "cholesterol"],
        "prep": "Fast for 10–12 hours before the test (water is allowed).",
        "params": [
            {"key": "ldl", "label": "LDL cholesterol", "unit": "mg/dL", "high": 100},
            {"key": "hdl", "label": "HDL cholesterol", "unit": "mg/dL", "low": 40},
            {"key": "tg", "label": "Triglycerides", "unit": "mg/dL", "high": 150},
        ],
    },
    {"code": "HBA1C", "name": "HbA1c", "aliases": ["hba1c", "a1c", "glycated"], "params": [{"key": "hba1c", "label": "HbA1c", "unit": "%", "high": 6.5}]},
    {
        "code": "FBS",
        "name": "Fasting Blood Sugar",
        "aliases": ["fbs", "fasting sugar", "fasting glucose", "blood sugar", "glucose"],
        "prep": "Fast for 8 hours before the test.",
        "params": [{"key": "glucose", "label": "Fasting glucose", "unit": "mg/dL", "low": 70, "high": 100, "criticalLow": 50, "criticalHigh": 400}],
    },
    {"code": "INR", "name": "PT / INR", "aliases": ["inr", "pt/inr", "prothrombin", "coagulation"], "params": [{"key": "inr", "label": "INR", "unit": "", "low": 0.8, "high": 1.2, "criticalHigh": 4.5}]},
    {"code": "TROP", "name": "Troponin I", "aliases": ["troponin"], "params": [{"key": "trop", "label": "Troponin I", "unit": "ng/mL", "high": 0.04, "criticalHigh": 0.4}]},
    {"code": "XRAY", "name": "X-Ray", "aliases": ["x-ray", "xray", "radiograph"], "params": []},
    {"code": "ECG", "name": "Electrocardiogram", "aliases": ["ecg", "ekg", "electrocardiogram"], "params": [{"key": "hr", "label": "Heart rate", "unit": "bpm", "low": 60, "high": 100}]},
]


def resolve_test(name: str) -> dict[str, Any]:
    s = name.lower()
    for t in TEST_CATALOGUE:
        if any(a in s for a in t["aliases"]):
            return t
    return {"code": "CUSTOM", "name": name.strip(), "aliases": [], "params": []}


def _num(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else str(v)


def flag_values(panel: dict[str, Any], values: dict[str, float]) -> list[dict[str, Any]]:
    out = []
    for p in panel["params"]:
        v = values.get(p["key"])
        if not isinstance(v, (int, float)) or v != v:  # noqa: PLR0124 (NaN check)
            continue
        flag = "NORMAL"
        if p.get("criticalLow") is not None and v < p["criticalLow"]:
            flag = "CRITICAL_LOW"
        elif p.get("criticalHigh") is not None and v > p["criticalHigh"]:
            flag = "CRITICAL_HIGH"
        elif p.get("low") is not None and v < p["low"]:
            flag = "LOW"
        elif p.get("high") is not None and v > p["high"]:
            flag = "HIGH"
        lo, hi = p.get("low"), p.get("high")
        rng = f"{_num(lo)}–{_num(hi)}" if lo is not None and hi is not None else f"< {_num(hi)}" if hi is not None else f"> {_num(lo)}" if lo is not None else "—"
        out.append({"key": p["key"], "label": p["label"], "value": v, "unit": p["unit"], "flag": flag, "range": rng})
    return out
