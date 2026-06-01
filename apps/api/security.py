from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Mapping

from fastapi import HTTPException

DEFAULT_PARTNER_ID = "demo-enterprise-partner"


@dataclass(frozen=True)
class PartnerContext:
    partner_id: str | None
    authenticated: bool


def resolve_partner_context(
    sandbox_api_keys: Mapping[str, str],
    x_partner_id: str | None,
    x_api_key: str | None,
) -> PartnerContext:
    if not sandbox_api_keys:
        return PartnerContext(partner_id=x_partner_id, authenticated=False)

    if not x_partner_id or not x_api_key:
        raise HTTPException(status_code=401, detail="Missing sandbox partner credentials")

    expected_key = sandbox_api_keys.get(x_partner_id)
    if expected_key is None or not secrets.compare_digest(expected_key, x_api_key):
        raise HTTPException(status_code=401, detail="Invalid sandbox partner credentials")

    return PartnerContext(partner_id=x_partner_id, authenticated=True)


def effective_partner_id(context: PartnerContext, requested_partner_id: str | None) -> str:
    if context.partner_id and requested_partner_id and requested_partner_id != context.partner_id:
        raise HTTPException(status_code=403, detail="Partner context does not match request partner_id")
    return requested_partner_id or context.partner_id or DEFAULT_PARTNER_ID


def assert_partner_access(context: PartnerContext, incident: dict) -> None:
    if context.partner_id and incident["partner_id"] != context.partner_id:
        raise HTTPException(status_code=403, detail="Partner cannot access this incident")
