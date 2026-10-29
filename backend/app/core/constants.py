"""Domain vocabularies (SQLite has no enums; values are strings exactly as in the legacy app)."""
from __future__ import annotations

ROLES = ("DOCTOR", "NURSE", "PATIENT", "TEST_CENTER", "PROVIDER", "ADMIN", "CAREGIVER")

# PROVIDER (external care partner) and TEST_CENTER share the /provider dashboard area
ROLE_HOME = {"CAREGIVER": "/caregiver", "ADMIN": "/admin", "DOCTOR": "/doctor", "NURSE": "/nurse", "PATIENT": "/patient", "TEST_CENTER": "/provider", "PROVIDER": "/provider"}

ITEM_CATEGORIES = (
    "MEDICATION",
    "INVESTIGATION",
    "FOLLOW_UP",
    "REFERRAL",
    "MONITORING",
    "DIET",
    "EXERCISE",
    "RESTRICTION",
    "CARE_INSTRUCTION",
    "RED_FLAG",
)

CATEGORY_LABEL = {
    "MEDICATION": "Medication",
    "INVESTIGATION": "Investigation",
    "FOLLOW_UP": "Follow-up",
    "REFERRAL": "Referral / Rehabilitation",
    "MONITORING": "Monitoring",
    "DIET": "Diet",
    "EXERCISE": "Exercise",
    "RESTRICTION": "Restriction",
    "CARE_INSTRUCTION": "Care Instruction",
    "RED_FLAG": "Red Flag",
}

AGENT_KEYS = ("PLANNING", "EXECUTION", "MONITORING", "COMMUNICATION", "INTELLIGENCE", "SERVICE", "HUMAN")

METRICS = {
    "TEMPERATURE": ("Temperature", "°F"),
    "SYSTOLIC_BP": ("Systolic BP", "mmHg"),
    "DIASTOLIC_BP": ("Diastolic BP", "mmHg"),
    "HEART_RATE": ("Heart rate", "bpm"),
    "SPO2": ("SpO₂", "%"),
    "PAIN": ("Pain score", "/10"),
    "BLOOD_GLUCOSE": ("Blood glucose", "mg/dL"),
    "WEIGHT": ("Weight", "kg"),
    "WEIGHT_GAIN": ("Weight gain (72 h)", "kg"),
    "SYMPTOM": ("Symptom", ""),
    "MISSED_DOSES": ("Missed doses", ""),
    "MISSED_APPOINTMENT": ("Missed appointment", ""),
    "LAB_ABNORMAL": ("Abnormal lab value", ""),
}

OBSERVATION_UNITS = {"TEMPERATURE": "°F", "BP": "mmHg", "HEART_RATE": "bpm", "SPO2": "%", "PAIN": "/10", "BLOOD_GLUCOSE": "mg/dL", "WEIGHT": "kg"}
