FROM apache/airflow:3.2.0-python3.11

COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt

USER root
RUN apt-get update && \
    apt-get install -y --no-install-recommends openjdk-17-jre-headless && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    python -m playwright install-deps chromium && \
    mkdir -p /opt/airflow/project/data/heart_failure/raw \
             /opt/airflow/project/data/heart_failure/processed \
             /opt/airflow/project/data/heart_failure/artifacts && \
    chown -R airflow:root /opt/airflow/project

USER airflow
RUN python -m playwright install chromium
