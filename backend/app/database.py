"""
database.py — Configuración de SQLAlchemy ORM + SQLite.

Patrón del curso Python para APIs e IA (Semana 7):
  - Motor SQLite embebido (cero configuración, ideal para el proyecto).
  - SessionLocal crea sesiones por request, cerradas automáticamente.
  - get_db() como generador inyectable con Depends().

Migración futura:
  Para producción basta con cambiar DATABASE_URL a PostgreSQL
  sin modificar ningún modelo ORM ni ruta.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import get_settings

settings = get_settings()

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=False,  # Cambiar a True para ver SQL en consola (debug)
)

# ── Session factory ───────────────────────────────────
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# ── Base declarativa para modelos ORM ─────────────────
Base = declarative_base()


def get_db():
    """
    Generador que provee una sesión de BD por request.

    El bloque try/finally garantiza que la sesión se cierra
    incluso si el endpoint lanza una excepción.

    Uso con FastAPI:
        @app.get("/ejemplo")
        async def endpoint(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
