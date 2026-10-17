# 파일 역할: Python 실습 앱과 변경할 수 없는 빌드 버전 정보를 하나의 배포 이미지로 만든다.
# Python 표준 라이브러리 HTTP 앱을 실행할 기본 이미지를 선택한다.
FROM python:3.12-slim
# 앱 소스와 빌드 메타데이터가 저장될 작업 디렉터리를 지정한다.
WORKDIR /app
# Jenkins에서 확정한 버전·릴리스·커밋을 빌드 인자로 받는다.
ARG APP_VERSION
ARG RELEASE_ID
ARG GIT_REVISION
LABEL io.sohyeon.owner="sohyeon" io.sohyeon.project="sohyeon-cicd" io.sohyeon.release="$RELEASE_ID"
# 실행에 필요한 앱 소스만 이미지에 복사한다.
COPY app/server.py ./server.py
# 릴리스 정보는 이미지에 고정한다. 실행 시에는 SERVER_ID만 전달한다.
RUN python -c 'import json,sys; keys=("version","release_id","git_revision"); assert all(sys.argv[1:]); json.dump(dict(zip(keys,sys.argv[1:])),open("release.json","w"))' "$APP_VERSION" "$RELEASE_ID" "$GIT_REVISION"
# 컨테이너 내부 서비스 포트를 명시한다. 호스트 포트 연결은 Ansible에서 설정한다.
EXPOSE 80
# 컨테이너 시작 시 앱을 실행하고 로그를 즉시 출력한다.
CMD ["python", "-u", "server.py"]
