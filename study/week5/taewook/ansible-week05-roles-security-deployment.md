# 5주차: Roles, Security & Deployment Orchestration

> 목표: Role로 작업을 모듈화하고, Secret 관리와 순차 배포를 적용해 Jenkins에서 실행할 수 있는 배포 구조를 구성한다.

## 1. Role-Based Architecture

### Role 구조

Role은 특정 기능에 필요한 작업·변수·설정 파일을 묶은 재사용 단위이다. Playbook은 대상과 실행 순서를 정하고, Role은 실제 작업을 구현한다. 예를 들어 `common`, `nginx`, `app`으로 분리할 수 있다.

| 경로 | 용도 |
| --- | --- |
| `tasks/main.yml` | Role의 기본 진입점. 설치·설정·배포 작업 정의 |
| `handlers/main.yml` | `notify`로 호출할 재시작·재로드 작업 정의 |
| `templates/` | 변수를 치환할 Jinja2 템플릿 저장 |
| `files/` | 내용 변경 없이 복사할 파일 저장 |
| `defaults/main.yml` | 사용자가 덮어쓸 수 있는 기본값 정의 |
| `vars/main.yml` | 우선순위가 높은 Role 변수 정의 |
| `meta/main.yml` | Role 의존성 및 메타데이터 정의 |

모든 디렉터리가 필수는 아니다. 필요한 것만 사용하며, 기본 구조는 `ansible-galaxy role init roles/app`으로 생성한다.

### defaults와 vars

`defaults`는 환경별 변경을 전제로 하는 설정에 적합하다. `vars`는 Inventory 변수보다 우선하므로, 포트·버전처럼 운영 환경에서 바꿔야 할 값을 넣으면 재사용이 어려워진다. 단, `vars`도 상수는 아니며 더 높은 우선순위의 변수로 변경할 수 있다.

이번 범위에서 주요 변수의 우선순위는 다음과 같다. 오른쪽일수록 높다.

`Role defaults < Inventory 변수 < Play 변수 < Role vars < Extra Variables(-e)`

```yaml
# roles/app/defaults/main.yml
app_port: 8080
app_version: "1.0.0"
```

```yaml
# inventories/prod/group_vars/web/main.yml
app_port: 9000
```

```yaml
# deploy.yml
- name: Deploy application
  hosts: web
  become: true
  roles:
    - role: app
```

이 구성에서는 `web` 그룹의 `app_port`가 9000이 된다. `-e app_port=8081`을 전달하면 8081이 적용된다.

### import_role과 include_role

| 구분 | `import_role` | `include_role` |
| --- | --- | --- |
| 처리 방식 | 실행 전 정적으로 작업 확장 | 실행 중 동적으로 Role 로드 |
| 적합한 경우 | 구조가 고정된 작업 | 조건·반복에 따라 달라지는 작업 |
| `when` | 내부 각 작업에 조건 적용 | Role을 포함할지 판단 |
| 반복문 | import 자체에 적용 불가 | `loop` 사용 가능 |
| 태그 | 내부 작업으로 상속 | include의 태그만으로 내부에 상속되지 않음 |

`roles:`는 일반적인 정적 Role 실행 방식이다. 작업 중간에 Role을 넣을 때 `import_role`이나 `include_role`을 사용한다. 동적 include 내부까지 태그를 적용하려면 `apply: tags` 등을 함께 설정해야 한다.

### Galaxy와 의존성 관리

Ansible Galaxy는 Role과 Collection을 배포하는 저장소이다. Collection은 Role뿐 아니라 Module·Plugin 등을 포함하며, `amazon.aws`처럼 네임스페이스로 구분한다.

```yaml
# requirements.yml — 버전은 프로젝트에서 검증한 값으로 고정한다.
roles:
  - name: geerlingguy.nginx
    version: "3.1.4"
collections:
  - name: amazon.aws
    version: "9.0.0"
```

```bash
ansible-galaxy role install -r requirements.yml
ansible-galaxy collection install -r requirements.yml
```

예시 버전은 최신 버전 권장이 아니다. Ansible·Python과의 호환성을 확인한 뒤 고정한다. Collection이 요구하는 Python 패키지는 별도로 설치하며, 외부 Role도 실행 전에 내용을 검토한다.

## 2. Security & Secret Management

### Ansible Vault

Ansible Vault는 비밀번호·토큰 등이 들어 있는 파일이나 변수 값을 암호화하는 기능이다. 저장된 데이터를 보호하며, 실행 중 로그나 대상 서버에 저장된 평문까지 자동으로 보호하지는 않는다.

```bash
# 기존 파일 전체 암호화
ansible-vault encrypt inventories/prod/group_vars/web/vault.yml --vault-id prod@prompt

# 암호화된 파일 편집 및 조회
ansible-vault edit inventories/prod/group_vars/web/vault.yml --vault-id prod@prompt
ansible-vault view inventories/prod/group_vars/web/vault.yml --vault-id prod@prompt

# 개별 값 암호화: 비밀값을 명령 인자로 남기지 않고 입력한다.
ansible-vault encrypt_string --vault-id prod@prompt --name vault_db_password

# 실행 시 복호화 비밀번호 입력
ansible-playbook -i inventories/prod/hosts.ini deploy.yml --vault-id prod@prompt
```

`encrypt_string`의 출력은 YAML 변수 파일에 넣는다. 파일 전체 암호화는 관리가 단순하고, 개별 변수 암호화는 변수명과 일반 설정을 읽기 쉽다는 차이가 있다.

`--vault-id prod@prompt`에서 `prod`는 식별자, `prompt`는 비밀번호 입력 방식이다. 식별자 자체가 접근 권한을 분리하지는 않는다. 개발·운영을 분리하려면 실제 비밀번호와 접근 권한도 나누어야 한다.

### Password File과 로그 보호

자동화 환경에서는 프롬프트 대신 비밀번호 파일을 전달한다.

```bash
ansible-playbook -i inventories/prod/hosts.ini deploy.yml \
  --vault-id prod@/secure/vault-pass
```

- 비밀번호 파일은 평문이므로 Git에 넣지 않고, 읽기 권한을 제한한다. 일반적인 권한은 `0600`이다.
- CI/CD에서는 Jenkins Credentials로 보관하고 실행 중에만 파일 경로를 제공한다.
- `ANSIBLE_VAULT_PASSWORD_FILE` 환경변수에는 비밀번호 자체가 아니라 **파일 경로**를 지정한다.
- 암호화된 파일은 Git으로 관리할 수 있지만 복호화 비밀번호는 별도 관리한다.

```yaml
- name: Write application credentials
  ansible.builtin.template:
    src: app.env.j2
    dest: /etc/app.env
    owner: root
    group: root
    mode: "0600"
  no_log: true
  diff: false
```

`no_log: true`는 해당 작업의 인자와 결과가 실행 로그에 노출되는 것을 막는다. 다른 작업에서 같은 값을 `debug`로 출력하면 노출되며, 파일 권한이나 애플리케이션 로그까지 보호하지는 않는다.

### External Secret Manager

| 방식 | 비밀값 보관 위치 | 조회 방식 |
| --- | --- | --- |
| Ansible Vault | 암호화된 프로젝트 파일 | 실행 시 비밀번호로 복호화 |
| HashiCorp Vault | 별도 Vault 서버 | 인증 후 API로 조회 |
| AWS Secrets Manager | AWS 관리형 서비스 | IAM 권한으로 조회 |

외부 저장소는 중앙 권한 관리·감사·비밀값 교체에 유리하다. 대신 실행 환경에 인증 수단과 네트워크 접근이 필요하다.

```yaml
vars:
  db_password: "{{ lookup('amazon.aws.secretsmanager_secret', 'prod/app/db-password', region='ap-northeast-2') }}"
```

이 예시는 Secret에 비밀번호 문자열 하나를 저장한 경우이다. JSON으로 저장했다면 필요한 필드를 추출해야 한다. Lookup은 제어 노드에서 실행되므로 Jenkins 연계 시 Agent에 Collection, `boto3` 등 의존성과 IAM 권한이 필요하다.

HashiCorp Vault는 `community.hashi_vault` Collection과 `hvac` 등을 사용한다. AppRole·JWT 등 인증 방식을 구성하며, 인증 토큰 자체를 Playbook에 하드코딩하지 않는다.

## 3. Multi-Host Execution & Orchestration

### 실행 순서와 동시 실행 수

| 설정 | 의미 |
| --- | --- |
| `strategy: linear` | 기본값. 현재 배치의 호스트가 같은 작업을 마친 후 다음 작업 진행 |
| `strategy: free` | 각 호스트가 다른 호스트를 기다리지 않고 다음 작업 진행 |
| `forks` | 병렬 작업을 처리하는 Worker 수. 기본값 5 |
| `serial` | 한 배치에서 Play 전체를 수행할 호스트 수 또는 비율 |
| `throttle` | 특정 작업·블록 등의 동시 실행 수 제한 |

`forks`는 병렬 처리량이고 `serial`은 배포 묶음의 크기이다. `forks=10`, `serial=3`, 특정 작업의 `throttle=1`이면 3대씩 배포하면서 해당 작업은 한 번에 1대씩 실행한다.

```yaml
- name: Deploy in batches
  hosts: web
  strategy: linear
  serial: [1, 2, "25%"]
  tasks:
    - name: Restart application
      ansible.builtin.service:
        name: app
        state: restarted
      throttle: 1
```

첫 배치는 1대, 다음 배치는 2대, 이후는 전체 대상의 25%씩 실행한다. 서비스 중단 범위를 통제하는 배포에는 `linear`와 `serial` 조합이 적합하다.

### run_once와 delegate_to

- `run_once: true`: 현재 배치에서 한 호스트만 작업을 실행한다. `serial`과 함께 사용하면 **배치마다 한 번** 실행된다.
- `delegate_to`: 작업 실행 위치를 다른 호스트로 옮긴다. 실행 횟수를 줄이는 설정은 아니다.
- `delegate_to: localhost`: 제어 노드에서 실행한다. Jenkins에서는 Ansible을 실행하는 Agent가 이에 해당한다.

```yaml
- name: Check deployment gateway
  ansible.builtin.uri:
    url: https://gateway.example.com/health
    status_code: 200
  delegate_to: localhost
  become: false
  run_once: true
```

전체 배포에서 정확히 한 번 실행해야 하는 작업은 단일 호스트를 대상으로 하는 별도 Play로 분리하는 편이 명확하다. `free`에서는 `run_once` 동작을 보장할 수 없으므로 이 조합에 의존하지 않는다.

### 실패 정책

| 설정 | 동작 |
| --- | --- |
| 기본 동작 | 실패한 호스트의 후속 작업을 중단하고 나머지는 계속 실행 |
| `any_errors_fatal: true` | 처리되지 않은 실패가 발생하면 현재 배치의 해당 작업 처리가 끝난 뒤 전체 진행 중단 |
| `max_fail_percentage` | 실패 비율이 지정값을 **초과**하면 중단. `serial` 사용 시 배치 기준 |

배치가 4대일 때 `max_fail_percentage: 25`는 1대 실패까지 허용하고 2대 실패에서 중단한다. 한 대의 실패도 허용하지 않으려면 `0`을 사용한다. 배포 실패 정책은 기본 `linear` 기준으로 설계한다.

## 4. Rolling Deployment & Failure Handling

### Rolling Deployment

일부 서버만 교체하면서 나머지 서버로 서비스를 유지하는 방식이다. 각 서버에 다음 순서를 적용한다.

1. Load Balancer에서 신규 요청을 차단하고 기존 연결이 정리될 때까지 기다린다.
2. 새 버전을 배포하고 서비스를 재시작한다.
3. Health Check로 실제 요청 처리 가능 여부를 확인한다.
4. 정상일 때만 Load Balancer에 복귀시킨다.
5. 다음 배치로 진행한다.

프로세스 실행 여부만으로 정상 배포를 판단하지 않는다. Health Check는 HTTP 응답과 필요한 의존성 상태를 확인해야 하며, 남은 서버가 트래픽을 감당할 수 있도록 배치 크기를 정한다.

### 실패 처리 구조

`block`은 정상 작업, `rescue`는 실패 시 복구, `always`는 성공·실패와 관계없는 정리 작업이다. 연결 불가나 잘못된 작업 정의 등은 일반적인 작업 실패와 달리 `rescue`로 처리되지 않는다.

아래는 흐름을 보여주는 골격이다. `tasks/` 파일과 `app` Role은 LB 종류와 배포 방식에 맞게 별도로 구현해야 한다.

```yaml
- name: Rolling deployment
  hosts: web
  become: true
  serial: 1
  any_errors_fatal: true
  tasks:
    - name: Deploy and recover on failure
      block:
        - name: Drain traffic
          ansible.builtin.include_tasks: tasks/lb_drain.yml

        - name: Deploy new release
          ansible.builtin.include_role:
            name: app

        - name: Apply pending restart handlers
          ansible.builtin.meta: flush_handlers

        - name: Check application readiness
          ansible.builtin.uri:
            url: http://127.0.0.1:8080/health
            status_code: 200
          register: health
          until: health.status | default(0) == 200
          retries: 10
          delay: 3

        - name: Restore traffic
          ansible.builtin.include_tasks: tasks/lb_enable.yml

      rescue:
        - name: Restore previous release and check readiness
          ansible.builtin.include_tasks: tasks/rollback_and_check.yml

        - name: Restore traffic after successful recovery
          ansible.builtin.include_tasks: tasks/lb_enable.yml

        - name: Stop remaining deployment
          ansible.builtin.fail:
            msg: "Deployment failed; previous release restored."
```

- `lb_drain.yml`은 대상 제외와 연결 정리 대기를 수행한다. LB API 호출은 필요에 따라 제어 노드나 LB로 위임한다.
- Handler는 보통 작업 구간이 끝날 때 실행되므로, Health Check 전에 필요한 재시작은 `flush_handlers`로 먼저 반영한다.
- `rollback_and_check.yml`은 이전 버전 복구와 재기동·정상 여부 검증까지 수행해야 한다. 복구 검증 실패 시 LB 복귀 작업으로 넘어가지 않는다.
- `rescue`가 성공하면 원래 실패는 복구된 것으로 취급된다. 복구 후에도 다음 서버 배포를 막으려면 `fail`로 실패 상태를 다시 남긴다.
- `always`에서 무조건 LB에 복귀시키면 장애 서버로 트래픽이 들어갈 수 있다.

롤백은 자동으로 제공되지 않는다. 이전 배포 파일·이미지 버전을 보존하고 복구 절차를 구현해야 한다. DB 스키마 변경은 애플리케이션만 되돌려 해결되지 않을 수 있으므로 구버전과의 호환성을 고려한다.

### Canary와 Blue-Green

| 방식 | 배포 및 전환 방식 | 고려 사항 |
| --- | --- | --- |
| Rolling | 서버를 여러 배치로 나누어 교체 | 배포 중 구버전·신버전 공존 |
| Canary | 소수 서버·트래픽에 먼저 배포하고 지표 확인 후 확대 | 오류율·지연시간·관찰 시간 등의 통과 기준 필요 |
| Blue-Green | 별도 환경에 배포·검증한 뒤 트래픽 전환 | 추가 자원과 데이터 호환성 필요 |

`serial: [1, "25%"]`만으로 Canary 검증이 완성되지는 않는다. 첫 배치 이후 지표 확인이나 승인 단계를 넣어야 한다. 특정 서버를 Canary로 지정하려면 별도 Inventory 그룹으로 관리한다.

Blue-Green은 `blue`, `green` 그룹으로 환경을 나누고 비활성 그룹에 배포한 뒤 LB 대상을 바꾼다. Inventory 그룹만 바꾼다고 실제 트래픽이 전환되는 것은 아니다.

## 5. Jenkins CI/CD Integration & Operations

### 실행 환경과 Credentials

Ansible은 Jenkins Controller가 아니라 **Pipeline을 실행하는 Agent**에 설치한다. Agent는 대상 서버로 SSH 접속할 수 있어야 하며, Ansible·Python·Collection 버전을 고정해 실행 환경 차이를 줄인다.

| Jenkins Credential | 용도 |
| --- | --- |
| SSH Username with private key | 대상 서버 접속 계정과 SSH 개인키 |
| Secret file | Ansible Vault 비밀번호 파일 |
| Secret text | API 토큰 등 문자열 Secret |

SSH Host Key는 검증된 `known_hosts`로 관리한다. 편의상 검증을 끄는 설정을 기본값으로 두지 않는다.

### Declarative Pipeline에서 CLI 실행

다음 예시는 Credential Binding Plugin을 사용한다. Agent에 실행 도구·의존성과 `known_hosts`가 준비되어 있고, 예시 SSH 키는 별도 암호 입력이 필요 없는 구성을 전제로 한다. 암호화된 SSH 키는 SSH Agent Plugin 등으로 로드할 수 있다.

```groovy
pipeline {
    agent { label 'ansible' }
    options { disableConcurrentBuilds() }
    parameters {
        choice(name: 'TARGET', choices: ['web', 'canary'], description: '배포 대상')
        choice(name: 'TASK_TAG', choices: ['all', 'config'], description: '실행 범위')
        string(name: 'APP_VERSION', defaultValue: '1.0.0', description: '배포 버전')
    }
    stages {
        stage('Validate and Deploy') {
            steps {
                withCredentials([
                    sshUserPrivateKey(credentialsId: 'deploy-ssh',
                        keyFileVariable: 'SSH_KEY', usernameVariable: 'SSH_USER'),
                    file(credentialsId: 'ansible-vault-prod', variable: 'VAULT_FILE')
                ]) {
                    sh '''
                        set -eu
                        set +x
                        export ANSIBLE_VAULT_PASSWORD_FILE="$VAULT_FILE"
                        ansible-lint deploy.yml
                        ansible-playbook -i inventories/prod/hosts.ini deploy.yml --syntax-check
                        python3 -c 'import json, os; print(json.dumps({"app_version": os.environ["APP_VERSION"]}))' > deploy-vars.json
                        trap 'rm -f deploy-vars.json' EXIT
                        ansible-playbook -i inventories/prod/hosts.ini deploy.yml \
                          --private-key "$SSH_KEY" -u "$SSH_USER" \
                          --limit "$TARGET" --tags "$TASK_TAG" \
                          -e @deploy-vars.json
                    '''
                }
            }
        }
    }
}
```

`deploy-vars.json`에는 비밀값이 아닌 배포 버전만 기록한다. Secret은 Vault나 Credentials로 전달한다. 여러 Job이 같은 환경에 배포한다면 `disableConcurrentBuilds()` 외에 환경 단위 잠금도 필요하다.

Groovy의 작은따옴표 문자열을 사용해 Secret 확장을 셸에 맡긴다. Jenkins의 로그 마스킹만으로 모든 노출이 방지되지는 않으므로 Secret을 출력하거나 명령 인자로 직접 넣지 않는다.

### Parameter와 Ansible 옵션 연결

| 옵션 | 역할 | 주의점 |
| --- | --- | --- |
| `--limit` | Inventory 중 실행할 호스트 제한 | Play의 `hosts` 범위 안에서 대상을 좁힘 |
| `--tags` | 태그가 지정된 작업 선택 | 선행 작업·검증 작업이 빠지지 않도록 구성 |
| `-e`, `--extra-vars` | 실행 시 변수 덮어쓰기 | 우선순위가 높으므로 허용할 변수 제한 |

예시의 `config` 선택은 관련 작업에 해당 태그가 정의되어 있어야 한다. `-e @파일.json`은 자료형과 인용 처리를 명확히 하기 위한 방식이다. 버전 값도 Role에서 사용하기 전에 형식과 허용 범위를 검증한다.

### CLI와 Jenkins Ansible Plugin

| 방식 | 장점 | 관리할 부분 |
| --- | --- | --- |
| `sh 'ansible-playbook ...'` | 로컬 명령과 동일하고 동작이 명시적 | Credential Binding과 옵션 전달 직접 구성 |
| `ansiblePlaybook` Step | SSH·Vault Credential과 실행 옵션을 Step에 연결 | Plugin 버전과 지원 옵션 관리 |

```groovy
ansiblePlaybook(
    playbook: 'deploy.yml',
    inventory: 'inventories/prod/hosts.ini',
    credentialsId: 'deploy-ssh',
    vaultCredentialsId: 'ansible-vault-prod',
    limit: params.TARGET,
    tags: params.TASK_TAG,
    extraVars: [app_version: params.APP_VERSION]
)
```

두 방식 모두 Agent에 Ansible 실행 환경이 필요하다. Plugin은 Ansible을 대체하지 않고 실행과 Jenkins 연계를 돕는다.

### 품질 검사와 성능 조정

```bash
ansible-lint deploy.yml
ansible-playbook -i inventories/prod/hosts.ini deploy.yml --syntax-check
ansible-playbook -i inventories/prod/hosts.ini deploy.yml --check --diff
```

`ansible-lint`는 Module 사용·명명·멱등성 관련 규칙 등을 점검한다. `--syntax-check`는 문법 검사이고, `--check`는 지원되는 작업의 변경 예측이다. 실제 배포 성공을 보장하지 않으며 `--diff`는 민감한 설정 내용이 노출되지 않도록 주의해야 한다.

```ini
# ansible.cfg
[defaults]
forks = 10

[ssh_connection]
pipelining = True
```

- `forks`: 대상 수와 Agent·네트워크·외부 API 부하를 보고 조정한다.
- SSH Pipelining: 모듈 실행에 필요한 전송·연결 작업을 줄인다. `become` 사용 시 sudo의 TTY 요구 설정 등과 호환성을 확인한다.
- Fact 수집: 필요 없는 Play에서는 `gather_facts: false`로 생략한다.
- 배포에서는 처리 속도보다 정상 검증과 실패 시 중단 범위를 우선한다.

## 참고 자료

- [Ansible Roles](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_reuse_roles.html)
- [Galaxy User Guide](https://docs.ansible.com/projects/ansible/latest/galaxy/user_guide.html)
- [Vault 암호화](https://docs.ansible.com/projects/ansible/latest/vault_guide/vault_encrypting_content.html) · [암호화 데이터 사용](https://docs.ansible.com/projects/ansible/latest/vault_guide/vault_using_encrypted_content.html)
- [실행 전략](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_strategies.html) · [오류 처리](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_error_handling.html) · [Blocks](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_blocks.html)
- [AWS Secrets Manager Lookup](https://docs.ansible.com/projects/ansible/latest/collections/amazon/aws/secretsmanager_secret_lookup.html) · [HashiCorp Vault Lookup](https://docs.ansible.com/projects/ansible/latest/collections/community/hashi_vault/hashi_vault_lookup.html)
- [Jenkins Credentials Binding](https://www.jenkins.io/doc/pipeline/steps/credentials-binding/) · [Jenkins Ansible Plugin](https://www.jenkins.io/doc/pipeline/steps/ansible/)
- [Ansible Lint](https://docs.ansible.com/projects/lint/usage/)
