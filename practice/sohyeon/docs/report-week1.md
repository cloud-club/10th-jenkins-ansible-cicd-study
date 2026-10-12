> 문서 역할: Week1 CI/CD 구성 요소가 필요한 이유와 각 작업의 실행 위치를 설명하는 학습 자료다.

# 1주 차 CI/CD 프로젝트 이해하기

> 이전 대화에서 작성한 설명을 바탕으로 복원한 문서다. 설명 당시 저장소 코드를 기준으로 하며, 실제 Jenkins UI 설정과 서버 실행 상태는 별도 확인이 필요하다.
>
> 목표: 각 파일의 문법을 외우는 것보다 **왜 필요하고 어디서 실행되는지** 설명할 수 있게 되기.

## 목차

1. [무엇을 만든 프로젝트인가](#1-무엇을-만든-프로젝트인가)
2. [서버와 요청 흐름](#2-서버와-요청-흐름)
3. [앱과 Docker](#3-앱과-docker)
4. [Jenkins 실행 과정](#4-jenkins-실행-과정)
5. [SSH 인증](#5-ssh-인증)
6. [Ansible 배포와 변수 전달](#6-ansible-배포와-변수-전달)
7. [Nginx 로드밸런서](#7-nginx-로드밸런서)
8. [검증과 장애 확인](#8-검증과-장애-확인)
9. [구현 범위와 한계](#9-구현-범위와-한계)
10. [직접 만든다면 어떤 순서인가](#10-직접-만든다면-어떤-순서인가)
11. [이해도 확인](#11-이해도-확인)

## 1. 무엇을 만든 프로젝트인가

**Jenkins에서 실행하면 앱을 이미지로 만들고, 테스트하고, 서버 3대에 배포하는 자동화 프로젝트다.**

자동화가 없다면 사람이 매번 다음 일을 해야 한다.

```text
앱 작성 → 이미지 생성 → 테스트 → 서버 3대로 전달
→ 기존 앱 교체 → 서버별 확인 → 사용자 접속 경로 확인
```

이 반복 작업을 도구로 나눠 자동화했다.

| 도구 | 담당 | 코드 |
| --- | --- | --- |
| Jenkins | 전체 작업의 순서와 실행 관리 | `Jenkinsfile` |
| Ansible | 원격 서버에 접속해서 배포·설정·검증 수행 | `ansible/` |
| Docker | 앱을 이미지로 묶고 컨테이너로 실행 | `Dockerfile` 및 배포 명령 |
| Nginx | 사용자 요청 분산, 실습용 앱의 HTTP 응답 | LB 설정 및 앱 설정 |

빌드·테스트는 CI에 해당하는 작업이고, 배포 자동화는 CD에 해당하는 작업이다. 이번 요구사항은 Jenkins UI에서 실행하는 방식이다. GitHub에 푸시할 때 자동 실행되는지는 별도 Job 설정을 확인해야 한다.

## 2. 서버와 요청 흐름

### 서버별 역할

| 서버 | IP | 하는 일 |
| --- | --- | --- |
| VM 1 | `1.201.117.194` | Jenkins Controller: Job과 실행 관리 |
| VM 2 | `1.201.116.180` | Jenkins Agent: 빌드·테스트 및 Ansible 실행 |
| VM 3 | `1.201.116.156` | Nginx Load Balancer: 요청 분산 |
| VM 4 | `1.201.118.202` | 앱 컨테이너 실행 |
| VM 5 | `1.201.118.10` | 앱 컨테이너 실행 |
| VM 6 | `1.201.118.90` | 앱 컨테이너 실행 |

Agent와 Ansible Control Node는 **VM 2가 맡는 두 가지 역할**이다.

### 배포할 때의 흐름

```text
GitHub의 코드
     ↓
Jenkins Controller가 작업 배정
     ↓
Jenkins Agent가 빌드·테스트
     ↓
같은 Agent에서 Ansible 실행
     ↓ SSH
App Server 1·2·3에 이미지 전달 및 컨테이너 실행
```

### 사용자가 접속할 때의 흐름

```text
사용자
  ↓ http://1.201.116.156:18007/version
Nginx Load Balancer
  ↓ 앱 서버 중 하나 선택
App Server의 20007번 포트
  ↓ Docker 포트 연결
앱 컨테이너의 80번 포트
  ↓
v15 등의 응답
```

사용자의 일반 웹 요청은 Jenkins를 거치지 않는다. Jenkins가 멈춰도 이미 실행 중인 앱 컨테이너가 그 이유만으로 멈추지는 않는다.

### 포트 세 개의 차이

| 포트 | 위치 | 의미 |
| --- | --- | --- |
| `18007` | 공용 Load Balancer | 사용자가 들어오는 내 서비스 입구 |
| `20007` | 각 App Server | 호스트에서 내 컨테이너로 연결하는 포트 |
| `80` | 각 앱 컨테이너 내부 | 앱이 실제로 요청을 받는 포트 |

```bash
docker run -p 20007:80 ...
#             호스트:컨테이너
```

서버 3대는 IP가 다르므로 모두 `20007`을 사용할 수 있다. 같은 서버의 컨테이너들도 내부 네트워크가 분리된 일반적인 실행 방식에서는 각각 내부 포트 `80`을 사용할 수 있다.

할당된 추가 포트 `21007`은 설명 당시 코드에서 사용하지 않는다.

## 3. 앱과 Docker

### 앱은 무엇인가

파일: [app/default.conf.template](../app/default.conf.template)

앱은 **Nginx가 정해진 문자열을 반환하는 HTTP 서버**다. Spring이나 Python으로 작성한 별도 프로그램은 없다.

| 경로 | 응답 | 목적 |
| --- | --- | --- |
| `/` | `Sohyeon Jenkins + Ansible CI/CD` | 기본 접속 확인 |
| `/health` | `OK` | HTTP 응답 가능 여부 확인 |
| `/version` | `v15` 등 | 배포 버전 표시 확인 |

```nginx
location = /health {
    default_type text/plain;
    return 200 "OK\n";
}
```

읽는 방법:

- `location = /health`: 경로가 정확히 `/health`인 요청에 적용한다.
- `default_type text/plain`: 응답은 일반 텍스트다.
- `return 200`: HTTP 성공 코드로 응답한다.
- `"OK\n"`: 본문은 `OK`와 줄바꿈이다.

**Nginx가 두 역할로 등장한다.** VM 3에서는 요청을 전달하고, 앱 컨테이너에서는 응답을 직접 만든다.

### Dockerfile은 이미지 제작 설명서

파일: [Dockerfile](../Dockerfile)

```dockerfile
FROM nginx:alpine
COPY app/default.conf.template /etc/nginx/templates/default.conf.template
EXPOSE 80
```

| 코드 | 의미 |
| --- | --- |
| `FROM` | Nginx가 들어 있는 기존 이미지에서 시작 |
| `COPY` | 내 앱 설정을 이미지 안에 포함 |
| `EXPOSE 80` | 컨테이너가 사용하는 포트 정보 선언 |

`EXPOSE`만으로 외부 접속 포트가 열리지는 않는다. 실제 연결은 `docker run -p`가 담당한다.

| 개념 | 의미 | 예시 |
| --- | --- | --- |
| Dockerfile | 이미지를 만드는 방법 | 위의 세 줄 |
| 이미지 | 앱 실행에 필요한 파일을 묶은 원본 | `sohyeon-cicd-app:15` |
| 컨테이너 | 이미지로 만든 실행 인스턴스 | 각 서버의 `sohyeon-cicd-app` |

이 프로젝트는 **이미지를 한 번 만들고 같은 이미지를 서버 3대에서 실행**한다.

### 버전 값이 만들어지는 과정

이 문서에서는 Jenkins 빌드 번호가 `15`라고 가정한다.

```text
BUILD_NUMBER=15
    ├─ 이미지 이름과 태그: sohyeon-cicd-app:15
    └─ 실행 환경변수: APP_VERSION=v15
                         ↓
        앱 템플릿의 ${APP_VERSION}을 v15로 치환
                         ↓
                  /version → v15
```

공식 Nginx 이미지의 시작 스크립트가 `/etc/nginx/templates/`의 템플릿을 처리한다. 자세한 동작은 [공식 이미지 스크립트](https://github.com/nginx/docker-nginx/blob/master/entrypoint/20-envsubst-on-templates.sh)를 참고한다.

이미지 태그와 환경변수는 별개다. 파이프라인이 같은 빌드 번호를 사용해 둘을 맞춘다. `/version`이 이미지의 내용을 분석하는 것은 아니다.

## 4. Jenkins 실행 과정

파일: [Jenkinsfile](../Jenkinsfile)

### 기본 구조

```groovy
pipeline {
    agent { label 'ansible-agent' }
    stages {
        stage('Build') {
            steps {
                sh '실행할 셸 명령'
            }
        }
    }
}
```

| 문법 | 의미 |
| --- | --- |
| `agent` | 작업을 실행할 Jenkins 노드 선택 |
| `stage` | Build, Test 등의 작업 단계 |
| `steps` | 단계 안의 실행 작업 |
| `sh` | Agent에서 셸 명령 실행 |
| `environment` | 사용할 환경변수 |
| `parameters` | 실행할 때 사용자가 선택할 값 |
| `post` | 단계 실행 후 처리 |

`ansible-agent`는 노드 라벨이다. 실제로 VM 2에 연결되어 있는지는 Jenkins 설정에서 확인한다.

**Workspace**는 해당 Job이 코드를 받고 작업하는 디렉터리다. `${WORKSPACE}`는 그 경로를 나타낸다.

설명 당시 Jenkinsfile에는 명시적인 checkout 단계가 없다. Job을 `Pipeline from SCM` 등으로 구성하면 Declarative Pipeline의 기본 checkout 동작을 이용할 수 있다. 저장소 URL과 브랜치는 실제 Job 설정에서 확인한다. [Jenkins 공식 문서](https://www.jenkins.io/doc/book/pipeline/syntax/)

### 단계별 역할

| 순서 | 단계 | 핵심 작업 |
| --- | --- | --- |
| 1 | Check Environment | 실행 계정, Docker 권한, 도구 설치 여부 확인 |
| 2 | Build | 앱 이미지 생성 |
| 3 | Test | 임시 컨테이너에서 응답 검사 |
| 4 | Prepare Artifact | 이미지를 tar 파일로 저장 |
| 5 | Prepare SSH | 서버 호스트 키 수집 |
| 6 | Deploy | Ansible로 앱 서버 3대에 배포 |
| 7 | Configure Nginx | 선택한 경우 LB 설정 배포 |
| 8 | Verify | LB를 통한 응답 확인 |

### Check Environment: 실행 환경 확인

`hostname`, `whoami`, `pwd`는 어느 서버에서 어떤 계정으로 어느 디렉터리에서 실행 중인지 보여준다. `docker --version`, `ansible --version` 등은 필요한 프로그램의 설치 여부를 확인한다. 프로그램을 설치하는 단계는 아니다.

### Build: 실행할 이미지 만들기

변수를 실제 값으로 풀면 다음 명령이다.

```bash
docker build -t sohyeon-cicd-app:15 .
```

- `-t`: 이미지 이름과 태그 지정
- `.`: 현재 디렉터리를 빌드 컨텍스트로 사용

여기서 빌드는 소스 컴파일이 아니라 Nginx와 앱 설정을 이미지로 묶는 작업이다.

코드의 `sg docker -c "..."`는 Docker 명령을 `docker` 그룹으로 실행하려는 구문이다. 계정에 해당 그룹을 사용할 권한이 있어야 한다. 권한을 새로 부여하는 명령은 아니다.

### Test: 배포 전에 이미지 실행해 보기

```bash
docker run -d \
  --name sohyeon-cicd-test \
  -e APP_VERSION=v15 \
  sohyeon-cicd-app:15
```

| 옵션 | 의미 |
| --- | --- |
| `-d` | 백그라운드 실행 |
| `--name` | 컨테이너 이름 지정 |
| `-e` | 컨테이너 환경변수 전달 |

그다음 컨테이너 내부에서 HTTP 요청을 보낸다.

```bash
docker exec sohyeon-cicd-test wget -qO- http://127.0.0.1/health
```

`docker exec`는 실행 중인 컨테이너 안에서 명령을 실행한다. 따라서 이 주소의 `127.0.0.1`은 테스트 컨테이너 자신이다. 테스트용 호스트 포트를 공개할 필요가 없다.

`/health`가 `OK`, `/version`이 `v15`인지 검사한다. 검사에 실패하면 이후 배포 단계로 진행하지 않는다.

### Prepare Artifact: 이미지를 파일로 만들기

```groovy
stage('Prepare Artifact') {
    steps {
        sh '''
            mkdir -p .artifacts

            sg docker -c \
            "docker save \
            -o .artifacts/${IMAGE_NAME}.tar \
            ${IMAGE_NAME}:${BUILD_NUMBER}"
        '''
    }
}
```

**Artifact는 빌드 결과로 만들어진 배포용 산출물**이다. 이 프로젝트에서는 Docker 이미지가 담긴 `.tar` 파일이다.

| 명령 | 의미 |
| --- | --- |
| `mkdir -p .artifacts` | Workspace에 디렉터리 생성. 이미 있어도 오류 없이 진행 |
| `sg docker -c "..."` | 따옴표 안 명령을 docker 그룹으로 실행 |
| `docker save` | Docker 이미지를 파일로 저장 |
| `-o 경로` | 저장할 파일 지정 |
| `${IMAGE_NAME}:${BUILD_NUMBER}` | 저장할 이미지 지정 |

줄 끝의 `\`는 긴 명령을 다음 줄로 이어 쓰기 위한 표시다.

변수를 풀어 쓰면 다음과 같다.

```bash
docker save -o .artifacts/sohyeon-cicd-app.tar sohyeon-cicd-app:15
```

Agent에 만든 이미지는 앱 서버에 자동으로 생기지 않는다. 그래서 파일로 저장해 전달한다.

```text
Agent의 이미지 → docker save → tar 파일
→ Ansible로 서버에 복사 → docker load → 앱 서버의 이미지
```

이 방식은 이미지 파일을 직접 전달한다. 컨테이너 레지스트리에 push/pull하는 코드는 없다.

### 실행 옵션과 정리

- `CONFIGURE_NGINX`: LB 설정을 배포할 때만 켜는 옵션. 기본값은 `false`다.
- `disableConcurrentBuilds()`: 같은 Job이 동시에 여러 번 실행되는 것을 막는다.
- `timestamps()`: 콘솔 로그에 시간을 표시한다.
- `post → always`: 성공·실패 여부와 관계없이 테스트 컨테이너와 Workspace의 `.artifacts`, `.ssh`를 정리한다.

앱 서버에 배포한 컨테이너는 정리 대상이 아니다. 이전 Docker 이미지까지 지우는 작업도 없다.

## 5. SSH 인증

Ansible은 Agent에서 SSH로 앱 서버와 LB에 접속한다.

### Jenkins Credentials에서 인증 정보 가져오기

```groovy
withCredentials([
    sshUserPrivateKey(
        credentialsId: 'sohyeon-deploy-ssh',
        keyFileVariable: 'SSH_KEY',
        usernameVariable: 'SSH_USER'
    )
]) {
    // 여기에서 인증 정보를 사용한다.
}
```

| 설정 | 의미 |
| --- | --- |
| `credentialsId` | Jenkins에 저장해 둔 인증 정보의 ID |
| `keyFileVariable: 'SSH_KEY'` | 개인 키가 담긴 임시 파일 경로를 제공할 변수 |
| `usernameVariable: 'SSH_USER'` | 접속 계정명을 제공할 변수 |

**SSH_KEY는 개인 키 내용 자체가 아니라 파일 경로다.** `withCredentials`는 감싼 블록 안에서 인증 정보를 사용할 수 있도록 제공한다.

### Ansible이 읽을 환경변수에 연결하기

```bash
export ANSIBLE_PRIVATE_KEY_FILE="${SSH_KEY}"
export ANSIBLE_REMOTE_USER="${SSH_USER}"
export ANSIBLE_SSH_ARGS="-o UserKnownHostsFile=${WORKSPACE}/.ssh/known_hosts -o StrictHostKeyChecking=yes"
```

`export`는 뒤에 실행할 프로그램이 환경변수를 전달받도록 한다. 여기서는 `ansible-playbook`이 접속 정보를 읽는다.

| 변수·옵션 | 의미 |
| --- | --- |
| `ANSIBLE_PRIVATE_KEY_FILE` | 접속에 사용할 개인 키 파일 |
| `ANSIBLE_REMOTE_USER` | 원격 서버 접속 계정 |
| `UserKnownHostsFile` | 서버 호스트 키를 확인할 파일 |
| `StrictHostKeyChecking=yes` | 등록되지 않았거나 키가 일치하지 않는 서버 연결 거부 |

### 개인 키와 known_hosts의 차이

| 항목 | 확인하는 대상 |
| --- | --- |
| SSH 개인 키 | 접속하는 사용자의 신원 |
| `known_hosts` | 접속받는 서버의 호스트 키 |

`Prepare SSH` 단계가 `ssh-keyscan`으로 키를 수집해 Workspace의 `.ssh/known_hosts`에 기록한다. 매번 수집한 값을 신뢰하므로, 사전에 확인한 서버 키와 대조하는 방식과는 다르다.

Ansible의 `become: true`는 해당 작업에 권한 상승을 요청한다. SSH 로그인 권한과 관리자 작업 권한은 별개이며, 서버에 필요한 권한 설정이 있어야 한다.

## 6. Ansible 배포와 변수 전달

### 파일을 나눈 이유

| 파일 | 답하는 질문 |
| --- | --- |
| [inventory.ini](../ansible/inventory.ini) | 어느 서버에 실행할까? |
| [deploy.yml](../ansible/deploy.yml) | 어느 그룹에 어떤 Role을 적용할까? |
| [app/defaults/main.yml](../ansible/roles/app/defaults/main.yml) | 기본 이름과 포트는 무엇인가? |
| [app/tasks/main.yml](../ansible/roles/app/tasks/main.yml) | 배포할 때 실제로 무슨 일을 할까? |

**Inventory**는 서버 목록, **Playbook**은 작업 지시서, **Role**은 관련 작업·변수 등을 모아 둔 묶음이다.

### Inventory 읽기

```ini
[app_servers]
sohyeon-app1 ansible_host=1.201.118.202
sohyeon-app2 ansible_host=1.201.118.10
sohyeon-app3 ansible_host=1.201.118.90
```

- `app_servers`: 서버 그룹 이름
- `sohyeon-app1`: Ansible에서 사용하는 서버 별명
- `ansible_host`: 실제 접속 주소

### Playbook 읽기

```yaml
- name: Deploy Sohyeon CI/CD application
  hosts: app_servers
  gather_facts: false
  roles:
    - role: app
```

“앱 서버 그룹에 app Role을 실행한다”라는 뜻이다. `gather_facts: false`는 시작 전 시스템 정보 수집을 생략한다.

### Deploy 단계가 실행하는 명령

```bash
ansible-playbook \
  -i ansible/inventory.ini \
  ansible/deploy.yml \
  --limit app_servers \
  -e "image_name=${IMAGE_NAME}" \
  -e "image_tag=${BUILD_NUMBER}" \
  -e "image_tar=${WORKSPACE}/.artifacts/${IMAGE_NAME}.tar"
```

| 부분 | 의미 |
| --- | --- |
| `ansible-playbook` | Playbook 실행 |
| `-i` | 서버 목록 파일 지정 |
| `ansible/deploy.yml` | 실행할 작업 지시서 |
| `--limit` | 실행 대상 추가 제한 |
| `-e` | 이번 실행에 적용할 Ansible 변수 전달 |

### 오른쪽 변수는 어디서 오는가

| 변수 | 제공하는 곳 | 예시 |
| --- | --- | --- |
| `${IMAGE_NAME}` | Jenkinsfile의 `environment`에 직접 지정 | `sohyeon-cicd-app` |
| `${BUILD_NUMBER}` | Jenkins가 빌드마다 자동 제공 | `15` |
| `${WORKSPACE}` | Jenkins가 해당 Job의 작업 경로 제공 | `/…/workspace/내-Job` |

```groovy
environment {
    IMAGE_NAME = 'sohyeon-cicd-app'
    TEST_CONTAINER = 'sohyeon-cicd-test'
}
```

### 왼쪽 변수는 Ansible에서 어떻게 받는가

```bash
-e "image_tag=${BUILD_NUMBER}"
```

셸이 Jenkins 환경변수 값을 넣으면 다음처럼 된다.

```bash
-e "image_tag=15"
```

Ansible은 이를 변수로 등록한다. 별도로 받는 함수를 만들 필요가 없다. 작업 파일에서는 `{{ image_tag }}`로 사용한다.

```text
Jenkins 환경변수          명령줄 전달                  Ansible에서 사용

IMAGE_NAME          →  -e "image_name=..."       →  {{ image_name }}
BUILD_NUMBER        →  -e "image_tag=..."        →  {{ image_tag }}
WORKSPACE 등으로 경로 →  -e "image_tar=..."        →  {{ image_tar }}
```

실제 사용 예:

```yaml
- name: Copy Sohyeon Docker image
  ansible.builtin.copy:
    src: "{{ image_tar }}"
    dest: "/tmp/{{ app_name }}-{{ image_tag }}.tar"
```

`image_tar`는 **Agent에 있는 파일 경로**다. Ansible이 이 파일을 읽어 앱 서버들로 복사한다.

`app_name`처럼 `-e`로 넘기지 않은 값은 Role의 기본 변수 등을 사용한다. 기본 변수에 `image_tag: latest`가 있어도 `-e "image_tag=15"`로 넘기면 이번 실행에서는 `15`가 우선한다.

### 실제 배포 작업의 연결

```text
Jenkins의 Deploy 단계
        ↓
ansible/deploy.yml
        ↓
ansible/roles/app/tasks/main.yml
        ↓
앱 서버 3대 각각에서 작업 수행
```

Jenkins는 접속 정보와 배포 값을 준비해 Ansible을 실행한다. 서버에서 실제 컨테이너를 교체하는 작업은 Ansible이 담당한다.

### 서버마다 수행하는 배포 순서

```text
필수 변수 검사
  ↓
이미지 tar 파일 복사
  ↓
docker load로 이미지 등록
  ↓
기존 sohyeon-cicd-app 컨테이너 조회
  ↓
기존 컨테이너가 있으면 제거
  ↓
새 컨테이너 실행
  ↓
/health 및 /version 확인
  ↓
임시 tar 파일 삭제
```

변수를 풀어 쓴 컨테이너 실행 명령:

```bash
docker run -d \
  --name sohyeon-cicd-app \
  --restart unless-stopped \
  -e APP_VERSION=v15 \
  -p 20007:80 \
  sohyeon-cicd-app:15
```

`--restart unless-stopped`는 컨테이너 재시작 정책이다. `/health` 실패를 감지해서 이전 버전으로 돌리는 기능은 아니다.

### 자주 나오는 문법

| 문법 | 의미 |
| --- | --- |
| `{{ image_tag }}` | Ansible 변수 값 삽입 |
| `register: result` | 작업 결과를 변수에 저장 |
| `when: 조건` | 조건을 만족할 때 실행 |
| `changed_when: false` | 결과를 변경 발생으로 표시하지 않음 |
| `until` + `retries` + `delay` | 조건을 만족할 때까지 정해진 횟수와 간격으로 재시도 |
| `assert` | 조건이 틀리면 실패 처리 |
| `content \| trim` | 응답 앞뒤 공백과 줄바꿈 제거 |
| `'v' ~ image_tag` | 문자열을 연결해 `v15` 같은 값 생성 |

## 7. Nginx 로드밸런서

파일: [sohyeon.conf.j2](../ansible/roles/nginx_lb/templates/sohyeon.conf.j2)

핵심 설정은 다음과 같다.

```nginx
upstream sohyeon_backend {
    server 1.201.118.202:20007;
    server 1.201.118.10:20007;
    server 1.201.118.90:20007;
}

server {
    listen 18007;
    location / {
        proxy_pass http://sohyeon_backend;
    }
}
```

| 항목 | 의미 |
| --- | --- |
| `upstream` | 요청을 보낼 앱 서버 묶음 |
| `listen 18007` | 내 서비스 포트로 요청 수신 |
| `proxy_pass` | 요청을 선택된 앱 서버로 전달 |

원본의 `proxy_set_header` 설정은 호스트, 클라이언트 IP, 접속 프로토콜 등의 정보를 백엔드에 전달한다.

### 설정 배포 과정

```text
nginx.yml에서 nginx_lb Role 실행
  ↓
/etc/nginx/conf.d/sohyeon.conf에 개인 설정 배포
  ↓
nginx -t로 문법 검사
  ↓
설정이 변경되었고 검사가 성공하면 Handler로 Reload
```

`notify`는 변경이 있을 때 후속 작업인 Handler를 예약한다. 해당 Handler는 Nginx Reload를 수행한다.

앱 버전만 바뀌고 IP와 포트가 같으면 LB 설정을 매번 바꿀 필요가 없다. 그래서 `CONFIGURE_NGINX`를 선택할 때만 실행한다.

## 8. 검증과 장애 확인

### 검증은 세 군데에서 한다

| 검증 | 요청 실행 위치 | 대상 | 확인 범위 |
| --- | --- | --- | --- |
| Jenkins Test | Agent의 테스트 컨테이너 안 | `127.0.0.1:80` | 이미지 실행과 응답 |
| 배포 후 검사 | 각 App Server | `127.0.0.1:20007` | 서버별 컨테이너와 포트 연결 |
| 최종 Verify | LB 서버 | `127.0.0.1:18007` | Nginx를 통한 백엔드 응답 |

**127.0.0.1은 명령이 실행되는 환경 자신이다.**

[verify.yml](../ansible/verify.yml)의 `hosts`는 `load_balancer`다. Agent에서 Ansible을 시작해도 해당 HTTP 검사 작업은 LB 서버에서 실행된다.

따라서 최종 Verify는 사용자 PC에서 Public IP로 접속하는 경로까지 검증하지 않는다. 또한 LB에 한 번 요청했다고 서버 3대를 모두 검사한 것은 아니다. 서버별 검사는 앱 배포 Role이 따로 수행한다.

`/health`는 고정 문자열을 반환한다. 데이터베이스 연결이나 복잡한 앱 기능까지 검사하는 것은 아니다.

### 어디서 실패했는지에 따라 조사 범위를 좁힌다

| 증상 | 우선 확인할 것 |
| --- | --- |
| Build 실패 | Dockerfile, 빌드 파일, Docker 사용 권한 |
| Test 실패 | 앱 설정, 컨테이너 상태, 기대 응답 |
| SSH 실패 | 접속 계정, 개인 키, 호스트 키, 네트워크 |
| 컨테이너 실행 실패 | 이미지 존재, 포트 충돌, Docker 권한 |
| 서버별 검사는 성공, LB 검사는 실패 | LB 설정 및 LB에서 앱 서버로의 통신 |
| LB 검사는 성공, 사용자 PC에서는 실패 | 외부 접근 경로와 방화벽·접근 정책 |

## 9. 구현 범위와 한계

다음은 이전 설명 당시 코드 기준이다.

| 항목 | 구현 상태 |
| --- | --- |
| 이미지 빌드·테스트 | 구현됨 |
| 동일 이미지의 서버 3대 배포 | 구현됨 |
| 서버별 health·version 검사 | 구현됨 |
| 개인 LB 설정과 경유 검사 | 구현됨 |
| 무중단 배포 | 보장하지 않음 |
| 실패 시 자동 롤백 | 구현되지 않음 |
| 사용자 전체의 Nginx 변경 잠금 | 저장소에서 확인되지 않음 |
| 이전 Docker 이미지 정리 | 구현되지 않음 |

### 왜 무중단 배포가 아닌가

배포 순서는 `기존 컨테이너 제거 → 새 컨테이너 실행`이다. 그 사이에는 해당 서버의 앱이 응답하지 못한다.

또한 `serial` 설정이 없어 한 서버의 배포를 끝낸 뒤 다음 서버를 교체하도록 구성되어 있지 않다. 기본 Ansible 전략에서는 여러 서버에 같은 작업을 수행한 뒤 다음 작업으로 진행한다. 세 서버의 기존 앱이 비슷한 시점에 내려갈 수 있다. [Ansible 공식 문서](https://docs.ansible.com/projects/ansible-core/2.17/playbook_guide/playbooks_strategies.html)

### 실패를 감지하는 것과 복구하는 것은 다르다

새 앱의 health 검사에 실패하면 배포 실패를 감지한다. 하지만 이전 컨테이너를 자동으로 되살리는 작업은 없다.

### 공용 서버 규칙과 관련된 부분

- 컨테이너 이름과 설정 파일에 `sohyeon`을 사용한다.
- 할당된 `18007`, `20007`을 사용한다.
- 앱 배포 대상을 `app_servers`로 제한한다.
- 개인 키는 Jenkins Credentials에서 제공받는다.
- `nginx -t`로 설정을 검사한다.
- `disableConcurrentBuilds()`는 같은 Job만 보호한다. 다른 사용자의 Nginx 변경과 동시 실행되는 것까지 막지 않는다. [Jenkins 공식 문서](https://www.jenkins.io/doc/book/pipeline/syntax/)

공통 시스템 패키지 설치, Docker 서비스 재시작, 서버 재부팅은 설명 당시 파이프라인에 포함되어 있지 않다.

## 10. 직접 만든다면 어떤 순서인가

처음부터 생각할 때는 Jenkinsfile보다 **실행 가능한 앱과 수동 작업 순서**가 먼저다.

| 순서 | 필요한 것 | 작성할 파일 |
| --- | --- | --- |
| 1 | 정상 응답하는 작은 앱 | `app/default.conf.template` |
| 2 | 앱을 같은 환경에서 실행할 이미지 | `Dockerfile` |
| 3 | 배포 대상 목록 | `ansible/inventory.ini` |
| 4 | 반복할 서버 배포 작업 | `roles/app/defaults/`, `roles/app/tasks/` |
| 5 | 대상 그룹과 배포 작업 연결 | `ansible/deploy.yml` |
| 6 | 사용자에게 제공할 단일 접속 주소 | `nginx_lb` Role, `ansible/nginx.yml` |
| 7 | 배포 후 경유 검사 | `ansible/verify.yml` |
| 8 | 전체 과정을 순서대로 자동 실행 | `Jenkinsfile` |

Jenkins 쪽에는 별도로 개인 Folder와 Job, GitHub 저장소 연결, Agent 라벨, SSH Credentials가 준비되어 있어야 한다.

소스 파일, 이미지, 컨테이너를 차례로 연결해서 설명하는 연습을 하면 좋다.

```text
앱 설정 변경
→ 새 이미지 빌드
→ 임시 컨테이너 테스트
→ 이미지 파일 전송
→ 서버의 컨테이너 교체
→ 실제 응답 확인
```

## 11. 이해도 확인

답을 가리고 먼저 자신의 말로 설명해 본다.

| 질문 | 핵심 답 |
| --- | --- |
| 왜 `docker save`와 `load`가 필요한가? | Agent의 이미지를 파일로 전달해 앱 서버에도 등록하려고 |
| `20007:80`에서 왼쪽과 오른쪽은? | 호스트 서버 포트와 컨테이너 내부 포트 |
| Jenkins와 Ansible은 어떻게 다른가? | Jenkins는 전체 실행 흐름, Ansible은 원격 서버 작업 담당 |
| Inventory와 Playbook은 어떻게 다른가? | 대상 서버 목록과 작업 지시서 |
| `-e "image_tag=${BUILD_NUMBER}"`는 무엇인가? | Jenkins 빌드 번호를 Ansible의 image_tag 변수로 전달 |
| `/version`의 값은 어디서 오는가? | 실행 환경변수 APP_VERSION이 앱 설정에 반영됨 |
| Test 단계는 왜 호스트 포트를 열지 않는가? | 컨테이너 안에서 직접 HTTP 요청을 보내므로 |
| 서버 3대가 있는데 왜 무중단이 아닌가? | 기존 앱을 먼저 제거하며 순차 교체가 구성되지 않았으므로 |
| Verify가 성공하면 외부 접속도 보장되는가? | 아니며, 해당 검사는 LB 서버 내부에서 실행됨 |

**설명 연습:** “빌드 번호 15를 실행했을 때 어떤 파일과 값이 어느 서버로 이동하는가?”를 코드 없이 말해 본다. 막히는 부분에 해당하는 절을 다시 읽는다.
