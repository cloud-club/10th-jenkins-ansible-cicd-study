# 05-Jenkins-CI/CD-Integration-&-Operations

## 5. Jenkins와 Ansible을 왜 연결할까?

---

Ansible을 사람이 직접 실행하면 자동화 스크립트는 있어도 **배포 실행 자체는 수동**이다.

Jenkins와 연결하면 Build Artifact가 준비된 뒤 정해진 Parameter와 Credentials를 이용해 Ansible Playbook을 실행하고, 배포 결과를 Pipeline으로 관리할 수 있다.

```
Git Push / Manual Trigger
        ↓
Jenkins Pipeline
        ↓
Build / Test
        ↓
Artifact 생성
        ↓
ansible-lint
        ↓
ansible-playbook
        ↓
Rolling Deployment
        ↓
Health Check
```

### 5-1. Jenkins Agent의 실행 환경

---

`ansible-playbook`은 **실제로 Pipeline Stage가 실행되는 Jenkins 실행 노드**에 설치되어 있어야 한다. 운영에서는 Controller에 배포 도구를 얹기보다 전용 Agent에서 실행하는 구성이 일반적으로 관리하기 쉽다.

필요 항목 예:

- Python
- `ansible-core`
- 프로젝트에서 사용하는 Collection / Role
- SSH Client
- Managed Node로 연결 가능한 Network Route
- 필요한 Credentials 접근 권한

설치 확인:

```bash
python3 --version
ansible --version
ansible-playbook --version
ansible-galaxy --version
```

의존성 설치:

```bash
ansible-galaxy install -r requirements.yml
```

<aside>
🤔

배포 Agent를 고정 VM으로 둘 수도 있고, Ansible 실행 환경이 포함된 Container Image를 사용해 실행 환경 자체를 재현 가능하게 만들 수도 있다.

</aside>

### 5-2. Jenkins Credentials

---

대표적으로 다음 Credential이 필요하다.

- Managed Node 접속용 **SSH Private Key**
- Ansible Vault 복호화용 **Vault Password**
- 외부 Secret Manager / Cloud API 접근 Credential
- Artifact Repository Credential

구조:

```
Jenkins Credentials
   │
   ├── SSH Key
   ├── Vault Password
   └── Cloud Credential
           │
           ▼
      Jenkins Agent
           │
           ▼
     ansible-playbook
```

Secret을 Jenkinsfile에 직접 문자열로 작성하지 않는다.

### 5-3. Declarative Pipeline에서 CLI 실행

---

가장 명확한 방식은 Jenkins에서 `ansible-playbook` CLI를 직접 실행하는 것이다.

```groovy
pipeline {
    agent { label 'ansible' }

    parameters {
        choice(name: 'ENV', choices: ['dev', 'prod'])
        string(name: 'TARGET', defaultValue: 'app')
        string(name: 'APP_VERSION', defaultValue: '')
    }

    stages {
        stage('Install Dependencies') {
            steps {
                sh 'ansible-galaxy install -r requirements.yml'
            }
        }

        stage('Lint') {
            steps {
                sh 'ansible-lint playbooks/deploy.yml'
            }
        }

        stage('Deploy') {
            steps {
                withCredentials([
                    sshUserPrivateKey(
                        credentialsId: 'ansible-ssh-key',
                        keyFileVariable: 'SSH_KEY',
                        usernameVariable: 'SSH_USER'
                    ),
                    string(
                        credentialsId: 'ansible-vault-password',
                        variable: 'VAULT_PASS'
                    )
                ]) {
                    sh '''
                        set +x
                        printf '%s' "$VAULT_PASS" > .vault-pass
                        chmod 600 .vault-pass

                        ansible-playbook playbooks/deploy.yml                           -i inventories/$ENV/hosts.yml                           --limit "$TARGET"                           --user "$SSH_USER"                           --private-key "$SSH_KEY"                           --vault-password-file .vault-pass                           -e "app_version=$APP_VERSION"

                        rm -f .vault-pass
                    '''
                }
            }
        }
    }

    post {
        always {
            sh 'rm -f .vault-pass || true'
        }
    }
}
```

운영에서는 Parameter Validation과 승인 절차도 함께 고려한다.

### 5-4. Jenkins Parameter와 Ansible 옵션 연결

---

Jenkins Parameter를 Ansible 실행 범위에 연결할 수 있다.

| Jenkins Parameter | Ansible | 역할 |
| --- | --- | --- |
| ENV | `-i inventories/$ENV/hosts.yml` | 환경 선택 |
| TARGET | `--limit` | 대상 Host/Group 제한 |
| TAGS | `--tags` | 실행 Task 범위 제한 |
| APP_VERSION | `-e` | 배포 Artifact 버전 전달 |

예:

```bash
ansible-playbook playbooks/deploy.yml   -i inventories/prod/hosts.yml   --limit app01   --tags deploy   -e "app_version=1.4.2"
```

<aside>
⚠️

Extra Variables(`-e`)는 Variable 우선순위가 매우 높다. 또한 Secret을 CLI 문자열로 직접 넘기면 Process Argument나 Log에 노출될 수 있으므로 일반 배포 값과 Secret 전달 방식을 구분해야 한다.

</aside>

### 5-5. CLI vs Jenkins Ansible Plugin

---

Jenkins Ansible Plugin은 Pipeline에서 `ansiblePlaybook` Step을 사용할 수 있게 한다.

개념 예시:

```groovy
ansiblePlaybook(
    playbook: 'playbooks/deploy.yml',
    inventory: 'inventories/prod/hosts.yml',
    credentialsId: 'ansible-ssh-key',
    vaultCredentialsId: 'ansible-vault-password',
    forks: 10
)
```

| 구분 | CLI 직접 실행 | Ansible Plugin |
| --- | --- | --- |
| 장점 | 동작이 명확하고 Jenkins 외 환경에서도 동일 | Credentials와 주요 옵션을 Step으로 표현 |
| 단점 | Credential File 처리 등을 직접 구성 | Plugin 버전과 제공 옵션에 의존 |
| 적합한 경우 | 재현성과 CLI 중심 운영 | Jenkins 중심으로 단순한 통합을 원할 때 |

둘 중 하나가 무조건 정답이라기보다 **팀이 운영하기 쉬운 실행 경계**를 선택하면 된다.

### 5-6. ansible-lint

---

`ansible-lint`는 Playbook과 Role의 품질 문제를 정적으로 검사한다.

로컬 실행:

```bash
ansible-lint
```

Pipeline에서는 실제 배포 전에 실행한다.

```groovy
stage('Ansible Lint') {
    steps {
        sh 'ansible-lint'
    }
}
```

배포 전에 다음 흐름으로 묶으면 좋다.

```
YAML / Syntax Check
       ↓
ansible-lint
       ↓
--check / --diff
       ↓
Canary
       ↓
Rolling Deployment
```

### 5-7. forks와 SSH Pipelining

---

Host 수가 많아지면 Ansible 실행 시간도 중요해진다.

```
# ansible.cfg
[defaults]
forks = 20

[ssh_connection]
pipelining = True
```

- **forks**: 동시 실행 가능한 Host 수 증가
- **pipelining**: SSH 연결 과정에서 불필요한 파일 전송/명령 단계를 줄여 실행 비용을 낮출 수 있음

다만 성능 옵션은 운영 환경의 SSH, `become`, 보안 정책과 함께 검증해야 한다.

<aside>
🔐

성능 때문에 Host Key Checking을 무조건 비활성화하는 방식은 운영 보안 정책과 충돌할 수 있다. 성능 최적화와 SSH 신뢰 모델은 별도로 설계한다.

</aside>

### 5-8. 배포 Pipeline 권장 흐름

---

```
Checkout
   ↓
Build / Unit Test
   ↓
Artifact Publish
   ↓
Install Role / Collection Dependencies
   ↓
ansible-lint
   ↓
Syntax Check
   ↓
Target 확인
   ↓
Canary Deployment
   ↓
Health Check
   ↓
Rolling Deployment
   ↓
Post Deployment Verification
```

### 5-9. 실습

---

- [ ]  Jenkins Agent에 Ansible 설치
- [ ]  `requirements.yml` 의존성 설치 Stage 추가
- [ ]  SSH Private Key를 Jenkins Credentials에 등록
- [ ]  Vault Password를 Jenkins Credentials에 등록
- [ ]  Declarative Pipeline에서 `ansible-playbook` 실행
- [ ]  ENV / TARGET / APP_VERSION Parameter 추가
- [ ]  `--limit`, `--tags`, `-e`와 Parameter 연결
- [ ]  `ansible-lint` Stage 추가
- [ ]  DEV에서 Canary → Rolling Deployment 실행
- [ ]  실패 시 Jenkins Build 상태가 실패로 종료되는지 확인

### 5-10. 운영 체크리스트

---

- [ ]  Jenkins Agent의 Ansible 버전이 관리되고 있는가?
- [ ]  Role/Collection 의존성이 `requirements.yml`로 고정되어 있는가?
- [ ]  SSH Key와 Vault Password가 Jenkins Credentials에 있는가?
- [ ]  Secret이 Jenkinsfile이나 Console Log에 노출되지 않는가?
- [ ]  PROD Inventory가 DEV와 분리되어 있는가?
- [ ]  `--limit` 대상이 의도한 Host인지 확인하는 단계가 있는가?
- [ ]  배포 전에 Lint/Syntax Check가 실행되는가?
- [ ]  Canary와 Health Check 이후 전체 배포가 진행되는가?
- [ ]  Ansible 실패가 Jenkins Pipeline 실패로 전파되는가?
- [ ]  실패 시 Rollback 또는 재실행 절차가 정의되어 있는가?

### 5-11. 여기서 생각해볼 질문

---

1. Ansible을 Jenkins Controller보다 Agent에서 실행하는 이유는?
2. CLI 방식과 Jenkins Ansible Plugin 방식은 어떤 차이가 있는가?
3. Jenkins Parameter를 `--limit`에 연결할 때 어떤 Validation이 필요할까?
4. `-e`로 Secret을 전달하지 않는 것이 좋은 이유는?
5. `forks` 값을 크게 할수록 항상 배포가 빨라지지는 않는 이유는?

### 5-12. 참고 자료

---

- [Jenkins Ansible Plugin](https://plugins.jenkins.io/ansible/)
- [Jenkins 공식 문서 - Credentials](https://www.jenkins.io/doc/book/using/using-credentials/)
- [Ansible 공식 문서 - Strategies and forks](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_strategies.html)
- [ansible-lint 공식 문서](https://ansible.readthedocs.io/projects/lint/latest/)
- [Ansible 공식 문서 - Sample Setup](https://docs.ansible.com/projects/ansible/latest/tips_tricks/sample_setup.html)