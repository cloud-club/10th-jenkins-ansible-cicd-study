# Security & Secret Management

## 파일 단위 암호화

비밀번호 파일을 프로젝트 폴더 밖에 두었다. 레포에 함께 올라가면 암호화한 의미가 없다.

```
$ openssl rand -base64 32 > ~/.ansible/vault/dev.pass
$ chmod 600 ~/.ansible/vault/dev.pass
```

`vars.yml`(평문)과 `vault.yml`(암호화)을 나누는 패턴을 썼다. `vars.yml`에서 `vault_` 접두사가 붙은 변수를 참조하게 한다.

```yaml
# group_vars/web/vars.yml (평문)
db_password: "{{ vault_db_password }}"

# group_vars/web/vault.yml (암호화 대상)
vault_db_password: "W5-Vault-S3cret-7731"
```

```
$ ansible-vault encrypt group_vars/web/vault.yml --vault-id dev@...
Encryption successful
$ head -1 group_vars/web/vault.yml
$ANSIBLE_VAULT;1.2;AES256;dev
$ grep -rn "W5-Vault-S3cret-7731" group_vars roles *.yml; echo "grep exit: $?"
grep exit: 1
```

암호화된 파일을 열지 않아도 `vars.yml`을 grep하면 어떤 비밀이 존재하는지는 찾을 수 있다. 레포 안에는 평문이 남지 않는다(`grep exit: 1`은 일치 없음).

`--vault-id`에 `~` 대신 `$HOME`을 썼다. `dev@~/...`처럼 `~`가 단어 중간에 오면 셸이 홈 디렉터리로 확장하지 않는다.

### 비밀번호 없이 실행

```
$ ansible-playbook site.yml --limit web
PLAY [Web servers] ***
[ERROR]: Attempting to decrypt but no vault secrets found.
```

play가 시작되자마자, task를 하나도 실행하기 전에 멈춘다. 비밀을 못 풀면 아무것도 하지 않는다.

이 동작은 조회 명령에도 적용된다. web 그룹을 대상으로 하면 `group_vars/web/` 안의 `vault.yml`을 로드하므로, 로그 한 줄을 보려는 명령도 비밀번호가 없으면 막힌다.

```
$ ansible web -m command -a "cat /etc/webapp/app.conf"
[ERROR]: Attempting to decrypt but no vault secrets found.
```

web 서버에 무슨 작업이든 하려는 사람은 vault 비밀번호가 필요하다. 비밀번호를 가진 사람이 실제로 비밀이 필요한 사람보다 넓어진다.

### 배포 후 서버 상태

webapp Role이 비밀번호를 설정 파일에 써넣도록 task를 추가했다(`mode: "0600"`). 비밀번호를 주고 실행한 뒤 서버를 확인했다.

```
$ ansible web -m command -a "cat /etc/webapp/app.conf" --vault-id dev@...
node1 | CHANGED | rc=0 >>
db_password=W5-Vault-S3cret-7731
```

Vault는 레포에 있는 파일을 암호화할 뿐이다. 배포가 끝나면 비밀은 서버에 평문으로 존재한다. 서버에서 그 파일을 지키는 것은 파일 권한(`mode: "0600"`)이다.

## 노출 실험

`no_log`가 어디까지 막는지, verbose·debug·diff 모드에서 비밀이 어떻게 새는지 확인했다. 로그를 파일로 남기고 `grep -c`로 검출 횟수를 셌다.

### 조건별 검출

| 케이스 | 조건 | 검출 |
|---|---|---|
| A | `debug: var=db_password` | 1 |
| B | 일반 실행 | 0 |
| C | `-vvv` (template 배포) | 0 |
| D | `--diff` (template 배포) | 1 |
| E | no_log + `-vvv` + `--diff` | 0 |
| F | no_log + `ANSIBLE_DEBUG=1` | 0 |

A는 `debug` 모듈이 복호화된 값을 그대로 출력한 것이다. D는 `--diff`가 새로 배포하는 파일 내용을 보여준 것이다. `--diff`는 4주차에 "안전하게 변경 사항을 미리 보는 도구"로 소개했는데, 그 도구가 비밀까지 보여준다.

C와 F가 0으로 나온 것은 4주차 결과("`-vvv`와 `ANSIBLE_DEBUG`에서 각각 노출")와 어긋났다. 이 실험들은 `template` 모듈을 썼는데, 4주차 실험은 `debug`·`command`·`copy`를 썼다. 노출 여부가 모드가 아니라 비밀이 전달되는 경로에 달려 있을 가능성이 있어 경로별로 다시 측정했다.

### 경로별 측정

같은 비밀을 같은 서버에 쓰되 전달 방법만 세 가지로 달리했다. task를 태그로 하나씩 분리해 합계가 섞이지 않게 했다.

| 전달 경로 | `-vvv` | no_log + `-vvv` | no_log + `ANSIBLE_DEBUG` |
|---|---|---|---|
| template (파일 렌더링) | 0 | 0 | 0 |
| copy `content` (모듈 인자) | 0 | 0 | 0 |
| shell (명령 문자열) | 2 | 0 | 3 |

`copy content`도 모듈 인자지만 노출되지 않았다. copy는 내용을 임시 파일로 만들어 전송하므로 template과 같은 경로를 탄다. 기준은 "인자냐 파일이냐"가 아니라 "모듈이 그 값을 결과에 담아 돌려주느냐"다. shell은 실행한 명령(`cmd`)을 결과로 돌려주므로 비밀이 섞여 나온다.

shell이 새는 위치를 로그에서 확인했다.

- `-vvv`(no_log 없음): 모듈이 SSH로 돌려준 원본 JSON과 화면 결과의 `"cmd"` 필드.
- `ANSIBLE_DEBUG`(no_log 있음): 원본 JSON 외에 `_execute_module (... '_raw_params': 'echo db_password=...')`. 모듈을 호출할 때 넘긴 인자 자체.

`no_log`는 모듈이 결과를 돌려준 다음 그 결과를 화면에 내보내는 단계에서 가린다. `-vvv`의 원본 JSON 출력도 그 단계에 속해 no_log를 켜면 함께 가려진다. `ANSIBLE_DEBUG`는 그보다 아래 단계(모듈 호출·결과 수신)를 기록하므로 가리는 처리가 일어나기 전의 데이터를 찍는다.

### 4주차 결론 정정

4주차 문서는 "`-vvv`와 `ANSIBLE_DEBUG=1`에서 각각 4건 노출"을 근거로 "`no_log`는 verbose 모드로 우회된다"고 결론 내렸다. 당시 playbook에는 `no_log`가 없는 task가 섞여 있었고, 4건을 task별로 나누지 않고 합계로만 셌다.

4주차 playbook을 task별로 분리해 재측정했다(node1 한 대 기준).

| task | no_log | `-vvv` | `ANSIBLE_DEBUG` |
|---|---|---|---|
| plain debug | 없음 | 1 | 1 |
| debug + no_log | 있음 | 0 | 0 |
| command + environment + no_log | 있음 | 1 | 1 |
| copy content | 없음 | 0 | 0 |
| 한 대 합계 | | 2 | 2 |

4주차는 `hosts: webservers`(2대)를 대상으로 했으므로 두 배가 되어 각 4건이 된다. 4건 중 절반(plain debug)은 처음부터 `no_log`가 없던 task이고, 나머지 절반(environment)은 `no_log`를 걸었는데도 나왔다.

정정: "`-vvv`는 no_log를 우회한다"는 과장이었다. 정확히는 특정 경로로 전달된 값에 한해서다. `command + environment`가 `-vvv`에서 샌 이유는 `environment`로 지정한 값이 SSH 실행 명령줄에 붙기 때문이다.

```
# -vvv
<...> SSH: EXEC ssh ... (SECRET=SuperSecret123 포함)
# ANSIBLE_DEBUG
_low_level_execute_command(): executing: /bin/sh -c 'SECRET=SuperSecret123 /usr/bin/python3 ...'
```

이 실행 단계는 결과를 가리는 no_log보다 앞이다. 비밀이 `/bin/sh -c '...'`의 인자로 들어가므로, 실행되는 순간 대상 서버의 `ps` 결과에도 보일 수 있다(직접 확인하지 않은 추론). `environment`로 비밀을 넘기면 로그뿐 아니라 서버 쪽에도 노출 경로가 생긴다.

### 노출 경로 정리

| 비밀이 실리는 곳 | 예시 | `-vvv` + no_log | `ANSIBLE_DEBUG` + no_log |
|---|---|---|---|
| 모듈 결과 | shell의 `cmd` | 가려짐 | 노출 |
| SSH 실행 명령줄 | `environment` | 노출 | 노출 |
| 파일 전송 | template, copy `content` | 가려짐 | 가려짐 |
| 컨트롤 노드 내부 | debug `msg` | 가려짐 | 가려짐 |
| `--diff` | template 결과 | 노출 | — |
| 대상 서버 파일 | `/etc/webapp/app.conf` | 평문 | 평문 |

`no_log`는 우발적 노출을 줄이는 장치이고, 비밀이 실리는 위치에 따라 선별적으로 가린다. Vault는 저장 시점(레포)에서만 비밀을 지키고, 배포가 끝나면 비밀은 파일 권한 뒤에 평문으로 남는다.

## encrypt_string — 값 단위 암호화

haproxy 통계 페이지(`localhost:8404/stats`)에 인증을 걸면서 `encrypt_string`을 썼다.

```
$ ansible-vault encrypt_string --vault-id dev@... 'Stats-Pass-4410' --name 'haproxy_stats_password'
```

파일 전체가 아니라 값 하나만 암호화된다. 변수 이름은 평문이고 값 자리에 `!vault |` 블록이 들어간다.

```yaml
haproxy_stats_password: !vault |
          $ANSIBLE_VAULT;1.2;AES256;dev
          30633037...
```

비밀번호가 있을 때만 인증 줄을 넣도록 템플릿을 구성했다(기본값은 빈 문자열).

```jinja
{% if haproxy_stats_password %}
    stats auth {{ haproxy_stats_user }}:{{ haproxy_stats_password }}
{% endif %}
```

```
$ curl -s -o /dev/null -w "%{http_code}" localhost:8404/stats            → 401
$ curl -s -o /dev/null -w "%{http_code}" -u admin:Stats-Pass-4410 ...      → 200
```

### 파일 단위와 값 단위 비교

```
$ ansible-vault view group_vars/lb/vars.yml --vault-id dev@...
[ERROR]: Input is not vault encrypted data.
$ ansible lb -m debug -a "var=haproxy_stats_password" --vault-id dev@...
node3 | SUCCESS => { "haproxy_stats_password": "Stats-Pass-4410" }
```

파일 자체는 암호화된 것이 아니므로 `ansible-vault view`로 열 수 없다. Ansible을 통해 값을 불러와야 볼 수 있다.

| | 파일 단위 (`vault.yml`) | 값 단위 (`encrypt_string`) |
|---|---|---|
| 변경 이력 | 한 글자만 바꿔도 파일 전체가 바뀜. 리뷰어가 무엇이 바뀌었는지 알 수 없음 | 바뀐 변수 줄만 바뀜 |
| 열람 | `ansible-vault view` | Ansible로 불러와야 함 |
| 비밀번호 교체(`rekey`) | 명령 한 번 | 값마다 다시 암호화 |

파일 단위 암호화는 PR diff가 알아볼 수 없는 숫자 덩어리라 비밀 변경을 리뷰로 검토하기 어렵다.

### 파일 권한

이 비밀번호를 넣은 뒤 haproxy 설정 파일 권한을 확인했다.

```
$ ansible lb -m command -a "stat -c '%U:%G %a' /etc/haproxy/haproxy.cfg" --vault-id dev@...
root:root 644
$ ansible lb -m command -a "grep 'stats auth' /etc/haproxy/haproxy.cfg" --vault-id dev@...
    stats auth admin:Stats-Pass-4410
```

`mode: "0644"`는 설정에 비밀이 없던 초기에 정한 값이다. 지금은 `stats auth admin:Stats-Pass-4410`이 평문으로 들어가 서버의 모든 사용자가 읽을 수 있다. 소유자·그룹·권한을 조정했다.

```yaml
    owner: root
    group: haproxy
    mode: "0640"
```

haproxy는 root로 시작하며 설정을 읽으므로 일반 사용자 읽기 권한만 빼도 동작에는 문제가 없다. 적용 후 `root:haproxy 640`, 인증 요청은 `200`.

Basic 인증은 HTTP로 보내면 비밀번호가 base64로만 인코딩된 채 매 요청마다 전송된다. 운영 환경이라면 TLS가 필요하다.

## --vault-id 라벨

헤더에 붙는 `dev` 라벨이 접근 제한인지 단순 이름표인지 확인했다. prod용 비밀번호를 따로 만들고 dev·prod 라벨로 값을 하나씩 암호화한 뒤, 대상을 `localhost`로 해서 네 조건으로 실행했다.

| | 조건 | dev_secret | prod_secret |
|---|---|---|---|
| A | dev + prod 비밀번호 모두 | 읽힘 | 읽힘 |
| B | dev만 | 읽힘 | 실패 (ignored=1) |
| C | prod 비밀번호를 dev 라벨로 지정 | 실패 | 읽힘 (ignored=1) |
| D | C + `ANSIBLE_VAULT_ID_MATCH=1` | 실패 | 실패 (ignored=2) |

C가 핵심이다. prod 라벨이 붙은 값을 "dev라는 이름표를 단 prod 비밀번호"로 풀었다. 라벨은 어떤 비밀번호부터 시도할지 정하는 힌트일 뿐이고, 비밀번호가 맞으면 라벨이 달라도 풀린다. `VAULT_ID_MATCH`를 켜야(D) 라벨이 일치할 때만 시도한다. 다만 이것도 비밀번호를 가진 사람이 환경변수 하나만 끄면 사라지는 설정이다.

B는 play가 멈추지 않고 dev만 읽히고 prod만 실패했다(`ignored=1`). `encrypt_string` 값은 실제로 사용하는 순간에 복호화된다. 파일 단위 암호화가 play 시작 전에 전부 막혔던 것과 다르다.

dev와 prod의 분리는 라벨이 아니라 비밀번호 파일을 누가 갖고 있느냐로 정해진다. 한 job에 두 비밀번호가 다 들어 있으면 라벨이 있어도 분리는 없다.

## CI에서 vault 비밀번호 전달

Jenkins Credential에서 고를 수 있는 두 방식(파일·환경변수)을 Ansible 쪽에서 확인했다.

**방식 1 — 파일 경로**: `ANSIBLE_VAULT_PASSWORD_FILE` 환경변수에 파일 위치를 지정한다.

**방식 2 — 환경변수 + 스크립트**: vault 비밀번호 파일 자리에 실행 가능한 스크립트를 넣으면 Ansible이 스크립트를 실행해 출력을 비밀번호로 쓴다. 스크립트가 환경변수 값을 출력하게 했다.

컨트롤 노드에서 도는 task(`localhost`)는 ansible-playbook 프로세스의 자식이라 환경변수를 물려받는다. 앞부분만 잘라 확인했다.

| | 컨트롤 노드 환경변수에 보이는 것 | 코드가 비밀번호를 얻는 방법 | 원격 노드 |
|---|---|---|---|
| env 방식 | 비밀번호 값 (`VAULT_PASS=Q...`) | `env` 한 줄 | 0건 (안 넘어감) |
| file 방식 | 경로만 (`...=/Users/.../dev.pass`) | 경로를 읽으면 (`QlZemoU0...`) | — |

두 방식의 차이는 우발적 노출뿐이다. env 방식은 누가 디버깅하려고 `env`를 로그에 찍기만 해도 비밀번호가 새고, file 방식은 경로만 샌다. 컨트롤 노드에서 코드를 실행할 수 있는 사람에게는 둘 다 뚫린다. 이 환경변수는 원격 노드(node1)로 넘어가지 않는다(0건 확인).

## 비밀번호 교체(rekey) 중 사고

`rekey`로 비밀번호를 교체하려다 사고가 났다. 명령 순서를 잘못 짜서, rekey가 성공했는지 확인하지 않고 옛 비밀번호 파일을 새 파일로 덮어썼다.

```
$ ansible-vault rekey --vault-id dev@old --new-vault-id dev@new group_vars/web/vault.yml
[ERROR]: Failed to rekey ...: Decryption failed (no vault secrets were found that could decrypt).
```

rekey는 실패했는데 뒤이어 옛 비밀번호 파일을 덮어쓰는 명령이 실행되어, `group_vars/web/vault.yml`이 어떤 비밀번호로도 풀 수 없는 상태가 됐다. 실습용이라 평문(`W5-Vault-S3cret-7731`)을 알고 있어 재암호화로 복구했다.

원인을 확인하려 같은 조건(같은 라벨/다른 라벨, 프로젝트 폴더/`/tmp`, 원본 복사본)으로 세 번 재현했으나 모두 성공했다. 원인은 확정하지 못했다. 실패 당시 상태를 다시 확인하려면 옛 비밀번호로 그 파일을 열어야 하는데, 옛 비밀번호를 덮어쓰면서 원인 분석의 증거까지 함께 사라졌다.

정리: 새 키로 복호화되는 것을 확인하기 전에 옛 키를 폐기하지 않는다. 옛 키는 복구 수단이면서 원인 분석의 증거다. 이번 사고는 rekey 실패 자체보다, 실패를 확인하지 않고 다음 단계로 넘어간 절차에서 생겼다.

올바른 교체 절차:

1. 새 비밀번호를 다른 라벨(또는 `--new-vault-password-file`)로 지정해 rekey
2. 새 비밀번호로 `view`가 되는지 확인
3. 전체 playbook이 새 비밀번호로 도는지 확인
4. 그다음에 옛 비밀번호 파일 삭제

## External Secret Manager (개념)

실습은 하지 않고 개념만 정리한다. 비밀을 레포에 두지 않고, 실행 시점에 lookup 플러그인이 외부 저장소에서 가져오는 구조다.

```yaml
db_password: "{{ lookup('amazon.aws.secretsmanager_secret', 'prod/webapp/db') }}"
db_password: "{{ lookup('community.hashi_vault.vault_kv2_get', 'webapp/db').secret.password }}"
```

Vault 파일 방식보다 나아지는 점:

- **접근 통제**: 비밀마다 누가 읽을 수 있는지 정책으로 정한다. `--vault-id` 라벨의 "힌트일 뿐" 문제가 여기서 해소된다.
- **감사 기록**: 누가 언제 어떤 비밀을 읽었는지 남는다. AWS라면 `GetSecretValue` 호출이 CloudTrail에 기록된다.
- **교체·폐기**: 레포 수정 없이 중앙에서 처리한다. HashiCorp Vault는 동적 비밀도 지원한다.

나아지지 않는 점:

- 실행 중에는 여전히 컨트롤 노드 메모리에 평문으로 있다. 앞 노출 경로(shell 결과, environment, `ANSIBLE_DEBUG`, `--diff`, 서버 파일)는 그대로다.
- **Secret zero 문제**: 외부 저장소에 접근하려면 또 인증 정보가 필요하다. 그 인증 정보를 Jenkins에 넣으면 vault 비밀번호를 넣은 것과 구조가 같다. 문제가 없어지는 것이 아니라 위치가 옮겨간다.

Secret zero를 줄이는 방법은 저장된 비밀 대신 실행 환경 자체의 신원을 쓰는 것이다(EC2 IAM 인스턴스 프로파일, OIDC 등 짧게 유효한 자격 증명).

감사 기록이 남는다는 것은 탐지가 가능하다는 뜻이다. 평소 Jenkins 역할만 읽던 비밀을 처음 보는 주체가 읽거나 비정상적인 시간에 대량으로 읽으면 CloudTrail 기반으로 잡을 수 있다. Vault 파일 방식은 비밀번호 파일을 누가 읽었는지 기록이 남지 않는다. 통제는 둘 다 뚫릴 수 있지만 탐지 가능성에서 차이가 난다.

## 참고 자료

- [Ansible Vault](https://docs.ansible.com/ansible/latest/vault_guide/index.html)
- [Ansible - Protecting sensitive data with no_log](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_advanced_syntax.html)
- [Ansible - Using vault in playbooks (multiple vault passwords, vault IDs)](https://docs.ansible.com/ansible/latest/vault_guide/vault_managing_passwords.html)
