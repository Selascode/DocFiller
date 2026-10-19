"""Orchestration du traitement d'un document : analyse, apprentissage, génération.

Le traitement est découpé en phases indépendantes de l'interface :

1. `analyze()`  : lit le PDF et trouve les correspondances automatiques ;
2. `resolve()` / `skip()` : l'interface traite les champs manquants
   (boîte de dialogue sur desktop, écran dédié sur mobile...) ;
3. `generate()` : produit le PDF rempli.

Ce découpage permet une interface **non bloquante** (indispensable sur mobile).
Pour un usage simple et synchrone (ligne de commande), `process()` enchaîne
les trois phases à l'aide d'un `MissingFieldResolver`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from docfiller.core.data_store import DataStore, normalize_key
from docfiller.core.exceptions import InvalidKeyError
from docfiller.core.matcher import FieldMatcher, Match
from docfiller.core.pdf_engine import FillResult, FormField, PdfEngine, PdfSource
from docfiller.core.synonyms import VALUE_EQUIVALENTS

# Longueur maximale d'une clé proposée automatiquement.
_MAX_SUGGESTED_KEY_LENGTH = 50


@dataclass(frozen=True)
class Resolution:
    """Réponse de l'utilisateur pour un champ manquant."""

    value: str
    save: bool = True  # Mémoriser pour les futurs documents ?
    key: str | None = None  # Clé sous laquelle mémoriser (None = clé suggérée)


class MissingFieldResolver(Protocol):
    """Fonction appelée pour chaque champ manquant (traitement synchrone).

    Retourne une `Resolution`, ou None pour ignorer le champ.
    Peut lever `ProcessingCancelled` pour tout annuler.
    """

    def __call__(self, form_field: FormField, position: int, total: int, suggested_key: str) -> Resolution | None:
        ...


@dataclass
class Analysis:
    """État du traitement d'un document."""

    source: PdfSource
    source_name: str  # Nom du fichier d'origine (sert à nommer la sortie)
    fields: list[FormField]
    matches: dict[str, Match]  # Correspondances automatiques
    missing: list[FormField]  # Champs remplissables sans correspondance
    not_handled: list[FormField]  # Signatures, boutons, lecture seule, déjà remplis
    manual_values: dict[str, str] = field(default_factory=dict)  # Saisies de l'utilisateur
    skipped: set[str] = field(default_factory=set)  # Champs ignorés par l'utilisateur

    @property
    def pending(self) -> list[FormField]:
        """Champs manquants qui attendent encore une réponse."""
        return [f for f in self.missing if f.name not in self.manual_values and f.name not in self.skipped]

    def values(self) -> dict[str, str]:
        """Valeurs finales à injecter : nom technique -> valeur."""
        values = {name: m.value for name, m in self.matches.items()}
        values.update(self.manual_values)
        return values


class DocumentProcessor:
    """Point d'entrée du cœur métier, utilisé par l'interface graphique."""

    def __init__(
        self,
        data_store: DataStore,
        alias_store: DataStore,
        engine: PdfEngine | None = None,
        matcher: FieldMatcher | None = None,
        overwrite_prefilled: bool = False,
    ) -> None:
        """
        Args:
            data_store: données personnelles (`data.json`).
            alias_store: correspondances apprises intitulé -> clé (`aliases.json`).
            engine: moteur PDF (injectable pour les tests).
            matcher: moteur de correspondance (injectable pour les tests).
            overwrite_prefilled: remplacer les champs déjà remplis dans le PDF source.
        """
        self.data_store = data_store
        self.alias_store = alias_store
        self.engine = engine or PdfEngine(value_equivalents=VALUE_EQUIVALENTS)
        self.matcher = matcher or FieldMatcher()
        self.overwrite_prefilled = overwrite_prefilled

    @classmethod
    def from_directory(cls, data_dir: str | Path, **kwargs: object) -> DocumentProcessor:
        """Crée un processeur à partir d'un dossier de données (data.json + aliases.json)."""
        directory = Path(data_dir)
        return cls(
            DataStore(directory / "data.json"),
            DataStore(directory / "aliases.json"),
            **kwargs,  # type: ignore[arg-type]
        )

    # ------------------------------------------------------------------ #
    # Phase 1 : analyse
    # ------------------------------------------------------------------ #
    def analyze(self, source: PdfSource, source_name: str | None = None) -> Analysis:
        """Lit le PDF et calcule les correspondances automatiques.

        Raises:
            PdfError (et sous-classes) : fichier introuvable, corrompu, sans formulaire...
        """
        if source_name is None:
            source_name = "document.pdf" if isinstance(source, bytes) else Path(source).name

        fields = self.engine.list_fields(source)
        to_fill: list[FormField] = []
        not_handled: list[FormField] = []
        for form_field in fields:
            if form_field.is_fillable and (self.overwrite_prefilled or form_field.is_empty):
                to_fill.append(form_field)
            else:
                not_handled.append(form_field)

        matches = self.matcher.match_all(to_fill, self.data_store.as_dict(), self.alias_store.as_dict())
        missing = [f for f in to_fill if f.name not in matches]
        return Analysis(
            source=source,
            source_name=source_name,
            fields=fields,
            matches=matches,
            missing=missing,
            not_handled=not_handled,
        )

    # ------------------------------------------------------------------ #
    # Phase 2 : champs manquants et apprentissage
    # ------------------------------------------------------------------ #
    def suggest_key(self, form_field: FormField) -> str:
        """Propose une clé pour mémoriser la valeur d'un champ.

        Un intitulé reconnu dans une autre langue donne la clé standard
        (« Surname » -> « nom ») : les données restent cohérentes entre langues.
        """
        concept = self.matcher.suggest_concept(form_field)
        if concept:
            return concept
        for label in (*form_field.label_candidates, form_field.name):
            try:
                return normalize_key(label)[:_MAX_SUGGESTED_KEY_LENGTH].strip("_")
            except InvalidKeyError:
                continue
        return "champ"

    def resolve(self, analysis: Analysis, form_field: FormField, resolution: Resolution) -> None:
        """Enregistre la réponse de l'utilisateur pour un champ manquant.

        Si `resolution.save` est vrai :
          - la valeur est ajoutée/mise à jour dans `data.json` ;
          - les intitulés du champ sont mémorisés comme alias de la clé,
            pour reconnaître ce champ automatiquement la prochaine fois ;
          - les champs encore en attente sont réexaminés : la nouvelle donnée
            peut en compléter d'autres (ex. date de naissance -> jour, mois, année).

        Raises:
            InvalidKeyError: clé de sauvegarde invalide.
        """
        value = resolution.value.strip()
        analysis.skipped.discard(form_field.name)
        analysis.manual_values[form_field.name] = value

        if not resolution.save or not value:
            return

        key = normalize_key(resolution.key or self.suggest_key(form_field))
        if self.data_store.get(key) != value:
            self.data_store.set(key, value)

        aliases: dict[str, str] = {}
        for label in form_field.label_candidates:
            try:
                if normalize_key(label) != key:
                    aliases[label] = key
            except InvalidKeyError:
                continue
        if aliases:
            self.alias_store.update(aliases)

        self._rematch_pending(analysis)

    def _rematch_pending(self, analysis: Analysis) -> None:
        """Réexamine les champs en attente avec les données à jour.

        Les alias ne sont volontairement pas utilisés ici : deux champs d'un même
        document portant le même intitulé (« Numéro ») n'ont pas forcément la même valeur.
        """
        pending = analysis.pending
        if not pending:
            return
        found = self.matcher.match_all(pending, self.data_store.as_dict(), aliases={})
        for form_field in pending:
            if form_field.name in found:
                analysis.matches[form_field.name] = found[form_field.name]
                analysis.missing.remove(form_field)

    def skip(self, analysis: Analysis, form_field: FormField) -> None:
        """Ignore un champ manquant (il restera vide)."""
        analysis.manual_values.pop(form_field.name, None)
        analysis.skipped.add(form_field.name)

    # ------------------------------------------------------------------ #
    # Phase 3 : génération
    # ------------------------------------------------------------------ #
    def generate(self, analysis: Analysis, output_dir: str | Path) -> FillResult:
        """Génère le PDF rempli dans `output_dir` sans écraser l'existant.

        Raises:
            PdfWriteError: écriture impossible.
        """
        output_path = self.engine.build_output_path(analysis.source_name, output_dir)
        return self.engine.fill(analysis.source, analysis.values(), output_path)

    def generate_bytes(self, analysis: Analysis) -> tuple[bytes, FillResult]:
        """Génère le PDF rempli en mémoire (partage direct sur mobile)."""
        return self.engine.fill_to_bytes(analysis.source, analysis.values())

    # ------------------------------------------------------------------ #
    # Traitement complet synchrone
    # ------------------------------------------------------------------ #
    def process(
        self,
        source: PdfSource,
        output_dir: str | Path,
        resolver: MissingFieldResolver | None = None,
        source_name: str | None = None,
    ) -> tuple[Analysis, FillResult]:
        """Enchaîne analyse, résolution des champs manquants et génération.

        Raises:
            ProcessingCancelled: si le `resolver` annule le traitement.
        """
        analysis = self.analyze(source, source_name)
        position = 0
        # La liste des champs en attente peut raccourcir en cours de route (voir `resolve`).
        while resolver is not None and analysis.pending:
            form_field = analysis.pending[0]
            position += 1
            total = position + len(analysis.pending) - 1
            resolution = resolver(form_field, position, total, self.suggest_key(form_field))
            if resolution is None:
                self.skip(analysis, form_field)
            else:
                self.resolve(analysis, form_field, resolution)
        return analysis, self.generate(analysis, output_dir)
