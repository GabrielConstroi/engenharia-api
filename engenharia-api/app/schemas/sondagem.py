"""Schemas de resposta do módulo de Sondagem SPT."""
from pydantic import BaseModel, Field


class CamadaSolo(BaseModel):
    inicio: float = Field(..., description="Profundidade inicial da camada (m)")
    fim: float = Field(..., description="Profundidade final da camada (m)")
    solo: str = Field(..., description="Classificação do solo")
    solo_normalizado: str = Field(..., description="Categoria padronizada do solo")
    nspt: int | None = Field(None, description="Valor NSPT médio da camada")
    umidade: str | None = None
    descricao_original: str | None = None


class FuroSondagem(BaseModel):
    furo: str = Field(..., description="Identificação do furo (ex.: SP-01)")
    profundidade_inicial: float = 0.0
    profundidade_total: float | None = None
    nivel_agua: float | None = Field(None, description="Nível do lençol freático (m)")
    presenca_agua: bool = False
    camadas: list[CamadaSolo] = []
    nspt_por_metro: dict[str, int] = Field(
        default_factory=dict, description="NSPT por profundidade, ex.: {'1.00': 5}"
    )
    avisos: list[str] = []


class SondagemResponse(BaseModel):
    arquivo: str
    total_furos: int
    furos: list[FuroSondagem]
    tempo_processamento_s: float
