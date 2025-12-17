"""
Configuration de l'application - ValoMaison
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Configuration de base."""
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

    # API DVF
    DVF_API_URL = "https://api.cquest.org/dvf"
    CACHE_TIMEOUT = 3600  # 1 heure

    # Database
    SQLALCHEMY_DATABASE_URI = os.getenv(
        'DATABASE_URL',
        'sqlite:///valomaison.db'  # SQLite par défaut pour le développement
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,  # Vérifie les connexions avant utilisation
    }


class DevelopmentConfig(Config):
    """Configuration de développement."""
    DEBUG = True
    SQLALCHEMY_ECHO = False


class ProductionConfig(Config):
    """Configuration de production."""
    DEBUG = False
    SQLALCHEMY_ECHO = False

    # Pool de connexions optimisé pour la production
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_size': 5,
        'pool_recycle': 300,
        'max_overflow': 10,
    }


class TestingConfig(Config):
    """Configuration de test."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'


# Mapping des configurations
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}


def get_config():
    """Retourne la configuration selon l'environnement."""
    env = os.getenv('FLASK_ENV', 'development')
    return config.get(env, config['default'])
