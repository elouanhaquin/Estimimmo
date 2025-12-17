"""
Module de securite - EstimImmo
Protection CSRF, Rate Limiting, Validation des inputs
"""

import re
import bleach
from functools import wraps
from flask import request, jsonify


# === VALIDATION DES INPUTS ===

def sanitize_string(value, max_length=200):
    """Nettoie une chaine de caracteres."""
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    # Supprime les balises HTML
    value = bleach.clean(value, tags=[], strip=True)
    # Limite la longueur
    return value[:max_length].strip()


def validate_code_postal(code_postal):
    """Valide un code postal francais."""
    if not code_postal:
        return None, "Code postal requis"
    code_postal = str(code_postal).strip()
    if not re.match(r'^[0-9]{5}$', code_postal):
        return None, "Code postal invalide (5 chiffres requis)"
    return code_postal, None


def validate_telephone(telephone):
    """Valide un numero de telephone francais."""
    if not telephone:
        return None, "Telephone requis"
    # Nettoie le numero
    tel = re.sub(r'[\s\.\-]', '', str(telephone))
    # Formats acceptes: 0612345678, +33612345678
    if re.match(r'^0[1-9][0-9]{8}$', tel):
        return tel, None
    if re.match(r'^\+33[1-9][0-9]{8}$', tel):
        return '0' + tel[3:], None
    return None, "Numero de telephone invalide"


def validate_email(email):
    """Valide une adresse email."""
    if not email:
        return None, None  # Email optionnel
    email = str(email).strip().lower()
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        return None, "Email invalide"
    if len(email) > 255:
        return None, "Email trop long"
    return email, None


def validate_positive_number(value, field_name, min_val=0, max_val=None):
    """Valide un nombre positif."""
    if value is None:
        return None, None
    try:
        num = float(value)
        if num < min_val:
            return None, f"{field_name} doit etre >= {min_val}"
        if max_val and num > max_val:
            return None, f"{field_name} doit etre <= {max_val}"
        return num, None
    except (ValueError, TypeError):
        return None, f"{field_name} invalide"


def validate_integer(value, field_name, min_val=0, max_val=None):
    """Valide un entier."""
    if value is None:
        return None, None
    try:
        num = int(value)
        if num < min_val:
            return None, f"{field_name} doit etre >= {min_val}"
        if max_val and num > max_val:
            return None, f"{field_name} doit etre <= {max_val}"
        return num, None
    except (ValueError, TypeError):
        return None, f"{field_name} invalide"


def validate_choice(value, choices, field_name):
    """Valide une valeur parmi une liste de choix."""
    if value is None:
        return None, None
    if value not in choices:
        return None, f"{field_name} invalide"
    return value, None


# === VALIDATION ESTIMATION ===

TYPES_BIEN = ['appartement', 'maison']
ETATS = ['a_renover', 'correct', 'bon', 'tres_bon', 'neuf']
DPE_VALUES = ['A', 'B', 'C', 'D', 'E', 'F', 'G', None, '']
EXPOSITIONS = ['nord', 'est', 'ouest', 'sud', None, '']
VUES = ['vis_a_vis', 'degagee', 'exceptionnelle', None, '']
STANDINGS = ['economique', 'standard', 'standing', 'luxe']


def validate_estimation_data(data):
    """Valide les donnees d'estimation."""
    errors = []
    validated = {}

    # Code postal (requis)
    val, err = validate_code_postal(data.get('code_postal'))
    if err:
        errors.append(err)
    validated['code_postal'] = val

    # Type de bien (requis)
    val, err = validate_choice(data.get('type_bien'), TYPES_BIEN, 'Type de bien')
    if err or not val:
        errors.append(err or "Type de bien requis")
    validated['type_bien'] = val

    # Surface (requis)
    val, err = validate_positive_number(data.get('surface'), 'Surface', min_val=9, max_val=10000)
    if err or val is None:
        errors.append(err or "Surface requise")
    validated['surface'] = val

    # Nombre de pieces (requis)
    val, err = validate_integer(data.get('nb_pieces'), 'Nombre de pieces', min_val=1, max_val=50)
    if err or val is None:
        errors.append(err or "Nombre de pieces requis")
    validated['nb_pieces'] = val

    # Champs optionnels
    val, _ = validate_integer(data.get('etage'), 'Etage', min_val=0, max_val=100)
    validated['etage'] = val

    val, _ = validate_integer(data.get('nb_etages_immeuble'), 'Etages immeuble', min_val=1, max_val=100)
    validated['nb_etages_immeuble'] = val

    val, _ = validate_positive_number(data.get('surface_terrain'), 'Surface terrain', min_val=0, max_val=1000000)
    validated['surface_terrain'] = val

    val, _ = validate_integer(data.get('annee_construction'), 'Annee construction', min_val=1800, max_val=2030)
    validated['annee_construction'] = val

    val, _ = validate_choice(data.get('etat_general'), ETATS, 'Etat')
    validated['etat_general'] = val or 'bon'

    val, _ = validate_choice(data.get('dpe'), DPE_VALUES + [None], 'DPE')
    validated['dpe'] = val if val else None

    val, _ = validate_choice(data.get('exposition'), EXPOSITIONS + [None], 'Exposition')
    validated['exposition'] = val if val else None

    val, _ = validate_choice(data.get('vue'), VUES + [None], 'Vue')
    validated['vue'] = val if val else None

    val, _ = validate_choice(data.get('standing'), STANDINGS, 'Standing')
    validated['standing'] = val or 'standard'

    # Booleens
    bool_fields = [
        'ascenseur', 'balcon_terrasse', 'parking', 'cave', 'jardin',
        'veranda', 'dependances', 'cuisine_equipee', 'double_vitrage',
        'climatisation', 'cheminee', 'parquet', 'fibre', 'alarme',
        'digicode', 'gardien', 'portail_auto', 'piscine', 'potager',
        'spa', 'terrain_tennis', 'abri_jardin', 'arrosage_auto'
    ]
    for field in bool_fields:
        validated[field] = bool(data.get(field))

    return validated, errors


# === VALIDATION LEAD ===

LEAD_TYPES = ['callback', 'visit']
PROJETS = ['vente', 'estimation', 'succession', 'investissement']
CRENEAUX = ['matin', 'midi', 'aprem', 'soir']


def validate_lead_data(data):
    """Valide les donnees de lead."""
    errors = []
    validated = {}

    # Type (requis)
    val, err = validate_choice(data.get('type'), LEAD_TYPES, 'Type')
    if err or not val:
        errors.append(err or "Type requis")
    validated['type'] = val or 'callback'

    # Telephone (requis)
    val, err = validate_telephone(data.get('telephone'))
    if err:
        errors.append(err)
    validated['telephone'] = val

    # Nom/Prenom (optionnels mais sanitizes)
    validated['nom'] = sanitize_string(data.get('nom'), 100)
    validated['prenom'] = sanitize_string(data.get('prenom'), 100)

    # Email
    val, err = validate_email(data.get('email'))
    if err:
        errors.append(err)
    validated['email'] = val

    # Adresse
    validated['adresse'] = sanitize_string(data.get('adresse'), 500)

    # Projet
    val, _ = validate_choice(data.get('projet'), PROJETS, 'Projet')
    validated['projet'] = val

    # Creneau/Horaires
    val, _ = validate_choice(data.get('creneau'), CRENEAUX, 'Creneau')
    validated['creneau'] = val

    val, _ = validate_choice(data.get('horaires'), CRENEAUX, 'Horaires')
    validated['horaires'] = val

    # Message
    validated['message'] = sanitize_string(data.get('message'), 2000)

    # Date souhaitee
    validated['date_souhaitee'] = data.get('date_souhaitee')

    # Estimation data (JSON)
    validated['estimation_data'] = data.get('estimation_data')

    return validated, errors


# === VALIDATION TRACKING ===

def validate_track_data(data):
    """Valide les donnees de tracking."""
    validated = {}

    # Session ID (requis)
    session_id = sanitize_string(data.get('session_id'), 64)
    if not session_id:
        return None, "session_id requis"
    validated['session_id'] = session_id

    # Visitor ID
    validated['visitor_id'] = sanitize_string(data.get('visitor_id'), 64)

    # Event type
    event_type = sanitize_string(data.get('event_type'), 30)
    validated['event_type'] = event_type or 'pageview'

    # URLs (limites)
    validated['page_url'] = sanitize_string(data.get('page_url'), 500)
    validated['page_path'] = sanitize_string(data.get('page_path'), 200)
    validated['referrer'] = sanitize_string(data.get('referrer'), 500)

    # Element details
    validated['element_id'] = sanitize_string(data.get('element_id'), 100)
    validated['element_text'] = sanitize_string(data.get('element_text'), 200)
    validated['element_class'] = sanitize_string(data.get('element_class'), 200)

    # Form tracking
    val, _ = validate_integer(data.get('form_step'), 'form_step', 0, 100)
    validated['form_step'] = val
    validated['form_field'] = sanitize_string(data.get('form_field'), 50)

    # Scroll
    val, _ = validate_integer(data.get('scroll_depth'), 'scroll_depth', 0, 100)
    validated['scroll_depth'] = val

    # Screen
    val, _ = validate_integer(data.get('screen_width'), 'screen_width', 0, 10000)
    validated['screen_width'] = val
    val, _ = validate_integer(data.get('screen_height'), 'screen_height', 0, 10000)
    validated['screen_height'] = val

    # Time on page
    val, _ = validate_integer(data.get('time_on_page'), 'time_on_page', 0, 86400)
    validated['time_on_page'] = val

    # Extra data (JSON) - limite la taille
    extra = data.get('extra_data')
    if extra and isinstance(extra, dict):
        validated['extra_data'] = extra
    else:
        validated['extra_data'] = None

    return validated, None
