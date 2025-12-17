"""
Modèles de base de données - EstimImmo
"""

import re
import unicodedata
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def generate_slug(nom, code_postal):
    """Génère un slug URL-friendly à partir du nom et code postal."""
    # Normaliser les accents
    slug = unicodedata.normalize('NFKD', nom.lower())
    slug = slug.encode('ascii', 'ignore').decode('ascii')
    # Remplacer les caractères spéciaux par des tirets
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    # Supprimer les tirets en début/fin
    slug = slug.strip('-')
    return f"{slug}-{code_postal}"


# Table d'association pour les communes voisines
commune_voisines = db.Table(
    'commune_voisines',
    db.Column('commune_id', db.Integer, db.ForeignKey('communes.id'), primary_key=True),
    db.Column('voisine_id', db.Integer, db.ForeignKey('communes.id'), primary_key=True),
    db.Column('distance_km', db.Float)
)


class Departement(db.Model):
    """Modèle pour les départements français (stats agrégées)."""
    __tablename__ = 'departements'

    code = db.Column(db.String(3), primary_key=True)
    nom = db.Column(db.String(100), nullable=False)
    region = db.Column(db.String(100))

    # Stats agrégées du département
    prix_m2_appartement = db.Column(db.Float)
    prix_m2_maison = db.Column(db.Float)
    evolution_appartement = db.Column(db.Float)  # % sur 1 an
    evolution_maison = db.Column(db.Float)
    nb_transactions_12m = db.Column(db.Integer)
    stats_updated_at = db.Column(db.DateTime)

    def __repr__(self):
        return f'<Departement {self.code} - {self.nom}>'


class Commune(db.Model):
    """Modèle pour les communes françaises (pages SEO)."""
    __tablename__ = 'communes'

    id = db.Column(db.Integer, primary_key=True)
    code_postal = db.Column(db.String(5), index=True)
    code_insee = db.Column(db.String(5), unique=True, index=True)
    nom = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(120), unique=True, index=True)
    departement_code = db.Column(db.String(3), db.ForeignKey('departements.code'))
    region = db.Column(db.String(100))
    population = db.Column(db.Integer)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)

    # Stats DVF cachées (mises à jour hebdomadaire)
    prix_m2_appartement = db.Column(db.Float)
    prix_m2_maison = db.Column(db.Float)
    evolution_appartement = db.Column(db.Float)  # % sur 1 an
    evolution_maison = db.Column(db.Float)
    nb_transactions_12m = db.Column(db.Integer)
    prix_min = db.Column(db.Integer)
    prix_max = db.Column(db.Integer)
    surface_moyenne = db.Column(db.Float)
    stats_updated_at = db.Column(db.DateTime)

    # Relations
    departement = db.relationship('Departement', backref='communes')
    voisines = db.relationship(
        'Commune',
        secondary=commune_voisines,
        primaryjoin=(commune_voisines.c.commune_id == id),
        secondaryjoin=(commune_voisines.c.voisine_id == id),
        backref='voisines_de'
    )

    def __repr__(self):
        return f'<Commune {self.nom} ({self.code_postal})>'

    def get_comparison_dept(self, type_bien='appartement'):
        """Calcule la différence de prix vs moyenne départementale."""
        if not self.departement:
            return None

        if type_bien == 'appartement':
            prix_commune = self.prix_m2_appartement
            prix_dept = self.departement.prix_m2_appartement
        else:
            prix_commune = self.prix_m2_maison
            prix_dept = self.departement.prix_m2_maison

        if not prix_commune or not prix_dept:
            return None

        return ((prix_commune - prix_dept) / prix_dept) * 100

    def to_dict(self):
        """Convertit la commune en dictionnaire."""
        return {
            'id': self.id,
            'code_postal': self.code_postal,
            'code_insee': self.code_insee,
            'nom': self.nom,
            'slug': self.slug,
            'departement': self.departement.nom if self.departement else None,
            'region': self.region,
            'population': self.population,
            'prix_m2_appartement': self.prix_m2_appartement,
            'prix_m2_maison': self.prix_m2_maison,
            'evolution_appartement': self.evolution_appartement,
            'evolution_maison': self.evolution_maison,
            'nb_transactions_12m': self.nb_transactions_12m
        }


class Lead(db.Model):
    """
    Modèle pour stocker les leads (demandes de rappel/visite).
    """
    __tablename__ = 'leads'

    id = db.Column(db.Integer, primary_key=True)

    # Type de lead
    type = db.Column(db.String(20), nullable=False)  # 'callback' ou 'visit'

    # Informations contact
    nom = db.Column(db.String(100))
    prenom = db.Column(db.String(100))
    telephone = db.Column(db.String(20), nullable=False, index=True)
    email = db.Column(db.String(255))

    # Informations visite
    adresse = db.Column(db.Text)
    date_souhaitee = db.Column(db.Date)
    creneau = db.Column(db.String(20))  # 'matin', 'apres-midi', 'soir'
    horaires = db.Column(db.String(20))  # 'matin', 'apres-midi', 'soiree'

    # Informations projet
    projet = db.Column(db.String(50))  # 'vente', 'achat', 'estimation'
    message = db.Column(db.Text)

    # Données d'estimation (stockées en JSON)
    estimation_data = db.Column(db.JSON)

    # Gestion du lead
    status = db.Column(db.String(20), default='nouveau', index=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Lead {self.id} - {self.type} - {self.telephone}>'

    def to_dict(self):
        """Convertit le lead en dictionnaire."""
        return {
            'id': self.id,
            'type': self.type,
            'nom': self.nom,
            'prenom': self.prenom,
            'telephone': self.telephone,
            'email': self.email,
            'adresse': self.adresse,
            'date_souhaitee': self.date_souhaitee.isoformat() if self.date_souhaitee else None,
            'creneau': self.creneau,
            'horaires': self.horaires,
            'projet': self.projet,
            'message': self.message,
            'estimation_data': self.estimation_data,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class Activity(db.Model):
    """Modèle pour tracker l'activité des visiteurs."""
    __tablename__ = 'activities'

    id = db.Column(db.Integer, primary_key=True)

    # Identification visiteur
    session_id = db.Column(db.String(64), nullable=False, index=True)
    visitor_id = db.Column(db.String(64), index=True)  # Persistant (localStorage)

    # Event
    event_type = db.Column(db.String(30), nullable=False, index=True)
    # Types: pageview, click, form_start, form_step, form_submit, form_abandon, scroll, cta_click

    # Contexte page
    page_url = db.Column(db.String(500))
    page_path = db.Column(db.String(200), index=True)
    referrer = db.Column(db.String(500))

    # Détails event
    element_id = db.Column(db.String(100))      # ID de l'élément cliqué
    element_text = db.Column(db.String(200))    # Texte du bouton/lien
    element_class = db.Column(db.String(200))   # Classes CSS
    form_step = db.Column(db.Integer)           # Étape du formulaire (1-4)
    form_field = db.Column(db.String(50))       # Dernier champ rempli
    scroll_depth = db.Column(db.Integer)        # % de scroll

    # Données supplémentaires (JSON flexible)
    extra_data = db.Column(db.JSON)

    # Infos techniques
    user_agent = db.Column(db.String(500))
    screen_width = db.Column(db.Integer)
    screen_height = db.Column(db.Integer)
    ip_address = db.Column(db.String(45))

    # Timing
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    time_on_page = db.Column(db.Integer)  # Secondes passées sur la page

    def __repr__(self):
        return f'<Activity {self.event_type} - {self.session_id[:8]}>'


class Consent(db.Model):
    """Modele pour stocker les preuves de consentement RGPD."""
    __tablename__ = 'consents'

    id = db.Column(db.Integer, primary_key=True)

    # Identification
    visitor_id = db.Column(db.String(64), nullable=False, index=True)
    ip_address = db.Column(db.String(45), nullable=False)

    # Consentement
    consent_type = db.Column(db.String(20), nullable=False)  # 'cookies', 'marketing', etc.
    consent_value = db.Column(db.Boolean, nullable=False)  # True = accepte, False = refuse
    consent_text = db.Column(db.Text)  # Texte affiche au moment du consentement

    # Contexte
    page_url = db.Column(db.String(500))
    user_agent = db.Column(db.String(500))

    # Timestamp
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def __repr__(self):
        status = 'accepted' if self.consent_value else 'refused'
        return f'<Consent {self.consent_type} {status} - {self.ip_address}>'
