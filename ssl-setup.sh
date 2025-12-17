#!/bin/bash
# ============================================
# Script de configuration SSL - Let's Encrypt
# Pour ValoMaison
# ============================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Charger les variables d'environnement
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

DOMAIN=${DOMAIN:-"valomaison.fr"}
EMAIL=${SSL_EMAIL:-"admin@$DOMAIN"}

show_help() {
    echo "Usage: ./ssl-setup.sh [COMMAND]"
    echo ""
    echo "Commandes:"
    echo "  init        Obtenir les certificats SSL (premiere fois)"
    echo "  renew       Renouveler les certificats"
    echo "  enable      Activer SSL dans Nginx"
    echo "  status      Verifier l'etat des certificats"
    echo "  help        Afficher cette aide"
    echo ""
    echo "Variables (.env):"
    echo "  DOMAIN      Nom de domaine (default: valomaison.fr)"
    echo "  SSL_EMAIL   Email pour Let's Encrypt"
}

# Installer Certbot si necessaire
install_certbot() {
    if ! command -v certbot &> /dev/null; then
        log_info "Installation de Certbot..."
        apt-get update
        apt-get install -y certbot
    else
        log_info "Certbot deja installe"
    fi
}

# Obtenir les certificats (premiere fois)
init_ssl() {
    log_info "=== Obtention des certificats SSL pour $DOMAIN ==="

    install_certbot

    # Arreter Nginx temporairement pour liberer le port 80
    log_info "Arret temporaire de Nginx..."
    docker-compose stop nginx || true

    # Obtenir les certificats en mode standalone
    log_info "Obtention des certificats via Let's Encrypt..."
    certbot certonly \
        --standalone \
        --non-interactive \
        --agree-tos \
        --email "$EMAIL" \
        -d "$DOMAIN" \
        -d "www.$DOMAIN"

    # Copier les certificats dans le dossier nginx/ssl
    log_info "Copie des certificats..."
    mkdir -p nginx/ssl
    cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem nginx/ssl/
    cp /etc/letsencrypt/live/$DOMAIN/privkey.pem nginx/ssl/
    chmod 600 nginx/ssl/privkey.pem

    # Activer SSL dans la config Nginx
    enable_ssl

    # Redemarrer Nginx
    log_info "Redemarrage de Nginx avec SSL..."
    docker-compose up -d nginx

    log_info "=== SSL configure avec succes ! ==="
    echo ""
    echo "Votre site est maintenant accessible en HTTPS:"
    echo "  https://$DOMAIN"
    echo "  https://www.$DOMAIN"
}

# Activer SSL dans nginx.conf
enable_ssl() {
    log_info "Activation de SSL dans nginx.conf..."

    # Utiliser la config SSL
    if [ -f nginx/nginx-ssl.conf ]; then
        cp nginx/nginx-ssl.conf nginx/nginx.conf
        log_info "Configuration SSL activee"
    else
        log_error "nginx/nginx-ssl.conf non trouve!"
        exit 1
    fi
}

# Renouveler les certificats
renew_ssl() {
    log_info "=== Renouvellement des certificats SSL ==="

    # Renouveler via Certbot
    certbot renew --quiet

    # Copier les nouveaux certificats
    if [ -f /etc/letsencrypt/live/$DOMAIN/fullchain.pem ]; then
        cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem nginx/ssl/
        cp /etc/letsencrypt/live/$DOMAIN/privkey.pem nginx/ssl/
        chmod 600 nginx/ssl/privkey.pem

        # Recharger Nginx
        docker-compose exec nginx nginx -s reload
        log_info "Certificats renouveles et Nginx recharge"
    fi
}

# Verifier l'etat des certificats
status_ssl() {
    log_info "=== Etat des certificats SSL ==="

    if [ -f nginx/ssl/fullchain.pem ]; then
        echo ""
        echo "Certificat:"
        openssl x509 -in nginx/ssl/fullchain.pem -noout -subject -dates
        echo ""

        # Verifier expiration
        EXPIRY=$(openssl x509 -in nginx/ssl/fullchain.pem -noout -enddate | cut -d= -f2)
        EXPIRY_EPOCH=$(date -d "$EXPIRY" +%s)
        NOW_EPOCH=$(date +%s)
        DAYS_LEFT=$(( ($EXPIRY_EPOCH - $NOW_EPOCH) / 86400 ))

        if [ $DAYS_LEFT -lt 30 ]; then
            log_warn "Certificat expire dans $DAYS_LEFT jours - Renouvellement recommande"
        else
            log_info "Certificat valide encore $DAYS_LEFT jours"
        fi
    else
        log_warn "Aucun certificat trouve dans nginx/ssl/"
        echo "Executez: ./ssl-setup.sh init"
    fi
}

# Setup du cron pour renouvellement auto
setup_cron() {
    log_info "Configuration du renouvellement automatique..."

    CRON_CMD="0 3 * * * cd $(pwd) && ./ssl-setup.sh renew >> /var/log/ssl-renew.log 2>&1"

    # Ajouter au crontab si pas deja present
    (crontab -l 2>/dev/null | grep -v "ssl-setup.sh"; echo "$CRON_CMD") | crontab -

    log_info "Cron configure: renouvellement tous les jours a 3h"
}

# Main
case "${1:-help}" in
    init)
        init_ssl
        setup_cron
        ;;
    renew)
        renew_ssl
        ;;
    enable)
        enable_ssl
        ;;
    status)
        status_ssl
        ;;
    help|*)
        show_help
        ;;
esac
