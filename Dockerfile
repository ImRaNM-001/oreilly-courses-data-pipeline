FROM apache/airflow:2.10.5

USER root

# Install system dependencies for Playwright
RUN apt update && apt upgrade && apt install -y \
    libwoff1 \
    libopus0 \
    libwebpdemux2 \
    libharfbuzz-icu0 \
    libwebpmux3 \
    libenchant-2-2 \
    libhyphen0 \
    libegl1 \
    libglx0 \
    libgudev-1.0-0 \
    libevdev2 \
    libgles2 \
    libx264-155 \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libxcomposite1 \
    libxrandr2 \
    libxdamage1 \
    libxkbcommon0 \
    libgbm1 \
    libpango1.0-0 \
    libasound2 \
    libwayland-client0 \
    libwayland-cursor0 \
    libwayland-egl1 \
    libxshmfence1 \
    && rm -rf /var/lib/apt/lists/*              # Remove cached package lists to reduce image size

# Copy requirements.txt
COPY requirements.txt /requirements.txt

# Install dependencies
RUN pip3 install --no-cache-dir -r /requirements.txt && \
    playwright install

# Switch to the airflow user
USER airflow
    