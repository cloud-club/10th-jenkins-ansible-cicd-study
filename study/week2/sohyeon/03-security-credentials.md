## 3. Security & Credentials

### 3-1) Matrix-based security 및 Role-Based Access Control

**권한 제어 방식**

- **Authentication**: 보안 영역 (사용자가 본인임을 증명)
- **Authorization**: 권한 부여 (사용자가 특정 작업을 수행하는 것을 허용)

**Matrix Authorization**

- 각 항목 또는 Agent에 대한 권한을 독립적으로 구성할 수 있다.
- 전역 구성에서 부여된 권한은 해당 항목 또는 Agent 모두에게 적용된다.
  - **권한 상속**: 개별 항목 또는 Agent에 명시적으로 부여된 권한은 전역적으로 또는 상위 항목에 정의된 권한에만 추가된다.
  - **전역 구성만 상속**: 이 옵션을 선택하면 전역적으로 부여된 권한만 상속되고 상위 폴더에 부여된 권한은 상속되지 않는다. 따라서 폴더 내의 작업은 상위 폴더와 관계없이 액세스 권한을 독립적으로 제어할 수 있다.
  - **권한 상속 안 함**: Agent 또는 항목에 명시적으로 정의된 권한만 부여한다.
- 프로젝트 기반 매트릭스 권한 부여 방식을 사용할 경우, 항목 또는 Agent를 구성할 수 있는 권한을 부여받은 사용자는 해당 항목 또는 Agent에 대한 다른 모든 권한도 스스로 부여할 수 있다.
  - Jenkins에 대한 읽기 권한이 부여되지 않은 사용자는 부여받은 다른 권한 대부분을 사용할 수 없다.
  - 작업에 대한 읽기 권한이 부여되지 않은 사용자는 새 빌드를 시작하거나, 작업을 삭제하거나, 작업을 구성하는 등의 작업을 수행할 수 없다.
  - 글로벌 매트릭스 권한 부여를 사용하는 경우, 작업 구성 권한은 부여받았지만 작업을 시작할 권한은 부여받지 못한 사용자도 주기적으로 실행될 작업을 구성할 수 있다.

**Role-based Authorization Strategy**

- 사용자의 권한을 관리하는 새로운 역할 기반 메커니즘을 추가하기 위해 사용한다.
  - 전역 역할을 생성할 수 있다.
  - 항목 별 역할을 생성하여 그에 따른 권한을 설정할 수 있다.
  - Agent 별 권한을 설정할 수 있다.
  - 사용자 및 사용자 그룹에 역할을 할당할 수 있다.

**Matrix-based와 Role-based의 차이**

- Matrix-based는 권한을 직접 부여하지만 Role-based는 역할로 묶어서 부여한다.

### 3-2) Jenkins Credentials Store

**Credentials**: 액세스를 보호하기 위한 자격 증명 (여러 종류의 인증 정보 저장)

- 종류: Secret text, Username and password, Secret file, SSH Username with private key, Certificate, Docker Host Certificate Authentication
- 파이프라인에 하는 하드코딩보다 안전하고 편리하다.
- 자격 증명에 대한 접근 범위를 제한해야 한다.
  - 자격 증명의 생성 권한 제한 (Matrix 기반 보안)
- 암호가 들어있는 디렉토리를 보호해야 한다.
  - 백업할 때 제외하기
  - SCM에 저장하지 않기

### 3-3) Secret Masking & External Vault Integration: HashiCorp Vault 또는 AWS Secrets Manager 연동 기법

**Secret Masking**

- Credentials Binding을 사용하면 Jenkins에 저장된 Credential을 파이프라인의 환경 변수 등에 연결하여 사용할 수 있다.
- Secret이 빌드 로그에 출력되는 경우 Jenkins가 해당 값을 `**` 형태로 마스킹한다.
- 하지만 Secret Masking 자체가 완전한 보안 방법은 아니다.
  - Pipeline을 수정할 수 있는 사용자가 Secret을 의도적으로 다른 방식으로 출력하거나 사용할 수도 있다.
  - 따라서 Secret Masking뿐만 아니라 Credential에 접근할 수 있는 사용자와 Job 자체를 제한해야 한다.
- Secret을 Groovy 문자열 등에 직접 넣는 것보다 Credentials Binding을 이용하여 필요한 범위에서만 사용하는 것이 좋다.

**External Secret Management**

- Jenkins 내부의 Credentials Store에 Secret을 저장하는 대신 외부 Secret 관리 시스템을 사용할 수도 있다.
- 대표적으로 HashiCorp Vault와 AWS Secrets Manager를 사용할 수 있다.
- Jenkins에서는 플러그인을 통해 외부에 저장된 Secret을 파이프라인에서 사용할 수 있도록 연동할 수 있다.

**HashiCorp Vault**

- HashiCorp Vault 플러그인을 사용하면 Vault에 저장된 Secret을 파이프라인에서 가져와 사용할 수 있다.
- AppRole 인증 백엔드를 사용하여 Vault에 대한 인증을 지원한다.
  - AppRole의 작동 방식: 사용자가 직접 선택한 이름을 사용하여 approle 인증 백엔드를 등록한다. approle은 고유 식별자로 지정되고 보안 토큰으로 보호되며, 이 두 가지 값을 모두 가지고 있으면 Vault에 접근하는 데 사용할 수 있다.
- GitHub 개인 액세스 토큰 또는 Vault 토큰을 사용할 수 있도록 지원하며, 이러한 토큰은 Jenkins에 직접 구성하거나 Jenkins 컨트롤러의 임의 파일에서 읽어올 수 있다.
- 작업이나 폴더에 각각 별도의 Vault 정책을 할당했을 시의 절차:
  1. Jenkins가 Vault에서 비밀 정보를 가져오려고 시도한다.
  2. AppRole 인증이 새 토큰을 가져오는 데 사용된다.
  3. Vault 플러그인이 정책 목록을 생성한다.
  4. AppRole 토큰을 사용해서 지정된 정책만 적용된 새 토큰을 가져온다.

```yaml
unclassified:
  hashicorpVault:
    configuration:
      vaultCredentialId: "vaultToken"
      vaultUrl: "https://vault.company.io"

credentials:
  system:
    domainCredentials:
      - credentials:
          - vaultTokenCredential:
              description: "Uber Token"
              id: "vaultToken"
              scope: GLOBAL
              token: "${MY_SECRET_TOKEN}"
```

**AWS Secrets Manager**

- AWS 환경에서는 AWS Secrets Manager Credentials Provider 플러그인을 사용하여 Secrets Manager에 저장된 Secret을 Jenkins Credential처럼 사용할 수 있다.
- Jenkins가 Secrets Manager의 Secret을 가져오기 위해서는 AWS IAM 권한 설정이 필요하며, `secretsmanager:GetSecretValue`, `secretsmanager:ListSecrets` 등의 권한이 사용된다.
- 이렇게 구성하면 비밀번호나 API Key 같은 민감한 정보를 Jenkins 내부에 직접 관리하기보다 AWS Secrets Manager에서 관리하고 Jenkins에서는 필요한 Credential을 가져와 사용할 수 있다.

### 3-4) 참고 문헌

- https://www.jenkins.io/doc/book/security/managing-security/
- https://plugins.jenkins.io/matrix-auth/
- https://plugins.jenkins.io/role-strategy/
- https://www.jenkins.io/doc/book/security/credentials/
- https://www.jenkins.io/doc/book/using/using-credentials/
- https://www.jenkins.io/doc/pipeline/steps/credentials-binding/
- https://plugins.jenkins.io/hashicorp-vault-plugin/
- https://plugins.jenkins.io/aws-secrets-manager-credentials-provider/
