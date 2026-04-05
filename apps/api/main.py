from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from .schemas import FieldSignalIn, ImmediateResponse, IncidentCreate, IncidentOut, IncidentWithSignals, RestoreIn, SignalOut
from .services import IncidentService


def create_app(db_path: str | Path | None = None) -> FastAPI:
    service = IncidentService(db_path=db_path)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield

    app = FastAPI(
        title="Outage Intelligence API MVP",
        version="0.1.0",
        summary="Public-safe event-driven outage intelligence demo",
        lifespan=lifespan,
    )
    app.state.service = service

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/api/v1/incidents", response_model=ImmediateResponse)
    def create_incident(payload: IncidentCreate):
        incident = app.state.service.create_incident(
            client_name=payload.client_name,
            site_id=payload.site_id,
            province=payload.province,
            scada_status=payload.scada_status,
        )
        return {
            "incident": incident,
            "recommendation": incident["dispatch_decision"],
            "message": f"Initial hold ETA is {incident['current_eta_hours']} hours.",
        }

    @app.get("/api/v1/incidents/{incident_id}", response_model=IncidentWithSignals)
    def get_incident(incident_id: str):
        try:
            incident = app.state.service.get_incident(incident_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        signals = app.state.service.list_signals(incident_id)
        return {"incident": incident, "signals": signals}

    @app.post("/api/v1/incidents/{incident_id}/signals/field", response_model=IncidentWithSignals)
    def add_field_signal(incident_id: str, payload: FieldSignalIn):
        try:
            incident, _signal = app.state.service.add_field_signal(
                incident_id=incident_id,
                channel=payload.channel,
                raw_text=payload.raw_text,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        signals = app.state.service.list_signals(incident_id)
        return {"incident": incident, "signals": signals}

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
