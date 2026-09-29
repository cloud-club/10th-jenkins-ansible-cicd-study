# 5. Jenkins CI/CD Integration & Operations

## 1. Jenkins Agent 실행 환경

Ansible은 Jenkins Controller가 아니라 전용 Agent에서 실행하는 것이 좋다. Controller는 빌드 코드와 자격 증명에 직접 노출되는 범위를 줄이고, Agent 이미지에는 필요한 버전의 도구를 고정한다.

필요 요소:

- Python 및 `ansible-core`
- `ansible-lint`
- `requirements.yml`에 정의된 Collection과 Role
- 대상 서버로 연결할 네트워크 경로
- SSH client와 known hosts 정책

CI와 로컬 환경의 Ansible 버전 및 Collection 구성이 다르면 같은 Playbook도 다르게 동작할 수 있다. Agent 환경을 이미지 또는 설치 스크립트로 재현 가능하게 관리한다.

## 2. Declarative Pipeline 예시

```groovy
pipeline {
  agent { label 'ansible' }

  parameters {
    choice(name: 'ENVIRONMENT', choices: ['staging', 'production'])
    string(name: 'LIMIT', defaultValue: 'web')
    string(name: 'TARGET_VERSION', defaultValue: '')
    booleanParam(name: 'CHECK_MODE', defaultValue: false)
  }

  stages {
    stage('Install dependencies') {
      steps {
        sh 'ansible-galaxy install -r requirements.yml'
      }
    }

    stage('Lint') {
      steps {
        sh 'ansible-lint'
      }
    }

    stage('Deploy') {
      steps {
        withCredentials([
          sshUserPrivateKey(credentialsId: 'ansible-ssh', keyFileVariable: 'SSH_KEY'),
          file(credentialsId: 'ansible-vault-prod', variable: 'VAULT_FILE')
        ]) {
          sh '''
            set -eu
            test -n "$TARGET_VERSION"

            check_arg=""
            if [ "$CHECK_MODE" = "true" ]; then
              check_arg="--check"
            fi

            ansible-playbook \
              -i "inventories/$ENVIRONMENT/hosts.yml" \
              deploy.yml \
              --limit "$LIMIT" \
              --private-key "$SSH_KEY" \
              --vault-id "prod@$VAULT_FILE" \
              --extra-vars "target_version=$TARGET_VERSION" \
              $check_arg
          '''
        }
      }
    }
  }
}
```

실제 운영에서는 자유 입력 파라미터를 그대로 셸 명령에 붙이지 않는다. choice 파라미터, 허용 목록, 정규식 검증을 사용해 명령 주입과 잘못된 대상 선택을 막는다.

## 3. Jenkins Parameter 연결

| Jenkins Parameter | Ansible 옵션 | 용도 |
|---|---|---|
| 환경 | `-i inventories/...` | inventory 선택 |
| 배포 대상 | `--limit` | 일부 그룹·호스트만 실행 |
| 작업 종류 | `--tags`, `--skip-tags` | 선택적 task 실행 |
| 버전 | `-e target_version=...` | 실행 시 변수 전달 |
| 사전 점검 | `--check` | 변경 예상 확인 |

주의 사항:

- `--limit`은 오타로 대상이 0대가 되거나 예상보다 넓어질 수 있다.
- 태그를 남용하면 원래 필요했던 선행 task나 handler가 빠질 수 있다.
- `-e`는 변수 우선순위가 매우 높다.
- 빈 문자열도 변수 정의로 취급될 수 있으므로 필수 파라미터를 먼저 검증한다.
- check mode가 실제 외부 API나 명령의 변경을 완벽히 예측하지 못할 수 있다.

## 4. ansible-lint

```bash
ansible-lint
```

정적 분석은 다음 문제를 배포 전에 발견하는 데 도움을 준다.

- Fully Qualified Collection Name 미사용
- 멱등성이 불분명한 `command`, `shell`
- task 이름 누락
- 잘못된 파일 권한 표현
- 위험한 최신 버전 설치 방식
- YAML 스타일 및 구조 문제

Lint 통과가 실행 성공이나 무중단을 보장하지는 않는다. 문법 검사, Molecule 또는 테스트 환경 실행, canary 검증과 함께 사용한다.

## 5. CLI와 Jenkins Ansible Plugin 비교

| 구분 | CLI (`sh`) | `ansiblePlaybook` Step |
|---|---|---|
| 장점 | 표준 CLI와 같고 로컬 재현이 쉬움 | Jenkinsfile에서 옵션을 구조화 가능 |
| 단점 | 문자열 조립과 입력 검증을 직접 처리 | Plugin 버전·문법에 의존 |
| 적합한 경우 | 실행 흐름을 명확히 통제 | 조직에서 Plugin 사용법을 표준화 |

Plugin을 사용해도 내부적으로 Ansible을 실행한다. 보안, Vault, inventory, 변수 우선순위 문제를 Plugin이 대신 해결해 주는 것은 아니다.

## 6. 성능 최적화

```ini
[defaults]
forks = 20

[ssh_connection]
pipelining = True
```

- `forks`: 동시에 처리할 호스트 수를 늘린다.
- SSH pipelining: 불필요한 파일 전송과 연결 작업을 줄일 수 있다.
- fact가 필요 없다면 `gather_facts: false`를 고려한다.
- 긴 작업에는 SSH 연결 재사용 설정이 도움이 된다.

성능 옵션은 운영 환경에서 점진적으로 조정한다. pipelining은 대상 서버의 권한 상승 정책과 충돌할 수 있고, 높은 forks는 Control Node와 대상 시스템에 부하를 줄 수 있다.

## 7. 운영 체크리스트

- [ ] Agent의 Ansible·Python·Collection 버전이 고정되어 있는가?
- [ ] Controller에서 일반 빌드를 실행하지 않는가?
- [ ] SSH Key와 Vault 비밀번호가 Jenkins Credentials에 있는가?
- [ ] 파라미터가 허용 목록으로 검증되는가?
- [ ] `ansible-lint`와 syntax check를 통과했는가?
- [ ] 운영 배포에 승인 또는 보호된 브랜치 정책이 있는가?
- [ ] 배포 후 Health Check와 외부 모니터링을 확인하는가?
- [ ] 누가 어떤 버전을 배포했는지 기록되는가?

