from fastapi import Request

from app.orchestration.message_processor import MessageProcessor
from app.shared.exceptions import ServiceNotReadyError


def get_message_processor(request: Request) -> MessageProcessor:
    processor = request.app.state.dependencies.message_processor
    if processor is None:
        raise ServiceNotReadyError
    return processor
