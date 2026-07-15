"""Cache em memória com TTL e limite de itens (LRU simples).

Para múltiplas instâncias em produção, substitua por Redis mantendo a mesma interface.
"""
import time
from collections import OrderedDict
from threading import Lock
from typing import Any

from app.config.settings import get_settings


class TTLCache:
    def __init__(self, ttl: int, max_items: int) -> None:
        self._ttl = ttl
        self._max = max_items
        self._dados: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = Lock()

    def get(self, chave: str) -> Any | None:
        with self._lock:
            item = self._dados.get(chave)
            if item is None:
                return None
            expira, valor = item
            if time.monotonic() > expira:
                del self._dados[chave]
                return None
            self._dados.move_to_end(chave)
            return valor

    def set(self, chave: str, valor: Any) -> None:
        with self._lock:
            self._dados[chave] = (time.monotonic() + self._ttl, valor)
            self._dados.move_to_end(chave)
            while len(self._dados) > self._max:
                self._dados.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._dados.clear()


_settings = get_settings()
cache_resultados = TTLCache(_settings.cache_ttl_seconds, _settings.cache_max_items)
