import uuid
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth_dependencies import get_studio_id, solo_dueno
from database import get_db
from services import agent_dashboard_service

router = APIRouter(prefix="/api/agent/dashboard", tags=["Agent - Dashboard"])


class MessageContext(BaseModel):
    current_view: Optional[str] = None
    date_range: Optional[dict] = None


class ConversationMessage(BaseModel):
    role: str
    content: str


class DashboardChatRequest(BaseModel):
    message: str
    context: Optional[MessageContext] = None
    conversation_history: list[ConversationMessage] = []
    session_id: Optional[str] = None


@router.post("/chat")
async def chat(
    body: DashboardChatRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
    studio_id: int = Depends(get_studio_id),
):
    """
    Endpoint del Dashboard Intelligence Agent.
    Retorna interpretación en lenguaje natural con datos reales del estudio.
    """
    session_id = body.session_id or str(uuid.uuid4())
    history = [{"role": m.role, "content": m.content} for m in body.conversation_history]
    context_dict = body.context.model_dump() if body.context else {}

    return await agent_dashboard_service.chat(
        db=db,
        studio_id=studio_id,
        message=body.message,
        context=context_dict,
        conversation_history=history,
        session_id=session_id,
    )
