#!/bin/bash
set -e

echo "=== ValoMaison - Demarrage ==="

# Attendre que la base de donnees soit prete
echo "Attente de la base de donnees..."
python -c "
import time
import sys
from sqlalchemy import create_engine, text
import os

db_url = os.environ.get('DATABASE_URL', 'sqlite:///valomaison.db')
max_retries = 30
retry_interval = 2

for i in range(max_retries):
    try:
        engine = create_engine(db_url)
        with engine.connect() as conn:
            result = conn.execute(text('SELECT COUNT(*) FROM communes'))
            count = result.scalar()
            print(f'Base de donnees accessible - {count} communes')
        sys.exit(0)
    except Exception as e:
        print(f'Tentative {i+1}/{max_retries} - En attente... ({e})')
        time.sleep(retry_interval)

print('Impossible de se connecter a la base de donnees')
sys.exit(1)
"

echo "=== Demarrage de Gunicorn ==="
exec gunicorn --config gunicorn.conf.py app:app
