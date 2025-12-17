#!/bin/bash
# ============================================
# Script d'installation initiale ValoMaison
# Pour VPS Ubuntu/Debian
# ============================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Verifier qu'on est root
if [ "$EUID" -ne 0 ]; then
    log_error "Ce script doit etre execute en root (sudo)"
    exit 1
fi

log_info "=== Installation ValoMaison ==="

# 1. Mise a jour du systeme
log_info "Mise a jour du systeme..."
apt-get update && apt-get upgrade -y

# 2. Installation des dependances
log_info "Installation des dependances..."
apt-get install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    git \
    ufw \
    fail2ban

# 3. Installation de Docker
if ! command -v docker &> /dev/null; then
    log_info "Installation de Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm get-docker.sh
    systemctl enable docker
    systemctl start docker
else
    log_info "Docker deja installe"
fi

# 4. Installation de Docker Compose
if ! command -v docker-compose &> /dev/null; then
    log_info "Installation de Docker Compose..."
    curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
else
    log_info "Docker Compose deja installe"
fi

# 5. Configuration du firewall
log_info "Configuration du firewall..."
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow http
ufw allow https
ufw --force enable

# 6. Configuration de fail2ban
log_info "Configuration de fail2ban..."
systemctl enable fail2ban
systemctl start fail2ban

# 7. Creer l'utilisateur de deploiement
if ! id "deploy" &>/dev/null; then
    log_info "Creation de l'utilisateur deploy..."
    useradd -m -s /bin/bash -G docker deploy
    log_warn "N'oubliez pas de configurer le mot de passe: passwd deploy"
    log_warn "Et d'ajouter votre cle SSH: ssh-copy-id deploy@<ip>"
fi

# 8. Creer le repertoire de l'application
APP_DIR="/opt/valomaison"
log_info "Creation du repertoire $APP_DIR..."
mkdir -p $APP_DIR
chown deploy:deploy $APP_DIR

# 9. Instructions finales
echo ""
log_info "=== Installation terminee ==="
echo ""
echo "Prochaines etapes:"
echo ""
echo "1. Connectez-vous en tant que 'deploy':"
echo "   su - deploy"
echo ""
echo "2. Clonez le repository:"
echo "   cd /opt/valomaison"
echo "   git clone git@github.com:elouanhaquin/Estimimmo.git ."
echo ""
echo "3. Configurez l'environnement:"
echo "   cp .env.example .env"
echo "   nano .env  # Modifier les variables"
echo ""
echo "4. Lancez le deploiement:"
echo "   chmod +x deploy.sh"
echo "   ./deploy.sh deploy"
echo ""
echo "5. (Optionnel) Configurez SSL avec Let's Encrypt:"
echo "   apt install certbot"
echo "   certbot certonly --standalone -d valomaison.fr"
echo "   # Puis copiez les certificats dans nginx/ssl/"
echo ""
log_info "Bonne installation!"
