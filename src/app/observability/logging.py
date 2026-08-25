import logging

from app.bootstrap.settings import LogLevel


def configure_logging(level: LogLevel) -> None:
    logging.basicConfig(
        level=level.value,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )
