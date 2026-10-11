#!/bin/sh
set -eu

if [ "$#" -eq 0 ]; then
    echo "Usage: gradle-in-docker.sh TASK [GRADLE_OPTIONS...]" >&2
    exit 2
fi
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
app_dir=$(CDPATH= cd -- "$script_dir/../app" && pwd)

# Agent의 Java 버전 대신 JDK 25를 사용한다. 결과물은 Agent 계정 소유로 생성한다.
# Gradle 캐시는 해당 앱의 무시되는 .gradle 디렉터리에만 보관한다.
docker run --rm \
    --user "$(id -u):$(id -g)" \
    --env HOME=/tmp \
    --env GRADLE_USER_HOME=/workspace/.gradle/ci-cache \
    --mount "type=bind,source=$app_dir,target=/workspace" \
    --workdir /workspace \
    eclipse-temurin:25-jdk \
    sh ./gradlew --no-daemon "$@"
