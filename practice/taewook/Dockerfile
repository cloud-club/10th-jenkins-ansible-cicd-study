FROM python:3.12-alpine
WORKDIR /app
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
ARG APP_VERSION
ARG GIT_SHA
ARG RELEASE_ID
ENV APP_VERSION=${APP_VERSION} GIT_SHA=${GIT_SHA} RELEASE_ID=${RELEASE_ID} PYTHONUNBUFFERED=1
COPY app/app.py .
USER 10001:10001
EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
