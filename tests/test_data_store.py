"""Tests unitaires du moteur de données (`DataStore`)."""

import json
import tempfile
import unittest
from pathlib import Path

from docfiller.core import (
    DataCorruptedError,
    DataStore,
    InvalidKeyError,
    normalize_key,
)


class TestNormalizeKey(unittest.TestCase):
    def test_accents_casse_espaces(self) -> None:
        self.assertEqual(normalize_key("  Prénom "), "prenom")
        self.assertEqual(normalize_key("Code Postal"), "code_postal")
        self.assertEqual(normalize_key("Date-de-naissance"), "date_de_naissance")

    def test_cle_vide(self) -> None:
        with self.assertRaises(InvalidKeyError):
            normalize_key("   ")
        with self.assertRaises(InvalidKeyError):
            normalize_key("!!!")


class TestDataStore(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "data.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_fichier_absent_cree_base_vide(self) -> None:
        store = DataStore(self.path)
        self.assertTrue(self.path.exists())
        self.assertEqual(len(store), 0)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), {})

    def test_set_get_et_persistance(self) -> None:
        store = DataStore(self.path)
        store.set("Nom", "Dupont")
        store["Adresse"] = "1 rue de la Lune"

        # Recharge depuis le disque : les données doivent être conservées.
        reloaded = DataStore(self.path)
        self.assertEqual(reloaded.get("nom"), "Dupont")
        self.assertEqual(reloaded["ADRESSE"], "1 rue de la Lune")
        self.assertIn("adresse", reloaded)

    def test_update_et_delete(self) -> None:
        store = DataStore(self.path)
        store.update({"ville": "Paris", "Code postal": 75000})
        self.assertEqual(store.get("code_postal"), "75000")
        self.assertTrue(store.delete("Ville"))
        self.assertFalse(store.delete("ville"))
        self.assertEqual(store.keys(), ["code_postal"])

    def test_json_corrompu_non_ecrase(self) -> None:
        self.path.write_text("{ ceci n'est pas du json", encoding="utf-8")
        with self.assertRaises(DataCorruptedError):
            DataStore(self.path)
        # Le fichier d'origine doit rester intact.
        self.assertEqual(self.path.read_text(encoding="utf-8"), "{ ceci n'est pas du json")

    def test_racine_non_objet(self) -> None:
        self.path.write_text("[1, 2, 3]", encoding="utf-8")
        with self.assertRaises(DataCorruptedError):
            DataStore(self.path)

    def test_fichier_vide(self) -> None:
        self.path.write_text("", encoding="utf-8")
        self.assertEqual(len(DataStore(self.path)), 0)

    def test_nettoyage_contenu_edite_a_la_main(self) -> None:
        self.path.write_text(
            json.dumps({"Prénom": "Jean", "age": 42, "liste": [1, 2], "": "x"}),
            encoding="utf-8",
        )
        store = DataStore(self.path)
        self.assertEqual(store.as_dict(), {"prenom": "Jean", "age": "42"})

    def test_sans_autosave(self) -> None:
        store = DataStore(self.path, autosave=False)
        store.set("nom", "Dupont")
        self.assertNotIn("nom", DataStore(self.path))
        store.save()
        self.assertIn("nom", DataStore(self.path))

    def test_backup(self) -> None:
        store = DataStore(self.path)
        store.set("nom", "Dupont")
        backup = store.backup()
        self.assertEqual(json.loads(backup.read_text(encoding="utf-8")), {"nom": "Dupont"})


if __name__ == "__main__":
    unittest.main()
