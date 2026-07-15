"""Schemas de resposta do módulo de Planta Baixa."""
from pydantic import BaseModel, Field


class Cota(BaseModel):
    valor: float = Field(..., description="Valor da cota em metros")
    texto_original: str = Field(..., description="Texto identificado pelo OCR")
    orientacao: str = Field(..., description="horizontal | vertical | desconhecida")
    confianca: float = Field(..., ge=0.0, le=1.0)
    posicao: list[float] | None = Field(
        None, description="Bounding box [x0, y0, x1, y1] em pixels"
    )


class Ambiente(BaseModel):
    nome: str
    area: float | None = Field(None, description="Área em m² (quando disponível)")
    confianca: float = Field(1.0, ge=0.0, le=1.0)


class PlantaAnalise(BaseModel):
    frente: float | None = None
    fundos: float | None = None
    lateral_direita: float | None = None
    lateral_esquerda: float | None = None
    area_construida: float | None = None
    escala: str | None = None
    pavimentos: int | None = None
    cotas: list[Cota] = []
    ambientes: list[Ambiente] = []
    avisos: list[str] = []


class PlantaResponse(BaseModel):
    arquivo: str
    total_plantas: int
    plantas: list[PlantaAnalise]
    tempo_processamento_s: float
