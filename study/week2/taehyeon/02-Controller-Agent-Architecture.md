# Controller / Agent Architecture

## 핵심 개념

---

- Jenkins는 분산 실행 환경을 구성하기 위해 **Controller와 Agent 구조**를 사용한다.
- Controller는 Jenkins의 중심 서버로서 다음 역할을 담당한다.
    - Web UI / API 처리
    - Job / Pipeline 설정 관리
    - Authentication / Authorization
    - Build Queue 관리
    - 작업 스케줄링
    - Agent 연결 상태 및 Health Monitoring
    - Credentials / Plugin / Global 설정 관리
- Agent는 Controller의 요청을 받아 실제 작업을 수행한다.
    - Checkout
    - Build
    - Test
    - Package
    - Docker Build
    - Deploy
- Controller 자체에도 Built-in Node가 존재해 작업 실행이 가능하지만, 운영 환경에서는 실제 Build를 별도 Agent로 분리하는 구성이 권장된다.
- Controller와 Agent를 분리하는 주요 이유는 다음과 같다.
    - Controller 안정성 확보
    - Build 리소스 격리
    - 보안 영역 분리
    - 프로젝트별 실행 환경 분리
    - 병렬 처리 및 확장성 확보

## 전체 구조

---

```
                    Jenkins Controller
                 ┌──────────────────────┐
Developer ──────▶│ Web UI / API         │
Git Webhook ────▶│ Job / Pipeline       │
                 │ Build Queue          │
                 │ Scheduler            │
                 │ Credentials          │
                 │ Agent Monitoring     │
                 └──────────┬───────────┘
                            │
                     Jenkins Remoting
                   ┌────────┼────────┐
                   │        │        │
                   ▼        ▼        ▼

              Agent A    Agent B    Agent C
              Java 21    Java 17    Docker
              Maven      Gradle     kubectl
                │
             Executor
                │
                ▼
          Checkout / Build
          Test / Package
          Deploy
```

## Controller / Agent 운영 원칙

---

### Controller

주요 역할

- Web UI / API
- Job / Pipeline 설정
- BuildQueue 관리
- Agent 선택 및 작업 스케줄링
- Authentication / Authorization
- Credentials
- Plugin / Global Configuration
- Agent 상태 Monitoring

### Controller Agent는 어떻게 통신하는가?

- Remoting은 Controller와 Agent간의 통신계층
    - RPC
    - 명령 실행
    - 데이터 전송
    - 클래스 로딩
    - 파일 처리
- 연결이 된 이후에는 양방향 통신
- 연결 방식
    - SSH Agent
    - Inbound Agent

### SSH Agent

- SSH Connector
- 연결 방향 : `Controller → Agent`
- agent 서버에 접속하기 위한 SSH Credential 필요
- 연결 과정
    
    ```
    1. Build 발생
    
    2. Controller
          ↓
       Agent가 필요한지 확인
    
    3. Controller
          ↓ SSH
       Agent 서버 접속
    
    4. Agent 서버
          ↓
       Jenkins Agent Process 실행
    
    5. Controller ↔ Agent
          Jenkins Remoting 연결
    
    6. Build 실행
    
    7. 결과 전달
    ```
    

### Inbound Agent

- 연결방향 : `Agent → Controller`
- 필요한 경우
    - Agent가 NAT / 방화벽 뒤에 있는 경우
    - Agent 서버에 SSH 포트를 열고 싶지 않은 경우
    - Docker / Kubernetes처럼 Agent가 동적으로 생성되는 경우
- 통신 방식
    - TCP
        - TCP Listener Port를 열어서 사용
        - Remoting 프로토콜 관점에서는 보통 `JNLP4-connect` 사용
    - WebSocket
        - **HTTP/HTTPS 포트**를 이용해서 Remoting 통신
    
    ```
    TCP 방식
    
    Agent ───── TCP :50000 ─────→ Controller
    
    WebSocket 방식
    
    Agent ───── HTTPS :443 ─────→ Nginx / LB ─────→ Controller
    ```
    

### 연결 방식 비교

| 구분 | SSH Connector | Inbound Agent |
| --- | --- | --- |
| 연결 시작 | Controller → Agent | Agent → Controller |
| SSH Server | 필요 | 불필요 |
| Agent 시작 | Controller가 SSH로 실행 | Agent 측에서 직접 실행 |
| 네트워크 조건 | Controller가 Agent에 접근 가능해야 함 | Agent가 Controller에 접근 가능하면 됨 |
| 대표 환경 | 내부 Linux VM, 고정 EC2 | NAT/Firewall 내부 Worker, Container |

## Controller 보안 및 격리

---

### Controller Isolation

- Jenkins Controller에는 기본적으로 Built-in Node가 존재한다.
    - Built-in Node : Controller 자신을 하나의 실행 노드로 취급
- Built-in Node에서도 기술적으로 Build를 실행할 수 있다.
- 운영 환경에서는 Built-in Node의 Executor를 `0`으로 설정
- 주요 이유는 다음과 같다.
    - 무거운 Build가 Controller CPU / Memory를 점유하는 문제 방지
    - Build I/O와 Jenkins 자체 I/O의 경합 방지
    - Jenkins UI / Queue / Scheduling 기능의 안정성 확보
    - Build Script가 Controller 파일 시스템에 접근할 위험 감소
    - 프로젝트별 Toolchain을 Controller에 모두 설치해야 하는 문제 방지

### Agent to Controller Access Control

> Agent에서 실행되는 코드가 Remoting을 통해 controller의 파일을 읽거나, 임의의 명령을 실행하는 것을 제한하는 보안 기능
> 
- Built-in Node를 사용하지 않는 것만으로 Controller 보안이 완전히 해결되는 것은 아니다.
- Agent는 작업 수행 과정에서 Controller에 특정 정보나 작업을 요청할 수 있다.
- Jenkins는 Agent에서 Controller로 허용되지 않은 호출을 제한하기 위해 **Agent to Controller Access Control**을 제공한다.
- 주요 목적은 다음과 같다.
    - Agent에서 Controller로 허용되지 않은 호출 제한
    - Controller 내부 데이터 및 기능 보호
    - 신뢰 수준이 낮은 Agent와 Controller 사이의 권한 경계 유지

## Agent 유형과 Dynamic Provisioning

---

### Built-in Node

- Controller 프로세스 내부에 존재하는 기본 Node이다.
- 테스트나 초기 학습 환경에서는 편리하다.
- 운영 환경에서는 보안, 안정성, 확장성 때문에 실제 Build 실행 용도로는 권장되지 않는다.
- Executor를 `0`으로 설정해 Build 실행을 차단할 수 있다.

### Static Agent

- 관리자가 미리 생성하고 Jenkins에 등록해 둔 고정 Agent이다.
- 물리 서버, VM, EC2, 고정 Container 등으로 구성할 수 있다.
- Job이 없어도 Agent 환경이 계속 존재한다.
- 특정 Tool, License, OS가 항상 필요한 환경에 적합하다.

### Dynamic Agent / Cloud Agent

- Job이 필요할 때 생성되고 작업이 끝나면 제거되는 Agent이다.
- Docker, Kubernetes, EC2, Azure, Google Cloud 등의 환경과 연동할 수 있다.
- 주요 장점
    - 깨끗한 일회성 Build 환경 제공
    - 빌드 수요에 따른 Agent 수 자동 확장
    - 유휴 리소스 감소
    - 프로젝트별 실행 환경 격리
- 기본 흐름

```
Job 발생
   ↓
적합한 Agent 없음
   ↓
Cloud / Docker / Kubernetes에 Agent 생성 요청
   ↓
Agent 생성 및 Controller 연결
   ↓
Build / Test / Deploy
   ↓
작업 완료 후 Agent 제거
```

## 운영 및 확장 기준

---

### Executor 구성

- Executor 수가 많을수록 동시에 많은 작업을 실행할 수 있지만 Node의 리소스 경합도 커진다.
- 가장 보수적인 구성은 Node당 Executor `1`개이다.
- 작업이 가볍고 독립적이라면 CPU Core 수 등을 참고해 Executor를 늘릴 수 있다.
- 여러 Executor를 사용할 때는 다음 지표를 함께 확인해야 한다.
    - CPU 사용률
    - Memory 사용량
    - Disk I/O
    - Network I/O
    - Build Queue 길이
    - 평균 Build 시간

### 확장 방식

- **Agent 확장**
    - 하나의 Controller가 더 많은 Build를 처리해야 할 때 Agent 수를 늘리는 방식이다.
    - Static Agent 추가 또는 Dynamic Agent Provisioning을 사용할 수 있다.
- **Controller 확장**
    - 팀, 프로젝트, 보안 경계, 장애 영향 범위를 분리해야 할 때 Controller 자체를 추가하는 방식이다.
    - 여러 Controller를 운영하면 Plugin, Jenkins Core, Backup, Security 설정을 각각 관리해야 한다.

## 전체 실행 흐름

---

```
Developer
   ↓ Git Push
GitLab / GitHub
   ↓ Webhook / Trigger
Jenkins Controller
   ↓ Job / Pipeline 확인
Build Queue
   ↓ Label / Node / Executor 선택
Jenkins Agent
   ↓ Workspace
Checkout
   ↓
Build
   ↓
Test
   ↓
Package / Docker Build
   ↓
Deploy
   ↓
Result 반환
   ↓
SUCCESS / FAILURE
```

## 핵심 관계

---

```
Controller
= 관리 / Scheduling / Queue / Agent Monitoring

Agent
= 실제 Build / Test / Deploy 실행

Node
= 작업 실행 환경

Executor
= 동시 실행 슬롯

Workspace
= Agent의 실제 작업 디렉터리

SSH
= Controller → Agent

Inbound
= Agent → Controller

Static Agent
= 미리 존재하는 고정 Agent

Dynamic Agent
= 필요할 때 생성하고 완료 후 제거

Docker Pipeline
= Build 환경을 Container화

Docker Dynamic Agent
= Agent 자체를 Container화
```

## 참고 자료

---

- [Jenkins 공식 문서 - Controller Isolation](https://www.jenkins.io/doc/book/security/controller-isolation/)
- [Jenkins 공식 문서 - Using Jenkins agents](https://www.jenkins.io/doc/book/using/using-agents/)
- [Jenkins 공식 문서 - Managing Nodes](https://www.jenkins.io/doc/book/managing/nodes/)
- [Jenkins 공식 문서 - Architecting for Scale](https://www.jenkins.io/doc/book/scaling/architecting-for-scale/)
- [Jenkins 공식 문서 - Jenkins Remoting](https://www.jenkins.io/projects/remoting/)
- [Jenkins 공식 문서 - Using Docker with Pipeline](https://www.jenkins.io/doc/book/pipeline/docker/)
- [Jenkins Plugin - Docker Plugin](https://plugins.jenkins.io/docker-plugin/)