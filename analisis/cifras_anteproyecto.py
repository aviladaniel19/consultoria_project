"""Reproduce las cifras del planteamiento del problema del anteproyecto.

Uso:
    python analisis/cifras_anteproyecto.py            # cifras del índice, con la copia local
    python analisis/cifras_anteproyecto.py --casos    # además, DIVIPOLA y SECOP II en la API (requiere red)
    python analisis/cifras_anteproyecto.py --descargar  # guarda una copia nueva y fechada de la evaluación

La copia local es la evaluación de MinTIC con corte del 19 de diciembre de 2025, descargada el
5 de noviembre de 2026 de https://www.datos.gov.co/d/wa49-85xq (licencia CC BY-SA 4.0). Su huella
SHA-256 está junto al archivo: si no coincide, el script se detiene.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import date
from pathlib import Path

import httpx
import pandas as pd

DATOS = Path(__file__).parent / "datos"
COPIA = DATOS / "evaluacion_mintic_corte_2025-12-19.csv"
API = "https://www.datos.gov.co"
CRITERIOS = [
    "actualidad", "completitud", "credibilidad", "accesibilidad", "conformidad", "comprensibilidad",
    "exactitud", "relevancia", "portabilidad", "disponibilidad", "trazabilidad", "unicidad",
    "confidencialidad", "consistencia", "eficiencia", "precisi_n", "recuperabilidad",
]
INDICE = "ndice_global_de_calidad"
# Criterios que valen 0 a la vez en SECOP II; el patrón sugiere conjuntos que no se pudieron evaluar.
PATRON_CEROS = ["unicidad", "consistencia", "eficiencia", "precisi_n", "portabilidad", "conformidad"]


def pct(x: float, dec: int = 1) -> str:
    return f"{x * 100:.{dec}f} %".replace(".", ",")


def num(x: float, dec: int = 0) -> str:
    return f"{x:,.{dec}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def verificar_huella(ruta: Path) -> None:
    esperada = (ruta.parent / (ruta.name + ".sha256")).read_text(encoding="utf-8").split()[0]
    real = hashlib.sha256(ruta.read_bytes()).hexdigest()
    if real != esperada:
        sys.exit(f"La huella de {ruta.name} no coincide: el archivo cambió.")


def descargar() -> Path:
    destino = DATOS / f"evaluacion_mintic_descarga_{date.today():%Y-%m-%d}.csv"
    if destino.exists():
        sys.exit(f"{destino.name} ya existe; no se sobrescribe.")
    r = httpx.get(f"{API}/resource/wa49-85xq.csv", params={"$limit": 100_000}, timeout=120)
    r.raise_for_status()
    destino.write_bytes(r.content)
    huella = hashlib.sha256(r.content).hexdigest()
    (destino.parent / (destino.name + ".sha256")).write_text(f"{huella} {destino.name}\n", encoding="utf-8")
    print(f"Copia guardada en {destino} (SHA-256 {huella})")
    return destino


def cifras_indice(d: pd.DataFrame) -> None:
    print(f"Conjuntos evaluados: {num(len(d))} de {num(d['informaci_n_de_la_entidad'].nunique())} entidades")
    print(f"Cortes publicados: {d['fecha_corte'].nunique()} ({', '.join(sorted(d['fecha_corte'].str[:10].unique()))})")
    indice = d[INDICE]
    t1, t2 = indice.quantile([1 / 3, 2 / 3])
    print(f"Índice Global >= 8: {pct((indice >= 8).mean())}; terciles {num(t1, 2)} y {num(t2, 2)}")

    pocos = [c for c in CRITERIOS if d[c].nunique() <= 2]
    print(f"Criterios con dos valores o menos: {len(pocos)} de {len(CRITERIOS)} ({', '.join(pocos)})")
    for c in ("accesibilidad", "disponibilidad", "exactitud"):
        moda = d[c].mode().iloc[0]
        print(f"  {c}: vale {num(moda, 1)} en el {pct((d[c] == moda).mean())} de los conjuntos")

    ceros = (d[PATRON_CEROS] == 0).all(axis=1)
    print(f"Conjuntos con seis criterios en cero: {num(ceros.sum())} ({pct(ceros.mean())})")

    dias = d["d_as_desde_la_ltima"]
    print(f"Sin actualizar hace más de un año: {pct((dias > 365).mean())}; mediana {num(dias.median())} días")

    casos = d[d["uid"].isin(["gdxc-w37w", "p6dx-8zbt"])].set_index("uid")
    for uid, fila in casos.iterrows():
        print(f"  {fila['nombre']}: índice {num(fila[INDICE], 2)}, unicidad {num(fila['unicidad'], 1)}, "
              f"consistencia {num(fila['consistencia'], 1)}")


def casos_api() -> None:
    with httpx.Client(base_url=API, timeout=180) as http:
        meta = http.get("/api/views/gdxc-w37w.json").json()
        tipos = {c["fieldName"]: c["dataTypeName"] for c in meta["columns"]}
        muestra = http.get("/resource/gdxc-w37w.json", params={"$limit": 1}).json()[0]
        print(f"DIVIPOLA: longitud declarada como {tipos['longitud']}, ejemplo «{muestra['longitud']}»")

        dia = "fecha_de_publicacion_del between '2026-01-02T00:00:00' and '2026-01-02T23:59:59'"
        grupos = http.get("/resource/p6dx-8zbt.json", params={
            "$select": "id_del_proceso, count(*) as c", "$where": dia,
            "$group": "id_del_proceso", "$limit": 50_000}).json()
        filas = sum(int(g["c"]) for g in grupos)
        repetidos = sum(1 for g in grupos if int(g["c"]) > 1)
        print(f"SECOP II, 2 ene 2026: {num(filas)} filas, {num(len(grupos))} ids distintos "
              f"({pct(1 - len(grupos) / filas)} de filas repetidas, en {repetidos} procesos)")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--casos", action="store_true", help="consulta DIVIPOLA y SECOP II en la API")
    p.add_argument("--descargar", action="store_true", help="guarda una copia nueva y fechada")
    args = p.parse_args()

    if args.descargar:
        descargar()
    verificar_huella(COPIA)
    cifras_indice(pd.read_csv(COPIA))
    if args.casos:
        casos_api()


if __name__ == "__main__":
    main()
