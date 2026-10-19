"""Exceptions métier de DocFiller.

Toutes les erreurs propres à l'application héritent de `DocFillerError`,
ce qui permet à l'interface (desktop ou mobile) de les intercepter
de manière uniforme pour afficher un message à l'utilisateur.
"""


class DocFillerError(Exception):
    """Classe de base de toutes les erreurs DocFiller."""


# --------------------------------------------------------------------------- #
# Base de données JSON
# --------------------------------------------------------------------------- #
class DataStoreError(DocFillerError):
    """Erreur générique liée à la base de données JSON."""


class DataCorruptedError(DataStoreError):
    """Le fichier JSON existe mais son contenu est illisible ou mal structuré."""


class InvalidKeyError(DataStoreError):
    """La clé fournie est vide ou invalide après normalisation."""


# --------------------------------------------------------------------------- #
# Moteur PDF
# --------------------------------------------------------------------------- #
class PdfError(DocFillerError):
    """Erreur générique liée à un fichier PDF."""


class PdfNotFoundError(PdfError):
    """Le fichier PDF source n'existe pas."""


class PdfCorruptedError(PdfError):
    """Le fichier n'est pas un PDF valide (corrompu ou mauvais format)."""


class PdfEncryptedError(PdfError):
    """Le PDF est protégé par un mot de passe."""


class NoFormFieldsError(PdfError):
    """Le PDF ne contient aucun champ de formulaire interactif (AcroForm)."""


class PdfWriteError(PdfError):
    """Impossible d'écrire le PDF généré."""


# --------------------------------------------------------------------------- #
# Traitement
# --------------------------------------------------------------------------- #
class ProcessingCancelled(DocFillerError):
    """L'utilisateur a annulé le traitement en cours."""
