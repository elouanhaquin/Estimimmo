#!/usr/bin/env python3
"""
Script RAPIDE de mise à jour des statistiques DVF.
Utilise le multiprocessing pour paralléliser les requêtes.

Usage:
    python scripts/update_stats_fast.py
    python scripts/update_stats_fast.py --workers 20
    python scripts/update_stats_fast.py --dept 75
"""

import sys
import os
import argparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from flask import Flask
from models import db, Commune, Departement
from config import get_config

# Lock pour les prints thread-safe
print_lock = threading.Lock()

# Compteurs globaux
stats = {
    'processed': 0,
    'updated': 0,
    'errors': 0,
    'cached': 0
}
stats_lock = threading.Lock()


def create_app():
    """Crée une instance Flask pour ce worker."""
    app = Flask(__name__)
    app.config.from_object(get_config())
    db.init_app(app)
    return app


def get_dvf_data(code_postal, session):
    """Récupère les données DVF via l'API avec retry."""
    import requests

    url = "https://api.cquest.org/dvf"

    for attempt in range(3):
        try:
            response = session.get(
                url,
                params={'code_postal': code_postal},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            return data.get('resultats', [])
        except Exception as e:
            if attempt < 2:
                time.sleep(1)
            else:
                return None
    return None


def calculate_stats(transactions):
    """Calcule les stats à partir des transactions."""
    if not transactions:
        return None

    def get_surface(t):
        s = t.get('surface_relle_bati') or t.get('surface_reelle_bati')
        try:
            return float(s) if s else 0
        except:
            return 0

    def get_prix(t):
        p = t.get('valeur_fonciere')
        try:
            return float(p) if p else 0
        except:
            return 0

    def get_type(t):
        return (t.get('type_local') or '').strip().lower()

    def get_year(t):
        try:
            return int(t.get('date_mutation', '')[:4])
        except:
            return 0

    valid = [t for t in transactions if get_surface(t) > 9 and get_prix(t) > 5000]
    if not valid:
        return None

    appartements = [t for t in valid if get_type(t) == 'appartement']
    maisons = [t for t in valid if get_type(t) == 'maison']

    def calc_median(txs):
        prices = []
        for t in txs:
            surface = get_surface(t)
            prix = get_prix(t)
            if surface > 0:
                p = prix / surface
                if 100 < p < 25000:
                    prices.append(p)
        return np.median(prices) if prices else None

    current_year = datetime.now().year
    prev_year = current_year - 1

    def calc_evolution(txs):
        prev = [t for t in txs if get_year(t) == prev_year]
        curr = [t for t in txs if get_year(t) == current_year]
        prev_med = calc_median(prev)
        curr_med = calc_median(curr)
        if prev_med and curr_med and prev_med > 0:
            return ((curr_med - prev_med) / prev_med) * 100
        return None

    surfaces = [get_surface(t) for t in valid if get_surface(t) > 0]
    all_prices = []
    for t in valid:
        surface = get_surface(t)
        prix = get_prix(t)
        if surface > 0:
            p = prix / surface
            if 100 < p < 25000:
                all_prices.append(p)

    return {
        'prix_m2_appartement': calc_median(appartements),
        'prix_m2_maison': calc_median(maisons),
        'evolution_appartement': calc_evolution(appartements),
        'evolution_maison': calc_evolution(maisons),
        'nb_transactions_12m': len(valid),
        'prix_min': int(min(all_prices)) if all_prices else None,
        'prix_max': int(max(all_prices)) if all_prices else None,
        'surface_moyenne': np.mean(surfaces) if surfaces else None
    }


def process_commune(commune_data, cache):
    """Traite une commune (appelé dans un thread)."""
    import requests

    commune_id, code_postal = commune_data

    with stats_lock:
        stats['processed'] += 1

    if not code_postal:
        return None

    # Vérifier le cache
    if code_postal in cache:
        transactions = cache[code_postal]
        with stats_lock:
            stats['cached'] += 1
    else:
        # Requête API
        session = requests.Session()
        session.headers.update({'User-Agent': 'ValoMaison/1.0'})
        transactions = get_dvf_data(code_postal, session)

        if transactions is None:
            with stats_lock:
                stats['errors'] += 1
            return None

        cache[code_postal] = transactions

    # Calculer les stats
    result = calculate_stats(transactions)

    if result:
        with stats_lock:
            stats['updated'] += 1
        return (commune_id, result)

    return None


def main():
    parser = argparse.ArgumentParser(description='Mise à jour RAPIDE des stats DVF')
    parser.add_argument('--workers', type=int, default=10, help='Nombre de workers (defaut: 10)')
    parser.add_argument('--dept', type=str, help='Traiter un seul département')
    parser.add_argument('--limit', type=int, help='Limiter le nombre de communes')
    args = parser.parse_args()

    print(f"=== Mise a jour RAPIDE des stats DVF ===")
    print(f"Workers: {args.workers}")

    app = create_app()

    with app.app_context():
        # Charger les communes
        query = Commune.query
        if args.dept:
            query = query.filter(Commune.departement_code == args.dept)
            print(f"Departement: {args.dept}")
        if args.limit:
            query = query.limit(args.limit)

        communes = query.all()
        total = len(communes)
        print(f"Communes a traiter: {total}")

        # Préparer les données (id, code_postal)
        commune_data = [(c.id, c.code_postal) for c in communes]

        # Cache partagé thread-safe
        cache = {}
        cache_lock = threading.Lock()

        # Résultats
        results = []

        start_time = time.time()

        # Traitement parallèle
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(process_commune, data, cache): data
                for data in commune_data
            }

            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)

                # Progress
                with stats_lock:
                    processed = stats['processed']
                    if processed % 500 == 0:
                        elapsed = time.time() - start_time
                        rate = processed / elapsed if elapsed > 0 else 0
                        eta = (total - processed) / rate if rate > 0 else 0
                        with print_lock:
                            print(f"  {processed}/{total} ({stats['updated']} maj, {stats['cached']} cache, {stats['errors']} err) - {rate:.1f}/s - ETA: {eta/60:.1f}min")

        # Appliquer les résultats en batch
        print(f"\nApplication des {len(results)} mises a jour...")

        batch_size = 500
        for i in range(0, len(results), batch_size):
            batch = results[i:i+batch_size]
            for commune_id, data in batch:
                commune = Commune.query.get(commune_id)
                if commune:
                    if data['prix_m2_appartement']:
                        commune.prix_m2_appartement = data['prix_m2_appartement']
                    if data['prix_m2_maison']:
                        commune.prix_m2_maison = data['prix_m2_maison']
                    if data['evolution_appartement']:
                        commune.evolution_appartement = data['evolution_appartement']
                    if data['evolution_maison']:
                        commune.evolution_maison = data['evolution_maison']
                    if data['nb_transactions_12m']:
                        commune.nb_transactions_12m = data['nb_transactions_12m']
                    if data['prix_min']:
                        commune.prix_min = data['prix_min']
                    if data['prix_max']:
                        commune.prix_max = data['prix_max']
                    if data['surface_moyenne']:
                        commune.surface_moyenne = data['surface_moyenne']
                    commune.stats_updated_at = datetime.utcnow()

            db.session.commit()
            print(f"  Batch {i//batch_size + 1}/{(len(results)//batch_size) + 1} sauvegarde")

        # Stats départementales
        print("\nMise a jour des stats departementales...")
        if args.dept:
            departements = Departement.query.filter_by(code=args.dept).all()
        else:
            departements = Departement.query.all()

        for dept in departements:
            communes_with_data = [
                c for c in dept.communes
                if c.prix_m2_appartement or c.prix_m2_maison
            ]

            if communes_with_data:
                prix_appart = [c.prix_m2_appartement for c in communes_with_data if c.prix_m2_appartement]
                prix_maison = [c.prix_m2_maison for c in communes_with_data if c.prix_m2_maison]

                if prix_appart:
                    dept.prix_m2_appartement = np.median(prix_appart)
                if prix_maison:
                    dept.prix_m2_maison = np.median(prix_maison)

                dept.nb_transactions_12m = sum(c.nb_transactions_12m or 0 for c in communes_with_data)
                dept.stats_updated_at = datetime.utcnow()

        db.session.commit()

        elapsed = time.time() - start_time
        print(f"\n=== TERMINE ===")
        print(f"Temps total: {elapsed/60:.1f} minutes")
        print(f"Communes traitees: {stats['processed']}")
        print(f"Communes mises a jour: {stats['updated']}")
        print(f"Depuis cache: {stats['cached']}")
        print(f"Erreurs: {stats['errors']}")
        print(f"Departements: {len(departements)}")


if __name__ == '__main__':
    main()
