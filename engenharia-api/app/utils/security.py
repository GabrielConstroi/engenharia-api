"""Autenticação JWT opcional (ativada via API_JWT_ENABLED=true)."""
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config.settings import get_settings

_bearer = HTTPBearer(auto_error=False)


def criar_token(sub: str) -> str:
    import jwt  # PyJWT

    settings = get_settings()
    payload = {
        "sub": sub,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expiration_minutes),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


async def verificar_token(
    credenciais: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str | None:
    """Dependência de autenticação. Se JWT estiver desativado, permite acesso livre."""
    settings = get_settings()
    if not settings.jwt_enabled:
        return None

    if credenciais is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticação ausente.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    import jwt

    try:
        payload = jwt.decode(
            credenciais.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        return payload.get("sub")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token expirado.")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token inválido.")
