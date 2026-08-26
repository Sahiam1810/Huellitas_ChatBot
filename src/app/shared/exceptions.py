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


class VectorStoreUnavailableError(RuntimeError):
    """Raised when the configured vector store cannot serve requests."""


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
