-- Import des donnees depuis les fichiers CSV

-- Import departements
COPY departements(code, nom, region, prix_m2_appartement, prix_m2_maison, evolution_appartement, evolution_maison, nb_transactions_12m, stats_updated_at)
FROM '/docker-entrypoint-initdb.d/departements.csv'
WITH (FORMAT csv, HEADER true, NULL '');

-- Import communes
COPY communes(id, code_postal, code_insee, nom, slug, departement_code, region, population, latitude, longitude, prix_m2_appartement, prix_m2_maison, evolution_appartement, evolution_maison, nb_transactions_12m, prix_min, prix_max, surface_moyenne, stats_updated_at)
FROM '/docker-entrypoint-initdb.d/communes.csv'
WITH (FORMAT csv, HEADER true, NULL '');

-- Reset sequence pour communes.id
SELECT setval('communes_id_seq', (SELECT MAX(id) FROM communes));

-- Verification
DO $$
DECLARE
    dept_count INTEGER;
    commune_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO dept_count FROM departements;
    SELECT COUNT(*) INTO commune_count FROM communes;
    RAISE NOTICE 'Import termine: % departements, % communes', dept_count, commune_count;
END $$;
