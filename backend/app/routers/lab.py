"""
ShadowPrompt Lab — API Router
Endpoints for LLM connection testing, campaign management, and payload listing.
API keys are passed via X-LLM-API-Key header and NEVER stored.
"""

import json
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from sqlalchemy import select, desc

from app.database import async_session
from app.models import Campaign, TestResult
from app.lab.proxy import test_connection, LLMProxyError
from app.lab.payloads.registry import get_all_payloads, get_level_metadata, get_payloads_for_levels
from app.lab.campaign import (
    create_campaign,
    run_campaign,
    cancel_campaign,
    calculate_per_level_scores,
    calculate_score,
    get_rating,
)

router = APIRouter()


# --- Request/Response Models ---

class ConnectionTestRequest(BaseModel):
    base_url: str
    model: str

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Base URL cannot be empty.")
        if not v.startswith(("http://", "https://")):
            raise ValueError("Base URL must start with http:// or https://")
        return v

    @field_validator("model")
    @classmethod
    def validate_model(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Model name cannot be empty.")
        return v


class CampaignCreateRequest(BaseModel):
    base_url: str
    model: str
    selected_levels: list[int]

    @field_validator("selected_levels")
    @classmethod
    def validate_levels(cls, v):
        if not v:
            raise ValueError("At least one level must be selected.")
        for level in v:
            if level not in (1, 2, 3):
                raise ValueError(f"Invalid level: {level}. Must be 1, 2, or 3.")
        return sorted(set(v))


# --- Helper ---

def _get_api_key(x_llm_api_key: Optional[str]) -> str:
    """Extract and validate the API key from header."""
    if not x_llm_api_key or not x_llm_api_key.strip():
        raise HTTPException(
            status_code=401,
            detail="Missing X-LLM-API-Key header. Please provide your LLM API key.",
        )
    return x_llm_api_key.strip()


# --- Endpoints ---

@router.post("/connect")
async def test_llm_connection(
    req: ConnectionTestRequest,
    x_llm_api_key: Optional[str] = Header(None),
):
    """
    Test the LLM connection with a simple prompt.
    The API key is passed via X-LLM-API-Key header and never stored.
    """
    api_key = _get_api_key(x_llm_api_key)

    try:
        response = await test_connection(
            api_key=api_key,
            base_url=req.base_url,
            model=req.model,
        )
        return {
            "status": "connected",
            "model": response.model,
            "response": response.content,
            "latency_ms": response.latency_ms,
        }
    except LLMProxyError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "failed",
                "error": e.message,
                "error_code": e.error_code,
            },
        )


@router.post("/campaigns")
async def create_and_start_campaign(
    req: CampaignCreateRequest,
    x_llm_api_key: Optional[str] = Header(None),
):
    """
    Create a new campaign and return its ID.
    The campaign will be started when the client connects to the SSE stream.
    """
    api_key = _get_api_key(x_llm_api_key)

    # Verify connection first
    try:
        await test_connection(api_key=api_key, base_url=req.base_url, model=req.model)
    except LLMProxyError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot start campaign — connection test failed: {e.message}",
        )

    # Verify payloads exist for selected levels
    payloads = get_payloads_for_levels(req.selected_levels)
    if not payloads:
        raise HTTPException(status_code=400, detail="No payloads found for selected levels.")

    # Create campaign record
    campaign = await create_campaign(
        model_name=req.model,
        base_url=req.base_url,
        selected_levels=req.selected_levels,
    )

    return {
        "id": campaign.id,
        "status": campaign.status,
        "total_payloads": campaign.total_payloads,
        "selected_levels": req.selected_levels,
        "model": req.model,
        "stream_url": f"/api/v1/lab/campaigns/{campaign.id}/stream",
    }


@router.get("/campaigns/{campaign_id}/stream")
async def stream_campaign(
    campaign_id: str,
    x_llm_api_key: Optional[str] = Header(None),
):
    """
    SSE stream of live campaign verdicts.
    Connect to this endpoint after creating a campaign to start execution.
    """
    api_key = _get_api_key(x_llm_api_key)

    # Verify campaign exists
    async with async_session() as session:
        result = await session.execute(select(Campaign).where(Campaign.id == campaign_id))
        campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    if campaign.status not in ("running",):
        raise HTTPException(status_code=400, detail=f"Campaign is already {campaign.status}.")

    selected_levels = json.loads(campaign.selected_levels)

    return StreamingResponse(
        run_campaign(
            campaign_id=campaign_id,
            api_key=api_key,
            base_url=campaign.base_url,
            model_name=campaign.model_name,
            selected_levels=selected_levels,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str):
    """Get campaign results with all test results."""
    async with async_session() as session:
        result = await session.execute(select(Campaign).where(Campaign.id == campaign_id))
        campaign = result.scalar_one_or_none()

        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found.")

        # Fetch all test results
        tr_result = await session.execute(
            select(TestResult)
            .where(TestResult.campaign_id == campaign_id)
            .order_by(TestResult.created_at)
        )
        test_results = tr_result.scalars().all()

        # Build per-level scores
        tr_dicts = [
            {
                "id": tr.id,
                "payload_id": tr.payload_id,
                "payload_name": tr.payload_name,
                "level": tr.level,
                "category": tr.category,
                "attack_prompt": tr.attack_prompt,
                "llm_response": tr.llm_response,
                "verdict": tr.verdict,
                "evaluation_layer": tr.evaluation_layer,
                "confidence": tr.confidence,
                "latency_ms": tr.latency_ms,
                "created_at": tr.created_at.isoformat() if tr.created_at else None,
            }
            for tr in test_results
        ]

        level_scores = calculate_per_level_scores(tr_dicts)

        return {
            "id": campaign.id,
            "model_name": campaign.model_name,
            "base_url": campaign.base_url,
            "selected_levels": json.loads(campaign.selected_levels),
            "status": campaign.status,
            "total_payloads": campaign.total_payloads,
            "completed_payloads": campaign.completed_payloads,
            "pass_count": campaign.pass_count,
            "fail_count": campaign.fail_count,
            "partial_count": campaign.partial_count,
            "unclear_count": campaign.unclear_count,
            "overall_score": campaign.overall_score,
            "overall_rating": campaign.overall_rating,
            "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
            "completed_at": campaign.completed_at.isoformat() if campaign.completed_at else None,
            "level_scores": level_scores,
            "test_results": tr_dicts,
        }


@router.post("/campaigns/{campaign_id}/cancel")
async def cancel_running_campaign(campaign_id: str):
    """Cancel a running campaign."""
    success = await cancel_campaign(campaign_id)
    if success:
        return {"status": "cancellation_requested", "campaign_id": campaign_id}
    else:
        raise HTTPException(status_code=400, detail="Campaign is not currently running.")


@router.get("/campaigns")
async def list_campaigns(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
):
    """List past campaigns with pagination."""
    async with async_session() as session:
        query = select(Campaign).order_by(desc(Campaign.created_at))

        if status:
            query = query.where(Campaign.status == status)

        query = query.offset((page - 1) * per_page).limit(per_page)
        result = await session.execute(query)
        campaigns = result.scalars().all()

        return [
            {
                "id": c.id,
                "model_name": c.model_name,
                "selected_levels": json.loads(c.selected_levels),
                "status": c.status,
                "total_payloads": c.total_payloads,
                "completed_payloads": c.completed_payloads,
                "pass_count": c.pass_count,
                "fail_count": c.fail_count,
                "overall_score": c.overall_score,
                "overall_rating": c.overall_rating,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "completed_at": c.completed_at.isoformat() if c.completed_at else None,
            }
            for c in campaigns
        ]


@router.get("/payloads")
async def list_payloads(level: Optional[int] = Query(None, ge=1, le=3)):
    """List all payloads with metadata, optionally filtered by level."""
    payloads = get_all_payloads()
    if level is not None:
        payloads = [p for p in payloads if p.level == level]

    return {
        "levels": get_level_metadata(),
        "payloads": [
            {
                "id": p.id,
                "level": p.level,
                "name": p.name,
                "category": p.category,
                "description": p.description,
                "expected_behavior": p.expected_behavior,
            }
            for p in payloads
        ],
        "total": len(payloads),
    }
