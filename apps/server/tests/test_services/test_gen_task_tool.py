from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from pydantic_ai import Agent, ModelResponse, TextPart, ToolCallPart, models
from pydantic_ai.models.function import AgentInfo, FunctionModel
from src.exceptions import DatabaseError, ServiceError
from src.models.chat import ChatMessage, Role
from src.services.llm import AgentDeps, LLMService

pytestmark = pytest.mark.anyio
models.ALLOW_MODEL_REQUESTS = False


@pytest.mark.anyio
async def test_gen_task_tool_handles_db_disconn() -> None:
    mock_task_svc: MagicMock = MagicMock()
    mock_chat_svc: MagicMock = MagicMock()
    session_id: UUID = uuid4()

    # sim unexpected error
    db_err: DatabaseError = DatabaseError("database connection was lost")
    svc_err: ServiceError = ServiceError(
        f"Could not generate roadmap: {str(db_err)}"
    )
    svc_err.__cause__ = db_err
    mock_task_svc.create_roadmap.side_effect = svc_err

    mock_chat_svc.get_history.return_value = []
    mock_chat_svc.add_message.return_value = ChatMessage(
        id=uuid4(),
        session_id=session_id,
        role=Role.ASSISTANT,
        content="Mocked Response",
    )

    deps: AgentDeps = AgentDeps(
        task_svc=mock_task_svc, chat_svc=mock_chat_svc, session_id=session_id
    )

    async def mock_llm_behavior(messages, info: AgentInfo) -> ModelResponse:
        subtask = {
            "temp_id": "temp_id",
            "title": "subtask title",
            "description": "subtask desc",
            "depends_on": [],
        }

        # if initial turn, make llm req a tool call
        if not any(isinstance(p, ToolCallPart) for m in messages for p in getattr(m, "parts", [])):
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="generate_task_tool",
                        args={
                            "roadmap": {
                                "title": "Test Task",
                                "description": None,
                                "subtasks": [subtask],
                            }
                        },
                    )
                ]
            )
        # for subsequent calls (after the tool runs), stop execution by returning text
        return ModelResponse(parts=[TextPart(content="yada yada nothing impt here")])

    llm_svc: LLMService = LLMService()
    agent: Agent[AgentDeps, str] = llm_svc.agent
    mock_model = FunctionModel(function=mock_llm_behavior)

    with agent.override(model=mock_model, deps=deps):
        await llm_svc.handle_chat(
            session_id=session_id,
            user_input="some user input",
            task_svc=mock_task_svc,
            chat_svc=mock_chat_svc,
        )

    mock_task_svc.create_roadmap.assert_called_once()
    mock_chat_svc.link_task_to_session.assert_not_called()

    # user message and assistant error message saved
    assert mock_chat_svc.add_message.call_count == 2
