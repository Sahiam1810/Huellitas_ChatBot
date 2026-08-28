class ServiceNotReadyError(RuntimeError):
    """Raised when the application cannot receive traffic yet."""


class ChatModelError(RuntimeError):
    """Base error for provider-neutral model failures."""


class ModelConfigurationError(ChatModelError):
    pass


class ModelAuthenticationError(ChatModelError):
    pass


class ModelRateLimitError(ChatModelError):
    pass


class ModelTimeoutError(ChatModelError):
    pass


class ModelUnavailableError(ChatModelError):
    pass


class ModelRequestError(ChatModelError):
    pass


class ModelInvalidResponseError(ChatModelError):
    pass


class VectorStoreError(RuntimeError):
    """Base error for provider-neutral vector store failures."""


class VectorStoreUnavailableError(VectorStoreError):
    """Raised when the configured vector store cannot serve requests."""


class VectorStoreConfigurationError(VectorStoreError):
    """Raised when vector storage is incompatible with active configuration."""


class VectorStoreInvalidResponseError(VectorStoreError):
    """Raised when vector storage returns an invalid response."""


class EmbeddingModelError(RuntimeError):
    """Base error for provider-neutral embedding failures."""


class EmbeddingConfigurationError(EmbeddingModelError):
    pass


class EmbeddingAuthenticationError(EmbeddingModelError):
    pass


class EmbeddingRateLimitError(EmbeddingModelError):
    pass


class EmbeddingTimeoutError(EmbeddingModelError):
    pass


class EmbeddingUnavailableError(EmbeddingModelError):
    pass


class EmbeddingRequestError(EmbeddingModelError):
    pass


class EmbeddingInvalidResponseError(EmbeddingModelError):
    pass


class KnowledgeError(RuntimeError):
    """Base error for global knowledge document operations."""


class KnowledgeNotConfiguredError(KnowledgeError):
    pass


class KnowledgeDocumentNotFoundError(KnowledgeError):
    pass


class KnowledgeExternalIdConflictError(KnowledgeError):
    pass


class KnowledgeDocumentDeletedError(KnowledgeError):
    pass


class KnowledgeDocumentConsistencyError(KnowledgeError):
    pass


class IdempotencyError(RuntimeError):
    """Base error for provider-neutral idempotency failures."""


class IdempotencyKeyConflictError(IdempotencyError):
    pass


class IdempotencyCapacityExceededError(IdempotencyError):
    pass


class TokenValidatorConfigurationError(RuntimeError):
    """Raised when access-token validation cannot be configured safely."""


class AuthenticationError(RuntimeError):
    """Base error for access-token authentication failures."""


class AuthenticationRequiredError(AuthenticationError):
    pass


class InvalidAccessTokenError(AuthenticationError):
    pass


class AuthorizationError(RuntimeError):
    """Base error for authenticated requests that are not authorized."""


class IdentityMismatchError(AuthorizationError):
    pass


class InsufficientPermissionsError(AuthorizationError):
    pass


class GraphCompositionError(RuntimeError):
    """Raised when the main orchestration graph cannot be composed safely."""


class InvalidModuleResultError(RuntimeError):
    """Raised when a module returns data outside its selected contract."""
