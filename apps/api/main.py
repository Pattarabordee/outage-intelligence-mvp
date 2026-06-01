from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse

from .config import settings
from .exceptions import StateConflictError
from .schemas import FieldSignalIn, ImmediateResponse, IncidentCreate, IncidentOut, IncidentWithSignals, RestoreIn
from .services import IncidentService


def create_app(db_path: str | Path | None = None) -> FastAPI:
    service = IncidentService(db_path=db_path)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield

    app = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
        summary="Public-safe event-driven outage intelligence demo",
        lifespan=lifespan,
    )
    app.state.service = service

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException):
        code = "http_error"
        if exc.status_code == 404:
            code = "not_found"
        elif exc.status_code == 409:
            code = "state_conflict"
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
        return {"status": "ok"}

    def incident_payload(incident: dict) -> dict:
        return {
            "incident": incident,
            "signals": app.state.service.list_signals(incident["id"]),
            "events": app.state.service.list_events(incident["id"]),
            "decision": app.state.service.decision_for_incident(incident),
        }

    @app.post("/api/v1/incidents", response_model=ImmediateResponse, status_code=201)
    def create_incident(payload: IncidentCreate, response: Response):
        incident, created = app.state.service.create_incident(
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
    def get_incident(incident_id: str):
        try:
            incident = app.state.service.get_incident(incident_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return incident_payload(incident)

    @app.post("/api/v1/incidents/{incident_id}/signals/field", response_model=IncidentWithSignals)
    def add_field_signal(incident_id: str, payload: FieldSignalIn):
        try:
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
    def apply_timeout(incident_id: str):
        try:
            return app.state.service.apply_timeout_if_needed(incident_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/v1/incidents/{incident_id}/restore", response_model=IncidentOut)
    def restore_incident(incident_id: str, payload: RestoreIn):
        try:
            return app.state.service.restore_incident(incident_id, restored_by=payload.restored_by)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/demo/incidents", response_class=HTMLResponse)
    def demo_incidents():
        incidents = app.state.service.list_incidents()
        rows = []
        for inc in incidents:
            rows.append(
                f"<tr><td>{inc['id']}</td><td>{inc['site_id']}</td><td>{inc['province']}</td>"
                f"<td>{inc['status']}</td><td>{inc['severity']}</td><td>{inc['current_eta_hours']}</td>"
                f"<td>{inc['dispatch_decision']}</td></tr>"
            )
        html = f"""
        <html>
        <head>
          <title>Outage Intelligence Demo</title>
          <style>
            body {{ font-family: Arial, sans-serif; margin: 24px; }}
            table {{ border-collapse: collapse; width: 100%; }}
            td, th {{ border: 1px solid #ddd; padding: 8px; }}
            th {{ text-align: left; background: #f3f3f3; }}
          </style>
        </head>
        <body>
          <h1>Outage Intelligence Demo</h1>
          <p>Simple HTML view for incident state, ETA revisions, and operational recommendation.</p>
          <table>
            <thead>
              <tr>
                <th>ID</th><th>Site</th><th>Province</th><th>Status</th><th>Severity</th><th>ETA Hours</th><th>Decision</th>
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
