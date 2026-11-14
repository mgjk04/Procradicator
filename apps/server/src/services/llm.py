import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic_ai import Agent, AgentRunResult, ModelMessage, NativeOutput
from pydantic_ai.models.groq import GroqModel
from pydantic_ai.providers.groq import GroqProvider

from src.constants.messages import (
    ERR_CRITICAL,
    ERR_DATABASE_UNAVAIL,
    ERR_MISSING_REF,
    ROADMAP_CREATED_TEMPLATE,
    ROADMAP_UPDATED_TEMPLATE,
)
from src.constants.prompts import DATETIME_PROMPT, INIT_INSTRUCTIONS, UPDATE_CONTEXT
from src.core.config import settings
from src.exceptions import (
    DependencyUnavailableError,
    ItemNotFoundError,
)
from src.models.chat import ChatMessage, ChatSession, Role
from src.models.task import Task
from src.schemas.llm import ChatResponse
from src.schemas.task import CreateTask, GetTask, UpdateTask
from src.services.protocols import ChatServiceProtocol, TaskServiceProtocol
from src.utils import chat_hist_mapper

logger: logging.Logger = logging.getLogger(__name__)


@dataclass
class AgentDeps:
    task_svc: TaskServiceProtocol
    chat_svc: ChatServiceProtocol
    session_id: UUID
    user_id: UUID


class LLMService:
    def __init__(self) -> None:
        # turns out they had one for groq the whole time
        self.model = GroqModel(
            model_name=settings.model_name,
            provider=GroqProvider(api_key=settings.groq_api_key),
        )

        self.agent: Agent[AgentDeps, ChatResponse | CreateTask | UpdateTask] = Agent(
            model=self.model,
            deps_type=AgentDeps,
            output_type=NativeOutput(
                [ChatResponse, CreateTask, UpdateTask],
                name="llm_response",
                description=(
                    "Choose between asking a clarification question, "
                    "creating the roadmap or updating an existing roadmap"
                ),
            ),
            instructions=(INIT_INSTRUCTIONS),
            system_prompt=(),
            retries=3,
        )

    async def handle_chat(
        self,
        session_id: UUID,
        user_id: UUID,
        user_input: str,
        task_svc: TaskServiceProtocol,
        chat_svc: ChatServiceProtocol,
        tz: str,
    ) -> ChatMessage:
        reply: str = ERR_CRITICAL
        role: Role = Role.ASSISTANT
        try:
            await chat_svc.add_message(
                session_id, user_id, role=Role.USER, content=user_input
            )  # user input

            session: ChatSession = await chat_svc.get_session(session_id, user_id)
            linked_task_id: UUID | None = session.task_id

            db_history: Sequence[ChatMessage] = (await chat_svc.get_history(session_id, user_id))[
                ::-1
            ]  # oldest first
            pydantic_history: Sequence[ModelMessage] = chat_hist_mapper.map_chat_history(db_history)
            deps: AgentDeps = AgentDeps(
                task_svc=task_svc,
                chat_svc=chat_svc,
                session_id=session_id,
                user_id=user_id,
            )

            update_context: str = ""

            if linked_task_id:
                current_task: Task = await task_svc.read_map(linked_task_id, user_id)
                current_task_payload: dict[str, object] = GetTask.model_validate(
                    current_task
                ).model_dump(mode="json")

                update_context = UPDATE_CONTEXT.format(
                    current_task=json.dumps(current_task_payload)
                )

            user_tz = ZoneInfo(tz)
            now = datetime.now(user_tz).isoformat()
            result: AgentRunResult[ChatResponse | CreateTask | UpdateTask] = await self.agent.run(
                deps=deps,
                message_history=pydantic_history,
                instructions=DATETIME_PROMPT.format(now=now, tz=tz) + update_context,
            )
            response: ChatResponse | CreateTask | UpdateTask = result.output
            if isinstance(response, (CreateTask, UpdateTask)):
                due_at = response.due_at
                if due_at.tzinfo is None:
                    due_at = due_at.replace(tzinfo=user_tz)
                response.due_at = due_at.astimezone(UTC)

            match response:
                case ChatResponse():
                    reply = response.msg
                case CreateTask():
                    if not linked_task_id:
                        task: Task = await task_svc.create_map(response, user_id)
                        await chat_svc.link_task_to_session(task.id, session_id, user_id)
                        reply = ROADMAP_CREATED_TEMPLATE.format(
                            title=task.title, count=len(response.subtasks)
                        )
                        role = Role.TOOL
                case UpdateTask():
                    if linked_task_id:
                        await task_svc.update_map(linked_task_id, response, user_id)
                        await chat_svc.link_task_to_session(linked_task_id, session_id, user_id)
                        task: Task = await task_svc.read_map(linked_task_id, user_id)
                        reply = ROADMAP_UPDATED_TEMPLATE.format(
                            title=task.title, count=len(response.subtasks)
                        )
                        role = Role.TOOL

        except ItemNotFoundError as e:
            logger.error(f"Roadmap build failed due to missing reference subtask tracking: {e}")
            reply = ERR_MISSING_REF

        except DependencyUnavailableError as e:
            logger.error(f"DB unavailable during roadmap save: {e}")
            reply = ERR_DATABASE_UNAVAIL

        except Exception as e:
            logger.critical(f"Critical LLM execution: {str(e)}", exc_info=True)
            reply = ERR_CRITICAL
        finally:
            res: ChatMessage = await chat_svc.add_message(
                session_id, user_id, role=role, content=reply
            )
        return res
