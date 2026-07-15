"""Serviço de interpretação de relatórios de sondagem SPT.

Extrai furos, camadas, NSPT, tipo de solo, umidade e nível d'água a partir de
texto vetorial (PDF) ou OCR (PDF digitalizado / imagem).
"""
from __future__ import annotations

import asyncio
import re
import time
import unicodedata

from app.ocr.engine import extrair_textos
from app.schemas.sondagem import CamadaSolo, FuroSondagem, SondagemResponse
from app.utils.logging import get_logger
from app.vision.documento import Pagina, carregar_paginas

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Classificação de solos — tolerante a variações de nomenclatura
# ---------------------------------------------------------------------------
CATEGORIAS_SOLO: dict[str, list[str]] = {
    "argila": ["argila", "argiloso", "argilosa", "argilo"],
    "areia": ["areia", "arenoso", "arenosa", "areno"],
    "silte": ["silte", "siltoso", "siltosa", "silto"],
    "pedregulho": ["pedregulho", "cascalho", "seixo", "pedra"],
    "rocha": ["rocha", "rochoso", "alterada", "sa", "impenetravel"],
    "solo residual": ["residual", "saprolito", "saprolitico"],
    "solo lateritico": ["lateritico", "laterita", "lateritica"],
    "solo organico": ["organico", "organica", "turfa", "materia organica"],
    "aterro": ["aterro", "entulho"],
}

CONSISTENCIAS = [
    "muito mole", "mole", "media", "médio", "rija", "rijo", "dura", "duro",
    "fofa", "fofo", "pouco compacta", "medianamente compacta", "compacta",
    "muito compacta",
]

RE_FURO = re.compile(r"\b(SP|SPT|SM|F|FURO)\s*[-.\s]?\s*(\d{1,3})\b", re.IGNORECASE)
RE_NIVEL_AGUA = re.compile(
    r"(?:N\.?\s*A\.?|N[ÍI]VEL\s+D?[' ]?[ÁA]GUA|LEN[ÇC]OL\s+FRE[ÁA]TICO)"
    r"\s*[:=\-]?\s*(\d{1,2}[.,]\d{1,2})",
    re.IGNORECASE,
)
RE_AGUA_NAO_ENCONTRADA = re.compile(
    r"(?:N\.?A\.?|[ÁA]GUA)\s*(?:N[ÃA]O\s+(?:ENCONTRAD[OA]|ATINGID[OA])|AUSENTE|SECO)",
    re.IGNORECASE,
)
RE_PROF_TOTAL = re.compile(
    r"PROF(?:UNDIDADE)?\.?\s*(?:TOTAL|FINAL|ATINGIDA)?\s*[:=\-]?\s*(\d{1,2}[.,]\d{1,2})",
    re.IGNORECASE,
)
RE_INTERVALO = re.compile(r"(\d{1,2}[.,]\d{1,2})\s*(?:a|à|-|—|até)\s*(\d{1,2}[.,]\d{1,2})")
RE_NSPT_LINHA = re.compile(r"\b(\d{1,2})\s*/\s*(\d{2})\b")  # ex.: 8/30 (golpes/cm)
RE_UMIDADE = re.compile(
    r"\b(sec[oa]|muito [úu]mid[oa]|pouco [úu]mid[oa]|[úu]mid[oa]|saturad[oa]|molhad[oa])\b",
    re.IGNORECASE,
)


def _normalizar(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalizar_solo(descricao: str) -> str:
    """Mapeia descrições variadas para uma categoria padronizada.

    'Argila siltosa mole' → 'argila'; 'AREIA FINA CINZA' → 'areia'.
    A primeira categoria encontrada na descrição define o solo predominante.
    """
    norm = _normalizar(descricao)
    melhor: tuple[int, str] | None = None
    for categoria, termos in CATEGORIAS_SOLO.items():
        for termo in termos:
            pos = norm.find(termo)
            if pos >= 0 and (melhor is None or pos < melhor[0]):
                melhor = (pos, categoria)
    return melhor[1] if melhor else "nao classificado"


async def analisar_arquivo(conteudo: bytes, tipo: str, nome_arquivo: str) -> SondagemResponse:
    inicio = time.perf_counter()

    paginas = await asyncio.to_thread(carregar_paginas, conteudo, tipo)
    textos_paginas = await asyncio.gather(
        *(asyncio.to_thread(_texto_da_pagina, p) for p in paginas)
    )

    furos = _interpretar_furos("\n".join(textos_paginas))

    return SondagemResponse(
        arquivo=nome_arquivo,
        total_furos=len(furos),
        furos=furos,
        tempo_processamento_s=round(time.perf_counter() - inicio, 3),
    )


def _texto_da_pagina(pagina: Pagina) -> str:
    """Prefere texto vetorial; recorre ao OCR quando o PDF é digitalizado."""
    if len(pagina.texto_vetorial.strip()) > 50:
        return pagina.texto_vetorial
    try:
        detectados = extrair_textos(pagina.imagem)
        # Ordena pela posição vertical e depois horizontal para reconstruir linhas
        detectados.sort(key=lambda t: (round(t.centro[1] / 15), t.centro[0]))
        linhas: list[str] = []
        ultima_y = None
        atual: list[str] = []
        for t in detectados:
            y = round(t.centro[1] / 15)
            if ultima_y is not None and y != ultima_y:
                linhas.append(" ".join(atual))
                atual = []
            atual.append(t.texto)
            ultima_y = y
        if atual:
            linhas.append(" ".join(atual))
        return "\n".join(linhas)
    except Exception as exc:
        logger.exception("OCR falhou na página %d da sondagem", pagina.numero)
        return ""


def _interpretar_furos(texto: str) -> list[FuroSondagem]:
    """Divide o texto por furos e interpreta cada bloco."""
    posicoes: list[tuple[int, str]] = []
    for m in RE_FURO.finditer(texto):
        prefixo = m.group(1).upper()
        if prefixo == "FURO":
            prefixo = "SP"
        nome = f"{prefixo}-{int(m.group(2)):02d}"
        posicoes.append((m.start(), nome))

    if not posicoes:
        furo = _interpretar_bloco(texto, "SP-01")
        furo.avisos.append("Identificação do furo não encontrada; assumido SP-01.")
        return [furo]

    # Remove repetições consecutivas do mesmo furo (cabeçalho repetido por página)
    blocos: list[tuple[str, int, int]] = []
    for i, (inicio, nome) in enumerate(posicoes):
        fim = posicoes[i + 1][0] if i + 1 < len(posicoes) else len(texto)
        if blocos and blocos[-1][0] == nome:
            blocos[-1] = (nome, blocos[-1][1], fim)
        else:
            blocos.append((nome, inicio, fim))

    return [_interpretar_bloco(texto[i:f], nome) for nome, i, f in blocos]


def _interpretar_bloco(texto: str, nome_furo: str) -> FuroSondagem:
    avisos: list[str] = []

    # Nível d'água
    nivel_agua = None
    presenca_agua = False
    m = RE_NIVEL_AGUA.search(texto)
    if m:
        nivel_agua = float(m.group(1).replace(",", "."))
        presenca_agua = True
    elif RE_AGUA_NAO_ENCONTRADA.search(texto):
        presenca_agua = False
    else:
        avisos.append("Informação sobre nível d'água não localizada.")

    camadas = _extrair_camadas(texto)
    nspt_por_metro = _extrair_nspt_por_metro(texto)

    # Preenche NSPT das camadas com a média dos valores por metro dentro do intervalo
    for camada in camadas:
        if camada.nspt is None and nspt_por_metro:
            valores = [
                v for prof, v in nspt_por_metro.items()
                if camada.inicio < float(prof) <= camada.fim
            ]
            if valores:
                camada.nspt = round(sum(valores) / len(valores))

    profundidade_total = None
    m = RE_PROF_TOTAL.search(texto)
    if m:
        profundidade_total = float(m.group(1).replace(",", "."))
    elif camadas:
        profundidade_total = max(c.fim for c in camadas)
        avisos.append("Profundidade total inferida pela última camada.")

    if not camadas:
        avisos.append("Nenhuma camada de solo pôde ser interpretada neste furo.")

    return FuroSondagem(
        furo=nome_furo,
        profundidade_inicial=min((c.inicio for c in camadas), default=0.0),
        profundidade_total=profundidade_total,
        nivel_agua=nivel_agua,
        presenca_agua=presenca_agua,
        camadas=camadas,
        nspt_por_metro=nspt_por_metro,
        avisos=avisos,
    )


def _extrair_camadas(texto: str) -> list[CamadaSolo]:
    camadas: list[CamadaSolo] = []
    for linha in texto.splitlines():
        m = RE_INTERVALO.search(linha)
        if not m:
            continue
        inicio = float(m.group(1).replace(",", "."))
        fim = float(m.group(2).replace(",", "."))
        if fim <= inicio or fim > 60:
            continue

        categoria = normalizar_solo(linha)
        if categoria == "nao classificado" and not any(
            t in _normalizar(linha) for termos in CATEGORIAS_SOLO.values() for t in termos
        ):
            # Linha com intervalo mas sem descrição de solo: pode ser cabeçalho
            if len(linha.strip()) < 15:
                continue

        # Descrição = linha sem o intervalo numérico
        descricao = RE_INTERVALO.sub("", linha).strip(" -–—:|\t")
        # NSPT explícito no fim da linha (número inteiro isolado)
        nspt = None
        m_nspt = re.search(r"(?:NSPT|N)\s*[:=]?\s*(\d{1,2})\b|\b(\d{1,2})\s*$", descricao)
        if m_nspt:
            valor = m_nspt.group(1) or m_nspt.group(2)
            if valor and 0 < int(valor) <= 60:
                nspt = int(valor)
                descricao = descricao[: m_nspt.start()].strip(" -–—:|\t")

        m_umid = RE_UMIDADE.search(linha)
        umidade = m_umid.group(1).lower() if m_umid else None

        solo_legivel = _titulo_solo(descricao) or categoria.title()

        camadas.append(
            CamadaSolo(
                inicio=inicio,
                fim=fim,
                solo=solo_legivel,
                solo_normalizado=categoria,
                nspt=nspt,
                umidade=umidade,
                descricao_original=linha.strip(),
            )
        )

    # Ordena e mescla camadas contíguas idênticas
    camadas.sort(key=lambda c: c.inicio)
    mescladas: list[CamadaSolo] = []
    for c in camadas:
        if (
            mescladas
            and mescladas[-1].solo_normalizado == c.solo_normalizado
            and abs(mescladas[-1].fim - c.inicio) < 0.05
            and mescladas[-1].nspt == c.nspt
        ):
            mescladas[-1].fim = c.fim
        else:
            mescladas.append(c)
    return mescladas


def _titulo_solo(descricao: str) -> str | None:
    """Extrai uma descrição curta e legível, ex.: 'Argila Mole', 'Silte Arenoso'."""
    norm = _normalizar(descricao)
    partes: list[str] = []
    categoria = normalizar_solo(descricao)
    if categoria != "nao classificado":
        partes.append(categoria)
    # Textura secundária (siltoso, arenoso, argiloso)
    for sufixo in ("siltoso", "siltosa", "arenoso", "arenosa", "argiloso", "argilosa"):
        if sufixo in norm and sufixo[:5] != categoria[:5]:
            partes.append(sufixo)
            break
    for cons in sorted(CONSISTENCIAS, key=len, reverse=True):
        if _normalizar(cons) in norm:
            partes.append(cons)
            break
    return " ".join(p.title() for p in partes) if partes else None


def _extrair_nspt_por_metro(texto: str) -> dict[str, int]:
    """Captura pares profundidade → golpes, ex.: '1,00  5' ou tabelas '2.00 - 8'."""
    resultado: dict[str, int] = {}
    padrao = re.compile(r"^\s*(\d{1,2}[.,]00)\s*[-|:\t ]\s*(\d{1,2})\s*$")
    for linha in texto.splitlines():
        m = padrao.match(linha)
        if m:
            prof = m.group(1).replace(",", ".")
            golpes = int(m.group(2))
            if 0 < golpes <= 60:
                resultado[prof] = golpes
    return resultado
