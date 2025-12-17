#!/usr/bin/env python3
"""
Script de mise à jour des statistiques DVF pour toutes les communes.
À exécuter régulièrement (cron hebdomadaire recommandé).

Exécuter avec: python scripts/update_stats.py
Options:
  --limit N    : Traiter seulement N communes (pour test)
  --dept XX    : Traiter seulement le département XX
"""

import sys
import os
import argparse
from datetime import datetime
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models import Commune, Departement
from dvf_service import DVFService


def calculate_evolution(stats_current, stats_previous):
    """Calcule l'évolution en % entre deux années."""
    if not stats_previous or stats_previous.get('moyenne', 0) == 0:
        return None
    if not stats_current or stats_current.get('moyenne', 0) == 0:
        return None
    return ((stats_current['moyenne'] - stats_previous['moyenne']) /
            stats_previous['moyenne']) * 100


def update_commune_stats(commune, dvf_service, current_year):
    """Met à jour les stats DVF d'une commune."""
    code_postal = commune.code_postal
    if not code_postal:
        return False

    try:
        transactions = dvf_service.get_transactions_by_postal_code(code_postal)
        valid_transactions = [
            t for t in transactions
            if dvf_service._get_surface(t) > 0 and dvf_service._get_prix(t) > 0
        ]

        if not valid_transactions:
            return False

        appartements = [t for t in valid_transactions
                       if dvf_service._get_type_local(t).lower() == 'appartement']
        maisons = [t for t in valid_transactions
                  if dvf_service._get_type_local(t).lower() == 'maison']

        stats_appart = dvf_service.calculate_price_per_sqm(appartements)
        if stats_appart['nb_transactions'] > 0:
            commune.prix_m2_appartement = stats_appart['mediane']

        stats_maison = dvf_service.calculate_price_per_sqm(maisons)
        if stats_maison['nb_transactions'] > 0:
            commune.prix_m2_maison = stats_maison['mediane']

        stats_global = dvf_service.calculate_price_per_sqm(valid_transactions)
        commune.nb_transactions_12m = stats_global['nb_transactions']
        commune.prix_min = int(stats_global['min']) if stats_global['min'] else None
        commune.prix_max = int(stats_global['max']) if stats_global['max'] else None

        surfaces = [dvf_service._get_surface(t) for t in valid_transactions
                   if dvf_service._get_surface(t) > 0]
        if surfaces:
            commune.surface_moyenne = np.mean(surfaces)

        # Évolution sur 1 an
        prev_year = current_year - 1
        transactions_prev = [
            t for t in valid_transactions
            if dvf_service._extract_year(t.get('date_mutation', '')) == prev_year
        ]
        transactions_current = [
            t for t in valid_transactions
            if dvf_service._extract_year(t.get('date_mutation', '')) == current_year
        ]

        if transactions_prev and transactions_current:
            appart_prev = [t for t in transactions_prev
                          if dvf_service._get_type_local(t).lower() == 'appartement']
            appart_curr = [t for t in transactions_current
                          if dvf_service._get_type_local(t).lower() == 'appartement']
            stats_appart_prev = dvf_service.calculate_price_per_sqm(appart_prev)
            stats_appart_curr = dvf_service.calculate_price_per_sqm(appart_curr)
            commune.evolution_appartement = calculate_evolution(
                stats_appart_curr, stats_appart_prev
            )

            maison_prev = [t for t in transactions_prev
                          if dvf_service._get_type_local(t).lower() == 'maison']
            maison_curr = [t for t in transactions_current
                          if dvf_service._get_type_local(t).lower() == 'maison']
            stats_maison_prev = dvf_service.calculate_price_per_sqm(maison_prev)
            stats_maison_curr = dvf_service.calculate_price_per_sqm(maison_curr)
            commune.evolution_maison = calculate_evolution(
                stats_maison_curr, stats_maison_prev
            )

        commune.stats_updated_at = datetime.utcnow()
        return True

    except Exception:
        return False


def update_departement_stats(departement):
    """Agrège les stats de toutes les communes d'un département."""
    communes_with_data = [
        c for c in departement.communes
        if c.prix_m2_appartement or c.prix_m2_maison
    ]

    if not communes_with_data:
        return

    prix_appart = [c.prix_m2_appartement for c in communes_with_data if c.prix_m2_appartement]
    prix_maison = [c.prix_m2_maison for c in communes_with_data if c.prix_m2_maison]
    evol_appart = [c.evolution_appartement for c in communes_with_data if c.evolution_appartement is not None]
    evol_maison = [c.evolution_maison for c in communes_with_data if c.evolution_maison is not None]
    total_transactions = sum(c.nb_transactions_12m or 0 for c in communes_with_data)

    if prix_appart:
        departement.prix_m2_appartement = np.median(prix_appart)
    if prix_maison:
        departement.prix_m2_maison = np.median(prix_maison)
    if evol_appart:
        departement.evolution_appartement = np.median(evol_appart)
    if evol_maison:
        departement.evolution_maison = np.median(evol_maison)

    departement.nb_transactions_12m = total_transactions
    departement.stats_updated_at = datetime.utcnow()


def main():
    parser = argparse.ArgumentParser(description='Mise à jour des stats DVF')
    parser.add_argument('--limit', type=int, help='Limiter le nombre de communes')
    parser.add_argument('--dept', type=str, help='Traiter un seul département')
    args = parser.parse_args()

    current_year = datetime.now().year
    print(f"Mise a jour des stats DVF (annee: {current_year})...")

    with app.app_context():
        dvf_service = DVFService()

        query = Commune.query
        if args.dept:
            query = query.filter(Commune.departement_code == args.dept)
        if args.limit:
            query = query.limit(args.limit)

        communes = query.all()
        total = len(communes)
        updated = 0
        batch_size = 100

        for i, commune in enumerate(communes, 1):
            if update_commune_stats(commune, dvf_service, current_year):
                updated += 1

            if i % batch_size == 0:
                db.session.commit()
                print(f"  {i}/{total} communes traitees ({updated} avec donnees)")

        db.session.commit()

        # Stats départementales
        if args.dept:
            departements = Departement.query.filter_by(code=args.dept).all()
        else:
            departements = Departement.query.all()

        for dept in departements:
            update_departement_stats(dept)

        db.session.commit()

        print(f"Termine: {updated}/{total} communes mises a jour, {len(departements)} departements")


if __name__ == '__main__':
    main()
