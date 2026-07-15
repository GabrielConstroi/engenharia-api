"""Carregamento de documentos: PDF → páginas (imagem + texto vetorial) e imagens."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.utils.logging import get_logger

logger = get_logger(__name__)

DPI_RENDER = 200  # resolução de rasterização das páginas de PDF


@dataclass
class Pagina:
    numero: int
    imagem: Any  # numpy array RGB
    texto_vetorial: str = ""  # texto embutido no PDF (quando não é digitalizado)
    palavras: list[dict] = field(default_factory=list)  # palavras com posição (pdfplumber)


def carregar_paginas(conteudo: bytes, tipo: str) -> list[Pagina]:
    """Converte o arquivo enviado em uma lista de páginas prontas para análise."""
    if tipo == "pdf":
        return _carregar_pdf(conteudo)
    return [_carregar_imagem(conteudo)]


def _carregar_pdf(conteudo: bytes) -> list[Pagina]:
    import fitz  # PyMuPDF
    import numpy as np

    paginas: list[Pagina] = []
    with fitz.open(stream=conteudo, filetype="pdf") as doc:
        for i, page in enumerate(doc):
            zoom = DPI_RENDER / 72.0
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width, pix.n
            )
            paginas.append(Pagina(numero=i + 1, imagem=img, texto_vetorial=page.get_text()))

    # Enriquecer com palavras posicionadas via pdfplumber (melhor para tabelas de SPT)
    try:
        import io

        import pdfplumber

        with pdfplumber.open(io.BytesIO(conteudo)) as pdf:
            for i, page in enumerate(pdf.pages):
                if i < len(paginas):
                    paginas[i].palavras = page.extract_words() or []
    except Exception as exc:  # pragma: no cover
        logger.warning("pdfplumber falhou ao extrair palavras: %s", exc)

    return paginas


def _carregar_imagem(conteudo: bytes) -> Pagina:
    import cv2
    import numpy as np

    arr = np.frombuffer(conteudo, dtype=np.uint8)
    img_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img_bgr is None:
        raise ValueError("Não foi possível decodificar a imagem enviada.")
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    return Pagina(numero=1, imagem=img_rgb)
