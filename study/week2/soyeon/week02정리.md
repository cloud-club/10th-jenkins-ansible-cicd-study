# Jenkins 1주차 — Architecture, Infrastructure & Security

## 1. Jenkins가 하는 일

Jenkins는 개발자가 반복하는 빌드·테스트·배포 절차를 자동으로 실행하는 서버다. GitHub에 코드를 올리는 것만으로 배포가 되는 것은 아니다. 어떤 이벤트를 받을지, 어떤 명령을 실행할지, 어디에 배포할지를 Jenkins에 설정해야 한다.

- **CI(Continuous Integration)**: 코드를 자주 통합하고 빌드·테스트로 문제를 빠르게 발견한다.
- **Continuous Delivery**: 검증된 결과를 언제든 배포할 수 있게 준비한다. 실제 배포에는 승인이 있을 수 있다.
- **Continuous Deployment**: 검증을 통과한 변경을 운영 환경에 자동 배포한다.

```text
개발자 Push / PR
       ↓
GitHub → Webhook → Jenkins Controller
                         ↓ 작업 배정
                       Agent
                         ↓
                소스 받기 → 테스트 → 이미지 빌드
                                         ↓
                                    이미지 저장소
                                         ↓
                                      배포 서버
```

**Jenkins는 작업을 조율하고, Gradle·Docker 같은 도구가 실제 작업을 수행한다.** Jenkins 설치와 빌드 도구 설치를 구분해야 한다.

## 2. Controller / Agent Architecture

### 2.1 Controller, Node, Agent, Executor

| 개념 | 의미 | 예시 |
| --- | --- | --- |
| Controller | Jenkins 설정과 작업 실행을 관리하는 중심 프로세스 | 웹 UI, 권한, 대기열, Pipeline 조율 |
| Node | Jenkins가 작업을 실행할 수 있는 환경 | EC2, VM, 컨테이너 |
| Agent | Node에서 Controller와 통신하고 작업을 수행하는 프로세스 | `agent.jar`를 실행하는 Java 프로세스 |
| Executor | Node가 작업을 동시에 처리할 수 있는 슬롯 | executor 2개이면 두 작업을 동시에 수용 가능 |
| Workspace | 소스와 작업 중 파일이 놓이는 작업 디렉터리 | Git checkout 결과, 테스트 결과 파일 |

예를 들어 Agent A의 executor가 2개이고 빌드 3개가 동시에 요청되면, 다른 사용 가능한 Agent가 없을 때 하나는 대기한다. Executor는 CPU 코어 그 자체가 아니므로 숫자를 늘린다고 항상 빨라지지는 않는다. 메모리와 CPU가 부족하면 오히려 느려진다.

### 2.2 왜 Controller와 Agent를 분리할까?

Controller에서 대형 빌드까지 수행하면 Jenkins UI, 작업 관리, Pipeline 실행이 함께 영향을 받는다. 빌드 스크립트가 Controller의 파일에 접근할 위험도 커진다.

일반적으로 **Built-in Node의 executor를 `0`으로 설정**하고, 실제 빌드는 별도 Agent에 맡긴다. 이 설정은 Controller를 끄는 것이 아니다. Controller는 계속 Pipeline을 조율한다.

Agent에는 수행할 작업에 맞는 도구가 필요하다. Java 프로젝트라면 적절한 JDK가, Docker 이미지 빌드라면 Docker CLI와 접근 가능한 빌더가 있어야 한다. Agent용 Java와 애플리케이션 빌드용 JDK의 요구사항은 별개로 확인한다.

### 2.3 연결 방향 이해하기

| 방식 | 연결 시작 주체 | 준비할 것 |
| --- | --- | --- |
| Inbound Agent | Agent → Controller | Controller 주소, Agent 인증 정보, 네트워크 경로 |
| SSH Agent | Controller → Agent | SSH 서버, 접속 키, Agent 실행 환경 |

Inbound Agent는 TCP 또는 WebSocket으로 연결할 수 있다. WebSocket은 Jenkins의 HTTP(S) 경로를 이용하므로 별도 Agent TCP 포트 없이 구성할 수 있지만, 프록시도 WebSocket을 지원해야 한다. 오래된 자료의 JNLP는 현재 Inbound Agent 설명과 함께 등장하는 옛 표현이다.

SSH 방식에서는 Controller가 원격 서버에 접속해 Agent를 실행한다. “Outbound”라는 표현을 볼 때는 별도의 단일 프로토콜로 외우기보다 **누가 연결을 시작하는가**를 확인한다.

### 2.4 Label로 실행 환경 선택하기

Label은 Node에 붙이는 실행 환경 표시다. 서버 이름이 아니라 필요한 기능을 나타내는 이름으로 이해하면 쉽다.

```groovy
agent { label 'linux && docker' }
```

위 조건은 `linux`와 `docker` 라벨을 모두 가진 Node를 선택한다. 라벨을 붙였다고 Docker가 설치되지는 않는다. 실제 환경과 라벨이 일치해야 한다.

## 3. Docker 실행 환경과 동적 Agent

### 3.1 구분해야 할 세 가지

| 형태 | 의미 |
| --- | --- |
| Jenkins Controller를 Docker로 실행 | Jenkins 자체를 컨테이너로 배포 |
| Docker Pipeline으로 작업 실행 | 기존 Docker 가능 Node에서 빌드용 컨테이너 실행 |
| Docker 기반 동적 Agent | 필요할 때 Agent 컨테이너 자체를 생성하고 정리 |

Docker Pipeline 플러그인만 설치했다고 Agent 서버가 자동으로 늘어나는 것은 아니다. Agent의 동적 생성은 Docker/Kubernetes Cloud 같은 별도 구성에서 담당한다.

### 3.2 Docker Pipeline 예시

아래는 Docker Pipeline 플러그인과 Docker가 준비된 Node에서 JDK 컨테이너를 사용하는 예시다. Gradle Wrapper가 저장소에 있고 실행 권한이 있어야 한다.

```groovy
pipeline {
    agent {
        docker {
            image 'eclipse-temurin:21-jdk'
            label 'docker'
        }
    }
    stages {
        stage('Test') {
            steps { sh './gradlew test' }
        }
    }
}
```

Jenkins는 Node를 배정한 뒤 컨테이너를 시작하고, 작업 디렉터리를 연결해 명령을 실행한다. 프로젝트마다 도구 버전을 다르게 사용할 때 유용하다. 실제 프로젝트의 JDK 버전에 맞춰 이미지를 선택하고, 재현성이 필요하면 검증한 태그나 digest를 고정한다.

### 3.3 빌드 환경과 배포 이미지의 차이

`agent { docker ... }`는 **명령을 실행할 환경**을 고른다. `docker build`는 **배포할 애플리케이션 이미지**를 만든다. `agent { dockerfile true }`도 저장소의 Dockerfile로 실행 환경을 만드는 기능이므로, 애플리케이션 이미지 빌드·Push와 동일하게 생각하면 안 된다.

Docker 소켓을 컨테이너에 연결하면 호스트에 매우 강한 권한을 줄 수 있다. 학습 편의상 연결하더라도, 운영에서는 빌드 전용 환경과 신뢰 경계를 설계해야 한다.

## 4. JCasC: Jenkins 설정을 코드로 관리하기

### 4.1 왜 필요한가?

UI 설정만 사용하면 서버를 다시 만들 때 어떤 옵션을 선택했는지 기억해야 한다. JCasC는 지원되는 Jenkins 설정을 YAML로 선언해 변경 이력을 남기고 새 서버에 재적용하게 해 준다.

**JCasC는 설정 도구이며, 서버 전체의 백업 파일은 아니다.** 설치된 플러그인이 제공하는 설정을 다루므로 플러그인 버전에 따라 YAML 항목도 달라질 수 있다.

### 4.2 파일별 책임

```text
jenkins-infra/
├── Dockerfile
├── docker-compose.yml
├── plugins.txt
├── jenkins.yaml
└── terraform/          # EC2·네트워크 등 인프라 코드
```

| 파일 | 담당 |
| --- | --- |
| `Dockerfile` | Jenkins 기반 이미지와 플러그인 설치 절차 |
| `plugins.txt` | 설치할 플러그인 ID와 검증된 버전 |
| `docker-compose.yml` | 컨테이너 실행, 포트, 볼륨, 환경 변수 |
| `jenkins.yaml` | 계정, 권한, Agent, 도구 등 지원되는 설정 |
| `terraform/` | Jenkins 바깥의 서버·네트워크·IAM 구성 |

플러그인은 JCasC가 직접 설치하지 않는다. 이미지 생성 시 `jenkins-plugin-cli` 등으로 먼저 설치한다. Pipeline, Docker 실행 환경, GitHub 연동은 각각 필요한 플러그인이 다르다.

### 4.3 설정 적용 흐름

```text
Jenkins 이미지 준비 → 플러그인 설치 → YAML과 비밀값 주입
                                         ↓
                                Jenkins 시작 → JCasC 적용
```

다음은 설정의 일부다. 계정과 권한을 생략했으므로 이것만으로 외부 공개용 서버를 구성하지 않는다.

```yaml
jenkins:
  systemMessage: "Study Jenkins"
  numExecutors: 0
```

컨테이너에서는 YAML을 읽을 수 있는 경로에 배치하고 `CASC_JENKINS_CONFIG`로 위치를 알려줄 수 있다.

```yaml
# Compose 서비스 설정의 일부
volumes:
  - ./jenkins.yaml:/var/jenkins_config/jenkins.yaml:ro
environment:
  CASC_JENKINS_CONFIG: /var/jenkins_config/jenkins.yaml
```

### 4.4 계정·도구·Credentials는 어떻게 관리할까?

- **계정과 인증**: 로컬 계정 또는 LDAP 등의 인증 방식 설정을 관리한다.
- **권한**: Matrix나 역할 기반 정책을 코드로 남긴다.
- **Global Tools**: JDK·Git 등의 설치 이름과 경로, 지원되는 자동 설치 설정을 관리한다. 경로 선언만으로 모든 Agent에 도구가 설치되지는 않는다.
- **Credentials**: 종류·ID 등의 설정과 실제 비밀값의 공급 경로를 관리한다. 비밀값 자체는 외부에서 주입한다.

YAML은 현재 Jenkins의 **Configuration as Code → Documentation**과 플러그인 예시를 기준으로 작성한다. UI에서 설정한 후 Export를 참고할 수도 있지만, 내보낸 내용을 그대로 커밋하기 전에 불필요한 값과 민감 정보를 검토한다.

변경은 별도 학습 환경에서 검증하고 적용한다. UI에서만 수정하고 YAML에 반영하지 않으면 재생성·재적용 시 원하는 설정이 유지되지 않을 수 있다.

## 5. Security & Credentials

### 5.1 인증과 인가

**인증(Authentication)**은 사용자가 누구인지 확인하는 것이다. **인가(Authorization)**는 로그인한 사용자가 무엇을 할 수 있는지 결정하는 것이다. 로그인 가능하다고 관리자 권한까지 필요한 것은 아니다.

| 전략 | 관리 방식 | 이해를 위한 예 |
| --- | --- | --- |
| Matrix-based | 사용자·그룹과 권한을 표로 매핑 | 개발팀에 Job 조회·실행 권한 |
| Role-based | 역할을 만들고 사용자·그룹에 부여 | 운영 역할에 배포 Job 실행 권한 |

역할·프로젝트 범위 설정은 관련 플러그인 기능에 따라 달라진다. 실제 권한은 필요한 범위만 부여하고, 관리자 계정과 일반 작업 계정을 구분한다. Pipeline 편집 권한 역시 Agent에서 코드를 실행할 수 있는 중요한 권한이다.

### 5.2 Credential 종류와 범위

| 종류 | 사용 예 |
| --- | --- |
| Secret text | API 토큰 |
| Username/Password | 레지스트리 로그인 |
| SSH Username with private key | Git SSH 접근, 원격 접속 |
| Secret file | 파일 형태로 필요한 인증 정보 |

Credential ID는 Pipeline이 비밀값을 찾는 이름이다. 비밀번호 자체가 아니지만, 그 ID를 사용할 수 있는 Job과 사용자 범위를 제한해야 한다. 가능한 경우 프로젝트 Folder 아래에 자격 증명을 두어 사용 범위를 좁힌다. `System` 범위는 Jenkins 자체 연결용이며 일반 Pipeline 사용을 위한 `Global` 범위와 다르다.

### 5.3 Pipeline에서 사용하는 예시

Credentials Binding 플러그인과 `registry-login` ID의 Username/Password Credential이 필요하다. 아래는 `steps` 안에서 사용하는 조각이며, `registry.example.com`은 실제 레지스트리 주소로 바꾼다.

```groovy
withCredentials([usernamePassword(
    credentialsId: 'registry-login',
    usernameVariable: 'REG_USER', passwordVariable: 'REG_PASS'
)]) {
    sh '''
        set +x
        printf '%s' "$REG_PASS" | docker login registry.example.com \
            --username "$REG_USER" --password-stdin
    '''
}
```

Groovy의 작은따옴표 문자열로 전달하고 셸이 환경 변수를 해석하게 한다. 비밀번호를 명령 인자에 직접 넣는 방식도 피한다. Docker 로그인 정보는 Agent의 설정 파일에 남을 수 있으므로 격리된 작업 환경과 로그인 정보 정리도 고려한다.

### 5.4 Masking과 외부 Secret 저장소

Masking은 로그에 나타나는 알려진 비밀값을 가리는 기능이다. 악의적인 스크립트가 비밀값을 외부로 보내는 것까지 막지는 못한다. 신뢰하지 않는 PR에 배포용 Credentials를 주면 안 되는 이유다.

외부 저장소를 사용하면 비밀값의 보관·회전을 Jenkins 밖에서 관리할 수 있다.

| 방식 | 일반적인 흐름 |
| --- | --- |
| HashiCorp Vault | Jenkins가 인증 → 허용된 경로의 Secret 조회 → 필요한 작업에 값 제공 |
| AWS Secrets Manager | Jenkins의 AWS 권한으로 Secret 조회 → Provider가 Jenkins Credential로 제공 |

Vault는 인증 방식과 경로별 정책을, AWS는 IAM 권한과 플러그인이 요구하는 Secret 형식·메타데이터를 설정한다. 플러그인 설치만으로 연결이 완성되지는 않는다. Secret을 읽기 위한 최초 인증 수단도 필요하며, 캐시와 갱신 동작은 선택한 플러그인 문서에서 확인한다.

## 6. 여러 저장소를 하나의 Jenkins로 관리하기

```text
GitHub
├── jenkins-infra     # Jenkins 자체 구성
├── backend           # Jenkinsfile + 애플리케이션 Dockerfile
├── frontend          # Jenkinsfile + 애플리케이션 Dockerfile
└── batch             # Jenkinsfile + 애플리케이션 Dockerfile
```

Controller 하나가 여러 저장소의 Job을 관리하고, 실제 작업은 여러 Agent에 배정할 수 있다. 서비스별 Dockerfile은 이미지 제작법이고, Jenkinsfile은 checkout·테스트·빌드·Push·배포의 순서다.

**서버를 지운 뒤 다시 구성하는 것과 과거 상태를 복원하는 것은 다르다.**

| 필요한 결과 | 준비할 것 |
| --- | --- |
| 서버와 Jenkins 재생성 | 인프라 코드, 설치 절차, 이미지·플러그인 버전 |
| 동일한 설정 재적용 | JCasC |
| 저장소와 Job 자동 연결 | Job DSL 등으로 Multibranch/Organization Folder 정의 |
| Pipeline 재실행 | 각 저장소의 Jenkinsfile, 공통 라이브러리 |
| 외부 시스템 접속 | Secret 저장소와 접근 권한 |
| 과거 빌드 이력 복원 | 필요한 Jenkins 데이터와 결과물의 백업 |

`Jenkinsfile`만 있어도 Jenkins가 알아서 모든 GitHub 저장소를 찾아오지는 않는다. 탐색할 저장소와 인증 정보를 담은 상위 Job 설정이 필요하다. 재구성 후 Jenkins 주소가 바뀌면 DNS·Webhook 연결도 점검한다.

영속 볼륨은 컨테이너 재시작에도 데이터를 남긴다. 하지만 서버나 볼륨 삭제에 대비하려면 독립적인 백업이 필요하다. Jenkins 내부 Credential을 복원하려면 암호화 데이터뿐 아니라 관련 키도 필요하므로, 공식 백업 지침에 따라 보호하고 복원 연습을 한다.


## 공식 문서 및 프로젝트 자료

- [Jenkins Agents](https://www.jenkins.io/doc/book/using/using-agents/)
- [Controller Isolation](https://www.jenkins.io/doc/book/security/controller-isolation/)
- [Using Docker with Pipeline](https://www.jenkins.io/doc/book/pipeline/docker/)
- [Configuration as Code](https://www.jenkins.io/doc/book/managing/casc/)
- [JCasC 플러그인 — 설정 위치·Secret·플러그인 설치](https://plugins.jenkins.io/configuration-as-code/)
- [Jenkins 공식 Docker 이미지](https://github.com/jenkinsci/docker)
- [Matrix Authorization Strategy](https://plugins.jenkins.io/matrix-auth/)
- [Role-based Authorization Strategy](https://plugins.jenkins.io/role-strategy/)
- [Using Credentials](https://www.jenkins.io/doc/book/using/using-credentials/)
- [Credentials Binding](https://www.jenkins.io/doc/pipeline/steps/credentials-binding/)
- [HashiCorp Vault 플러그인](https://plugins.jenkins.io/hashicorp-vault-plugin/)
- [AWS Secrets Manager Credentials Provider](https://plugins.jenkins.io/aws-secrets-manager-credentials-provider/)
- [Backing up Jenkins](https://www.jenkins.io/doc/book/system-administration/backing-up/)
