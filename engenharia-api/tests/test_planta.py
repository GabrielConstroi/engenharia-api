"""Testes do módulo de Planta Baixa."""
from unittest.mock import patch

from app.ocr.engine import corrigir_numero_ocr, interpretar_cota_metros
from app.services.planta_service import _extrair_escala


def test_correcao_erros_ocr():
    """Leitura correta das cotas mesmo com erros típicos de OCR."""
    assert corrigir_numero_ocr("3,50") == "3.50"
    assert corrigir_numero_ocr("l2.50") == "12.50"   # l → 1
    assert corrigir_numero_ocr("3.5O") == "3.50"     # O → 0
    assert corrigir_numero_ocr("350 cm") == "350"
    assert corrigir_numero_ocr("12.50m") == "12.50"
    assert corrigir_numero_ocr("###") is None


def test_interpretacao_cotas_em_metros():
    assert interpretar_cota_metros("3,50") == 3.50
    assert interpretar_cota_metros("350") == 3.50      # cm → m
    assert interpretar_cota_metros("12.40") == 12.40
    assert interpretar_cota_metros("12") == 12.0       # cota de terreno em m
    assert interpretar_cota_metros("0") is None
    assert interpretar_cota_metros("abc") is None


def test_extracao_escala():
    assert _extrair_escala("ESCALA 1:100") == "1:100"
    assert _extrair_escala("ESC. 1/50") == "1:50"
    assert _extrair_escala("Planta baixa esc: 1 : 75") == "1:75"
    assert _extrair_escala("sem escala aqui") is None


def test_upload_pdf_planta(client, pdf_planta):
    """PDF com texto vetorial: escala, área e ambientes devem ser extraídos."""
    with patch("app.services.planta_service.extrair_textos", return_value=[]):
        r = client.post(
            "/api/v1/planta/analisar",
            files={"arquivo": ("planta.pdf", pdf_planta, "application/pdf")},
        )
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["total_plantas"] >= 1
    planta = corpo["plantas"][0]
    assert planta["escala"] == "1:100"
    assert planta["area_construida"] == 182.40
    nomes = {a["nome"].lower() for a in planta["ambientes"]}
    assert {"sala", "cozinha", "quarto"} <= nomes


def test_upload_imagem(client, png_simples):
    """Upload de imagem PNG deve ser aceito e processado sem erro."""
    with patch("app.services.planta_service.extrair_textos", return_value=[]):
        r = client.post(
            "/api/v1/planta/analisar",
            files={"arquivo": ("planta.png", png_simples, "image/png")},
        )
    assert r.status_code == 200
    assert r.json()["arquivo"] == "planta.png"


def test_ocr_com_falha_gera_aviso(client, png_simples):
    """Erros de OCR não devem derrubar a requisição — geram aviso no resultado."""
    with patch(
        "app.services.planta_service.extrair_textos",
        side_effect=RuntimeError("modelo OCR indisponível"),
    ):
        r = client.post(
            "/api/v1/planta/analisar",
            files={"arquivo": ("planta.png", png_simples, "image/png")},
        )
    assert r.status_code == 200
    plantas = r.json()["plantas"]
    assert any("OCR" in a for p in plantas for a in p["avisos"])


def test_cache_segunda_chamada(client, pdf_planta):
    with patch("app.services.planta_service.extrair_textos", return_value=[]) as mock_ocr:
        for _ in range(2):
            r = client.post(
                "/api/v1/planta/analisar",
                files={"arquivo": ("planta.pdf", pdf_planta, "application/pdf")},
            )
            assert r.status_code == 200
    # OCR roda apenas na primeira chamada; a segunda vem do cache
    assert mock_ocr.call_count <= 1
