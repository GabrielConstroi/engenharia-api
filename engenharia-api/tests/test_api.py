"""Testes de status, validação de upload e erros."""


def test_status(client):
    r = client.get("/api/v1/status")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["status"] == "online"
    assert "planta" in corpo["modulos"]


def test_pdf_invalido_rejeitado(client):
    """Arquivo com extensão .pdf mas conteúdo falso deve retornar 415."""
    r = client.post(
        "/api/v1/planta/analisar",
        files={"arquivo": ("falso.pdf", b"isto nao e um pdf", "application/pdf")},
    )
    assert r.status_code == 415


def test_extensao_nao_suportada(client):
    r = client.post(
        "/api/v1/planta/analisar",
        files={"arquivo": ("dados.exe", b"MZ\x90\x00", "application/octet-stream")},
    )
    assert r.status_code == 415


def test_arquivo_vazio(client):
    r = client.post(
        "/api/v1/sondagem/analisar",
        files={"arquivo": ("vazio.pdf", b"", "application/pdf")},
    )
    assert r.status_code == 400


def test_arquivo_muito_grande(client, monkeypatch):
    from app.config.settings import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "max_upload_size_mb", 0)
    conteudo = b"%PDF-1.4 " + b"x" * 1024
    r = client.post(
        "/api/v1/planta/analisar",
        files={"arquivo": ("grande.pdf", conteudo, "application/pdf")},
    )
    assert r.status_code == 413
