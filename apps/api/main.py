from __future__ import annotations

import html as html_escape
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Mapping

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse

from .config import settings
from .exceptions import AccessDeniedError, StateConflictError
from .schemas import (
    ExecutiveSummaryOut,
    FieldSignalIn,
    ImmediateResponse,
    IncidentCreate,
    IncidentOut,
    IncidentWithSignals,
    PartnerProfileIn,
    PartnerProfileOut,
    RestoreIn,
    WebhookAttemptIn,
    WebhookAttemptResultOut,
    WebhookDeliveryAttemptOut,
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
                "partner_profile_store": "ok",
                "webhook_outbox": "ok",
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

    def assert_partner_profile_access(context: PartnerContext, partner_id: str) -> None:
        if context.partner_id and context.partner_id != partner_id:
            raise HTTPException(status_code=403, detail="Partner cannot access this sandbox profile")

    @app.get("/api/v1/partners/{partner_id}/sandbox-profile", response_model=PartnerProfileOut)
    def get_partner_profile(partner_id: str, context: PartnerContext = Depends(partner_context)):
        assert_partner_profile_access(context, partner_id)
        return app.state.service.ensure_partner_profile(partner_id)

    @app.put("/api/v1/partners/{partner_id}/sandbox-profile", response_model=PartnerProfileOut)
    def upsert_partner_profile(
        partner_id: str,
        payload: PartnerProfileIn,
        context: PartnerContext = Depends(partner_context),
    ):
        assert_partner_profile_access(context, partner_id)
        return app.state.service.upsert_partner_profile(
            partner_id=partner_id,
            display_name=payload.display_name,
            partner_class=payload.partner_class,
            allowed_site_prefixes=payload.allowed_site_prefixes,
            webhook_mode=payload.webhook_mode,
            notification_contact_label=payload.notification_contact_label,
        )

    @app.post("/api/v1/incidents", response_model=ImmediateResponse, status_code=201)
    def create_incident(
        payload: IncidentCreate,
        response: Response,
        context: PartnerContext = Depends(partner_context),
    ):
        partner_id = effective_partner_id(context, payload.partner_id)
        try:
            incident, created = app.state.service.create_incident(
                partner_id=partner_id,
                client_name=payload.client_name,
                site_id=payload.site_id,
                province=payload.province,
                scada_status=payload.scada_status,
                source_event_id=payload.source_event_id,
                idempotency_key=payload.idempotency_key,
            )
        except AccessDeniedError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
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
        except StateConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/v1/webhook-deliveries/{event_id}/attempts", response_model=list[WebhookDeliveryAttemptOut])
    def list_webhook_attempts(event_id: str, context: PartnerContext = Depends(partner_context)):
        try:
            delivery = app.state.service.get_webhook_delivery(event_id)
            assert_webhook_delivery_access(context, delivery)
            return app.state.service.list_webhook_attempts(event_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post(
        "/api/v1/webhook-deliveries/{event_id}/attempts",
        response_model=WebhookAttemptResultOut,
        status_code=201,
    )
    def record_webhook_attempt(
        event_id: str,
        payload: WebhookAttemptIn,
        context: PartnerContext = Depends(partner_context),
    ):
        try:
            delivery = app.state.service.get_webhook_delivery(event_id)
            assert_webhook_delivery_access(context, delivery)
            return app.state.service.record_webhook_attempt(
                event_id=event_id,
                outcome=payload.outcome,
                response_status=payload.response_status,
                error_message=payload.error_message,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except StateConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/v1/demo/executive-summary", response_model=ExecutiveSummaryOut)
    def executive_summary():
        return app.state.service.executive_summary()

    @app.get("/demo/incidents", response_class=HTMLResponse)
    def demo_incidents():
        summary = app.state.service.executive_summary()

        def esc(value) -> str:
            return html_escape.escape(str(value))

        def percent(value: float) -> str:
            return f"{round(value * 100)}%"

        metrics = summary["metrics"]
        ml_readiness = summary["ml_readiness"]
        metric_cards = "".join(
            [
                f"<article class='metric'><span>{label}</span><strong>{esc(value)}</strong><em>{esc(note)}</em></article>"
                for label, value, note in [
                    ("Partner profiles", metrics["partner_profiles"], "sandbox tenants"),
                    ("Incidents", metrics["total_incidents"], "synthetic cases"),
                    ("Closed loop rows", ml_readiness["closed_dataset_rows"], "ML-ready outcomes"),
                    ("Webhook events", metrics["webhook_deliveries"], "outbox records"),
                    ("Audit completeness", percent(metrics["audit_completeness_rate"]), "events captured"),
                    ("Ground truth coverage", percent(ml_readiness["restoration_ground_truth_coverage"]), "restored cases"),
                ]
            ]
        )
        journey_items = "".join(
            [
                "<li>"
                f"<span class='timeline-dot' aria-hidden='true'></span>"
                f"<div><strong>{esc(item['stage'])}</strong>"
                f"<p>{esc(item['site_id'])} | {esc(item['reason_code'])} | ETA {esc(item['eta_hours'])}h</p>"
                f"<small>{esc(item['partner_id'])} | {esc(item['status'])}</small></div>"
                "</li>"
                for item in summary["partner_journey"]
            ]
        )
        if not journey_items:
            journey_items = "<li><span class='timeline-dot' aria-hidden='true'></span><div><strong>No journey yet</strong><p>Run the seed script to populate a synthetic partner pilot story.</p></div></li>"

        decision_cards = "".join(
            [
                "<article class='panel-card'>"
                f"<span class='eyebrow'>{esc(item['site_id'])} | {esc(item['confidence_band'])} confidence</span>"
                f"<h3>{esc(item['reason_code'])}</h3>"
                f"<p>{esc(item['partner_action'])}</p>"
                f"<small>{esc(item['policy_explanation'])}</small>"
                "</article>"
                for item in summary["decision_rationale"]
            ]
        )
        if not decision_cards:
            decision_cards = "<article class='panel-card'><h3>No decisions yet</h3><p>Create a synthetic incident to show policy rationale.</p></article>"

        webhook_rows = "".join(
            [
                "<tr>"
                f"<td>{esc(event['event_type'])}</td>"
                f"<td>{esc(event['partner_id'])}</td>"
                f"<td><span class='status'>{esc(event['status'])}</span></td>"
                f"<td>{esc(event['attempt_count'])}/{esc(event['max_attempts'])}</td>"
                "</tr>"
                for event in summary["webhook_delivery"]["recent_events"]
            ]
        )
        if not webhook_rows:
            webhook_rows = "<tr><td colspan='4'>No webhook delivery records yet.</td></tr>"

        export_shape = "".join(f"<li>{esc(field)}</li>" for field in ml_readiness["export_shape"])
        safe_controls = "".join(f"<li>{esc(control)}</li>" for control in summary["public_safe_controls"])
        html = f"""
        <!doctype html>
        <html lang="en">
        <head>
          <meta charset="utf-8" />
          <meta name="viewport" content="width=device-width, initial-scale=1" />
          <title>Executive Partner Demo | Outage Intelligence</title>
          <style>
            :root {{
              --ink: #102033;
              --muted: #536172;
              --paper: #fbf7ef;
              --surface: #ffffff;
              --line: #d8cbb9;
              --navy: #0f2f4a;
              --teal: #0f766e;
              --amber: #b45309;
              --mint: #d9f4ec;
              --focus: #f59e0b;
            }}
            * {{ box-sizing: border-box; }}
            body {{
              margin: 0;
              color: var(--ink);
              background:
                radial-gradient(circle at top left, rgba(15, 118, 110, 0.18), transparent 32rem),
                linear-gradient(135deg, #fbf7ef 0%, #edf6f4 52%, #f8fbff 100%);
              font-family: "Aptos Display", "Bahnschrift", "Trebuchet MS", sans-serif;
              line-height: 1.55;
            }}
            .skip {{
              position: absolute;
              left: 1rem;
              top: -4rem;
              background: var(--navy);
              color: white;
              padding: 0.75rem 1rem;
              border-radius: 999px;
            }}
            .skip:focus {{ top: 1rem; outline: 3px solid var(--focus); }}
            main {{ max-width: 1180px; margin: 0 auto; padding: 32px 20px 56px; }}
            .hero {{
              display: grid;
              gap: 24px;
              grid-template-columns: minmax(0, 1.5fr) minmax(260px, 0.8fr);
              padding: 34px;
              border-radius: 28px;
              color: white;
              background: linear-gradient(135deg, #0f2f4a 0%, #155e63 62%, #9a5b13 100%);
              box-shadow: 0 24px 60px rgba(16, 32, 51, 0.18);
            }}
            h1, h2, h3, p {{ margin-top: 0; }}
            h1 {{ font-size: clamp(2.25rem, 5vw, 4.8rem); line-height: 0.95; letter-spacing: -0.06em; margin-bottom: 18px; }}
            h2 {{ font-size: clamp(1.45rem, 3vw, 2rem); letter-spacing: -0.03em; }}
            .hero p {{ font-size: 1.1rem; max-width: 66ch; color: #eef8f5; }}
            .badge {{
              display: inline-flex;
              min-height: 32px;
              align-items: center;
              gap: 8px;
              border: 1px solid rgba(255, 255, 255, 0.35);
              border-radius: 999px;
              padding: 6px 12px;
              background: rgba(255, 255, 255, 0.12);
              font-size: 0.88rem;
              font-weight: 700;
            }}
            .hero-aside {{
              border: 1px solid rgba(255, 255, 255, 0.28);
              border-radius: 22px;
              padding: 22px;
              background: rgba(255, 255, 255, 0.12);
            }}
            .metrics {{
              display: grid;
              grid-template-columns: repeat(3, minmax(0, 1fr));
              gap: 14px;
              margin: 22px 0;
            }}
            .metric, .panel, .panel-card {{
              border: 1px solid var(--line);
              background: rgba(255, 255, 255, 0.88);
              border-radius: 22px;
              box-shadow: 0 12px 28px rgba(16, 32, 51, 0.08);
            }}
            .metric {{ padding: 18px; min-height: 132px; }}
            .metric span, .eyebrow {{ display: block; color: var(--muted); font-size: 0.86rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; }}
            .metric strong {{ display: block; margin: 10px 0 4px; font-size: 2rem; line-height: 1; color: var(--navy); }}
            .metric em, small {{ color: var(--muted); font-style: normal; }}
            .grid {{ display: grid; grid-template-columns: 1.1fr 0.9fr; gap: 18px; }}
            .panel {{ padding: 24px; margin-top: 18px; }}
            .timeline-list {{ list-style: none; padding: 0; margin: 0; display: grid; gap: 14px; }}
            .timeline-list li {{ display: grid; grid-template-columns: 22px 1fr; gap: 12px; align-items: start; }}
            .timeline-dot {{ width: 14px; height: 14px; border-radius: 50%; margin-top: 6px; background: var(--teal); box-shadow: 0 0 0 6px var(--mint); }}
            .panel-card {{ padding: 18px; margin-top: 12px; }}
            .panel-card h3 {{ margin: 8px 0; color: var(--navy); }}
            table {{ width: 100%; border-collapse: collapse; overflow: hidden; border-radius: 16px; }}
            th, td {{ border-bottom: 1px solid var(--line); padding: 12px; text-align: left; vertical-align: top; }}
            th {{ color: var(--navy); background: #f4eadc; font-size: 0.88rem; }}
            caption {{ text-align: left; font-weight: 800; margin-bottom: 12px; color: var(--navy); }}
            .status {{ display: inline-flex; min-height: 28px; align-items: center; border-radius: 999px; padding: 4px 10px; background: var(--mint); color: #064e3b; font-weight: 800; }}
            .ml-list, .safe-list {{ margin: 0; padding-left: 20px; }}
            .safe-list li, .ml-list li {{ margin: 7px 0; }}
            a:focus, button:focus, [tabindex]:focus {{ outline: 3px solid var(--focus); outline-offset: 3px; }}
            @media (max-width: 820px) {{
              main {{ padding: 18px 12px 40px; }}
              .hero, .grid, .metrics {{ grid-template-columns: 1fr; }}
              .hero {{ padding: 24px; border-radius: 22px; }}
              th, td {{ padding: 10px 8px; }}
            }}
          </style>
        </head>
        <body>
          <a class="skip" href="#main">Skip to main content</a>
          <main id="main">
            <section class="hero" aria-labelledby="page-title">
              <div>
                <span class="badge">Executive Partner Demo</span>
                <h1 id="page-title">Enterprise Outage Intelligence</h1>
                <p>{esc(summary['narrative'])}</p>
              </div>
              <aside class="hero-aside" aria-label="Public-safe demo boundary">
                <h2>Public-Safe Boundary</h2>
                <ul class="safe-list">{safe_controls}</ul>
              </aside>
            </section>

            <section class="panel" aria-labelledby="summary-title">
              <h2 id="summary-title">Executive Summary</h2>
              <div class="metrics">{metric_cards}</div>
            </section>

            <div class="grid">
              <section class="panel" aria-labelledby="journey-title">
                <h2 id="journey-title">Partner Journey</h2>
                <ol class="timeline-list">{journey_items}</ol>
              </section>
              <section class="panel" aria-labelledby="decision-title">
                <h2 id="decision-title">Decision Rationale</h2>
                {decision_cards}
              </section>
            </div>

            <section class="panel" aria-labelledby="webhook-title">
              <h2 id="webhook-title">Webhook Delivery</h2>
              <table>
                <caption>Sandbox outbox status without private delivery headers</caption>
                <thead><tr><th>Event</th><th>Partner</th><th>Status</th><th>Attempts</th></tr></thead>
                <tbody>{webhook_rows}</tbody>
              </table>
            </section>

            <section class="panel" aria-labelledby="ml-title">
              <h2 id="ml-title">ML Readiness</h2>
              <p>Closed incidents become measurable training rows with ETA error and policy metadata.</p>
              <ul class="ml-list">{export_shape}</ul>
            </section>
          </main>
        </body>
        </html>
        """
        return HTMLResponse(content=html)

    return app


app = create_app()
