"""
Service pour récupérer les données DVF (Demandes de Valeurs Foncières)
Utilise la base de données locale PostgreSQL
"""

import os
from typing import Dict, Any
import psycopg2
from psycopg2.extras import RealDictCursor


class DVFService:
    """Service pour interroger les stats de prix depuis la DB locale."""

    def __init__(self):
        self.database_url = os.getenv('DATABASE_URL')

    def _get_connection(self):
        """Crée une connexion à la base de données."""
        return psycopg2.connect(self.database_url)

    def get_price_stats_by_type_aggregated(
        self,
        code_postal: str
    ) -> Dict[str, Any]:
        """
        Récupère les stats de prix depuis la table communes.
        Agrège avec les communes voisines si nécessaire.
        """
        print(f"[DVF-DB] Recherche stats pour {code_postal}")

        try:
            conn = self._get_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)

            # Chercher la commune principale
            cur.execute("""
                SELECT
                    code_postal, nom,
                    prix_m2_appartement, prix_m2_maison,
                    nb_transactions_12m, prix_min, prix_max
                FROM communes
                WHERE code_postal = %s
                LIMIT 1
            """, (code_postal,))

            commune = cur.fetchone()

            if commune and (commune['prix_m2_appartement'] or commune['prix_m2_maison']):
                prix_a = commune['prix_m2_appartement'] or 0
                prix_m = commune['prix_m2_maison'] or 0
                print(f"[DVF-DB] Trouvé: {commune['nom']} - Appart: {prix_a:.0f}€/m², Maison: {prix_m:.0f}€/m²")

                result = self._build_stats_from_commune(commune)
                cur.close()
                conn.close()
                return result

            # Si pas de données, chercher dans les communes voisines
            print(f"[DVF-DB] Pas de données directes, recherche communes voisines...")

            cur.execute("""
                SELECT
                    c2.code_postal, c2.nom,
                    c2.prix_m2_appartement, c2.prix_m2_maison,
                    c2.nb_transactions_12m, c2.prix_min, c2.prix_max
                FROM communes c1
                JOIN commune_voisines cv ON c1.id = cv.commune_id
                JOIN communes c2 ON c2.id = cv.voisine_id
                WHERE c1.code_postal = %s
                AND (c2.prix_m2_appartement IS NOT NULL OR c2.prix_m2_maison IS NOT NULL)
                ORDER BY c2.nb_transactions_12m DESC
                LIMIT 10
            """, (code_postal,))

            voisines = cur.fetchall()

            if voisines:
                print(f"[DVF-DB] Trouvé {len(voisines)} communes voisines avec données")
                result = self._aggregate_stats(voisines)
                result['est_agrege'] = True
                result['nb_communes'] = len(voisines)
                cur.close()
                conn.close()
                return result

            # Fallback: chercher par département
            dept = code_postal[:2]
            print(f"[DVF-DB] Fallback département {dept}")

            cur.execute("""
                SELECT
                    code_postal, nom,
                    prix_m2_appartement, prix_m2_maison,
                    nb_transactions_12m, prix_min, prix_max
                FROM communes
                WHERE departement_code = %s
                AND prix_m2_appartement IS NOT NULL
                ORDER BY nb_transactions_12m DESC
                LIMIT 20
            """, (dept,))

            dept_communes = cur.fetchall()
            cur.close()
            conn.close()

            if dept_communes:
                print(f"[DVF-DB] Trouvé {len(dept_communes)} communes dans le département")
                result = self._aggregate_stats(dept_communes)
                result['est_agrege'] = True
                result['rayon_km'] = 50
                result['nb_communes'] = len(dept_communes)
                return result

            # Aucune donnée
            print(f"[DVF-DB] Aucune donnée trouvée pour {code_postal}")
            return self._empty_stats()

        except Exception as e:
            print(f"[DVF-DB] Erreur: {e}")
            return self._empty_stats()

    def _build_stats_from_commune(self, commune: Dict) -> Dict[str, Any]:
        """Construit les stats depuis une commune."""
        prix_appart = float(commune['prix_m2_appartement'] or 0)
        prix_maison = float(commune['prix_m2_maison'] or 0)
        nb_trans = int(commune['nb_transactions_12m'] or 0)

        # Estimation de l'écart-type (environ 15% du prix moyen)
        ecart_appart = prix_appart * 0.15 if prix_appart else 0
        ecart_maison = prix_maison * 0.15 if prix_maison else 0

        # Prix de référence (utilise celui disponible)
        prix_ref = prix_appart or prix_maison

        return {
            'appartement': {
                'moyenne': prix_appart or prix_ref,
                'mediane': prix_appart or prix_ref,
                'min': (prix_appart or prix_ref) * 0.7,
                'max': (prix_appart or prix_ref) * 1.3,
                'ecart_type': ecart_appart or prix_ref * 0.15,
                'nb_transactions': nb_trans
            },
            'maison': {
                'moyenne': prix_maison or prix_ref,
                'mediane': prix_maison or prix_ref,
                'min': (prix_maison or prix_ref) * 0.7,
                'max': (prix_maison or prix_ref) * 1.3,
                'ecart_type': ecart_maison or prix_ref * 0.15,
                'nb_transactions': nb_trans
            },
            'global': {
                'moyenne': prix_ref,
                'mediane': prix_ref,
                'min': prix_ref * 0.7,
                'max': prix_ref * 1.3,
                'ecart_type': prix_ref * 0.15,
                'nb_transactions': nb_trans
            },
            'codes_postaux_utilises': [commune['code_postal']],
            'rayon_km': 0,
            'est_agrege': False
        }

    def _aggregate_stats(self, communes: list) -> Dict[str, Any]:
        """Agrège les stats de plusieurs communes."""
        total_trans = sum(int(c['nb_transactions_12m'] or 0) for c in communes)

        # Moyenne pondérée par nombre de transactions
        if total_trans > 0:
            prix_appart = sum(
                float(c['prix_m2_appartement'] or 0) * int(c['nb_transactions_12m'] or 0)
                for c in communes
            ) / total_trans

            prix_maison = sum(
                float(c['prix_m2_maison'] or 0) * int(c['nb_transactions_12m'] or 0)
                for c in communes
            ) / total_trans
        else:
            prix_appart = sum(float(c['prix_m2_appartement'] or 0) for c in communes) / len(communes)
            prix_maison = sum(float(c['prix_m2_maison'] or 0) for c in communes) / len(communes)

        ecart_appart = prix_appart * 0.18  # Plus large car agrégé
        ecart_maison = prix_maison * 0.18

        return {
            'appartement': {
                'moyenne': prix_appart,
                'mediane': prix_appart,
                'min': prix_appart * 0.65,
                'max': prix_appart * 1.35,
                'ecart_type': ecart_appart,
                'nb_transactions': total_trans
            },
            'maison': {
                'moyenne': prix_maison,
                'mediane': prix_maison,
                'min': prix_maison * 0.65,
                'max': prix_maison * 1.35,
                'ecart_type': ecart_maison,
                'nb_transactions': total_trans
            },
            'global': {
                'moyenne': (prix_appart + prix_maison) / 2,
                'mediane': (prix_appart + prix_maison) / 2,
                'min': min(prix_appart, prix_maison) * 0.65,
                'max': max(prix_appart, prix_maison) * 1.35,
                'ecart_type': (ecart_appart + ecart_maison) / 2,
                'nb_transactions': total_trans
            },
            'codes_postaux_utilises': [c['code_postal'] for c in communes],
            'rayon_km': 15,
            'est_agrege': True
        }

    def _empty_stats(self) -> Dict[str, Any]:
        """Retourne des stats vides."""
        empty = {
            'moyenne': 0,
            'mediane': 0,
            'min': 0,
            'max': 0,
            'ecart_type': 0,
            'nb_transactions': 0
        }
        return {
            'appartement': empty.copy(),
            'maison': empty.copy(),
            'global': empty.copy(),
            'codes_postaux_utilises': [],
            'rayon_km': 0,
            'est_agrege': False
        }


# Instance singleton
dvf_service = DVFService()
