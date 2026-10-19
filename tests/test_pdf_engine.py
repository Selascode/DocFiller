"""Tests du moteur PDF (Étape 2)."""

import tempfile
import unittest
from pathlib import Path

import pymupdf

from docfiller.core import (
    FieldType,
    FormField,
    NoFormFieldsError,
    PdfCorruptedError,
    PdfEngine,
    PdfNotFoundError,
    PdfWriteError,
)
from docfiller.core.synonyms import VALUE_EQUIVALENTS
from tests.sample_form import build_plain_pdf, build_sample_form


class TestPdfEngine(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.pdf = self.tmp / "formulaire.pdf"
        build_sample_form(self.pdf)
        self.engine = PdfEngine(VALUE_EQUIVALENTS)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _values_of(self, path: Path) -> dict[str, str]:
        return {f.name: f.current_value for f in self.engine.list_fields(path)}

    # --- Lecture ------------------------------------------------------- #
    def test_liste_des_champs(self) -> None:
        fields = {f.name: f for f in self.engine.list_fields(self.pdf)}
        self.assertEqual(len(fields), 12)  # « Text1 » présent sur 2 pages, compté une fois
        self.assertEqual(fields["country_list"].field_type, FieldType.COMBOBOX)
        self.assertEqual(fields["country_list"].options, ("France", "Germany", "Spain"))
        self.assertEqual(fields["consent"].field_type, FieldType.CHECKBOX)
        self.assertTrue(fields["reference"].read_only)
        self.assertFalse(fields["reference"].is_fillable)

    def test_intitules(self) -> None:
        fields = {f.name: f for f in self.engine.list_fields(self.pdf)}
        # Intitulé lu sur la page, à gauche du champ.
        self.assertEqual(fields["Text1"].nearby_text, "Last name")
        self.assertEqual(fields["Text1"].display_label, "Last name")
        # L'info-bulle est prioritaire.
        self.assertEqual(fields["f2"].display_label, "First name")
        # Nom technique rendu lisible.
        self.assertIn("Date Of Birth", fields["topmostSubform[0].Page1[0].DateOfBirth[0]"].label_candidates)
        # Les noms génériques ne sont pas des intitulés.
        self.assertNotIn("Text1", fields["Text1"].label_candidates)

    def test_source_en_octets(self) -> None:
        self.assertEqual(len(self.engine.list_fields(self.pdf.read_bytes())), 12)

    # --- Remplissage --------------------------------------------------- #
    def test_remplissage(self) -> None:
        output = self.tmp / "sortie" / "rempli.pdf"
        result = self.engine.fill(
            self.pdf,
            {"Text1": "Dupont", "country_list": "Allemagne", "consent": "Oui", "inexistant": "x"},
            output,
        )
        self.assertEqual(result.output_path, output)
        self.assertCountEqual(result.filled, ["Text1", "country_list", "consent"])
        self.assertIn("inexistant", result.errors)

        values = self._values_of(output)
        self.assertEqual(values["Text1"], "Dupont")
        self.assertEqual(values["country_list"], "Germany")  # « Allemagne » traduit
        self.assertEqual(values["consent"], "Yes")
        # Le fichier d'origine n'est pas modifié.
        self.assertEqual(self._values_of(self.pdf)["Text1"], "")

    def test_boutons_radio(self) -> None:
        gender = next(f for f in self.engine.list_fields(self.pdf) if f.name == "gender")
        self.assertEqual(gender.field_type, FieldType.RADIO)
        self.assertEqual(gender.display_label, "Gender")
        self.assertEqual(gender.options, ("Male", "Female"))

        output = self.tmp / "out.pdf"
        result = self.engine.fill(self.pdf, {"gender": "Femme"}, output)
        self.assertEqual(result.errors, {})
        doc = pymupdf.open(output)
        states = [doc.xref_get_key(w.xref, "AS")[1] for w in doc[1].widgets() if w.field_name == "gender"]
        doc.close()
        self.assertEqual(states, ["/Off", "/Yes"])

    def test_champ_sur_plusieurs_pages(self) -> None:
        output = self.tmp / "out.pdf"
        self.engine.fill(self.pdf, {"Text1": "Dupont"}, output)
        doc = pymupdf.open(output)
        values = [w.field_value for page in doc for w in page.widgets() if w.field_name == "Text1"]
        doc.close()
        self.assertEqual(values, ["Dupont", "Dupont"])

    def test_suppression_couche_xfa(self) -> None:
        # Simule un formulaire hybride AcroForm + XFA (fréquent sur les cerfa).
        doc = pymupdf.open(self.pdf)
        doc.xref_set_key(doc.pdf_catalog(), "AcroForm/XFA", "(xfa factice)")
        hybrid = self.tmp / "hybride.pdf"
        doc.save(hybrid)
        doc.close()

        output = self.tmp / "out.pdf"
        self.engine.fill(hybrid, {"Text1": "Dupont"}, output)
        doc = pymupdf.open(output)
        self.assertEqual(doc.xref_get_key(doc.pdf_catalog(), "AcroForm/XFA")[0], "null")
        self.assertEqual(len(list(doc[0].widgets())), 11)  # Le formulaire reste intact
        doc.close()

    def test_intitules_techniques(self) -> None:
        field = FormField(
            name="topmostSubform[0].Page1[0].infosPerso-identite-info-nomUsage[0]",
            field_type=FieldType.TEXT,
            page=0,
            tooltip="infosPerso-identite-info-nomUsage",
            nearby_text="NOM D'USAGE",
        )
        # Le texte imprimé passe avant l'identifiant technique.
        self.assertEqual(field.display_label, "NOM D'USAGE")
        self.assertIn("nom Usage", field.label_candidates)

    def test_choix_impossible(self) -> None:
        result = self.engine.fill(self.pdf, {"country_list": "Japon"}, self.tmp / "out.pdf")
        self.assertIn("country_list", result.errors)

    def test_case_non_cochee(self) -> None:
        output = self.tmp / "out.pdf"
        self.engine.fill(self.pdf, {"consent": "Non"}, output)
        self.assertEqual(self._values_of(output)["consent"], "Off")

    def test_remplissage_en_memoire(self) -> None:
        data, result = self.engine.fill_to_bytes(self.pdf, {"Text1": "Dupont"})
        self.assertEqual(result.filled, ["Text1"])
        self.assertEqual({f.name: f.current_value for f in self.engine.list_fields(data)}["Text1"], "Dupont")

    def test_refus_ecraser_original(self) -> None:
        with self.assertRaises(PdfWriteError):
            self.engine.fill(self.pdf, {"Text1": "x"}, self.pdf)

    def test_chemin_de_sortie_sans_ecrasement(self) -> None:
        first = PdfEngine.build_output_path("formulaire.pdf", self.tmp)
        self.assertEqual(first.name, "formulaire_rempli.pdf")
        first.write_bytes(b"")
        self.assertEqual(PdfEngine.build_output_path("formulaire.pdf", self.tmp).name, "formulaire_rempli_2.pdf")

    # --- Erreurs ------------------------------------------------------- #
    def test_fichier_introuvable(self) -> None:
        with self.assertRaises(PdfNotFoundError):
            self.engine.list_fields(self.tmp / "absent.pdf")

    def test_pdf_corrompu(self) -> None:
        corrupted = self.tmp / "corrompu.pdf"
        corrupted.write_bytes(b"ceci n'est pas un PDF")
        with self.assertRaises(PdfCorruptedError):
            self.engine.list_fields(corrupted)

    def test_fichier_texte(self) -> None:
        text_file = self.tmp / "notes.txt"
        text_file.write_text("Bonjour", encoding="utf-8")
        with self.assertRaises(PdfCorruptedError):
            self.engine.list_fields(text_file)

    def test_pdf_sans_formulaire(self) -> None:
        with self.assertRaises(NoFormFieldsError):
            self.engine.list_fields(build_plain_pdf())


if __name__ == "__main__":
    unittest.main()
