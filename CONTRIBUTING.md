# Guía de Contribución — VIGÍA API

¡Gracias por tu interés en contribuir a la Red de Monitoreo Vigía! Este documento describe cómo participar en el desarrollo del backend FastAPI del proyecto.

## Reporte de Bugs

Si encuentras un bug:

1. **Verifica que no exista ya** — Busca en [Issues](../../issues)
2. **Crea un nuevo issue** con:
   - Título claro (ej: `[BUG] POST /auth/login devuelve 500 con usuario vacío`)
   - Descripción detallada del comportamiento inesperado
   - Pasos para reproducir el error
   - Comportamiento esperado vs actual
   - Entorno: SO, versión Python, método de ejecución (local/Docker)

## Propuesta de Nuevas Características

Para sugerir una nueva característica:

1. Abre un [issue de discusión](../../issues) con el título `[FEATURE]`
2. Describe el caso de uso dentro del contexto de Vigía (monitoreo de proyectos, índices, agentes IA)
3. Espera feedback de los maintainers antes de codificar

## Flujo de Contribución

### 1. Fork y Rama

```powershell
git clone https://github.com/tu-usuario/vigia.git
cd vigia
git checkout -b feature/nombre-descriptivo
```

Convención de nombres de rama:

- `feature/agente-02-impacto` — nueva funcionalidad
- `fix/indice-veracidad-division-cero` — corrección de bug
- `docs/endpoints-datasets` — documentación

### 2. Desarrollo Local

```powershell
# Instalar dependencias del backend
cd backend
python -m venv venv
venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt

# Configurar variables de entorno
copy .env.example .env
# Editar .env con tus claves (GOOGLE_API_KEY, GROQ_API_KEY, etc.)

# Levantar la API
uvicorn app.main:app --reload --port 8000
```

Alternativamente, con Docker:

```powershell
docker-compose up -d --build
```

### 3. Estructura del Código

Antes de añadir código, respeta la arquitectura modular del proyecto:

| Qué añadir                  | Dónde va                        |
|-----------------------------|---------------------------------|
| Nuevo endpoint              | `backend/app/routers/`          |
| Nuevo schema Pydantic       | `backend/app/models/schemas.py` |
| Nuevo modelo ORM            | `backend/app/models/db_models.py` |
| Nuevo agente IA             | `backend/app/services/agente_XX.py` |
| Nuevo servicio de cálculo   | `backend/app/services/`         |

### 4. Estilo de Código

- Usa **PEP 8** para Python
- Incluye **docstrings** en funciones y clases
- Escribe **type hints** en todos los parámetros y retornos
- Comenta lógica compleja, especialmente en cálculos estadísticos

Ejemplo de endpoint bien documentado:

```python
@router.post(
    "/{proyecto_id}/afirmaciones/{afirmacion_id}/contrastar",
    response_model=ContrasteResponse,
    summary="Agente 01: Contrastar una afirmación de impacto",
)
async def contrastar_afirmacion_individual(
    proyecto_id: str,
    afirmacion_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> ContrasteResponse:
    """
    Invoca el Agente 01 para contrastar una afirmación.

    Flujo: Gemini -> Groq -> modo offline.
    Persiste el veredicto y genera alertas si aplica.
    """
    ...
```

### 5. Agentes IA

Al añadir o modificar un agente (`services/agente_XX.py`):

- Implementa el **patrón fallback**: proveedor principal → fallback → modo offline.
- El modo offline **siempre** debe retornar una respuesta válida (nunca lanzar excepción).
- Respeta los rate limits: usa `asyncio.sleep()` entre llamadas en batch.
- Registra en `AlertaLog` cuando corresponda.

### 6. Tests

- Escribe tests para nuevas funcionalidades en `backend/tests/` (crear si no existe).
- Ejecuta la suite antes de abrir el PR:

```powershell
cd backend
pytest tests/ -v
```

### 7. Commit y Push

```powershell
git add .
git commit -m "feat(afirmaciones): agregar Agente 02 para análisis de impacto"
git push origin feature/nombre-descriptivo
```

**Formato de commit** (Conventional Commits):

| Prefijo      | Cuándo usarlo                                      |
|--------------|----------------------------------------------------|
| `feat:`      | Nueva funcionalidad (endpoint, agente, índice)     |
| `fix:`       | Corrección de bug                                  |
| `docs:`      | Cambios en documentación                           |
| `refactor:`  | Refactorización sin cambios funcionales            |
| `test:`      | Agregar o actualizar tests                         |
| `chore:`     | Actualización de dependencias o configuración      |

### 8. Pull Request

1. Crea un PR desde tu rama hacia `main`
2. Describe qué cambia y por qué
3. Referencia el issue relacionado (ej: `Closes #42`)
4. Espera revisión y aplica los cambios solicitados
5. ¡Merge! 🎉

## Estándares del Proyecto

- **Python**: 3.11+
- **Framework**: FastAPI — respetar la estructura de routers y dependencias existente
- **BD**: SQLAlchemy ORM — no escribir SQL crudo salvo casos excepcionales
- **Auth**: todos los endpoints de escritura (POST/PUT/DELETE) requieren `Depends(get_current_user)`
- **Validación**: toda entrada de datos debe tener un schema Pydantic en `schemas.py`
- **Dependencias**: añadir con versión mínima en `requirements.txt` (ej: `paquete>=1.2.0`)

## Preguntas

- Abre un [Discussion](../../discussions)
- Contacta al equipo: `estadistica@usta.edu.co`

---

**¡Gracias por contribuir a la Red de Monitoreo Vigía — USTA Estadística!** 🎓
