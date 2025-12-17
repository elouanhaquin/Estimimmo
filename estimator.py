"""
Module d'estimation immobilière basé sur les données DVF et des coefficients d'ajustement.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any
from dvf_service import dvf_service
import numpy as np


@dataclass
class PropertyCriteria:
    """Critères du bien immobilier à estimer."""
    code_postal: str
    surface: float  # en m²
    nb_pieces: int
    type_bien: str  # "appartement" ou "maison"
    etage: Optional[int] = None  # Pour appartements
    nb_etages_immeuble: Optional[int] = None
    ascenseur: bool = False
    balcon_terrasse: bool = False
    parking: bool = False
    cave: bool = False
    jardin: bool = False
    veranda: bool = False  # Maison
    dependances: bool = False  # Maison (garage, abri, etc.)
    surface_terrain: Optional[float] = None  # Pour maisons, en m²
    annee_construction: Optional[int] = None
    etat_general: str = "bon"  # "a_renover", "correct", "bon", "tres_bon", "neuf"
    dpe: Optional[str] = None  # A, B, C, D, E, F, G
    exposition: Optional[str] = None  # "nord", "sud", "est", "ouest"
    vue: Optional[str] = None  # "degagee", "vis_a_vis", "exceptionnelle"
    standing: str = "standard"  # "economique", "standard", "standing", "luxe"
    # Confort & Équipements
    cuisine_equipee: bool = False
    double_vitrage: bool = False
    climatisation: bool = False
    cheminee: bool = False
    parquet: bool = False
    fibre: bool = False
    # Sécurité
    alarme: bool = False
    digicode: bool = False
    gardien: bool = False
    portail_auto: bool = False  # Maison
    # Extérieur Maison
    piscine: bool = False
    potager: bool = False
    spa: bool = False
    terrain_tennis: bool = False
    abri_jardin: bool = False
    arrosage_auto: bool = False


class PropertyEstimator:
    """Estimateur de prix immobilier basé sur les transactions réelles."""

    # Coefficients d'ajustement basés sur les études de marché
    COEFFICIENTS = {
        # Ajustement par étage (appartements)
        'etage': {
            0: -0.05,   # RDC: -5%
            1: -0.02,   # 1er: -2%
            2: 0.0,     # 2ème: référence
            3: 0.02,    # 3ème: +2%
            4: 0.03,    # 4ème: +3%
            5: 0.04,    # 5ème et +: +4%
            'dernier': 0.06,  # Dernier étage: +6%
        },

        # Ajustement ascenseur
        'ascenseur': {
            True: 0.03,   # +3%
            False: -0.02  # -2% si pas d'ascenseur et étage > 2
        },

        # État général du bien
        'etat': {
            'a_renover': -0.15,   # -15%
            'correct': -0.05,     # -5%
            'bon': 0.0,           # référence
            'tres_bon': 0.05,     # +5%
            'neuf': 0.15          # +15%
        },

        # Équipements - Espaces
        'balcon_terrasse': 0.04,  # +4%
        'parking': 0.05,           # +5%
        'cave': 0.02,              # +2%
        'jardin': 0.08,            # +8%
        'veranda': 0.05,           # +5%
        'dependances': 0.03,       # +3%

        # Équipements - Confort
        'cuisine_equipee': 0.03,   # +3%
        'double_vitrage': 0.02,    # +2%
        'climatisation': 0.04,     # +4%
        'cheminee': 0.02,          # +2%
        'parquet': 0.02,           # +2%
        'fibre': 0.01,             # +1%

        # Équipements - Sécurité
        'alarme': 0.02,            # +2%
        'digicode': 0.01,          # +1%
        'gardien': 0.03,           # +3%
        'portail_auto': 0.02,      # +2%

        # Équipements - Extérieur Maison
        'piscine': 0.12,           # +12%
        'potager': 0.01,           # +1%
        'spa': 0.05,               # +5%
        'terrain_tennis': 0.08,    # +8%
        'abri_jardin': 0.01,       # +1%
        'arrosage_auto': 0.01,     # +1%

        # DPE (Diagnostic de Performance Énergétique)
        'dpe': {
            'A': 0.10,   # +10%
            'B': 0.06,   # +6%
            'C': 0.03,   # +3%
            'D': 0.0,    # référence
            'E': -0.05,  # -5%
            'F': -0.12,  # -12%
            'G': -0.20   # -20%
        },

        # Exposition
        'exposition': {
            'nord': -0.03,
            'est': 0.0,
            'ouest': 0.01,
            'sud': 0.04
        },

        # Vue
        'vue': {
            'vis_a_vis': -0.05,
            'degagee': 0.03,
            'exceptionnelle': 0.10
        },

        # Standing
        'standing': {
            'economique': -0.10,
            'standard': 0.0,
            'standing': 0.15,
            'luxe': 0.30
        },

        # Ajustement surface (dégressivité)
        'surface_degressive': {
            30: 1.10,   # < 30m²: +10%
            50: 1.05,   # 30-50m²: +5%
            80: 1.0,    # 50-80m²: référence
            120: 0.97,  # 80-120m²: -3%
            200: 0.94,  # 120-200m²: -6%
            999: 0.90   # > 200m²: -10%
        },

        # Coefficient terrain pour maisons (€/m² terrain)
        'terrain_par_m2': {
            'urbain': 150,
            'periurbain': 80,
            'rural': 30
        }
    }

    def __init__(self):
        self.dvf = dvf_service

    def estimate(self, criteria: PropertyCriteria) -> Dict[str, Any]:
        """
        Estime le prix d'un bien immobilier.

        Args:
            criteria: Critères du bien

        Returns:
            Dict avec estimation basse, moyenne, haute et détails
        """
        # Récupération des stats de prix avec agrégation des codes postaux voisins si nécessaire
        stats = self.dvf.get_price_stats_by_type_aggregated(criteria.code_postal)

        type_key = criteria.type_bien.lower()
        if type_key not in stats or stats[type_key]['nb_transactions'] == 0:
            # Fallback sur les stats globales
            type_key = 'global'

        price_stats = stats[type_key]

        if price_stats['nb_transactions'] == 0:
            return {
                'erreur': True,
                'message': f"Pas assez de données pour le code postal {criteria.code_postal} et ses environs",
                'estimation_basse': None,
                'estimation_moyenne': None,
                'estimation_haute': None
            }

        # Prix de base au m²
        base_price_sqm = price_stats['mediane']

        # Calcul des ajustements
        adjustments = self._calculate_adjustments(criteria, price_stats)

        # Prix ajusté au m²
        total_adjustment = sum(adjustments.values())
        adjusted_price_sqm = base_price_sqm * (1 + total_adjustment)

        # Ajustement dégressif selon la surface
        surface_coef = self._get_surface_coefficient(criteria.surface)
        final_price_sqm = adjusted_price_sqm * surface_coef

        # Calcul du prix total
        base_price = final_price_sqm * criteria.surface

        # Ajout valeur terrain pour les maisons
        terrain_value = 0
        if criteria.type_bien.lower() == 'maison' and criteria.surface_terrain:
            terrain_value = self._calculate_terrain_value(
                criteria.surface_terrain,
                criteria.code_postal
            )
            base_price += terrain_value

        # Calcul des fourchettes (basé sur l'écart-type du marché)
        ecart_relatif = price_stats['ecart_type'] / price_stats['moyenne'] if price_stats['moyenne'] > 0 else 0.15
        # Élargir la fourchette si données agrégées
        if stats.get('est_agrege', False):
            ecart_relatif = min(max(ecart_relatif, 0.12), 0.30)  # Plus large si agrégé
        else:
            ecart_relatif = min(max(ecart_relatif, 0.10), 0.25)

        estimation_basse = base_price * (1 - ecart_relatif)
        estimation_haute = base_price * (1 + ecart_relatif)

        result = {
            'erreur': False,
            'estimation_basse': round(estimation_basse, 0),
            'estimation_moyenne': round(base_price, 0),
            'estimation_haute': round(estimation_haute, 0),
            'prix_m2_zone': round(price_stats['mediane'], 0),
            'prix_m2_ajuste': round(final_price_sqm, 0),
            'nb_transactions_reference': price_stats['nb_transactions'],
            'ajustements': {k: f"{v:+.1%}" for k, v in adjustments.items()},
            'ajustement_total': f"{total_adjustment:+.1%}",
            'coefficient_surface': surface_coef,
            'valeur_terrain': terrain_value if terrain_value > 0 else None,
            'confiance': self._calculate_confidence(price_stats, stats.get('est_agrege', False))
        }

        # Ajouter les infos d'agrégation si applicable
        if stats.get('est_agrege', False):
            result['zone_elargie'] = True
            result['rayon_km'] = stats.get('rayon_km', 0)
            result['nb_communes'] = stats.get('nb_communes', 1)
            result['message_zone'] = f"Estimation basée sur {result['nb_communes']} communes dans un rayon de {result['rayon_km']} km"
        else:
            result['zone_elargie'] = False

        return result

    def _calculate_adjustments(
        self,
        criteria: PropertyCriteria,
        price_stats: Dict[str, float]
    ) -> Dict[str, float]:
        """Calcule tous les ajustements à appliquer."""
        adjustments = {}

        # Ajustement étage (appartements uniquement)
        if criteria.type_bien.lower() == 'appartement' and criteria.etage is not None:
            if criteria.nb_etages_immeuble and criteria.etage == criteria.nb_etages_immeuble:
                adjustments['etage'] = self.COEFFICIENTS['etage']['dernier']
            else:
                etage_key = min(criteria.etage, 5)
                adjustments['etage'] = self.COEFFICIENTS['etage'].get(etage_key, 0.04)

            # Ajustement ascenseur
            if criteria.etage > 2:
                if criteria.ascenseur:
                    adjustments['ascenseur'] = self.COEFFICIENTS['ascenseur'][True]
                else:
                    adjustments['ascenseur'] = self.COEFFICIENTS['ascenseur'][False]

        # État général
        if criteria.etat_general in self.COEFFICIENTS['etat']:
            adjustments['etat'] = self.COEFFICIENTS['etat'][criteria.etat_general]

        # Équipements - Espaces
        if criteria.balcon_terrasse:
            adjustments['balcon_terrasse'] = self.COEFFICIENTS['balcon_terrasse']
        if criteria.parking:
            adjustments['parking'] = self.COEFFICIENTS['parking']
        if criteria.cave:
            adjustments['cave'] = self.COEFFICIENTS['cave']
        if criteria.jardin and criteria.type_bien.lower() == 'maison':
            adjustments['jardin'] = self.COEFFICIENTS['jardin']
        if criteria.veranda and criteria.type_bien.lower() == 'maison':
            adjustments['veranda'] = self.COEFFICIENTS['veranda']
        if criteria.dependances and criteria.type_bien.lower() == 'maison':
            adjustments['dependances'] = self.COEFFICIENTS['dependances']

        # Équipements - Confort
        if criteria.cuisine_equipee:
            adjustments['cuisine_equipee'] = self.COEFFICIENTS['cuisine_equipee']
        if criteria.double_vitrage:
            adjustments['double_vitrage'] = self.COEFFICIENTS['double_vitrage']
        if criteria.climatisation:
            adjustments['climatisation'] = self.COEFFICIENTS['climatisation']
        if criteria.cheminee:
            adjustments['cheminee'] = self.COEFFICIENTS['cheminee']
        if criteria.parquet:
            adjustments['parquet'] = self.COEFFICIENTS['parquet']
        if criteria.fibre:
            adjustments['fibre'] = self.COEFFICIENTS['fibre']

        # Équipements - Sécurité
        if criteria.alarme:
            adjustments['alarme'] = self.COEFFICIENTS['alarme']
        if criteria.digicode:
            adjustments['digicode'] = self.COEFFICIENTS['digicode']
        if criteria.gardien:
            adjustments['gardien'] = self.COEFFICIENTS['gardien']
        if criteria.portail_auto and criteria.type_bien.lower() == 'maison':
            adjustments['portail_auto'] = self.COEFFICIENTS['portail_auto']

        # Équipements - Extérieur Maison
        if criteria.type_bien.lower() == 'maison':
            if criteria.piscine:
                adjustments['piscine'] = self.COEFFICIENTS['piscine']
            if criteria.potager:
                adjustments['potager'] = self.COEFFICIENTS['potager']
            if criteria.spa:
                adjustments['spa'] = self.COEFFICIENTS['spa']
            if criteria.terrain_tennis:
                adjustments['terrain_tennis'] = self.COEFFICIENTS['terrain_tennis']
            if criteria.abri_jardin:
                adjustments['abri_jardin'] = self.COEFFICIENTS['abri_jardin']
            if criteria.arrosage_auto:
                adjustments['arrosage_auto'] = self.COEFFICIENTS['arrosage_auto']

        # DPE
        if criteria.dpe and criteria.dpe.upper() in self.COEFFICIENTS['dpe']:
            adjustments['dpe'] = self.COEFFICIENTS['dpe'][criteria.dpe.upper()]

        # Exposition
        if criteria.exposition and criteria.exposition in self.COEFFICIENTS['exposition']:
            adjustments['exposition'] = self.COEFFICIENTS['exposition'][criteria.exposition]

        # Vue
        if criteria.vue and criteria.vue in self.COEFFICIENTS['vue']:
            adjustments['vue'] = self.COEFFICIENTS['vue'][criteria.vue]

        # Standing
        if criteria.standing in self.COEFFICIENTS['standing']:
            adjustments['standing'] = self.COEFFICIENTS['standing'][criteria.standing]

        return adjustments

    def _get_surface_coefficient(self, surface: float) -> float:
        """Retourne le coefficient dégressif selon la surface."""
        for max_surface, coef in self.COEFFICIENTS['surface_degressive'].items():
            if surface < max_surface:
                return coef
        return 0.90

    def _calculate_terrain_value(self, surface_terrain: float, code_postal: str) -> float:
        """Calcule la valeur du terrain pour une maison."""
        # Détermination du type de zone selon le code postal
        dept = code_postal[:2]

        # Prix au m² selon la zone
        if dept in ['75', '92', '93', '94']:
            price_per_m2 = self.COEFFICIENTS['terrain_par_m2']['urbain']
        elif dept in ['77', '78', '91', '95', '69', '13', '31', '33', '59', '44']:
            price_per_m2 = self.COEFFICIENTS['terrain_par_m2']['periurbain']
        else:
            price_per_m2 = self.COEFFICIENTS['terrain_par_m2']['rural']

        # Dégressivité pour grands terrains
        if surface_terrain > 1000:
            effective_surface = 1000 + (surface_terrain - 1000) * 0.3
        elif surface_terrain > 500:
            effective_surface = 500 + (surface_terrain - 500) * 0.5
        else:
            effective_surface = surface_terrain

        return effective_surface * price_per_m2

    def _calculate_confidence(self, price_stats: Dict[str, float], est_agrege: bool = False) -> str:
        """Calcule le niveau de confiance de l'estimation."""
        nb_transactions = price_stats['nb_transactions']

        # Réduire la confiance si les données sont agrégées
        if est_agrege:
            if nb_transactions >= 150:
                return "moyenne"
            elif nb_transactions >= 50:
                return "faible"
            else:
                return "tres_faible"
        else:
            if nb_transactions >= 100:
                return "haute"
            elif nb_transactions >= 30:
                return "moyenne"
            elif nb_transactions >= 10:
                return "faible"
            else:
                return "tres_faible"


# Instance singleton
estimator = PropertyEstimator()
