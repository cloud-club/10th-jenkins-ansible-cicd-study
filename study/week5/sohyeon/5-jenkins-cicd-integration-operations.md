## **5. Jenkins CI/CD Integration & Operations**

---

### 5-1) Jenkins Agent에 Ansible 실행 환경 구성

```
[ Jenkins Controller ]
          │
          ├── 빌드/배포 파이프라인 제어 (Jenkinsfile 해석)
          ▼
   [ Jenkins Agent ]
          │
          ├── (1) Ansible Control Node 역할 수행 (ansible-core, Python 환경 필요)
          ├── (2) SSH/WinRM 통신을 통한 Managed Node 명령어/모듈 전달
          ▼
   [ Managed Nodes ]
    (3) Agentless 기반 원격 작업 실행 (설정 관리, 패키지 설치, 애플리케이션 배포)
```

**Jenkins Agent**

- Jenkins Controller로부터 전달받은 실제 빌드 및 배포 작업을 수행하는 인스턴스
- Ansible을 통한 인프라 자동화를 수행하기 위해 Ansible Control Node 역할을 겸임한다.

**Ansible Control Node (Agent 내 구축)**

- `ansible`, `ansible-playbook` 등의 CLI 명령어가 실행되는 주체
- Python 3.x 환경 및 `ansible-core` 패키지가 필수적으로 설치되어 있어야 한다.

**ansiblePlaybook Step (Jenkins Pipeline)**

- Jenkins의 Ansible Plugin이 제공하는 Pipeline DSL 스텝
- Agent 내에 설치된 Ansible CLI를 호출하며, Jenkins Credential과 인벤토리 정보를 파이프라인 코드 레벨에서 선언적으로 전달한다.

**Jenkins Agent 내 Ansible 환경 구성 원칙**

- **Control Node 조건 충족**
    - Ansible의 Agentless 특성에 따라 Managed Node에는 아무것도 설치할 필요가 없지만, 작업을 명령할 Jenkins Agent 노드 자체는 반드시 Control Node의 요구사항(Python, CLI)을 충족해야 한다.
- **SSH Credentials 바인딩 및 보안 관리**
    - Managed Node에 접근하기 위한 SSH Private Key를 Agent disk에 파일 형태로 하드코딩하지 않고, Jenkins의 `credentialsId`를 통해 실행 시점에만 메모리에 안전하게 바인딩한다.
- **`PATH` 환경변수 식별 및 실행 격리**
    - Agent 시스템 내 `pip` 등으로 설치된 Ansible CLI 바이너리 경로(`~/.local/bin` 등)가 Jenkins Agent 실행 세션의 `PATH`에 올바르게 포함되어야 `ansible-playbook: command not found` 오류를 방지할 수 있다.

**Jenkins Agent + Ansible 구성 핵심 파라미터 (`ansiblePlaybook`)**

- `playbook`: Agent 워크스페이스 내에서 실행할 YAML 플레이북 파일 경로
- `inventory`: 대상 Managed Node 목록이 정의된 인벤토리 파일 경로 (또는 동적 인벤토리)
- `credentialsId`: Managed Node SSH 접속을 위해 Jenkins에 미리 등록된 SSH User Private Key ID
- `colorized`: Jenkins 빌드 콘솔 출력 시 Ansible 실행 로그의 색상 구분 여부 (`true`/`false`)

**구성 및 실행 예시 (Jenkinsfile)**

```
pipeline {
    agent { label 'ansible-agent' } // Ansible이 설치된 Jenkins Agent 지정
    stages {
        stage('Deploy via Ansible') {
            steps {
                // Jenkins Agent(Control Node)에서 Managed Node로 작업 전송
                ansiblePlaybook(
                    playbook: 'deploy.yml',
                    inventory: 'inventories/production',
                    credentialsId: 'managed-node-ssh-key',
                    colorized: true
                )
            }
        }
    }
}
```

---

### 5-2) Jenkins Credentials를 활용한 SSH Key 및 Vault Secret 전달

```
Jenkins Controller / Agent
    │
    │ withCredentials (Credentials Binding)
    ▼
Environment Variables ($SSH_KEY, $VAULT_SECRET 등)
    │
    │ SSH / API Request
    ▼
Target Node / Remote Service
```

**Credentials Binding Plugin**

- Jenkins 파이프라인 단계에서 안전하게 보안 자격 증명(Secrets)을 환경 변수로 바인딩하는 플러그인
- `withCredentials` 블록을 활용해 보안 정보를 코드에 노출하지 않고 선언적으로 사용한다.

**SSH Key 전달 (`sshUserPrivateKey`, `vaultSSHUserPrivateKey`)**

- 원격 서버 접속 또는 Git 저장소 인증을 위한 SSH 개인 키 자격 증명
- SSH Key를 변수로 바인딩하여 안전하게 SSH 명령어 및 원격 제어 스크립트에 전달한다.

**Vault Secret 전달 (`vaultString`, `vaultFile`, `vaultTokenCredentialBinding` 등)**

- HashiCorp Vault 및 인증 시스템과 연동되는 비밀번호, 토큰, 파일 형태의 Secret 정보
- 파이프라인 실행 시점에 비밀 값을 동적으로 불러와 환경 변수에 할당한다.

**Jenkins Credentials 활용의 원칙**

- **보안성 및 로그 마스킹 (Secrets Masking)**
    - 파이프라인 빌드 로그 출력 시 비밀 값은 `***` 형태로 자동 마스킹되어 민감한 정보의 유출을 방지한다.
    - `set +x` (Linux) 또는 `@echo off` (Windows)를 사용하여 명령어 쉘 로깅 시 비밀 값이 노출되는 것을 차단한다.
- **안전한 변수 확장 (Variable Interpolation Security)**
    - Groovy의 쌍따옴표(`""`) 대신 작은따옴표(`''`)를 사용해 쉘의 환경 변수로 직접 확장되도록 구성한다.
    - Groovy 보간법을 직접 사용할 경우 프로세스 목록 등에 비밀 값이 노출될 수 있다.
- **작업 공간 보안 (Workspace Isolation)**
    - Secret File 바인딩 시 파일이 `$WORKSPACE` 내부 하위 디렉토리에 위치하지 않도록 관리하여 타 사용자의 무단 접근을 방지한다.

**Jenkins Credentials의 사용 사례**

- SSH Key를 활용한 원격 배포 서버 접속 및 명령 실행
- HashiCorp Vault 연동을 통한 API 토큰 및 데이터베이스 접속 정보 수급
- CI/CD 파이프라인 내 외부 서비스 인증 및 보안 파일 전달

**Ansible 실행 시 전달 방식 (Ansible Integration)**

```
Jenkins (withCredentials)
    │
    │ $SSH_KEY_PATH / $ANSIBLE_VAULT_PASS
    ▼
ansible-playbook 실행
    │
    ├─ SSH Key 전달 ──> Managed Node 접속 (--private-key)
    └─ Vault Secret 전달 ──> 변수 복호화 및 적용 (ANSIBLE_VAULT_PASSWORD_FILE)
```

**Ansible 연동을 위한 자격 증명 주입 방식**

- 개발자가 코드(GitHub)나 로그에 서버 비밀번호/SSH 키를 노출하지 않고, Jenkins가 안전하게 열쇠를 쥐고 있다가 필요할 때만 Ansible에게 잠깐 빌려주어 원격 서버를 자동 배포하는 과정
- **SSH Key 주입 (`-private-key` / `ansible_ssh_private_key_file`)**
    - `sshUserPrivateKey`로 바인딩된 SSH Key 파일 경로를 `ansible-playbook -i inventory site.yml --private-key=$SSH_KEY_PATH` 형태로 전달한다.
    - 이를 통해 Ansible이 대상 서버(Managed Node)에 별도의 프로그램 설치 없이 안전하게 접속하여 제어할 수 있습니다.
- **Ansible Vault 비밀번호 주입 (`ANSIBLE_VAULT_PASSWORD_FILE`)**
    - Jenkins Secret Text/File로 보관된 Vault 암호를 `ANSIBLE_VAULT_PASSWORD_FILE` 환경 변수로 주입한다.
    - 파이프라인 실행 중에만 Ansible이 암호화된 변수 파일(`vars/vault.yml`)을 동적으로 복호화하여 플레이북에 적용한다.
- **Extra Vars 전달 (`-extra-vars`)**
    - `vaultString`으로 불러온 단일 Secret 값을 `ansible-playbook --extra-vars "db_password=$DB_PASS"` 형식으로 플레이북 실행 시점에 직접 주입한다.

**Ansible 연동 시 보안 원칙**

- **이중 로그 마스킹 (`no_log: true`)**
    - Jenkins 레벨에서의 빌드 로그 마스킹 외에도, Ansible 플레이북 태스크에 `no_log: true`를 지정하여 execution 로그나 디버그 출력에 비밀 값이 남는 것을 방지한다.
- **작업 완료 후 임시 자격 증명 제거**
    - `withCredentials` 블록 범위가 종료되면 Jenkins가 생성한 임시 SSH 키 파일이나 비밀번호 파일은 자동으로 삭제되어 노출 위험을 최소화한다.

---

### 5-3) Declarative Pipeline에서 `ansible-playbook` CLI 실행

```
Jenkins Controller / Agent (Control Node)
    │
    │ sh / bat Step (ansible-playbook 실행)
    │ SSH
    ▼
Target Servers (Managed Nodes)
```

**Jenkins 내 Control Node 역할**

- Jenkins Agent(또는 Controller)가 Ansible Control Node 역할을 겸하여 ansible-playbook CLI 명령을 수행한다.
- Pipeline의 `steps` 블록 내에서 셸 명령어 실행 스텝(`sh` 또는 `bat`)을 통해 Ansible CLI를 직접 호출한다.

**Declarative Pipeline에서의 실행 방식**

- **`sh` / `bat` Step 활용**
    - Declarative Pipeline의 `stage` 내 `steps` 구문에서 `sh 'ansible-playbook ...'` 형태의 CLI 스크립트를 작성하여 자동화를 수행한다.
- **환경 변수 및 자격 증명(Credentials) 바인딩**
    - `environment` 지시어를 사용하여 SSH 키, 접속 계정 정보, 인벤토리 파일 경로 등을 안전하게 정의하고 파이프라인 전역 또는 특정 스테이지에 주입한다.
    - `credentials()` 헬퍼 메서드를 사용해 Jenkins에 저장된 Secret Text나 SSH Private Key를 파이프라인 안전하게 가져와 `ansible-playbook` 명령어 옵션으로 전달한다.

**핵심 특징 및 구성 원칙**

- **Agentless 기반의 CI/CD 연동**
    - 타겟 서버(Managed Node)에 별도의 Jenkins Agent나 추가 수신 프로그램을 설치할 필요 없이, Jenkins에서 SSH 통신을 통해 직접 배포 및 환경 구성을 제어한다.
- **Declarative 구조의 명확성 (Simplicity)**
    - Jenkins의 가독성 높은 Declarative Syntax와 Ansible의 YAML 기반 플레이북이 결합되어 전체 CI/CD 파이프라인의 흐름을 직관적으로 파악할 수 있다.
- **실패 처리 및 후속 작업 (Post Handling)**
    - ansible-playbook 실행 결과에 따라 발생한 성공/실패 여부를 Jenkins의 `post` 블록(`success`, `failure`, `always` 등)을 통해 감지하고 알림 전송이나 후속 정리를 수행한다.
- **멱등성(Idempotence)을 통한 안전한 배포**
    - 동일한 Pipeline을 여러 번 실행하더라도 Ansible 플레이북의 멱등성 원칙 덕분에 변경이 필요한 부분만 적용되어 안정적인 지속적 배포(CD)가 가능하다.

**주요 활용 사례**

- Jenkins 빌드/테스트 완료 후 타겟 서버로의 자동 애플리케이션 배포
- CI/CD 파이프라인 내에서 배포 대상 서버의 상태/환경 구성(Configuration Management) 자동화
- 롤링 업데이트 스크립트를 실행하여 무중단 배포 워크플로우 구성

---

### 5-4) Jenkins Parameter와 Ansible `-limit`, `tags`, Extra Variables(`e`) 연계

**Jenkins Parameters 지시어**

- Jenkins 파이프라인 실행 시 사용자로부터 빌드 변수를 입력받기 위해 `parameters` 지시어를 정의한다.
- 파이프라인 내 `params.변수명` 또는 환경 변수 형태 (`$변수명`)로 접근하여 스크립트에 전달한다.

**Ansible 옵션 연계 요소**

```yaml
# [예시 1] Jenkins 파라미터($TARGET_HOST)로 넘겨받은 특정 그룹(web_servers)만 실행
ansible-playbook -i inventory.ini site.yml --limit "web_servers"

# [예시 2] 특정 단일 호스트(web01.example.com) 지정
ansible-playbook -i inventory.ini site.yml -l "web01.example.com"

# [예시 3] Jenkins Shell Step 내 연계 패턴
ansible-playbook -i inventory.ini site.yml --limit "${params.TARGET_HOST}"
```

- **`limit` (호스트 대상 제한)**
    - Inventory에 등록된 전체 대상 중 특정 호스트나 그룹만 선택하여 플레이북을 실행한다.
    - Jenkins의 `string` 또는 `choice` 파라미터로 실행 대상을 동적으로 제어할 때 사용한다.
- **`-tags` (특정 태그 Task 실행)**
    - 플레이북 내부 Task에 지정된 특정 `tags`만 골라 실행하거나 제외한다.
    - 전체 인프라 재배포 없이 특정 서비스 업데이트나 Config 변경 작업만 선택하여 수행할 수 있다.
- **`e` / `-extra-vars` (추가 변수 전달)**
    - 플레이북 내부 변수(Vars)의 우선순위를 덮어쓰고, 외부에서 동적으로 값을 주입한다.
    - Jenkins 빌드 번호, 배포 버전을 전달하거나 JSON/Key=Value 형태로 다양한 파라미터를 넘길 때 활용한다.

**파이프라인 연계의 특징**

- **파이프라인 가형성 및 유연성 향상**
    - 동일한 Ansible Playbook 코드라도 Jenkins 파라미터 조합에 따라 다목적(특정 서버 배포, 특정 롤백, 특정 모듈만 실행)으로 재사용이 가능하다.
- **실무 중심의 제어 매커니즘**
    - 파라미터 조건 처리를 통해 운영 환경(Prod, Stage, Dev)이나 특정 타겟 대상에만 안전하게 변경 사항을 적용할 수 있다.

**주요 사용 사례**

- 특정 관리 대상 호스트만 선택하여 핀포인트 배포 수행 (`limit`)
- 정기 점검 또는 특정 구성 요소(예: Nginx, DB)의 설정을 부분적으로 업데이트 (`-tags`)
- Jenkins에서 빌드된 애플리케이션의 버전을 Ansible 플레이북으로 전달하여 동적 배포 (`e`)

---

### 5-5) Jenkins Ansible Plugin 및 `ansiblePlaybook` Step 활용 방식 비교

**Jenkins Ansible Plugin**

- Jenkins 빌드 스텝 및 Pipeline 내에서 Ansible 작업(Playbook, Ad-hoc, Vault 등)을 실행할 수 있도록 지원하는 플러그인.
- Jenkins의 Global Tool Configuration 기능을 통해 여러 버전의 Ansible 실행 파일을 등록 및 관리 가능.

**Shell Script (`sh` Step) 직접 실행 방식**

- 작동 방식
    - Pipeline의 `sh` 스텝을 통해 `ansible-playbook` CLI 명령어를 직접 호출.
- 장점
    - 별도의 Jenkins 플러그인 설치 없이 즉시 적용 가능.
    - Ansible CLI의 모든 옵션과 파라미터를 그대로 활용 가능.
- 단점 및 한계
    - SSH Key, Vault Password 등 Jenkins Credentials를 사용하려면 `withCredentials` 블록과 CLI 옵션(`-private-key`, `-vault-password-file` 등)을 직접 매핑해야 함.
    - 로그의 ANSI Color 출력을 처리하기 위해 추가적인 Wrapper 설정 필요.
    - 파이프라인 코드가 길어지고 CLI 명령어 구문 관리가 복잡해짐.

**`ansiblePlaybook` Step 활용 방식 (Ansible Plugin)**

- 작동 방식
    - Jenkins Pipeline DSL에서 제공하는 `ansiblePlaybook` Step 선언을 통해 Playbook 실행.
- 주요 특징 및 제공 기능
    - **Credentials 통합 관리**: `credentialsId` 및 `vaultCredentialsId` 파라미터를 통해 Jenkins 자격 증명 저장소와 바로 연동.
    - **인벤토리 유연성**: 인벤토리 파일 경로(`inventory`) 지정 외에도 인라인 인벤토리(`inventoryContent`) 지원.
    - **로그 파이프라인 연동**: `colorized: true` 옵션과 AnsiColor plugin 연동을 통해 가독성 높은 ANSI 컬러 로그 출력 지원.
    - **환경 변수 자동 주입**: Jenkins의 빌드 환경 변수(`BUILD_TAG` 등)가 Ansible 내 `lookup('env', ...)`을 통해 플레이북으로 전달됨.
    - **추가 파라미터 전달**: `extraVars` 및 `extras` 파라미터로 가변 변수 및 CLI 추가 옵션 정의 가능.

**`ansiblePlaybook` Step 주요 설정 파라미터**

- **`playbook`**: 실행할 Playbook 파일 경로 (필수 항목).
- **`inventory` / `inventoryContent`**: 인벤토리 파일 경로 또는 직접 작성한 인라인 인벤토리 내용.
- **`credentialsId`**: SSH 접속용 Jenkins Credential ID.
- **`vaultCredentialsId`**: Ansible Vault 복호화용 Secret Text / File Credential ID.
- **`extraVars`**: Playbook에 전달할 추가 변수 (Map 형태로 제공 및 로그 내 민감 정보 마스킹 지원).
- **`colorized`**: 콘솔 로그 컬러 출력 여부.

**파이프라인 작성 예시 (Declarative Pipeline)**

```
pipeline {
    agent any
    options {
        // ANSI Color 출력을 위한 wrap 설정
        ansiColor('xterm')
    }
    stages {
        stage('Deploy with Ansible') {
            steps {
                ansiblePlaybook(
                    playbook: 'deploy.yml',
                    inventory: 'inventories/production/hosts',
                    credentialsId: 'ssh-private-key-id',
                    vaultCredentialsId: 'ansible-vault-secret-id',
                    colorized: true,
                    extraVars: [
                        target_env: 'production',
                        app_version: "${env.BUILD_NUMBER}"
                    ]
                )
            }
        }
    }
}
```

**도입 효과 및 결론**

- **인프라/배포 보안성 강화**: SSH Key 및 Vault Secret 등의 자격 증명이 Script에 노출되지 않고 Jenkins Credentials Store를 통해 안전하게 주입됨.
- **파이프라인 가독성 및 유지보수성 향상**: 긴 Shell 명령어 대신 구조화된 DSL 파라미터 형태로 작성하여 CI/CD 파이프라인 표준화 가능.
- **운영 편의성 증가**: 빌드 로그의 ANSI Color 가독성 확보 및 Jenkins 환경 변수의 자연스러운 전달로 디버깅 및 가시성 제공.

---

### 5-6) `ansible-lint`를 활용한 정적 분석 및 Playbook 품질 관리

**Ansible Lint**

- Playbook, Role, Collection을 대상으로 정적 분석을 수행하는 커맨드라인 도구 (CLI Tool)
- 모든 Ansible 사용자를 대상으로 코드의 모범 사례 적용과 품질 관리를 지원한다.

**주요 기능 및 목표**

- **Proven Practices 검증**: 검증된 모범 사례와 디자인 패턴, 동작 방식을 적용하도록 권장한다.
- **잠재적 버그 예방**: 버그로 이어지거나 코드 유지보수를 어렵게 만드는 흔한 실수를 방지한다.
- **Ansible 버전 업그레이드 지원**: 최신 버전의 Ansible과 호환되도록 코드를 개선하는 데 도움을 준다.
- **품질 점수 산출**: Ansible Galaxy Hub에 기여하는 콘텐츠의 품질 점수(Quality Score)를 측정하는 데 활용된다.

**Ansible Lint의 특징**

- **주관적 규칙(Opinionated) 제공**: 커뮤니티의 기여로 만들어진 가이드라인과 주관적인 규칙 세트를 기본 제공한다.
- **유연한 규칙 제어**: 사용자의 필요에 따라 특정 규칙을 개별적 또는 카테고리별로 비활성화할 수 있다.
- **미공개 코드의 문서화 관리**: `galaxy.yml`이나 `meta.yml`의 `galaxy_info` 세션을 점검하여, 공유되지 않는 자체 역할/컬렉션에 대해서도 문서화 및 유지보수성을 향상시킨다.
- **커뮤니티 중심 개발**: 다른 Ansible 팀들과의 협력을 바탕으로 커뮤니티 주도로 지속적으로 개발 및 관리된다.

**권장 사용 방식**

- 프로덕션 환경의 Ansible 버전이 낮추어져 있더라도, 정적 분석 시에는 가장 최신의 Ansible 버전과 함께 `ansible-lint`를 사용하는 것이 권장된다.

**사용 사례**

- Playbook 작성 과정에서의 실시간 구문 및 모범 사례 검증
- CI/CD 파이프라인 연동을 통한 Playbook 품질 자동 점검
- Ansible 버전을 상위 버전으로 올리기 위한 사전 코드 호환성 검사
- Galaxy Hub 또는 사내 공유용 Role/Collection의 정적 품질 평가

---

### 5-7) `forks`, SSH Pipelining 등 기본적인 Ansible 성능 최적화

**Forks (동시 실행 병렬 처리 수)**

- Ansible이 Managed Node들에 동시에 명령을 수행할 수 있는 병렬 프로세스(작업 세션) 수이다.
- 기본값(Default)은 5로 설정되어 있어, 한 번에 최대 5개의 호스트에만 동시에 작업을 수행한다.
- 호스트 수가 많거나 Control Node의 리소스(CPU, Memory, Network)가 충분할 경우, `ansible.cfg` 파일의 `forks` 옵션 값을 늘려 전체 실행 시간을 단축할 수 있다.

**SSH Pipelining (파이프라이닝 최적화)**

- ANSIBLE_PIPELINING을 활성화하여 모듈 실행을 위한 네트워크 작업(파일 전송) 횟수를 줄이는 기능이다.
- 기본적으로 Ansible은 모듈을 임시 파이썬 파일로 만들어 Managed Node로 복사(SCP/SFTP)한 후 실행하지만, Pipelining을 켜면 파일 전송 없이 SSH 세션 스트림을 통해 파이썬 모듈을 직접 실행한다.
- 네트워크 오버헤드가 줄어들어 전체 플레이북 실행 속도가 크게 향상된다.
- 주의사항: `sudo`와 같은 권한 상승(privilege escalation) 사용 시 Managed Node의 `/etc/sudoers` 파일에 `requiretty` 설정이 해제되어 있어야 정상 동작한다.

**Fact Gathering 최적화 (Fact Caching)**

- 플레이북 실행 시 기본적으로 수행되는 `gathering facts` 작업을 제어하거나 캐싱하여 속도를 개선한다.
- 매번 시스템 정보를 수집하지 않도록 `gathering = smart` 또는 `explicit`으로 설정하고, CACHE_PLUGIN (Redis, JSON, Memcached 등)을 활용해 Fact 정보를 메모리나 파일에 저장하여 재사용할 수 있다.

**SSH Connection Reuse (ControlMaster / ControlPersist)**

- OpenSSH의 ControlMaster 및 ControlPersist 기능을 활용해 SSH 커넥션을 재사용한다.
- 매 작업마다 SSH 연결을 끊고 다시 맺는 과정을 생략하고, 한 번 맺은 SSH 연결(소켓)을 계속 유지하여 커넥션 핸드셰이크 비용을 단축한다.

**Ansible 성능 최적화의 원칙**

- **병렬성 극대화 (Scalability)**
    - 타겟 인프라의 규모와 Control Node의 사양에 맞게 `forks`를 적절히 조절하여 병렬 처리 능력을 향상시킨다.
- **네트워크 오버헤드 최소화 (Efficiency)**
    - SSH Pipelining 및 Connection Reuse를 적용하여 파일 전송 및 반복적인 SSH 연결 요청 체인을 제거한다.
- **불필요한 작업 스킵 (Optimization)**
    - Fact 수집 단계를 줄이거나 Caching을 적용하여 플레이북 실행 초기 지연을 방지한다.

**성능 최적화 주요 사용 사례**

- 대규모 호스트(수백~수천 대) 대상 플레이북 배포 시간 단축
- 네트워크 지연(Latency)이 높은 환경에서의 자동화 수행 속도 개선
- 빈번하게 실행되는 CI/CD 파이프라인의 Ansible 빌드 타임 절감

---

### 5-8) 참고 문헌

- https://docs.ansible.com/projects/ansible/latest/installation_guide/intro_installation.html
- https://www.jenkins.io/doc/pipeline/steps/ansible/
- https://www.jenkins.io/doc/pipeline/steps/credentials-binding/
- https://www.jenkins.io/doc/book/pipeline/syntax/
- https://www.jenkins.io/doc/book/pipeline/syntax/
- https://plugins.jenkins.io/ansible/
- https://docs.ansible.com/projects/lint/
- https://docs.ansible.com/projects/ansible/latest/reference_appendices/config.html