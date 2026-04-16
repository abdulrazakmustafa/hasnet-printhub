from pydantic import BaseModel


class APIMessage(BaseModel):
    status: str
    detail: str | None = None

