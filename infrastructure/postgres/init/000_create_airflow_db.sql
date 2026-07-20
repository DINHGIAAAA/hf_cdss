-- Create airflow database for Airflow metadata
-- This runs automatically when PostgreSQL container starts

-- Create the airflow database (owned by hf_cdss user)
CREATE DATABASE airflow OWNER hf_cdss;

-- Grant all privileges on airflow database to hf_cdss
GRANT ALL PRIVILEGES ON DATABASE airflow TO hf_cdss;

-- Connect to airflow database and grant schema permissions
\c airflow;
GRANT ALL ON SCHEMA public TO hf_cdss;
