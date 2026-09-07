# Jenkins 개요

### Jenkins란?

> 소프트웨어의 빌드, 테스트, 제공 및 배포와 관련된 모든 종류의 작업(CI/CD)을 자동화 하는데 사용할 수 있는 **독립형 오픈 소스 자동화 서버**
> 

### Jenkins 특징

---

1. Pipeline as Code
    - 기존에는 GUI에서 Job을 생성해야 했다.
    - 현재는 코드로 빌드를 과정을 정의 할 수 있음
    - 프로젝트 루트에 `Jenkinsfile`
    
    ```groovy
    pipeline {
        agent any
    
        stages {
            stage('Build') {
                steps {
                    sh './mvnw clean package'
                }
            }
    
            stage('Test') {
                steps {
                    sh './mvnw test'
                }
            }
    
            stage('Deploy') {
                steps {
                    sh './deploy.sh'
                }
            }
        }
    }
    ```
    
2. 플러그인
- 기본으로 빌드, 테스트 배포 기능만 포함하고 있다.
- 이후 기능들은 플러그인을 통해 확장할 수 있다.
- 필요한 플로그인 을 조합하여 기능을 확장하는 구조이다.

```
Jenkins

├── Git Plugin
├── GitLab Plugin
├── Docker Plugin
├── Pipeline Plugin
├── Credentials Plugin
├── JCasC Plugin
├── Kubernetes Plugin
└── Slack Plugin
```

1. Controller-Agent 구조
- Jenkins는 Controller와 Agent를 기반으로 분산 실행 구조를 구성할 수 있다.
- Controller는 Jenkins 전체를 관리하고 작업을 스케줄링한다.
- Agent는 Controller로부터 할당받은 실제 Build, Test, Deploy 작업을 수행한다.
- 여러 Agent를 구성하여 작업을 병렬로 실행하거나, 서로 다른 빌드 환경을 분리할 수 있다.
- Controller에서도 작업 실행은 가능하지만, 일반적으로 실제 빌드는 별도의 Agent에서 수행하도록 구성한다.

전체적인 흐름

```
           Jenkins Controller

         ┌────────────────────┐
         │ Job 관리            │
         │ Pipeline 관리       │
         │ Queue 관리          │
         │ Agent 관리          │
         │ Credential 관리     │
         │ 사용자/권한 관리       │
         └─────────┬──────────┘
                   │
                   │ 작업 할당
                   │
     ┌─────────────┼─────────────┐
     ▼             ▼             ▼

Jenkins Agent  Jenkins Agent  Jenkins Agent

Java / Maven    Docker       Node.js
Executor        Executor     Executor

     │             │             │
     ▼             ▼             ▼
   Build          Deploy        Test
```

- Controller
    - Jenkins 전체를 관리하는 중앙 서버
    - Job / Pipeline 관리
    - Build Queue 관리
    - Agent 관리 및 작업 스케줄링
    - Credentials, Plugin, 사용자 및 권한 관리
- Agent
    - Controller로부터 할당받은 작업을 실제로 수행하는 실행 주체
    - Build, Test, Deploy 등의 명령을 실행
1. Jenkins 알람
- 알람 형태로 제공해 빠른 피드백 및 문제 해결 가능

```
다양한 채널
- 이메일(Email) : 기본적인 알람 방식(SMTP 설정 필요)
- 메신저 연동 : Slack, Discord, Teams, Telegram 등 실시간 협업 도구와 통합
- Webhook : 외부 시스템(API 서버, 챗봇, 모니터링 시스템 등)과 연동
- 이슈 트래커 : Jira, Githup 등 빌드 실패 시 자동으로 티켓 생성
- 대시보드(Grafana, Prometheus 등)와 연동해 빌드 상태 시각화

알람 트리거(Trigger) 제공
- 성공(Success) : 모든 단계가 정상 완료되었을 때
- 실패(Failure) : 빌드 또는 테스트가 실패했을 때
- 불안정(Unstable) : 일부 테스트 실패 등 경고 상황
- 연속 실패(Repeated Failure) : 같은 Job이 연속해서 실패할 때
- 배포 완료(Deployment Completed) : 프로덕션에 성공적으로 배포되었을 때
```

### Jenkins 구성

---

전체 구성

```
Jenkins

├── Controller
│    ├── Job / Pipeline
│    ├── Build Queue
│    ├── Credentials
│    ├── Plugins
│    └── Agent Management
│
└── Node
     └── Agent
          ├── Executor
          └── Workspace
```

#### 용어 정리

- **Controller**
    - Jenkins 서비스가 실행되는 중심 서버이다.
    - Web UI / API 요청을 처리하고 Job / Pipeline 설정을 관리한다.
    - Build Queue를 관리하고 어떤 Node / Agent에서 작업을 실행할지 Scheduling한다.
    - Agent 상태, Credentials, Plugins, 사용자 및 권한 등 Jenkins 전역 설정을 관리한다.
    - 운영 환경에서는 실제 Build 실행보다 관리와 조정 역할에 집중하도록 구성하는 것이 권장된다.
- **Node**
    - Jenkins가 작업 실행 대상으로 인식하는 머신 또는 실행 환경이다.
    - 물리 서버, VM, EC2, Container, Kubernetes Pod 등이 Node가 될 수 있다.
    - Controller 내부에도 `Built-in Node`가 존재한다.
    - Node가 Offline 상태이면 Controller는 해당 Node에 새로운 작업을 할당하지 않는다.
- **Agent**
    - Node에서 실행되며 Controller와 통신하는 Jenkins 실행 프로세스이다.
    - Controller의 요청을 받아 Build, Test, Deploy 등 실제 작업을 수행한다.
    - 기본적으로 Java와 Controller에 연결 가능한 네트워크 경로가 필요하다.
    - 개념적으로 `Node = 실행 환경`, `Agent = 그 환경에서 동작하며 Jenkins 작업을 수행하는 프로세스`로 구분한다.
- **Executor**
    - Node에서 동시에 실행할 수 있는 Jenkins 작업 슬롯이다.
    - Executor가 2개이면 해당 Node에서 최대 2개의 작업을 동시에 실행할 수 있다.
    - 모든 Executor가 사용 중이면 추가 작업은 Build Queue에서 대기한다.
    - CPU, Memory, Disk I/O, Network I/O, 빌드 특성을 고려해 수를 정해야 한다.
- **Workspace**
    - Agent가 Job을 실행할 때 사용하는 실제 작업 디렉터리이다.
    - SCM에서 Checkout한 소스 코드와 Build 결과물이 위치한다.
    - 예: `src/`, `pom.xml`, `Jenkinsfile`, `target/`
- **Label**
    - Node / Agent의 실행 환경 특성을 표현하는 식별자이다.
    - 예: `linux`, `windows`, `docker`, `java17`, `high-memory`
    - Job / Pipeline은 Label Expression을 이용해 특정 조건을 만족하는 Agent에서만 실행되도록 제한할 수 있다.
- **Job**
    - Jenkins에 등록해 놓은 하나의 자동화 작업 단위이다.
    - 무엇을 실행할지에 대한 작업 정의라고 볼 수 있다.
- **Pipeline**
    - Build, Test, Deploy 등의 여러 작업을 순서와 조건을 가지고 연결한 자동화 흐름이다.
    - 일반적으로 프로젝트 루트의 `Jenkinsfile`로 정의한다.
    - 예: `Checkout → Build → Test → Docker Build → Deploy`
- **Stage**
    - Pipeline을 구성하는 큰 작업 단계이다.
    - 의미적으로 연관된 Step들을 하나의 구간으로 묶는다.
    
    ```
    Pipeline
    
    ├─ Checkout Stage
    ├─ Build Stage
    ├─ Test Stage
    └─ Deploy Stage
    ```
    
- **Step**
    - Stage 안에서 실제로 수행되는 세부 작업 또는 명령이다.
    - 예: `sh './mvnw test'`, `checkout scm`
- **Build**
    - Job 또는 Pipeline이 한 번 실행된 실행 단위이다.
    - 각 Build에는 성공 / 실패 상태, 실행 로그, 실행 시간 등의 결과가 기록된다.
    - 예: `Build #101`, `Build #102`
- **Build Queue**
    - 실행 요청은 들어왔지만 아직 사용할 수 있는 Executor가 없어 대기 중인 작업 목록이다.
- **Credentials**
    - Jenkins가 외부 시스템에 접근할 때 사용하는 인증 정보이다.
    - Pipeline 코드에 비밀값을 직접 작성하지 않고 Credentials Store에 저장한 뒤 Credential ID로 참조한다.
    
    ```
    예:
    
    GitLab Token
    GitHub Token
    AWS Access Key
    SSH Private Key
    Docker Registry ID/PW
    API Token
    ```
    
- **Plugins**
    - Jenkins Core에 기능을 추가하는 확장 모듈이다.
    - Git / GitLab, Docker, Kubernetes, Slack, JCasC 등 다양한 기능을 Plugin으로 확장할 수 있다.