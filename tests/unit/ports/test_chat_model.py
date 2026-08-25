import pytest

from app.ports.chat_model import ChatMessage, ChatRequest, ChatResponse, ChatRole, ModelProvider


def test_chat_request_requires_at_least_one_message() -> None:
    with pytest.raises(ValueError, match="at least one message"):
        ChatRequest(messages=())


def test_chat_message_rejects_blank_content() -> None:
    with pytest.raises(ValueError, match="content cannot be blank"):
        ChatMessage(role=ChatRole.USER, content="   ")


def test_chat_request_rejects_invalid_output_limit() -> None:
    message = ChatMessage(role=ChatRole.USER, content="Hello")

    with pytest.raises(ValueError, match="max_output_tokens"):
        ChatRequest(messages=(message,), max_output_tokens=0)


def test_chat_response_keeps_neutral_usage_metadata() -> None:
    response = ChatResponse(
        text="Hello",
        provider=ModelProvider.OPENROUTER,
        model="google/gemini-3.5-flash",
        input_tokens=10,
        output_tokens=4,
        finish_reason="stop",
    )

    assert response.text == "Hello"
    assert response.input_tokens == 10
    assert response.output_tokens == 4
