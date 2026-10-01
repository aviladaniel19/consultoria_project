"""
agente_01.py — Agente de Contraste de Afirmaciones de Impacto.

Responsabilidad única:
  Recibe una afirmación de impacto (texto libre) y retorna:
    - veredicto:  SUSTENTADA | REFUTADA | SIN DATOS
    - razonamiento: explicación breve del análisis
    - fuente_url:   URL de referencia si se encuentra evidencia pública
    - confianza:    score 0.0 – 1.0

Estrategia de proveedores (fallback):
  1. Google Gemini (google-generativeai) — si GOOGLE_API_KEY está configurada
  2. Groq (langchain-groq) — si GROQ_API_KEY está configurada
  3. Modo offline/simulado — para desarrollo sin claves (devuelve análisis básico)

Patrón:
  - Prompt estructurado con instrucción de rol + afirmación + formato JSON esperado
  - Parse de la respuesta JSON del LLM
  - Fallback a modo simulado si ambas claves faltan o hay error de red

Uso:
    from app.services.agente_01 import contrastar_afirmacion
    resultado = await contrastar_afirmacion("La tasa de mortalidad infantil bajó un 30%")
"""

import json
import logging
import re
import asyncio
from typing import Optional

logger = logging.getLogger("vigia.agente_01")


# ═══════════════════════════════════════════════════════════
# PROMPT TEMPLATE
# ═══════════════════════════════════════════════════════════

SYSTEM_PROMPT = """
Eres el Agente 01 de la Red de Monitoreo Vigía — un sistema de verificación de 
afirmaciones de impacto social para proyectos de la Facultad de Estadística USTA.

Tu rol es analizar una afirmación de impacto de un proyecto social o académico y 
determinar si puede sustentarse con evidencia disponible públicamente.

Responde ÚNICAMENTE en formato JSON con esta estructura exacta:
{
  "veredicto": "SUSTENTADA" | "REFUTADA" | "SIN DATOS",
  "razonamiento": "<explicación concisa de 2-4 oraciones>",
  "fuente_url": "<URL de referencia o null si no aplica>",
  "confianza": <número entre 0.0 y 1.0>,
  "indicadores_clave": ["<indicador1>", "<indicador2>"]
}

Criterios de veredicto:
- SUSTENTADA: La afirmación es consistente con datos empíricos, teoría establecida 
  o evidencia razonable de proyectos similares.
- REFUTADA: La afirmación contradice datos conocidos, es interna o lógicamente 
  inconsistente.
- SIN DATOS: No hay suficiente información pública para evaluar la afirmación.

Sé objetivo, conciso y neutral. No inventes datos específicos. Si la afirmación 
hace referencia a un proyecto privado sin datos públicos, usa SIN DATOS con 
confianza baja (0.3-0.5).
""".strip()


USER_PROMPT_TEMPLATE = """
Analiza la siguiente afirmación de impacto de un proyecto social:

AFIRMACIÓN: {texto}

Evalúa si esta afirmación puede sustentarse con evidencia disponible y responde 
en el formato JSON indicado.
""".strip()


# ═══════════════════════════════════════════════════════════
# PARSER DE RESPUESTA LLM
# ═══════════════════════════════════════════════════════════

def _parse_llm_response(raw: str) -> dict:
    """
    Extrae el JSON de la respuesta del LLM.
    Maneja casos donde el modelo añade texto antes/después del JSON.
    """
    # Intentar extraer bloque JSON entre llaves
    match = re.search(r'\{.*?\}', raw, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            return _validate_veredicto(data)
        except json.JSONDecodeError:
            pass

    # Fallback: intentar parsear todo
    try:
        data = json.loads(raw.strip())
        return _validate_veredicto(data)
    except json.JSONDecodeError:
        logger.warning("No se pudo parsear JSON del LLM. Usando SIN DATOS.")
        return {
            "veredicto": "SIN DATOS",
            "razonamiento": "El agente no pudo procesar la respuesta correctamente.",
            "fuente_url": None,
            "confianza": 0.3,
            "indicadores_clave": [],
        }


def _validate_veredicto(data: dict) -> dict:
    """Normaliza y valida los campos del resultado."""
    veredictos_validos = {"SUSTENTADA", "REFUTADA", "SIN DATOS"}
    veredicto = str(data.get("veredicto", "SIN DATOS")).upper().strip()
    if veredicto not in veredictos_validos:
        veredicto = "SIN DATOS"

    confianza = float(data.get("confianza", 0.5))
    confianza = max(0.0, min(1.0, confianza))

    return {
        "veredicto": veredicto,
        "razonamiento": str(data.get("razonamiento", "")).strip()[:1000],
        "fuente_url": data.get("fuente_url") or None,
        "confianza": round(confianza, 3),
        "indicadores_clave": list(data.get("indicadores_clave", [])),
    }


# ═══════════════════════════════════════════════════════════
# PROVEEDOR 1: GOOGLE GEMINI
# ═══════════════════════════════════════════════════════════

async def _contrastar_con_gemini(texto: str, api_key: str) -> dict:
    """Usa google-generativeai para contrastar la afirmación."""
    try:
        import google.generativeai as genai  # type: ignore

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            system_instruction=SYSTEM_PROMPT,
        )

        prompt = USER_PROMPT_TEMPLATE.format(texto=texto)

        # Ejecutar en thread pool para no bloquear el event loop
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=0.2,
                    max_output_tokens=512,
                ),
            ),
        )

        raw_text = response.text
        logger.info(f"[Gemini] Respuesta recibida ({len(raw_text)} chars)")
        return _parse_llm_response(raw_text)

    except ImportError:
        logger.warning("google-generativeai no instalado. Intentando Groq...")
        raise
    except Exception as e:
        logger.error(f"[Gemini] Error: {e}")
        raise


# ═══════════════════════════════════════════════════════════
# PROVEEDOR 2: GROQ (langchain-groq)
# ═══════════════════════════════════════════════════════════

async def _contrastar_con_groq(texto: str, api_key: str) -> dict:
    """Usa Groq con LangChain para contrastar la afirmación."""
    try:
        from langchain_groq import ChatGroq  # type: ignore
        from langchain_core.messages import HumanMessage, SystemMessage  # type: ignore

        llm = ChatGroq(
            api_key=api_key,
            model_name="llama-3.1-8b-instant",
            temperature=0.2,
            max_tokens=512,
        )

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=USER_PROMPT_TEMPLATE.format(texto=texto)),
        ]

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: llm.invoke(messages))
        raw_text = response.content

        logger.info(f"[Groq] Respuesta recibida ({len(raw_text)} chars)")
        return _parse_llm_response(raw_text)

    except ImportError:
        logger.warning("langchain-groq no instalado.")
        raise
    except Exception as e:
        logger.error(f"[Groq] Error: {e}")
        raise


# ═══════════════════════════════════════════════════════════
# PROVEEDOR 3: MODO OFFLINE / SIMULADO
# ═══════════════════════════════════════════════════════════

def _contrastar_offline(texto: str) -> dict:
    """
    Análisis básico sin LLM.
    Usa heurísticas simples para una respuesta razonada localmente.
    Apropiado para desarrollo sin API keys.
    """
    texto_lower = texto.lower()

    # Indicadores de afirmaciones cuantificables
    tiene_numero = bool(re.search(r'\d+', texto))
    palabras_positivas = ["mejoró", "aumentó", "redujo", "logró", "alcanzó",
                          "incrementó", "superó", "benefició", "impactó"]
    palabras_negativas = ["fracasó", "empeoró", "falló", "no logró", "no cumplió"]
    palabras_vagas = ["podría", "debería", "se espera", "se estima", "aproximadamente"]

    score_positivo = sum(1 for p in palabras_positivas if p in texto_lower)
    score_negativo = sum(1 for p in palabras_negativas if p in texto_lower)
    score_vago = sum(1 for p in palabras_vagas if p in texto_lower)

    if score_negativo > score_positivo:
        veredicto = "REFUTADA"
        confianza = 0.45
        razonamiento = (
            "La afirmación contiene indicadores lingüísticos de resultado negativo o incumplimiento. "
            "Se requiere evidencia cuantitativa para una evaluación definitiva. "
            "Análisis realizado en modo offline."
        )
    elif score_vago > 1 or not tiene_numero:
        veredicto = "SIN DATOS"
        confianza = 0.35
        razonamiento = (
            "La afirmación no contiene datos cuantitativos verificables o utiliza lenguaje impreciso. "
            "No es posible contrastarla sin evidencia empírica específica. "
            "Análisis realizado en modo offline — configure GOOGLE_API_KEY o GROQ_API_KEY para análisis completo."
        )
    else:
        veredicto = "SUSTENTADA"
        confianza = 0.55
        razonamiento = (
            "La afirmación contiene indicadores cuantitativos y lenguaje de resultado verificable. "
            "Es consistente con afirmaciones típicas de proyectos sociales bien documentados. "
            "Análisis realizado en modo offline — configure GOOGLE_API_KEY o GROQ_API_KEY para análisis completo."
        )

    return {
        "veredicto": veredicto,
        "razonamiento": razonamiento,
        "fuente_url": None,
        "confianza": confianza,
        "indicadores_clave": ["análisis_heurístico", "modo_offline"],
    }


# ═══════════════════════════════════════════════════════════
# FUNCIÓN PRINCIPAL — contrastar_afirmacion()
# ═══════════════════════════════════════════════════════════

async def contrastar_afirmacion(texto: str) -> dict:
    """
    Punto de entrada principal del Agente 01.

    Args:
        texto: La afirmación de impacto a contrastar.

    Returns:
        dict con campos: veredicto, razonamiento, fuente_url, confianza, indicadores_clave
    """
    from app.config import get_settings
    settings = get_settings()

    google_key = settings.GOOGLE_API_KEY.strip()
    groq_key = settings.GROQ_API_KEY.strip()

    logger.info(f"[Agente 01] Contrastando: {texto[:80]}...")

    # Prioridad 1: Gemini
    if google_key and google_key != "tu_google_api_key":
        try:
            resultado = await _contrastar_con_gemini(texto, google_key)
            resultado["proveedor"] = "gemini"
            logger.info(f"[Agente 01] Veredicto Gemini: {resultado['veredicto']} (confianza={resultado['confianza']})")
            return resultado
        except Exception:
            logger.warning("[Agente 01] Gemini falló. Intentando Groq...")

    # Prioridad 2: Groq
    if groq_key and groq_key != "tu_groq_api_key":
        try:
            resultado = await _contrastar_con_groq(texto, groq_key)
            resultado["proveedor"] = "groq"
            logger.info(f"[Agente 01] Veredicto Groq: {resultado['veredicto']} (confianza={resultado['confianza']})")
            return resultado
        except Exception:
            logger.warning("[Agente 01] Groq falló. Usando modo offline.")

    # Prioridad 3: Modo offline
    resultado = _contrastar_offline(texto)
    resultado["proveedor"] = "offline"
    logger.info(f"[Agente 01] Veredicto Offline: {resultado['veredicto']} (confianza={resultado['confianza']})")
    return resultado
