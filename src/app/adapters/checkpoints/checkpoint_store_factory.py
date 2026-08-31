from app.adapters.checkpoints.memory import MemoryCheckpointStore
from app.adapters.checkpoints.redis import RedisCheckpointStore, StrictAsyncShallowRedisSaver
from app.adapters.redis.client_factory import create_redis_client
from app.bootstrap.settings import CheckpointProvider, Settings
from app.ports.checkpoint_store import CheckpointStore


def create_checkpoint_store(settings: Settings) -> CheckpointStore:
    checkpoint_configuration = settings.active_checkpoint_configuration()
    if checkpoint_configuration.provider is CheckpointProvider.MEMORY:
        return MemoryCheckpointStore()

    redis_configuration = settings.active_redis_configuration()
    assert redis_configuration is not None
    client = create_redis_client(redis_configuration)
    raw_saver = StrictAsyncShallowRedisSaver(
        redis_client=client,
        ttl={
            "default_ttl": checkpoint_configuration.ttl_minutes,
            "refresh_on_read": True,
        },
    )
    return RedisCheckpointStore(raw_saver, client)
