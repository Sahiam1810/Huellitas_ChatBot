from pydantic import BaseModel, ConfigDict

from app.bootstrap.settings import Environment


class ServiceInfoResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    environment: Environment
    api_version: str = "v1"
