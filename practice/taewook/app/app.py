import os
from html import escape

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

app = FastAPI(title="Taewook 배포 실습")


@app.middleware("http")
async def disable_cache(request: Request, call_next):
    response = await call_next(request)
    # 버전이 바뀌면 이전 응답이 남지 않도록 캐시를 끈다.
    response.headers["Cache-Control"] = "no-store"
    return response


def release_info():
    return {
        "service": "taewook-app",
        "version": os.getenv("APP_VERSION", "dev"),
        "git_sha": os.getenv("GIT_SHA", "local"),
        "release": os.getenv("RELEASE_ID", "local"),
        "instance": os.getenv("INSTANCE", "local"),
    }


@app.get("/", response_class=HTMLResponse)
def index():
    info = release_info()
    return f"""<!doctype html>
<html lang="ko">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Demo App</title>
</head>
<body>
    <h1>Demo App</h1>
    <p>버전: {escape(info["version"])}</p>
    <p>서버: {escape(info["instance"])}</p>
    <p>상태: 정상</p>
</body>
</html>"""


@app.get("/health")
def health():
    return {**release_info(), "status": "ok"}


@app.get("/version")
def version():
    return release_info()
