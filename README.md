# DocFiller

Application locale qui remplit automatiquement des formulaires PDF (AcroForm)
à partir d'une base de données personnelle `data.json`, et qui apprend les champs inconnus.

## Structure

```
docfiller/
  core/            # Logique métier, sans dépendance à l'UI (réutilisable sur mobile)
    data_store.py  # Lecture / écriture / mise à jour de data.json
    exceptions.py  # Exceptions métier
data/
  data.example.json  # Exemple de base (data.json réel non versionné)
tests/
```

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Utilisation du moteur de données

```python
from docfiller.core import DataStore

store = DataStore("data/data.json")   # créé s'il n'existe pas
store.set("Prénom", "Jean")           # clé normalisée en "prenom"
print(store.get("prenom"))            # -> "Jean"
```

## Tests

```bash
python3 -m unittest discover -s tests -v
```
