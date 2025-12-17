#!/usr/bin/env python3
"""
Script d'import des communes françaises depuis l'API geo.api.gouv.fr
Exécuter avec: python scripts/import_communes.py
"""

import sys
import os
import time
import requests

# Ajouter le répertoire parent au path pour importer les modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models import Commune, Departement, generate_slug

GEO_API_URL = "https://geo.api.gouv.fr"


def fetch_departements():
    """Récupère tous les départements depuis l'API."""
    url = f"{GEO_API_URL}/departements?fields=nom,code,codeRegion"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_regions():
    """Récupère toutes les régions depuis l'API."""
    url = f"{GEO_API_URL}/regions"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return {r['code']: r['nom'] for r in response.json()}


def fetch_communes():
    """Récupère toutes les communes depuis l'API."""
    url = f"{GEO_API_URL}/communes?fields=nom,code,codesPostaux,codeDepartement,codeRegion,population,centre&limit=50000"
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    return response.json()


def import_departements(departements_data, regions):
    """Importe les départements en base."""
    count = 0

    for dept in departements_data:
        existing = Departement.query.get(dept['code'])
        if existing:
            continue

        departement = Departement(
            code=dept['code'],
            nom=dept['nom'],
            region=regions.get(dept.get('codeRegion', ''), '')
        )
        db.session.add(departement)
        count += 1

    db.session.commit()
    print(f"Departements: {count} importes")


def import_communes(communes_data, regions):
    """Importe les communes en base."""
    count = 0
    skipped = 0
    batch_size = 1000

    for commune_data in communes_data:
        codes_postaux = commune_data.get('codesPostaux', [])
        if not codes_postaux:
            skipped += 1
            continue

        code_postal = codes_postaux[0]
        code_insee = commune_data['code']

        existing = Commune.query.filter_by(code_insee=code_insee).first()
        if existing:
            skipped += 1
            continue

        centre = commune_data.get('centre', {})
        coords = centre.get('coordinates', [None, None]) if centre else [None, None]

        slug = generate_slug(commune_data['nom'], code_postal)
        slug_count = Commune.query.filter(Commune.slug.like(f"{slug}%")).count()
        if slug_count > 0:
            slug = f"{slug}-{slug_count + 1}"

        commune = Commune(
            code_postal=code_postal,
            code_insee=code_insee,
            nom=commune_data['nom'],
            slug=slug,
            departement_code=commune_data.get('codeDepartement'),
            region=regions.get(commune_data.get('codeRegion', ''), ''),
            population=commune_data.get('population'),
            longitude=coords[0] if coords else None,
            latitude=coords[1] if coords else None
        )
        db.session.add(commune)
        count += 1

        if count % batch_size == 0:
            db.session.commit()

    db.session.commit()
    print(f"Communes: {count} importees ({skipped} ignorees)")


def main():
    """Fonction principale d'import."""
    print("Import des communes francaises...")

    with app.app_context():
        db.create_all()

        try:
            regions = fetch_regions()
            time.sleep(0.5)
            departements_data = fetch_departements()
            time.sleep(0.5)
            communes_data = fetch_communes()

            import_departements(departements_data, regions)
            import_communes(communes_data, regions)

            print(f"Total: {Departement.query.count()} departements, {Commune.query.count()} communes")

        except requests.RequestException as e:
            print(f"Erreur API: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"Erreur: {e}")
            db.session.rollback()
            raise


if __name__ == '__main__':
    main()
