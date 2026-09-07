# Security & Credentials

## 핵심 개념

- Jenkins 보안은 인증(Authentication), 인가(Authorization), Credentials 관리 세 축으로 나뉜다.
- 인증은 Security Realm이, 인가는 Authorization Strategy가 담당한다. 두 축은 서로 독립적으로 구성한다.
- Credentials는 Jenkins 로그인 계정과 별개로, Git·SSH·Docker Registry·Cloud API 등 외부 시스템 접근에 쓰는 인증 정보를 관리하는 기능이다.
- 운영 기준은 최소 권한 원칙이다. 사용자 권한과 Credential 접근 범위를 모두 필요한 최소로 제한한다.

## 인증 — Security Realm

- Jenkins 자체 사용자 데이터베이스: 내부에 계정을 저장한다. 소규모나 실습 환경에 적합하다.
- LDAP / Active Directory: 조직의 중앙 계정 시스템을 그대로 사용한다.
- GitHub, Google, GitLab 등 외부 인증 플러그인: 외부 계정으로 로그인한다. 단, 누구나 계정을 만들 수 있는 인증 방식과 관대한 인가 전략을 함께 쓰면 위험하다.

## 인가 — Authorization Strategy

- **Anyone can do anything**: 익명 사용자 포함 전원이 전체 권한. 로컬 테스트 외에는 사용하지 않는다.
- **Legacy mode**: admin은 전체 권한, 나머지는 읽기. 호환성 목적이며 운영에 부적합하다.
- **Logged-in users can do anything**: 로그인한 모두가 관리자 수준. 초기 단일 계정 단계에서만 성립하고, 외부 인증을 붙이는 순간 위험해진다.
- **Matrix-based Security**: 사용자·그룹별로 권한을 개별 지정한다. 운영 환경의 기본 출발점이다.
- **Project-based Matrix**: Folder, Job, Agent 단위까지 권한을 세분화한다.
- **Role-Based Strategy**: 역할을 정의하고 할당한다. 팀과 프로젝트가 많을 때 매트릭스보다 관리가 쉽다.

### 주요 권한

- `Overall/Read` — Jenkins 접근의 전제 권한
- `Overall/Administer` — 전체 설정 변경, 플러그인 관리, Script Console 접근. 최소 인원에게만 부여
- `Job/Read`, `Job/Build` — 조회 및 실행
- `Job/Configure` — **Pipeline Script와 Jenkinsfile 경로를 바꿀 수 있는 권한.** 아래 실습에서 다루듯 사실상 Credential 접근 권한과 동등하게 취급해야 한다
- `Credentials/Create` — Credential 생성. 엄격히 제한

## Credentials Store

- 외부 시스템 접근용 Secret을 Controller에 암호화 저장한다.
- Pipeline은 실제 값이 아니라 **Credential ID로 참조**한다. Jenkinsfile에 비밀값을 하드코딩하지 않게 하는 것이 목적이다.
- 복호화 키는 `$JENKINS_HOME/secrets/`에 있다. 백업과 SCM에서 분리해 관리해야 하며, 백업본과 이 키가 함께 유출되면 연결된 외부 시스템까지 위험해진다.

### 유형

- Secret text — API Token 같은 단일 문자열
- Username and password — 계정 정보
- Secret file — 인증서, 서비스 계정 키 등 파일
- SSH Username with private key — Git 접근, Agent 연결
- Certificate — PKCS#12

### Scope

- **System** — Controller 자체가 쓰는 것. Agent 연결, 메일 서버 인증 등. 일반 Pipeline에서는 사용할 수 없다
- **Global** — 모든 Item에서 사용 가능. 범위가 넓으므로 신중히 결정한다
- **Folder** — 특정 Folder와 하위 Job에서만 사용 가능. 배포 Credential처럼 민감한 값은 가능한 낮은 범위에 둔다

## 실습 — Secret Masking의 경계 확인

Jenkins는 바인딩된 Secret이 빌드 로그에 노출되지 않도록 마스킹한다. 이 보호가 **어디까지 유효한지** 직접 확인해봤다.

### 구성

Secret text `test-secret`에 더미 값 `MySecret1234`를 등록하고, 여러 방식으로 로그에 출력하는 Pipeline을 실행했다.

```groovy
pipeline {
    agent any
    stages {
        stage('Masking Test') {
            steps {
                withCredentials([string(credentialsId: 'test-secret', variable: 'SECRET')]) {
                    sh 'echo "1. plain:  $SECRET"'
                    sh 'echo "2. base64: $(echo $SECRET | base64)"'
                    sh 'echo "3. rev:    $(echo $SECRET | rev)"'
                    sh 'echo "4. cut:    $(echo $SECRET | cut -c1-6)"'
                }
            }
        }
    }
}
```

### 결과

| 출력 방식 | 로그 출력 | 마스킹 |
|---|---|---|
| `echo $SECRET` | `****` | 성공 |
| `echo $SECRET \| base64` | `****Cg==` | 부분 |
| `echo $SECRET \| rev` | `4321terceSyM` | 실패 |
| `echo $SECRET \| cut -c1-6` | `MySecr` | 실패 |

### 해석

- **1번**은 정상적으로 치환됐다. 빌드 로그에 `Masking supported pattern matches of $SECRET`가 함께 출력된다.
- **2번**은 예상과 달랐다. 공식 블로그(2019)에는 base64 인코딩 시 마스킹이 뚫린다고 나와 있는데, 실제로는 대부분 치환됐다. Jenkins가 원본 값뿐 아니라 그 값의 base64 형태까지 "supported pattern"으로 등록해두기 때문으로 보인다. 다만 꼬리에 `Cg==`가 남았다. `echo`가 붙이는 개행문자(`\n`) 때문에 실제 출력은 `MySecret1234\n`의 base64가 되고, 등록된 패턴(개행 없는 값의 base64)과 마지막 블록이 어긋난 결과다.
- **3번**은 전량 노출됐다. 문자열 뒤집기는 지원 패턴 목록에 없다.
- **4번**도 앞 6자리가 그대로 나왔다.

### 결론

- 마스킹은 **알려진 변형 목록에 대한 치환**이다. base64는 목록에 있어 막혔고, `rev`는 없어서 뚫렸다.
- 변형 방법은 사실상 무한하다. 뒤집기, 부분 추출, 문자 단위 분리 출력, 16진수 변환, 파일로 저장 후 아티팩트 업로드, 외부 서버 전송 등.
- 따라서 **Secret Masking은 보안 경계가 아니라 실수 방지 장치**다. 개발자가 실수로 `env`를 출력했을 때 사고를 줄여주는 용도이지, 의도적 유출을 막는 통제가 아니다.
- 공식 문서도 같은 입장이다. 마스킹은 우발적 노출을 줄이기 위한 것이며, Jenkins가 악의적 빌드 스크립트의 모든 유출을 막을 수는 없다고 명시한다.

### 실제 통제 지점

위 코드를 Pipeline에 넣을 수 있는 사람은 Credential 읽기 권한이 없어도 값을 가져갈 수 있다. 따라서 통제는 마스킹이 아니라 다음에서 이루어져야 한다.

- **Job/Configure 권한 제한** — Jenkinsfile과 Pipeline Script를 수정할 수 있는 사람은 그 Job이 쓰는 Credential을 유출할 수 있다고 가정한다
- **Jenkinsfile 저장소의 쓰기 권한** — Pipeline이 SCM에 있으면 저장소 권한이 곧 Credential 권한이다
- **Credential Scope 축소** — Global 대신 Folder 범위로 두고, 그 Folder를 만질 수 있는 사람을 제한한다
- **Controller/Agent 분리** — Built-in Node에서 일반 Job이 실행되지 않게 한다

즉 1번 주제(Controller/Agent 분리)와 3번 주제(권한 설계)가 별개가 아니라 같은 통제 구조의 다른 층이라는 점이 이번 정리에서 가장 크게 남았다.

## 외부 Secret Manager

- HashiCorp Vault, AWS Secrets Manager 등과 연동하면 Secret 저장·접근 제어·감사 로그·주기적 회전을 Jenkins 외부에서 관리할 수 있다.
- 다만 Job이 Secret을 사용할 수 있게 되는 순간 유출 가능성은 여전히 존재한다. Vault 정책과 Jenkins 권한, Folder 범위, 저장소 권한을 함께 설계해야 한다.

## 참고 자료

- [Jenkins 공식 문서 - Managing Security](https://www.jenkins.io/doc/book/security/managing-security/)
- [Jenkins 공식 문서 - Access Control](https://www.jenkins.io/doc/book/security/access-control/)
- [Jenkins 공식 문서 - Using credentials](https://www.jenkins.io/doc/book/using/using-credentials/)
- [Jenkins Blog - Limitations of Credentials Masking](https://www.jenkins.io/blog/2019/02/21/credentials-masking/)
- [Matrix Authorization Strategy Plugin](https://plugins.jenkins.io/matrix-auth/)
