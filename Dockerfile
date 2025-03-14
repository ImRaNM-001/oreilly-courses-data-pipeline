FROM apache/airflow:2.10.5

WORKDIR /opt/airflow

USER root

# Copy requirements.txt
COPY requirements.txt .

# Set environment variable for Playwright browsers
ENV PLAYWRIGHT_BROWSERS_PATH=/home/airflow/.cache/ms-playwright

RUN pip3 install --no-cache-dir -r requirements.txt && \
    mkdir -p $PLAYWRIGHT_BROWSERS_PATH && \
    playwright install --with-deps && \
    chown -R airflow $PLAYWRIGHT_BROWSERS_PATH && chmod -R 755 $PLAYWRIGHT_BROWSERS_PATH
    
WORKDIR /opt/airflow

# Switch to the airflow user
USER airflow
    