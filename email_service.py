"""
Service d'envoi d'emails pour ValoMaison
- Alertes leads en temps reel
- Rapports quotidiens de trafic
- Utilise Brevo (ex-Sendinblue) API
"""

import os
import requests
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


def get_email_config():
    """Recupere la configuration email depuis les variables d'environnement."""
    return {
        'api_key': os.getenv('BREVO_API_KEY'),
        'sender_email': os.getenv('SENDER_EMAIL', 'contact@valomaison.fr'),
        'sender_name': os.getenv('SENDER_NAME', 'ValoMaison'),
        'notify_email': os.getenv('NOTIFY_EMAIL', 'contact@valomaison.fr')
    }


def send_email(subject, html_content, to_email=None):
    """
    Envoie un email via Brevo API.

    Args:
        subject: Sujet de l'email
        html_content: Contenu HTML de l'email
        to_email: Destinataire (defaut: NOTIFY_EMAIL)

    Returns:
        bool: True si envoi reussi, False sinon
    """
    config = get_email_config()

    if not config['api_key']:
        logger.warning("Cle API Brevo manquante - email non envoye")
        print("ERREUR: BREVO_API_KEY non configuree")
        return False

    to_email = to_email or config['notify_email']

    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "api-key": config['api_key']
    }

    payload = {
        "sender": {
            "name": config['sender_name'],
            "email": config['sender_email']
        },
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_content
    }

    try:
        print(f"Envoi email via Brevo a {to_email}...")
        response = requests.post(BREVO_API_URL, json=payload, headers=headers, timeout=30)

        if response.status_code == 201:
            logger.info(f"Email envoye: {subject}")
            print("Email envoye!")
            return True
        else:
            logger.error(f"Erreur Brevo: {response.status_code} - {response.text}")
            print(f"ERREUR: {response.status_code} - {response.text}")
            return False

    except requests.exceptions.Timeout:
        logger.error("Timeout lors de l'envoi")
        print("ERREUR: Timeout")
        return False
    except Exception as e:
        logger.error(f"Erreur envoi email: {e}")
        print(f"ERREUR: {e}")
        return False


def send_lead_alert(lead):
    """
    Envoie une alerte email immediate pour un nouveau lead.

    Args:
        lead: Instance du modele Lead
    """
    subject = f"[ValoMaison] Nouveau lead: {lead.type}"

    # Formater les donnees d'estimation si presentes
    estimation_info = ""
    if lead.estimation_data:
        data = lead.estimation_data
        estimation_info = f"""
        <tr><td><strong>Estimation</strong></td><td></td></tr>
        <tr><td>Code postal</td><td>{data.get('code_postal', '-')}</td></tr>
        <tr><td>Type de bien</td><td>{data.get('type_bien', '-')}</td></tr>
        <tr><td>Surface</td><td>{data.get('surface', '-')} m2</td></tr>
        <tr><td>Pieces</td><td>{data.get('nb_pieces', '-')}</td></tr>
        <tr><td>Prix estime</td><td>{data.get('prix_moyen', '-')} EUR</td></tr>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: #2563eb; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
            .content {{ background: #f8fafc; padding: 20px; border: 1px solid #e2e8f0; }}
            table {{ width: 100%; border-collapse: collapse; }}
            td {{ padding: 8px; border-bottom: 1px solid #e2e8f0; }}
            td:first-child {{ font-weight: 500; width: 40%; color: #64748b; }}
            .footer {{ text-align: center; padding: 20px; color: #94a3b8; font-size: 12px; }}
            .badge {{ display: inline-block; background: #22c55e; color: white; padding: 4px 12px; border-radius: 20px; font-size: 14px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Nouveau Lead</h1>
                <span class="badge">{lead.type.upper()}</span>
            </div>
            <div class="content">
                <table>
                    <tr><td><strong>Contact</strong></td><td></td></tr>
                    <tr><td>Nom</td><td>{lead.prenom} {lead.nom}</td></tr>
                    <tr><td>Telephone</td><td><a href="tel:{lead.telephone}">{lead.telephone}</a></td></tr>
                    <tr><td>Email</td><td><a href="mailto:{lead.email}">{lead.email or '-'}</a></td></tr>
                    <tr><td>Adresse</td><td>{lead.adresse or '-'}</td></tr>
                    <tr><td></td><td></td></tr>
                    <tr><td><strong>Demande</strong></td><td></td></tr>
                    <tr><td>Type</td><td>{lead.type}</td></tr>
                    <tr><td>Date souhaitee</td><td>{lead.date_souhaitee or '-'}</td></tr>
                    <tr><td>Creneau</td><td>{lead.creneau or '-'}</td></tr>
                    <tr><td>Horaires</td><td>{lead.horaires or '-'}</td></tr>
                    <tr><td>Projet</td><td>{lead.projet or '-'}</td></tr>
                    <tr><td>Message</td><td>{lead.message or '-'}</td></tr>
                    {estimation_info}
                </table>
            </div>
            <div class="footer">
                <p>Recu le {datetime.now().strftime('%d/%m/%Y a %H:%M')}</p>
                <p>ValoMaison - Estimation immobiliere</p>
            </div>
        </div>
    </body>
    </html>
    """

    return send_email(subject, html_content)


def send_daily_report(stats):
    """
    Envoie le rapport quotidien de trafic.

    Args:
        stats: Dictionnaire avec les statistiques du jour
            - visitors: nombre de visiteurs uniques
            - pageviews: nombre de pages vues
            - avg_time: temps moyen sur le site (secondes)
            - estimations: nombre d'estimations
            - leads: nombre de leads
            - top_pages: liste des pages les plus visitees
    """
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%d/%m/%Y')
    subject = f"[ValoMaison] Rapport du {yesterday}"

    # Formater le temps moyen
    avg_time_min = stats.get('avg_time', 0) // 60
    avg_time_sec = stats.get('avg_time', 0) % 60
    avg_time_str = f"{avg_time_min}min {avg_time_sec}s"

    # Top pages HTML
    top_pages_html = ""
    for page in stats.get('top_pages', [])[:10]:
        top_pages_html += f"<tr><td>{page['path']}</td><td style='text-align:right'>{page['views']}</td></tr>"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: #2563eb; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
            .content {{ background: #f8fafc; padding: 20px; border: 1px solid #e2e8f0; }}
            .stats-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; margin-bottom: 20px; }}
            .stat-card {{ background: white; padding: 15px; border-radius: 8px; text-align: center; border: 1px solid #e2e8f0; }}
            .stat-value {{ font-size: 28px; font-weight: bold; color: #2563eb; }}
            .stat-label {{ font-size: 12px; color: #64748b; text-transform: uppercase; }}
            .section {{ margin-top: 20px; }}
            .section h3 {{ margin-bottom: 10px; color: #1e293b; }}
            table {{ width: 100%; border-collapse: collapse; background: white; }}
            td {{ padding: 8px; border-bottom: 1px solid #e2e8f0; }}
            .footer {{ text-align: center; padding: 20px; color: #94a3b8; font-size: 12px; }}
            .highlight {{ background: #fef3c7; padding: 15px; border-radius: 8px; margin-top: 15px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Rapport Quotidien</h1>
                <p>{yesterday}</p>
            </div>
            <div class="content">
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-value">{stats.get('visitors', 0)}</div>
                        <div class="stat-label">Visiteurs</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{stats.get('pageviews', 0)}</div>
                        <div class="stat-label">Pages vues</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{avg_time_str}</div>
                        <div class="stat-label">Temps moyen</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{stats.get('estimations', 0)}</div>
                        <div class="stat-label">Estimations</div>
                    </div>
                </div>

                <div class="highlight">
                    <strong>{stats.get('leads', 0)} nouveau(x) lead(s)</strong> enregistre(s) hier
                </div>

                <div class="section">
                    <h3>Pages les plus visitees</h3>
                    <table>
                        <tr style="background:#f1f5f9"><td><strong>Page</strong></td><td style="text-align:right"><strong>Vues</strong></td></tr>
                        {top_pages_html}
                    </table>
                </div>
            </div>
            <div class="footer">
                <p>ValoMaison - Estimation immobiliere</p>
            </div>
        </div>
    </body>
    </html>
    """

    return send_email(subject, html_content)
