"""Motor de OCR: EasyOCR como principal, Tesseract como fallback.

As importações são preguiçosas (lazy) para que a API suba mesmo sem os
modelos de OCR instalados — os endpoints retornam erro claro nesse caso.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.config.settings import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

_easyocr_reader: Any = None
_easyocr_falhou = False


@dataclass
class TextoDetectado:
    texto: str
    confianca: float
    bbox: list[float]  # [x0, y0, x1, y1]

    @property
    def centro(self) -> tuple[float, float]:
        return ((self.bbox[0] + self.bbox[2]) / 2, (self.bbox[1] + self.bbox[3]) / 2)

    @property
    def largura(self) -> float:
        return self.bbox[2] - self.bbox[0]

    @property
    def altura(self) -> float:
        return self.bbox[3] - self.bbox[1]


def _get_easyocr():
    global _easyocr_reader, _easyocr_falhou
    if _easyocr_reader is not None or _easyocr_falhou:
        return _easyocr_reader
    try:
        import easyocr

        settings = get_settings()
        _easyocr_reader = easyocr.Reader(settings.ocr_languages, gpu=False)
        logger.info("EasyOCR inicializado com idiomas %s", settings.ocr_languages)
    except Exception as exc:  # pragma: no cover - depende do ambiente
        logger.warning("EasyOCR indisponível (%s); usando fallback Tesseract.", exc)
        _easyocr_falhou = True
    return _easyocr_reader


def _ocr_tesseract(imagem) -> list[TextoDetectado]:
    """Fallback com Tesseract via pytesseract."""
    import pytesseract
    from pytesseract import Output

    dados = pytesseract.image_to_data(imagem, lang="por+eng", output_type=Output.DICT)
    resultados: list[TextoDetectado] = []
    for i, texto in enumerate(dados["text"]):
        texto = texto.strip()
        conf = float(dados["conf"][i])
        if not texto or conf < 0:
            continue
        x, y, w, h = (dados[k][i] for k in ("left", "top", "width", "height"))
        resultados.append(
            TextoDetectado(texto=texto, confianca=conf / 100.0, bbox=[x, y, x + w, y + h])
        )
    return resultados


def extrair_textos(imagem) -> list[TextoDetectado]:
    """Extrai textos de uma imagem (numpy array BGR ou RGB).

    Tenta EasyOCR; se indisponível, usa Tesseract.
    """
    settings = get_settings()
    reader = _get_easyocr()

    resultados: list[TextoDetectado] = []
    if reader is not None:
        for bbox, texto, conf in reader.readtext(imagem):
            xs = [p[0] for p in bbox]
            ys = [p[1] for p in bbox]
            resultados.append(
                TextoDetectado(
                    texto=texto.strip(),
                    confianca=float(conf),
                    bbox=[min(xs), min(ys), max(xs), max(ys)],
                )
            )
    else:
        resultados = _ocr_tesseract(imagem)

    return [r for r in resultados if r.confianca >= settings.ocr_min_confidence and r.texto]


# ---------------------------------------------------------------------------
# Correção de erros comuns de OCR em cotas numéricas
# ---------------------------------------------------------------------------

_SUBSTITUICOES_NUMERICAS = str.maketrans(
    {
        "O": "0", "o": "0", "Q": "0", "D": "0",
        "l": "1", "I": "1", "|": "1", "i": "1",
        "Z": "2", "z": "2",
        "S": "5", "s": "5",
        "B": "8",
        "g": "9",
        ",": ".",
    }
)

_RE_NUMERO = re.compile(r"^\d+(?:\.\d+)?$")


def corrigir_numero_ocr(texto: str) -> str | None:
    """Tenta transformar um texto de OCR em número de cota válido.

    Corrige trocas típicas (O→0, l→1, vírgula→ponto) e remove ruído nas bordas.
    Retorna a string numérica corrigida ou None se irrecuperável.
    """
    t = texto.strip()
    # Remove unidades e símbolos comuns em cotas: "3,50m", "350 cm", "12.50 M"
    t = re.sub(r"\s*(m|M|cm|CM|mm|MM)\.?$", "", t).strip()
    t = t.strip("()[]{}<>-–—_~*'\" ")
    if not t:
        return None
    t = t.translate(_SUBSTITUICOES_NUMERICAS)
    # Mantém apenas dígitos e pontos; se sobrar lixo no meio, descarta
    if not _RE_NUMERO.match(t):
        # Última tentativa: extrair primeiro número presente
        m = re.search(r"\d+(?:\.\d+)?", t)
        if m and len(m.group(0)) >= max(1, len(t) - 2):
            t = m.group(0)
        else:
            return None
    # Normaliza múltiplos pontos ("12.50.0" → inválido)
    if t.count(".") > 1:
        return None
    return t


def interpretar_cota_metros(texto: str) -> float | None:
    """Converte texto de cota para metros.

    Heurística brasileira: cotas em plantas residenciais geralmente estão em
    centímetros quando inteiras e grandes (ex.: '350' → 3,50 m) ou já em metros
    quando têm casas decimais (ex.: '3.50').
    """
    corrigido = corrigir_numero_ocr(texto)
    if corrigido is None:
        return None
    try:
        valor = float(corrigido)
    except ValueError:
        return None

    if valor <= 0:
        return None

    if "." in corrigido:
        # Já em metros (ex.: 3.50, 12.40)
        return valor if valor < 200 else None
    # Inteiro: decidir entre cm e m
    if valor >= 100:  # 350 → 3,50 m
        metros = valor / 100.0
        return metros if metros < 200 else None
    if valor <= 60:  # 12 → provavelmente 12 m (cota de terreno)
        return float(valor)
    return None
