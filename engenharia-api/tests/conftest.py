"""Fixtures compartilhadas: cliente de teste e arquivos sintéticos."""
import io

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.utils.cache import cache_resultados


@pytest.fixture()
def client():
    cache_resultados.clear()
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def pdf_sondagem() -> bytes:
    """PDF de sondagem SPT gerado com PyMuPDF contendo texto vetorial realista."""
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    texto = (
        "RELATÓRIO DE SONDAGEM SPT\n"
        "FURO: SP-01\n"
        "N.A.: 3,20\n"
        "PROFUNDIDADE TOTAL: 18,00\n"
        "0,00 a 2,00 - Argila mole, úmida - NSPT: 3\n"
        "2,00 a 5,00 - Silte arenoso, pouco úmido - NSPT: 8\n"
        "5,00 a 12,00 - Areia média compacta - NSPT: 22\n"
        "12,00 a 18,00 - Solo residual duro - NSPT: 35\n"
    )
    page.insert_text((50, 50), texto, fontsize=11)
    buf = doc.tobytes()
    doc.close()
    return buf


@pytest.fixture()
def pdf_planta() -> bytes:
    """PDF com texto de planta baixa (escala, área, ambientes)."""
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    texto = (
        "PLANTA BAIXA - PAVIMENTO TÉRREO\n"
        "ESCALA 1:100\n"
        "ÁREA CONSTRUÍDA: 182,40 m²\n"
        "SALA 25,30 m²\n"
        "COZINHA 12,10 m²\n"
        "QUARTO 14,00 m²\n"
    )
    page.insert_text((50, 50), texto, fontsize=11)
    buf = doc.tobytes()
    doc.close()
    return buf


@pytest.fixture()
def png_simples() -> bytes:
    """PNG branco pequeno válido."""
    import numpy as np
    from PIL import Image

    img = Image.fromarray(np.full((60, 120, 3), 255, dtype=np.uint8))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
