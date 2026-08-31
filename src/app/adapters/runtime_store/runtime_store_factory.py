from app.adapters.redis.client_factory import create_redis_client
from app.adapters.runtime_store.redis import RedisRuntimeStore
from app.bootstrap.settings import Settings
from app.ports.runtime_store import RuntimeStore


def create_runtime_store(settings: Settings) -> RuntimeStore | None:
    configuration = settings.active_redis_configuration()
    if configuration is None:
        return None
    client = create_redis_client(configuration)
    return RedisRuntimeStore(client)
