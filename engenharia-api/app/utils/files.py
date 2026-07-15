"""Validação de arquivos enviados: tamanho, extensão e assinatura (magic bytes)."""
import hashlib

from fastapi import HTTPException, UploadFile, status

from app.config.settings import get_settings

# Assinaturas de arquivo (magic bytes) — não confiar apenas no content-type do cliente
_MAGIC_SIGNATURES: dict[str, list[bytes]] = {
    "pdf": [b"%PDF"],
    "png": [b"\x89PNG\r\n\x1a\n"],
    "jpg": [b"\xff\xd8\xff"],
    "jpeg": [b"\xff\xd8\xff"],
    "tiff": [b"II*\x00", b"MM\x00*"],
    "tif": [b"II*\x00", b"MM\x00*"],
}


def _detectar_tipo(conteudo: bytes) -> str | None:
    for ext, assinaturas in _MAGIC_SIGNATURES.items():
        if any(conteudo.startswith(a) for a in assinaturas):
            return "jpg" if ext == "jpeg" else ext
    return None


async def validar_e_ler(arquivo: UploadFile) -> tuple[bytes, str]:
    """Lê o upload validando extensão, tamanho e assinatura real.

    Retorna (conteúdo, tipo_detectado) onde tipo é 'pdf' ou uma extensão de imagem.
    """
    settings = get_settings()

    nome = arquivo.filename or "arquivo"
    ext = nome.rsplit(".", 1)[-1].lower() if "." in nome else ""
    if ext not in settings.allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Extensão '.{ext}' não suportada. Use: {', '.join(settings.allowed_extensions)}",
        )

    conteudo = await arquivo.read()

    if len(conteudo) == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Arquivo vazio.")

    if len(conteudo) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Arquivo excede o limite de {settings.max_upload_size_mb} MB.",
        )

    tipo_real = _detectar_tipo(conteudo)
    if tipo_real is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Conteúdo do arquivo não corresponde a PDF ou imagem válida.",
        )

    return conteudo, tipo_real


def hash_conteudo(conteudo: bytes) -> str:
    """SHA-256 do conteúdo — usado como chave de cache."""
    return hashlib.sha256(conteudo).hexdigest()
