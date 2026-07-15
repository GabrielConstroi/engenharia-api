"""Endpoints da API v1. Os endpoints apenas orquestram — a lógica vive nos services."""
from fastapi import APIRouter, Depends, File, Request, UploadFile

from app.config.settings import get_settings
from app.schemas.common import ErroResponse, StatusResponse
from app.schemas.planta import PlantaResponse
from app.schemas.sondagem import SondagemResponse
from app.services import planta_service, sondagem_service
from app.utils.cache import cache_resultados
from app.utils.files import hash_conteudo, validar_e_ler
from app.utils.limiter import limiter
from app.utils.logging import get_logger
from app.utils.security import verificar_token

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["v1"])

_RESPOSTAS_ERRO = {
    400: {"model": ErroResponse, "description": "Arquivo inválido"},
    413: {"model": ErroResponse, "description": "Arquivo muito grande"},
    415: {"model": ErroResponse, "description": "Tipo de arquivo não suportado"},
    429: {"model": ErroResponse, "description": "Limite de requisições excedido"},
}


@router.get("/status", response_model=StatusResponse, summary="Verifica se a API está online")
async def status() -> StatusResponse:
    settings = get_settings()
    return StatusResponse(
        status="online",
        versao=settings.version,
        modulos=["planta", "sondagem"],
    )


@router.post(
    "/planta/analisar",
    response_model=PlantaResponse,
    responses=_RESPOSTAS_ERRO,
    summary="Analisa uma planta baixa (PDF ou imagem)",
    description=(
        "Recebe um PDF ou imagem (PNG, JPG, TIFF) de planta arquitetônica e retorna "
        "medidas perimetrais (frente, fundos, laterais), área construída, escala, "
        "todas as cotas identificadas, ambientes e número de pavimentos. "
        "Se o PDF contiver várias plantas, todas são retornadas na lista `plantas`."
    ),
)
@limiter.limit(get_settings().rate_limit)
async def analisar_planta(
    request: Request,
    arquivo: UploadFile = File(..., description="PDF ou imagem da planta baixa"),
    _usuario: str | None = Depends(verificar_token),
) -> PlantaResponse:
    conteudo, tipo = await validar_e_ler(arquivo)

    chave = f"planta:{hash_conteudo(conteudo)}"
    em_cache = cache_resultados.get(chave)
    if em_cache is not None:
        logger.info("Planta '%s' servida do cache.", arquivo.filename)
        return em_cache

    resultado = await planta_service.analisar_arquivo(conteudo, tipo, arquivo.filename or "arquivo")
    cache_resultados.set(chave, resultado)
    return resultado


@router.post(
    "/sondagem/analisar",
    response_model=SondagemResponse,
    responses=_RESPOSTAS_ERRO,
    summary="Interpreta um relatório de sondagem SPT (PDF ou imagem)",
    description=(
        "Recebe um relatório de sondagem SPT e retorna, para cada furo: identificação, "
        "profundidades, NSPT por camada e por metro, tipo de solo normalizado, "
        "umidade, presença de água e nível do lençol freático."
    ),
)
@limiter.limit(get_settings().rate_limit)
async def analisar_sondagem(
    request: Request,
    arquivo: UploadFile = File(..., description="PDF ou imagem do relatório SPT"),
    _usuario: str | None = Depends(verificar_token),
) -> SondagemResponse:
    conteudo, tipo = await validar_e_ler(arquivo)

    chave = f"sondagem:{hash_conteudo(conteudo)}"
    em_cache = cache_resultados.get(chave)
    if em_cache is not None:
        logger.info("Sondagem '%s' servida do cache.", arquivo.filename)
        return em_cache

    resultado = await sondagem_service.analisar_arquivo(conteudo, tipo, arquivo.filename or "arquivo")
    cache_resultados.set(chave, resultado)
    return resultado
