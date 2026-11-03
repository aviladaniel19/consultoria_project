"""Evaluación del contrato de datos declarado en el YAML de la fuente."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from ..registry.models import Check, Contract
from .profiling import as_numeric


@dataclass
class CheckResult:
    column_name: str
    rule: str
    severity: str
    total: int
    failed: int
    failure_rate: float
    threshold: float
    passed: bool
    detail: str | None = None

    def as_row(self) -> dict[str, Any]:
        return asdict(self)


def missing_columns(df: pd.DataFrame, contract: Contract) -> list[str]:
    return [c for c in contract.required_columns if c not in df.columns]


def _failures(s: pd.Series, check: Check) -> int:
    present = s.dropna()
    match check.rule:
        case "not_null":
            return int(s.isna().sum())
        case "unique":
            return int(present.astype(str).duplicated().sum())
        case "non_negative":
            return int((as_numeric(present) < 0).sum())
        case "range":
            x = as_numeric(present)
            bad = pd.Series(False, index=x.index)
            if check.min is not None:
                bad |= x < check.min
            if check.max is not None:
                bad |= x > check.max
            return int(bad.sum())
        case "in_set":
            allowed = {str(v) for v in check.values or []}
            return int((~present.astype(str).isin(allowed)).sum())
        case "regex":
            rx = re.compile(check.pattern or "")
            return int((~present.astype(str).map(lambda v: bool(rx.fullmatch(v)))).sum())
    raise ValueError(f"regla desconocida: {check.rule}")


def run_checks(df: pd.DataFrame, contract: Contract) -> list[CheckResult]:
    results: list[CheckResult] = []
    total = len(df)
    for check in contract.checks:
        if check.column not in df.columns:
            failed, detail = total, "columna ausente en la carga"
        else:
            failed, detail = _failures(df[check.column], check), None
        rate = failed / total if total else 0.0
        results.append(CheckResult(
            column_name=check.column,
            rule=check.rule,
            severity=check.severity,
            total=total,
            failed=failed,
            failure_rate=rate,
            threshold=check.max_failure_rate,
            passed=rate <= check.max_failure_rate,
            detail=detail,
        ))
    return results
