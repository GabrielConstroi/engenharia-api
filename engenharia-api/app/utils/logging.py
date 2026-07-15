"""Configuração de logs estruturados."""
import logging
import sys


def configurar_logs(debug: bool = False) -> None:
    nivel = logging.DEBUG if debug else logging.INFO
    formato = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    logging.basicConfig(level=nivel, format=formato, stream=sys.stdout, force=True)
    # Reduz ruído de bibliotecas de terceiros
    for lib in ("PIL", "matplotlib", "easyocr"):
        logging.getLogger(lib).setLevel(logging.WARNING)


def get_logger(nome: str) -> logging.Logger:
    return logging.getLogger(nome)
