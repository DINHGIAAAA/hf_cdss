-- Dedicated metadata database for Airflow (separate from hf_cdss app data).
SELECT 'CREATE DATABASE airflow'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'airflow')\gexec
