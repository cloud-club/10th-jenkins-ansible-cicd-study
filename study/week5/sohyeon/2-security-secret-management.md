## **2. Security & Secret Management**

---

### 2-1) Ansible Vault를 활용한 변수 및 Secret 암호화

```
Plaintext Variables / Files
            │
            │ ansible-vault encrypt / create
            ▼
Encrypted Data (Data at Rest)
            │
            │ ansible / ansible-playbook --vault-id or --ask-vault-pass
            ▼
Decrypted Data (Data in Use)
```

**Ansible Vault**

- 암호나 키와 같은 민감한 내용(Secret)을 일반 텍스트(Plaintext)로 남겨두지 않고 변수 및 파일 단위로 암호화하여 보호하는 기능
- 암호화된 콘텐츠는 소스 제어 시스템(Git 등)에 안전하게 커밋하고 공유할 수 있다.

**Ansible Vault의 암호화 대상 및 명령**

- **`ansible-vault` CLI 명령어**: 암호화된 변수 생성 및 보기, 파일 암호화/복호화, 기존 파일 수정, 비밀번호 변경(re-key) 등을 수행한다.
- **암호화 단위**: 플레이북 전체 파일, 특정 역할(Role) 내 변수 파일, 또는 개별 변수 단위로 암호화를 적용한다.

**Ansible Vault의 특징**

- 안전한 민감 정보 보관
    - 비밀번호, API 토큰, SSH 키 등을 코드 저장소에 안전하게 관리할 수 있도록 지원한다.
    - 하나 이상의 비밀번호를 사용하여 암호화 및 복호화를 수행한다.
- 비밀번호 자동화 지원
    - Vault 비밀번호를 외부 비밀번호 관리자(Secret Manager)에 저장한 경우, 스크립트를 통해 자동으로 가져와 연결할 수 있다.
    - `ansible.cfg` 설정 파일에 비밀번호 파일 위치를 지정하거나 실행 시 비밀번호 입력을 요청하도록 설정할 수 있다.

**Ansible Vault의 보안 원칙 및 보안 고려사항**

- Data at Rest 보호 원칙
    - Ansible Vault의 암호화는 저장되어 있는 상태인 **'Data at Rest'** 상태만 보호한다.
- Data in Use 상태에서의 노출 방지
    - 실행 단계에서 데이터가 복호화된 **'Data in Use'** 상태가 되면, 실행 로그나 출력 화면을 통해 민감 정보가 노출되지 않도록 `no_log` 설정을 적용해야 한다.
    - 에디터를 통해 암호화된 파일을 편집할 때 임시 파일 등으로 인한 보안 누수가 발생하지 않도록 에디터 보안 설정에 주의해야 한다.

---

### 2-2) `ansible-vault encrypt`, `encrypt_string`, `-vault-id` 활용

**Ansible Vault의 핵심 개념**

- 플레이북, 변수 파일 등 내부에 포함된 비밀번호, API 키와 같은 민감 데이터를 암호화하여 보호하는 기능.
- 암호화된 콘텐츠는 YAML 및 Ansible에 복호화가 필요함을 알리는 `!vault |` 태그가 부가됨.

**1. 파일 전체 암호화 (`ansible-vault encrypt`)**

- **특징**: 전체 구조화 데이터 파일(변수 파일, tasks 파일 등)을 통째로 암호화함.
- **장점 및 단점**: 변수명까지 완전히 숨길 수 있으며 비밀번호 재설정(`rekey`) 관리가 수월함. 다만 파일 내용 전체가 암호화되므로 가독성이 떨어짐.
- **사용 사례**:
    - 기존 일반 YAML 파일 암호화:
        
        ```
        ansible-vault encrypt foo.yml bar.yml
        ```
        
    - 신규 암호화 파일 생성 및 편집:
        
        ```
        ansible-vault create foo.yml
        ```
        

**2. 개별 변수 암호화 (`ansible-vault encrypt_string`)**

- **특징**: 전체 파일 대신 특정 변수의 값(문자열)만 골라서 암호화함.
- **장점 및 단점**: 일반 플레이북/변수 파일의 가독성을 유지하면서 민감 데이터만 숨길 수 있음. 다만 개별 변수는 `rekey` 명령으로 일괄 비밀번호 변경이 불가능함.
- **사용 사례**:
    - 기본 변수 암호화:
        
        ```
        ansible-vault encrypt_string --vault-password-file a_password_file 'foobar' --name 'the_secret'
        ```
        
    - 프롬프트를 통한 비밀번호 입력 및 변수 암호화:
        
        ```
        ansible-vault encrypt_string --vault-id dev@a_password_file --stdin-name 'new_user_password'
        ```
        

**3. 다중 암호화 및 식별자 관리 (`--vault-id`)**

- **특징**: 환경(dev, prod 등)이나 사용자별로 서로 다른 암호화 키/비밀번호를 명확히 구분하여 적용.
- **장점**: 어떤 비밀번호 파일이나 프롬프트로 복호화해야 하는지 레이블을 통해 직관적으로 지정 및 관리 가능.
- **사용 사례**:
    - Vault ID 레이블을 지정하여 개별 변수 암호화:
        
        ```
        ansible-vault encrypt_string --vault-id dev@a_password_file 'foooodev' --name 'the_dev_secret'
        ```
        
    - Vault ID 지정 및 비밀번호 프롬프트 입력을 통한 파일 생성:
        
        ```
        ansible-vault create --vault-id my_new_password@prompt foo.yml
        ```
        
    - 기존 암호화 파일의 Vault ID 및 비밀번호 변경 (`rekey`):
        
        ```
        ansible-vault rekey --vault-id preprod1@ppold --new-vault-id preprod2@prompt foo.yml
        ```
        

---

### 2-3) Vault Password File 및 CI/CD 환경에서의 Vault Password 전달 방식

```
[CI/CD Engine / Control Node]
    │
    ├── (1) CLI 옵션 / 환경변수 참조
    │       ├── --vault-password-file / --vault-id
    │       └── ANSIBLE_VAULT_PASSWORD_FILE
    │
    ▼
[Vault Password Source]
    ├── Plain Text File (.vault_pass.txt)
    └── Executable Script (Vault Client Script)
```

**Vault Password File 개요**

- Ansible Vault로 암호화된 변수나 파일을 복호화하기 위해 필요한 비밀번호 소스.
- 명령어 실행 시 매번 비밀번호를 직접 입력(`-ask-vault-pass`)하지 않고, 파일이나 스크립트를 통해 자동으로 비밀번호를 전달할 수 있다.

**Vault Password 전달 방식**

- CLI 옵션을 통한 단일 비밀번호 전달
    - `-vault-password-file`: 텍스트 파일 경로 또는 실행 가능한 스크립트 경로를 지정하여 비밀번호를 불러온다.
- Vault ID를 활용한 식별 및 전달 (`-vault-id`)
    - 여러 암호화 소스가 존재할 때 레이블(`dev`, `prod` 등)을 붙여 비밀번호를 명확히 구분하여 전달할 수 있다.
    - 레이블과 함께 파일 경로 또는 스크립트를 지정할 수 있다 (`dev@dev-password` 또는 `dev@my-script.py`).
- 기본값 설정 (Configuration / Environment Variables)
    - `ANSIBLE_VAULT_PASSWORD_FILE`: 환경변수로 비밀번호 파일 경로를 설정하여 명령어마다 옵션을 붙이지 않고 기본 소스로 활용한다.
    - `DEFAULT_VAULT_IDENTITY_LIST`: `ansible.cfg` 설정에서 기본으로 사용할 Vault ID 목록과 비밀번호 소스를 지정한다.

**CI/CD 환경에서의 Vault Password 활용**

- **자동화 파이프라인 연동**
    - Jenkins, GitLab CI, GitHub Actions 등 CI/CD 도구에서 사람의 개입 없이 Playbook을 실행할 때 필수적으로 활용된다.
- **Executable Script (Client Script) 활용**
    - 단순 평문 텍스트 파일 외에도 실행 권한이 있는 스크립트 파일(Python, Shell 등)을 비밀번호 소스로 지정할 수 있다.
    - 스크립트 내부에서 HashiCorp Vault, AWS Secrets Manager, CI/CD Secrets 등 외부 보안 저장소로부터 비밀번호를 동적으로 가져와 출력하도록 구성하여 보안성을 향상시킨다.

---

### 2-4) `no_log`를 활용한 실행 로그 내 Secret 노출 방지

```
Play / Role / Block / Task
    │
    │ (no_log: true 적용)
    ▼
Output & Logging System
[ Censored / Hidden Output ]
```

**`no_log` 키워드의 정의**

- Playbook 내 다양한 개체(Play, Role, Block, Task)에 설정 가능한 불리언(Boolean) 키워드
- 실행 결과 및 반환 데이터가 표준 출력(stdout)이나 시스템 로그에 노출되지 않도록 정보 공개를 제어한다.

**`no_log` 사용의 주요 이유**

- 민감한 데이터(Secret) 보호
    - 비밀번호, API 토큰, SSH 키 등의 데이터가 로그 파일이나 CI/CD 콘솔 출력에 평문으로 기록되는 것을 차단한다.
- 보조 변수 설정과의 보안 보완
    - `environment` 키워드를 통해 모듈에 환경 변수로 민감 데이터를 전달할 때, 문서상 기밀 데이터 전달 방식으로 권장되지 않으므로 `no_log: true`를 함께 사용하여 로그 출력을 감싸 보호한다.

**Ansible `no_log` 적용 수준 및 원칙**

- **Task 레벨 적용 (가장 권장)**
    - 비밀번호 설정, 토큰 발급 등 특정 민감 작업을 수행하는 단일 Task 단위로 적용하여 디버깅 편의성과 보안성을 동시에 확보한다.
- Block / Role / Play 레벨 적용
    - 해당 범주 내의 모든 Task에 일괄 적용할 수 있으나, 문제 발생 시 로그 확인이 어려워질 수 있으므로 범위 설정 시 주의가 필요하다.
- 안전성 및 예측 가능성
    - `no_log: true`가 설정되면 작업이 실패하더라도 민감한 반환 값(Return Values)이나 매개변수 데이터가 로그에 남지 않도록 보장한다.

**사용 시 유의사항**

- 디버깅의 어려움
    - 로깅을 차단하므로 작업 실패 원인을 파악하기 어렵기 때문에 디버깅 시에는 일시적으로 해제하거나 제한적인 환경에서 테스트해야 한다.
- 디버그 모드와의 관계
    - 디버거(`debugger`)나 강제 로그 출력 설정 시에도 보안 정책상 민감 정보가 숨겨지는지 확인이 필요하다.

---

### 2-5) Jenkins Credentials와 Ansible Vault 연계 방식

```
Jenkins (Master/Agent)
    │
    │ 1. credentials() / withCredentials()
    ▼
Vault Password / Key File (환경 변수 or 임시 파일)
    │
    │ 2. --vault-password-file / ANSIBLE_VAULT_PASSWORD_FILE
    ▼
Ansible Playbook Execution (Ansible Vault 암호화 해독)
```

**Jenkins Credentials**

- Credentials Binding Plugin을 통해 비밀번호, API 토큰, SSH 키, Secret File 등 다양한 형태의 기밀 정보를 중앙에서 통합 관리한다.
- 파이프라인 스크립트 내에서 `credentials()` 또는 `withCredentials` 구문을 사용해 시크릿을 선언된 범위(`environment` 또는 특정 Stage) 내로 바인딩한다.
- 주입 및 바인딩 메커니즘:
    - **Secret Text / Password**: 환경 변수로 직접 매핑되어 명령어 실행 시 즉시 참조할 수 있다.
    - **Secret File**: Secret File 타입으로 지정 시 빌드 실행 시점에 워크스페이스 내 임시 디렉터리(`.../workspace/...@tmp/secretFiles/...`)에 Vault 키 파일을 자동 생성하고 그 경로를 환경 변수에 매핑한다.
- 자동 마스킹(Secret Masking): 실행 중 빌드 콘솔 및 로그에 시크릿 값이 출력되더라도 보안 유지를 위해 `***`로 자동 마스킹 처리한다. (단, 우발적 노출을 방지하는 용도이므로 검증되지 않은 작업에 대한 권한 부여는 제한해야 한다.)

**Ansible Vault**

- 플레이북 데이터, 변수 파일, 암호화된 암호 등을 안전하게 보호하는 Ansible의 내장 암호화 기능
- `ansible-vault` 명령어를 사용하여 파일 전체 또는 개별 변수 단위로 암호화/복호화를 수행한다.
- 플레이북 실행 시 Vault 암호를 파일 경로(`-vault-password-file`)나 환경 변수(`ANSIBLE_VAULT_PASSWORD_FILE`), 명령어 인자 형태로 전달받아 실행 시점에 복호화한다.

**두 시스템의 연계 원칙**

- 보안 격리 (Separated Vault Key Management)
    - Vault 암호 자체를 Git 코드 저장소에 하드코딩하지 않고, Jenkins의 Secure Store(Credentials)에만 안전하게 보관한다.
- 동적 파이프라인 주입 (Dynamic Injection)
    - Jenkins가 파이프라인 실행 시점에만 Vault Password/Key를 임시 파일이나 환경 변수로 주입한다.
    - 실행 및 빌드가 완료되면 Jenkins가 임시 바인딩 및 파일 경로를 자동으로 제거하여 암호 유출 위험을 최소화한다.
- 최소 권한 및 유효 범위 제어 (Scoped Binding)
    - `environment` 선언 위치에 따라 시크릿 바인딩을 전체 파이프라인(Global Scope) 혹은 특정 `stage` 내부로 제한하여 최소 권한 원칙을 적용한다.
- 안전한 암호화 복호화 (Best Practices for Secret Masking)
    - Shell 실행 시 `set +x` 옵션을 적용하여 명령어가 에코되어 로그에 출력되는 것을 차단한다.
    - 워크스페이스 외부나 임시 경로(`@tmp`)에 생성된 Vault 비밀번호 파일의 접근 권한을 최소화하여 아티팩트 조회자의 암호 접근을 방지한다.

**주요 연계 사용 사례**

- 배포 파이프라인 실행 시 필요한 데이터베이스 비번, API Key 자동 주입
- 환경별(Dev/Staging/Prod)로 분리된 Vault 암호를 Jenkins Credentials에서 다르게 매핑하여 배포 자동화
- CI/CD 파이프라인 상에서 평문 민감 정보의 Git 유출 방지 및 중앙 집중식 자격 증명 관리

---

### 2-6)  HashiCorp Vault / AWS Secrets Manager 등 External Secret Manager 연동 방식 이해

```
Control Node (Ansible)
    │
    ├─ Lookup Plugin ────────► HashiCorp Vault (community.hashi_vault)
    │
    └─ Lookup Plugin ────────► AWS Secrets Manager (amazon.aws)
```

**amazon.aws (AWS Secrets Manager 연동)**

- `amazon.aws.secretsmanager_secret`
    - AWS Secrets Manager에 저장된 보안 비밀(Secrets) 정보를 조회 및 가져오기 위한 Lookup 플러그인.

**community.hashi_vault (HashiCorp Vault 연동)**

- `community.hashi_vault.hashi_vault`
    - HashiCorp Vault 서비스로부터 보안 비밀을 검색하고 조회하는 기본 Lookup 플러그인.
- `community.hashi_vault.vault_kv1_get`
    - HashiCorp Vault의 KV(Key-Value) Version 1 저장소에서 보안 비밀을 조회.
- `community.hashi_vault.vault_kv2_get`
    - HashiCorp Vault의 KV(Key-Value) Version 2 저장소에서 보안 비밀을 조회.
- `community.hashi_vault.vault_login`
    - HashiCorp Vault에 인증(Login) 수행.
- `community.hashi_vault.vault_read`
    - HashiCorp Vault 엔드포인트에 대한 Read 작업 수행.
- `community.hashi_vault.vault_write`
    - HashiCorp Vault 엔드포인트에 대한 Write 작업 수행.
- `community.hashi_vault.vault_token_create`
    - HashiCorp Vault 토큰 생성.
- `community.hashi_vault.vault_list`
    - HashiCorp Vault 데이터 목록 조회(List 작업).
- `community.hashi_vault.vault_ansible_settings`
    - 플러그인 설정 및 옵션 정보 반환.

**Ansible External Secret Manager 연동 특징 (Lookup Plugin)**

- **외부 중앙화 관리**
    - 변수 파일에 민감 정보를 직접 저장하지 않고, 중앙화된 외부 Secret Manager 시스템에서 실시간으로 보안 비밀을 불러와 활용.
- **Control Node 중심 조회**
    - Lookup 플러그인은 기본적으로 Managed Node가 아닌 **Control Node** 상에서 실행되어 외부 API와 통신하고 데이터를 가져옵니다.
- **다양한 인증 및 보안 옵션**
    - KV v1/v2, Token 생성, Login 등의 플러그인을 제공하여 HashiCorp Vault의 세부적인 기능 및 보안 동작을 맞춤형으로 제어 가능.

**Ansible External Secret Manager 연동 사용 사례**

- 외부 Secret Manager에 저장된 데이터베이스 암호 및 API 키를 런타임 시점에 유기적으로 로드
- 플레이북 코드 내 보안 민감 정보의 하드코딩 방지 및 중앙 집중식 보안 인증 관리
- 인프라 배포 시 토큰 발행, 권한 확인 등 동적 보안 워크플로우 구성

---

### 참고 문헌

- https://docs.ansible.com/projects/ansible/latest/vault_guide/vault.html
- https://docs.ansible.com/projects/ansible/latest/vault_guide/vault_encrypting_content.html
- https://docs.ansible.com/projects/ansible/latest/vault_guide/vault_using_encrypted_content.html
- https://docs.ansible.com/projects/ansible/latest/reference_appendices/playbooks_keywords.html
- https://www.jenkins.io/doc/pipeline/steps/credentials-binding/
- https://www.jenkins.io/doc/book/pipeline/jenkinsfile/
- https://docs.ansible.com/projects/ansible/latest/collections/index_lookup.html