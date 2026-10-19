"""Tests de l'orchestration et de l'apprentissage (Étape 3)."""

import tempfile
import unittest
from pathlib import Path

import pymupdf

from docfiller.core import (
    DocumentProcessor,
    FormField,
    MatchMethod,
    PdfEngine,
    ProcessingCancelled,
    Resolution,
)
from tests.sample_form import build_sample_form


class TestDocumentProcessor(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.pdf = self.tmp / "formulaire.pdf"
        build_sample_form(self.pdf)
        self.out_dir = self.tmp / "sortie"
        self.processor = DocumentProcessor.from_directory(self.tmp / "donnees")
        self.processor.data_store.update(
            {
                "nom": "Dupont",
                "prenom": "Jean",
                "email": "jean@exemple.fr",
                "adresse": "1 rue de la Lune",
                "pays": "France",
                "sexe": "Homme",
            }
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _field(self, analysis_fields: list[FormField], name: str) -> FormField:
        return next(f for f in analysis_fields if f.name == name)

    def test_analyse(self) -> None:
        analysis = self.processor.analyze(self.pdf)
        self.assertEqual(analysis.source_name, "formulaire.pdf")
        self.assertEqual(analysis.matches["Text1"].value, "Dupont")
        self.assertEqual(analysis.matches["Text6"].value, "Jean Dupont")
        self.assertEqual(analysis.matches["gender"].key, "sexe")
        missing = {f.name for f in analysis.missing}
        self.assertEqual(missing, {"topmostSubform[0].Page1[0].DateOfBirth[0]", "Text7", "Text8", "consent"})
        self.assertEqual([f.name for f in analysis.not_handled], ["reference"])

    def test_suggestion_de_cle(self) -> None:
        fields = self.processor.analyze(self.pdf).fields
        # Intitulé anglais reconnu -> clé standard française.
        self.assertEqual(self.processor.suggest_key(self._field(fields, "topmostSubform[0].Page1[0].DateOfBirth[0]")), "date_naissance")
        # Intitulé inconnu -> clé dérivée de l'intitulé.
        self.assertEqual(self.processor.suggest_key(self._field(fields, "Text7")), "favourite_colour")

    def test_apprentissage(self) -> None:
        analysis = self.processor.analyze(self.pdf)
        colour = self._field(analysis.fields, "Text7")
        self.processor.resolve(analysis, colour, Resolution("Bleu", save=True, key="couleur_preferee"))

        # Valeur et alias mémorisés.
        self.assertEqual(self.processor.data_store.get("couleur_preferee"), "Bleu")
        self.assertEqual(self.processor.alias_store.get("favourite_colour"), "couleur_preferee")

        # Au document suivant, le champ est reconnu automatiquement.
        new_analysis = self.processor.analyze(self.pdf)
        match = new_analysis.matches["Text7"]
        self.assertEqual((match.value, match.method), ("Bleu", MatchMethod.LEARNED))

    def test_reexamen_apres_apprentissage(self) -> None:
        # Formulaire avec date de naissance éclatée en trois cases (comme les cerfa).
        doc = pymupdf.open()
        page = doc.new_page()
        for index, part in enumerate(("jourNaissance", "moisNaissance", "anneeNaissance")):
            widget = pymupdf.Widget()
            widget.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
            widget.field_name = f"identite-dateNaissanceTriple-{part}"
            widget.rect = pymupdf.Rect(100 + 60 * index, 100, 150 + 60 * index, 120)
            page.add_widget(widget)
        analysis = self.processor.analyze(doc.tobytes(), "naissance.pdf")
        doc.close()
        self.assertEqual(len(analysis.pending), 3)

        # L'utilisateur saisit sa date complète en réponse à la case « jour »...
        day = analysis.pending[0]
        self.processor.resolve(analysis, day, Resolution("01/02/1990", save=True, key="date_naissance"))
        # ... les deux autres cases sont alors calculées sans nouvelle question.
        self.assertEqual(analysis.pending, [])
        values = sorted(m.value for m in analysis.matches.values())
        self.assertEqual(values, ["02", "1990"])

    def test_sans_sauvegarde(self) -> None:
        analysis = self.processor.analyze(self.pdf)
        colour = self._field(analysis.fields, "Text7")
        self.processor.resolve(analysis, colour, Resolution("Vert", save=False))
        self.assertEqual(analysis.values()["Text7"], "Vert")
        self.assertNotIn("favourite_colour", self.processor.data_store)
        self.assertEqual(len(self.processor.alias_store), 0)

    def test_ignorer(self) -> None:
        analysis = self.processor.analyze(self.pdf)
        colour = self._field(analysis.fields, "Text7")
        self.processor.skip(analysis, colour)
        self.assertNotIn(colour, analysis.pending)
        self.assertNotIn("Text7", analysis.values())

    def test_traitement_complet(self) -> None:
        questions: list[str] = []

        def resolver(field: FormField, position: int, total: int, suggested_key: str) -> Resolution | None:
            questions.append(field.name)
            self.assertEqual(total, 4)
            if field.name == "consent":
                return Resolution("Oui", save=False)
            if field.name == "Text8":
                return None  # Ignoré
            return Resolution("valeur", save=False)

        analysis, result = self.processor.process(self.pdf, self.out_dir, resolver)
        self.assertEqual(len(questions), 4)
        assert result.output_path is not None
        self.assertEqual(result.output_path.name, "formulaire_rempli.pdf")
        self.assertEqual(result.errors, {})

        values = {f.name: f.current_value for f in PdfEngine().list_fields(result.output_path)}
        self.assertEqual(values["Text1"], "Dupont")
        self.assertEqual(values["f2"], "Jean")
        self.assertEqual(values["country_list"], "France")
        self.assertEqual(values["consent"], "Yes")
        self.assertEqual(values["Text8"], "")
        self.assertEqual(values["reference"], "REF-123")
        self.assertEqual(values["gender"], "Male")  # « Homme » -> bouton « Male » coché

    def test_annulation(self) -> None:
        def resolver(*_: object) -> Resolution | None:
            raise ProcessingCancelled()

        with self.assertRaises(ProcessingCancelled):
            self.processor.process(self.pdf, self.out_dir, resolver)
        self.assertFalse(self.out_dir.exists())


if __name__ == "__main__":
    unittest.main()
