"""Testes do módulo de Sondagem SPT."""
from app.services.sondagem_service import _interpretar_furos, normalizar_solo


def test_upload_pdf_sondagem(client, pdf_sondagem):
    r = client.post(
        "/api/v1/sondagem/analisar",
        files={"arquivo": ("sondagem.pdf", pdf_sondagem, "application/pdf")},
    )
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["total_furos"] == 1
    furo = corpo["furos"][0]
    assert furo["furo"] == "SP-01"
    assert furo["nivel_agua"] == 3.20
    assert furo["presenca_agua"] is True
    assert furo["profundidade_total"] == 18.0
    assert len(furo["camadas"]) == 4


def test_leitura_correta_nspt(client, pdf_sondagem):
    r = client.post(
        "/api/v1/sondagem/analisar",
        files={"arquivo": ("sondagem.pdf", pdf_sondagem, "application/pdf")},
    )
    camadas = r.json()["furos"][0]["camadas"]
    nspts = {(c["inicio"], c["fim"]): c["nspt"] for c in camadas}
    assert nspts[(0.0, 2.0)] == 3
    assert nspts[(2.0, 5.0)] == 8
    assert nspts[(5.0, 12.0)] == 22
    assert nspts[(12.0, 18.0)] == 35


def test_classificacao_solo_com_variacoes():
    assert normalizar_solo("ARGILA SILTOSA MOLE CINZA") == "argila"
    assert normalizar_solo("areia fina a média, fofa") == "areia"
    assert normalizar_solo("Silte argiloso rijo") == "silte"
    assert normalizar_solo("solo residual de gnaisse") == "solo residual"
    assert normalizar_solo("material laterítico compacto") == "solo lateritico"
    assert normalizar_solo("turfa preta") == "solo organico"
    assert normalizar_solo("pedregulho com seixos") == "pedregulho"


def test_multiplos_furos():
    texto = (
        "SP-01\n0,00 a 3,00 - Argila mole - NSPT: 4\n"
        "SP-02\n0,00 a 2,50 - Areia compacta - NSPT: 20\n"
    )
    furos = _interpretar_furos(texto)
    assert [f.furo for f in furos] == ["SP-01", "SP-02"]
    assert furos[0].camadas[0].solo_normalizado == "argila"
    assert furos[1].camadas[0].nspt == 20


def test_agua_nao_encontrada():
    texto = "FURO 1\nN.A. não encontrado\n0,00 a 5,00 - Areia seca - NSPT: 12\n"
    furos = _interpretar_furos(texto)
    assert furos[0].presenca_agua is False
    assert furos[0].nivel_agua is None
