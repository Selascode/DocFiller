# DocFiller

Application locale qui remplit automatiquement des formulaires PDF (AcroForm)
à partir d'une base de données personnelle `data.json`, et qui apprend les champs inconnus.

## Fonctionnalités

- **Glisser-déposer** d'un PDF (ou clic pour parcourir), choix du dossier de destination.
- **Correspondance intelligente et multilingue**, entièrement hors ligne :
  - intitulés en français, anglais, espagnol, allemand, italien et portugais (`Surname`, `Apellido` → `nom`) ;
  - lecture du texte imprimé à côté des champs **et** des identifiants techniques (`infosPerso-nomUsage`) ;
  - valeurs calculées : nom complet, date du jour, jour/mois/année de naissance, adresse complète ;
  - tolérance aux fautes de frappe ; traduction des choix (« Homme » → « Male » / « H »).
- **Apprentissage actif** : pour chaque champ inconnu, une boîte de dialogue demande la valeur
  et propose de la sauvegarder pour les futurs documents (avec la clé standard suggérée).
- Le PDF d'origine n'est jamais modifié : `document_rempli.pdf`, `document_rempli_2.pdf`...
- Formulaires hybrides XFA (cerfa) : la couche XFA est retirée du PDF généré pour que tous les lecteurs affichent les valeurs.

> Les PDF « plats » (sans champs interactifs, simples scans ou impressions) ne sont pas encore pris en charge.

## Structure

```
docfiller/
  core/                 # Logique métier, sans dépendance à l'UI (réutilisable sur mobile)
    data_store.py       # Lecture / écriture / mise à jour des fichiers JSON
    pdf_engine.py       # Lecture des champs AcroForm et génération du PDF rempli
    matcher.py          # Correspondance champs PDF <-> données
    synonyms.py         # Dictionnaire multilingue (à enrichir librement)
    processor.py        # Orchestration : analyse -> champs manquants -> génération
    report.py           # Compte rendu textuel
  ui/desktop/           # Interface CustomTkinter (fenêtre principale + dialogues)
  cli.py                # Ligne de commande
data/
  data.example.json     # Exemple ; data.json, aliases.json, settings.json ne sont pas versionnés
tests/
```

## Installation

```bash
# Linux : Tkinter est fourni par le paquet système (ex. sudo apt install python3-tk)
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp data/data.example.json data/data.json   # puis renseignez vos informations
```

## Utilisation

```bash
python -m docfiller                         # Interface graphique
python -m docfiller formulaire.pdf          # ... avec un PDF préchargé

python -m docfiller.cli champs formulaire.pdf              # Lister les champs
python -m docfiller.cli remplir formulaire.pdf -o sortie/  # Remplir (questions dans le terminal)
```

Les données sont lues dans `data/` ; la variable d'environnement `DOCFILLER_DATA_DIR` permet d'utiliser un autre dossier.

| Fichier | Contenu |
|---|---|
| `data.json` | Vos informations : `{"nom": "Dupont", "prenom": "Jean", ...}` |
| `aliases.json` | Correspondances apprises : intitulé de champ → clé de `data.json` |
| `settings.json` | Préférences de l'interface (dernier dossier de destination) |

## Tests

```bash
python -m unittest -v
python -m tests.sample_form formulaire_test.pdf   # Formulaire d'essai (en anglais) pour tester l'interface
```

## Préparation mobile

Le cœur (`docfiller/core`) n'importe aucune bibliothèque graphique, accepte des PDF sous forme d'octets
(`analyze(bytes)`, `generate_bytes()`) et découpe le traitement en phases non bloquantes
(`analyze` → `resolve`/`skip` → `generate`), adaptées à une interface mobile événementielle.
