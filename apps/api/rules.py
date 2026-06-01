from __future__ import annotations

import re
from dataclasses import dataclass


KEYWORD_TO_SEVERITY = {
    "pole down": ("critical", 7.0, "STRUCTURAL_DAMAGE"),
    "conductor snapped": ("critical", 7.0, "BROKEN_CONDUCTOR"),
    "tree on line": ("high", 6.0, "VEGETATION_CONTACT"),
    "insulator flashover": ("high", 5.0, "INSULATOR_FAULT"),
    "transformer trip": ("medium", 4.0, "PROTECTION_OPERATION"),
    "breaker trip": ("medium", 3.5, "PROTECTION_OPERATION"),
    "patrol underway": ("low", 3.0, "PATROL_UNDERWAY"),
    "searching fault": ("low", 3.0, "FAULT_NOT_LOCATED"),
    "power restored": ("resolved", 0.0, "RESTORED"),
}

FALLBACK_ETA_BY_SCADA = {
    "OUTAGE_CONFIRMED": 2.0,
    "UNKNOWN": 2.5,
    "POWER_NORMAL": 0.5,
}

TIMEOUT_WORST_CASE_HOURS = 8.0
TIMEOUT_MINUTES = 120
POLICY_VERSION = "rules-v1"


@dataclass
class RuleResult:
    normalized_text: str
    severity: str
    predicted_eta_hours: float
    extracted_keywords: list[str]
    reason_code: str


def normalize_text(text: str) -> str:
    normalized = text.strip().lower()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def evaluate_text_signal(text: str) -> RuleResult:
    normalized = normalize_text(text)
    hits: list[tuple[str, tuple[str, float, str]]] = []
    for keyword, result in KEYWORD_TO_SEVERITY.items():
        if keyword in normalized:
            hits.append((keyword, result))

    if not hits:
        return RuleResult(
            normalized_text=normalized,
            severity="unknown",
            predicted_eta_hours=4.0,
            extracted_keywords=[],
            reason_code="UNCLASSIFIED_FIELD_SIGNAL",
        )

    best_keyword, best = sorted(
        hits,
        key=lambda item: item[1][1],
        reverse=True,
    )[0]
    severity, eta_hours, reason_code = best
    return RuleResult(
        normalized_text=normalized,
        severity=severity,
        predicted_eta_hours=eta_hours,
        extracted_keywords=[keyword for keyword, _ in hits],
        reason_code=reason_code,
    )


def initial_eta_from_scada(scada_status: str) -> float:
    return FALLBACK_ETA_BY_SCADA.get(scada_status, 2.5)


def recommendation_from_eta(eta_hours: float) -> str:
    if eta_hours <= 2:
        return "HOLD_BACKUP_DISPATCH"
    if eta_hours <= 5:
        return "MONITOR_AND_PREPARE"
    return "DISPATCH_BACKUP_IF_BATTERY_WINDOW_AT_RISK"


def partner_action_from_recommendation(recommendation: str) -> str:
    actions = {
        "HOLD_BACKUP_DISPATCH": "Wait for the next utility update before activating backup operations.",
        "MONITOR_AND_PREPARE": "Prepare backup resources while monitoring revised field evidence.",
        "DISPATCH_BACKUP_IF_BATTERY_WINDOW_AT_RISK": "Activate backup operations if the site battery window is at risk.",
        "CLOSE_TICKET_AND_LOG_GROUND_TRUTH": "Close the partner incident and retain restoration ground truth.",
    }
    return actions.get(recommendation, "Review the latest outage decision with operations.")


def policy_explanation(reason_code: str, eta_hours: float) -> str:
    if reason_code == "TIMEOUT_FAILSAFE":
        return f"No decisive field evidence arrived within {TIMEOUT_MINUTES} minutes, so the policy moved to a worst-case ETA."
    if reason_code == "RESTORED":
        return "A restoration signal closed the incident and converted the case into ground truth for analytics."
    if eta_hours <= 2:
        return "The current evidence indicates a short restoration window, so partner backup dispatch can remain on hold."
    if eta_hours <= 5:
        return "The current evidence indicates moderate uncertainty, so partner operations should prepare backup options."
    return "The current evidence indicates a prolonged outage risk, so backup activation should be considered."


def confidence_band(severity: str) -> str:
    if severity in {"critical", "high", "resolved", "timeout_worst_case"}:
        return "high"
    if severity in {"medium", "low", "baseline"}:
        return "medium"
    return "low"
