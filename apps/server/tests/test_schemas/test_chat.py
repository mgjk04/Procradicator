import pytest
from pydantic import ValidationError
from src.schemas.chat import CreateMessage


class TestChat:
    def test_chat_create_msg_valid(self) -> None:
        data = {"msg": "test", "tz": "Asia/Singapore"}
        model: CreateMessage = CreateMessage(**data)
        assert model.msg == "test"
        assert model.tz == "Asia/Singapore"

    def test_chat_create_msg_invalid_type(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            CreateMessage(msg=1, tz="Asia/Singapore")  # type: ignore[arg-type]
        assert "msg" in str(exc_info.value)
