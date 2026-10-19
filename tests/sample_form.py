"""Génère un formulaire PDF de test (en anglais, pour tester le multilinguisme).

Utilisable dans les tests ou en ligne de commande pour essayer l'interface :

    python -m tests.sample_form formulaire_test.pdf
"""

from __future__ import annotations

import sys
from pathlib import Path

import pymupdf

# (nom technique, intitulé imprimé, info-bulle) des champs texte.
TEXT_FIELDS: list[tuple[str, str, str | None]] = [
    ("Text1", "Last name:", None),  # Intitulé lu sur la page
    ("f2", "Given name:", "First name"),  # Info-bulle prioritaire
    ("topmostSubform[0].Page1[0].DateOfBirth[0]", "Birth:", None),  # Nom technique lisible
    ("Text4", "E-mail address:", None),
    ("Text5", "Adress:", None),  # Faute de frappe -> approximation
    ("Text6", "Full name:", None),  # Valeur calculée (prénom + nom)
    ("Text7", "Favourite colour:", None),  # Inconnu -> demandé à l'utilisateur
    ("Text8", "Nom du père :", None),  # Ne doit PAS correspondre à « nom »
]


def build_sample_form(path: str | Path | None = None) -> bytes:
    """Construit le formulaire et retourne son contenu (et l'écrit si `path` est fourni)."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 40), "Application form", fontsize=16)

    y = 70.0
    for name, label, tooltip in TEXT_FIELDS:
        page.insert_text((50, y + 14), label, fontsize=11)
        widget = pymupdf.Widget()
        widget.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
        widget.field_name = name
        widget.rect = pymupdf.Rect(200, y, 480, y + 20)
        if tooltip:
            widget.field_label = tooltip
        page.add_widget(widget)
        y += 30

    # Liste déroulante.
    page.insert_text((50, y + 14), "Country:", fontsize=11)
    combo = pymupdf.Widget()
    combo.field_type = pymupdf.PDF_WIDGET_TYPE_COMBOBOX
    combo.field_name = "country_list"
    combo.choice_values = ["France", "Germany", "Spain"]
    combo.rect = pymupdf.Rect(200, y, 480, y + 20)
    page.add_widget(combo)
    y += 30

    # Case à cocher.
    page.insert_text((50, y + 12), "I agree:", fontsize=11)
    checkbox = pymupdf.Widget()
    checkbox.field_type = pymupdf.PDF_WIDGET_TYPE_CHECKBOX
    checkbox.field_name = "consent"
    checkbox.rect = pymupdf.Rect(200, y, 215, y + 15)
    page.add_widget(checkbox)
    y += 30

    # Champ en lecture seule déjà rempli : ne doit pas être touché.
    page.insert_text((50, y + 14), "Reference:", fontsize=11)
    readonly = pymupdf.Widget()
    readonly.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
    readonly.field_name = "reference"
    readonly.field_value = "REF-123"
    readonly.field_flags = pymupdf.PDF_FIELD_IS_READ_ONLY
    readonly.rect = pymupdf.Rect(200, y, 480, y + 20)
    page.add_widget(readonly)

    # Page 2 : boutons radio (libellés à droite) et champ répété.
    page2 = doc.new_page()
    page2.insert_text((50, 64), "Gender:", fontsize=11)
    for index, label in enumerate(("Male", "Female")):
        x = 200 + 100 * index
        radio = pymupdf.Widget()
        radio.field_type = pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON
        radio.field_name = "gender"
        radio.field_value = False
        radio.rect = pymupdf.Rect(x, 52, x + 14, 66)
        page2.add_widget(radio)
        page2.insert_text((x + 18, 64), label, fontsize=11)

    page2.insert_text((50, 104), "Last name:", fontsize=11)
    repeated = pymupdf.Widget()
    repeated.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
    repeated.field_name = "Text1"  # Même champ qu'en page 1
    repeated.rect = pymupdf.Rect(200, 90, 480, 110)
    page2.add_widget(repeated)

    data = doc.tobytes()
    doc.close()
    if path is not None:
        Path(path).write_bytes(data)
    return data


def build_plain_pdf() -> bytes:
    """PDF valide mais sans aucun champ de formulaire."""
    doc = pymupdf.open()
    doc.new_page().insert_text((50, 50), "Pas de formulaire ici.")
    data = doc.tobytes()
    doc.close()
    return data


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "formulaire_test.pdf")
    build_sample_form(target)
    print(f"Formulaire de test créé : {target.resolve()}")
