from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class IncidentCreate(BaseModel):
    partner_id: str | None = Field(default=None, examples=["partner-telecom-sandbox"])
    client_name: str = Field(..., examples=["DemoEnterprisePartner"])
    site_id: str = Field(..., examples=["SITE-1001"])
    province: str = Field(..., examples=["North Zone"])
    scada_status: Literal["OUTAGE_CONFIRMED", "POWER_NORMAL", "UNKNOWN"] = "OUTAGE_CONFIRMED"
    source_event_id: str | None = Field(default=None, examples=["SRC-EVENT-1001"])
    idempotency_key: str | None = Field(default=None, examples=["client-event-1001"])


class FieldSignalIn(BaseModel):
    channel: Literal["FIELD_APP", "VOICE_SUMMARY", "SCADA_NOTE"] = "FIELD_APP"
    raw_text: str = Field(..., min_length=1)
    observed_at: datetime | None = None
    source_signal_id: str | None = Field(default=None, examples=["SRC-SIGNAL-1001"])


class RestoreIn(BaseModel):
    restored_by: Literal["SCADA_SENSOR", "CLIENT_CALLBACK", "DISPATCHER"] = "SCADA_SENSOR"


class PartnerProfileIn(BaseModel):
    display_name: str = Field(..., min_length=1, examples=["Telecom Sandbox Partner"])
    partner_class: Literal[
        "telecom",
        "data_center",
        "industrial_estate",
        "hospital_network",
        "critical_infrastructure",
        "enterprise_sandbox",
    ] = "enterprise_sandbox"
    allowed_site_prefixes: list[str] = Field(default_factory=lambda: ["SITE-"])
    webhook_mode: Literal["outbox_only", "mock_dispatch"] = "outbox_only"
    notification_contact_label: str | None = Field(default=None, examples=["Partner NOC sandbox queue"])


class PartnerProfileOut(PartnerProfileIn):
    partner_id: str
    created_at: datetime
    updated_at: datetime


class WebhookAttemptIn(BaseModel):
    outcome: Literal["delivered", "failed"]
    response_status: int | None = Field(default=None, ge=100, le=599)
    error_message: str | None = Field(default=None, max_length=240)


class IncidentOut(BaseModel):
    id: str
    partner_id: str
    client_name: str
    site_id: str
    province: str
    scada_status: str
    status: str
    created_at: datetime
    updated_at: datetime
    initial_eta_hours: float
    current_eta_hours: float
    severity: str
    reason_code: str
    hold_until: datetime
    restored_at: datetime | None = None
    restored_by: str | None = None
    dispatch_decision: str
    timeout_applied: bool
    last_signal_at: datetime | None = None
    source_event_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SignalOut(BaseModel):
    id: int
    incident_id: str
    channel: str
    raw_text: str
    normalized_text: str
    severity: str
    predicted_eta_hours: float
    extracted_keywords: list[str]
    observed_at: datetime | None = None
    source_signal_id: str | None = None
    created_at: datetime


class IncidentEventOut(BaseModel):
    id: int
    incident_id: str
    event_type: str
    source: str
    previous_eta_hours: float | None = None
    new_eta_hours: float | None = None
    reason_code: str
    policy_version: str
    confidence_band: str
    feature_snapshot: dict[str, Any] = Field(default_factory=dict)
    observed_at: datetime | None = None
    created_at: datetime


class DecisionOut(BaseModel):
    eta_hours: float
    recommendation: str
    partner_action: str
    confidence_band: str
    reason_code: str
    policy_version: str
    prediction_time: datetime
    policy_explanation: str
    sla_behavior: dict[str, Any] = Field(default_factory=dict)


class ImmediateResponse(BaseModel):
    incident: IncidentOut
    recommendation: str
    decision: DecisionOut
    message: str


class IncidentWithSignals(BaseModel):
    incident: IncidentOut
    signals: list[SignalOut]
    events: list[IncidentEventOut] = Field(default_factory=list)
    decision: DecisionOut


class WebhookDeliveryOut(BaseModel):
    event_id: str
    partner_id: str
    incident_id: str
    event_type: str
    payload: dict[str, Any]
    headers: dict[str, str]
    status: str
    attempt_count: int
    max_attempts: int
    next_attempt_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class WebhookDeliveryAttemptOut(BaseModel):
    id: int
    event_id: str
    attempt_number: int
    outcome: str
    response_status: int | None = None
    error_message: str | None = None
    created_at: datetime


class WebhookAttemptResultOut(BaseModel):
    delivery: WebhookDeliveryOut
    attempt: WebhookDeliveryAttemptOut


class ErrorDetail(BaseModel):
    field: str | None = None
    message: str
    code: str


class ErrorResponse(BaseModel):
    error: dict[str, Any]
