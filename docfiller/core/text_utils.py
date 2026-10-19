"""Utilitaires de traitement de texte partagés (normalisation, similarité).

Uniquement la bibliothèque standard (`difflib`, `unicodedata`) :
aucune dépendance native, donc portable sur mobile.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Iterable, Sequence

# Mots « de remplissage » ignorés lors des comparaisons, en plusieurs langues.
# Ex. : « Votre nom » et « Nom » doivent être considérés comme équivalents.
STOP_WORDS: frozenset[str] = frozenset(
    {
        # Français
        "votre", "vos", "ton", "ta", "tes", "le", "la", "les", "l", "de", "du", "des",
        "d", "un", "une", "veuillez", "indiquer", "saisir", "renseigner", "merci",
        # Anglais
        "your", "the", "of", "please", "enter", "an", "type", "here",
        # Espagnol / Italien / Portugais / Allemand
        "su", "tu", "el", "los", "las", "del", "il", "lo", "di", "seu", "sua",
        "ihr", "ihre", "der", "die", "das",
        # Abréviations de « numéro »
        "n", "no", "nr", "num", "nb",
    }
)

# Valeurs interprétées comme « coché » pour les cases à cocher (toutes langues).
TRUTHY_VALUES: frozenset[str] = frozenset(
    {"oui", "o", "yes", "y", "true", "vrai", "1", "x", "on", "si", "ja", "sim", "checked", "coche"}
)


def strip_accents(text: str) -> str:
    """Supprime les diacritiques : « Élève » -> « Eleve »."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


# Marques d'accord inclusives : « Né(e) », « Prénom(s) » -> « Né », « Prénom ».
_AGREEMENT_MARKS = re.compile(r"\((?:e|s|es|x|ne|le)\)")


def tokenize(text: str) -> list[str]:
    """Découpe un texte en mots normalisés (minuscules, sans accents)."""
    cleaned = _AGREEMENT_MARKS.sub("", strip_accents(text).lower())
    return re.findall(r"[a-z0-9]+", cleaned)


def canonical_text(text: str) -> str:
    """Forme canonique utilisée pour comparer des intitulés.

    Minuscules, sans accents, sans ponctuation, sans mots de remplissage.
    Si tous les mots sont des mots vides, on les conserve (évite une chaîne vide).

    Ex. : « Votre N° de téléphone : » -> « telephone ».
    """
    tokens = tokenize(text)
    meaningful = [t for t in tokens if t not in STOP_WORDS]
    return " ".join(meaningful or tokens)


def similarity(a: str, b: str) -> float:
    """Ratio de similarité (0.0 à 1.0) entre deux textes déjà canoniques."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def split_identifier(identifier: str) -> str:
    """Rend lisible un nom technique de champ PDF.

    Ex. : « topmostSubform[0].Page1[0].LastName_1[0] » -> « Last Name 1 ».
    """
    last_segment = identifier.split(".")[-1]
    without_index = re.sub(r"\[\d+\]", "", last_segment)
    # Sépare le camelCase : « lastName » -> « last Name ».
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", without_index)
    return re.sub(r"[_\-\s]+", " ", spaced).strip()


# Segments d'identifiants techniques qui ne décrivent pas le contenu.
_MEANINGLESS_SEGMENTS: frozenset[str] = frozenset(
    {"concat", "total", "info", "infos", "txt", "text", "value", "val", "field", "champ", "list", "liste", "calcule"}
)
# Segments de structure (sous-formulaires, pages) à ne jamais utiliser comme intitulé.
_STRUCTURE_SEGMENTS: frozenset[str] = frozenset({"page", "topmost subform", "subform", "form", "formulaire", "section"})
_CAMEL_CASE = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Za-z])(?=[0-9])")


def looks_technical(text: str) -> bool:
    """Indique si un texte ressemble à un identifiant technique (« infosPerso-nomUsage »)."""
    stripped = text.strip()
    return bool(stripped) and " " not in stripped and bool(re.search(r"[-_.\[]|[a-z][A-Z]", stripped))


def _humanize_segment(segment: str) -> str:
    """« nomNaissance » -> « nom Naissance » ; « mail1 » -> « mail » (un « 1 » final est retiré)."""
    words = _CAMEL_CASE.sub(" ", segment).split()
    if len(words) > 1 and words[-1] == "1":
        words.pop()
    return " ".join(words)


def technical_labels(identifier: str) -> list[str]:
    """Intitulés lisibles déduits d'un identifiant technique, du plus précis au plus large.

    Ex. : « infosPerso-identite-info-prenoms-concat » -> ["prenoms", "info prenoms"]
          « topmostSubform[0].Page1[0].DateOfBirth[0] » -> ["Date Of Birth", ...]
    """
    without_index = re.sub(r"\[\d+\]", "", identifier)
    if " " in without_index.strip():
        return [" ".join(without_index.split())]  # Nom déjà rédigé en clair
    segments = [seg for seg in re.split(r"[.\-_/]+", without_index) if seg]
    if not segments:
        return []
    while len(segments) > 1 and segments[-1].lower() in _MEANINGLESS_SEGMENTS:
        segments.pop()

    labels = [_humanize_segment(segments[-1])]
    if len(segments) > 1:
        parent = _humanize_segment(segments[-2])
        if parent.lower() not in _MEANINGLESS_SEGMENTS | _STRUCTURE_SEGMENTS:
            labels.append(f"{parent} {labels[0]}")
    return [label for label in labels if label]


# Noms techniques génériques qui ne décrivent pas le contenu du champ.
_GENERIC_NAME = re.compile(
    r"^(text|texte|txt|field|champ|textfield|textbox|fill|f|t|tf|zone|untitled|"
    r"check ?box|case|radio|combo ?box|list ?box|dropdown|button|bouton)?\s*\d*$",
    re.IGNORECASE,
)


def is_generic_name(name: str) -> bool:
    """Indique si un nom de champ est générique (« Text1 », « Champ 12 », « f2 »...)."""
    return bool(_GENERIC_NAME.match(name.strip()))


def is_truthy(value: str) -> bool:
    """Interprète une valeur texte comme vraie/fausse (pour les cases à cocher)."""
    return " ".join(tokenize(value)) in TRUTHY_VALUES


def best_option(
    value: str,
    options: Sequence[str],
    equivalents: Iterable[Iterable[str]] = (),
    threshold: float = 0.8,
) -> str | None:
    """Trouve l'option d'une liste qui correspond le mieux à une valeur.

    Args:
        value: valeur issue de la base (ex. « Homme »).
        options: choix proposés par le PDF (ex. ["Male", "Female"]).
        equivalents: groupes de valeurs équivalentes entre langues
            (ex. [("homme", "male", "m"), ...]).
        threshold: similarité minimale pour une correspondance approximative.

    Returns:
        L'option retenue, ou None si aucune ne convient.
    """
    target = canonical_text(value)
    if not target or not options:
        return None

    canon_options = {opt: canonical_text(opt) for opt in options}

    # 1. Égalité stricte (après normalisation).
    for opt, canon in canon_options.items():
        if canon == target:
            return opt

    # 2. Équivalence multilingue (ex. « Homme » <-> « Male »).
    for group in equivalents:
        canon_group = {canonical_text(term) for term in group}
        if target in canon_group:
            for opt, canon in canon_options.items():
                if canon in canon_group:
                    return opt

    # 3. Similarité approximative (fautes de frappe, variantes).
    scored = [(similarity(target, canon), opt) for opt, canon in canon_options.items()]
    score, opt = max(scored)
    return opt if score >= threshold else None
