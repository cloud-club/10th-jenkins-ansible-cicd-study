# Security & Credentials

## 핵심 개념

- Jenkins의 보안은 크게 **Authentication(인증)**과 **Authorization(인가)**으로 구분된다.
- Authentication은 사용자가 누구인지 확인하는 과정이며, Jenkins에서는 **Security Realm**이 담당한다.
- Authorization은 인증된 사용자가 어떤 작업을 수행할 수 있는지 결정하는 과정이며, **Authorization Strategy**가 담당한다.
- 운영 환경에서는 모든 사용자에게 관리자 권한을 부여하지 않고, 필요한 작업에 필요한 권한만 부여하는 **최소 권한 원칙(Least Privilege)**을 적용하는 것이 권장된다.

## Matrix-based Security

- Matrix-based Security는 **사용자 또는 그룹별로 Jenkins의 세부 권한을 직접 지정하는 방식**이다.
- `Job/Read`, `Job/Build`, `Job/Configure`, `Credentials/Create`, `Overall/Administer` 등 Jenkins의 권한을 세부적으로 제어할 수 있다.
- 사용자와 권한을 Matrix 형태로 구성하기 때문에 특정 사용자는 조회만 가능하게 하고, 특정 사용자는 Build까지 가능하도록 설정할 수 있다.
- Project-based Matrix Authorization을 사용하면 전체 Jenkins가 아니라 **특정 Folder나 Job 단위로 권한을 세분화**할 수도 있다.
- Matrix-based Security는 Jenkins Core 자체 기능이 아니라 **Matrix Authorization Strategy Plugin**을 통해 제공된다.

```
                    Read    Build    Configure    Admin

Developer A          O        O          X          X
Developer B          O        O          O          X
Administrator        O        O          O          O
```

## Role-Based Access Control (RBAC)

- Role-Based Access Control은 사용자에게 권한을 하나씩 직접 부여하는 대신 **Role을 정의하고 사용자 또는 그룹에 Role을 할당하는 방식**이다.
- Jenkins에서는 **Role Strategy Plugin**을 사용하여 Role 기반 권한 관리를 구성할 수 있다.
- `Admin`, `Developer`, `Viewer`와 같은 Role을 만들고 각 Role에 필요한 권한을 정의할 수 있다.
- Role은 Jenkins 전체에 적용되는 **Global Role**, Job이나 Folder에 적용되는 **Item Role**, Agent에 적용되는 **Agent Role** 등으로 구분할 수 있다.
- 사용자가 많거나 팀별로 권한을 관리해야 하는 환경에서는 사용자별 권한을 직접 관리하는 것보다 Role 기반 관리가 편리하다.

```
User / Group
     ↓
   Role
     ↓
Permissions

Developer
  ├── Job/Read
  ├── Job/Build
  └── Job/Cancel

Admin
  └── Overall/Administer
```

## Jenkins Credentials Store

- Jenkins Credentials Store는 Pipeline이나 Agent가 외부 시스템에 접근할 때 필요한 **비밀번호, Token, SSH Key 등의 인증 정보를 저장하고 관리하는 기능**이다.
- Git Repository, Docker Registry, AWS, 배포 서버, 데이터베이스 등 외부 시스템의 인증 정보를 Jenkinsfile에 직접 작성하지 않고 Credentials Store에 저장할 수 있다.
- Pipeline에서는 실제 Secret 값을 직접 사용하는 대신 **Credential ID를 이용해 필요한 인증 정보를 참조**한다.
- Jenkins에 저장된 Credentials는 Controller에서 암호화된 형태로 저장된다.

대표적인 Credential 종류는 다음과 같다.

- **Secret Text**
    - API Token, Access Token과 같은 단일 문자열 Secret
- **Username / Password**
    - Git, Registry 등의 계정과 비밀번호
- **SSH Username with Private Key**
    - SSH를 이용한 서버 접속이나 Git 인증
- **Secret File**
    - 인증서나 설정 파일처럼 파일 형태로 전달해야 하는 Secret
- **Certificate**
    - PKCS#12 형태의 인증서와 비밀번호

```
Jenkins Credentials Store
        │
        ├── git-credentials
        │     └── Username / Password
        │
        ├── github-token
        │     └── Secret Text
        │
        ├── deploy-server
        │     └── SSH Private Key
        │
        └── aws-credentials
              └── AWS 인증 정보

                    ↓

               Jenkinsfile

             credentialsId
```

## Credentials Scope

- Credentials는 필요한 범위에만 노출되도록 **Scope를 제한하여 관리하는 것이 권장된다.**
- Controller Root에 등록한 Credential은 많은 Job에서 사용할 수 있으므로 민감한 Credential의 접근 범위가 넓어질 수 있다.
- 특정 Folder에 Credential을 등록하면 해당 Folder 내부의 Pipeline에서만 사용할 수 있도록 제한할 수 있다.
- Jenkins 자체에서 사용하는 Agent 연결 등의 Credential에는 `System` Scope를 사용할 수 있다.
- 따라서 Credentials 역시 모든 Job에서 공유하기보다 **필요한 Job과 Folder에 최소한으로 제공하는 것이 중요하다.**

## Secret Masking

- Jenkins Pipeline에서 Credentials를 사용할 때 Secret이 Console Log에 그대로 출력되지 않도록 **Secret Masking**을 적용할 수 있다.
- `withCredentials` 등을 통해 주입한 Secret이 로그에 출력되면 Jenkins가 해당 값을 `***` 형태로 마스킹한다.
- Secret Masking의 목적은 **로그를 통한 우발적인 Secret 노출을 방지하는 것**이다.
- Secret Masking이 Secret 자체에 대한 완전한 접근 통제를 제공하는 것은 아니다.
- Credential을 사용할 수 있는 악의적인 Pipeline은 Secret을 다른 방식으로 외부에 전송할 수 있으므로 **신뢰할 수 없는 Job에는 Credential 자체를 제공하지 않는 것이 중요하다.**

```
실제 Secret

AWS_SECRET_ACCESS_KEY=abcdef123456

        ↓

Jenkins Console Log

AWS_SECRET_ACCESS_KEY=****
```

## External Vault Integration

- Jenkins 내부 Credentials Store 대신 **외부 Secret Store에서 Secret을 관리**할 수도 있다.
- 대표적으로 **HashiCorp Vault**와 **AWS Secrets Manager**를 Jenkins와 연동할 수 있다.
- Secret을 Jenkinsfile이나 `jenkins.yaml`에 직접 저장하지 않고 실행 시 외부 Secret Store에서 필요한 값을 가져오는 방식으로 사용할 수 있다.
- 이를 통해 Secret의 저장과 Jenkins 설정을 분리하고, Secret의 변경 및 접근 권한을 외부 Secret 관리 시스템에서 통제할 수 있다.

```
HashiCorp Vault
AWS Secrets Manager
        │
        │ Secret 조회
        ↓
     Jenkins
        │
        ↓
     Pipeline
        │
        ↓
 Build / Deploy
```

- AWS Secrets Manager Credentials Provider Plugin을 사용하면 AWS Secrets Manager의 Secret을 Jenkins Credential처럼 사용할 수 있다.
- 이 경우 Jenkins가 AWS Secrets Manager를 조회할 수 있도록 `secretsmanager:GetSecretValue` 등의 IAM 권한을 부여해야 한다.
- KMS Customer Managed Key를 사용하는 경우에는 추가로 `kms:Decrypt` 권한이 필요할 수 있다.

## 핵심 정리

- Jenkins 보안은 **Authentication과 Authorization**으로 구분된다.
- Matrix-based Security는 **사용자/그룹과 세부 권한을 직접 매핑하는 방식**이다.
- Role-Based Access Control은 **권한을 Role로 묶어 사용자나 그룹에 할당하는 방식**이다.
- Jenkins Credentials Store는 외부 시스템 접근에 필요한 Secret을 중앙에서 관리한다.
- Pipeline에서는 실제 Secret 대신 **Credential ID를 통해 인증 정보를 사용**하는 것이 기본 방식이다.
- Secret Masking은 Console Log를 통한 우발적인 노출을 방지하지만 완전한 보안 수단은 아니다.
- 중요한 Credential은 사용 가능한 Job과 Folder를 최소화해야 한다.
- HashiCorp Vault나 AWS Secrets Manager를 연동하면 **Secret 저장과 Jenkins 설정을 분리하여 관리**할 수 있다.