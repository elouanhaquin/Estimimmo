"""
Application Flask - Estimateur Immobilier
Basé sur les données DVF (Demandes de Valeurs Foncières)
"""

from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory, Response, abort
from flask_migrate import Migrate
from estimator import PropertyEstimator, PropertyCriteria
from config import get_config
from models import db, Lead, Commune, Departement, Activity, Consent

app = Flask(__name__)
app.config.from_object(get_config())

# Initialisation de la base de données
db.init_app(app)
migrate = Migrate(app, db)


# Création des tables au démarrage (développement uniquement)
with app.app_context():
    db.create_all()


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
def api_estimate():
    """
    API d'estimation immobilière.

    Attend un JSON avec les critères du bien.
    Retourne l'estimation avec fourchette basse/moyenne/haute.
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'erreur': True,
                'message': 'Données manquantes'
            }), 400

        # Validation des champs requis
        required_fields = ['code_postal', 'surface', 'nb_pieces', 'type_bien']
        for field in required_fields:
            if field not in data or data[field] is None:
                return jsonify({
                    'erreur': True,
                    'message': f'Champ requis manquant: {field}'
                }), 400

        # Création des critères
        criteria = PropertyCriteria(
            code_postal=str(data['code_postal']),
            surface=float(data['surface']),
            nb_pieces=int(data['nb_pieces']),
            type_bien=data['type_bien'],
            etage=int(data['etage']) if data.get('etage') else None,
            nb_etages_immeuble=int(data['nb_etages_immeuble']) if data.get('nb_etages_immeuble') else None,
            ascenseur=data.get('ascenseur', False),
            balcon_terrasse=data.get('balcon_terrasse', False),
            parking=data.get('parking', False),
            cave=data.get('cave', False),
            jardin=data.get('jardin', False),
            veranda=data.get('veranda', False),
            dependances=data.get('dependances', False),
            surface_terrain=float(data['surface_terrain']) if data.get('surface_terrain') else None,
            annee_construction=int(data['annee_construction']) if data.get('annee_construction') else None,
            etat_general=data.get('etat_general', 'bon'),
            dpe=data.get('dpe') if data.get('dpe') else None,
            exposition=data.get('exposition') if data.get('exposition') else None,
            vue=data.get('vue') if data.get('vue') else None,
            standing=data.get('standing', 'standard'),
            # Confort & Équipements
            cuisine_equipee=data.get('cuisine_equipee', False),
            double_vitrage=data.get('double_vitrage', False),
            climatisation=data.get('climatisation', False),
            cheminee=data.get('cheminee', False),
            parquet=data.get('parquet', False),
            fibre=data.get('fibre', False),
            # Sécurité
            alarme=data.get('alarme', False),
            digicode=data.get('digicode', False),
            gardien=data.get('gardien', False),
            portail_auto=data.get('portail_auto', False),
            # Extérieur Maison
            piscine=data.get('piscine', False),
            potager=data.get('potager', False),
            spa=data.get('spa', False),
            terrain_tennis=data.get('terrain_tennis', False),
            abri_jardin=data.get('abri_jardin', False),
            arrosage_auto=data.get('arrosage_auto', False)
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
def api_leads():
    """
    API pour enregistrer les leads (demandes de rappel/visite).
    Stocke les leads dans PostgreSQL.
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({'erreur': True, 'message': 'Données manquantes'}), 400

        # Validation basique
        if not data.get('telephone'):
            return jsonify({'erreur': True, 'message': 'Téléphone requis'}), 400

        # Parser la date si fournie
        date_souhaitee = None
        if data.get('date_souhaitee'):
            try:
                date_souhaitee = datetime.strptime(data['date_souhaitee'], '%Y-%m-%d').date()
            except ValueError:
                pass

        # Créer le lead
        lead = Lead(
            type=data.get('type', 'callback'),
            nom=data.get('nom'),
            prenom=data.get('prenom'),
            telephone=data.get('telephone'),
            email=data.get('email'),
            adresse=data.get('adresse'),
            date_souhaitee=date_souhaitee,
            creneau=data.get('creneau'),
            horaires=data.get('horaires'),
            projet=data.get('projet'),
            message=data.get('message'),
            estimation_data=data.get('estimation_data'),
            status='nouveau'
        )

        db.session.add(lead)
        db.session.commit()

        app.logger.info(f"Nouveau lead enregistré: {lead.type} - {lead.telephone} (ID: {lead.id})")

        return jsonify({
            'success': True,
            'message': 'Demande enregistrée avec succès',
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
def api_track():
    """
    API pour tracker l'activité des visiteurs.
    Enregistre les pageviews, clics, progression formulaire, etc.
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({'success': False}), 400

        # Session ID requis
        session_id = data.get('session_id')
        if not session_id:
            return jsonify({'success': False}), 400

        # Créer l'activité
        activity = Activity(
            session_id=session_id,
            visitor_id=data.get('visitor_id'),
            event_type=data.get('event_type', 'pageview'),
            page_url=data.get('page_url'),
            page_path=data.get('page_path'),
            referrer=data.get('referrer'),
            element_id=data.get('element_id'),
            element_text=data.get('element_text', '')[:200] if data.get('element_text') else None,
            element_class=data.get('element_class', '')[:200] if data.get('element_class') else None,
            form_step=data.get('form_step'),
            form_field=data.get('form_field'),
            scroll_depth=data.get('scroll_depth'),
            extra_data=data.get('extra_data'),
            user_agent=request.headers.get('User-Agent', '')[:500],
            screen_width=data.get('screen_width'),
            screen_height=data.get('screen_height'),
            ip_address=request.remote_addr,
            time_on_page=data.get('time_on_page')
        )

        db.session.add(activity)
        db.session.commit()

        return jsonify({'success': True})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False}), 500


@app.route('/api/consent', methods=['POST'])
def api_consent():
    """
    API pour enregistrer le consentement RGPD.
    Stocke la preuve de consentement avec IP et timestamp.
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({'success': False}), 400

        visitor_id = data.get('visitor_id')
        if not visitor_id:
            return jsonify({'success': False}), 400

        consent = Consent(
            visitor_id=visitor_id,
            ip_address=request.remote_addr,
            consent_type=data.get('consent_type', 'cookies'),
            consent_value=data.get('consent_value', False),
            consent_text=data.get('consent_text'),
            page_url=data.get('page_url'),
            user_agent=request.headers.get('User-Agent', '')[:500]
        )

        db.session.add(consent)
        db.session.commit()

        return jsonify({'success': True})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False}), 500


@app.route('/api/health')
def health():
    """Endpoint de vérification de santé."""
    try:
        # Vérifier la connexion à la base de données
        db.session.execute(db.text('SELECT 1'))
        return jsonify({'status': 'ok', 'database': 'connected'})
    except Exception as e:
        return jsonify({'status': 'error', 'database': 'disconnected', 'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
