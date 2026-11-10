"""Reglas sobre los metadatos del conjunto (ERR001, ERR002, ERR003, ERR008_3, ERR014, ERR017)."""
from __future__ import annotations

import re
from datetime import UTC, datetime

import pandas as pd

from ..modelos import Hallazgo, MetadatosDCAT
from ..util import hallazgo, sin_tildes

VIGENCIA = re.compile(r"\b(19|20)\d{2}\b")
CARACTER_EXTRANO = re.compile(r"[^\w\s.,:;()¿?¡!/&%°-]|_")
SIGLA = re.compile(r"\b[A-ZÁÉÍÓÚÑ]{2,6}\b")
ROMANOS = {"II", "III", "IV", "VI", "VII", "VIII", "IX", "XI", "XII"}
DOMINIOS_PERSONALES = {"gmail.com", "hotmail.com", "outlook.com", "outlook.es", "yahoo.com", "yahoo.es",
                       "live.com", "icloud.com", "hotmail.es", "msn.com", "protonmail.com"}
INSTITUCION = re.compile(
    r"alcaldia|ministerio|universidad|secretaria|instituto|gobernacion|departamento|agencia|unidad|facultad|"
    r"superintendencia|corporacion|empresa|direccion|oficina|contraloria|procuraduria|fiscalia|concejo|"
    r"hospital|e\.?s\.?e|s\.?a\.?s?\b|fondo|comision|consejo|banco|registraduria|defensoria|personeria")
LICENCIA_ABIERTA = re.compile(r"cc[\s-]?(by|0)|creative commons|odbl|dominio publico|open data commons")
FRECUENCIAS = {"diaria": 1, "semanal": 7, "quincenal": 15, "mensual": 30, "bimestral": 60, "trimestral": 90,
               "cuatrimestral": 120, "semestral": 180, "anual": 365}
DESCRIPCION_MINIMA = 80        # caracteres para que la descripción dé contexto (criterio de la plataforma)
DESCRIPCION_COLUMNA_MINIMA = 15


def titulo_y_descripcion(df: pd.DataFrame, m: MetadatosDCAT) -> list[Hallazgo]:
    """ERR001: título descriptivo, sin vigencias, siglas ni caracteres especiales; con descripción."""
    problemas: list[str] = []
    titulo = m.titulo.strip()
    if len(titulo) < 10 or len(titulo.split()) < 2:
        problemas.append("es demasiado corto para describir el contenido")
    if VIGENCIA.search(titulo):
        problemas.append(f"contiene una vigencia («{VIGENCIA.search(titulo).group(0)}»)")
    if raros := sorted(set(CARACTER_EXTRANO.findall(titulo))):
        problemas.append(f"tiene caracteres especiales ({' '.join(raros)})")
    if not titulo.isupper():      # en un título todo en mayúsculas no se distinguen las siglas
        siglas = sorted({s for s in SIGLA.findall(titulo) if s not in ROMANOS})
        if siglas:
            problemas.append(f"usa siglas sin explicar ({', '.join(siglas)})")
    out = [hallazgo("ERR001", "advertencia", 2.5 * len(problemas), "metadatos: título",
                    "El título " + "; ".join(problemas) + ".")] if problemas else []
    descripcion = m.descripcion.strip()
    if not descripcion or sin_tildes(descripcion) == sin_tildes(titulo):
        out.append(hallazgo("ERR001", "advertencia", 4, "metadatos: descripción",
                            "La descripción está vacía o repite el título."))
    return out


def comprensibilidad(df: pd.DataFrame, m: MetadatosDCAT) -> list[Hallazgo]:
    """ERR017: la descripción debe dar contexto suficiente para interpretar los datos."""
    d = m.descripcion.strip()
    if d and sin_tildes(d) != sin_tildes(m.titulo) and len(d) < DESCRIPCION_MINIMA:
        return [hallazgo("ERR017", "advertencia", 2, "metadatos: descripción",
                         f"La descripción tiene {len(d)} caracteres: no alcanza a explicar qué contiene el "
                         "conjunto, de dónde viene y para qué sirve.")]
    return []


def completitud_metadatos(df: pd.DataFrame, m: MetadatosDCAT) -> list[Hallazgo]:
    """ERR002: entidad, correo, categoría (no «Otros»), frecuencia, cobertura y licencia abierta."""
    faltan = [nombre for nombre, valor in (
        ("entidad productora", m.entidad), ("correo de contacto", m.correo), ("categoría", m.categoria),
        ("frecuencia de actualización", m.frecuencia), ("cobertura geográfica", m.cobertura),
        ("licencia", m.licencia)) if not (valor or "").strip()]
    out = []
    if faltan:
        out.append(hallazgo("ERR002", "error" if len(faltan) >= 4 else "advertencia", 10 * len(faltan) / 6,
                            "metadatos", "Faltan campos de la metadata: " + ", ".join(faltan) + ".",
                            afectados=len(faltan), tasa=len(faltan) / 6))
    if m.categoria and sin_tildes(m.categoria).strip() in ("otro", "otros", "sin categoria", "ninguna"):
        out.append(hallazgo("ERR002", "advertencia", 1.5, "metadatos: categoría",
                            f"La categoría «{m.categoria}» no clasifica el conjunto en un sector."))
    if m.licencia and not LICENCIA_ABIERTA.search(sin_tildes(m.licencia)):
        out.append(hallazgo("ERR002", "advertencia", 1.5, "metadatos: licencia",
                            f"«{m.licencia}» no es una licencia abierta reconocida; el portal usa CC BY-SA 4.0."))
    return out


def publicador_institucional(df: pd.DataFrame, m: MetadatosDCAT) -> list[Hallazgo]:
    """ERR003: quien publica debe ser la entidad, con correo institucional."""
    out = []
    usuario = (m.usuario_publicador or "").strip()
    if usuario and not INSTITUCION.search(sin_tildes(usuario)) and 2 <= len(usuario.split()) <= 4 \
            and all(p[:1].isupper() for p in usuario.split()):
        out.append(hallazgo("ERR003", "advertencia", 3, "metadatos: usuario publicador",
                            "El responsable parece el nombre de una persona, no el de una entidad."))
    correo = (m.correo or "").strip().lower()
    if "@" in correo and correo.rsplit("@", 1)[1] in DOMINIOS_PERSONALES:
        out.append(hallazgo("ERR003", "advertencia", 3, "metadatos: correo",
                            "El correo de contacto es de un proveedor personal, no institucional."))
    return out


def descripcion_de_columnas(df: pd.DataFrame, m: MetadatosDCAT) -> list[Hallazgo]:
    """ERR008_3: cada columna con una descripción de al menos 15 caracteres."""
    if not len(df.columns):
        return []
    sin = [str(c) for c in df.columns
           if len((m.descripciones_columnas.get(str(c)) or "").strip()) < DESCRIPCION_COLUMNA_MINIMA]
    if not sin:
        return []
    muestra = ", ".join(sin[:8]) + ("…" if len(sin) > 8 else "")
    return [hallazgo("ERR008_3", "advertencia", 10 * len(sin) / len(df.columns), "metadatos: columnas",
                     f"{len(sin)} de {len(df.columns)} columnas no tienen una descripción de al menos "
                     f"{DESCRIPCION_COLUMNA_MINIMA} caracteres: {muestra}.",
                     afectados=len(sin), tasa=len(sin) / len(df.columns))]


def actualidad(df: pd.DataFrame, m: MetadatosDCAT) -> list[Hallazgo]:
    """ERR014: la última actualización debe respetar la frecuencia declarada."""
    dias = FRECUENCIAS.get(sin_tildes(m.frecuencia or "").strip())
    if not dias or m.ultima_actualizacion is None:
        return []
    ultima = m.ultima_actualizacion if m.ultima_actualizacion.tzinfo else m.ultima_actualizacion.replace(tzinfo=UTC)
    atraso = (datetime.now(UTC) - ultima).days
    if atraso <= dias * 1.5:
        return []
    return [hallazgo("ERR014", "advertencia", min(10.0, 3 + 2 * atraso / dias), "metadatos: frecuencia",
                     f"La frecuencia declarada es {m.frecuencia.lower()} y el conjunto lleva {atraso} días sin "
                     "actualizarse.", afectados=atraso)]


REGLAS = [titulo_y_descripcion, comprensibilidad, completitud_metadatos, publicador_institucional,
          descripcion_de_columnas, actualidad]
