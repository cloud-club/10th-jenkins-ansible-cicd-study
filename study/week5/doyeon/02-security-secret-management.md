# Ansible에서 Secret을 안전하게 관리하는 방법

> 한 줄 요약: **Secret은 Git과 로그에 평문으로 남기지 않고, 실행할 때 필요한 권한을 가진 주체에게만 전달한다.**

자동화에는 비밀번호, API 토큰, SSH 개인키, 인증서 비밀번호처럼 노출되면 안 되는 값이 필요하다. 이런 값을 Secret이라고 한다.

Ansible은 서버 설정을 코드로 관리하므로, Secret도 Playbook·Role·변수 파일과 함께 다루게 된다. 이때 중요한 질문은 세 가지다.

```text
1. Secret을 어디에 저장할 것인가?
2. 배포 실행 시 누가 Secret을 복호화하거나 조회하는가?
3. 실행 로그와 대상 서버에서 Secret 노출을 어떻게 줄일 것인가?
```

---

## 1. Secret과 Vault 비밀번호는 다르다

두 값을 혼동하면 안 된다.

| 구분 | 의미 | 예시 |
|---|---|---|
| Secret | 애플리케이션이나 인프라가 실제로 사용하는 민감한 값 | DB 비밀번호, API 토큰 |
| Vault 비밀번호 | Secret을 암호화·복호화하는 열쇠 | `production` Vault의 비밀번호 |

```text
demo_db_password = demo-db-password
                └─ 애플리케이션 설정에 들어갈 Secret

Vault 비밀번호 = 암호문을 여는 열쇠
                └─ Git에 저장하면 안 됨
```

Vault 비밀번호가 노출되면, 그 비밀번호로 암호화한 여러 Secret을 함께 열 수 있다. 따라서 Vault 비밀번호는 일반 Secret보다 영향 범위가 더 클 수 있다.

---

## 2. Ansible Vault의 역할

Ansible Vault는 변수와 파일을 암호화하는 기능이다. 평문 Secret 대신 암호문을 Git에 저장할 수 있게 한다.

```text
Git
├─ Playbook, Role, 일반 변수
└─ Vault로 암호화된 Secret

배포 실행
→ Vault 비밀번호 제공
→ Ansible이 필요한 값만 복호화
→ 서버 설정에 반영
```

Vault는 저장 중인 데이터를 보호한다.

```text
data at rest
→ Git, 디스크에 저장된 암호문
→ Ansible Vault가 보호

data in use
→ Ansible이 실행 중 복호화한 값, Task 결과, 대상 서버의 설정 파일
→ no_log, 파일 권한, 접근 제어로 별도 보호
```

즉 Vault만 사용한다고 로그나 대상 서버에서 Secret이 자동으로 숨겨지는 것은 아니다.

---

## 3. 변수 하나를 암호화할지, 파일 전체를 암호화할지

Ansible Vault는 변수 단위와 파일 단위 암호화를 제공한다.

| 방식 | 명령 | 장점 | 고려할 점 |
|---|---|---|---|
| 변수 단위 | `ansible-vault encrypt_string` | 같은 파일의 일반 설정은 읽기 쉬움 | 변수값마다 관리해야 하며 `rekey`가 단순하지 않음 |
| 파일 단위 | `ansible-vault encrypt` | 변수명까지 포함해 파일 전체를 숨기고 `rekey`하기 좋음 | Git에서 내용을 바로 읽을 수 없음 |

### 변수 단위 암호화

```bash
ansible-vault encrypt_string \
  --vault-id production@prompt \
  --stdin-name demo_db_password
```

출력은 YAML 변수 형태다.

```yaml
demo_db_password: !vault |
          $ANSIBLE_VAULT;1.2;AES256;production
          암호문...
```

`!vault`는 Ansible에 이 값이 복호화가 필요한 암호문임을 알린다.

### 파일 전체 암호화

```bash
ansible-vault encrypt \
  --vault-id production@prompt \
  inventory/group_vars/production/vault.yml
```

파일 전체를 암호화하면 파일의 변수명과 내용이 모두 숨겨진다. 환경별 Secret을 별도 `vault.yml` 파일로 관리할 때 자주 쓰는 방식이다.

---

## 4. Vault ID: 환경별 Vault를 구분하는 이름표

Vault ID는 어떤 환경 또는 용도의 Vault 비밀번호를 사용할지 나타내는 라벨이다.

```text
dev         개발 환경 Secret
production  운영 환경 Secret
```

명령 형식은 다음과 같다.

```text
--vault-id 라벨@비밀번호_가져오는_방법
```

```bash
# 터미널에서 production Vault 비밀번호 입력
--vault-id production@prompt

# 로컬 파일에서 production Vault 비밀번호 읽기
--vault-id production@vault-password-production
```

암호문 헤더에는 Vault ID가 평문으로 보인다.

```text
$ANSIBLE_VAULT;1.2;AES256;production
```

여기서 `production`은 비밀번호가 아니라 힌트다. Vault ID가 같다고 Ansible이 항상 같은 비밀번호 사용을 강제하지는 않는다. 팀의 운영 규칙으로 `production` ID에는 하나의 정해진 비밀번호를 사용해야 한다.

여러 Vault ID를 운영한다면 `DEFAULT_VAULT_ID_MATCH` 설정으로, 암호문 헤더의 ID와 전달한 ID가 일치할 때만 복호화를 시도하도록 만들 수 있다. 이는 실수를 줄이는 설정이지 비밀번호 자체를 보호하는 접근 제어는 아니다.

---

## 5. Vault 비밀번호를 전달하는 방법

| 방식 | 예시 | 적합한 상황 |
|---|---|---|
| Prompt | `production@prompt` | 개인 실습, 수동 실행 |
| Password File | `production@vault-password-production` | 로컬 자동화 |
| Client Script | `production@vault-client.py` | Keychain·Secret Manager 연동 |
| Jenkins Credential | `production@"$VAULT_FILE"` | CI/CD 배포 |

### Password File

Vault 비밀번호는 한 줄로 저장한다.

```text
vault-password-production
└─ Vault 비밀번호 한 줄
```

Password File은 다음 원칙을 지켜야 한다.

```text
Git에 커밋하지 않는다.
읽기 권한을 소유자로 제한한다.
공유 Workspace에 장기 보관하지 않는다.
```

```bash
chmod 600 vault-password-production
```

### 인벤토리 그룹과 Vault 파일이 읽히는 범위

`group_vars/<그룹 이름>/` 아래의 변수 파일은 해당 그룹과 그 하위 그룹의 호스트에 적용된다. 따라서 그 안에 암호화된 `vault.yml`이 있으면, Playbook의 Task가 Secret 변수를 직접 사용하지 않아도 Ansible은 파일을 읽고 복호화를 준비한다.

이번 인벤토리는 다음 관계다.

```text
production
└── rolling_targets
    ├── app01
    ├── app02
    └── app03
```

`inventory/group_vars/production/vault.yml`에 암호문이 있으므로 `rolling_targets`를 대상으로 하는 단순 실행 전략 실습도 Vault 비밀번호 없이 실행하면 실패한다.

```text
Attempting to decrypt but no vault secrets found.
```

이 경우에는 Task가 Secret을 사용하지 않더라도 해당 환경의 Vault ID를 전달한다.

```bash
ansible-playbook playbooks/strategy-lab.yml \
  --vault-id production@vault-password-production
```

Vault 파일을 필요한 환경 그룹 아래에 두는 것은 환경별 Secret 범위를 분리하는 방법이다. 반대로 Secret이 전혀 필요 없는 독립 실습은 `production`의 하위 그룹이 아닌 별도 인벤토리 그룹을 대상으로 구성할 수 있다.

### Client Script

Client Script는 Ansible이 실행할 때 Keychain, 데이터베이스, HashiCorp Vault 같은 외부 저장소에서 Vault 비밀번호를 읽어 오는 프로그램이다.

```text
Ansible
→ Vault Password Client Script 실행
→ Keychain 또는 Secret Manager에서 Vault 비밀번호 조회
→ Ansible이 암호문 복호화
```

스크립트는 Vault 비밀번호를 표준 출력으로 전달하고, 여러 환경을 지원한다면 `--vault-id` 인자로 어떤 환경의 비밀번호를 원하는지 받는다.

---

## 6. `no_log`: 실행 중 Secret을 로그에서 숨기기

Secret을 사용하는 Task에는 `no_log: true`를 적용한다.

```yaml
- name: Deploy runtime configuration with secret
  ansible.builtin.template:
    src: runtime.env.j2
    dest: /etc/myapp/app.env
    owner: root
    group: root
    mode: "0600"
  no_log: true
```

`no_log`는 이 Task의 결과와 변수값이 Ansible 출력에 나타나지 않도록 한다.

하지만 다음은 별도로 막아야 한다.

```text
debug로 Secret 출력
shell/command에서 echo로 Secret 출력
평문 Secret을 -e 옵션에 넣기
대상 서버에서 권한 없이 Secret 파일을 읽을 수 있게 두기
```

Secret 파일은 웹 루트 밖에 두고, 실행 계정만 읽을 수 있는 권한을 설정한다.

```text
/etc/myapp/app.env  → 0600
/var/www/html        → Secret을 두지 않음
```

---

## 7. Jenkins Credentials와 Ansible Vault

Jenkins는 Secret을 Jenkinsfile에 직접 쓰지 않고 Credential ID로 참조한다.

| Credential 종류 | 용도 |
|---|---|
| SSH Username with private key | Jenkins/Ansible 관리 서버에서 대상 VM에 SSH 접속 |
| Secret file | Vault 비밀번호를 실행 중 임시 파일로 제공 |
| Secret text | API 토큰처럼 단일 문자열 전달 |

Pipeline에서 Vault Password File을 받는 흐름은 다음과 같다.

```text
Jenkins Credential Store
→ Secret file을 실행 중 임시 생성
→ 환경 변수 VAULT_FILE에 파일 경로 전달
→ ansible-playbook이 Vault 비밀번호 파일을 읽음
→ 작업 종료 후 Jenkins가 임시 파일 정리
```

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

이 예시의 원칙은 다음과 같다.

1. Jenkinsfile에는 Vault 비밀번호를 쓰지 않는다.
2. Groovy 문자열 보간 대신 셸 환경 변수를 사용한다.
3. `set +x`로 셸 명령 추적 출력을 끈다.
4. Ansible의 Secret 사용 Task에는 `no_log`를 적용한다.

---

## 8. External Secret Manager

Ansible Vault는 Git에 암호문을 저장하는 방식이다. External Secret Manager는 Secret을 별도 서비스에 보관하고 실행 시 API로 조회한다.

| 구분 | Ansible Vault | External Secret Manager |
|---|---|---|
| Secret 저장 위치 | Git의 암호문 파일 | 별도 Secret 관리 서비스 |
| 실행 시 필요한 것 | Vault 비밀번호 | 서비스 인증 권한·네트워크 |
| Secret 교체 | 암호문 수정 후 배포 | 서비스에서 rotation 가능 |
| 적합한 환경 | 소규모 자동화, 단순 CI | 다수 서비스, 권한 분리, 자동 rotation |

### HashiCorp Vault

HashiCorp Vault는 인증된 사용자나 워크로드에 정책 기반으로 Secret 접근 권한을 부여하는 Secret 관리 시스템이다. 정적 Secret뿐 아니라 짧은 수명의 동적 DB 계정을 생성하는 방식도 지원한다.

```text
Jenkins 또는 Ansible Controller 인증
→ 정책에 따라 필요한 Secret만 조회
→ 배포에 사용
→ 만료 또는 회수
```

### AWS Secrets Manager

AWS Secrets Manager는 DB 인증정보, API 키 등을 저장·조회·교체하는 AWS 서비스다. Ansible은 `amazon.aws.secretsmanager_secret` lookup으로 실행 시 Secret을 가져올 수 있다.

```yaml
db_password: >-
  {{ lookup('amazon.aws.secretsmanager_secret',
            'production/app/db-password',
            region='ap-northeast-2') }}
```

이 lookup은 대상 VM이 아니라 Ansible Controller에서 실행된다. 따라서 Controller에 `amazon.aws` Collection과 AWS SDK 의존성이 필요하고, Controller의 IAM 권한은 필요한 Secret 읽기로 최소화해야 한다.

---

## 9. 선택 기준

```text
개인 또는 소규모 실습
→ Ansible Vault + prompt 또는 로컬 Password File

Jenkins 기반 CI/CD
→ Ansible Vault + Jenkins Secret File Credential

여러 서비스와 환경, 자동 Secret rotation
→ HashiCorp Vault 또는 Cloud Secret Manager
```

어떤 방식을 선택하든 공통 원칙은 같다.

```text
평문 Secret을 Git에 저장하지 않는다.
평문 Secret을 명령줄 인자에 넣지 않는다.
Secret 사용 Task에는 no_log를 적용한다.
필요한 주체에만 최소 권한을 부여한다.
Secret과 Vault 비밀번호를 분리해서 관리한다.
```

---

## 10. 실습 기록: Jenkins에서 Vault와 SSH Credential 전달

Jenkins Pipeline은 Ansible을 실행하는 Controller 역할을 한다. 따라서 Pipeline에는 두 종류의 Credential이 필요했다.

| Jenkins Credential ID | 종류 | 사용 목적 |
|---|---|---|
| `ansible-vault-production` | Secret file | `vault.yml`을 복호화할 Vault 비밀번호 파일 전달 |
| `app-server-ssh-key` | SSH Username with private key | Jenkins Agent가 App VM에 SSH 접속 |

Vault 비밀번호 파일은 `withCredentials(file(...))`로, SSH 개인키는 `sshagent(...)`로 Pipeline 실행 중에만 전달한다.

```groovy
sshagent(credentials: ['app-server-ssh-key']) {
  withCredentials([
    file(credentialsId: 'ansible-vault-production', variable: 'VAULT_FILE')
  ]) {
    sh '''
      set +x
      ansible-playbook playbooks/rolling-deploy.yml \
        --vault-id production@"$VAULT_FILE"
    '''
  }
}
```

SSH 개인키에 passphrase가 설정되어 있다면 Jenkins Credential의 **Passphrase** 항목에도 같은 값을 등록해야 한다. 등록하지 않으면 Jenkins Agent의 `ssh-add`가 키를 잠금 해제할 수 없고 다음과 같이 실패한다.

```text
Enter passphrase for ...private_key...key:
```

passphrase는 개인키 파일을 보호하는 암호다. App VM 계정의 로그인 비밀번호나 Vault 비밀번호와는 다른 값이며, Git과 Jenkinsfile에 저장하지 않는다.

### SSH Host Key 검증

개인키를 올바르게 전달해도 Jenkins Agent가 App VM을 처음 만나는 경우 다음 오류가 날 수 있다.

```text
Host key verification failed.
```

이는 SSH가 서버의 신원을 확인하기 위해 `known_hosts`를 검사했지만, Jenkins Agent의 `~/.ssh/known_hosts`에 App VM의 host key가 없다는 뜻이다. 로컬 Mac의 `known_hosts`와 Jenkins Agent 컨테이너의 `known_hosts`는 서로 다른 파일이다.

실습에서는 Jenkins Agent 컨테이너의 `jenkins` 사용자에게 host key를 등록했다.

```bash
docker exec -u jenkins jenkins-agent1 sh -lc \
  'mkdir -p /home/jenkins/.ssh && chmod 700 /home/jenkins/.ssh && \
  ssh-keyscan -H <app01-ip> <app02-ip> <app03-ip> >> /home/jenkins/.ssh/known_hosts && \
  chmod 600 /home/jenkins/.ssh/known_hosts'
```

`ssh-keyscan` 결과를 바로 신뢰하는 방식은 최초 연결 시 위조 서버를 구별하지 못할 수 있다. 운영 환경에서는 VM 콘솔·클라우드 관리 화면 등 별도 신뢰 경로로 host key fingerprint를 확인한 뒤 `known_hosts`에 고정해야 한다. `host_key_checking=False`로 검증을 끄는 방식은 문제를 숨길 뿐 서버 신원 확인을 포기하므로 사용하지 않는다.

Jenkins Agent 컨테이너를 삭제하거나 새로 만들면 이 `known_hosts` 등록은 사라질 수 있다. 반복 가능한 운영 환경에서는 검증한 host key 목록을 Agent 이미지, Configuration as Code, 또는 안전하게 관리되는 Pipeline 준비 단계에 포함한다.

## 참고 문서

- [Ansible Vault 개요](https://docs.ansible.com/projects/ansible/latest/vault_guide/vault.html)
- [Vault 암호화 방식과 Vault ID](https://docs.ansible.com/projects/ansible/latest/vault_guide/vault_encrypting_content.html)
- [Vault Password 관리](https://docs.ansible.com/projects/ansible/latest/vault_guide/vault_managing_passwords.html)
- [Jenkins Credentials](https://www.jenkins.io/doc/book/using/using-credentials/)
- [Jenkinsfile에서 Credential 사용](https://www.jenkins.io/doc/book/pipeline/jenkinsfile/#handling-credentials)
- [HashiCorp Vault 개요](https://developer.hashicorp.com/vault/docs/about-vault/what-is-vault)
- [AWS Secrets Manager 개요](https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html)
- [Ansible AWS Secrets Manager Lookup](https://docs.ansible.com/projects/ansible/latest/collections/amazon/aws/secretsmanager_secret_lookup.html)
