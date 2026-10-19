"""Dictionnaire multilingue des intitulés de formulaires administratifs.

Chaque concept (clé canonique, en français, utilisée dans `data.json`)
est associé à ses variantes en français, anglais, espagnol, allemand,
italien et portugais. Ainsi, un champ « Surname » ou « Apellido »
est relié à la donnée `nom`, sans connexion Internet.

Pour enrichir la reconnaissance, il suffit d'ajouter des termes ici.
Les termes sont normalisés automatiquement (accents, casse, ponctuation).
"""

from __future__ import annotations

# Concept -> variantes (le concept lui-même est implicitement inclus).
FIELD_SYNONYMS: dict[str, tuple[str, ...]] = {
    "nom": (
        "nom de famille", "nom d'usage", "nom usuel",
        "last name", "lastname", "surname", "family name",
        "apellido", "apellidos", "primer apellido",
        "nachname", "familienname",
        "cognome", "sobrenome", "achternaam",
    ),
    "prenom": (
        "prénom", "prénoms", "premier prénom",
        "first name", "firstname", "given name", "given names", "forename",
        "nombre", "nombre de pila",
        "vorname", "vornamen",
        "nome", "nome proprio", "primeiro nome", "voornaam",
    ),
    "nom_complet": (
        "nom complet", "nom et prénom", "nom prénom", "prénom et nom", "prénom nom", "identité",
        "full name", "name", "complete name", "name and surname",
        "nombre completo", "nombre y apellidos",
        "vollständiger name", "vor und nachname", "vorname und nachname",
        "nome completo", "nome e cognome",
    ),
    "nom_naissance": (
        "nom de naissance", "nom de jeune fille",
        "birth name", "maiden name", "name at birth",
        "apellido de soltera", "geburtsname", "cognome da nubile", "nome de solteira",
    ),
    "civilite": (
        "civilité", "titre",
        "title", "salutation", "form of address",
        "tratamiento", "anrede", "titolo", "tratamento",
    ),
    "sexe": (
        "genre",
        "sex", "gender",
        "sexo", "geschlecht", "sesso", "género",
    ),
    "date_naissance": (
        "date de naissance", "né le", "née le", "né(e) le",
        "date of birth", "birth date", "birthdate", "dob", "born on",
        "fecha de nacimiento", "geburtsdatum", "geboren am",
        "data di nascita", "data de nascimento",
    ),
    "lieu_naissance": (
        "lieu de naissance", "ville de naissance", "commune de naissance", "né à", "née à", "né(e) à",
        "place of birth", "birthplace", "city of birth", "town of birth",
        "lugar de nacimiento", "geburtsort", "luogo di nascita", "local de nascimento",
    ),
    "jour_naissance": (
        "jour de naissance", "day of birth", "birth day", "día de nacimiento", "giorno di nascita",
    ),
    "mois_naissance": (
        "mois de naissance", "month of birth", "birth month", "mes de nacimiento", "geburtsmonat", "mese di nascita",
    ),
    "annee_naissance": (
        "année de naissance", "year of birth", "birth year", "año de nacimiento", "geburtsjahr", "anno di nascita",
    ),
    "pays_naissance": (
        "pays de naissance", "country of birth", "birth country",
        "país de nacimiento", "geburtsland", "paese di nascita", "país de nascimento",
    ),
    "departement_naissance": (
        "département de naissance", "code département de naissance", "département ou collectivité de naissance",
    ),
    "nationalite": (
        "nationalité",
        "nationality", "citizenship",
        "nacionalidad", "staatsangehörigkeit", "nationalität", "staatsbürgerschaft",
        "nazionalità", "cittadinanza", "nacionalidade",
    ),
    "situation_familiale": (
        "situation familiale", "situation matrimoniale", "état civil",
        "marital status", "civil status",
        "estado civil", "familienstand", "stato civile",
    ),
    "adresse": (
        "adresse postale", "adresse personnelle", "domicile", "adresse du domicile", "rue", "voie",
        "libellé de voie", "libellé voie", "lib voie", "nom de voie",
        "address", "street address", "home address", "address line 1", "street", "postal address",
        "dirección", "domicilio", "calle",
        "anschrift", "straße", "strasse", "straße und hausnummer", "wohnanschrift",
        "indirizzo", "via", "endereço", "morada", "adres",
    ),
    "adresse_complete": (
        "adresse complète", "adresse, ville, pays", "adresse postale complète", "adresse et ville",
        "full address", "complete address", "address, city, country",
        "dirección completa", "vollständige anschrift", "vollständige adresse", "indirizzo completo",
    ),
    "numero_voie": (
        "numéro de voie", "numéro de rue",
        "street number", "house number", "hausnummer", "número de calle", "numero civico",
    ),
    "complement_adresse": (
        "complément d'adresse", "complément", "bâtiment", "appartement",
        "address line 2", "apartment", "apt", "suite", "unit",
        "adresszusatz", "piso",
    ),
    "code_postal": (
        "cp", "code postal",
        "postal code", "zip", "zip code", "postcode", "post code",
        "código postal", "plz", "postleitzahl", "cap", "codice postale", "codigo postal",
    ),
    "ville": (
        "commune", "localité", "ville de résidence",
        "city", "town", "city town",
        "ciudad", "localidad", "población", "municipio",
        "stadt", "ort", "wohnort", "città", "comune", "cidade", "localidade",
    ),
    "region": (
        "région", "département", "province", "état",
        "region", "state", "county", "province state",
        "provincia", "estado", "comunidad autónoma",
        "bundesland", "regione", "distrito",
    ),
    "pays": (
        "pays de résidence",
        "country", "country of residence",
        "país", "land", "staat", "paese", "nazione",
    ),
    "telephone": (
        "téléphone", "tél", "tel", "numéro de téléphone", "portable", "téléphone portable", "mobile",
        "tél mobile", "tél portable", "téléphone mobile", "numéro de portable", "numéro de mobile",
        "phone", "phone number", "telephone", "telephone number", "mobile phone", "cell phone", "mobile number",
        "mobile phone number",
        "teléfono", "móvil", "celular",
        "telefon", "telefonnummer", "handy", "handynummer",
        "telefono", "cellulare", "telemóvel",
    ),
    "telephone_professionnel": (
        "téléphone professionnel", "tél professionnel", "tel pro", "tél bureau", "téléphone du bureau",
        "work phone", "office phone", "business phone", "work phone number", "work telephone",
        "teléfono del trabajo", "telefon geschäftlich", "dienstliche telefonnummer", "telefono ufficio",
    ),
    "email": (
        "e-mail", "mail", "courriel", "adresse email", "adresse e-mail", "adresse électronique", "adresse mail",
        "email address", "e-mail address",
        "correo", "correo electrónico", "e-mail-adresse", "posta elettronica", "indirizzo email",
    ),
    "profession": (
        "métier", "emploi", "fonction", "activité professionnelle", "poste",
        "occupation", "job", "job title", "position",
        "profesión", "ocupación", "beruf", "tätigkeit", "professione", "profissão",
    ),
    "employeur": (
        "entreprise", "société", "nom de l'employeur",
        "institution", "nom de l'institution", "organisme", "nom de l'organisme", "organisation",
        "organization", "organisation name", "organization name", "institution name",
        "employer", "company", "company name", "employer name",
        "empresa", "arbeitgeber", "firma", "azienda", "datore di lavoro",
    ),
    "numero_securite_sociale": (
        "numéro de sécurité sociale", "sécurité sociale", "nir", "numéro ss",
        "social security number", "ssn", "national insurance number",
        "número de seguridad social", "sozialversicherungsnummer",
    ),
    "numero_fiscal": (
        "numéro fiscal", "numéro d'identification fiscale", "numéro fiscal de référence",
        "tax id", "tax identification number", "tin",
        "nif", "steuernummer", "steuer id", "codice fiscale",
    ),
    "numero_passeport": (
        "numéro de passeport", "passeport",
        "passport number", "passport no", "passport",
        "número de pasaporte", "reisepassnummer", "numero di passaporto",
    ),
    "numero_carte_identite": (
        "numéro de carte d'identité", "carte nationale d'identité", "cni",
        "id card number", "identity card number", "national id",
        "dni", "número de dni", "personalausweisnummer", "numero carta d'identità",
    ),
    "iban": ("iban", "numéro iban", "bank account", "numéro de compte", "kontonummer", "cuenta bancaria"),
    "bic": ("bic", "swift", "code bic", "bic swift", "swift code"),
    # Concepts « calculés » si absents de la base (voir matcher.DERIVED_VALUES).
    "date_du_jour": (
        "date", "fait le", "date du jour", "date de signature", "le",
        "today's date", "date of signature", "signature date", "date signed",
        "fecha", "fecha de hoy", "datum", "heutiges datum", "data",
    ),
    "lieu_signature": (
        "fait à", "lieu", "lieu de signature",
        "place", "signed at", "place of signature",
        "lugar", "ort der unterschrift", "luogo",
    ),
}

# Groupes de valeurs équivalentes entre langues (pour cases, radios et listes).
VALUE_EQUIVALENTS: tuple[tuple[str, ...], ...] = (
    ("oui", "yes", "si", "sí", "ja", "sim", "vrai", "true", "1", "x"),
    ("non", "no", "nein", "não", "faux", "false", "0"),
    ("homme", "masculin", "m", "h", "male", "man", "hombre", "masculino", "männlich", "mann", "maschio", "uomo"),
    ("femme", "féminin", "f", "female", "woman", "mujer", "femenino", "weiblich", "frau", "femmina", "donna", "feminino"),
    ("monsieur", "m.", "mr", "mr.", "señor", "sr", "herr", "signor", "sig", "senhor"),
    ("madame", "mme", "mrs", "ms", "señora", "sra", "frau", "signora", "sig.ra", "senhora"),
    ("célibataire", "single", "soltero", "soltera", "ledig", "celibe", "nubile", "solteiro"),
    ("marié", "mariée", "marié(e)", "married", "casado", "casada", "verheiratet", "sposato", "sposata"),
    ("divorcé", "divorcée", "divorcé(e)", "divorced", "divorciado", "divorciada", "geschieden", "divorziato"),
    ("veuf", "veuve", "widowed", "viudo", "viuda", "verwitwet", "vedovo", "vedova"),
    ("pacsé", "pacsée", "pacsé(e)", "civil partnership", "registered partnership", "eingetragene partnerschaft"),
    ("france", "french republic", "francia", "frankreich", "frança"),
    ("française", "français", "french", "francés", "francesa", "französisch", "francese", "francês"),
    ("allemagne", "germany", "alemania", "deutschland", "germania", "alemanha"),
    ("espagne", "spain", "españa", "spanien", "spagna", "espanha"),
    ("italie", "italy", "italia", "italien", "itália"),
    ("belgique", "belgium", "bélgica", "belgien", "belgio"),
    ("suisse", "switzerland", "suiza", "schweiz", "svizzera", "suíça"),
    ("royaume-uni", "united kingdom", "uk", "great britain", "reino unido", "vereinigtes königreich", "regno unito"),
    ("états-unis", "united states", "usa", "us", "estados unidos", "vereinigte staaten", "stati uniti"),
)
