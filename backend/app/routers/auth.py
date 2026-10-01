"""
auth.py — Router de autenticación JWT para Vigía.

Endpoints:
  POST /auth/login   → genera access token
  GET  /auth/me      → info del usuario actual
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings, Settings
from app.models.schemas import TokenResponse

router = APIRouter(prefix="/auth", tags=["Auth"])
logger = logging.getLogger("vigia.auth")

# ── Contexto de hashing ───────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# ── Usuarios demo (en producción: tabla User en BD) ───
# Los hashes se calculan la primera vez que se necesitan (lazy)
_USUARIOS_PLAIN: dict[str, dict] = {
    "admin":   {"username": "admin",   "password": "vigia2025", "rol": "admin"},
    "monitor": {"username": "monitor", "password": "vigia2025", "rol": "lector"},
}
_USUARIOS_DEMO: dict[str, dict] | None = None


def _get_usuarios() -> dict[str, dict]:
    global _USUARIOS_DEMO
    if _USUARIOS_DEMO is None:
        _USUARIOS_DEMO = {
            u["username"]: {
                "username": u["username"],
                "hashed_password": pwd_context.hash(u["password"]),
                "rol": u["rol"],
            }
            for u in _USUARIOS_PLAIN.values()
        }
    return _USUARIOS_DEMO


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict, settings: Settings) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    settings: Settings = Depends(get_settings),
) -> dict:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido o expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str | None = payload.get("sub")
        if username is None:
            raise credentials_exc
    except JWTError:
        raise credentials_exc

    user = _get_usuarios().get(username)
    if user is None:
        raise credentials_exc
    return user


# ── Endpoints ─────────────────────────────────────────

@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Obtener token JWT",
)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    settings: Settings = Depends(get_settings),
):
    """
    Autenticación con usuario y contraseña.

    Credenciales de demo:
    - **admin** / vigia2025
    - **monitor** / vigia2025
    """
    user = _get_usuarios().get(form_data.username)
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        logger.warning(f"Intento fallido de login: usuario='{form_data.username}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token({"sub": user["username"], "rol": user["rol"]}, settings)
    logger.info(f"Login exitoso: usuario='{user['username']}'")
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get(
    "/me",
    summary="Información del usuario actual",
)
async def get_me(
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """Retorna el perfil del usuario autenticado."""
    return {
        "username": current_user["username"],
        "rol": current_user["rol"],
    }
