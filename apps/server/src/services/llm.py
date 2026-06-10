import logging
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from pydantic_ai import Agent, AgentRunResult, ModelMessage, ModelRetry, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

# from pydantic_ai.models.ollama import OllamaModel
# from pydantic_ai.providers.ollama import OllamaProvider
from src.core.config import settings
from src.exceptions import DatabaseError, ResourceNotFoundError, ServiceError
from src.models.chat import ChatMessage, Role
from src.models.task import Task
from src.schemas.task import CreateTask
from src.services.chat import ChatService
from src.services.task import TaskService
from src.utils import chat_hist_mapper

logger: logging.Logger = logging.getLogger(__name__)


@dataclass
class AgentDeps:
    task_svc: TaskService
    chat_svc: ChatService
    session_id: UUID


class LLMService:
    def __init__(self) -> None:
        # self.model = OllamaModel(
        #     model_name=settings.model_name,
        #     provider=OllamaProvider(base_url=settings.ollama_base_url),
        # )
        self.model = OpenAIChatModel(
            model_name=settings.model_name,
            provider=OpenAIProvider(base_url=settings.base_url, api_key=settings.groq_api_key),
        )

        # TODO: move the prompt to txt file in prompts folder n create txt file loader
        self.agent = Agent(
            model=self.model,
            deps_type=AgentDeps,
            output_type=str,
            instructions=(
                """
            ROLE: You are the "Procradicator AI Planner," a specialized logic engine
            that converts vague human goals into a strict Directed Acyclic Graph (DAG)
            of actionable tasks.
            STRICT SCHEMA ENFORCEMENT:
            You must output data that match the schema for 'generate_task_tool' exactly.
            Use 'temp_id'.
            Never use 'id' or 'uuid'. This must be a unique slug (e.g., "setup-env").
            Use 'depends_on'.
            Title is mandatory. Description is optional but helpful.
            NEVER use the word 'dependencies'. This is a list of 'temp_id' strings.
            ERROR PREVENTION: If a task has no prerequisites,
            'depends_on' must be an empty list [].

            OPERATIONAL WORKFLOW:
            1. ANALYZE: Review the user's input.
            2. VALIDATE: Do you have enough detail to create at least 3-5 distinct,
            chronological subtasks? Is each subtask such that it is completable within
            hour?
            3. INTERACT: If NO, ask ONE concise question (e.g. "What tools are you using?"
            or "What is your deadline?"). DO NOT PROVIDE THE ROADMAP UNTIL THIS IS
            ANSWERED.
            4. EXECUTE: If YES, call 'generate_task_tool' immediately.

            LOGIC CONSTRAINTS:
            Every 'depends_on' entry must refer to a 'temp_id' that exists within the
            same task set. Tasks must be "atomic"—small enough that a user doesn't
            procrastinate starting them. Direct output to the tool only; do not add
            conversational "here is your roadmap" fluff when calling the tool.
                          """
            ),
            system_prompt=(),
            retries=3,
        )

        @self.agent.tool
        async def generate_task_tool(ctx: RunContext[AgentDeps], roadmap: CreateTask) -> str | None:
            try:
                logger.info("TOOL CALL")
                task: Task = ctx.deps.task_svc.create_roadmap(roadmap)
                if not task.id:
                    raise ValueError()
                ctx.deps.chat_svc.link_task_to_session(task.id, ctx.deps.session_id)
                return (
                    f"SUCCESS: Task '{task.title}' created with {len(roadmap.subtasks)} subtasks."  # noqa: E501
                )

            except ValueError as e:
                raise ModelRetry(
                    f"Value Error: {str(e)}. Check your structure and ensure your fields for tasks and subtasks are correct."  # noqa: E501
                ) from e
            except ServiceError as e:
                match e.__cause__:
                    case ResourceNotFoundError():
                        raise ModelRetry(
                            f"Not Found: {str(e)}. Ensure all dependencies exist in your list."
                        ) from e
                    case DatabaseError():
                        # if fatal DB error, stop retrying
                        return f"Encountered a database issue: {str(e)}"
                    case _:
                        return f"An unexpected error occured: {str(e)}"


    async def handle_chat(
        self,
        session_id: UUID,
        user_input: str,
        task_svc: TaskService,
        chat_svc: ChatService,
    ) -> ChatMessage:
        chat_svc.add_message(session_id, role=Role.USER, content=user_input)  # user input

        db_history: Sequence[ChatMessage] = chat_svc.get_history(session_id)
        pydantic_history: Sequence[ModelMessage] = chat_hist_mapper.map_chat_history(db_history)
        deps: AgentDeps = AgentDeps(task_svc=task_svc, chat_svc=chat_svc, session_id=session_id)

        result: AgentRunResult[str] = await self.agent.run(
            user_input, deps=deps, message_history=pydantic_history
        )

        res: ChatMessage = chat_svc.add_message(
            session_id, role=Role.ASSISTANT, content=result.output
        )  # agent input

        return res
