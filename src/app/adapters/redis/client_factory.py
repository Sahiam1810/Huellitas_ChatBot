from urllib.parse import urlsplit, urlunsplit

from app.bootstrap.settings import ActiveRedisConfiguration
from redis.asyncio import Redis


def create_redis_client(configuration: ActiveRedisConfiguration) -> Redis:
    parsed_url = urlsplit(str(configuration.url))
    network_url = urlunsplit((parsed_url.scheme, parsed_url.netloc, "", "", ""))
    password = (
        configuration.password.get_secret_value() if configuration.password is not None else None
    )
    return Redis.from_url(
        network_url,
        username=configuration.username,
        password=password,
        db=configuration.database,
        socket_connect_timeout=configuration.connect_timeout_seconds,
        socket_timeout=configuration.operation_timeout_seconds,
        max_connections=configuration.max_connections,
        decode_responses=False,
    )
