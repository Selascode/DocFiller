"""Interface en ligne de commande (tests rapides, usage sans écran).

    python -m docfiller.cli champs formulaire.pdf
    python -m docfiller.cli remplir formulaire.pdf -o dossier_sortie
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from docfiller.config import default_data_dir
from docfiller.core import (
    DocFillerError,
    DocumentProcessor,
    FormField,
    PdfEngine,
    ProcessingCancelled,
    Resolution,
)
from docfiller.core.report import format_report

_CANCEL_COMMAND = "!q"


def _ask_in_console(form_field: FormField, position: int, total: int, suggested_key: str) -> Resolution | None:
    """Résolution interactive d'un champ manquant dans le terminal."""
    try:
        return _prompt_field(form_field, position, total, suggested_key)
    except EOFError:  # Ctrl+D ou entrée fermée
        raise ProcessingCancelled() from None


def _prompt_field(form_field: FormField, position: int, total: int, suggested_key: str) -> Resolution | None:
    print(f"\n[{position}/{total}] Information manquante : {form_field.display_label} ({form_field.field_type.value})")
    if form_field.options:
        print(f"  Choix possibles : {', '.join(form_field.options)}")
    value = input(f"  Valeur (vide = ignorer, {_CANCEL_COMMAND} = annuler) : ").strip()
    if value == _CANCEL_COMMAND:
        raise ProcessingCancelled()
    if not value:
        return None
    answer = input("  Voulez-vous sauvegarder cette information pour les futurs documents ? [O/n] ").strip().lower()
    save = answer in ("", "o", "oui", "y", "yes")
    key = None
    if save:
        key = input(f"  Clé [{suggested_key}] : ").strip() or suggested_key
    return Resolution(value=value, save=save, key=key)


def _list_fields(pdf: Path) -> None:
    for form_field in PdfEngine().list_fields(pdf):
        status = "lecture seule" if form_field.read_only else "remplissable" if form_field.is_fillable else "ignoré"
        print(f"- {form_field.display_label!r} [{form_field.field_type.value}, page {form_field.page + 1}, {status}]")
        print(f"    nom technique : {form_field.name}")
        if form_field.options:
            print(f"    choix : {', '.join(form_field.options)}")
        if form_field.current_value and not form_field.is_empty:
            print(f"    valeur actuelle : {form_field.current_value}")


def _fill(pdf: Path, output_dir: Path, interactive: bool) -> None:
    processor = DocumentProcessor.from_directory(default_data_dir())
    resolver = _ask_in_console if interactive else None
    analysis, result = processor.process(pdf, output_dir, resolver)
    print("\n" + format_report(analysis, result))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="docfiller", description="Remplissage automatique de formulaires PDF.")
    commands = parser.add_subparsers(dest="command", required=True)

    list_cmd = commands.add_parser("champs", help="Lister les champs d'un formulaire PDF")
    list_cmd.add_argument("pdf", type=Path)

    fill_cmd = commands.add_parser("remplir", help="Remplir un formulaire PDF avec data.json")
    fill_cmd.add_argument("pdf", type=Path)
    fill_cmd.add_argument("-o", "--sortie", type=Path, help="Dossier de destination (défaut : celui du PDF)")
    fill_cmd.add_argument("--non-interactif", action="store_true", help="Ne pas demander les champs manquants")

    args = parser.parse_args(argv)
    try:
        if args.command == "champs":
            _list_fields(args.pdf)
        else:
            _fill(args.pdf, args.sortie or args.pdf.parent, not args.non_interactif)
    except (ProcessingCancelled, KeyboardInterrupt):
        print("\nTraitement annulé.")
        return 1
    except DocFillerError as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
