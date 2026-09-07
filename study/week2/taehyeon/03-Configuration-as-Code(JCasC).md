# Configuration as Code (JCasC)

## JCasC(Configuration as Code)란?

> Jenkins Controller 설정을 웹 UI에서 클릭해서 관리하지 않고 YAML 파일로 선언하여 관리하는 방식
> 

### JCasC 핵심 개념

1. JCasC는 Jenkins Controller의 설정을 **YAML 파일로 선언하고 관리할 수 있게 해주는 기능**이다.
2. 일반적으로 `jenkins.yaml` 파일에 Controller 설정을 작성하고, Jenkins 시작 시 해당 설정을 로드한다.
3. 인증/인가, 사용자, Credentials, Agent, Global Tools, Plugin의 전역 설정 등을 코드로 관리할 수 있다.
4. 설정 파일은 Git과 같은 SCM에서 관리할 수 있어 **변경 이력 추적, 코드 리뷰, 롤백**이 가능하다.
5. 동일한 `jenkins.yaml`을 사용하면 Jenkins Controller를 새로 구축하더라도 동일한 설정을 재현할 수 있다.

### 관리 범위

- JCasC를 통해 Jenkins Controller의 주요 전역 설정을 관리할 수 있다.
- 주요 관리 대상은 다음과 같다.
    - 인증 및 인가 설정
    - 사용자 및 계정 설정
    - Credentials
    - Agent 설정
    - Global Tools
    - Jenkins 및 Plugin의 전역 설정
- 설정 파일은 Git과 같은 SCM에서 관리할 수 있어 **변경 이력 추적, 코드 리뷰, 롤백**이 가능하다.

### 운영 특성

1. 비밀번호나 토큰 같은 민감 정보는 YAML에 직접 작성하지 않고 **환경 변수나 Secret Store를 통해 주입**하는 것이 권장된다.
2. JCasC는 **Plugin의 설정은 관리할 수 있지만 Plugin 자체를 설치하지는 않는다.**
3. Plugin 설치는 `jenkins-plugin-cli`, Docker Image, Helm 등의 방법으로 별도로 관리해야 한다.
4. JCasC를 사용하는 환경에서는 UI에서 직접 설정을 변경하기보다 **YAML을 Source of Truth로 관리하는 것이 권장된다.**

### Plugin 관리

- JCasC는 **Plugin의 설정은 관리할 수 있지만 Plugin 자체를 설치하지는 않는다.**
- Plugin 설치는 `jenkins-plugin-cli`, Docker Image, Helm 등의 방법으로 별도로 관리해야 한다.
- 따라서 Jenkins 환경을 완전히 코드로 관리하려면 Plugin 설치와 JCasC 설정을 함께 구성해야 한다.

```
Plugin 설치
    ↓
jenkins-plugin-cli
Docker Image
Helm

        +

Controller 설정
    ↓
JCasC
jenkins.yaml
```

### 설정 구조

```
Jenkins Controller
        │
        └── jenkins.yaml
                │
                ├── Security
                │   ├── Authentication
                │   └── Authorization
                │
                ├── Users
                │
                ├── Credentials
                │   ├── Username / Password
                │   ├── Token
                │   └── SSH Key
                │
                ├── Agents
                │
                ├── Global Tools
                │   ├── Git
                │   ├── JDK
                │   ├── Maven
                │   └── Gradle
                │
                └── Plugin Configuration
```

Jenkins 시작 시 설정 파일을 읽어 Controller 설정을 구성한다.

```
Jenkins 시작
    ↓
JCasC Plugin 로드
    ↓
jenkins.yaml 읽기
    ↓
Controller 설정 적용
```

### Jenkinsfile과의 차이

- JCasC는 **Jenkins Controller 자체의 설정**을 관리한다.
- Jenkinsfile은 **Build, Test, Deploy와 같은 Pipeline 실행 과정**을 정의한다.

```
JCasC
jenkins.yaml
    ↓
Jenkins 환경 설정
    ↓
Controller / Agent / Credentials / Tools

Jenkinsfile
    ↓
Pipeline 실행
    ↓
Build / Test / Deploy
```

### YAML 설정 예시

---

```yaml
jenkins:
  # Jenkins 화면에 표시할 메시지
  systemMessage: "Jenkins configured by JCasC"

  # Controller에서 직접 Build를 실행하지 않도록 설정
  numExecutors: 0

  # Jenkins 자체 사용자 인증 사용
  securityRealm:
    local:
      allowsSignup: false
      users:
        - id: "${JENKINS_ADMIN_ID}"
          password: "${JENKINS_ADMIN_PASSWORD}"

  # 로그인한 사용자만 Jenkins 사용 가능
  authorizationStrategy:
    loggedInUsersCanDoAnything:
      allowAnonymousRead: false

credentials:
  system:
    domainCredentials:
      - credentials:
          - usernamePassword:
              scope: GLOBAL
              id: "git-credentials"
              description: "Git Repository Credentials"
              username: "${GIT_USERNAME}"
              password: "${GIT_PASSWORD}"

tool:
  git:
    installations:
      - name: "Default Git"
        home: "/usr/bin/git"
```