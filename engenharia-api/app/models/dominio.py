"""Modelos de domínio internos (dataclasses usadas entre os módulos).

Os schemas Pydantic em `app/schemas/` definem os contratos externos da API;
estes modelos representam estruturas internas de processamento.
"""
from app.ocr.engine import TextoDetectado
from app.vision.documento import Pagina
from app.vision.planta_vision import LinhaDetectada, ResultadoVisao

__all__ = ["TextoDetectado", "Pagina", "LinhaDetectada", "ResultadoVisao"]
