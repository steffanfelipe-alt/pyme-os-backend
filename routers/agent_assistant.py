import uuid
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth_dependencies import require_rol
from database import get_db
from services import agent_assistant_service

router = APIRouter(prefix="/api/agent/assistant", tags=["Agent - Assistant"])


class ConversationMessage(BaseModel):
    role: str
    content: str


class AssistantChatRequest(BaseModel):
    message: str
    conversation_history: list[ConversationMessage] = []
    session_id: Optional[str] = None


@router.post("/chat")
async def chat(
    body: AssistantChatRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
):
    """
    Chatbot interno de consultas de contabilidad argentina.
    No accede a datos del estudio — es un experto en normativa fiscal.
    """
    session_id = body.session_id or str(uuid.uuid4())
    history = [{"role": m.role, "content": m.content} for m in body.conversation_history]

    return await agent_assistant_service.chat(
        db=db,
        studio_id=current_user.get("studio_id"),
        user_id=current_user.get("user_id"),
        message=body.message,
        conversation_history=history,
        session_id=session_id,
    )
