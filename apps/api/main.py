from __future__ import annotations

import html as html_escape
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Mapping

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse

from .config import settings
from .exceptions import StateConflictError
from .schemas import (
    FieldSignalIn,
    ImmediateResponse,
    IncidentCreate,
    IncidentOut,
    IncidentWithSignals,
    RestoreIn,
    WebhookDeliveryOut,
)
from .security import PartnerContext, assert_partner_access, effective_partner_id, resolve_partner_context
from .services import IncidentService


def create_app(
    db_path: str | Path | None = None,
    sandbox_api_keys: Mapping[str, str] | None = None,
    webhook_secret: str | None = None,
    webhook_max_attempts: int | None = None,
) -> FastAPI:
    service = IncidentService(
        db_path=db_path,
        webhook_secret=webhook_secret,
        webhook_max_attempts=webhook_max_attempts,
    )
    configured_api_keys = dict(settings.sandbox_api_keys if sandbox_api_keys is None else sandbox_api_keys)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield

    app = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
        summary="Public-safe enterprise outage intelligence API for partner pilot readiness",
        lifespan=lifespan,
    )
    app.state.service = service
    app.state.sandbox_api_keys = configured_api_keys

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException):
        code = "http_error"
        if exc.status_code == 404:
            code = "not_found"
        elif exc.status_code == 409:
            code = "state_conflict"
        elif exc.status_code == 401:
            code = "unauthorized"
        elif exc.status_code == 403:
            code = "forbidden"
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": code, "message": str(exc.detail), "details": []}},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed",
                    "details": exc.errors(),
                }
            },
        )

    @app.get("/health")
    def health() -> dict:
        return {
            "status": "ok",
            "service": "enterprise-outage-intelligence",
            "version": settings.api_version,
            "data_boundary": "synthetic-public-safe",
            "sandbox_auth": "enabled" if app.state.sandbox_api_keys else "disabled",
        }

    @app.get("/ready")
    def ready() -> dict:
        return {
            "status": "ready",
            "checks": {
                "incident_store": "ok",
                "sandbox_auth_configured": bool(app.state.sandbox_api_keys),
                "data_boundary": "synthetic-public-safe",
            },
        }

    def partner_context(
        x_partner_id: str | None = Header(default=None, alias="X-Partner-Id"),
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    ) -> PartnerContext:
        return resolve_partner_context(app.state.sandbox_api_keys, x_partner_id, x_api_key)

    def incident_payload(incident: dict) -> dict:
        return {
            "incident": incident,
            "signals": app.state.service.list_signals(incident["id"]),
            "events": app.state.service.list_events(incident["id"]),
            "decision": app.state.service.decision_for_incident(incident),
        }

    def assert_webhook_delivery_access(context: PartnerContext, delivery: dict) -> None:
        if context.partner_id and delivery["partner_id"] != context.partner_id:
            raise HTTPException(status_code=403, detail="Partner cannot access this webhook delivery")

    @app.post("/api/v1/incidents", response_model=ImmediateResponse, status_code=201)
    def create_incident(
        payload: IncidentCreate,
        response: Response,
        context: PartnerContext = Depends(partner_context),
    ):
        partner_id = effective_partner_id(context, payload.partner_id)
        incident, created = app.state.service.create_incident(
            partner_id=partner_id,
            client_name=payload.client_name,
            site_id=payload.site_id,
            province=payload.province,
            scada_status=payload.scada_status,
            source_event_id=payload.source_event_id,
            idempotency_key=payload.idempotency_key,
        )
        if created:
            response.headers["Location"] = f"/api/v1/incidents/{incident['id']}"
        else:
            response.status_code = 200
        return {
            "incident": incident,
            "recommendation": incident["dispatch_decision"],
            "decision": app.state.service.decision_for_incident(incident),
            "message": f"Initial hold ETA is {incident['current_eta_hours']} hours.",
        }

    @app.get("/api/v1/incidents/{incident_id}", response_model=IncidentWithSignals)
    def get_incident(incident_id: str, context: PartnerContext = Depends(partner_context)):
        try:
            incident = app.state.service.get_incident(incident_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        assert_partner_access(context, incident)
        return incident_payload(incident)

    @app.post("/api/v1/incidents/{incident_id}/signals/field", response_model=IncidentWithSignals)
    def add_field_signal(
        incident_id: str,
        payload: FieldSignalIn,
        context: PartnerContext = Depends(partner_context),
    ):
        try:
            incident = app.state.service.get_incident(incident_id)
            assert_partner_access(context, incident)
            incident, _signal = app.state.service.add_field_signal(
                incident_id=incident_id,
                channel=payload.channel,
                raw_text=payload.raw_text,
                observed_at=payload.observed_at,
                source_signal_id=payload.source_signal_id,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except StateConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return incident_payload(incident)

    @app.post("/api/v1/incidents/{incident_id}/timeout-check", response_model=IncidentOut)
    def apply_timeout(incident_id: str, context: PartnerContext = Depends(partner_context)):
        try:
            incident = app.state.service.get_incident(incident_id)
            assert_partner_access(context, incident)
            return app.state.service.apply_timeout_if_needed(incident_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/v1/incidents/{incident_id}/restore", response_model=IncidentOut)
    def restore_incident(
        incident_id: str,
        payload: RestoreIn,
        context: PartnerContext = Depends(partner_context),
    ):
        try:
            incident = app.state.service.get_incident(incident_id)
            assert_partner_access(context, incident)
            return app.state.service.restore_incident(incident_id, restored_by=payload.restored_by)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/webhook-deliveries", response_model=list[WebhookDeliveryOut])
    def list_webhook_deliveries(context: PartnerContext = Depends(partner_context)):
        return app.state.service.list_webhook_deliveries(partner_id=context.partner_id)

    @app.get("/api/v1/webhook-deliveries/{event_id}", response_model=WebhookDeliveryOut)
    def get_webhook_delivery(event_id: str, context: PartnerContext = Depends(partner_context)):
        try:
            delivery = app.state.service.get_webhook_delivery(event_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        assert_webhook_delivery_access(context, delivery)
        return delivery

    @app.post("/api/v1/webhook-deliveries/{event_id}/retry", response_model=WebhookDeliveryOut)
    def retry_webhook_delivery(event_id: str, context: PartnerContext = Depends(partner_context)):
        try:
            delivery = app.state.service.get_webhook_delivery(event_id)
            assert_webhook_delivery_access(context, delivery)
            return app.state.service.retry_webhook_delivery(event_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/demo/incidents", response_class=HTMLResponse)
    def demo_incidents():
        incidents = app.state.service.list_incidents()
        rows = []
        timeline_items = []
        for inc in incidents:
            decision = app.state.service.decision_for_incident(inc)
            rows.append(
                f"<tr><td>{html_escape.escape(inc['id'])}</td><td>{html_escape.escape(inc['partner_id'])}</td>"
                f"<td>{html_escape.escape(inc['site_id'])}</td><td>{html_escape.escape(inc['province'])}</td>"
                f"<td>{html_escape.escape(inc['status'])}</td><td>{html_escape.escape(inc['severity'])}</td>"
                f"<td>{inc['current_eta_hours']}</td><td>{html_escape.escape(decision['partner_action'])}</td></tr>"
            )
            for event in app.state.service.list_events(inc["id"]):
                timeline_items.append(
                    f"<li><strong>{html_escape.escape(event['event_type'])}</strong> "
                    f"<span class='small'>{html_escape.escape(inc['site_id'])} | "
                    f"{html_escape.escape(event['reason_code'])} | "
                    f"ETA {event['new_eta_hours']}h</span></li>"
                )
        html = f"""
        <html>
        <head>
          <title>Outage Intelligence Demo</title>
          <style>
            body {{ font-family: Arial, sans-serif; margin: 24px; color: #172033; background: #f7f9fc; }}
            .hero {{ background: #12355b; color: white; padding: 24px; border-radius: 16px; }}
            .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 20px 0; }}
            .card {{ background: white; border: 1px solid #d9e2ef; border-radius: 12px; padding: 14px; }}
            .card strong {{ display: block; margin-bottom: 6px; color: #12355b; }}
            .timeline {{ background: white; border: 1px solid #d9e2ef; border-radius: 12px; padding: 18px; }}
            .timeline li {{ margin: 8px 0; }}
            table {{ border-collapse: collapse; width: 100%; background: white; }}
            td, th {{ border: 1px solid #d9e2ef; padding: 8px; }}
            th {{ text-align: left; background: #eaf1fb; }}
            .small {{ color: #526070; }}
          </style>
        </head>
        <body>
          <section class="hero">
            <h1>Enterprise Outage Intelligence</h1>
            <p>Public-safe product prototype for utility-to-enterprise coordination across outage ETA, partner action, audit trail, and ML-ready ground truth.</p>
          </section>
          <section class="cards">
            <div class="card"><strong>1. Incident opened</strong><span class="small">Enterprise partner sends a synthetic outage event.</span></div>
            <div class="card"><strong>2. ETA returned</strong><span class="small">Decision policy returns an immediate partner recommendation.</span></div>
            <div class="card"><strong>3. Evidence revises ETA</strong><span class="small">Field signals update confidence, reason code, and action.</span></div>
            <div class="card"><strong>4. Ground truth captured</strong><span class="small">Restoration closes the loop for analytics and ML baselines.</span></div>
          </section>
          <section class="timeline">
            <h2>Pilot Timeline</h2>
            <ol>{''.join(timeline_items) or '<li>No incident events yet. Run the seed script to populate a synthetic partner journey.</li>'}</ol>
          </section>
          <h2>Incident Portfolio</h2>
          <table>
            <thead>
              <tr>
                <th>ID</th><th>Partner</th><th>Site</th><th>Province</th><th>Status</th><th>Severity</th><th>ETA Hours</th><th>Partner Action</th>
              </tr>
            </thead>
            <tbody>{''.join(rows)}</tbody>
          </table>
        </body>
        </html>
        """
        return HTMLResponse(content=html)

    return app


app = create_app()
