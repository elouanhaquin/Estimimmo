"""
Application Flask - Estimateur Immobilier
Base sur les donnees DVF (Demandes de Valeurs Foncieres)
"""

import os
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory, Response, abort
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from estimator import PropertyEstimator, PropertyCriteria
from config import get_config
from models import db, Lead, Commune, Departement, Activity, Consent
from security import (
    validate_estimation_data, validate_lead_data, validate_track_data,
    sanitize_string, validate_code_postal
)
from email_service import send_lead_alert

app = Flask(__name__)
app.config.from_object(get_config())

# === SECURITE ===

# Protection CSRF
csrf = CSRFProtect(app)

# Rate Limiting
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# Headers de securite
# Note: HTTPS est gere par Nginx, pas par Flask
csp = {
    'default-src': "'self'",
    'script-src': "'self' 'unsafe-inline' https://fonts.googleapis.com",
    'style-src': "'self' 'unsafe-inline' https://fonts.googleapis.com https://fonts.gstatic.com",
    'font-src': "'self' https://fonts.gstatic.com",
    'img-src': "'self' data:",
    'connect-src': "'self'",
}

if os.getenv('FLASK_ENV') == 'production':
    Talisman(
        app,
        content_security_policy=csp,
        force_https=False,  # Nginx gere HTTPS, pas Flask
        session_cookie_secure=True,
        session_cookie_http_only=True,
        strict_transport_security=True,
        strict_transport_security_max_age=31536000
    )
else:
    Talisman(
        app,
        content_security_policy=None,
        force_https=False,
        session_cookie_secure=False,
        session_cookie_http_only=True
    )

# Les exemptions CSRF sont ajoutees via decorateur sur chaque route API

# Initialisation de la base de données
db.init_app(app)
migrate = Migrate(app, db)


# Création des tables au démarrage
# En production, utiliser flask db upgrade (migrations)
try:
    with app.app_context():
        db.create_all()
except Exception as e:
    app.logger.warning(f"Could not create tables at startup: {e}")


# SEO Routes
@app.route('/robots.txt')
def robots():
    return send_from_directory(app.static_folder, 'robots.txt')


# Instance de l'estimateur
estimator = PropertyEstimator()


@app.route('/')
def index():
    """Page d'accueil - Landing page."""
    return render_template('index.html')


@app.route('/estimation')
def estimation():
    """Page du formulaire d'estimation."""
    return render_template('estimation.html')


@app.route('/a-propos')
def a_propos():
    """Page À propos."""
    return render_template('a-propos.html')


@app.route('/contact')
def contact():
    """Page Contact."""
    return render_template('contact.html')


@app.route('/politique-confidentialite')
def politique_confidentialite():
    """Page Politique de confidentialite."""
    return render_template('politique-confidentialite.html')


@app.route('/cgu')
def cgu():
    """Page Conditions Generales d'Utilisation."""
    return render_template('cgu.html')


@app.route('/mentions-legales')
def mentions_legales():
    """Page Mentions legales."""
    return render_template('mentions-legales.html')


# =====================================================
# PAGES COMMUNES (SEO)
# =====================================================

@app.route('/prix-immobilier')
def prix_immobilier_index():
    """Page index des prix immobiliers (liste des départements)."""
    departements = Departement.query.order_by(Departement.code).all()
    return render_template('prix-immobilier-index.html', departements=departements)


@app.route('/prix-immobilier/<slug>')
def commune_page(slug):
    """Page de prix immobilier pour une commune spécifique."""
    commune = Commune.query.filter_by(slug=slug).first()
    if not commune:
        abort(404)

    # Calculer les comparaisons avec le département
    comparison_appart = commune.get_comparison_dept('appartement')
    comparison_maison = commune.get_comparison_dept('maison')

    # Récupérer les communes voisines (avec prix)
    voisines = [v for v in commune.voisines[:10]
                if v.prix_m2_appartement or v.prix_m2_maison]

    return render_template(
        'commune.html',
        commune=commune,
        comparison_appart=comparison_appart,
        comparison_maison=comparison_maison,
        voisines=voisines
    )


# =====================================================
# SITEMAPS DYNAMIQUES
# =====================================================

@app.route('/sitemap.xml')
def sitemap_index():
    """Sitemap index principal."""
    # Compter les communes pour déterminer le nombre de sitemaps
    total_communes = Commune.query.count()
    num_sitemaps = (total_communes // 5000) + 1

    xml = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml.append('<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')

    # Sitemap des pages statiques
    xml.append(f'  <sitemap><loc>{request.url_root}sitemap-pages.xml</loc></sitemap>')

    # Sitemaps des communes (5000 par fichier max)
    for i in range(1, num_sitemaps + 1):
        xml.append(f'  <sitemap><loc>{request.url_root}sitemap-communes-{i}.xml</loc></sitemap>')

    xml.append('</sitemapindex>')

    return Response('\n'.join(xml), mimetype='application/xml')


@app.route('/sitemap-pages.xml')
def sitemap_pages():
    """Sitemap des pages statiques."""
    pages = [
        ('', '1.0', 'daily'),
        ('estimation', '0.9', 'weekly'),
        ('a-propos', '0.5', 'monthly'),
        ('contact', '0.5', 'monthly'),
        ('prix-immobilier', '0.8', 'daily'),
    ]

    xml = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')

    for path, priority, changefreq in pages:
        xml.append('  <url>')
        xml.append(f'    <loc>{request.url_root}{path}</loc>')
        xml.append(f'    <priority>{priority}</priority>')
        xml.append(f'    <changefreq>{changefreq}</changefreq>')
        xml.append('  </url>')

    xml.append('</urlset>')

    return Response('\n'.join(xml), mimetype='application/xml')


@app.route('/sitemap-communes-<int:page>.xml')
def sitemap_communes(page):
    """Sitemap paginé des communes (5000 par page)."""
    per_page = 5000
    offset = (page - 1) * per_page

    communes = Commune.query.order_by(Commune.id).offset(offset).limit(per_page).all()

    if not communes:
        abort(404)

    xml = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')

    for commune in communes:
        xml.append('  <url>')
        xml.append(f'    <loc>{request.url_root}prix-immobilier/{commune.slug}</loc>')
        xml.append('    <priority>0.6</priority>')
        xml.append('    <changefreq>weekly</changefreq>')
        if commune.stats_updated_at:
            xml.append(f'    <lastmod>{commune.stats_updated_at.strftime("%Y-%m-%d")}</lastmod>')
        xml.append('  </url>')

    xml.append('</urlset>')

    return Response('\n'.join(xml), mimetype='application/xml')


# =====================================================
# API
# =====================================================

@app.route('/api/estimate', methods=['POST'])
@csrf.exempt
@limiter.limit("30 per minute")  # Rate limit: 30 estimations/minute max
def api_estimate():
    """
    API d'estimation immobiliere.

    Attend un JSON avec les criteres du bien.
    Retourne l'estimation avec fourchette basse/moyenne/haute.
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'erreur': True,
                'message': 'Donnees manquantes'
            }), 400

        # Validation securisee des donnees
        validated, errors = validate_estimation_data(data)
        if errors:
            return jsonify({
                'erreur': True,
                'message': errors[0]  # Premier message d'erreur
            }), 400

        # Creation des criteres avec donnees validees
        criteria = PropertyCriteria(
            code_postal=validated['code_postal'],
            surface=validated['surface'],
            nb_pieces=validated['nb_pieces'],
            type_bien=validated['type_bien'],
            etage=validated['etage'],
            nb_etages_immeuble=validated['nb_etages_immeuble'],
            ascenseur=validated['ascenseur'],
            balcon_terrasse=validated['balcon_terrasse'],
            parking=validated['parking'],
            cave=validated['cave'],
            jardin=validated['jardin'],
            veranda=validated['veranda'],
            dependances=validated['dependances'],
            surface_terrain=validated['surface_terrain'],
            annee_construction=validated['annee_construction'],
            etat_general=validated['etat_general'],
            dpe=validated['dpe'],
            exposition=validated['exposition'],
            vue=validated['vue'],
            standing=validated['standing'],
            # Confort & Equipements
            cuisine_equipee=validated['cuisine_equipee'],
            double_vitrage=validated['double_vitrage'],
            climatisation=validated['climatisation'],
            cheminee=validated['cheminee'],
            parquet=validated['parquet'],
            fibre=validated['fibre'],
            # Securite
            alarme=validated['alarme'],
            digicode=validated['digicode'],
            gardien=validated['gardien'],
            portail_auto=validated['portail_auto'],
            # Exterieur Maison
            piscine=validated['piscine'],
            potager=validated['potager'],
            spa=validated['spa'],
            terrain_tennis=validated['terrain_tennis'],
            abri_jardin=validated['abri_jardin'],
            arrosage_auto=validated['arrosage_auto']
        )

        # Estimation
        result = estimator.estimate(criteria)

        return jsonify(result)

    except ValueError as e:
        return jsonify({
            'erreur': True,
            'message': f'Erreur de format: {str(e)}'
        }), 400
    except Exception as e:
        app.logger.error(f"Erreur lors de l'estimation: {e}")
        return jsonify({
            'erreur': True,
            'message': 'Erreur interne du serveur'
        }), 500


@app.route('/api/stats/<code_postal>')
@csrf.exempt
def api_stats(code_postal):
    """
    Récupère les statistiques de prix pour un code postal.

    Args:
        code_postal: Code postal à analyser

    Returns:
        Statistiques de prix par type de bien
    """
    try:
        from dvf_service import dvf_service
        stats = dvf_service.get_price_stats_by_type(code_postal)
        return jsonify(stats)
    except Exception as e:
        app.logger.error(f"Erreur lors de la récupération des stats: {e}")
        return jsonify({
            'erreur': True,
            'message': str(e)
        }), 500


@app.route('/api/leads', methods=['POST'])
@csrf.exempt
@limiter.limit("10 per minute")  # Rate limit strict: 10 leads/minute max
def api_leads():
    """
    API pour enregistrer les leads (demandes de rappel/visite).
    Stocke les leads dans PostgreSQL.
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({'erreur': True, 'message': 'Donnees manquantes'}), 400

        # Validation securisee des donnees
        validated, errors = validate_lead_data(data)
        if errors:
            return jsonify({'erreur': True, 'message': errors[0]}), 400

        # Parser la date si fournie
        date_souhaitee = None
        if validated.get('date_souhaitee'):
            try:
                date_souhaitee = datetime.strptime(validated['date_souhaitee'], '%Y-%m-%d').date()
            except ValueError:
                pass

        # Creer le lead avec donnees validees
        lead = Lead(
            type=validated['type'],
            nom=validated['nom'],
            prenom=validated['prenom'],
            telephone=validated['telephone'],
            email=validated['email'],
            adresse=validated['adresse'],
            date_souhaitee=date_souhaitee,
            creneau=validated['creneau'],
            horaires=validated['horaires'],
            projet=validated['projet'],
            message=validated['message'],
            estimation_data=validated['estimation_data'],
            status='nouveau'
        )

        db.session.add(lead)
        db.session.commit()

        app.logger.info(f"Nouveau lead enregistre: {lead.type} - {lead.telephone} (ID: {lead.id})")

        # Envoyer alerte email (async-safe, ne bloque pas la reponse)
        try:
            send_lead_alert(lead)
        except Exception as e:
            app.logger.warning(f"Erreur envoi alerte lead: {e}")

        return jsonify({
            'success': True,
            'message': 'Demande enregistree avec succes',
            'id': lead.id
        })

    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Erreur lors de l'enregistrement du lead: {e}")
        return jsonify({
            'erreur': True,
            'message': 'Erreur lors de l\'enregistrement'
        }), 500


@app.route('/api/track', methods=['POST'])
@csrf.exempt
@limiter.limit("100 per minute")  # Rate limit: 100 events/minute max
def api_track():
    """
    API pour tracker l'activite des visiteurs.
    Enregistre les pageviews, clics, progression formulaire, etc.
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({'success': False}), 400

        # Validation securisee des donnees
        validated, error = validate_track_data(data)
        if error:
            return jsonify({'success': False}), 400

        # Creer l'activite avec donnees validees
        activity = Activity(
            session_id=validated['session_id'],
            visitor_id=validated['visitor_id'],
            event_type=validated['event_type'],
            page_url=validated['page_url'],
            page_path=validated['page_path'],
            referrer=validated['referrer'],
            element_id=validated['element_id'],
            element_text=validated['element_text'],
            element_class=validated['element_class'],
            form_step=validated['form_step'],
            form_field=validated['form_field'],
            scroll_depth=validated['scroll_depth'],
            extra_data=validated['extra_data'],
            user_agent=sanitize_string(request.headers.get('User-Agent', ''), 500),
            screen_width=validated['screen_width'],
            screen_height=validated['screen_height'],
            ip_address=request.remote_addr,
            time_on_page=validated['time_on_page']
        )

        db.session.add(activity)
        db.session.commit()

        return jsonify({'success': True})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False}), 500


@app.route('/api/consent', methods=['POST'])
@csrf.exempt
@limiter.limit("20 per minute")  # Rate limit: 20 consentements/minute max
def api_consent():
    """
    API pour enregistrer le consentement RGPD.
    Stocke la preuve de consentement avec IP et timestamp.
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({'success': False}), 400

        visitor_id = sanitize_string(data.get('visitor_id'), 64)
        if not visitor_id:
            return jsonify({'success': False}), 400

        consent = Consent(
            visitor_id=visitor_id,
            ip_address=request.remote_addr,
            consent_type=sanitize_string(data.get('consent_type', 'cookies'), 20),
            consent_value=bool(data.get('consent_value', False)),
            consent_text=sanitize_string(data.get('consent_text'), 1000),
            page_url=sanitize_string(data.get('page_url'), 500),
            user_agent=sanitize_string(request.headers.get('User-Agent', ''), 500)
        )

        db.session.add(consent)
        db.session.commit()

        return jsonify({'success': True})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False}), 500


@app.route('/api/health')
@csrf.exempt
def health():
    """Endpoint de vérification de santé."""
    try:
        # Vérifier la connexion à la base de données
        db.session.execute(db.text('SELECT 1'))
        db_status = 'connected'
    except Exception as e:
        db_status = f'error: {str(e)}'

    # Retourner OK meme si DB down (pour que le container reste up)
    return jsonify({
        'status': 'ok',
        'database': db_status,
        'service': 'running'
    })


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
