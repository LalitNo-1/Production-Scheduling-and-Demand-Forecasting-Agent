"""
Agent interaction endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.models.db import get_db
from app.models.schemas import AgentRunRequest, AgentRunResponse
from app.services.agent import get_agent

router = APIRouter()


@router.post("/agent/run", response_model=AgentRunResponse)
def run_agent(req: AgentRunRequest, db: Session = Depends(get_db)):
    """
    Trigger a full agent reasoning cycle for a SKU.
    The agent will: forecast → check capacity → propose change → simulate impact → summarize.
    Returns a proposed_change_id if a proposal was made (confidence=medium/high).
    Returns status=flagged_low_confidence if forecast is too uncertain.
    """
    agent = get_agent(db)
    try:
        result = agent.run(req.sku, req.horizon_days, req.machine_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent run failed: {str(e)}")

    return AgentRunResponse(**result)


@router.get("/agent/status")
def agent_status():
    """Returns the current LLM mode."""
    import os
    mode = os.getenv("LLM_MODE", "mock").lower()
    has_key = bool(os.getenv("ANTHROPIC_API_KEY", "").strip())
    return {
        "llm_mode": "real_claude" if (mode != "mock" and has_key) else "mock",
        "has_api_key": has_key,
        "note": "Set LLM_MODE=real and ANTHROPIC_API_KEY to use Claude.",
    }
