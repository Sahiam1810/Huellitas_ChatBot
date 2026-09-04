from enum import StrEnum


class MessageResponseType(StrEnum):
    AI_GENERATED = "ai_generated"
    RETRIEVED = "retrieved"
    HUMAN_CONTROLLED = "human_controlled"


class AccessRequirement(StrEnum):
    NONE = "none"
    IDENTITY_VERIFICATION = "identity_verification"
