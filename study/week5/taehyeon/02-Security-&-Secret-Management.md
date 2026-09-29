# 02-Security-&-Secret-Management

## 2. Ansible에서 Secret을 어떻게 관리할까?

---

> **비밀번호, API Key, DB 계정 같은 민감정보를 평문 YAML이나 Git에 그대로 넣지 않는다.**
> 

Ansible에서는 Secret을 보통 **Ansible Vault를 중심으로 관리**하고, 규모가 커지면 AWS Secrets Manager, HashiCorp Vault , jenkins Credentials 같은 외부 Secret Store와 연동

```
Git Repository
  └── 암호화된 Secret (Ansible Vault)

Jenkins Credentials
  └── Vault Password
        │
        ▼
ansible-playbook 실행 시 복호화
        │
        ▼
Managed Node에 필요한 값 적용
```

> Ansible Vault는 **저장된 데이터(Data at Rest)를 암호화**하는 기능이다. 실행 시 복호화된 Secret이 Log나 명령행에 노출되지 않도록 별도 관리가 필요하다.
> 

### 2-1. 파일 전체 암호화

---

Ansible Vault

- Ansible에서 비밀번호, API key, 인증서 키 같은 Secret 값을 암호화해서 관리하는 기능

암호화하기(encrypt)

```bash
ansible-vault encrypt vault.yml
```

```

$ANSIBLE_VAULT;1.1;AES256663864393637343331343935...
```

내용 확인(view)

```bash
ansible-vault view vault.yml
```

편집(edit)

```bash
ansible-vault edit vault.yml
```

### 2-2. 특정 문자열만 암호화: encrypt_string

---

파일 전체가 아니라 특정 `Variable 값만 Vault 형식`으로 만들 수도 있다.

```bash
ansible-vault encrypt_string --name 'db_password'
```

결과는 다음과 같은 형태로 Variable 파일에 저장된다.

```yaml
db_password: !vault |
  $ANSIBLE_VAULT;1.1;AES256
  ...
```

파일 구조와 Variable 이름은 읽을 수 있게 두고 **값만 암호화하고 싶을 때** 유용하다.

### 2-3. --vault-id

---

> Vault에 이름표를 붙이고, 그 Vault의 비밀번호를 어디서 가져올지도 기정하는 기능
각각 어떤 비밀번호로 복호화할지 지정하는 옵션(환경별로 다르게 관리하기 위해)
> 

@뒤에 올 수 있는 방식(Vault 비밀번호를 얻는 방법)

- prompt : 실행할 때 터미널에서 직접 비밀번호 입력
- 비밀번호 파일(@prod-password : ansible이 비밀번호 파일을 복호화해서 사용
- 실행가능한 스크립트(@my-vault-password-client.py) : 스크립트 실행결과에서 읽음

```
prod @ prompt
│       │
│       └─ Vault 비밀번호를 어디서 받을지
│          prompt = 실행할 때 직접 입력
│
└─ Vault ID(이름표)
```

```bash
ansible-vault encrypt --vault-id prod@prompt vault.yml
```

Playbook 실행:

```bash
ansible-playbook playbooks/deploy.yml -i inventories/prod/hosts.yml --vault-id prod@prompt
```

Password File을 사용한다면:

```bash
ansible-playbook playbooks/deploy.yml   -i inventories/prod/hosts.yml   --vault-id prod@/secure/path/prod-vault-password
```

여러 Vault가 필요하면 `--vault-id`를 여러 번 전달할 수 있다.

### 2-4. Vault Password File

---

> Ansible Vault를 복호화할 비밀번호를 저장해두는 파일
> 

```bash
ansible-playbook site.yml \
  --vault-id prod@~/.ansible/prod-vault-pass
```

중요한 점은 **Password File 자체가 Secret**이라는 것이다.

왜 씀?

- CI/CD에서 사람이 매번 비밀번호를 주입할 수 없기 떄문
- jenkins → credential에 저장 → 실행 시 임시 password File 생성 → ansible-playbook --vault-id prod@파일

주의 사항

- Git Repository에 Commit하지 않는다.
- 파일 권한을 최소화한다.
- Jenkins Workspace에 임시 생성했다면 실행 후 삭제한다.
- 가능하면 Jenkins Credentials나 Secret Manager에서 실행 시점에 주입한다.

### 2-5. no_log

---

> Ansible 실행 로그에 민감한 값이 노출되지 않도록 숨기는 옵션
> 

```yaml
- name: DB 계정 생성
  ansible.builtin.command:
    cmd: create-user --password "{{ db_password }}"
  no_log: true
```

`no_log: true`를 사용하면 해당 Task 결과가 Console Log에 노출되는 것을 줄일 수 있다.

### 2-6. Jenkins Credentials와 Ansible Vault

---

CI/CD에서는 다음 구조로 연결할 수 있다.

```
Jenkins Credentials
 ├── SSH Private Key
 └── Vault Password
        │
        ▼
Jenkins Agent
        │
        ├── SSH Key → Managed Node 접속
        └── Vault Password → Vault 복호화
```

실생순서

```
Jenkins Pipeline 실행
        ↓
Jenkins Credentials에서
Vault Password 가져옴
        ↓
ansible-playbook 실행
        ↓
Ansible Vault 복호화
        ↓
DB Password/API Key 등을 사용
        ↓
Managed Node 배포
```

CLI 방식에서는 Jenkins Secret Text를 임시 Password File로 만든 뒤 `--vault-password-file`에 전달할 수 있다.

Jenkins Ansible Plugin을 사용하는 경우에는 별도의 **Vault Credentials**를 설정하고 Pipeline의 `vaultCredentialsId`를 통해 전달할 수도 있다.

### 2-7. External Secret Manager

---

운영 규모가 커지면 Secret 자체를 Repository의 Vault 암호문으로 관리하는 대신, **HashiCorp Vault / AWS Secrets Manager 같은 외부 Secret Manager를 Source of Truth로 두는 방식**도 사용할 수 있다.

```
Ansible
   │
   ├── Lookup Plugin / Collection
   │
   ▼
External Secret Manager
   │
   └── 실행 시 Secret 조회
```

장점:

- Secret Rotation을 중앙에서 관리할 수 있다.
- Repository에 Secret 원문이나 장기간 유지되는 Vault Password를 둘 필요가 줄어든다.
- 애플리케이션/환경별 접근 권한을 분리하기 쉽다.

다만 Secret Manager에 접근하기 위한 **인증 주체와 권한 자체는 여전히 안전하게 관리**해야 한다.

### 2-8. 여기서 생각해볼 질문

---

1. Ansible Vault와 Password Manager/Secret Manager는 어떤 차이가 있는가?
2. Vault로 암호화했는데도 `no_log`가 필요한 이유는?
3. DEV와 PROD Vault Password를 분리하면 어떤 장점이 있는가?
4. Vault Password File을 Repository에 함께 저장하면 왜 의미가 없어지는가?
5. Jenkins에서 Secret을 전달할 때 Workspace와 Console Log를 왜 같이 확인해야 할까?

### 2-9. 참고 자료

---

- [Ansible 공식 문서 - Ansible Vault](https://docs.ansible.com/projects/ansible/latest/vault_guide/vault.html)
- [Ansible 공식 문서 - Encrypting content](https://docs.ansible.com/projects/ansible/latest/vault_guide/vault_encrypting_content.html)
- [Ansible 공식 문서 - Using encrypted content](https://docs.ansible.com/projects/ansible/latest/vault_guide/vault_using_encrypted_content.html)
- [Ansible 공식 문서 - Managing Vault Passwords](https://docs.ansible.com/projects/ansible/latest/vault_guide/vault_managing_passwords.html)
- [Jenkins Ansible Plugin](https://plugins.jenkins.io/ansible/)