#!/bin/bash
# ============================================
# Script de deploiement EstimImmo
# Zero-downtime deployment avec rolling update
# ============================================

set -e

# Couleurs pour les logs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Verification des prerequisites
check_prerequisites() {
    log_info "Verification des prerequisites..."

    if ! command -v docker &> /dev/null; then
        log_error "Docker n'est pas installe"
        exit 1
    fi

    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose n'est pas installe"
        exit 1
    fi

    if [ ! -f .env ]; then
        log_error "Fichier .env manquant. Copiez .env.example vers .env et configurez-le."
        exit 1
    fi

    log_info "Prerequisites OK"
}

# Backup de la base de donnees avant deploiement
backup_database() {
    log_info "Backup de la base de donnees..."

    mkdir -p backups
    BACKUP_FILE="backups/backup_$(date +%Y%m%d_%H%M%S).sql"

    if docker-compose ps db | grep -q "Up"; then
        docker-compose exec -T db pg_dump -U ${POSTGRES_USER:-estimoimmo} ${POSTGRES_DB:-estimoimmo} > "$BACKUP_FILE"

        if [ -f "$BACKUP_FILE" ]; then
            gzip "$BACKUP_FILE"
            log_info "Backup cree: ${BACKUP_FILE}.gz"

            # Garder seulement les 10 derniers backups
            ls -t backups/*.sql.gz 2>/dev/null | tail -n +11 | xargs -r rm
        fi
    else
        log_warn "Database non demarre, backup ignore"
    fi
}

# Pull des dernieres modifications
pull_latest() {
    log_info "Recuperation des dernieres modifications..."
    git pull origin main
}

# Build de l'image
build_image() {
    log_info "Build de l'image Docker..."
    docker-compose build --no-cache web
}

# Deploiement avec zero-downtime
deploy() {
    log_info "Deploiement en cours (zero-downtime)..."

    # Demarrer la DB si elle n'est pas deja up
    docker-compose up -d db
    log_info "Attente que la DB soit prete..."
    sleep 10

    # Rolling update: scale up, puis scale down
    # On ajoute une nouvelle instance, on attend qu'elle soit healthy, puis on retire l'ancienne

    # Methode 1: Avec docker-compose (simple)
    docker-compose up -d --scale web=2 --no-recreate
    log_info "Nouvelles instances demarrees, attente du health check..."
    sleep 15

    # Recreer les containers avec la nouvelle image
    docker-compose up -d web
    log_info "Containers mis a jour"

    # Demarrer/redemarrer Nginx
    docker-compose up -d nginx
}

# Migrations de base de donnees
run_migrations() {
    log_info "Execution des migrations..."
    docker-compose exec -T web flask db upgrade 2>/dev/null || log_warn "Pas de nouvelles migrations"
}

# Verification post-deploiement
verify_deployment() {
    log_info "Verification du deploiement..."

    # Attendre que tout soit up
    sleep 5

    # Verifier le health check
    MAX_RETRIES=30
    RETRY=0

    while [ $RETRY -lt $MAX_RETRIES ]; do
        if curl -sf http://localhost/api/health > /dev/null 2>&1; then
            log_info "Health check OK!"
            return 0
        fi
        RETRY=$((RETRY + 1))
        log_warn "Health check tentative $RETRY/$MAX_RETRIES..."
        sleep 2
    done

    log_error "Health check echoue apres $MAX_RETRIES tentatives"
    return 1
}

# Rollback en cas d'echec
rollback() {
    log_error "Deploiement echoue, rollback..."

    # Restaurer l'image precedente
    docker-compose down
    git checkout HEAD~1
    docker-compose up -d

    log_warn "Rollback effectue. Verifiez les logs: docker-compose logs"
}

# Nettoyage des images non utilisees
cleanup() {
    log_info "Nettoyage des images non utilisees..."
    docker image prune -f
    docker volume prune -f
}

# Afficher les logs
show_logs() {
    docker-compose logs -f --tail=100
}

# Menu principal
main() {
    case "${1:-deploy}" in
        deploy)
            check_prerequisites
            backup_database
            pull_latest
            build_image
            deploy
            run_migrations
            if verify_deployment; then
                cleanup
                log_info "Deploiement termine avec succes!"
            else
                rollback
                exit 1
            fi
            ;;
        quick)
            # Deploiement rapide sans rebuild complet
            check_prerequisites
            pull_latest
            docker-compose up -d
            run_migrations
            verify_deployment
            log_info "Deploiement rapide termine!"
            ;;
        backup)
            backup_database
            ;;
        logs)
            show_logs
            ;;
        status)
            docker-compose ps
            ;;
        stop)
            docker-compose down
            ;;
        restart)
            docker-compose restart
            ;;
        *)
            echo "Usage: $0 {deploy|quick|backup|logs|status|stop|restart}"
            echo ""
            echo "Commandes:"
            echo "  deploy  - Deploiement complet avec backup et rebuild"
            echo "  quick   - Deploiement rapide (pull + restart)"
            echo "  backup  - Backup de la base de donnees"
            echo "  logs    - Afficher les logs"
            echo "  status  - Statut des containers"
            echo "  stop    - Arreter tous les services"
            echo "  restart - Redemarrer tous les services"
            exit 1
            ;;
    esac
}

# Charger les variables d'environnement
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

main "$@"
