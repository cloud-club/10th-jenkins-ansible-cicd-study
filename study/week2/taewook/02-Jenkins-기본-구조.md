## 1. Jenkins란?

Jenkins는 **빌드, 테스트, 배포 등의 작업을 자동화하기 위한 오픈소스 자동화 서버**이다.

개발자가 코드를 변경할 때마다 사람이 직접 빌드하고 테스트하는 대신 Jenkins를 이용하면 이러한 과정을 자동으로 실행할 수 있다.

대표적으로 다음과 같은 흐름을 구성할 수 있다.

```
Source Code
    ↓
Build
    ↓
Test
    ↓
Deploy
```

이처럼 애플리케이션의 빌드부터 배포까지의 과정을 자동화하여 **CI/CD Pipeline**을 구성하는 것이 Jenkins의 대표적인 사용 사례이다.

---

# 2. Jenkins 기본 구조

Jenkins는 크게 **Controller와 Agent** 구조로 동작한다.

```
              Jenkins Controller
        ┌─────────────────────────┐
        │ Job / Pipeline 관리     │
        │ Build Scheduling        │
        │ Agent 관리              │
        │ Web UI 제공             │
        └────────────┬────────────┘
                     │
             작업 할당 / 관리
                     │
          ┌──────────┴──────────┐
          │                     │
          ▼                     ▼
    Jenkins Agent          Jenkins Agent
    ┌────────────┐         ┌────────────┐
    │ Executor   │         │ Executor   │
    │ Workspace  │         │ Workspace  │
    │ Build/Test │         │ Build/Test │
    └────────────┘         └────────────┘
```

Controller가 전체 Jenkins 환경을 관리하고, 실제 빌드 작업은 Agent에 할당할 수 있다.

---

## 2.1 Controller

**Controller**는 Jenkins의 중앙 관리 역할을 수행하는 프로세스이다.

주요 역할은 다음과 같다.

- Jenkins Web UI 제공
- Jenkins 설정 및 Plugin 관리
- Job 및 Pipeline 관리
- Build 실행 요청 관리
- Build Queue 관리
- Agent 관리
- Agent에 작업 스케줄링

즉, Controller는 Jenkins 환경에서 **어떤 작업을 언제 어디에서 실행할지 관리하는 역할**을 담당한다.

과거 Jenkins에서는 Controller를 `Master`라고 부르기도 했지만 현재는 `Controller`라는 용어를 사용한다.

---

## 2.2 Agent

**Agent**는 Controller의 요청을 받아 실제 작업을 수행하는 실행 환경이다.

Agent는 물리 서버일 수도 있고, VM이나 Container일 수도 있다.

Agent에서는 다음과 같은 작업이 실행될 수 있다.

```
Source Code Checkout
        ↓
Build
        ↓
Test
        ↓
Package
        ↓
Deploy
```

예를 들어 다음과 같이 서로 다른 Agent를 구성할 수 있다.

```
Controller
   │
   ├── Linux Agent
   │     └── Linux Application Build
   │
   ├── Windows Agent
   │     └── Windows Application Build
   │
   └── Docker Agent
         └── Container Image Build
```

Agent에는 하나 이상의 **Executor**가 존재하며, Executor가 실제 Jenkins 작업을 실행한다.

---

## 2.3 Executor

Executor는 Agent에서 **동시에 실행할 수 있는 작업의 단위**이다.

예를 들어 어떤 Agent에 Executor가 2개 설정되어 있다면 해당 Agent는 최대 2개의 작업을 동시에 수행할 수 있다.

```
Agent
├── Executor #1 → Job A 실행
└── Executor #2 → Job B 실행
```

실제 운영 환경에서는 Controller 자체에서 빌드를 실행하기보다는 Controller의 Executor를 비활성화하고 별도의 Agent에서 빌드를 실행하는 것이 권장된다.

Controller는 Jenkins 관리에 집중시키고 실제 빌드 부하는 Agent로 분리하기 위함이다.

---

# 3. Job

**Job은 Jenkins가 수행하는 하나의 작업 단위**이다.

예를 들어 다음과 같은 작업들을 각각 Job으로 만들 수 있다.

```
backend-build
frontend-build
application-test
production-deploy
```

Job을 실행하면 하나의 **Build**가 생성된다.

```
backend-build
├── Build #1
├── Build #2
├── Build #3
└── Build #4
```

따라서 다음과 같이 구분할 수 있다.

```
Job
= 어떤 작업을 수행할 것인지에 대한 정의

Build
= 해당 Job을 실제로 한 번 실행한 결과
```

Jenkins에는 여러 형태의 Job이 있으며 대표적으로 다음이 있다.

- Freestyle Project
- Pipeline
- Multibranch Pipeline

최근 CI/CD 환경에서는 Pipeline을 이용해 작업을 코드로 관리하는 방식이 주로 사용된다.

---

# 4. Pipeline

**Pipeline은 빌드, 테스트, 배포와 같은 여러 작업을 하나의 흐름으로 정의하는 방법**이다.

예를 들어 애플리케이션 배포 과정을 다음과 같이 구성할 수 있다.

```
Checkout
    ↓
Build
    ↓
Test
    ↓
Deploy
```

Pipeline을 사용하면 CI/CD 과정을 코드로 작성할 수 있다.

이를 **Pipeline as Code**라고 하며 일반적으로 `Jenkinsfile`이라는 파일에 Pipeline을 정의한다.

```
Git Repository
│
├── src/
├── ...
└── Jenkinsfile
```

Jenkinsfile을 Git과 같은 SCM(Source Control Management)에 함께 저장하면 Pipeline 변경 사항 역시 소스 코드처럼 버전 관리할 수 있다.

---

# 5. Stage와 Step

Pipeline 내부의 작업은 여러 개의 **Stage**로 구성할 수 있다.

예를 들어 다음 Pipeline이 있다고 가정한다.

```
Pipeline
│
├── Stage: Build
│
├── Stage: Test
│
└── Stage: Deploy
```

## Stage

Stage는 Pipeline을 구성하는 **논리적인 작업 단계**이다.

일반적으로 다음과 같이 애플리케이션 생명주기의 주요 작업 단위로 나눈다.

```
Build
Test
Deploy
```

## Step

각 Stage 내부에서 실제로 수행하는 명령을 **Step**이라고 한다.

```
Pipeline
│
└── Stage: Build
      │
      ├── Step: echo
      ├── Step: sh
      └── Step: archiveArtifacts
```

즉 구조를 정리하면 다음과 같다.

```
Pipeline
└── Stages
    ├── Stage
    │   └── Steps
    │       ├── Step
    │       └── Step
    │
    └── Stage
        └── Steps
            └── Step
```

---

# 6. Jenkinsfile

Jenkins Pipeline은 일반적으로 `Jenkinsfile`을 통해 정의한다.

Jenkins에는 크게 두 가지 Pipeline 문법이 존재한다.

```
Pipeline
├── Declarative Pipeline
└── Scripted Pipeline
```

처음 Jenkins를 사용할 때는 구조가 명확하고 읽기 쉬운 **Declarative Pipeline**을 사용하는 것이 일반적이다.

가장 기본적인 Declarative Pipeline은 다음과 같다.

```groovy
pipeline {
    agent any

    stages {
        stage('Build') {
            steps {
                echo 'Building...'
            }
        }

        stage('Test') {
            steps {
                echo 'Testing...'
            }
        }

        stage('Deploy') {
            steps {
                echo 'Deploying...'
            }
        }
    }
}
```

구조를 나누어 보면 다음과 같다.

```groovy
pipeline {
```

전체 Pipeline을 정의한다.

```groovy
agent any
```

Pipeline을 실행할 수 있는 Agent를 할당한다.

```groovy
stages {
```

Pipeline에 존재하는 Stage들을 정의한다.

```groovy
stage('Build') {
```

하나의 Stage를 정의한다.

```groovy
steps {
```

해당 Stage에서 실행할 Step들을 정의한다.

```groovy
echo 'Building...'
```

실제로 실행되는 하나의 Pipeline Step이다.

따라서 위 Pipeline은 다음 순서로 실행된다.

```
Pipeline
│
├── Build
│     └── echo 'Building...'
│
├── Test
│     └── echo 'Testing...'
│
└── Deploy
      └── echo 'Deploying...'
```

---

# 7. Workspace

**Workspace는 Jenkins가 Job을 실행할 때 사용하는 작업 디렉터리**이다.

Agent가 Job을 실행하게 되면 해당 Job을 위한 Workspace가 생성되고 그 안에서 소스 코드 Checkout, Build, Test 등의 작업이 수행된다.

예를 들어 `first-pipeline`이라는 Job이 있다면 다음과 같은 Workspace가 생성될 수 있다.

```
/var/jenkins_home/workspace/first-pipeline
```

Pipeline에서 다음 명령을 실행하면 현재 Workspace를 확인할 수 있다.

```groovy
stage('Check Workspace') {
    steps {
        sh 'pwd'
        sh 'ls -la'
    }
}
```

Pipeline 실행 과정은 다음과 같이 볼 수 있다.

```
Agent
└── Workspace
    │
    ├── Source Code
    ├── Build Files
    ├── Test Files
    └── Temporary Files
```

예를 들어 Build Stage에서 파일을 생성하면 이후 Test Stage에서 동일한 Workspace의 파일을 사용할 수 있다.

```groovy
pipeline {
    agent any

    stages {
        stage('Build') {
            steps {
                sh 'echo "Hello Jenkins" > result.txt'
            }
        }

        stage('Test') {
            steps {
                sh 'cat result.txt'
            }
        }
    }
}
```

Build Stage에서 생성된 `result.txt`가 Workspace에 존재하기 때문에 Test Stage에서도 접근할 수 있다.

단, 서로 다른 Agent에서 Stage를 실행하거나 Workspace가 정리되는 경우에는 같은 파일이 자동으로 공유된다고 볼 수 없으므로 별도의 artifact, stash 등의 방법을 사용할 수 있다.

---

# 8. Jenkins 구성 요소 관계

지금까지 살펴본 개념의 관계를 정리하면 다음과 같다.

```
Jenkins Controller
│
├── Job 관리
├── Pipeline 관리
└── Agent 관리
        │
        ▼
      Agent
        │
        ├── Executor
        │     │
        │     └── Job 실행
        │
        └── Workspace
              │
              └── 실제 작업 파일 저장
```

Pipeline 기준으로 보면 다음과 같다.

```
Job
└── Pipeline
    │
    ├── Stage: Build
    │     └── Steps
    │
    ├── Stage: Test
    │     └── Steps
    │
    └── Stage: Deploy
          └── Steps
```

이를 하나로 연결하면 다음과 같이 볼 수 있다.

```
Controller
    │
    │ Job Scheduling
    ▼
Agent
    │
    │ Executor 할당
    ▼
Pipeline Job
    │
    ├── Stage: Build
    ├── Stage: Test
    └── Stage: Deploy
    │
    ▼
Workspace에서 실제 명령 실행
```

---

# 9. Jenkins 구축 실습

Jenkins 실습 환경은 Docker로 간단히 구축해보거나, 리눅스 환경(vm)에 직접 설치해 볼 수 있다.

## Docker로 실습

### Jenkins Volume 생성

```bash
docker volume create jenkins_home
```

Jenkins의 설정과 Job 데이터를 Container가 삭제된 이후에도 유지하기 위해 Docker Volume을 사용한다.

### Jenkins Container 실행

```bash
docker run -d \
  --name jenkins \
  -p 8080:8080 \
  -p 50000:50000 \
  -v jenkins_home:/var/jenkins_home \
  jenkins/jenkins:lts-jdk21
```

각 옵션의 의미는 다음과 같다.

| 옵션 | 설명 |
| --- | --- |
| `-d` | Container를 Background에서 실행 |
| `--name jenkins` | Container 이름 지정 |
| `-p 8080:8080` | Jenkins Web UI Port 연결 |
| `-p 50000:50000` | Jenkins Agent 통신을 위한 Port |
| `-v` | Jenkins 데이터를 Docker Volume에 저장 |

Jenkins 실행 후 다음 주소를 통해 Web UI에 접근할 수 있다.

```
http://localhost:8080
```

초기 관리자 Password는 다음 명령으로 확인할 수 있다.

```bash
docker exec jenkins \
  cat /var/jenkins_home/secrets/initialAdminPassword
```

## Linux VM으로 실습

Linux VM에 Jenkins를 직접 설치하여 Jenkins Controller를 구축한다.

### Java 설치

Jenkins 실행을 위해 Java Runtime이 필요하다.

```
sudo apt update
sudo apt install -y fontconfig openjdk-21-jre
```

설치 확인:

```
java -version
```

### Jenkins Repository 추가

```
sudo mkdir -p /etc/apt/keyrings

sudo wget -O /etc/apt/keyrings/jenkins-keyring.asc \
  https://pkg.jenkins.io/debian-stable/jenkins.io-2026.key

echo "deb [signed-by=/etc/apt/keyrings/jenkins-keyring.asc] https://pkg.jenkins.io/debian-stable binary/" \
  | sudo tee /etc/apt/sources.list.d/jenkins.list > /dev/null
```

### Jenkins 설치

```
sudo apt update
sudo apt install -y jenkins
```

Jenkins 서비스가 정상적으로 실행 중인지 확인한다.

```
sudo systemctl status jenkins
```

필요한 경우 Jenkins 서비스를 시작하고 부팅 시 자동으로 실행되도록 설정한다.

```
sudo systemctl enable --now jenkins
```

### Jenkins Web UI 접속

Jenkins는 기본적으로 TCP 8080 Port를 사용한다.

```
http://<VM-IP>:8080
```

초기 관리자 Password는 다음 경로에서 확인할 수 있다.

```
sudo cat /var/lib/jenkins/secrets/initialAdminPassword
```

Ubuntu/Debian 패키지로 Jenkins를 설치한 경우 기본 `JENKINS_HOME`은 다음과 같다.

```
/var/lib/jenkins
```

Job 실행 과정에서 생성되는 Workspace 역시 해당 디렉터리 아래에서 확인할 수 있다.

```
sudo ls -la /var/lib/jenkins/workspace
```

---

# 10. 첫 Pipeline 생성

Jenkins Web UI에서 다음과 같이 Pipeline Job을 생성한다.

```
Dashboard
→ New Item
→ first-pipeline
→ Pipeline
```

Pipeline Script에 다음 코드를 작성한다.

```groovy
pipeline {
    agent any

    stages {
        stage('Build') {
            steps {
                echo 'Building...'
            }
        }

        stage('Test') {
            steps {
                echo 'Testing...'
            }
        }

        stage('Deploy') {
            steps {
                echo 'Deploying...'
            }
        }
    }
}
```

Pipeline을 실행하면 논리적으로 다음 흐름을 갖는다.

```
Build
  ↓
Test
  ↓
Deploy
```

각 Stage 내부의 `echo` Step이 실행되며 실행 결과는 Jenkins의 Console Output에서 확인할 수 있다.

---

# 11. 정리

Jenkins의 기본 구조는 **Controller와 Agent**로 구성된다.

Controller는 Jenkins의 설정, Job, Pipeline, Agent 및 작업 스케줄링을 관리하고 Agent는 Controller가 할당한 실제 작업을 수행한다.

Jenkins에서 하나의 자동화 작업 정의를 Job이라고 하며 Job이 한 번 실행된 결과를 Build라고 한다.

CI/CD와 같이 여러 작업이 연결된 흐름은 Pipeline으로 정의할 수 있으며 Pipeline은 여러 Stage와 Step으로 구성된다.

```
Controller
    ↓
Agent
    ↓
Executor
    ↓
Job / Pipeline
    ↓
Stage
    ↓
Step
    ↓
Workspace
```

Pipeline은 `Jenkinsfile`로 코드화할 수 있기 때문에 애플리케이션 소스 코드와 함께 버전 관리할 수 있다는 장점이 있다.
