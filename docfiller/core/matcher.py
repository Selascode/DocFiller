"""Correspondance entre les champs d'un PDF et les clés de `data.json`.

Stratégies, de la plus fiable à la moins fiable :

1. **Apprise**     : l'utilisateur a déjà relié cet intitulé à une clé (alias).
2. **Exacte**      : l'intitulé normalisé est identique à une clé (« Code postal » = `code_postal`).
3. **Synonyme**    : l'intitulé est une variante connue, dans une autre langue
                     ou formulation (« Surname », « Apellido » -> `nom`).
4. **Calculée**    : valeur déduite d'autres données (`nom_complet` = prénom + nom,
                     `date_du_jour`...).
5. **Approximative** : similarité textuelle (fautes de frappe : « Adrese » -> `adresse`).

Tout est local et hors-ligne (bibliothèque standard uniquement).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Callable, Iterable, Mapping

from docfiller.core.data_store import normalize_key
from docfiller.core.exceptions import InvalidKeyError
from docfiller.core.pdf_engine import FormField
from docfiller.core.synonyms import FIELD_SYNONYMS
from docfiller.core.text_utils import canonical_text, similarity

# Fonction qui calcule une valeur à partir des données existantes (ou None).
DerivedValue = Callable[[Mapping[str, str]], str | None]


def _join_non_empty(*parts: str | None, separator: str = " ") -> str | None:
    return separator.join(p.strip() for p in parts if p and p.strip()) or None


# Date au format jour/mois/année (séparateurs « / », « . », « - » ou espace).
_DATE_PATTERN = re.compile(r"^\s*(\d{1,2})[/.\-\s](\d{1,2})[/.\-\s](\d{2,4})\s*$")


def _birth_date_part(index: int) -> DerivedValue:
    """Extrait le jour (1), le mois (2) ou l'année (3) de `date_naissance`."""

    def derive(data: Mapping[str, str]) -> str | None:
        found = _DATE_PATTERN.match(data.get("date_naissance", ""))
        if not found:
            return None
        part = found.group(index)
        return part if index == 3 else part.zfill(2)

    return derive


# Valeurs calculées lorsqu'elles ne sont pas présentes dans la base.
DERIVED_VALUES: dict[str, DerivedValue] = {
    "nom_complet": lambda d: _join_non_empty(d.get("prenom"), d.get("nom")),
    "date_du_jour": lambda d: date.today().strftime("%d/%m/%Y"),
    "lieu_signature": lambda d: d.get("ville") or None,
    "jour_naissance": _birth_date_part(1),
    "mois_naissance": _birth_date_part(2),
    "annee_naissance": _birth_date_part(3),
    "adresse_complete": lambda d: _join_non_empty(
        d.get("adresse"),
        _join_non_empty(d.get("code_postal"), d.get("ville")),
        d.get("pays"),
        separator=", ",
    ),
}


class MatchMethod(str, Enum):
    """Comment la correspondance a été trouvée."""

    LEARNED = "apprise"
    EXACT = "exacte"
    SYNONYM = "synonyme"
    DERIVED = "calculée"
    FUZZY = "approximative"


@dataclass(frozen=True)
class Match:
    """Correspondance trouvée pour un champ du PDF."""

    key: str  # Clé de data.json (ou concept calculé)
    value: str  # Valeur à injecter
    method: MatchMethod
    score: float  # Confiance, de 0.0 à 1.0
    label: str  # Intitulé du champ qui a permis la correspondance


class SynonymIndex:
    """Index « terme canonique -> concept » construit à partir du dictionnaire."""

    def __init__(self, groups: Mapping[str, Iterable[str]]) -> None:
        self._concept_of: dict[str, str] = {}
        for concept, terms in groups.items():
            for term in (concept.replace("_", " "), *terms):
                canon = canonical_text(term)
                if canon:
                    # En cas de doublon, le premier concept déclaré l'emporte.
                    self._concept_of.setdefault(canon, concept)

    def concept_for(self, text: str) -> str | None:
        """Concept correspondant à un intitulé, ou None."""
        return self._concept_of.get(canonical_text(text))

    def items(self) -> Iterable[tuple[str, str]]:
        """Paires (terme canonique, concept)."""
        return self._concept_of.items()


class FieldMatcher:
    """Associe les champs d'un formulaire aux données de l'utilisateur."""

    def __init__(
        self,
        synonyms: Mapping[str, Iterable[str]] = FIELD_SYNONYMS,
        derived: Mapping[str, DerivedValue] = DERIVED_VALUES,
        fuzzy_threshold: float = 0.85,
        fuzzy_min_length: int = 5,
    ) -> None:
        """
        Args:
            synonyms: dictionnaire concept -> variantes multilingues.
            derived: valeurs calculables à partir d'autres données.
            fuzzy_threshold: similarité minimale pour une correspondance approximative.
            fuzzy_min_length: en dessous de cette longueur, seule l'égalité compte
                (« nom » et « non » sont trop proches pour être devinés).
        """
        self._synonyms = SynonymIndex(synonyms)
        self._derived = dict(derived)
        self._fuzzy_threshold = fuzzy_threshold
        self._fuzzy_min_length = fuzzy_min_length

    # ------------------------------------------------------------------ #
    # API publique
    # ------------------------------------------------------------------ #
    def concept_for(self, label: str) -> str | None:
        """Concept standard correspondant à un intitulé (ex. « Surname » -> « nom »)."""
        return self._synonyms.concept_for(label)

    def match_all(
        self,
        fields: Iterable[FormField],
        data: Mapping[str, str],
        aliases: Mapping[str, str] | None = None,
    ) -> dict[str, Match]:
        """Cherche une correspondance pour chaque champ.

        Returns:
            Nom technique du champ -> correspondance (les champs sans
            correspondance sont absents du dictionnaire).
        """
        context = _MatchContext(self, data, aliases or {})
        matches: dict[str, Match] = {}
        for form_field in fields:
            found = context.match(form_field)
            if found is not None:
                matches[form_field.name] = found
        return matches

    def match(
        self,
        form_field: FormField,
        data: Mapping[str, str],
        aliases: Mapping[str, str] | None = None,
    ) -> Match | None:
        """Cherche la correspondance d'un seul champ."""
        return _MatchContext(self, data, aliases or {}).match(form_field)

    def suggest_concept(self, form_field: FormField) -> str | None:
        """Concept standard le plus précis pour un champ (ex. « jour_naissance »)."""
        return _MatchContext(self, {}, {}).suggest_concept(form_field)


class _MatchContext:
    """Index précalculés pour un jeu de données (évite de les recalculer par champ)."""

    def __init__(self, matcher: FieldMatcher, data: Mapping[str, str], aliases: Mapping[str, str]) -> None:
        self._matcher = matcher
        # On ignore les valeurs vides : elles ne permettent pas de remplir.
        self._data: dict[str, str] = {k: v for k, v in data.items() if v and v.strip()}
        self._aliases = aliases

        # Clé canonique -> clé de la base (« date naissance » -> « date_naissance »).
        self._exact: dict[str, str] = {canonical_text(k.replace("_", " ")): k for k in self._data}

        # Concept -> clé de la base qui le représente (directement ou via un synonyme).
        self._concept_key: dict[str, str] = {}
        for key in self._data:
            concept = matcher.concept_for(key.replace("_", " "))
            if concept and (concept not in self._concept_key or key == concept):
                self._concept_key[concept] = key

        # Termes utilisables pour la recherche approximative : terme -> (clé, valeur).
        self._fuzzy_terms: dict[str, tuple[str, str]] = {}
        for canon, key in self._exact.items():
            self._fuzzy_terms[canon] = (key, self._data[key])
        for canon, concept in matcher._synonyms.items():
            resolved = self._resolve_concept(concept)
            if resolved and canon not in self._fuzzy_terms:
                self._fuzzy_terms[canon] = (resolved[0], resolved[1])

    def _resolve_concept(self, concept: str) -> tuple[str, str, MatchMethod] | None:
        """Trouve la valeur d'un concept : en base, sinon calculée."""
        key = self._concept_key.get(concept)
        if key is not None:
            return key, self._data[key], MatchMethod.SYNONYM
        derive = self._matcher._derived.get(concept)
        if derive is not None:
            value = derive(self._data)
            if value:
                return concept, value, MatchMethod.DERIVED
        return None

    def match(self, form_field: FormField) -> Match | None:
        """Choisit la correspondance d'un champ parmi ses différents intitulés.

        Règles :
          1. une correspondance apprise (alias) l'emporte toujours ;
          2. sinon, parmi les intitulés *reconnus* (clé exacte ou synonyme), le plus
             spécifique (le plus de mots) l'emporte : « jour Naissance » est plus
             précis que « Né le ». S'il n'a pas de valeur, le champ est considéré
             comme manquant plutôt que rempli avec une donnée trop générale ;
          3. sinon, la meilleure correspondance approximative.
        """
        recognized: list[tuple[tuple[int, int], Match | None]] = []
        best_fuzzy: Match | None = None
        for order, label in enumerate(form_field.label_candidates):
            canon = canonical_text(label)
            if not canon:
                continue
            learned = self._match_alias(label)
            if learned is not None:
                return learned
            outcome = self._match_known(canon, label)
            if outcome is not None:
                specificity = (len(canon.split()), -order)
                recognized.append((specificity, outcome.match))
                continue
            fuzzy = self._match_fuzzy(canon, label)
            if fuzzy is not None and (best_fuzzy is None or fuzzy.score > best_fuzzy.score):
                best_fuzzy = fuzzy

        if recognized:
            return max(recognized, key=lambda item: item[0])[1]
        return best_fuzzy

    def suggest_concept(self, form_field: FormField) -> str | None:
        """Concept standard le plus spécifique parmi les intitulés du champ."""
        best: tuple[tuple[int, int], str] | None = None
        for order, label in enumerate(form_field.label_candidates):
            concept = self._matcher.concept_for(label)
            if concept:
                specificity = (len(canonical_text(label).split()), -order)
                if best is None or specificity > best[0]:
                    best = (specificity, concept)
        return best[1] if best else None

    def _match_alias(self, label: str) -> Match | None:
        """Correspondance apprise (alias enregistré par l'utilisateur)."""
        try:
            target = self._aliases.get(normalize_key(label))
        except InvalidKeyError:
            return None
        if not target:
            return None
        if target in self._data:
            return Match(target, self._data[target], MatchMethod.LEARNED, 1.0, label)
        resolved = self._resolve_concept(target)
        if resolved:
            return Match(resolved[0], resolved[1], MatchMethod.LEARNED, 1.0, label)
        return None

    def _match_known(self, canon: str, label: str) -> _Recognized | None:
        """Clé exacte ou synonyme. None si l'intitulé n'est pas reconnu du tout."""
        key = self._exact.get(canon)
        if key is not None:
            return _Recognized(Match(key, self._data[key], MatchMethod.EXACT, 1.0, label))

        concept = self._matcher.concept_for(label)
        if concept is None:
            return None
        resolved = self._resolve_concept(concept)
        if resolved is None:
            return _Recognized(None)  # Concept reconnu, mais aucune donnée
        key, value, method = resolved
        return _Recognized(Match(key, value, method, 0.95, label))

    def _match_fuzzy(self, canon: str, label: str) -> Match | None:
        """Correspondance approximative (même nombre de mots, longueur suffisante)."""
        min_length = self._matcher._fuzzy_min_length
        if len(canon) < min_length:
            return None
        word_count = canon.count(" ")
        best_score, best_term = 0.0, None
        for term in self._fuzzy_terms:
            if term.count(" ") != word_count or len(term) < min_length:
                continue
            score = similarity(canon, term)
            if score > best_score:
                best_score, best_term = score, term
        if best_term is None or best_score < self._matcher._fuzzy_threshold:
            return None
        key, value = self._fuzzy_terms[best_term]
        return Match(key, value, MatchMethod.FUZZY, round(best_score, 3), label)


@dataclass(frozen=True)
class _Recognized:
    """Intitulé reconnu : `match` vaut None si aucune donnée n'est disponible."""

    match: Match | None
