"""
Service pour récupérer les données DVF (Demandes de Valeurs Foncières)
Utilise l'API cquest.org avec cache persistant pour éviter les appels répétés
"""

import requests
import json
import os
import time
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
import numpy as np


class DVFService:
    """Service pour interroger l'API DVF avec cache persistant."""

    BASE_URL = "https://api.cquest.org/dvf"
    GEO_API_URL = "https://geo.api.gouv.fr"
    MIN_TRANSACTIONS = 10
    RATE_LIMIT_DELAY = 0.5  # Délai entre requêtes en secondes

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'ImmoEstimator/1.0',
            'Accept': 'application/json'
        })

        # Cache persistant sur disque
        self._cache_dir = Path(__file__).parent / "cache"
        self._cache_dir.mkdir(exist_ok=True)
        self._cache_file = self._cache_dir / "dvf_cache.json"
        self._cache = self._load_cache()
        self._last_request_time = 0

    def _load_cache(self) -> Dict:
        """Charge le cache depuis le disque."""
        if self._cache_file.exists():
            try:
                with open(self._cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_cache(self):
        """Sauvegarde le cache sur disque."""
        try:
            with open(self._cache_file, 'w', encoding='utf-8') as f:
                json.dump(self._cache, f)
        except Exception:
            pass

    def _rate_limit(self):
        """Applique le rate limiting."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.RATE_LIMIT_DELAY:
            time.sleep(self.RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.time()

    def get_transactions_by_postal_code(
        self,
        code_postal: str,
        annee_min: int = None
    ) -> List[Dict[str, Any]]:
        """
        Récupère les transactions pour un code postal donné via l'API cquest.
        Utilise le cache persistant pour éviter les appels répétés.
        """
        cache_key = f"dvf_{code_postal}"

        # Vérifier le cache
        if cache_key in self._cache:
            return self._cache[cache_key]

        if annee_min is None:
            annee_min = 2014  # Les données DVF commencent en 2014

        try:
            self._rate_limit()

            response = self.session.get(
                self.BASE_URL,
                params={'code_postal': code_postal},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            transactions = data.get('resultats', [])
            transactions = [
                t for t in transactions
                if self._extract_year(t.get('date_mutation', '')) >= annee_min
            ]

            self._cache[cache_key] = transactions
            self._save_cache()

            return transactions

        except requests.RequestException:
            return []

    def _extract_year(self, date_str: str) -> int:
        """Extrait l'année d'une date."""
        try:
            if date_str:
                return int(date_str.split('-')[0])
        except (ValueError, IndexError, AttributeError):
            pass
        return 0

    def _get_type_local(self, transaction: Dict) -> str:
        """Extrait le type de local."""
        return (transaction.get('type_local') or '').strip()

    def _get_surface(self, transaction: Dict) -> float:
        """Extrait la surface."""
        # L'API a une typo: "surface_relle_bati" au lieu de "surface_reelle_bati"
        surface = transaction.get('surface_relle_bati') or transaction.get('surface_reelle_bati')
        if surface:
            try:
                return float(surface)
            except (ValueError, TypeError):
                pass
        return 0

    def _get_prix(self, transaction: Dict) -> float:
        """Extrait le prix."""
        prix = transaction.get('valeur_fonciere')
        if prix:
            try:
                return float(prix)
            except (ValueError, TypeError):
                pass
        return 0

    def calculate_price_per_sqm(
        self,
        transactions: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """
        Calcule les statistiques de prix au m².
        """
        prices_per_sqm = []

        for t in transactions:
            surface = self._get_surface(t)
            prix = self._get_prix(t)

            # Filtrer les transactions valides
            if surface > 9 and prix > 5000:
                price_sqm = prix / surface
                # Filtre des valeurs aberrantes
                if 100 < price_sqm < 25000:
                    prices_per_sqm.append(price_sqm)

        if not prices_per_sqm:
            return {
                'moyenne': 0,
                'mediane': 0,
                'min': 0,
                'max': 0,
                'ecart_type': 0,
                'nb_transactions': 0
            }

        prices = np.array(prices_per_sqm)

        return {
            'moyenne': float(np.mean(prices)),
            'mediane': float(np.median(prices)),
            'min': float(np.min(prices)),
            'max': float(np.max(prices)),
            'ecart_type': float(np.std(prices)),
            'nb_transactions': len(prices_per_sqm)
        }

    def get_nearby_postal_codes(self, code_postal: str, radius_km: int = 20) -> List[str]:
        """Trouve les codes postaux voisins (avec cache)."""
        cache_key = f"geo_nearby_{code_postal}_{radius_km}"

        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            self._rate_limit()

            # Coordonnées de la commune
            response = self.session.get(
                f"{self.GEO_API_URL}/communes",
                params={'codePostal': code_postal, 'fields': 'centre,codesPostaux'},
                timeout=10
            )
            response.raise_for_status()
            communes = response.json()

            if not communes:
                return [code_postal]

            centre = communes[0].get('centre', {}).get('coordinates', [])
            if not centre or len(centre) < 2:
                return [code_postal]

            lon, lat = centre[0], centre[1]

            self._rate_limit()

            # Communes dans le rayon
            response = self.session.get(
                f"{self.GEO_API_URL}/communes",
                params={
                    'lat': lat, 'lon': lon,
                    'distance': radius_km * 1000,
                    'fields': 'codesPostaux'
                },
                timeout=15
            )
            response.raise_for_status()
            nearby = response.json()

            postal_codes = set([code_postal])
            for c in nearby:
                for cp in c.get('codesPostaux', []):
                    postal_codes.add(cp)

            result = list(postal_codes)
            self._cache[cache_key] = result
            self._save_cache()
            return result

        except Exception:
            return [code_postal]

    def get_aggregated_transactions(
        self,
        code_postal: str,
        min_transactions: int = None
    ) -> Tuple[List[Dict[str, Any]], List[str], int]:
        """
        Récupère les transactions avec agrégation si nécessaire.
        """
        if min_transactions is None:
            min_transactions = self.MIN_TRANSACTIONS

        transactions = self.get_transactions_by_postal_code(code_postal)
        valid_transactions = [
            t for t in transactions
            if self._get_surface(t) > 0 and self._get_prix(t) > 0
        ]

        if len(valid_transactions) >= min_transactions:
            return valid_transactions, [code_postal], 0

        for radius in [15, 30, 50]:
            nearby_codes = self.get_nearby_postal_codes(code_postal, radius)
            all_transactions = []
            used_codes = []

            for cp in nearby_codes:
                cp_transactions = self.get_transactions_by_postal_code(cp)
                valid = [t for t in cp_transactions if self._get_surface(t) > 0 and self._get_prix(t) > 0]
                if valid:
                    all_transactions.extend(valid)
                    used_codes.append(cp)

            if len(all_transactions) >= min_transactions:
                return all_transactions, used_codes, radius

        return (all_transactions if all_transactions else valid_transactions,
                used_codes if used_codes else [code_postal], 50)

    def get_price_stats_by_type_aggregated(
        self,
        code_postal: str
    ) -> Dict[str, Any]:
        """Stats de prix par type avec agrégation automatique."""
        all_transactions, used_codes, radius = self.get_aggregated_transactions(code_postal)

        appartements = [t for t in all_transactions if self._get_type_local(t).lower() == 'appartement']
        maisons = [t for t in all_transactions if self._get_type_local(t).lower() == 'maison']

        return {
            'appartement': self.calculate_price_per_sqm(appartements),
            'maison': self.calculate_price_per_sqm(maisons),
            'global': self.calculate_price_per_sqm(all_transactions),
            'codes_postaux_utilises': used_codes,
            'rayon_km': radius,
            'est_agrege': len(used_codes) > 1
        }

    def get_price_stats_by_type(
        self,
        code_postal: str
    ) -> Dict[str, Dict[str, float]]:
        """Version simple sans agrégation."""
        transactions = self.get_transactions_by_postal_code(code_postal)

        appartements = [t for t in transactions if self._get_type_local(t).lower() == 'appartement']
        maisons = [t for t in transactions if self._get_type_local(t).lower() == 'maison']

        return {
            'appartement': self.calculate_price_per_sqm(appartements),
            'maison': self.calculate_price_per_sqm(maisons),
            'global': self.calculate_price_per_sqm(transactions)
        }


# Instance singleton
dvf_service = DVFService()
