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
