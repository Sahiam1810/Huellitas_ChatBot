from fastapi import Request

from app.knowledge.management_service import KnowledgeManagementService
from app.orchestration.message_handler import MessageHandler
from app.shared.exceptions import KnowledgeNotConfiguredError, ServiceNotReadyError


def get_message_processor(request: Request) -> MessageHandler:
    processor = request.app.state.dependencies.message_processor
    if processor is None:
        raise ServiceNotReadyError
    return processor


def get_knowledge_management_service(request: Request) -> KnowledgeManagementService:
    service = request.app.state.dependencies.knowledge_management_service
    if service is None:
        raise KnowledgeNotConfiguredError("Knowledge management is not configured")
    return service
