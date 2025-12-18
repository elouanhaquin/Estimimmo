-- Script d'initialisation PostgreSQL - ValoMaison
-- Ce script est execute automatiquement au premier demarrage du container PostgreSQL

-- Table departements
CREATE TABLE IF NOT EXISTS departements (
    code VARCHAR(3) NOT NULL PRIMARY KEY,
    nom VARCHAR(100) NOT NULL,
    region VARCHAR(100),
    prix_m2_appartement FLOAT,
    prix_m2_maison FLOAT,
    evolution_appartement FLOAT,
    evolution_maison FLOAT,
    nb_transactions_12m INTEGER,
    stats_updated_at TIMESTAMP
);

-- Table communes
CREATE TABLE IF NOT EXISTS communes (
    id SERIAL PRIMARY KEY,
    code_postal VARCHAR(5),
    code_insee VARCHAR(5),
    nom VARCHAR(100) NOT NULL,
    slug VARCHAR(120),
    departement_code VARCHAR(3) REFERENCES departements(code),
    region VARCHAR(100),
    population INTEGER,
    latitude FLOAT,
    longitude FLOAT,
    prix_m2_appartement FLOAT,
    prix_m2_maison FLOAT,
    evolution_appartement FLOAT,
    evolution_maison FLOAT,
    nb_transactions_12m INTEGER,
    prix_min INTEGER,
    prix_max INTEGER,
    surface_moyenne FLOAT,
    stats_updated_at TIMESTAMP
);

-- Index communes
CREATE UNIQUE INDEX IF NOT EXISTS ix_communes_slug ON communes (slug);
CREATE UNIQUE INDEX IF NOT EXISTS ix_communes_code_insee ON communes (code_insee);
CREATE INDEX IF NOT EXISTS ix_communes_code_postal ON communes (code_postal);

-- Table commune_voisines (relation N:N)
CREATE TABLE IF NOT EXISTS commune_voisines (
    commune_id INTEGER NOT NULL REFERENCES communes(id),
    voisine_id INTEGER NOT NULL REFERENCES communes(id),
    distance_km FLOAT,
    PRIMARY KEY (commune_id, voisine_id)
);

-- Table leads
CREATE TABLE IF NOT EXISTS leads (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    commune_id INTEGER REFERENCES communes(id),
    bien_type VARCHAR(20),
    surface FLOAT,
    pieces INTEGER,
    estimation_basse INTEGER,
    estimation_haute INTEGER,
    nom VARCHAR(100),
    email VARCHAR(120),
    telephone VARCHAR(20),
    projet VARCHAR(50),
    delai VARCHAR(50),
    commentaire TEXT,
    source_page VARCHAR(255),
    ip_address VARCHAR(45),
    user_agent TEXT
);

CREATE INDEX IF NOT EXISTS ix_leads_email ON leads (email);
CREATE INDEX IF NOT EXISTS ix_leads_created_at ON leads (created_at);

-- Collectivites d'outre-mer manquantes (referencees par des communes)
INSERT INTO departements (code, nom, region) VALUES
('975', 'Saint-Pierre-et-Miquelon', 'Saint-Pierre-et-Miquelon'),
('977', 'Saint-Barthelemy', 'Saint-Barthelemy'),
('978', 'Saint-Martin', 'Saint-Martin'),
('986', 'Wallis-et-Futuna', 'Wallis-et-Futuna'),
('987', 'Polynesie francaise', 'Polynesie francaise'),
('988', 'Nouvelle-Caledonie', 'Nouvelle-Caledonie'),
('989', 'Ile de Clipperton', 'Ile de Clipperton')
ON CONFLICT (code) DO NOTHING;
