"""Moteur de données : lecture, écriture et mise à jour du fichier `data.json`.

Ce module est volontairement indépendant de toute interface graphique
(aucun import Tkinter/Qt/Kivy) afin d'être réutilisable tel quel
sur desktop comme sur mobile. Le chemin du fichier est injecté
par l'appelant : sur Android/iOS, il pointera vers le dossier
de stockage privé de l'application.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import threading
import unicodedata
from pathlib import Path
from typing import Iterator, Mapping

from docfiller.core.exceptions import (
    DataCorruptedError,
    DataStoreError,
    InvalidKeyError,
)

# Type des données stockées : paires clé -> valeur, toutes en texte.
DataDict = dict[str, str]


def normalize_key(key: str) -> str:
    """Normalise une clé pour la rendre comparable.

    - suppression des accents (« Prénom » -> « prenom ») ;
    - passage en minuscules ;
    - tout caractère non alphanumérique devient « _ ».

    Exemple : "  Code Postal " -> "code_postal".

    Raises:
        InvalidKeyError: si la clé est vide après normalisation.
    """
    if not isinstance(key, str):
        raise InvalidKeyError(f"La clé doit être une chaîne, reçu : {type(key).__name__}")

    # Décomposition Unicode puis suppression des diacritiques.
    decomposed = unicodedata.normalize("NFKD", key)
    without_accents = "".join(c for c in decomposed if not unicodedata.combining(c))

    normalized = re.sub(r"[^a-z0-9]+", "_", without_accents.lower()).strip("_")
    if not normalized:
        raise InvalidKeyError(f"Clé invalide : {key!r}")
    return normalized


class DataStore:
    """Gestionnaire de la base de données personnelle au format JSON.

    Le fichier est un simple objet JSON plat : {"nom": "Dupont", ...}.
    Les clés sont normalisées (voir `normalize_key`) à l'écriture et à la lecture,
    les valeurs sont toujours stockées sous forme de texte.

    Les écritures sont atomiques (fichier temporaire + remplacement)
    pour éviter de corrompre les données en cas de crash ou de coupure.
    """

    def __init__(self, path: str | Path, autosave: bool = True) -> None:
        """
        Args:
            path: chemin du fichier JSON. Créé automatiquement s'il n'existe pas.
            autosave: si True, chaque modification est immédiatement écrite sur disque.
        """
        self._path: Path = Path(path)
        self._autosave: bool = autosave
        self._data: DataDict = {}
        # Verrou : l'UI lancera le traitement PDF dans un thread séparé.
        self._lock = threading.RLock()
        self.load()

    # ------------------------------------------------------------------ #
    # Propriétés
    # ------------------------------------------------------------------ #
    @property
    def path(self) -> Path:
        """Chemin du fichier JSON géré."""
        return self._path

    # ------------------------------------------------------------------ #
    # Chargement / sauvegarde
    # ------------------------------------------------------------------ #
    def load(self) -> None:
        """Charge le fichier JSON en mémoire.

        - Fichier absent : une base vide est créée sur disque.
        - Fichier vide : considéré comme une base vide.
        - JSON invalide ou racine non-objet : `DataCorruptedError`
          (le fichier n'est jamais écrasé dans ce cas).

        Raises:
            DataCorruptedError: contenu illisible.
            DataStoreError: problème d'accès disque (droits, etc.).
        """
        with self._lock:
            if not self._path.exists():
                self._data = {}
                self.save()
                return

            try:
                raw = self._path.read_text(encoding="utf-8")
            except OSError as exc:
                raise DataStoreError(f"Impossible de lire {self._path} : {exc}") from exc

            if not raw.strip():
                self._data = {}
                return

            try:
                content = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise DataCorruptedError(
                    f"Le fichier {self._path} n'est pas un JSON valide "
                    f"(ligne {exc.lineno}, colonne {exc.colno})."
                ) from exc

            if not isinstance(content, dict):
                raise DataCorruptedError(
                    f"Le fichier {self._path} doit contenir un objet JSON {{...}}, "
                    f"pas un(e) {type(content).__name__}."
                )

            self._data = self._sanitize(content)

    def save(self) -> None:
        """Écrit les données sur disque de manière atomique.

        Raises:
            DataStoreError: en cas d'échec d'écriture.
        """
        with self._lock:
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                # Écriture dans un fichier temporaire du même dossier, puis remplacement
                # atomique : le fichier d'origine n'est jamais à moitié écrit.
                fd, tmp_name = tempfile.mkstemp(
                    dir=self._path.parent, prefix=f".{self._path.name}.", suffix=".tmp"
                )
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
                        json.dump(self._data, tmp_file, ensure_ascii=False, indent=2, sort_keys=True)
                        tmp_file.write("\n")
                    os.replace(tmp_name, self._path)
                except BaseException:
                    Path(tmp_name).unlink(missing_ok=True)
                    raise
            except OSError as exc:
                raise DataStoreError(f"Impossible d'écrire {self._path} : {exc}") from exc

    def backup(self) -> Path:
        """Crée une copie de sauvegarde `data.json.bak` à côté du fichier.

        Returns:
            Le chemin de la sauvegarde.
        """
        with self._lock:
            backup_path = self._path.with_suffix(self._path.suffix + ".bak")
            try:
                shutil.copy2(self._path, backup_path)
            except OSError as exc:
                raise DataStoreError(f"Impossible de sauvegarder {self._path} : {exc}") from exc
            return backup_path

    # ------------------------------------------------------------------ #
    # Accès aux données
    # ------------------------------------------------------------------ #
    def get(self, key: str, default: str | None = None) -> str | None:
        """Retourne la valeur associée à `key` (clé normalisée), ou `default`."""
        try:
            normalized = normalize_key(key)
        except InvalidKeyError:
            return default
        with self._lock:
            return self._data.get(normalized, default)

    def set(self, key: str, value: object) -> None:
        """Ajoute ou met à jour une paire clé/valeur.

        Args:
            key: intitulé du champ (sera normalisé).
            value: valeur à stocker (convertie en texte).

        Raises:
            InvalidKeyError: clé vide ou invalide.
        """
        normalized = normalize_key(key)
        with self._lock:
            self._data[normalized] = self._to_text(value)
            self._autosave_if_needed()

    def update(self, values: Mapping[str, object]) -> None:
        """Ajoute ou met à jour plusieurs paires en une seule écriture disque."""
        prepared = {normalize_key(k): self._to_text(v) for k, v in values.items()}
        with self._lock:
            self._data.update(prepared)
            self._autosave_if_needed()

    def delete(self, key: str) -> bool:
        """Supprime une clé.

        Returns:
            True si la clé existait, False sinon.
        """
        try:
            normalized = normalize_key(key)
        except InvalidKeyError:
            return False
        with self._lock:
            if normalized not in self._data:
                return False
            del self._data[normalized]
            self._autosave_if_needed()
            return True

    def keys(self) -> list[str]:
        """Liste triée des clés connues (utile pour la correspondance à l'étape 3)."""
        with self._lock:
            return sorted(self._data)

    def as_dict(self) -> DataDict:
        """Copie des données (la modifier n'affecte pas la base)."""
        with self._lock:
            return dict(self._data)

    # ------------------------------------------------------------------ #
    # Méthodes spéciales (confort d'utilisation)
    # ------------------------------------------------------------------ #
    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and self.get(key) is not None

    def __getitem__(self, key: str) -> str:
        value = self.get(key)
        if value is None:
            raise KeyError(key)
        return value

    def __setitem__(self, key: str, value: object) -> None:
        self.set(key, value)

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)

    def __iter__(self) -> Iterator[str]:
        return iter(self.keys())

    def __repr__(self) -> str:
        return f"DataStore(path={str(self._path)!r}, entries={len(self)})"

    # ------------------------------------------------------------------ #
    # Utilitaires internes
    # ------------------------------------------------------------------ #
    def _autosave_if_needed(self) -> None:
        if self._autosave:
            self.save()

    @staticmethod
    def _to_text(value: object) -> str:
        """Convertit une valeur en texte (les formulaires PDF n'acceptent que du texte)."""
        if value is None:
            return ""
        if isinstance(value, bool):
            return "Oui" if value else "Non"
        return str(value).strip()

    @classmethod
    def _sanitize(cls, content: dict[object, object]) -> DataDict:
        """Nettoie le contenu lu sur disque (fichier éventuellement édité à la main).

        Les clés invalides ou les valeurs complexes (listes, objets) sont ignorées
        plutôt que de bloquer toute l'application.
        """
        clean: DataDict = {}
        for raw_key, raw_value in content.items():
            if not isinstance(raw_key, str) or isinstance(raw_value, (dict, list)):
                continue
            try:
                clean[normalize_key(raw_key)] = cls._to_text(raw_value)
            except InvalidKeyError:
                continue
        return clean
