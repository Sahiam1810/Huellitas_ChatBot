from unittest.mock import Mock

import pytest

from app.adapters.checkpoints import checkpoint_store_factory
from app.adapters.checkpoints.memory import MemoryCheckpointStore
from app.adapters.checkpoints.redis import RedisCheckpointStore
from app.bootstrap.settings import Settings


def test_memory_selection_never_constructs_a_redis_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructor = Mock()
    monkeypatch.setattr(checkpoint_store_factory, "create_redis_client", constructor)

    store = checkpoint_store_factory.create_checkpoint_store(Settings(_env_file=None))

    assert isinstance(store, MemoryCheckpointStore)
    constructor.assert_not_called()


def test_redis_selection_uses_shallow_saver_and_refreshing_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis_client = Mock()
    raw_saver = Mock()
    client_constructor = Mock(return_value=redis_client)
    saver_constructor = Mock(return_value=raw_saver)
    monkeypatch.setattr(checkpoint_store_factory, "create_redis_client", client_constructor)
    monkeypatch.setattr(checkpoint_store_factory, "AsyncShallowRedisSaver", saver_constructor)
    settings = Settings(
        redis_enabled=True,
        checkpoint_provider="redis",
        checkpoint_ttl_minutes=1440,
        _env_file=None,
    )

    store = checkpoint_store_factory.create_checkpoint_store(settings)

    assert isinstance(store, RedisCheckpointStore)
    redis_configuration = settings.active_redis_configuration()
    assert redis_configuration is not None
    client_constructor.assert_called_once_with(redis_configuration)
    saver_constructor.assert_called_once_with(
        redis_client=redis_client,
        ttl={"default_ttl": 1440, "refresh_on_read": True},
    )
