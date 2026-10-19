"""Moteur PDF : lecture des champs AcroForm et génération d'un PDF rempli.

Basé sur PyMuPDF (`pymupdf`, anciennement `fitz`), disponible sur desktop
et sur Android (via les recettes Kivy/python-for-android).

Les sources peuvent être un chemin **ou des octets** : sur mobile, les fichiers
partagés arrivent souvent sous forme de flux, pas de chemin disque.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import pymupdf

from docfiller.core.exceptions import (
    NoFormFieldsError,
    PdfCorruptedError,
    PdfEncryptedError,
    PdfError,
    PdfNotFoundError,
    PdfWriteError,
)
from docfiller.core.text_utils import (
    best_option,
    is_generic_name,
    is_truthy,
    looks_technical,
    split_identifier,
    technical_labels,
)

logger = logging.getLogger(__name__)

# Source d'un PDF : chemin sur disque ou contenu brut.
PdfSource = str | Path | bytes

# Distance maximale (en points PDF) pour rechercher un intitulé autour d'un champ.
_LABEL_MAX_DISTANCE_LEFT = 300.0
_LABEL_MAX_DISTANCE_RIGHT = 20.0
_LABEL_MAX_DISTANCE_ABOVE = 25.0
# Écart maximal entre deux mots d'un même intitulé.
_LABEL_MAX_WORD_GAP = 15.0
# Ordre de recherche de l'intitulé autour d'un champ, selon son type.
_DEFAULT_LABEL_SIDES = ("left", "above")
_CHECKBOX_LABEL_SIDES = ("right", "left", "above")
_RADIO_OPTION_SIDES = ("right",)


class FieldType(str, Enum):
    """Types de champs de formulaire pris en charge."""

    TEXT = "texte"
    CHECKBOX = "case à cocher"
    RADIO = "bouton radio"
    COMBOBOX = "liste déroulante"
    LISTBOX = "liste"
    SIGNATURE = "signature"
    BUTTON = "bouton"
    UNKNOWN = "inconnu"


_PYMUPDF_TYPES: dict[int, FieldType] = {
    pymupdf.PDF_WIDGET_TYPE_TEXT: FieldType.TEXT,
    pymupdf.PDF_WIDGET_TYPE_CHECKBOX: FieldType.CHECKBOX,
    pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON: FieldType.RADIO,
    pymupdf.PDF_WIDGET_TYPE_COMBOBOX: FieldType.COMBOBOX,
    pymupdf.PDF_WIDGET_TYPE_LISTBOX: FieldType.LISTBOX,
    pymupdf.PDF_WIDGET_TYPE_SIGNATURE: FieldType.SIGNATURE,
    pymupdf.PDF_WIDGET_TYPE_BUTTON: FieldType.BUTTON,
}

# Types que l'on sait remplir.
FILLABLE_TYPES: frozenset[FieldType] = frozenset(
    {FieldType.TEXT, FieldType.CHECKBOX, FieldType.RADIO, FieldType.COMBOBOX, FieldType.LISTBOX}
)

# Bit « saisie libre autorisée » d'une liste déroulante (spécification PDF).
_COMBO_EDIT_FLAG = 1 << 18


@dataclass(frozen=True)
class FormField:
    """Description d'un champ de formulaire (regroupe tous ses widgets).

    Un même champ peut apparaître plusieurs fois (ex. le nom en haut
    de chaque page) : il n'est listé qu'une fois.
    """

    name: str  # Nom technique complet (identifiant unique dans le PDF)
    field_type: FieldType
    page: int  # Index (base 0) de la première page où le champ apparaît
    tooltip: str | None = None  # Info-bulle / nom alternatif (/TU)
    nearby_text: str | None = None  # Intitulé lu sur la page à côté du champ
    current_value: str = ""
    options: tuple[str, ...] = ()  # Choix possibles (listes, boutons radio)
    read_only: bool = False
    required: bool = False

    @property
    def readable_name(self) -> str:
        """Nom technique rendu lisible (« LastName[0] » -> « Last Name »)."""
        return split_identifier(self.name)

    @property
    def label_candidates(self) -> list[str]:
        """Intitulés possibles du champ, du plus lisible au plus technique.

        1. Info-bulle et texte imprimé à côté du champ, s'ils sont rédigés en clair ;
        2. intitulés déduits des identifiants techniques (info-bulle, nom du champ).

        Les noms génériques (« Text1 ») sont exclus : ils ne disent rien du contenu.
        """
        readable: list[str] = []
        technical: list[str] = []
        for text in (self.tooltip, self.nearby_text):
            if text and text.strip():
                (technical if looks_technical(text) else readable).append(text.strip())
        technical.append(self.name)

        candidates: list[str] = []
        for label in (*readable, *(lbl for ident in technical for lbl in technical_labels(ident))):
            if label and not is_generic_name(label) and label not in candidates:
                candidates.append(label)
        return candidates

    @property
    def display_label(self) -> str:
        """Intitulé le plus parlant pour l'utilisateur."""
        candidates = self.label_candidates
        return candidates[0] if candidates else self.name

    @property
    def is_fillable(self) -> bool:
        """Le champ peut-il être rempli automatiquement ?"""
        return self.field_type in FILLABLE_TYPES and not self.read_only

    @property
    def is_empty(self) -> bool:
        """Le champ est-il vide dans le PDF source ?"""
        return self.current_value.strip() in ("", "Off")


@dataclass
class FillResult:
    """Résultat d'un remplissage."""

    output_path: Path | None
    filled: list[str] = field(default_factory=list)  # Champs remplis
    errors: dict[str, str] = field(default_factory=dict)  # Champ -> raison de l'échec


class PdfEngine:
    """Lecture et remplissage des formulaires PDF interactifs."""

    def __init__(self, value_equivalents: Iterable[Iterable[str]] = ()) -> None:
        """
        Args:
            value_equivalents: groupes de valeurs équivalentes entre langues
                (ex. « Homme » / « Male »), pour les listes et boutons radio.
        """
        self._value_equivalents: list[tuple[str, ...]] = [tuple(g) for g in value_equivalents]

    # ------------------------------------------------------------------ #
    # Ouverture
    # ------------------------------------------------------------------ #
    @staticmethod
    def _open(source: PdfSource) -> pymupdf.Document:
        """Ouvre un PDF en vérifiant sa validité.

        Raises:
            PdfNotFoundError, PdfCorruptedError, PdfEncryptedError
        """
        try:
            if isinstance(source, bytes):
                doc = pymupdf.open(stream=source, filetype="pdf")
            else:
                path = Path(source)
                if not path.is_file():
                    raise PdfNotFoundError(f"Fichier introuvable : {path}")
                # filetype="pdf" : empêche PyMuPDF d'ouvrir un .txt comme document texte.
                doc = pymupdf.open(path, filetype="pdf")
        except PdfError:
            raise
        except Exception as exc:  # PyMuPDF lève des exceptions variées selon la corruption
            logger.debug("Ouverture PDF impossible : %s", exc)
            raise PdfCorruptedError(f"{_describe(source)} n'est pas un PDF valide ou est endommagé.") from exc

        if not doc.is_pdf or doc.page_count == 0:
            doc.close()
            raise PdfCorruptedError(f"{_describe(source)} n'est pas un PDF valide ou ne contient aucune page.")
        if doc.needs_pass:
            doc.close()
            raise PdfEncryptedError("Le PDF est protégé par un mot de passe.")
        return doc

    # ------------------------------------------------------------------ #
    # Lecture des champs
    # ------------------------------------------------------------------ #
    def list_fields(self, source: PdfSource) -> list[FormField]:
        """Liste les champs du formulaire, dans l'ordre d'apparition.

        Raises:
            PdfNotFoundError, PdfCorruptedError, PdfEncryptedError
            NoFormFieldsError: le PDF n'a aucun champ interactif.
        """
        doc = self._open(source)
        try:
            fields = self._extract_fields(doc)
        finally:
            doc.close()

        if not fields:
            raise NoFormFieldsError(
                "Ce PDF ne contient aucun champ de formulaire interactif. "
                "Seuls les formulaires PDF remplissables (AcroForm) sont pris en charge."
            )
        return fields

    def _extract_fields(self, doc: pymupdf.Document) -> list[FormField]:
        # Un widget PyMuPDF devient inutilisable dès que sa page est libérée :
        # on relève donc toutes ses informations pendant le parcours de la page.
        grouped: dict[str, list[_WidgetSnapshot]] = {}
        for page in doc:
            words: list[tuple] | None = None
            for widget in page.widgets():
                words = words if words is not None else page.get_text("words")
                name = widget.field_name or f"champ_sans_nom_{widget.xref}"
                grouped.setdefault(name, []).append(_snapshot(doc, page.number, widget, words))

        fields: list[FormField] = []
        for name, snapshots in grouped.items():
            first = snapshots[0]
            if first.field_type == FieldType.RADIO:
                current = next((s.value for s in snapshots if s.value), "")
                options = tuple(dict.fromkeys(s.option_label or "" for s in snapshots))
            else:
                current = first.value
                options = first.choices
            fields.append(
                FormField(
                    name=name,
                    field_type=first.field_type,
                    page=first.page,
                    tooltip=first.tooltip,
                    nearby_text=first.nearby,
                    current_value=current,
                    options=options,
                    read_only=bool(first.flags & pymupdf.PDF_FIELD_IS_READ_ONLY),
                    required=bool(first.flags & pymupdf.PDF_FIELD_IS_REQUIRED),
                )
            )
        return fields

    # ------------------------------------------------------------------ #
    # Remplissage
    # ------------------------------------------------------------------ #
    def fill(
        self,
        source: PdfSource,
        values: Mapping[str, str],
        output_path: str | Path,
    ) -> FillResult:
        """Remplit le formulaire et l'enregistre dans `output_path`.

        Args:
            source: PDF d'origine (jamais modifié).
            values: nom technique du champ -> valeur texte.
            output_path: chemin du PDF à générer.

        Raises:
            PdfWriteError: si l'écriture échoue.
        """
        output = Path(output_path)
        if not isinstance(source, bytes) and Path(source).resolve() == output.resolve():
            raise PdfWriteError("Le fichier de sortie ne peut pas être le fichier d'origine.")

        doc = self._open(source)
        try:
            result = self._fill_document(doc, values)
            _drop_xfa(doc)
            try:
                output.parent.mkdir(parents=True, exist_ok=True)
                doc.save(output, garbage=3, deflate=True)
            except Exception as exc:
                raise PdfWriteError(f"Impossible d'enregistrer {output} : {exc}") from exc
        finally:
            doc.close()

        result.output_path = output
        return result

    def fill_to_bytes(self, source: PdfSource, values: Mapping[str, str]) -> tuple[bytes, FillResult]:
        """Variante sans disque (utile sur mobile : partage direct du résultat)."""
        doc = self._open(source)
        try:
            result = self._fill_document(doc, values)
            _drop_xfa(doc)
            data = doc.tobytes(garbage=3, deflate=True)
        finally:
            doc.close()
        return data, result

    def _fill_document(self, doc: pymupdf.Document, values: Mapping[str, str]) -> FillResult:
        """Remplit le document en deux passes.

        Un widget PyMuPDF n'est utilisable que tant que sa page est chargée :
        on inventorie d'abord les widgets, puis on écrit pendant le parcours des pages.
        """
        result = FillResult(output_path=None)

        # Passe 1 : inventaire des widgets concernés (aucune modification).
        found: dict[str, list[_WidgetInfo]] = {}
        for page in doc:
            words: list[tuple] | None = None
            for widget in page.widgets():
                if widget.field_name not in values:
                    continue
                label = None
                if widget.field_type == pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON:
                    words = words if words is not None else page.get_text("words")
                    nearby = _find_nearby_label(words, widget.rect, _RADIO_OPTION_SIDES)
                    label = _radio_labels([(widget, nearby)])[0]
                found.setdefault(widget.field_name, []).append(
                    _WidgetInfo(
                        field_type=_PYMUPDF_TYPES.get(widget.field_type, FieldType.UNKNOWN),
                        radio_label=label,
                        options=tuple(_choice_labels(widget.choice_values)),
                        flags=widget.field_flags or 0,
                    )
                )

        # Valeur à écrire dans chaque widget de chaque champ.
        plans: dict[str, list[str | bool]] = {}
        for name, value in values.items():
            infos = found.get(name)
            if not infos:
                result.errors[name] = "champ absent du PDF"
                continue
            try:
                plans[name] = self._plan_values(infos, value)
            except _FieldValueError as exc:
                result.errors[name] = str(exc)

        # Passe 2 : écriture, page par page.
        written: dict[str, int] = {}
        for page in doc:
            for widget in page.widgets():
                name = widget.field_name
                if name not in plans:
                    continue
                index = written.get(name, 0)
                written[name] = index + 1
                try:
                    widget.field_value = plans[name][index]
                    widget.update()
                except Exception as exc:  # Un champ défaillant ne doit pas bloquer les autres
                    result.errors[name] = f"erreur PyMuPDF : {exc}"

        result.filled = [name for name in plans if name not in result.errors]
        return result

    def _plan_values(self, infos: Sequence[_WidgetInfo], value: str) -> list[str | bool]:
        """Calcule la valeur de chaque widget d'un champ.

        Raises:
            _FieldValueError: la valeur ne peut pas être appliquée à ce champ.
        """
        field_type = infos[0].field_type
        count = len(infos)

        if field_type == FieldType.TEXT:
            return [value] * count

        if field_type == FieldType.CHECKBOX:
            return [is_truthy(value)] * count

        if field_type == FieldType.RADIO:
            labels = [info.radio_label or "" for info in infos]
            chosen = best_option(value, labels, self._value_equivalents)
            if chosen is None:
                raise _FieldValueError(f"« {value} » ne correspond à aucun choix ({', '.join(dict.fromkeys(labels))})")
            selected = labels.index(chosen)
            return [index == selected for index in range(count)]

        if field_type in (FieldType.COMBOBOX, FieldType.LISTBOX):
            options = list(infos[0].options)
            chosen = best_option(value, options, self._value_equivalents)
            if chosen is None:
                if field_type == FieldType.COMBOBOX and infos[0].flags & _COMBO_EDIT_FLAG:
                    chosen = value  # Saisie libre autorisée
                else:
                    raise _FieldValueError(f"« {value} » ne correspond à aucun choix ({', '.join(options)})")
            return [chosen] * count

        raise _FieldValueError(f"type de champ non pris en charge : {field_type.value}")

    # ------------------------------------------------------------------ #
    # Chemins de sortie
    # ------------------------------------------------------------------ #
    @staticmethod
    def build_output_path(source_name: str | Path, output_dir: str | Path, suffix: str = "_rempli") -> Path:
        """Construit un chemin de sortie qui n'écrase jamais un fichier existant.

        Ex. : « formulaire.pdf » -> « formulaire_rempli.pdf »,
        puis « formulaire_rempli_2.pdf » s'il existe déjà, etc.
        """
        stem = Path(source_name).stem
        directory = Path(output_dir)
        candidate = directory / f"{stem}{suffix}.pdf"
        counter = 2
        while candidate.exists():
            candidate = directory / f"{stem}{suffix}_{counter}.pdf"
            counter += 1
        return candidate


# --------------------------------------------------------------------------- #
# Fonctions internes
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class _WidgetSnapshot:
    """Informations d'un widget relevées à la lecture."""

    page: int
    field_type: FieldType
    tooltip: str | None
    nearby: str | None  # Intitulé imprimé à côté du champ
    option_label: str | None  # Bouton radio : libellé de ce choix
    value: str
    choices: tuple[str, ...]
    flags: int


@dataclass(frozen=True)
class _WidgetInfo:
    """Informations d'un widget nécessaires pour calculer sa valeur."""

    field_type: FieldType
    radio_label: str | None
    options: tuple[str, ...]
    flags: int


class _FieldValueError(Exception):
    """Valeur inapplicable à un champ (erreur locale, non bloquante)."""


def _drop_xfa(doc: pymupdf.Document) -> None:
    """Supprime la couche XFA des formulaires hybrides (fréquent sur les cerfa).

    Sinon, certains lecteurs (Adobe Reader) affichent les données XFA d'origine,
    vides, au lieu des valeurs AcroForm que l'on vient d'écrire.
    """
    catalog = doc.pdf_catalog()
    if doc.xref_get_key(catalog, "AcroForm/XFA")[0] == "null":
        return

    kind, value = doc.xref_get_key(catalog, "AcroForm")
    if kind == "xref":
        acroform = int(value.split()[0])
    else:
        # Dictionnaire intégré au catalogue : on en fait un objet indépendant.
        acroform = doc.get_new_xref()
        doc.update_object(acroform, value)
        doc.xref_set_key(catalog, "AcroForm", f"{acroform} 0 R")
    # Écriture directe sur l'objet : la notation « AcroForm/XFA » de PyMuPDF
    # écrit une valeur parasite au lieu de supprimer la clé.
    doc.xref_set_key(acroform, "XFA", "null")
    logger.info("Couche XFA supprimée du document généré.")


def _describe(source: PdfSource) -> str:
    """Désignation lisible d'une source pour les messages d'erreur."""
    return "Le document" if isinstance(source, bytes) else f"« {Path(source).name} »"


def _choice_labels(choice_values: Sequence[object] | None) -> list[str]:
    """Libellés des choix d'une liste (certains PDF stockent des paires [export, affichage])."""
    labels: list[str] = []
    for choice in choice_values or []:
        if isinstance(choice, (list, tuple)) and choice:
            labels.append(str(choice[-1]))
        else:
            labels.append(str(choice))
    return labels


def _radio_state(widget: pymupdf.Widget) -> str:
    """Valeur « active » d'un bouton radio (ex. « Homme »)."""
    state = widget.on_state()
    return str(state) if state not in (None, True, False) else "Yes"


def _radio_labels(entries: Sequence[tuple[pymupdf.Widget, str | None]]) -> list[str]:
    """Libellé de chaque bouton d'un groupe radio (un par widget, même ordre).

    Si l'état « actif » est générique (« Yes »), l'intitulé imprimé
    à côté du bouton est plus parlant (ex. « Homme »).
    """
    labels: list[str] = []
    for widget, nearby in entries:
        state = _radio_state(widget)
        labels.append(nearby if state == "Yes" and nearby else state)
    return labels


def _is_switched_on(doc: pymupdf.Document, widget: pymupdf.Widget) -> bool:
    """Case ou bouton radio activé ? (état d'apparence /AS propre à chaque widget)."""
    kind, state = doc.xref_get_key(widget.xref, "AS")
    if kind == "name":
        return state not in ("/Off", "/")
    return widget.field_value not in (None, "", "Off", False)


def _snapshot(doc: pymupdf.Document, page_number: int, widget: pymupdf.Widget, words: Sequence[tuple]) -> _WidgetSnapshot:
    """Relève les informations d'un widget tant que sa page est chargée."""
    field_type = _PYMUPDF_TYPES.get(widget.field_type, FieldType.UNKNOWN)
    # Cases à cocher : le libellé est souvent à droite (« ☐ J'accepte »).
    sides = _CHECKBOX_LABEL_SIDES if field_type == FieldType.CHECKBOX else _DEFAULT_LABEL_SIDES
    option_label: str | None = None

    if field_type == FieldType.RADIO:
        option_label = _radio_labels([(widget, _find_nearby_label(words, widget.rect, _RADIO_OPTION_SIDES))])[0]
        value = option_label if _is_switched_on(doc, widget) else ""
    elif field_type == FieldType.CHECKBOX:
        value = "Yes" if _is_switched_on(doc, widget) else "Off"
    else:
        raw = widget.field_value
        value = "" if raw in (None, False) else str(raw)

    return _WidgetSnapshot(
        page=page_number,
        field_type=field_type,
        tooltip=(widget.field_label or "").strip() or None,
        nearby=_find_nearby_label(words, widget.rect, sides),
        option_label=option_label,
        value=value,
        choices=tuple(_choice_labels(widget.choice_values)),
        flags=widget.field_flags or 0,
    )


def _find_nearby_label(words: Sequence[tuple], rect: pymupdf.Rect, sides: Sequence[str]) -> str | None:
    """Devine l'intitulé imprimé à côté d'un champ.

    Les côtés sont explorés dans l'ordre donné (« left », « right », « above »).
    Chaque mot est un tuple PyMuPDF (x0, y0, x1, y1, texte, bloc, ligne, n°).
    """
    finders = {"left": _label_left, "right": _label_right, "above": _label_above}
    for side in sides:
        label = finders[side](words, rect)
        if label:
            return label
    return None


def _same_line(word: tuple, rect: pymupdf.Rect) -> bool:
    center_y = (rect.y0 + rect.y1) / 2
    return word[1] <= center_y <= word[3]


def _label_left(words: Sequence[tuple], rect: pymupdf.Rect) -> str | None:
    """Mots contigus sur la même ligne, juste à gauche (« Nom : [______] »)."""
    left = [
        w for w in words
        if _same_line(w, rect) and w[2] <= rect.x0 + 2 and rect.x0 - w[2] <= _LABEL_MAX_DISTANCE_LEFT
    ]
    if not left:
        return None
    left.sort(key=lambda w: w[0])
    chain = [left[-1]]
    for word in reversed(left[:-1]):
        if chain[0][0] - word[2] > _LABEL_MAX_WORD_GAP:
            break
        chain.insert(0, word)
    return _join_words(chain)


def _label_right(words: Sequence[tuple], rect: pymupdf.Rect) -> str | None:
    """Mots contigus sur la même ligne, juste à droite (« ○ Homme ○ Femme »)."""
    right = [
        w for w in words
        if _same_line(w, rect) and w[0] >= rect.x1 - 2 and w[0] - rect.x1 <= _LABEL_MAX_DISTANCE_RIGHT
    ]
    if not right:
        return None
    right.sort(key=lambda w: w[0])
    chain = [right[0]]
    for word in right[1:]:
        if word[0] - chain[-1][2] > _LABEL_MAX_WORD_GAP:
            break
        chain.append(word)
    return _join_words(chain)


def _label_above(words: Sequence[tuple], rect: pymupdf.Rect) -> str | None:
    """Ligne juste au-dessus du champ, qui le chevauche horizontalement."""
    above = [
        w for w in words
        if rect.y0 - _LABEL_MAX_DISTANCE_ABOVE <= w[3] <= rect.y0 + 2 and w[0] < rect.x1 and w[2] > rect.x0 - 10
    ]
    if not above:
        return None
    closest = max(above, key=lambda w: w[3])
    line = sorted((w for w in above if (w[5], w[6]) == (closest[5], closest[6])), key=lambda w: w[0])
    return _join_words(line)


def _join_words(words: Sequence[tuple]) -> str | None:
    text = " ".join(" ".join(str(w[4]) for w in words).split()).strip(" :.*_-–/")
    # Un intitulé sans lettre (« / », « @ ») n'apporte rien.
    return text if re.search(r"[^\W\d_]", text) else None
