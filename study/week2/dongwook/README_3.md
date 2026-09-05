# Security & Credentials

## 핵심 개념

- Jenkins 보안은 크게 인증(Authentication), 인가(Authorization), Credentials 관리로 나눌 수 있다.
- 인증은 사용자가 누구인지 확인하는 과정이며, Jenkins에서는 Security Realm이 담당한다.
- 인가는 인증된 사용자가 어떤 리소스에 접근하고 어떤 작업을 수행할 수 있는지 결정하는 과정이며, Authorization Strategy가 담당한다.
- Credentials는 Jenkins 사용자 로그인 정보와 별개로, Git, SSH 서버, Docker Registry, Cloud, API, DB 등 외부 시스템에 접근하기 위한 인증 정보를 관리하는 기능이다.
- 운영 환경에서는 최소 권한 원칙을 기준으로 사용자 권한과 Credential 접근 범위를 제한해야 한다.

## Jenkins 보안 기본 설정

- 과거 Jenkins에는 `Enable Security` 옵션이 있었고, 이를 통해 Jenkins의 보안 기능을 켜거나 끌 수 있었다.
- Jenkins 2.214 및 Jenkins LTS 2.222.1부터는 `Enable Security` 체크박스가 제거되었다.
- 현재 Jenkins는 기본적으로 보안을 사용하는 구조이며, 기본 Security Realm은 Jenkins 자체 사용자 데이터베이스이다.
- Jenkins 2.0부터 여러 보안 옵션이 기본 활성화되어 있으며, 운영 환경에서는 보안 기능을 임의로 비활성화하지 않는 것이 원칙이다.
- Jenkins Credentials는 사용자 계정 비밀번호가 아니라 Jenkins가 외부 시스템과 통신할 때 사용하는 Secret을 저장하는 기능이다.

## 인증과 인가

- Security Realm
  - Jenkins에 접근하는 사용자가 누구인지 확인한다.
  - 사용자 ID와 그룹 정보를 Jenkins에 제공한다.
  - Jenkins 자체 사용자 데이터베이스, LDAP, Active Directory, GitHub Authentication 같은 방식이 사용될 수 있다.

- Authorization Strategy
  - 인증된 사용자가 Jenkins에서 무엇을 할 수 있는지 결정한다.
  - Job 조회, 빌드 실행, Job 설정 변경, Agent 관리, Credentials 생성, Jenkins 관리 같은 권한을 제어한다.
  - Security Realm과 독립적으로 구성할 수 있으며, 조직의 인증 시스템과 Jenkins 권한 전략을 조합해서 사용할 수 있다.

```text
사용자 로그인
     |
     v
Security Realm
     |
     |  사용자 신원 / 그룹 확인
     v
Authorization Strategy
     |
     |  권한 확인
     v
Jenkins 리소스 접근 허용 또는 거부
```

## Security Realm 유형

- Jenkins 자체 사용자 데이터베이스
  - Jenkins 내부에 사용자 계정을 저장한다.
  - 소규모 환경이나 실습 환경에서 사용하기 쉽다.

- LDAP 또는 Active Directory
  - 외부 조직 계정 시스템을 Jenkins 인증에 사용한다.
  - 이미 중앙 사용자 관리 체계를 가진 조직에서 많이 사용한다.

- Servlet Container 위임
  - Jenkins가 실행되는 Servlet Container의 인증 기능에 위임한다.
  - 사용하는 컨테이너의 인증 설정을 별도로 이해해야 한다.

- GitHub, Google, GitLab 등 외부 인증 플러그인
  - 플러그인을 통해 외부 계정 시스템과 연동할 수 있다.
  - 외부 사용자가 쉽게 계정을 만들 수 있는 인증 방식과 `Logged-in users can do anything`를 함께 사용하면 위험하다.

## Authorization Strategy 유형

- Anyone can do anything
  - 익명 사용자를 포함한 모든 사용자가 Jenkins 전체 권한을 가진다.
  - 운영 환경에서는 사용하지 않아야 하며, 로컬 테스트 환경에서만 제한적으로 사용한다.

- Legacy mode
  - `admin` 역할을 가진 사용자는 전체 권한을 가지고, 그 외 사용자와 익명 사용자는 읽기 권한만 가진다.
  - 이전 Jenkins 버전과의 호환성을 위한 방식이며, 운영 환경에는 권장되지 않는다.

- Logged-in users can do anything
  - 로그인한 모든 사용자에게 Jenkins 전체 권한을 부여한다.
  - 단일 관리자 계정만 있는 초기 설정 단계에서는 사용할 수 있지만, 여러 사용자가 접근하는 운영 환경에는 적합하지 않다.
  - 외부 인증 연동이나 회원가입 허용 이후에도 이 전략을 유지하면 새로 로그인한 사용자도 관리자 수준 권한을 가질 수 있다.

- Matrix-based Security
  - 사용자 또는 그룹별로 Jenkins 권한을 세부적으로 부여하는 방식이다.
  - `Overall/Read`, `Job/Read`, `Job/Build`, `Job/Configure`, `Credentials/Create`, `Overall/Administer` 같은 권한을 개별적으로 제어할 수 있다.
  - 운영 환경에서는 가장 기본적인 출발점으로 많이 사용된다.

- Project-based Matrix Authorization Strategy
  - Matrix-based Security를 확장해 Folder, Job, Agent 같은 개별 리소스 단위의 권한 설정을 지원한다.
  - Global 권한과 프로젝트별 권한은 기본적으로 합산되어 적용된다.
  - 상위 Folder 권한 상속 방식은 설정에 따라 조정할 수 있다.

- Role-Based Authorization Strategy
  - Role Strategy Plugin을 사용해 역할 기반으로 권한을 관리하는 방식이다.
  - Global Role, Item Role, Agent Role을 정의하고 사용자 또는 그룹에 할당할 수 있다.
  - 팀, 프로젝트, 폴더가 많아 권한 매트릭스만으로 관리가 복잡할 때 유용하다.

## 주요 권한

- `Overall/Read`
  - Jenkins에 접근하기 위한 기본 권한이다.
  - 대부분의 다른 Jenkins 기능을 사용하기 위한 전제 권한이다.

- `Overall/Administer`
  - Jenkins에서 가장 높은 수준의 권한이다.
  - Jenkins 전체 설정 변경, 플러그인 설치 및 관리, Script Console 접근이 가능하다.
  - Jenkins Controller에 대한 강력한 제어 권한이므로 최소 인원에게만 부여해야 한다.

- `Job/Read`
  - 특정 Job을 조회할 수 있는 권한이다.
  - 이 권한이 없으면 해당 Job의 빌드 실행, 설정 변경, 삭제 같은 작업도 일반적으로 수행할 수 없다.

- `Job/Build`
  - 특정 Job을 실행할 수 있는 권한이다.
  - 배포 Job처럼 민감한 작업에는 신뢰할 수 있는 사용자나 그룹에만 부여해야 한다.

- `Job/Configure`
  - Job 설정을 변경할 수 있는 권한이다.
  - Pipeline Script 또는 Jenkinsfile 경로, 빌드 파라미터, 실행 Agent를 바꿀 수 있으므로 민감한 권한으로 봐야 한다.

- `Credentials/Create`
  - Jenkins Credentials를 생성할 수 있는 권한이다.
  - Credential을 추가할 수 있는 사용자는 엄격히 제한해야 한다.

## 흔한 보안 설정 실수

- `Anyone can do anything`를 운영 환경에서 사용하는 경우
  - Jenkins URL이 외부에 알려지지 않았다는 이유만으로 안전하다고 보면 안 된다.
  - 해당 전략은 익명 사용자에게도 전체 관리 권한을 줄 수 있다.

- `Logged-in users can do anything`를 계속 유지하는 경우
  - 처음에는 단일 관리자 계정만 있어서 문제가 없어 보일 수 있다.
  - 이후 LDAP, GitHub, Google, GitLab 같은 외부 인증과 연동하면 신뢰하지 않는 사용자도 관리자 권한을 얻을 수 있다.

- `anonymous` 또는 `authenticated`에 과도한 권한을 주는 경우
  - `anonymous`에 `Overall/Administer`를 부여하면 사실상 `Anyone can do anything`과 같다.
  - `authenticated`에 `Overall/Administer`를 부여하면 사실상 `Logged-in users can do anything`과 같다.

- Built-in Node에서 일반 Job을 실행하도록 두는 경우
  - 제한된 권한을 가진 사용자가 Controller에서 실행되는 Job을 설정할 수 있어서는 안 된다.
  - Controller에서 Job이 실행되면 Jenkins 파일 시스템, 환경 변수, Credential 등에 접근할 위험이 커진다.
  - 운영 환경에서는 Controller와 Agent를 분리하고 Built-in Node의 Executor를 0으로 설정하는 것이 좋다.

## 인바운드 Agent TCP 포트

- Jenkins는 인바운드 Agent와 통신하기 위해 별도의 TCP 포트를 사용할 수 있다.
- Jenkins 2.0부터 이 TCP 포트는 기본적으로 비활성화되어 있다.
- 인바운드 TCP Agent를 사용한다면 `Random Port` 또는 `Fixed Port` 중 하나를 선택할 수 있다.
- Jenkins 2.217부터는 인바운드 Agent가 WebSocket 전송 방식을 사용할 수 있다.
- WebSocket을 사용하면 별도의 TCP Agent 포트를 열기 어려운 환경에서도 Agent를 연결하기 쉽다.

- Random Port
  - Controller 시작 시 임의의 TCP 포트를 선택한다.
  - 포트 충돌을 피하기 쉽지만, 재시작할 때 포트가 바뀔 수 있어 방화벽 규칙 관리가 어렵다.

- Fixed Port
  - 관리자가 고정 TCP 포트를 지정한다.
  - Controller를 재시작해도 같은 포트를 사용하므로 방화벽 규칙 관리가 쉽다.

## Jenkins Credentials Store

- Jenkins Credentials Store는 외부 시스템 접근에 필요한 Secret을 Jenkins에 저장하고 관리하는 기능이다.
- Jenkins에 저장된 Credential은 Controller에 암호화된 형태로 저장된다.
- Pipeline이나 Job은 실제 Secret 값을 직접 저장하지 않고 Credential ID를 통해 Credential을 참조한다.
- 이 방식은 Secret이 Jenkins 사용자에게 노출될 가능성을 줄이고, Jenkinsfile이나 Job 설정에 비밀번호를 하드코딩하는 것을 방지한다.

## Credential 유형

- Secret text
  - API Token, GitHub Personal Access Token 같은 단일 Secret 문자열이다.

- Username and password
  - 사용자 이름과 비밀번호를 함께 저장한다.
  - Git, Docker Registry, 외부 API 인증 등에 사용할 수 있다.

- Secret file
  - 파일 형태의 Secret을 저장한다.
  - 인증서 파일, 설정 파일, 서비스 계정 키 파일 등에 사용할 수 있다.

- SSH Username with private key
  - SSH 사용자 이름과 Private Key를 저장한다.
  - Git 저장소 접근, SSH Agent 접속 등에 사용할 수 있다.

- Certificate
  - PKCS#12 인증서 파일과 선택적 비밀번호를 저장한다.

- Docker Host Certificate Authentication
  - Docker Host 인증에 필요한 인증서 정보를 저장한다.

## Credential Scope

- Global
  - Pipeline Job이나 Folder 등 Jenkins Item에서 사용할 수 있는 Credential이다.
  - 하위 Item에서도 사용할 수 있으므로 접근 범위를 신중히 정해야 한다.

- System
  - Jenkins Controller 자체가 시스템 관리 목적으로 사용하는 Credential이다.
  - 예를 들어 Agent 연결, 이메일 서버 인증 같은 Controller 내부 설정에 사용된다.
  - 일반 Pipeline에서 사용하기 위한 Credential은 보통 Global 또는 Folder 범위로 관리한다.

- Folder 수준 Credential
  - 특정 Folder와 그 하위 Job에서만 사용할 수 있는 Credential이다.
  - 배포 Credential처럼 민감한 값은 가능한 낮은 범위에 정의하는 것이 좋다.

## Credential 사용 예시

- Pipeline에서는 `withCredentials`를 사용해 Credential을 환경 변수로 바인딩할 수 있다.
- 아래 예시는 `amazon`이라는 Credential ID를 가진 Username/Password Credential을 사용하는 방식이다.

```groovy
withCredentials([
    usernamePassword(
        credentialsId: 'amazon',
        usernameVariable: 'USERNAME',
        passwordVariable: 'PASSWORD'
    )
]) {
    sh 'echo $PASSWORD'
    echo USERNAME
}
```

- 실제 운영에서는 예시처럼 Secret 값을 출력하지 않아야 한다.
- `sh 'echo $PASSWORD'`처럼 작은따옴표를 사용하면 Groovy 문자열 보간이 아니라 Shell에서 환경 변수가 확장된다.
- Pipeline 코드에서 Credential을 사용하려면 해당 Job 또는 Folder가 Credential에 접근할 수 있어야 한다.

## Secret Masking

- Jenkins는 `withCredentials` 등으로 바인딩된 Secret이 빌드 로그에 그대로 출력되지 않도록 마스킹한다.
- 일반적으로 Secret 값이 로그에 출력되면 `****`처럼 표시된다.
- Secret Masking은 실수로 로그에 Secret이 찍히는 것을 줄이기 위한 보호 장치이다.
- Secret Masking은 보안 경계가 아니며, Jenkins가 악의적인 빌드 스크립트의 모든 Secret 유출을 막을 수는 없다.
- 예를 들어 Secret을 인코딩해서 출력하거나, 파일로 저장한 뒤 아티팩트로 업로드하거나, 외부 서버로 전송하는 행위는 마스킹만으로 막을 수 없다.
- 따라서 Credential을 사용할 수 있는 Job, Folder, 사용자, Jenkinsfile 저장소의 쓰기 권한을 함께 제한해야 한다.

## Secret 보호와 백업

- Secret을 복호화하는 키는 `$JENKINS_HOME/secrets/` 디렉터리에 저장된다.
- 이 디렉터리는 매우 민감하므로 파일 시스템 권한과 백업 정책을 신중히 관리해야 한다.
- Jenkins 인스턴스를 복구하려면 Secret 복호화 키도 복구할 수 있어야 한다.
- 반대로 백업 파일과 Secret 복호화 키가 함께 유출되면 Jenkins 인스턴스와 연결된 외부 시스템까지 위험해질 수 있다.
- `$JENKINS_HOME/secrets/`를 일반 백업이나 SCM에 그대로 포함하지 않는 것이 좋다.
- Secret 키는 Jenkins 애플리케이션 백업과 분리된 안전한 위치에 별도로 보관하는 것이 권장된다.
- Credential 값은 주기적으로 교체하는 것이 좋다.

## 외부 Secret Manager 연동

- Jenkins 내부 Credentials Store 대신 HashiCorp Vault, AWS Secrets Manager 같은 외부 Secret Manager와 연동할 수 있다.
- 외부 Secret Manager를 사용하면 Secret 저장, 접근 제어, 감사 로그, Secret 회전 같은 기능을 Jenkins 외부 시스템에서 관리할 수 있다.
- Jenkins는 플러그인을 통해 외부 Secret Manager에 인증하고, Pipeline 또는 Job 실행 시 필요한 Secret을 가져온다.
- HashiCorp Vault Plugin은 Vault Secret을 환경 변수로 주입하거나 Pipeline에서 사용할 수 있게 해준다.
- Vault 연동은 개념적으로 다음 흐름으로 이해할 수 있다.

```text
+---------------------+
| HashiCorp Vault     |
|                     |
| secret/jenkins/db   |
| password=****       |
+----------^----------+
           |
           | HTTPS
           | 인증 + Secret 조회
           |
+----------+----------+
| Jenkins Controller  |
|                     |
| Vault Plugin        |
| Vault Credential    |
+----------+----------+
           |
           v
     Jenkins Agent
           |
           | DB_PASSWORD
           v
      Build / Deploy
```

- 외부 Secret Manager를 사용해도 Jenkins Job이 Secret을 사용할 수 있게 되는 순간 Secret 유출 가능성은 존재한다.
- 따라서 Vault 정책, Jenkins 권한, Folder 범위, Jenkinsfile 저장소 권한을 함께 설계해야 한다.

## 권장 운영 원칙

- 운영 환경에서는 `Anyone can do anything`, `Legacy mode`, `Logged-in users can do anything`를 사용하지 않는다.
- Matrix-based Security 또는 Role-Based Authorization Strategy를 사용해 사용자와 그룹별 권한을 명확히 나눈다.
- `Overall/Administer`는 최소 인원에게만 부여한다.
- `anonymous`와 `authenticated` 그룹에는 최소 권한만 부여한다.
- 일반 Job이 Built-in Node에서 실행되지 않도록 Controller와 Agent를 분리한다.
- Credential은 필요한 가장 낮은 범위에 정의한다.
- `Credentials/Create` 권한은 제한된 관리자에게만 부여한다.
- Jenkinsfile과 빌드 스크립트를 수정할 수 있는 사용자는 해당 Job에서 사용하는 Credential을 유출할 수 있다고 가정한다.
- Secret 값을 Jenkinsfile, Job 설정, Git 저장소, 빌드 로그에 직접 남기지 않는다.
- 민감한 배포 Secret은 Folder 권한, Credential Scope, 외부 Secret Manager 정책을 함께 사용해 보호한다.

## 참고 자료

- [Jenkins 공식 문서 - Managing Security](https://www.jenkins.io/doc/book/security/managing-security/)
- [Jenkins 공식 문서 - Access Control](https://www.jenkins.io/doc/book/security/access-control/)
- [Jenkins 공식 문서 - Using credentials](https://www.jenkins.io/doc/book/using/using-credentials/)
- [Jenkins 공식 문서 - Credentials](https://www.jenkins.io/doc/book/security/credentials/)
- [Jenkins Blog - Limitations of Credentials Masking](https://www.jenkins.io/blog/2019/02/21/credentials-masking/)
- [Jenkins Plugin - Matrix Authorization Strategy](https://plugins.jenkins.io/matrix-auth/)
- [Jenkins Plugin - Role-based Authorization Strategy](https://plugins.jenkins.io/role-strategy/)
- [Jenkins Plugin - HashiCorp Vault](https://plugins.jenkins.io/hashicorp-vault-plugin/)
