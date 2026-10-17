FROM python:3.12-alpine

# 빌드 시점에 고정되는 값. /version이 "실제로 배포된 이미지"를 가리키게 한다.
ARG APP_VERSION=dev
ARG GIT_SHA=unknown
ENV APP_VERSION=${APP_VERSION} \
    GIT_SHA=${GIT_SHA} \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY app/app.py .

# root가 아닌 사용자로 실행
USER 65534

EXPOSE 8080

# docker ps에서 healthy/unhealthy가 보이게 한다 (3주차 장애 탐지에서 사용)
HEALTHCHECK --interval=5s --timeout=2s --retries=3 \
  CMD wget -qO- http://127.0.0.1:8080/health >/dev/null || exit 1

CMD ["python", "app.py"]
