"""Visão computacional para plantas baixas.

Pipeline:
1. Detecção de paredes (linhas espessas via morfologia).
2. Detecção de linhas de cota (linhas finas longas via HoughLinesP).
3. Estimativa do contorno externo da edificação (bounding box das paredes).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class LinhaDetectada:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def horizontal(self) -> bool:
        return abs(self.y1 - self.y0) <= abs(self.x1 - self.x0) * 0.15

    @property
    def vertical(self) -> bool:
        return abs(self.x1 - self.x0) <= abs(self.y1 - self.y0) * 0.15

    @property
    def comprimento(self) -> float:
        return ((self.x1 - self.x0) ** 2 + (self.y1 - self.y0) ** 2) ** 0.5


@dataclass
class ResultadoVisao:
    paredes: list[LinhaDetectada]
    linhas_cota: list[LinhaDetectada]
    contorno_edificacao: tuple[float, float, float, float] | None  # x0, y0, x1, y1


def analisar_planta(imagem_rgb) -> ResultadoVisao:
    import cv2
    import numpy as np

    cinza = cv2.cvtColor(imagem_rgb, cv2.COLOR_RGB2GRAY)
    _, binaria = cv2.threshold(cinza, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # --- 1. Paredes: traços espessos → sobrevivem a uma erosão forte -------
    kernel_espesso = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    espessas = cv2.erode(binaria, kernel_espesso, iterations=1)
    espessas = cv2.dilate(espessas, kernel_espesso, iterations=2)

    paredes = _extrair_linhas(espessas, comprimento_min=max(imagem_rgb.shape) // 20)

    # --- 2. Linhas de cota: traços finos e longos ---------------------------
    finas = cv2.subtract(binaria, espessas)
    linhas_cota = _extrair_linhas(finas, comprimento_min=max(imagem_rgb.shape) // 15)

    # --- 3. Contorno externo da edificação ----------------------------------
    contorno = None
    contornos, _ = cv2.findContours(espessas, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contornos:
        maior = max(contornos, key=cv2.contourArea)
        if cv2.contourArea(maior) > (imagem_rgb.shape[0] * imagem_rgb.shape[1]) * 0.02:
            x, y, w, h = cv2.boundingRect(maior)
            contorno = (float(x), float(y), float(x + w), float(y + h))

    logger.debug(
        "Visão: %d paredes, %d linhas de cota, contorno=%s",
        len(paredes), len(linhas_cota), contorno is not None,
    )
    return ResultadoVisao(paredes=paredes, linhas_cota=linhas_cota, contorno_edificacao=contorno)


def _extrair_linhas(mascara, comprimento_min: int) -> list[LinhaDetectada]:
    import cv2

    segmentos = cv2.HoughLinesP(
        mascara,
        rho=1,
        theta=3.14159 / 180,
        threshold=80,
        minLineLength=comprimento_min,
        maxLineGap=10,
    )
    linhas: list[LinhaDetectada] = []
    if segmentos is not None:
        for seg in segmentos:
            x0, y0, x1, y1 = map(float, seg[0])
            linha = LinhaDetectada(x0, y0, x1, y1)
            if linha.horizontal or linha.vertical:
                linhas.append(linha)
    return linhas
