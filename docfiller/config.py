"""Configuration : emplacement des fichiers de données.

Sur desktop (exécution depuis les sources), les données sont dans `data/`
à la racine du projet. La variable d'environnement `DOCFILLER_DATA_DIR`
permet de les déplacer ; sur mobile, l'application fournira directement
le dossier privé de l'app à `DocumentProcessor.from_directory()`.
"""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "DocFiller"

DATA_FILENAME = "data.json"  # Données personnelles
ALIASES_FILENAME = "aliases.json"  # Correspondances apprises (intitulé -> clé)
SETTINGS_FILENAME = "settings.json"  # Préférences de l'interface


def default_data_dir() -> Path:
    """Dossier où sont stockés data.json, aliases.json et settings.json."""
    env_dir = os.environ.get("DOCFILLER_DATA_DIR")
    if env_dir:
        return Path(env_dir).expanduser()
    return Path(__file__).resolve().parent.parent / "data"
