FROM python:3.12-slim

ARG APP_VERSION=local
ARG RELEASE_ID=local
ARG GIT_REVISION=unknown
ENV APP_VERSION=${APP_VERSION} \
    RELEASE_ID=${RELEASE_ID} \
    GIT_REVISION=${GIT_REVISION} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
LABEL org.opencontainers.image.version=${APP_VERSION} \
    org.opencontainers.image.revision=${GIT_REVISION}
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2)"
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
