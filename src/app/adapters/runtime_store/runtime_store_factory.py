from redis.asyncio import Redis

from app.adapters.runtime_store.redis import RedisRuntimeStore
from app.bootstrap.settings import Settings
from app.ports.runtime_store import RuntimeStore


def create_runtime_store(settings: Settings) -> RuntimeStore | None:
    configuration = settings.active_redis_configuration()
    if configuration is None:
        return None
    password = (
        configuration.password.get_secret_value()
        if configuration.password is not None
        else None
    )
    client = Redis.from_url(
        str(configuration.url),
        username=configuration.username,
        password=password,
        db=configuration.database,
        socket_connect_timeout=configuration.connect_timeout_seconds,
        socket_timeout=configuration.operation_timeout_seconds,
        max_connections=configuration.max_connections,
        decode_responses=False,
    )
    return RedisRuntimeStore(client)
