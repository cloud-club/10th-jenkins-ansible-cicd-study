# 2. Security & Secret Management

## 1. Ansible Vault의 역할

Ansible Vault는 Git 저장소에 들어가는 변수나 파일을 암호화한다. 저장소 유출 시 평문 Secret이 바로 노출되는 것을 막는 장치이지, 대상 서버에 배포된 Secret까지 자동으로 보호하는 도구는 아니다.

## 2. 파일 단위 암호화

```bash
ansible-vault encrypt group_vars/prod/vault.yml
ansible-vault view group_vars/prod/vault.yml
ansible-vault edit group_vars/prod/vault.yml
ansible-vault decrypt group_vars/prod/vault.yml
```

평문 변수와 암호화 변수를 분리하면 어떤 설정이 있는지는 쉽게 읽으면서 실제 값은 숨길 수 있다.

```yaml
# group_vars/prod/vars.yml
db_user: app
db_password: "{{ vault_db_password }}"
```

```yaml
# group_vars/prod/vault.yml — 이 파일을 암호화
vault_db_password: change-me
```

암호화 파일에는 `vault_` 접두사를 붙이면 일반 변수와 구분하기 쉽다.

## 3. 값 단위 암호화

```bash
ansible-vault encrypt_string 'change-me' --name 'db_password'
```

출력된 `!vault` 값을 YAML에 넣을 수 있다.

```yaml
db_password: !vault |
  $ANSIBLE_VAULT;1.1;AES256
  6638...
```

| 방식 | 장점 | 단점 |
|---|---|---|
| 파일 단위 | 파일 전체가 가려져 구조까지 보호 | 일반 변수와 함께 보기 어려움 |
| 값 단위 | 평문 설정과 함께 관리 가능 | Secret 존재와 변수명은 보임 |

## 4. 여러 환경은 vault-id로 분리

```bash
ansible-playbook site.yml \
  --vault-id dev@/secure/dev.pass \
  --vault-id prod@/secure/prod.pass
```

개발·운영의 암호 키를 분리하면 개발용 비밀번호를 아는 사람이 운영 Secret까지 풀 수 없게 만들 수 있다.

## 5. Vault Password File

```bash
chmod 600 /secure/prod.pass
ansible-playbook site.yml --vault-password-file /secure/prod.pass
```

주의 사항:

- 비밀번호 파일을 Git에 커밋하지 않는다.
- 파일 권한을 최소화한다.
- 공용 Jenkins Agent에 영구 파일로 두지 않는다.
- 로그에 파일 내용을 출력하지 않는다.
- 가능하면 빌드가 끝날 때 삭제되는 임시 Credential 파일로 전달한다.

## 6. no_log로 실행 로그 보호

```yaml
- name: Configure database password
  ansible.builtin.template:
    src: app.conf.j2
    dest: /etc/myapp/app.conf
    owner: root
    group: root
    mode: "0600"
  no_log: true
```

`no_log: true`는 task 결과가 콘솔에 표시되는 것을 막는다. 다만 다음 문제까지 해결하지는 않는다.

- 대상 서버의 평문 파일
- 애플리케이션 자체 로그
- 외부 시스템으로 전송된 값
- Secret을 포함한 셸 명령이나 별도 디버그 출력

따라서 Secret을 `debug`로 출력하지 말고, 셸 명령 문자열에 직접 넣는 것도 피한다. `--diff` 사용 시 템플릿의 Secret이 diff에 나타날 수 있으므로 Secret을 다루는 task에는 특히 주의한다.

## 7. Jenkins Credentials와 연결

Jenkins에는 다음과 같이 저장할 수 있다.

| Secret | 권장 Credential 형태 | Ansible 전달 방식 |
|---|---|---|
| SSH 개인 키 | SSH Username with private key | `--private-key` |
| Vault 비밀번호 | Secret file | `--vault-password-file` 또는 `--vault-id` |

개념 예시:

```groovy
withCredentials([
  sshUserPrivateKey(credentialsId: 'ansible-ssh', keyFileVariable: 'SSH_KEY'),
  file(credentialsId: 'ansible-vault-prod', variable: 'VAULT_FILE')
]) {
  sh '''
    ansible-playbook -i inventories/prod site.yml \
      --private-key "$SSH_KEY" \
      --vault-id "prod@$VAULT_FILE"
  '''
}
```

Groovy 문자열 보간으로 Secret을 명령 문자열에 미리 삽입하지 않도록 `sh` 본문은 작은따옴표 계열을 사용한다.

## 8. External Secret Manager

HashiCorp Vault, AWS Secrets Manager 같은 외부 저장소를 사용하면 Secret을 Git에 암호문으로도 저장하지 않고 실행 시점에 조회할 수 있다.

```text
Jenkins/Ansible → 짧은 수명의 인증 → Secret Manager → 실행 시 Secret 조회
```

장점은 중앙 회전, 접근 감사, 짧은 수명의 자격 증명이다. 대신 네트워크 장애, 인증 정책, 조회 권한, 캐시·재시도 정책까지 운영해야 한다.

## 9. 정리

- Vault는 저장소의 Secret을 보호한다.
- `no_log`는 로그 노출을 줄이지만 만능 방어가 아니다.
- CI에는 Secret 값보다 임시 파일 경로를 전달하는 방식이 관리하기 쉽다.
- 규모가 커지면 중앙 Secret Manager와 짧은 수명 인증을 고려한다.

