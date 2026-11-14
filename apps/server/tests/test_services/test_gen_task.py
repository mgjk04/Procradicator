from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from pydantic_ai import (
    AgentRunResult,
    models,
)
from src.constants.messages import ERR_DATABASE_UNAVAIL
from src.exceptions import DependencyUnavailableError
from src.models.chat import ChatMessage, ChatSession, Role
from src.models.task import Task
from src.schemas.task import CreateSubtask, CreateTask
from src.services.llm import LLMService

pytestmark = pytest.mark.anyio
models.ALLOW_MODEL_REQUESTS = False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tz", "expected_due_at"),
    [
        ("Asia/Singapore", datetime(2026, 8, 14, 13, tzinfo=UTC)),
        ("America/New_York", datetime(2026, 8, 15, 1, tzinfo=UTC)),
    ],
)
async def test_ai_task_uses_user_timezone_for_deadline(tz: str, expected_due_at: datetime) -> None:
    session_id = uuid4()
    user_id = uuid4()
    saved_due_at: datetime | None = None

    async def create_map(roadmap: CreateTask, owner_id: UUID) -> Task:
        nonlocal saved_due_at
        saved_due_at = roadmap.due_at
        return Task(id=uuid4(), user_id=owner_id, title=roadmap.title, due_at=roadmap.due_at)

    task_svc = MagicMock()
    task_svc.create_map = AsyncMock(side_effect=create_map)
    chat_svc = MagicMock()
    chat_svc.get_session = AsyncMock(return_value=ChatSession(id=session_id, user_id=user_id))
    chat_svc.get_history = AsyncMock(return_value=[])
    chat_svc.add_message = AsyncMock(
        return_value=ChatMessage(
            id=uuid4(),
            session_id=session_id,
            role=Role.TOOL,
            content="Task created",
        )
    )
    chat_svc.link_task_to_session = AsyncMock()

    result = MagicMock(spec=AgentRunResult)
    result.output = CreateTask(
        title="Submit assignment",
        due_at=datetime(2026, 8, 14, 21),
        subtasks=[CreateSubtask(id="submit", title="Submit", est_m=1, depends_on=[])],
    )
    llm_service = LLMService()
    llm_service.agent.run = AsyncMock(return_value=result)

    await llm_service.handle_chat(
        session_id=session_id,
        user_id=user_id,
        user_input="Submit it by 9 PM",
        task_svc=task_svc,
        chat_svc=chat_svc,
        tz=tz,
    )

    assert saved_due_at == expected_due_at


@pytest.mark.asyncio
async def test_gen_task_handles_db_disconn() -> None:

    mock_task_svc = MagicMock()
    mock_chat_svc = MagicMock()
    session_id = uuid4()
    user_id = uuid4()

    mock_chat_svc.get_session = AsyncMock(return_value=ChatSession(id=session_id, user_id=user_id))
    mock_chat_svc.get_history = AsyncMock(return_value=[])
    mock_chat_svc.add_message = AsyncMock(
        return_value=ChatMessage(
            id=uuid4(),
            session_id=session_id,
            role=Role.ASSISTANT,
            content=ERR_DATABASE_UNAVAIL,
        )
    )

    mock_task_svc.create_map = AsyncMock(side_effect=DependencyUnavailableError("BOOM!"))

    mock_result = MagicMock(spec=AgentRunResult)
    mock_result.output = CreateTask(
        title="Mock roadmap",
        due_at=datetime.now(UTC),
        subtasks=[
            CreateSubtask(id="id 1", title="mock title", est_m=1, is_done=False, depends_on=[])
        ],
    )

    llm_service = LLMService()

    llm_service.agent.run = AsyncMock(return_value=mock_result)

    response_message = await llm_service.handle_chat(
        session_id=session_id,
        user_id=user_id,
        user_input="Fake it till you make it XD",
        task_svc=mock_task_svc,
        chat_svc=mock_chat_svc,
        tz="UTC",
    )

    assert response_message.content == ERR_DATABASE_UNAVAIL

    mock_chat_svc.add_message.assert_any_call(
        session_id,
        user_id,
        role=Role.ASSISTANT,
        content=ERR_DATABASE_UNAVAIL,
    )
