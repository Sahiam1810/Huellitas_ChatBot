import uvicorn

from app.bootstrap.application import create_application
from app.bootstrap.settings import load_settings


def run() -> None:
    settings = load_settings()
    app = create_application(settings)
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.value.lower(),
    )


if __name__ == "__main__":  # pragma: no cover
    run()
