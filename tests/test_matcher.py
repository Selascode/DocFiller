"""Tests de la correspondance champs PDF <-> données (Étape 3)."""

import unittest
from datetime import date

from docfiller.core import FieldMatcher, FieldType, FormField, MatchMethod
from docfiller.core.synonyms import FIELD_SYNONYMS, VALUE_EQUIVALENTS
from docfiller.core.text_utils import (
    best_option,
    canonical_text,
    is_generic_name,
    looks_technical,
    technical_labels,
)

DATA = {
    "nom": "Dupont",
    "prenom": "Jean",
    "date_naissance": "01/02/1990",
    "adresse": "1 rue de la Lune",
    "code_postal": "75000",
    "ville": "Paris",
    "couleur_preferee": "Bleu",
}


def text_field(label: str, name: str = "Text1") -> FormField:
    """Champ texte dont l'intitulé est lu sur la page."""
    return FormField(name=name, field_type=FieldType.TEXT, page=0, nearby_text=label)


class TestTextUtils(unittest.TestCase):
    def test_canonical_text(self) -> None:
        self.assertEqual(canonical_text("Votre N° de téléphone :"), "telephone")
        self.assertEqual(canonical_text("Date of birth"), "date birth")

    def test_marques_d_accord(self) -> None:
        self.assertEqual(canonical_text("NÉ(E) LE"), "ne")
        self.assertEqual(canonical_text("PRÉNOM(S)"), "prenom")

    def test_identifiants_techniques(self) -> None:
        self.assertTrue(looks_technical("infosPerso-identite-info-nomUsage"))
        self.assertFalse(looks_technical("Nom d'usage"))
        self.assertEqual(technical_labels("infosPerso-identite-info-prenoms-concat"), ["prenoms"])
        self.assertEqual(technical_labels("infosPerso-contactPerso-info-mail1"), ["mail"])
        self.assertEqual(technical_labels("adresseDomicile-Complement2")[0], "Complement 2")
        self.assertEqual(technical_labels("topmostSubform[0].Page1[0].DateOfBirth[0]")[0], "Date Of Birth")
        self.assertEqual(technical_labels("Nom  de l'institution"), ["Nom de l'institution"])

    def test_noms_generiques(self) -> None:
        for name in ("Text1", "Champ 12", "f2", "CheckBox3"):
            self.assertTrue(is_generic_name(name), name)
        self.assertFalse(is_generic_name("LastName"))

    def test_best_option_multilingue(self) -> None:
        self.assertEqual(best_option("Homme", ["Male", "Female"], VALUE_EQUIVALENTS), "Male")
        self.assertEqual(best_option("M.", ["Frau", "Herr"], VALUE_EQUIVALENTS), "Herr")
        self.assertEqual(best_option("francee", ["France", "Spain"]), "France")
        self.assertIsNone(best_option("Japon", ["France", "Spain"]))


class TestFieldMatcher(unittest.TestCase):
    def setUp(self) -> None:
        self.matcher = FieldMatcher()

    def assertMatch(self, label: str, key: str, method: MatchMethod, data: dict[str, str] = DATA) -> None:
        found = self.matcher.match(text_field(label), data)
        self.assertIsNotNone(found, f"Aucune correspondance pour « {label} »")
        assert found is not None
        self.assertEqual((found.key, found.method), (key, method), label)

    def test_exacte(self) -> None:
        self.assertMatch("Code postal :", "code_postal", MatchMethod.EXACT)
        self.assertMatch("Date de naissance", "date_naissance", MatchMethod.EXACT)
        self.assertMatch("Couleur préférée", "couleur_preferee", MatchMethod.EXACT)

    def test_synonymes_multilingues(self) -> None:
        cas = {
            "Surname": "nom",
            "Apellido": "nom",
            "Nachname": "nom",
            "Cognome": "nom",
            "Given name": "prenom",
            "Vorname": "prenom",
            "Fecha de nacimiento": "date_naissance",
            "Geburtsdatum": "date_naissance",
            "Postleitzahl": "code_postal",
            "ZIP code": "code_postal",
            "Città": "ville",
            "Street address": "adresse",
        }
        for label, key in cas.items():
            self.assertMatch(label, key, MatchMethod.SYNONYM)

    def test_cle_utilisateur_non_standard(self) -> None:
        # La clé « nom_de_famille » est reconnue comme le concept « nom ».
        self.assertMatch("Last name", "nom_de_famille", MatchMethod.SYNONYM, {"nom_de_famille": "Martin"})

    def test_valeurs_calculees(self) -> None:
        found = self.matcher.match(text_field("Full name"), DATA)
        assert found is not None
        self.assertEqual((found.value, found.method), ("Jean Dupont", MatchMethod.DERIVED))

        found = self.matcher.match(text_field("Fait le"), DATA)
        assert found is not None
        self.assertEqual(found.value, date.today().strftime("%d/%m/%Y"))

        found = self.matcher.match(text_field("Fait à"), DATA)
        assert found is not None
        self.assertEqual(found.value, "Paris")

    def test_approximative(self) -> None:
        self.assertMatch("Adrese", "adresse", MatchMethod.FUZZY)

    def test_pas_de_faux_positif(self) -> None:
        for label in ("Nom du père", "Date de naissance du conjoint", "Non", "Favourite colour", "Téléphone"):
            self.assertIsNone(self.matcher.match(text_field(label), DATA), label)

    def test_alias_appris(self) -> None:
        aliases = {"surnom": "prenom"}
        found = self.matcher.match(text_field("Surnom"), DATA, aliases)
        assert found is not None
        self.assertEqual((found.key, found.method), ("prenom", MatchMethod.LEARNED))

    def test_valeur_vide_ignoree(self) -> None:
        self.assertIsNone(self.matcher.match(text_field("Nom"), {"nom": "  "}))

    def test_intitule_le_plus_specifique(self) -> None:
        # Cerfa : texte imprimé « NÉ(E) LE » mais identifiant « ...-jourNaissance ».
        day = FormField(
            name="topmostSubform[0].Page1[0].infosPerso-identite-info-dateNaissanceTriple-jourNaissance[0]",
            field_type=FieldType.TEXT,
            page=0,
            tooltip="infosPerso-identite-info-dateNaissanceTriple-jourNaissance",
            nearby_text="NÉ(E) LE",
        )
        found = self.matcher.match(day, DATA)
        assert found is not None
        self.assertEqual((found.key, found.value), ("jour_naissance", "01"))
        self.assertEqual(self.matcher.suggest_concept(day), "jour_naissance")

    def test_concept_precis_sans_donnee(self) -> None:
        # « Pays » imprimé, mais l'identifiant indique le pays de NAISSANCE : on ne
        # remplit pas avec le pays de résidence, le champ sera demandé.
        birth_country = FormField(
            name="infosPerso-identite-info-paysNaissance", field_type=FieldType.TEXT, page=0, nearby_text="PAYS"
        )
        self.assertIsNone(self.matcher.match(birth_country, {**DATA, "pays": "France"}))

    def test_valeurs_calculees_avancees(self) -> None:
        for label, value in {"Mois de naissance": "02", "Year of birth": "1990"}.items():
            found = self.matcher.match(text_field(label), DATA)
            assert found is not None
            self.assertEqual(found.value, value, label)
        found = self.matcher.match(text_field("Adresse, ville, pays"), {**DATA, "pays": "France"})
        assert found is not None
        self.assertEqual(found.value, "1 rue de la Lune, 75000 Paris, France")

    def test_synonymes_sans_conflit(self) -> None:
        # Un même terme ne doit pas désigner deux concepts différents.
        seen: dict[str, str] = {}
        for concept, terms in FIELD_SYNONYMS.items():
            for term in (concept.replace("_", " "), *terms):
                canon = canonical_text(term)
                self.assertEqual(seen.setdefault(canon, concept), concept, f"« {term} » : {seen[canon]} / {concept}")

    def test_concept_for(self) -> None:
        self.assertEqual(self.matcher.concept_for("Correo electrónico"), "email")
        self.assertIsNone(self.matcher.concept_for("Couleur préférée"))


if __name__ == "__main__":
    unittest.main()
