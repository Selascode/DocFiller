"""Exceptions métier de DocFiller.

Toutes les erreurs propres à l'application héritent de `DocFillerError`,
ce qui permet à l'interface (desktop ou mobile) de les intercepter
de manière uniforme pour afficher un message à l'utilisateur.
"""


class DocFillerError(Exception):
    """Classe de base de toutes les erreurs DocFiller."""


class DataStoreError(DocFillerError):
    """Erreur générique liée à la base de données JSON."""


class DataCorruptedError(DataStoreError):
    """Le fichier JSON existe mais son contenu est illisible ou mal structuré."""


class InvalidKeyError(DataStoreError):
    """La clé fournie est vide ou invalide après normalisation."""
