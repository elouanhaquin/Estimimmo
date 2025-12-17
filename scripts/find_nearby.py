#!/usr/bin/env python3
"""
Script pour calculer les communes voisines (maillage interne SEO).

Exécuter avec: python scripts/find_nearby.py
Options:
  --limit N    : Traiter seulement N communes (pour test)
  --dept XX    : Traiter seulement le département XX
"""

import sys
import os
import argparse
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models import Commune, commune_voisines


def haversine_distance(lat1, lon1, lat2, lon2):
    """Calcule la distance en km entre deux points GPS."""
    R = 6371
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (math.sin(delta_lat / 2) ** 2 +
         math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def find_nearby_communes(commune, all_communes, max_distance_km=30, max_neighbors=10):
    """Trouve les communes voisines les plus proches."""
    if not commune.latitude or not commune.longitude:
        return []

    distances = []
    for other in all_communes:
        if other.id == commune.id:
            continue
        if not other.latitude or not other.longitude:
            continue

        distance = haversine_distance(
            commune.latitude, commune.longitude,
            other.latitude, other.longitude
        )

        if distance <= max_distance_km:
            distances.append((other, distance))

    distances.sort(key=lambda x: x[1])
    return distances[:max_neighbors]


def main():
    parser = argparse.ArgumentParser(description='Calcul des communes voisines')
    parser.add_argument('--limit', type=int, help='Limiter le nombre de communes')
    parser.add_argument('--dept', type=str, help='Traiter un seul département')
    parser.add_argument('--max-distance', type=int, default=30, help='Distance max en km')
    parser.add_argument('--max-neighbors', type=int, default=10, help='Nombre max de voisines')
    args = parser.parse_args()

    print(f"Calcul des communes voisines (max {args.max_distance}km, {args.max_neighbors} voisines)...")

    with app.app_context():
        all_communes = Commune.query.filter(
            Commune.latitude.isnot(None),
            Commune.longitude.isnot(None)
        ).all()

        query = Commune.query.filter(
            Commune.latitude.isnot(None),
            Commune.longitude.isnot(None)
        )
        if args.dept:
            query = query.filter(Commune.departement_code == args.dept)
        if args.limit:
            query = query.limit(args.limit)

        communes_to_process = query.all()
        total = len(communes_to_process)

        # Vider les relations existantes
        if args.dept:
            for commune in communes_to_process:
                commune.voisines = []
        else:
            db.session.execute(commune_voisines.delete())
        db.session.commit()

        processed = 0
        batch_size = 500

        for i, commune in enumerate(communes_to_process, 1):
            nearby = find_nearby_communes(
                commune, all_communes,
                max_distance_km=args.max_distance,
                max_neighbors=args.max_neighbors
            )

            if nearby:
                for neighbor, distance in nearby:
                    stmt = commune_voisines.insert().values(
                        commune_id=commune.id,
                        voisine_id=neighbor.id,
                        distance_km=round(distance, 2)
                    )
                    try:
                        db.session.execute(stmt)
                    except Exception:
                        pass
                processed += 1

            if i % batch_size == 0:
                db.session.commit()
                print(f"  {i}/{total} communes traitees")

        db.session.commit()
        print(f"Termine: {processed}/{total} communes avec voisines")


if __name__ == '__main__':
    main()
