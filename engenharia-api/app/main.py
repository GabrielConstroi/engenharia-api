"""Ponto de entrada da API.

Execução local:  uvicorn app.main:app --reload
Produção:        uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
"""
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.v1.rotas import router as router_v1
from app.config.settings import get_settings
from app.utils.limiter import limiter
from app.utils.logging import configurar_logs, get_logger

settings = get_settings()
configurar_logs(settings.debug)
logger = get_logger("app")

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description=(
        "API de leitura e interpretação de documentos de engenharia civil.\n\n"
        "**Módulo 1 — Planta Baixa:** medidas perimetrais, cotas, escala, ambientes.\n\n"
        "**Módulo 2 — Sondagem SPT:** furos, camadas, NSPT, solo e nível d'água.\n\n"
        "Documentação interativa: `/docs` (Swagger) e `/redoc`."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Rate limit
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — configurável para o domínio do GitHub Pages
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Compressão de respostas
app.add_middleware(GZipMiddleware, minimum_size=500)


@app.middleware("http")
async def log_requisicoes(request: Request, call_next):
    req_id = uuid.uuid4().hex[:8]
    inicio = time.perf_counter()
    try:
        resposta = await call_next(request)
    except Exception:
        logger.exception("[%s] Erro não tratado em %s %s", req_id, request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Erro interno ao processar a requisição.", "codigo": req_id},
        )
    duracao = (time.perf_counter() - inicio) * 1000
    logger.info(
        "[%s] %s %s → %d (%.0f ms)",
        req_id, request.method, request.url.path, resposta.status_code, duracao,
    )
    resposta.headers["X-Request-ID"] = req_id
    return resposta


app.include_router(router_v1)


@app.get("/", include_in_schema=False)
async def raiz():
    return {"api": settings.app_name, "docs": "/docs", "status": "/api/v1/status"}
