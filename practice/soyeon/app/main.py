"""배포 상태와 버전 식별 정보를 제공하는 FastAPI 실습 앱."""

import os
import socket

from fastapi import FastAPI, Response

app = FastAPI(title="Soyeon Deployment Lab")


def deployment_info() -> dict[str, str]:
    """환경 변수와 호스트 정보를 배포 확인용 응답으로 반환한다."""
    hostname = socket.gethostname()
    return {
        "service": "soyeon-app",
        "version": os.getenv("APP_VERSION", "local"),
        "release": os.getenv("RELEASE_ID", "local"),
        "revision": os.getenv("GIT_REVISION", "unknown"),
        "instance": os.getenv("INSTANCE_ID", hostname),
        "hostname": hostname,
        "slot": os.getenv("DEPLOYMENT_SLOT", "primary"),
    }


@app.get("/")
@app.get("/version")
def version(response: Response) -> dict[str, str]:
    response.headers["Cache-Control"] = "no-store"
    return deployment_info()


@app.get("/health")
def health(response: Response) -> dict[str, str]:
    response.headers["Cache-Control"] = "no-store"
    return {"status": "ok", **deployment_info()}
