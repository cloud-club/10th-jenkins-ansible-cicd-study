# Jenkins CI/CD와 Ansible 운영

> 한 줄 요약: Jenkins Agent는 Ansible을 실행하는 컨트롤 노드가 되고, Jenkins Credentials는 실행 중에만 SSH Key와 Vault 비밀번호를 제공한다. Pipeline은 검증을 먼저 통과한 뒤 제한된 대상에 배포해야 한다.

## 1. Jenkins와 Ansible의 역할

```text
Git 저장소
  ↓ checkout
Jenkins Controller
  ↓ Job을 실행할 Agent 할당
Jenkins Agent
  ├─ ansible-playbook 실행 (Ansible Control Node 역할)
  ├─ Jenkins Credentials에서 SSH Key / Vault 비밀번호를 임시 주입
  └─ SSH로 대상 서버에 연결
       ↓
  app01, app02, app03 ...
```

Jenkins Controller는 Pipeline을 관리하고 Agent에 작업을 할당한다. 실제 `ansible-playbook`은 **Jenkins Agent에서** 실행하므로, Agent에 Ansible 실행 환경과 네트워크 접근 권한이 있어야 한다.

## 2. Jenkins Agent에 준비할 것

Agent에는 다음이 필요하다.

- Python과 Ansible Core (`ansible-playbook`, `ansible-galaxy`)
- `ansible-lint`
- SSH client와 `ssh-agent` (`sshagent` Step을 쓸 경우)
- Git
- 대상 서버 및 필요한 API·Load Balancer에 연결할 네트워크 경로
- Playbook이 요구하는 Collection과 Python 라이브러리

### 실행 환경을 같게 유지하는 방법

Jenkins Agent가 여러 대인데 Agent마다 설치된 Ansible 버전이 다르면, 같은 Jenkinsfile도 실행하는 Agent에 따라 결과가 달라질 수 있다.

```text
Agent A: ansible-core 2.17
Agent B: ansible-core 2.19
→ 같은 Playbook이라도 모듈 동작·lint 결과가 달라질 수 있음
```

그래서 모든 Agent가 같은 버전의 Ansible·`ansible-lint`·Collection을 사용하도록 정해 둔다. 대표적인 방법은 다음과 같다.

| 방식 | 실제 의미 | 장단점 |
|---|---|---|
| Jenkins 전용 VM | Ansible 배포용 가상 머신을 만들고, 그 VM에 정한 버전의 도구만 설치해 Jenkins Agent로 사용 | 이해하기 쉽지만 VM의 도구 업데이트를 관리해야 함 |
| 컨테이너 Agent | Ansible과 lint가 미리 설치된 Docker 이미지를 만들고, 매 Build마다 그 이미지 안에서 실행 | 항상 같은 환경에서 실행되지만 Docker·Kubernetes 같은 컨테이너 실행 환경이 필요 |


프로젝트에는 필요한 Collection을 `requirements.yml`에 선언하고 Pipeline 초반에 설치한다.

```groovy
stage('Install Ansible dependencies') {
  steps {
    dir('study/week5/doyeon') {
      sh 'ansible-galaxy collection install -r requirements.yml'
    }
  }
}
```

운영에서는 `ansible-core`, `ansible-lint`, Collection 버전을 고정하고, Agent 이미지 변경은 별도 검증 후 반영한다.

---

## 3. Credentials: SSH Key와 Vault 비밀번호

비밀값은 Git·Jenkinsfile·로그에 평문으로 저장하지 않는다. Jenkins Credentials에 저장하고 Pipeline 실행 범위 안에서만 사용한다.

| 용도 | Jenkins Credential 종류 | Pipeline에서 사용하는 방법 |
|---|---|---|
| 대상 서버 SSH 접속 | SSH Username with private key | `sshagent(credentials: [...])` |
| Ansible Vault 비밀번호 | Secret file | `withCredentials([file(...)])` |
| API 토큰 | Secret text | `withCredentials([string(...)])` |

### SSH Key: `sshagent`

`sshagent`는 지정한 SSH private key를 실행 블록 동안 `ssh-agent`에 올린다. `ansible-playbook`은 평소처럼 SSH 연결을 사용하면 된다.

```groovy
sshagent(credentials: ['app-server-ssh-key']) {
  sh 'ansible-playbook -i inventory/hosts.yml playbooks/rolling-deploy.yml'
}
```

`app-server-ssh-key`는 Jenkins에 등록한 Credential ID다. 해당 Key는 대상 서버에서 필요한 최소 권한만 가져야 하며, Agent의 `known_hosts` 또는 조직의 Host Key 검증 정책도 구성해야 한다. 연결 오류를 피하려고 `StrictHostKeyChecking=no`를 무조건 쓰는 것은 운영 환경에서 피한다.

### Vault 비밀번호: `withCredentials(file(...))`

Vault 비밀번호 파일은 Secret file Credential로 등록하고, Jenkins가 생성한 임시 파일 경로만 환경 변수에 담는다.

```groovy
withCredentials([
  file(credentialsId: 'ansible-vault-production', variable: 'VAULT_FILE')
]) {
  sh '''
    set +x
    ansible-playbook playbooks/rolling-deploy.yml \
      --vault-id production@"$VAULT_FILE"
  '''
}
```

- `VAULT_FILE`에는 비밀번호 자체가 아니라 임시 파일 경로가 들어간다.
- `set +x`는 shell이 명령어를 로그에 확장해 출력하지 않게 한다.
- Groovy 문자열에 Secret을 직접 끼워 넣지 말고, 작은따옴표 또는 `'''`를 사용해 shell이 환경 변수를 확장하게 한다.
- Secret file은 실행이 끝나면 정리되지만, 같은 Agent에서 여러 executor가 동시에 동작하면 다른 프로세스가 파일을 읽을 위험이 있다. 민감한 배포는 격리된 Agent 또는 단일 executor를 고려한다.

---

## 4. Declarative Pipeline에서 CLI 실행

가장 직접적인 방법은 `sh` Step에서 `ansible-playbook` CLI를 실행하는 것이다. 이 방식은 로컬·Jenkins·다른 CI에서도 같은 명령을 재사용하기 쉽다.

```groovy
pipeline {
  agent { label 'ansible' }

  parameters {
    choice(name: 'HOST_LIMIT', choices: ['rolling_targets', 'app01', 'app02'])
    choice(name: 'TAGS', choices: ['all', 'deploy', 'healthcheck'])
    string(name: 'DEPLOY_VERSION', defaultValue: '1.0.2')
    booleanParam(name: 'CONFIRM_DEPLOY', defaultValue: false)
  }

  stages {
    stage('Lint') {
      steps {
        sh 'ansible-lint playbooks roles'
      }
    }

    stage('Syntax check') {
      steps {
        sshagent(credentials: ['app-server-ssh-key']) {
          withCredentials([file(credentialsId: 'ansible-vault-production', variable: 'VAULT_FILE')]) {
            sh '''
              set +x
              ansible-playbook playbooks/rolling-deploy.yml --syntax-check \
                --vault-id production@"$VAULT_FILE"
            '''
          }
        }
      }
    }

    stage('Deploy') {
      when { expression { params.CONFIRM_DEPLOY } }
      steps {
        sshagent(credentials: ['app-server-ssh-key']) {
          withCredentials([file(credentialsId: 'ansible-vault-production', variable: 'VAULT_FILE')]) {
            sh '''
              set +x
              ansible-playbook playbooks/rolling-deploy.yml \
                --limit "$HOST_LIMIT" \
                --tags "$TAGS" \
                -e "deploy_version=$DEPLOY_VERSION" \
                --vault-id production@"$VAULT_FILE"
            '''
          }
        }
      }
    }
  }
}
```

현재 저장소의 [`Jenkinsfile`](Jenkinsfile)도 이와 같은 CLI 실행 방식을 사용한다.

### Jenkins Parameter와 Ansible 옵션 연결

| Jenkins Parameter | Ansible 옵션 | 의미 | 운영 주의점 |
|---|---|---|---|
| `HOST_LIMIT` | `--limit` | 실행할 그룹 또는 호스트 제한 | 자유 입력보다 `choice`로 허용값을 제한 |
| `TAGS` | `--tags` | 특정 태그가 달린 Task만 실행 | 필수 Task가 빠지지 않게 태그 설계 |
| `DEPLOY_VERSION` | `-e deploy_version=...` | Playbook 변수 전달 | 변수명·허용 버전 형식을 검증 |
| `CONFIRM_DEPLOY` | `when` | 실제 배포 단계 실행 여부 | 운영 배포의 최소 확인 장치 |

`-e`(=`--extra-vars`)는 Ansible 변수 우선순위가 높다. Jenkins Parameter에 비밀번호, 호스트 주소, 임의 shell 문자열처럼 위험한 값을 직접 받지 않는다. 대상은 Inventory와 `--limit`, 비밀값은 Credentials 또는 Vault로 관리한다.

---

## 5. CLI 방식과 Ansible Plugin 방식 비교

> **본 실습은 CLI 방식만 구현한다.** 아래 `ansiblePlaybook` 예시는 Jenkins Ansible Plugin을 설치했을 때의 개념 비교용 예시다.

Jenkins Ansible Plugin을 설치하면 `ansiblePlaybook` Step을 쓸 수 있다.

```groovy
ansiblePlaybook(
  playbook: 'playbooks/rolling-deploy.yml',
  inventory: 'inventory/hosts.yml',
  credentialsId: 'app-server-ssh-key',
  vaultCredentialsId: 'ansible-vault-production',
  limit: params.HOST_LIMIT,
  tags: params.TAGS,
  extraVars: [deploy_version: params.DEPLOY_VERSION]
)
```

| 구분 | `sh 'ansible-playbook ...'` | `ansiblePlaybook` Step |
|---|---|---|
| 전제 조건 | Ansible만 Agent에 설치 | Ansible + Jenkins Ansible Plugin 필요 |
| 명령 확인 | 실행되는 CLI가 Jenkinsfile에 그대로 보임 | Step의 옵션으로 선언 |
| 이식성 | 다른 CI·로컬에서도 명령 재사용 쉬움 | Jenkins 의존적 |
| Credentials | `sshagent`, `withCredentials`로 직접 제어 | `credentialsId`, `vaultCredentialsId` 지원 |
| 세부 옵션 | 모든 CLI 옵션을 즉시 사용 가능 | Plugin이 지원하는 옵션 중심, 추가 옵션은 `extras` |

본 실습의 [`Jenkinsfile`](Jenkinsfile)은 `sshagent`와 `withCredentials`로 Credential을 전달한 뒤 `sh` Step에서 CLI를 실행한다. Plugin 방식은 Jenkins Credentials·Inventory·Vault를 Step 옵션으로 통일하고 싶을 때 추가로 적용할 수 있다. Plugin의 `extras`는 추가 CLI 인자를 그대로 전달하므로, 사용자 입력을 그대로 넣지 말고 Pipeline 코드에서 고정한 값만 사용한다.

---

## 6. `ansible-lint`로 정적 분석하기

`ansible-lint`는 Playbook을 실제 실행하기 전에 흔한 오류, 권장하지 않는 문법, 위험한 패턴을 찾아준다. 배포 전에 반드시 실행하고, 실패하면 배포 Stage로 넘어가지 않게 한다.

```groovy
stage('Lint') {
  steps {
    dir('study/week5/doyeon') {
      sh 'ansible-lint playbooks roles'
    }
  }
}
```

프로젝트 루트에 `.ansible-lint` 파일을 둘 수 있다.

```yaml
---
profile: production
exclude_paths:
  - .cache/
warn_list:
  - experimental
```

Lint 경고를 무조건 숨기기보다 원인을 확인한다. 예외가 필요하면 해당 Task에 이유를 주석으로 남기고 좁은 범위에서만 `noqa`를 사용한다.

```yaml
- name: Reload cache without reporting a configuration change
  ansible.builtin.command: /usr/local/bin/reload-cache
  changed_when: false
```

`ansible-lint`는 문법 검사(`--syntax-check`)를 대체하지 않고, 둘 다 필요하다. lint는 코드 품질 규칙을 확인하고, syntax check는 Ansible이 Playbook 구조와 참조를 해석할 수 있는지 확인한다.

---

## 7. 기본 성능 최적화

### `forks`

기본 `forks`는 5다. Agent의 CPU·메모리, SSH 연결 수, 대상 서버 부하가 허용하면 높일 수 있다.

```ini
# ansible.cfg
[defaults]
forks = 20
```

또는 이번 실행에만 적용한다.

```bash
ansible-playbook --forks 20 playbooks/site.yml
```

`forks`는 Agent의 병렬 처리 한도이고, 롤링 배포의 안전 범위는 `serial`이다. `forks`를 높여도 `serial: 1`인 배포는 한 대씩 진행된다.

### SSH Pipelining

Pipelining은 모듈을 원격 임시 파일로 복사하는 대신 표준 입력으로 전달해 네트워크 왕복을 줄이는 설정이다.

```ini
# ansible.cfg
[connection]
pipelining = True
```

특히 Task가 많고 SSH 지연이 큰 환경에서 효과가 있을 수 있다. 다만 `copy`, `template`, `fetch`처럼 파일 전송이 필요한 모듈에는 적용되지 않으며, `become`과 함께 쓸 때 대상 서버의 sudo 정책(`requiretty` 등) 호환성을 먼저 확인해야 한다. 검증 없이 운영 전체에 켜지지 말고, 스테이징 환경에서 실행 시간·권한 오류를 비교한다.

### 함께 확인할 항목

- 필요하지 않은 Play에서는 `gather_facts: false`로 fact 수집을 생략한다.
- `forks`는 Agent 자원과 대상 서버 부하를 측정하며 조금씩 높인다.
- `serial`은 성능 값이 아니라 서비스 영향 범위를 제한하는 배포 정책으로 유지한다.
- SSH ControlPersist 같은 연결 재사용은 조직의 SSH 정책과 보안 기준을 확인한 뒤 적용한다.

## 8. 권장 Pipeline 순서

```text
Checkout
  → Collection 설치
  → ansible-lint
  → ansible-playbook --syntax-check
  → (선택) --check / 테스트 Inventory 검증
  → 사용자 확인
  → 운영 Inventory에 --limit, --tags, -e를 붙여 배포
  → 배포 결과·헬스 체크·로그 확인
```

운영 배포는 배포 대상과 버전이 Build 화면에 분명히 보이게 하고, 실제 실행 전 확인 단계 또는 승인 절차를 둔다. 파라미터가 있어도 Playbook의 `serial`, Health Check, 실패 중단 정책은 그대로 유지해야 한다.

## 참고 문서

- [Using a Jenkinsfile](https://www.jenkins.io/doc/book/pipeline/jenkinsfile/)
- [Pipeline Syntax](https://www.jenkins.io/doc/book/pipeline/syntax/)
- [Using credentials](https://www.jenkins.io/doc/book/using/using-credentials/)
- [SSH Agent Plugin](https://www.jenkins.io/doc/pipeline/steps/ssh-agent/)
- [Ansible Plugin](https://plugins.jenkins.io/ansible)
- [Ansible Plugin Pipeline Steps](https://www.jenkins.io/doc/pipeline/steps/ansible/)
- [Ansible Lint configuration](https://docs.ansible.com/projects/lint/configuring/)
- [Ansible configuration settings](https://docs.ansible.com/projects/ansible/latest/reference_appendices/config.html)
- [Controlling playbook execution: strategies and more](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_strategies.html)
