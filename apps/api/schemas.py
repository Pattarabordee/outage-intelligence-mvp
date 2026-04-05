from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class IncidentCreate(BaseModel):
    client_name: str = Field(..., examples=["DemoOperator"])
    site_id: str = Field(..., examples=["SITE-1001"])
    province: str = Field(..., examples=["North Zone"])
    scada_status: Literal["OUTAGE_CONFIRMED", "POWER_NORMAL", "UNKNOWN"] = "OUTAGE_CONFIRMED"


class FieldSignalIn(BaseModel):
    channel: Literal["FIELD_APP", "VOICE_SUMMARY", "SCADA_NOTE"] = "FIELD_APP"
    raw_text: str


class RestoreIn(BaseModel):
    restored_by: Literal["SCADA_SENSOR", "CLIENT_CALLBACK", "DISPATCHER"] = "SCADA_SENSOR"


class IncidentOut(BaseModel):
    id: str
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
    created_at: datetime


class ImmediateResponse(BaseModel):
    incident: IncidentOut
    recommendation: str
    message: str


class IncidentWithSignals(BaseModel):
    incident: IncidentOut
    signals: list[SignalOut]
