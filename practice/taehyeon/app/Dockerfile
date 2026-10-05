FROM eclipse-temurin:25-jre
WORKDIR /app

# 빌드 정보를 이미지에 저장해 테스트와 배포에서 그대로 사용한다.
ARG APP_VERSION=local
ARG GIT_SHA=local
ARG RELEASE_ID=local
ENV APP_VERSION=${APP_VERSION} GIT_SHA=${GIT_SHA} RELEASE_ID=${RELEASE_ID}

COPY build/libs/jenkins-deploy-lab-0.0.1-SNAPSHOT.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
