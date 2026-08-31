from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Response, Security

from app.api.dependencies import (
    AuthenticatedAccess,
    bind_message_identity,
    get_authenticated_access,
    get_message_processor,
)
from app.api.schemas.requests import MessageRequest
from app.api.schemas.responses import (
    MessageProblemDetail,
    MessageResponse,
    RagResponse,
    TokenUsageResponse,
)
from app.orchestration.execution_context import ExecutionContext
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
            "description": (
                "The idempotency key conflicts or the conversation is already processing a message."
            ),
        },
        401: {"model": MessageProblemDetail, "description": "Authentication is required."},
        403: {
            "model": MessageProblemDetail,
            "description": "Authenticated identity does not match the message envelope.",
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
    access: Annotated[
        AuthenticatedAccess,
        Security(get_authenticated_access),
    ],
) -> MessageResponse:
    authenticated_roles = bind_message_identity(payload, access.principal)
    command = MessageCommand(
        message=payload.message,
        conversation_id=payload.conversation_id,
        user_id=payload.user_id,
        pet_id=payload.pet_id,
        channel=payload.channel,
        language=payload.language,
        roles=authenticated_roles,
        is_escalated=payload.is_escalated,
        correlation_id=payload.correlation_id,
        idempotency_key=payload.idempotency_key,
        publish_as_global_knowledge=payload.publish_as_global_knowledge,
    )
    result = await processor.process(
        command,
        ExecutionContext(
            bearer_token=access.bearer_token,
            principal=access.principal,
            execution_id=uuid4(),
            correlation_id=command.correlation_id,
        ),
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
            route=result.rag.route,
            top_score=result.rag.top_score,
            global_matches=result.rag.global_matches,
            conversation_matches=result.rag.conversation_matches,
            memory_stored=result.rag.memory_stored,
            knowledge_published=result.rag.knowledge_published,
        ),
    )
