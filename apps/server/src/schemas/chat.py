from uuid import UUID

from pydantic import BaseModel


class CreateSession(BaseModel):
    task_id: UUID | None = None


class CreateMessage(BaseModel):
    msg: str
    tz: str
