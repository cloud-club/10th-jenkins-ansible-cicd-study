# Jenkins CI/CD Integration & Operations

## 1. 로컬 배포 명령을 Jenkins로 옮기기

04번까지는 사람이 `ansible-playbook`을 실행했다. 이제 같은 명령을 Jenkins에서 실행해 보자. Jenkins는 배포할 코드와 입력값을 준비하고 실행 결과를 기록한다. Ansible은 전달받은 Inventory와 Playbook에 따라 서버를 변경한다.

**Ansible 명령은 Jenkins Agent에서 실행된다.** 따라서 이 구성에서는 Agent가 Ansible Control Node다. Ansible과 필요한 라이브러리를 설치하고 SSH 연결을 확인할 위치도 Agent다.

```text
Jenkins Controller
  └─ Job / 권한 / 실행 상태 관리
           ↓
Jenkins Agent = Ansible Control Node
  ├─ Playbook · Role · Inventory
  ├─ ansible-playbook / ansible-lint
  └─ 실행 중 전달받은 SSH Key · Vault 비밀번호
           ↓ SSH
   Web Servers + Load Balancer
```

이 문서는 별도 배포 저장소에 01번의 `site.yml`, 02번의 `secrets.yml`, 04번의 `rolling.yml`을 작성했다고 가정한다. 웹 서버와 HAProxy도 먼저 준비한다. 이번 Pipeline이 실행하는 배포는 `rolling.yml`이며, 앞의 두 Playbook은 검증 대상에 함께 넣는다.

공식문서: [Using a Jenkinsfile](https://www.jenkins.io/doc/book/pipeline/jenkinsfile/), [Installing Ansible](https://docs.ansible.com/projects/ansible/latest/installation_guide/intro_installation.html)

## 2. Agent에서 실행 환경 준비하기

로컬에서 성공한 명령이 Jenkins에서 실패한다면 먼저 실행 환경 차이를 확인한다. 내 터미널에 설치한 Ansible이나 등록한 SSH Key가 Agent에도 있다는 보장은 없다.

| 준비 항목 | 필요한 이유 |
| --- | --- |
| 호환되는 Python과 `ansible-core` | Playbook 실행 |
| `ansible-lint` | Playbook 작성 규칙 검사 |
| Role·Collection과 Python 의존성 | HAProxy 모듈·외부 Lookup 등 사용 |
| Git·OpenSSH 클라이언트 | 저장소 Checkout과 서버 접속 |
| 검증한 `known_hosts` | SSH로 접속할 서버의 신원 확인 |
| 서버·LB·Secret Manager로의 네트워크 | 실제 작업 수행 |

다음은 Agent 환경을 처음 준비할 때의 흐름이다. 운영에서는 함께 검증한 버전을 고정해 Agent 이미지나 의존성 파일로 관리한다.

```bash
# Agent 이미지/환경 준비 시 수행하는 기본 흐름
python3 -m venv .venv
.venv/bin/python -m pip install ansible-core ansible-lint
.venv/bin/ansible-galaxy collection install -r requirements.yml

# 실제 빌드 계정과 같은 환경에서 확인
.venv/bin/ansible --version
.venv/bin/ansible-lint --version
.venv/bin/ansible-galaxy collection list
```

`ansible-core`에는 외부 Collection이 포함되지 않으므로 `requirements.yml`의 의존성을 설치해야 한다. 아래 Pipeline은 준비한 가상환경의 실행 파일이 Agent의 `PATH`에 등록되어 있다고 가정한다.

실제 빌드 계정으로 버전과 SSH 접속을 확인한다. Host Key 검증을 끄기보다는 검증한 서버 키를 `known_hosts`에 준비한다. `ssh-keyscan`의 출력도 신뢰할 수 있는 경로로 확인한 뒤 등록한다.

공식문서: [Installing Ansible](https://docs.ansible.com/projects/ansible/latest/installation_guide/intro_installation.html), [Installing Ansible Lint](https://docs.ansible.com/projects/lint/installing/), [SSH connection plugin](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/ssh_connection.html)

## 3. 배포 입력과 인증 정보를 구분하기

### 3.1 Parameter는 무엇을 배포할지 정한다

사용자가 Jenkins 화면에서 dev 환경, `web01`, 버전 `v2`를 선택하면 그 값이 Ansible 실행 옵션으로 이어진다.

| Jenkins Parameter | 예시 값 | 연결할 Ansible 옵션 |
| --- | --- | --- |
| `TARGET_ENV` | `dev` | `-i inventories/dev/hosts.yml` |
| `TARGET_LIMIT` | `web01` | `--limit web01` |
| `TAGS` | `deploy` | `--tags deploy` |
| `RELEASE` | `v2` | `-e @ci-extra-vars.json` |

`--limit`은 Play의 `hosts`에서 대상을 더 좁힌다. `hosts: web`이라면 `web`에 속한 서버 중 선택한 대상에 적용한다. LB로 위임한 Task의 실행 위치까지 막지는 않는다.

배포 버전은 다음 JSON 파일로 만들어 전달한다. 전체 Pipeline에서는 `JsonOutput`으로 파일을 생성하므로 따옴표를 직접 이어 붙일 필요가 없다.

```json
{
  "study_web_release": "v2"
}
```

04번 예제는 LB 제외부터 복귀까지 하나의 배포 절차다. 이를 함께 실행하도록 태그를 `deploy` 또는 `all`로 제한한다. Extra vars의 우선순위도 높으므로 사용자가 임의 변수를 넣기보다는 필요한 입력만 받는다.

공식문서: [ansible-playbook CLI](https://docs.ansible.com/projects/ansible/latest/cli/ansible-playbook.html), [Extra vars](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_variables.html#passing-variables-on-the-command-line), [Tags](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_tags.html)

### 3.2 Credentials는 접속과 복호화에 사용한다

서버의 SSH Key와 Vault 비밀번호는 일반 Parameter 대신 Jenkins Credentials에 등록한다. 두 정보의 용도가 다르므로 따로 관리한다.

| Credential ID 예시 | 타입 | 용도 |
| --- | --- | --- |
| `ansible-ssh-dev` | SSH Username with private key | dev 서버·LB 접속 |
| `ansible-vault-dev` | Secret file | dev 변수 파일 복호화 |
| `ansible-ssh-prod` | SSH Username with private key | prod 서버·LB 접속 |
| `ansible-vault-prod` | Secret file | prod 변수 파일 복호화 |

예제는 passphrase가 없는 SSH Key와 비대화형 sudo가 준비된 실습 환경을 가정한다. passphrase가 있는 Key를 사용한다면 `sshagent` 등으로 잠금을 해제해 제공하는 구성이 필요하다.

dev/prod Inventory는 별도로 준비하고 Credential의 사용자와 `ansible_user`를 맞춘다. Inventory의 연결 변수는 일반 CLI의 `--user`보다 우선할 수 있다.

공식문서: [Using credentials](https://www.jenkins.io/doc/book/using/using-credentials/), [SSH Agent step](https://www.jenkins.io/doc/pipeline/steps/ssh-agent/), [Ansible precedence](https://docs.ansible.com/projects/ansible/latest/reference_appendices/general_precedence.html)

## 4. Declarative Pipeline의 흐름 이해하기

전체 Jenkinsfile을 보기 전에 단계를 먼저 정리해 보자. 이 예제는 `ansible-deploy` Label의 Agent에서 실행하는 배포 전용 Job이다.

```text
Checkout → 입력 검증 → Lint·구문·대상 확인 → 운영 승인 → 배포 → 결과 기록
```

| 단계 | 확인할 내용 |
| --- | --- |
| Checkout | 어떤 Git revision의 Playbook을 실행하는가? |
| 입력 검증 | 허용한 환경·대상·태그·버전인가? |
| 사전 검증 | 작성 규칙과 구문에 문제가 없는가? 대상이 맞는가? |
| 운영 승인 | prod 배포를 진행할 것인가? |
| 배포 | Credentials를 전달해 `rolling.yml` 실행 |
| 결과 기록 | 배포 버전과 성공·실패를 남김 |

### 4.1 핵심은 Credentials를 묶어 CLI에 전달하는 부분이다

아래는 dev 환경에서의 Deploy 단계만 줄여 본 예다. Pipeline의 `steps` 안에 작성하며, `ci-extra-vars.json`은 앞 단계에서 준비했다고 가정한다.

```groovy
withCredentials([
    sshUserPrivateKey(
        credentialsId: 'ansible-ssh-dev',
        keyFileVariable: 'SSH_KEY_FILE',
        usernameVariable: 'SSH_USER'
    ),
    file(credentialsId: 'ansible-vault-dev', variable: 'VAULT_PASS_FILE')
]) {
    sh '''
      set +x
      set -eu
      ansible-playbook -i inventories/dev/hosts.yml rolling.yml \
        --private-key "$SSH_KEY_FILE" --user "$SSH_USER" \
        --vault-id "dev@$VAULT_PASS_FILE" \
        --limit web01 --tags deploy -e @ci-extra-vars.json
    '''
}
```

SSH Key는 `--private-key`, Vault 비밀번호 파일은 `--vault-id`로 전달한다. `withCredentials`가 제공한 파일 경로를 사용하므로 Secret 원문을 Jenkinsfile에 적지 않는다.

`sh`에는 작은따옴표 세 개를 사용해 환경 변수를 Shell에서 읽게 한다. `set +x`로 명령 추적 출력을 끄고, `set -e`로 명령 실패를 이후 단계에 전달한다. Jenkins의 `sh`도 기본적으로 0이 아닌 종료 코드를 실패로 처리한다.

공식문서: [Credentials Binding](https://www.jenkins.io/doc/pipeline/steps/credentials-binding/), [sh step](https://www.jenkins.io/doc/pipeline/steps/workflow-durable-task-step/#sh-shell-script)

### 4.2 전체 Jenkinsfile 보기

위 흐름에 입력 검증, 운영 승인, 결과 기록을 연결한 코드다. 처음에는 각 `stage`의 역할을 따라 읽고, 실제 실습 때 세부 설정을 맞춘다.

<details>
<summary>Declarative Pipeline 전체 코드 펼치기</summary>

```groovy
// Jenkinsfile
pipeline {
    agent { label 'ansible-deploy' }

    options {
        skipDefaultCheckout(true)
        disableConcurrentBuilds()
        timeout(time: 30, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '20'))
    }

    parameters {
        choice(name: 'TARGET_ENV', choices: ['dev', 'prod'], description: '배포 환경')
        choice(name: 'TARGET_LIMIT', choices: ['web01', 'web'], description: '한 대 또는 전체 웹 그룹')
        choice(name: 'TAGS', choices: ['deploy', 'all'], description: '전체 배포 절차')
        string(name: 'RELEASE', defaultValue: 'v2', description: '배포 버전')
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Validate Inputs') {
            steps {
                script {
                    if (!(params.TARGET_ENV in ['dev', 'prod']) ||
                        !(params.TARGET_LIMIT in ['web01', 'web']) ||
                        !(params.TAGS in ['deploy', 'all']) ||
                        !(params.RELEASE ==~ /[A-Za-z0-9][A-Za-z0-9._-]{0,63}/)) {
                        error('허용되지 않은 배포 입력입니다.')
                    }
                    writeFile(
                        file: 'ci-extra-vars.json',
                        text: groovy.json.JsonOutput.toJson([
                            study_web_release: params.RELEASE
                        ])
                    )
                }
            }
        }

        stage('Lint and Preflight') {
            steps {
                withCredentials([
                    file(credentialsId: "ansible-vault-${params.TARGET_ENV}",
                         variable: 'VAULT_PASS_FILE')
                ]) {
                    sh '''
                      set +x
                      set -eu
                      export ANSIBLE_VAULT_PASSWORD_FILE="$VAULT_PASS_FILE"
                      ansible --version
                      ansible-lint --offline --profile basic site.yml secrets.yml rolling.yml
                      ansible-playbook -i "inventories/$TARGET_ENV/hosts.yml" rolling.yml \
                        --syntax-check -e @ci-extra-vars.json
                      ansible-playbook -i "inventories/$TARGET_ENV/hosts.yml" rolling.yml \
                        --list-hosts --limit "$TARGET_LIMIT"
                    '''
                }
            }
        }

        stage('Production Approval') {
            when {
                expression { params.TARGET_ENV == 'prod' }
            }
            steps {
                input message: "prod ${params.TARGET_LIMIT}에 ${params.RELEASE} 배포",
                      ok: '배포', submitter: 'deploy-approvers'
            }
        }

        stage('Deploy') {
            steps {
                withCredentials([
                    sshUserPrivateKey(
                        credentialsId: "ansible-ssh-${params.TARGET_ENV}",
                        keyFileVariable: 'SSH_KEY_FILE',
                        usernameVariable: 'SSH_USER'
                    ),
                    file(credentialsId: "ansible-vault-${params.TARGET_ENV}",
                         variable: 'VAULT_PASS_FILE')
                ]) {
                    sh '''
                      set +x
                      set -eu
                      ansible-playbook -i "inventories/$TARGET_ENV/hosts.yml" rolling.yml \
                        --private-key "$SSH_KEY_FILE" --user "$SSH_USER" \
                        --vault-id "$TARGET_ENV@$VAULT_PASS_FILE" \
                        --limit "$TARGET_LIMIT" --tags "$TAGS" \
                        --forks 5 -e @ci-extra-vars.json
                    '''
                }
            }
        }
    }

    post {
        failure {
            echo '배포 실패: 이전 버전 복구 여부와 LB 상태를 확인하세요.'
        }
        always {
            archiveArtifacts artifacts: 'ci-extra-vars.json', allowEmptyArchive: true
        }
        cleanup {
            deleteDir()
        }
    }
}
```

</details>

`deploy-approvers`는 실제 Jenkins 사용자·그룹으로 바꾼다. 예제의 30분 제한에는 승인 대기 시간도 포함된다. `prod`를 선택하기 전에 해당 Inventory와 Credentials가 준비되어 있어야 한다.

### 4.3 실행 결과를 어떻게 해석할까?

04번 Playbook은 이전 버전 복구에 성공해도 새 버전 배포가 실패했다면 실패 코드를 전달한다. Jenkins에서도 빌드를 실패로 남겨 다음 배포 전에 원인을 확인할 수 있다. 실행 명령 뒤에 `|| true`를 붙이면 이 연결이 끊어진다.

`--list-hosts`는 대상 목록을 보여주는 기능이다. 대상이 0대여도 그것만으로 실패하지 않으므로, 운영 Pipeline에는 빈 대상을 거르는 검증도 추가한다. 예제는 등록된 `web01`과 `web`을 선택하는 구성을 가정한다.

`disableConcurrentBuilds()`는 같은 Job의 동시 실행을 막는다. 여러 Job이 같은 환경에 배포한다면 Lockable Resources 등으로 공유 잠금도 구성한다. Jenkins timeout이나 강제 중단은 Ansible 복구 완료를 보장하지 않으므로 중단 후 LB와 서버 상태를 확인한다.

> Credentials 사용 범위: 배포 Job과 Jenkinsfile을 수정하는 권한은 Secret 사용 권한과 함께 관리한다. 별도 하위 경로에서 실행할 때는 `withCredentials` 안에 `dir(...)`을 배치한다. 콘솔 마스킹만으로 다른 작업의 Secret 접근을 막을 수는 없다.

공식문서: [Pipeline Syntax](https://www.jenkins.io/doc/book/pipeline/syntax/), [Pipeline Input Step](https://www.jenkins.io/doc/pipeline/steps/pipeline-input-step/), [Lockable Resources](https://plugins.jenkins.io/lockable-resources/)

## 5. Ansible Plugin을 사용하면 무엇이 달라질까?

CLI 방식은 로컬에서 쓰던 명령을 그대로 옮기기 쉽다. Jenkins Ansible Plugin을 사용하면 명령 대신 `ansiblePlaybook` Step의 인자로 설정할 수 있다.

| 방식 | 작성하는 내용 | 준비할 것 |
| --- | --- | --- |
| CLI | `sh` 안의 `ansible-playbook` 명령 | Ansible 실행 환경, Credentials 바인딩 |
| Plugin | `ansiblePlaybook`의 인자 | 같은 실행 환경, Plugin과 실행 경로 설정 |

다음은 앞 Pipeline의 Deploy 단계를 Plugin 방식으로 바꾼 예다. 입력 검증과 사전 검증은 유지한다.

```groovy
ansiblePlaybook(
    playbook: 'rolling.yml',
    inventory: "inventories/${params.TARGET_ENV}/hosts.yml",
    credentialsId: "ansible-ssh-${params.TARGET_ENV}",
    vaultCredentialsId: "ansible-vault-${params.TARGET_ENV}",
    vaultTmpPath: '/var/lib/jenkins/ansible-secrets',
    hostKeyChecking: true,
    limit: params.TARGET_LIMIT,
    tags: params.TAGS,
    forks: 5,
    extraVars: [study_web_release: params.RELEASE]
)
```

Plugin을 설치해도 Agent에 Ansible 실행 파일까지 설치되지는 않는다. Agent의 `PATH` 또는 Jenkins Tools 설정에서 실행 파일을 찾을 수 있어야 한다.

`vaultCredentialsId`는 Secret file이나 Secret text를 받아 `--vault-password-file`로 전달한다. 여러 Vault ID를 명시적으로 조합하려면 CLI 방식이 더 직접적이다. 예제의 `vaultTmpPath`는 빌드 계정만 접근할 수 있는 디렉토리를 미리 준비한 경로다. Plugin의 기본 임시 경로는 workspace이므로 보관 위치도 확인한다.

공식문서: [Ansible Plugin](https://plugins.jenkins.io/ansible/), [ansiblePlaybook step](https://www.jenkins.io/doc/pipeline/steps/ansible/)

## 6. `ansible-lint`로 무엇을 확인할까?

배포 전에 발견할 수 있는 문제는 먼저 걸러내는 편이 좋다. `ansible-lint`는 Task 이름, 모듈 표기, 파일 권한 등 Playbook 작성 규칙을 검사한다. 구문 검사나 실제 배포와 확인하는 범위가 다르다.

| 검증 방법 | 주로 확인하는 것 | 이것만으로 알 수 없는 것 |
| --- | --- | --- |
| `ansible-lint` | 작성 규칙과 일반적인 실수 | 실제 서버 상태 |
| `--syntax-check` | Playbook 구문 | SSH·sudo·서비스 동작 |
| `--check --diff` | 지원 모듈의 예상 변경 | 전체 배포와 복구 성공 |
| 실습 환경 적용 | 실제 연결·변경·응답 | 모든 운영 장애 상황 |

```bash
ansible-lint --offline --profile basic site.yml secrets.yml rolling.yml
ansible-playbook -i inventories/dev/hosts.yml site.yml --syntax-check
ansible-playbook -i inventories/dev/hosts.yml site.yml --limit web01 --check --diff
```

위 check mode 명령은 `site.yml`에 적용한다. `rolling.yml`은 HAProxy 모듈이 check mode를 지원하지 않아 실제 실습으로 배포·복구를 검증해야 한다. Vault 파일이 있으면 검사 명령에도 복호화 수단을 전달한다.

`--offline`은 의존성 자동 설치 등을 생략하므로 필요한 Role과 Collection을 먼저 설치한다. 모든 네트워크를 차단하는 격리 옵션은 아니다. 학습은 `basic` Profile부터 시작하고, 팀의 작성 기준이 정해지면 더 엄격한 Profile로 확장할 수 있다.

공식문서: [Ansible Lint usage](https://docs.ansible.com/projects/lint/usage/), [Lint profiles](https://docs.ansible.com/projects/lint/profiles/), [Check and diff mode](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_checkmode.html)

## 7. 배포가 느릴 때 조정할 것

먼저 어디에서 시간이 걸리는지 나누어 본다. SSH 접속, Facts 수집, 패키지 설치, 연결 drain, Health Check 대기는 원인과 개선 방법이 다르다.

### 7.1 `forks`로 병렬 처리 수 조정하기

```ini
# ansible.cfg: 실습 환경에서 측정하며 조정
[defaults]
forks = 10
host_key_checking = True

[ssh_connection]
pipelining = True
```

`forks`는 Agent 자원과 원격 서버 부하를 보며 조정한다. 03번에서 봤듯이 `serial: 1`인 배포는 forks를 늘려도 한 배치에 한 대만 참여한다. 전체 Jenkinsfile의 `--forks 5`는 설정 파일의 `10`보다 우선한다.

### 7.2 SSH Pipelining으로 연결 작업 줄이기

위 설정의 `pipelining = True`는 모듈 실행에 필요한 임시 파일 전송 등의 연결 작업을 줄인다. 여러 작은 Task를 실행할 때 도움이 될 수 있다. 모든 파일 전송이 없어지는 것은 아니며, sudo의 `requiretty` 정책과 충돌할 수 있으므로 한 대에서 먼저 검증한다.

SSH의 `ControlMaster`·`ControlPersist` 설정은 연결 재사용에 사용된다. Ansible의 기본 SSH 옵션을 바꿀 때 기존 연결 재사용 설정을 덮어쓰지 않는지도 확인한다.

공식문서: [SSH connection plugin](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/ssh_connection.html), [Configuration precedence](https://docs.ansible.com/projects/ansible/latest/reference_appendices/general_precedence.html)

### 7.3 사용하지 않는 Facts 수집 줄이기

04번 예제는 OS 정보를 사용하지 않아 `gather_facts: false`로 두었다. 반대로 OS 종류나 메모리 정보를 조건으로 사용하는 Role이라면 Facts 수집을 유지해야 한다. Facts 캐시를 도입할 때는 값의 최신성을 고려하고 Secret은 캐시하지 않는다.

공식문서: [Facts and caching](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_vars_facts.html)

## 8. 스터디에서 확인할 질문

- Jenkins와 연결했을 때 Ansible Control Node는 어디일까?
- SSH Key와 Vault 비밀번호 파일은 각각 어떤 옵션으로 전달할까?
- Lint를 통과한 Playbook도 실습 환경에서 배포·복구를 확인해야 하는 이유는 무엇일까?

이전: [Rolling Deployment & Failure Handling](04-rolling-deployment-and-failure-handling.md)
