#!/usr/bin/env python
"""
Script d'envoi du rapport quotidien de trafic ValoMaison.
A executer via cron chaque matin.

Usage:
    python scripts/send_daily_report.py

Cron (tous les jours a 8h):
    0 8 * * * cd /app && python scripts/send_daily_report.py
"""

import sys
import os

# Ajouter le repertoire parent au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from sqlalchemy import func, distinct
from app import app, db
from models import Activity, Lead
from email_service import send_daily_report


def calculate_daily_stats():
    """
    Calcule les statistiques des dernieres 24 heures.

    Returns:
        dict: Statistiques du jour
    """
    # Periode: dernières 24h
    now = datetime.now()
    yesterday = now - timedelta(hours=24)

    with app.app_context():
        # Visiteurs uniques (visitor_id distinct)
        visitors = db.session.query(
            func.count(distinct(Activity.visitor_id))
        ).filter(
            Activity.timestamp >= yesterday,
            Activity.timestamp <= now
        ).scalar() or 0

        # Pages vues
        pageviews = db.session.query(
            func.count(Activity.id)
        ).filter(
            Activity.timestamp >= yesterday,
            Activity.timestamp <= now,
            Activity.event_type == 'pageview'
        ).scalar() or 0

        # Temps moyen sur le site (moyenne des time_on_page)
        avg_time = db.session.query(
            func.avg(Activity.time_on_page)
        ).filter(
            Activity.timestamp >= yesterday,
            Activity.timestamp <= now,
            Activity.time_on_page.isnot(None),
            Activity.time_on_page > 0
        ).scalar() or 0

        # Nombre d'estimations (event_type = 'estimation_complete' ou page /estimation avec form_step)
        estimations = db.session.query(
            func.count(Activity.id)
        ).filter(
            Activity.timestamp >= yesterday,
            Activity.timestamp <= now,
            Activity.event_type == 'form_submit'
        ).scalar() or 0

        # Nouveaux leads
        leads = db.session.query(
            func.count(Lead.id)
        ).filter(
            Lead.created_at >= yesterday,
            Lead.created_at <= now
        ).scalar() or 0

        # Top pages
        top_pages_query = db.session.query(
            Activity.page_path,
            func.count(Activity.id).label('views')
        ).filter(
            Activity.timestamp >= yesterday,
            Activity.timestamp <= now,
            Activity.event_type == 'pageview'
        ).group_by(
            Activity.page_path
        ).order_by(
            func.count(Activity.id).desc()
        ).limit(10).all()

        top_pages = [{'path': p[0], 'views': p[1]} for p in top_pages_query]

        return {
            'visitors': visitors,
            'pageviews': pageviews,
            'avg_time': int(avg_time) if avg_time else 0,
            'estimations': estimations,
            'leads': leads,
            'top_pages': top_pages
        }


def main():
    """Point d'entree du script."""
    print(f"[{datetime.now()}] Calcul des statistiques...")

    stats = calculate_daily_stats()

    print(f"  Visiteurs: {stats['visitors']}")
    print(f"  Pages vues: {stats['pageviews']}")
    print(f"  Temps moyen: {stats['avg_time']}s")
    print(f"  Estimations: {stats['estimations']}")
    print(f"  Leads: {stats['leads']}")

    print(f"[{datetime.now()}] Envoi du rapport...")

    if send_daily_report(stats):
        print("Rapport envoye avec succes!")
    else:
        print("Erreur lors de l'envoi du rapport.")
        sys.exit(1)


if __name__ == '__main__':
    main()
