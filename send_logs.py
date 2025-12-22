"""
Script pour envoyer les logs par email via Brevo API
Usage: python send_logs.py logs_web.txt
"""

import os
import sys
import base64
import requests
from datetime import datetime

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"

def send_logs_email(log_file_path):
    api_key = os.getenv('BREVO_API_KEY')
    sender_email = os.getenv('SENDER_EMAIL', 'contact@valomaison.fr')
    sender_name = os.getenv('SENDER_NAME', 'ValoMaison')
    notify_email = os.getenv('NOTIFY_EMAIL', 'contact@valomaison.fr')

    if not api_key:
        print("ERREUR: BREVO_API_KEY non configuree")
        print("Export la variable: export BREVO_API_KEY=ta_cle")
        return False

    # Lire le fichier de log
    if not os.path.exists(log_file_path):
        print(f"ERREUR: Fichier {log_file_path} introuvable")
        return False

    with open(log_file_path, 'rb') as f:
        log_content = f.read()

    # Encoder en base64 pour l'API Brevo
    log_base64 = base64.b64encode(log_content).decode('utf-8')

    # Nom du fichier
    filename = os.path.basename(log_file_path)

    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "api-key": api_key
    }

    payload = {
        "sender": {
            "name": sender_name,
            "email": sender_email
        },
        "to": [{"email": notify_email}],
        "subject": f"[ValoMaison] Logs serveur - {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        "htmlContent": f"""
        <html>
        <body>
            <h2>Logs serveur ValoMaison</h2>
            <p>Date: {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
            <p>Fichier joint: {filename}</p>
            <p>Taille: {len(log_content) / 1024:.1f} KB</p>
        </body>
        </html>
        """,
        "attachment": [
            {
                "content": log_base64,
                "name": filename
            }
        ]
    }

    try:
        print(f"Envoi des logs a {notify_email}...")
        response = requests.post(BREVO_API_URL, json=payload, headers=headers, timeout=30)

        if response.status_code == 201:
            print("Email envoye avec succes!")
            return True
        else:
            print(f"ERREUR: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        print(f"ERREUR: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python send_logs.py <fichier_log>")
        print("Exemple: python send_logs.py logs_web.txt")
        sys.exit(1)

    log_file = sys.argv[1]
    success = send_logs_email(log_file)
    sys.exit(0 if success else 1)
