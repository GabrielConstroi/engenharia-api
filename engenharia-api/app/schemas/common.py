"""Schemas comuns."""
from pydantic import BaseModel


class StatusResponse(BaseModel):
    status: str = "online"
    versao: str
    modulos: list[str]


class ErroResponse(BaseModel):
    detail: str
    codigo: str | None = None
