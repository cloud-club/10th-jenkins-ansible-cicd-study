# Security & Secret Management

## 1. 비밀번호도 Inventory에 적으면 될까?

01번에서는 포트와 배포 버전을 변수로 분리했다. 그렇다면 DB 비밀번호도 같은 파일에 적으면 될까? 동작은 하지만, 저장소를 읽을 수 있는 사람에게 비밀번호까지 보이게 된다.

**Ansible Vault는 변수나 파일을 암호화해서 저장하는 기능이다.** Git에는 암호문을 올리고, 실행할 때만 복호화 비밀번호를 전달한다. 팀원은 같은 설정을 공유하면서도 비밀번호 원문은 별도로 관리할 수 있다.

```text
Git: 암호화된 변수 파일    Jenkins Credentials: 복호화 비밀번호
             └───────────┬───────────┘
                  Ansible 실행 시 복호화
                         ↓
                필요한 Task에서 값 사용
```

여기에는 두 가지 비밀번호가 등장한다. `study_app_password`는 애플리케이션이 사용할 비밀번호이고, **Vault 비밀번호는 그 값을 담은 암호문을 여는 열쇠**다. 두 값을 구분하면 이후의 CLI와 Jenkins 설정을 이해하기 쉽다.

공식문서: [Ansible Vault](https://docs.ansible.com/projects/ansible/latest/vault_guide/vault.html)

## 2. 파일 전체를 암호화해 보기

### 2.1 일반 설정과 Secret을 나눈다

[01번 예제](01-role-based-architecture.md)의 `group_vars/web.yml`을 다음과 같이 나누어 보자. 기존 내용을 `web/main.yml`로 옮긴 뒤 기존 `web.yml`은 제거해 같은 그룹의 설정이 중복되지 않게 한다.

```text
inventories/dev/
├── hosts.yml
└── group_vars/web/
    ├── main.yml     # 일반 설정
    └── vault.yml    # Secret만 저장하고 전체 암호화
```

일반 설정에는 포트와 버전을 두고, 비밀번호는 암호화할 변수 이름을 참조한다.

```yaml
# main.yml: 평문으로 관리할 값
study_web_port: 8080
study_web_release: v1
study_app_password: "{{ vault_study_app_password }}"
```

이렇게 하면 Role에서는 `study_app_password`라는 이름을 사용하고, 실제 값은 `vault_study_app_password`에서 가져오게 된다. 변수 이름에 `vault_`를 붙이는 것은 암호화된 값의 출처를 드러내기 위한 작성 관례다.

### 2.2 암호화된 파일을 만든다

새 파일을 만들 때는 `create`를 사용한다.

```bash
ansible-vault create --vault-id dev@prompt inventories/dev/group_vars/web/vault.yml
```

Vault 비밀번호를 입력하면 에디터가 열린다. 다음 형태의 YAML을 작성하되, 값은 실제 실습용 비밀번호로 바꾼다.

```yaml
# 에디터에서 입력할 내용의 형태
vault_study_app_password: 'replace-with-your-lab-password'
```

저장하고 나면 파일에는 평문 YAML 대신 암호문이 들어간다. 이후 값을 수정할 때는 `edit`로 연다.

```bash
ansible-vault edit --vault-id dev@prompt inventories/dev/group_vars/web/vault.yml
```

이미 평문 파일을 만들어 둔 경우에는 `create` 대신 `encrypt`를 선택한다. 다음 명령은 위 절차에 추가로 실행하는 단계가 아니다.

```bash
ansible-vault encrypt --vault-id dev@prompt inventories/dev/group_vars/web/vault.yml
```

평문 파일은 암호화한 뒤 Git에 올린다. 먼저 커밋했다면 나중에 암호화해도 이전 이력에는 원문이 남는다. 에디터의 백업·swap 파일에도 평문이 남을 수 있으므로 Secret 편집 시 함께 확인한다.

공식문서: [Encrypting files](https://docs.ansible.com/projects/ansible/latest/vault_guide/vault_encrypting_content.html#encrypting-files-with-ansible-vault), [ansible-vault CLI](https://docs.ansible.com/projects/ansible/latest/cli/ansible-vault.html)

## 3. 값 하나만 암호화할 수도 있다

설정 파일 대부분은 읽을 수 있게 두고 비밀번호만 감추고 싶다면 `encrypt_string`을 사용한다. 2절의 파일 전체 암호화와 비교해서 선택하는 방식이다.

```bash
ansible-vault encrypt_string --vault-id dev@prompt \
  --name vault_study_app_password --prompt
```

Vault 비밀번호와 암호화할 값을 차례로 입력하면 `!vault` 형식의 YAML이 출력된다. 이 결과를 변수 파일에 넣으면 된다. `--prompt`를 사용하면 Secret을 명령 인자에 직접 적지 않아도 된다.

| 선택 | 적합한 상황 | Git에서 보이는 내용 |
| --- | --- | --- |
| 파일 전체 암호화 | Secret을 한 파일로 모아 관리 | 파일 전체가 암호문 |
| 값 하나씩 암호화 | 일반 설정과 Secret을 함께 관리 | 변수 이름·일반 설정은 보이고 일부 값만 암호문 |

> 비밀번호 교체: 암호화된 파일은 `ansible-vault rekey`로 Vault 비밀번호를 바꿀 수 있다. 개별 `!vault` 값은 다시 암호화해야 한다. 어느 방식이든 DB나 API의 실제 비밀번호를 바꾸는 작업과는 별개다.

공식문서: [Encrypting individual variables](https://docs.ansible.com/projects/ansible/latest/vault_guide/vault_encrypting_content.html#encrypting-individual-variables-with-ansible-vault)

## 4. 실행할 때 복호화 비밀번호 전달하기

암호화된 변수를 사용하는 Playbook에는 복호화 수단을 알려주어야 한다. 로컬에서는 비밀번호를 직접 입력하는 방식으로 시작하면 된다.

```bash
ansible-playbook -i inventories/dev/hosts.yml site.yml --vault-id dev@prompt
```

`--vault-id`의 형식은 `이름@비밀번호를 얻을 곳`이다. `dev@prompt`는 dev라는 이름을 붙이고 프롬프트에서 비밀번호를 입력받겠다는 뜻이다. 이름은 암호문과 사용할 키를 구분하는 데 도움이 된다.

CI에서는 사람이 입력할 수 없으므로 **Vault Password File**을 사용한다. 비밀번호만 담긴 파일을 저장소 밖에 준비하고, 필요한 실행 계정만 읽게 한다.

```bash
# VAULT_PASS_FILE에는 비밀번호 파일의 경로가 들어 있다
ansible-playbook -i inventories/dev/hosts.yml site.yml \
  --vault-id "dev@$VAULT_PASS_FILE"
```

여러 키가 필요한 경우 `--vault-id`를 반복할 수 있다. 다만 기본 설정에서 이름은 키 선택의 힌트이므로, `dev`와 `prod`라는 이름만으로 접근 권한이 나뉘지는 않는다. 환경별 비밀번호와 해당 비밀번호를 읽을 권한을 따로 관리한다.

실행 가능한 Password Client Script를 지정하는 방법도 있다. 이 경우 Ansible은 스크립트의 표준 출력에서 비밀번호를 읽으므로 그 출력에 진단 로그가 섞이지 않게 한다.

공식문서: [Using encrypted variables and files](https://docs.ansible.com/projects/ansible/latest/vault_guide/vault_using_encrypted_content.html), [Managing vault passwords](https://docs.ansible.com/projects/ansible/latest/vault_guide/vault_managing_passwords.html)

## 5. 암호화했는데 왜 `no_log`도 필요할까?

Vault는 **저장된 데이터**를 보호한다. Ansible이 실행 중 값을 복호화한 뒤에는 Task 출력이나 설정 파일에 원문이 나타날 수 있다. 그래서 저장, 실행 로그, 대상 파일을 각각 보호한다.

| 보호할 곳 | 사용하는 방법 |
| --- | --- |
| Git의 변수 파일 | Ansible Vault |
| Task 실행 결과 | `no_log: true` |
| 변경 전후 파일 내용 | `diff: false` |
| 서버에 저장한 Secret 파일 | 소유자와 파일 권한 |

아래 `secrets.yml`은 이 차이를 확인하는 독립 실습이다. 01번의 Nginx가 읽는 파일은 아니며, 애플리케이션 설정 파일을 배치하는 상황을 가정한다.

```yaml
# secrets.yml
- name: Install the private application configuration
  hosts: web
  become: true
  tasks:
    - name: Create a private configuration directory
      ansible.builtin.file:
        path: /etc/ansible-study
        state: directory
        owner: root
        group: root
        mode: '0700'

    - name: Write the application secret
      ansible.builtin.copy:
        content: "{{ {'password': study_app_password} | to_nice_json }}\n"
        dest: /etc/ansible-study/app.json
        owner: root
        group: root
        mode: '0600'
      no_log: true
      diff: false
```

`no_log`는 이 Task의 출력을 숨기고, `diff: false`는 변경 전후 내용을 표시하지 않게 한다. `0600`은 생성한 파일을 소유자만 읽고 쓸 수 있게 한다. 실제 서비스가 읽어야 할 때는 해당 서비스 계정에 맞게 소유자와 권한을 정한다.

```bash
ansible-playbook -i inventories/dev/hosts.yml secrets.yml --vault-id dev@prompt
```

다른 Task에서 `debug`로 같은 값을 출력하면 다시 노출된다. 따라서 Secret을 사용하는 Task에도 `no_log`를 적용하고, `ansible-vault view`로 원문을 출력하거나 `decrypt`로 평문 파일을 만드는 작업은 CI의 확인 절차에 넣지 않는다.

공식문서: [Logging Ansible output](https://docs.ansible.com/projects/ansible/latest/reference_appendices/logging.html), [Diff mode](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_checkmode.html#using-diff-mode), [copy module](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/copy_module.html)

## 6. Jenkins에서는 Credentials로 전달한다

Jenkins에는 Vault 비밀번호 파일을 **Secret file** 타입으로 등록할 수 있다. Credential ID를 `ansible-vault-dev`로 정했다면 Pipeline의 `steps`에서 다음처럼 사용한다. Agent의 Ansible과 SSH 인증은 준비되어 있다고 가정한다.

```groovy
withCredentials([
    file(credentialsId: 'ansible-vault-dev', variable: 'VAULT_PASS_FILE')
]) {
    sh '''
      set +x
      ansible-playbook -i inventories/dev/hosts.yml secrets.yml \
        --vault-id "dev@$VAULT_PASS_FILE"
    '''
}
```

`withCredentials` 안에서는 `VAULT_PASS_FILE`에 임시 비밀번호 파일의 경로가 들어간다. Ansible은 그 파일을 읽어 복호화하고, 블록이 끝나면 바인딩이 해제된다. 비밀번호를 저장소나 명령문에 직접 적을 필요가 없다.

`sh`의 작은따옴표 세 개는 Groovy가 Secret을 먼저 문자열에 끼워 넣지 않고 Shell에서 환경 변수로 읽게 하기 위한 것이다. `set +x`는 실행 명령의 추적 출력을 끈다. 마스킹만으로 접근을 막을 수는 없으므로 이 Credentials를 사용하는 Job과 Agent에는 신뢰하는 코드만 실행한다.

> 하위 경로에서 실행한다면 `withCredentials` 안에 `dir(...)`을 둔다. 반대 순서로 배치하면 Secret 파일이 사용자가 탐색할 수 있는 하위 workspace에 만들어질 수 있다.

SSH Key를 함께 전달하는 전체 Pipeline은 [05번 문서](05-jenkins-cicd-integration-and-operations.md)에서 살펴본다.

공식문서: [Credentials Binding](https://www.jenkins.io/doc/pipeline/steps/credentials-binding/)

## 7. 외부 Secret Manager를 사용하면 무엇이 달라질까?

Secret을 Git의 암호문으로 관리하는 대신, 실행할 때 외부 서비스에서 가져올 수도 있다. **HashiCorp Vault는 Ansible Vault와 별개의 서비스**다.

| 방식 | 값이 저장되는 곳 | Ansible에 필요한 것 |
| --- | --- | --- |
| Ansible Vault | 저장소의 암호문 | 복호화 비밀번호 |
| HashiCorp Vault | Vault 서버 | 지정 경로를 읽을 인증 정보 |
| AWS Secrets Manager | AWS 서비스 | Secret 조회 권한이 있는 AWS 인증 |

아래 두 예제는 외부 저장소를 사용하는 경우의 대안이다. 둘을 모두 실행할 필요는 없다. Lookup은 Ansible Control Node에서 실행되므로 Jenkins와 연결할 때는 **Agent에 라이브러리·인증·네트워크 접근을 준비한다.**

### 7.1 HashiCorp Vault에서 읽기

`community.hashi_vault` Collection과 호환되는 `hvac` 라이브러리를 설치한다. `VAULT_ADDR`와 조회 권한을 가진 `VAULT_TOKEN`을 Agent 환경에 제공했다고 가정한다.

```yaml
# 기존 Play의 tasks에 넣는 대안: Ansible Vault 변수 대신 외부 Secret 사용
- name: Read the application password from Vault
  ansible.builtin.set_fact:
    study_app_password: >-
      {{ lookup('community.hashi_vault.vault_kv2_get',
                'study/dev/app', engine_mount_point='secret')['secret']['password'] }}
    cacheable: false
  no_log: true
```

이 코드는 `secret`이라는 KV v2 저장소에서 `study/dev/app` 데이터를 읽고 `password` 값을 꺼낸다. 경로에 `secret`이나 `/data/`를 다시 붙이지 않는다. 조회 결과를 사용하는 Task에도 `no_log`를 적용한다. 운영 환경에서는 AppRole·JWT 등 환경에 맞는 인증 방식을 선택할 수 있다.

공식문서: [vault_kv2_get lookup](https://docs.ansible.com/projects/ansible/latest/collections/community/hashi_vault/vault_kv2_get_lookup.html)

### 7.2 AWS Secrets Manager에서 읽기

`amazon.aws` Collection과 호환되는 `boto3`, `botocore`를 설치한다. Agent의 IAM Role 등으로 AWS 인증을 준비하고, Secret에는 `password` 키가 있는 JSON 문자열을 저장했다고 가정한다.

```yaml
- name: Read the application password from AWS Secrets Manager
  ansible.builtin.set_fact:
    study_app_password: >-
      {{ (lookup('amazon.aws.secretsmanager_secret',
                 'study/dev/app', region='ap-northeast-2') | from_json)['password'] }}
    cacheable: false
  no_log: true
```

Lookup 결과를 `from_json`으로 변환한 뒤 `password`를 꺼낸다. 해당 Secret의 `secretsmanager:GetSecretValue` 권한이 필요하며, 고객 관리 KMS 키를 사용하면 `kms:Decrypt` 권한도 필요하다. 조회에 실패하면 배포를 멈추고 인증과 경로를 확인한다.

공식문서: [secretsmanager_secret lookup](https://docs.ansible.com/projects/ansible/latest/collections/amazon/aws/secretsmanager_secret_lookup.html), [AWS GetSecretValue](https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html)

## 8. 스터디에서 확인할 질문

- Vault 비밀번호와 애플리케이션 비밀번호는 각각 무엇에 사용될까?
- Vault로 암호화한 값을 쓰는 Task에도 `no_log`가 필요한 이유는 무엇일까?
- Jenkins에서 외부 Secret Lookup이 실패하면 Agent와 웹 서버 중 어디부터 확인할까?

이전: [Role-Based Architecture](01-role-based-architecture.md) · 다음: [Multi-Host Execution & Orchestration](03-multi-host-execution-and-orchestration.md)
