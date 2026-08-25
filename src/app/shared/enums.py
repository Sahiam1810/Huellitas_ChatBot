from enum import StrEnum


class MessageResponseType(StrEnum):
    AI_GENERATED = "ai_generated"
    HUMAN_CONTROLLED = "human_controlled"
