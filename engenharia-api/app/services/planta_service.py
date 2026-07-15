"""Serviço de análise de plantas baixas.

Combina texto vetorial (PDF), OCR e visão computacional para identificar:
frente, fundos, laterais, área construída, escala, cotas, ambientes e pavimentos.
"""
from __future__ import annotations

import asyncio
import re
import time
import unicodedata

from app.ocr.engine import TextoDetectado, extrair_textos, interpretar_cota_metros
from app.schemas.planta import Ambiente, Cota, PlantaAnalise, PlantaResponse
from app.utils.logging import get_logger
from app.vision.documento import Pagina, carregar_paginas
from app.vision.planta_vision import analisar_planta

logger = get_logger(__name__)

RE_ESCALA = re.compile(r"(?:ESC(?:ALA)?\.?\s*[:\-]?\s*)?(1\s*[:/]\s*\d{2,4})", re.IGNORECASE)
RE_AREA = re.compile(
    r"(?:ÁREA|AREA)\s*(?:CONSTRU[IÍ]DA|TOTAL)?\s*[:\-=]?\s*(\d+[.,]\d{1,2})\s*m?[²2]?",
    re.IGNORECASE,
)
RE_AREA_AMBIENTE = re.compile(r"(\d+[.,]\d{1,2})\s*m?[²2]", re.IGNORECASE)
RE_PAVIMENTO = re.compile(
    r"(T[ÉE]RREO|SUPERIOR|1[ºo°]?\s*PAV|2[ºo°]?\s*PAV|3[ºo°]?\s*PAV|SUBSOLO|COBERTURA|MEZANINO)",
    re.IGNORECASE,
)

AMBIENTES_CONHECIDOS = [
    "sala", "sala de estar", "sala de jantar", "sala de tv", "cozinha", "copa",
    "quarto", "dormitorio", "suite", "banheiro", "banho", "wc", "lavabo",
    "area de servico", "servico", "lavanderia", "garagem", "varanda", "sacada",
    "terraco", "corredor", "hall", "escritorio", "despensa", "closet",
    "area gourmet", "churrasqueira", "piscina", "deposito", "quintal", "jardim",
]


def _normalizar(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c)).strip()


async def analisar_arquivo(conteudo: bytes, tipo: str, nome_arquivo: str) -> PlantaResponse:
    """Ponto de entrada assíncrono: processa cada página em thread separada."""
    inicio = time.perf_counter()

    paginas = await asyncio.to_thread(carregar_paginas, conteudo, tipo)
    analises = await asyncio.gather(
        *(asyncio.to_thread(_analisar_pagina, p) for p in paginas)
    )

    plantas = [a for a in analises if a is not None]
    if not plantas:
        plantas = [
            PlantaAnalise(avisos=["Nenhuma planta identificável foi encontrada no arquivo."])
        ]

    return PlantaResponse(
        arquivo=nome_arquivo,
        total_plantas=len(plantas),
        plantas=plantas,
        tempo_processamento_s=round(time.perf_counter() - inicio, 3),
    )


def _analisar_pagina(pagina: Pagina) -> PlantaAnalise | None:
    avisos: list[str] = []

    # 1. OCR + texto vetorial
    try:
        textos = extrair_textos(pagina.imagem)
    except Exception as exc:
        logger.exception("Falha no OCR da página %d", pagina.numero)
        textos = []
        avisos.append(f"OCR indisponível ou falhou: {exc}")

    texto_completo = pagina.texto_vetorial + "\n" + "\n".join(t.texto for t in textos)

    # Página sem qualquer conteúdo textual/visual relevante (e sem falhas a reportar)
    if not texto_completo.strip() and not textos and not avisos:
        return None

    # 2. Visão computacional
    try:
        visao = analisar_planta(pagina.imagem)
    except Exception as exc:
        logger.exception("Falha na análise visual da página %d", pagina.numero)
        visao = None
        avisos.append(f"Análise visual falhou: {exc}")

    # 3. Cotas: números detectados pelo OCR classificados por orientação
    cotas = _extrair_cotas(textos)
    if not cotas:
        avisos.append("Nenhuma cota numérica foi identificada com confiança suficiente.")

    # 4. Medidas perimetrais (frente/fundos/laterais)
    frente, fundos, lat_dir, lat_esq = _inferir_perimetro(cotas, visao, avisos)

    # 5. Escala, área construída, pavimentos, ambientes
    escala = _extrair_escala(texto_completo)
    area_construida = _extrair_area_construida(texto_completo)
    pavimentos = _contar_pavimentos(texto_completo)
    ambientes = _extrair_ambientes(textos, pagina)

    if area_construida is None and frente and lat_dir:
        area_construida = round(frente * lat_dir, 2)
        avisos.append("Área construída estimada pelo produto frente × lateral (não informada no desenho).")

    return PlantaAnalise(
        frente=frente,
        fundos=fundos,
        lateral_direita=lat_dir,
        lateral_esquerda=lat_esq,
        area_construida=area_construida,
        escala=escala,
        pavimentos=pavimentos,
        cotas=cotas,
        ambientes=ambientes,
        avisos=avisos,
    )


def _extrair_cotas(textos: list[TextoDetectado]) -> list[Cota]:
    cotas: list[Cota] = []
    for t in textos:
        valor = interpretar_cota_metros(t.texto)
        if valor is None:
            continue
        # Orientação inferida pela forma do bounding box do texto
        if t.altura > t.largura * 1.4:
            orientacao = "vertical"
        elif t.largura > t.altura * 1.2:
            orientacao = "horizontal"
        else:
            orientacao = "desconhecida"
        cotas.append(
            Cota(
                valor=valor,
                texto_original=t.texto,
                orientacao=orientacao,
                confianca=round(t.confianca, 3),
                posicao=[round(v, 1) for v in t.bbox],
            )
        )
    return _remover_duplicadas(cotas)


def _remover_duplicadas(cotas: list[Cota]) -> list[Cota]:
    """Valida medidas duplicadas: mantém a de maior confiança para posições próximas."""
    unicas: list[Cota] = []
    for c in sorted(cotas, key=lambda c: -c.confianca):
        duplicada = False
        for u in unicas:
            if c.posicao and u.posicao:
                dist = abs(c.posicao[0] - u.posicao[0]) + abs(c.posicao[1] - u.posicao[1])
                if c.valor == u.valor and dist < 30:
                    duplicada = True
                    break
        if not duplicada:
            unicas.append(c)
    return unicas


def _inferir_perimetro(
    cotas: list[Cota], visao, avisos: list[str]
) -> tuple[float | None, float | None, float | None, float | None]:
    """Seleciona as cotas perimetrais da edificação.

    Convenção adotada: frente = cota horizontal mais abaixo do desenho
    (fachada principal voltada para a rua), fundos = horizontal mais acima,
    laterais = cotas verticais nas extremidades esquerda/direita.
    """
    horizontais = [c for c in cotas if c.orientacao == "horizontal" and c.posicao]
    verticais = [c for c in cotas if c.orientacao == "vertical" and c.posicao]

    contorno = visao.contorno_edificacao if visao else None

    def _perto_da_borda(cota: Cota, indice_eixo: int, alvo: float, tolerancia: float) -> bool:
        centro = (cota.posicao[indice_eixo] + cota.posicao[indice_eixo + 2]) / 2
        return abs(centro - alvo) <= tolerancia

    frente = fundos = lat_dir = lat_esq = None

    if contorno:
        x0, y0, x1, y1 = contorno
        tol_y = (y1 - y0) * 0.35
        tol_x = (x1 - x0) * 0.35

        inferiores = [c for c in horizontais if _perto_da_borda(c, 1, y1, tol_y)]
        superiores = [c for c in horizontais if _perto_da_borda(c, 1, y0, tol_y)]
        direitas = [c for c in verticais if _perto_da_borda(c, 0, x1, tol_x)]
        esquerdas = [c for c in verticais if _perto_da_borda(c, 0, x0, tol_x)]

        frente = max((c.valor for c in inferiores), default=None)
        fundos = max((c.valor for c in superiores), default=None)
        lat_dir = max((c.valor for c in direitas), default=None)
        lat_esq = max((c.valor for c in esquerdas), default=None)

    # Fallback sem contorno: maiores cotas de cada orientação
    if frente is None and horizontais:
        valores_h = sorted({c.valor for c in horizontais}, reverse=True)
        frente = valores_h[0]
        fundos = fundos or (valores_h[1] if len(valores_h) > 1 else valores_h[0])
        avisos.append("Frente/fundos inferidos pelas maiores cotas horizontais (contorno não detectado).")
    if lat_dir is None and verticais:
        valores_v = sorted({c.valor for c in verticais}, reverse=True)
        lat_dir = valores_v[0]
        lat_esq = lat_esq or (valores_v[1] if len(valores_v) > 1 else valores_v[0])
        avisos.append("Laterais inferidas pelas maiores cotas verticais (contorno não detectado).")

    return frente, fundos, lat_dir, lat_esq


def _extrair_escala(texto: str) -> str | None:
    m = RE_ESCALA.search(texto)
    if m:
        return re.sub(r"\s", "", m.group(1)).replace("/", ":")
    return None


def _extrair_area_construida(texto: str) -> float | None:
    m = RE_AREA.search(texto)
    if m:
        return float(m.group(1).replace(",", "."))
    return None


def _contar_pavimentos(texto: str) -> int | None:
    encontrados = {m.group(1).upper().strip() for m in RE_PAVIMENTO.finditer(texto)}
    return len(encontrados) or None


def _extrair_ambientes(textos: list[TextoDetectado], pagina: Pagina) -> list[Ambiente]:
    ambientes: dict[str, Ambiente] = {}
    fontes = [(t.texto, t.confianca, t.bbox) for t in textos]
    # Também considera texto vetorial do PDF, linha a linha
    fontes += [(linha, 1.0, None) for linha in pagina.texto_vetorial.splitlines() if linha.strip()]

    for texto, conf, _bbox in fontes:
        norm = _normalizar(texto)
        for nome in AMBIENTES_CONHECIDOS:
            if re.search(rf"\b{re.escape(nome)}\b", norm):
                chave = nome
                area = None
                m = RE_AREA_AMBIENTE.search(texto)
                if m:
                    area = float(m.group(1).replace(",", "."))
                existente = ambientes.get(chave)
                if existente is None or (area and existente.area is None):
                    ambientes[chave] = Ambiente(
                        nome=nome.title(), area=area, confianca=round(conf, 3)
                    )
    return list(ambientes.values())
