"""Compte rendu textuel d'un traitement, partagé par toutes les interfaces."""

from __future__ import annotations

from docfiller.core.pdf_engine import FillResult, FormField
from docfiller.core.processor import Analysis


def _section(title: str, lines: list[str]) -> list[str]:
    if not lines:
        return []
    return ["", f"{title} ({len(lines)}) :", *(f"  • {line}" for line in lines)]


def format_fields_summary(analysis: Analysis) -> str:
    """Résumé court après analyse (ex. « 12 champs · 8 reconnus · 3 à compléter »)."""
    parts = [f"{len(analysis.fields)} champ(s) détecté(s)", f"{len(analysis.matches)} reconnu(s)"]
    if analysis.missing:
        parts.append(f"{len(analysis.missing)} à compléter")
    return " · ".join(parts)


def format_report(analysis: Analysis, result: FillResult) -> str:
    """Compte rendu détaillé : champs remplis, saisis, ignorés, en erreur."""
    by_name: dict[str, FormField] = {f.name: f for f in analysis.fields}

    def label(name: str) -> str:
        form_field = by_name.get(name)
        return form_field.display_label if form_field else name

    lines: list[str] = []
    if result.output_path is not None:
        lines.append(f"Document généré : {result.output_path}")

    auto = [
        f"{label(name)} → {m.key} = « {m.value} » ({m.method.value})"
        for name, m in analysis.matches.items()
        if name not in result.errors
    ]
    manual = [
        f"{label(name)} = « {value} »"
        for name, value in analysis.manual_values.items()
        if name not in result.errors
    ]
    skipped = [label(name) for name in analysis.skipped]
    unanswered = [f.display_label for f in analysis.pending]
    not_handled = [f"{f.display_label} ({f.field_type.value})" for f in analysis.not_handled]
    errors = [f"{label(name)} : {reason}" for name, reason in result.errors.items()]

    lines += _section("Remplis automatiquement", auto)
    lines += _section("Saisis manuellement", manual)
    lines += _section("Ignorés", skipped)
    lines += _section("Non remplis (aucune donnée)", unanswered)
    lines += _section("Non traités (signature, lecture seule ou déjà remplis)", not_handled)
    lines += _section("Erreurs", errors)
    return "\n".join(lines)
