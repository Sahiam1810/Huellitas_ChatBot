from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.dependencies import get_message_processor
from app.api.schemas.requests import MessageRequest
from app.api.schemas.responses import (
    MessageProblemDetail,
    MessageResponse,
    RagResponse,
    TokenUsageResponse,
)
from app.orchestration.message_handler import MessageHandler
from app.orchestration.message_processor import MessageCommand

router = APIRouter(tags=["Messages"])


@router.post(
    "/messages",
    response_model=MessageResponse,
    responses={
        200: {
            "description": "Message processed successfully.",
            "headers": {
                "Idempotency-Replayed": {
                    "description": (
                        "Whether the response was replayed from the idempotency store."
                    ),
                    "schema": {"type": "string"},
                }
            },
        },
        409: {
            "model": MessageProblemDetail,
            "description": "The idempotency key was reused with another request.",
        },
        422: {"model": MessageProblemDetail, "description": "Invalid message envelope."},
        502: {
            "model": MessageProblemDetail,
            "description": "Provider rejected the request or returned an invalid response.",
        },
        503: {
            "model": MessageProblemDetail,
            "description": "Chat is disabled, rate limited, or unavailable.",
        },
        504: {
            "model": MessageProblemDetail,
            "description": "Provider request timed out.",
        },
    },
    summary="Process a user message",
)
async def create_message(
    payload: MessageRequest,
    response: Response,
    processor: Annotated[MessageHandler, Depends(get_message_processor)],
) -> MessageResponse:
    result = await processor.process(
        MessageCommand(
            message=payload.message,
            conversation_id=payload.conversation_id,
            user_id=payload.user_id,
            pet_id=payload.pet_id,
            channel=payload.channel,
            language=payload.language,
            roles=tuple(payload.roles),
            is_escalated=payload.is_escalated,
            correlation_id=payload.correlation_id,
            idempotency_key=payload.idempotency_key,
            publish_as_global_knowledge=payload.publish_as_global_knowledge,
        )
    )
    usage = None
    if result.input_tokens is not None or result.output_tokens is not None:
        usage = TokenUsageResponse(
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )
    response.headers["Idempotency-Replayed"] = str(result.idempotency_replayed).lower()
    return MessageResponse(
        message=result.message,
        conversation_id=result.conversation_id,
        correlation_id=result.correlation_id,
        response_type=result.response_type,
        provider=result.provider,
        model=result.model,
        usage=usage,
        module=result.module,
        rag=RagResponse(
            status=result.rag.status,
            global_matches=result.rag.global_matches,
            conversation_matches=result.rag.conversation_matches,
            memory_stored=result.rag.memory_stored,
            knowledge_published=result.rag.knowledge_published,
        ),
    )
