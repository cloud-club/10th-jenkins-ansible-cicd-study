# Multibranch Pipeline

## 핵심 개념

---

Multibranch Pipeline은 SCM을 Scan하여 Jenkinsfile이 존재하는 Branch와 Pull Request 또는 Merge Request를 자동으로 발견하고 각각의 Job을 생성한다.

```
Git Repository
├── main
│   └── Jenkinsfile → main Job
├── develop
│   └── Jenkinsfile → develop Job
└── Pull Request #15
    └── Jenkinsfile → PR-15 Job
```

일반 Pipeline에서는 관리자가 Repository와 Branch를 직접 지정한다. Multibranch Pipeline에서는 Branch의 생성과 삭제, PR 생성과 갱신에 맞춰 Jenkins Job도 자동으로 관리된다.

## 전체 실행 흐름

---

```
Developer Push / Pull Request
            ↓
      GitHub 또는 GitLab
            ↓ Webhook
     Jenkins Branch Source
            ↓
        SCM Indexing
            ↓
 Jenkinsfile이 있는 Branch 탐색
            ↓
 Branch / PR별 Pipeline Job 생성
            ↓
      Build / Test / Analysis
            ↓
 GitHub/GitLab Status Feedback
```

# 2-1. SCM Organization Scanning과 Jenkinsfile 자동 감지

---

### Multibranch Pipeline

- 하나의 Repository를 대상으로 한다.
- Branch, PR/MR, Tag를 탐색한다.
- Jenkinsfile이 있는 항목만 Pipeline Job으로 관리한다.
- Branch마다 서로 다른 Jenkinsfile을 사용할 수도 있다.

### Organization Folder

- GitHub Organization 또는 GitLab Group 전체를 대상으로 한다.
- Repository를 자동으로 찾는다.
- 각 Repository 안에서 Branch와 PR/MR을 다시 탐색한다.
- Repository 수가 많은 조직에서 Job을 일일이 생성하지 않아도 된다.

```
GitHub Organization
├── service-a → Multibranch Pipeline
├── service-b → Multibranch Pipeline
└── service-c → Multibranch Pipeline
```

## 주요 환경 변수

---

- **BRANCH_NAME**: Jenkins가 인식한 Branch 또는 PR Job 이름
- **CHANGE_ID**: PR/MR 번호
- **CHANGE_BRANCH**: PR/MR의 Source Branch
- **CHANGE_TARGET**: PR/MR의 Target Branch
- **CHANGE_URL**: PR/MR URL
- **CHANGE_AUTHOR**: PR/MR 작성자
- **CHANGE_TITLE**: PR/MR 제목
- **TAG_NAME**: Tag Build인 경우 Tag 이름

```groovy
stage('PR Verification') {
    when {
        changeRequest target: 'main'
    }

    steps {
        echo "PR #${env.CHANGE_ID}"
        echo "${env.CHANGE_BRANCH} → ${env.CHANGE_TARGET}"
        sh './gradlew check'
    }
}
```

CHANGE_ID가 존재하면 일반 Branch Build가 아니라 PR/MR Build라고 판단할 수 있다.

## GitHub 연동

---

필요한 주요 Plugin:

- GitHub Branch Source
- Pipeline: Multibranch
- Credentials
- 선택 사항: GitHub Checks

구성 순서:

1. Jenkins에 GitHub Credential을 등록한다.
2. Jenkins에서 Multibranch Pipeline을 생성한다.
3. Branch Sources에 GitHub Repository를 추가한다.
4. Branch와 Pull Request 탐색 전략을 설정한다.
5. Script Path를 Jenkinsfile로 지정한다.
6. GitHub Webhook을 연결한다.
7. Scan Multibranch Pipeline Now를 실행한다.
8. Branch Push와 PR 생성 시 Job이 자동 생성되는지 확인한다.

일반적인 GitHub Webhook Endpoint:

```
https://jenkins.example.com/github-webhook/
```

확인 사항:

- Jenkins URL을 GitHub에서 접근할 수 있는가?
- HTTPS 인증서가 유효한가?
- Reverse Proxy가 Webhook 요청을 차단하지 않는가?
- GitHub Credential의 권한이 필요한 범위로 제한되어 있는가?
- Webhook Recent Deliveries에서 응답 코드를 확인했는가?

## GitLab 연동

---

필요한 주요 Plugin:

- GitLab Branch Source
- GitLab API
- Pipeline: Multibranch

GitLab Branch Source는 Branch, Merge Request, Tag를 탐색할 수 있다.

일반적인 GitLab Webhook Endpoint:

```
https://jenkins.example.com/gitlab-webhook/post
```

주요 Event:

- Push event
- Merge request event
- Tag event
- 필요한 경우 Note event

GitLab에서는 Secret Token으로 Webhook 요청을 검증한다. Plugin 설정에서 Webhook 자동 관리를 활성화할 수도 있다.

## SCM Scan과 Webhook

---

### SCM Scan

```
Jenkins가 일정 주기로 SCM 조회
        ↓
새 Repository / Branch / PR 탐색
        ↓
Job 생성, 갱신 또는 정리
```

- Webhook을 놓쳐도 다음 Scan에서 복구할 수 있다.
- 주기가 짧으면 SCM API 호출과 Controller 부하가 증가한다.
- 변경 사항 반영이 Webhook보다 늦다.

### Webhook

```
Git Push 또는 PR 갱신
        ↓
SCM이 Jenkins로 Event 전송
        ↓
해당 Pipeline 실행 또는 Indexing
```

- 변경에 빠르게 반응한다.
- 불필요한 Polling을 줄인다.
- 운영에서는 Webhook을 기본으로 두고 낮은 빈도의 정기 Scan을 복구 수단으로 둘 수 있다.
- ㄱ깃랩에 젠킨슨 웹훅 URL을 등록한다

# 2-2. PR Build·검증과 Status Check Feedback

---

```
Jenkins Build 시작
        ↓
pending / in_progress
        ↓
Build / Test / Analysis
        ↓
success / failure
        ↓
GitHub 또는 GitLab의 Merge 가능 여부 결정
```

GitHub Branch Source는 Status API 알림을 제공한다. GitHub Checks Plugin을 사용하면 Check Run 형태로 더 풍부한 결과를 표시할 수 있다.

확인 사항:

- Branch Protection의 Required Check 이름이 Jenkins가 전송하는 Context와 일치하는가?
- Check 이름 변경으로 기존 Branch Protection 규칙이 깨지지 않았는가?
- GitHub Checks와 Branch Source Status가 중복 생성되지 않는가?
- Jenkins가 성공했지만 Status 전송만 실패한 경우를 확인할 수 있는가?
- Required Check가 PR Head Commit에 연결되어 있는가?

GitHub Checks Plugin을 Branch Source Status와 함께 사용할 때는 Skip GitHub Branch Source notifications 설정 여부를 확인한다.

GitLab Branch Source에서도 Pipeline Status 알림을 제공하며, 필요하면 Skip pipeline status notifications 옵션으로 전송을 끌 수 있다.

## Multibranch Jenkinsfile 예시

---

```groovy
pipeline {
    agent {
        label 'linux && java21'
    }

    options {
        timestamps()
        timeout(time: 30, unit: 'MINUTES')
        disableConcurrentBuilds(abortPrevious: true)
        buildDiscarder(logRotator(numToKeepStr: '20'))
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
                echo "BRANCH_NAME=${env.BRANCH_NAME}"
                echo "CHANGE_ID=${env.CHANGE_ID ?: 'N/A'}"
                echo "CHANGE_TARGET=${env.CHANGE_TARGET ?: 'N/A'}"
            }
        }

        stage('Build') {
            steps {
                sh './gradlew --no-daemon clean assemble'
            }
        }

        stage('PR Verification') {
            when {
                changeRequest()
            }

            parallel {
                stage('Unit Test') {
                    steps {
                        sh './gradlew --no-daemon test'
                    }
                }

                stage('Static Analysis') {
                    steps {
                        sh './gradlew --no-daemon checkstyleMain'
                    }
                }
            }
        }

        stage('Main Verification') {
            when {
                branch 'main'
            }
            steps {
                sh './gradlew --no-daemon check'
            }
        }

        stage('Publish') {
            when {
                branch 'main'
            }
            steps {
                sh './scripts/publish.sh'
            }
        }
    }

    post {
        always {
            junit testResults: 'build/test-results/**/*.xml',
                  allowEmptyResults: true
        }
        failure {
            echo "실패: ${env.BUILD_URL}"
        }
    }
}
```

# 2-3. Concurrency와 Branch 전략

---

같은 변경 사항이 Branch Job과 PR Job에서 중복 실행될 수 있다.

```
feature/login Build
        +
PR-15 Build
```

PR이 존재하는 Branch를 별도 Branch Job으로 실행할 필요가 없다면 다음과 같은 전략을 사용한다.

```
Branches
└── Only branches that are not also filed as PRs

Pull Requests
└── Discover pull requests from origin
```

Fork PR은 신뢰 수준을 별도로 판단한다.

- Fork PR에는 배포 Credential을 제공하지 않는다.
- 신뢰할 수 없는 작성자의 Jenkinsfile이 Trusted Library 또는 Secret에 접근하지 못하게 한다.
- PR Head를 빌드할지, Target Branch와 임시 Merge한 결과를 빌드할지 결정한다.
- 실제 Merge 가능성 검증이 목적이라면 Target Branch와 합쳐진 결과를 검사하는 전략을 고려한다.

## PR 중복 빌드 취소

---

개발자가 PR에 커밋을 연속으로 Push하면 이전 커밋의 검사는 가치가 낮아질 수 있다.

### 이전 빌드 즉시 취소

```groovy
options {
    disableConcurrentBuilds(abortPrevious: true)
}
```

- 새 빌드가 시작되면 같은 PR Job의 이전 빌드를 중단한다.
- 최신 Commit 결과만 중요한 PR 검증에 적합하다.
- Agent와 외부 테스트 환경 사용량을 줄일 수 있다.

### Milestone

```groovy
stage('Build') {
    steps {
        sh './gradlew build'
        milestone 10
    }
}

stage('Deploy Approval') {
    steps {
        input message: '배포하시겠습니까?'
        milestone 20
    }
}
```

- 여러 Build의 동시 실행을 허용하면서 중요 지점의 통과 순서를 제어한다.
- 새 Build가 먼저 Milestone을 통과하면 이전 Build는 해당 지점을 넘어가지 못한다.
- 승인 대기가 있는 CD Pipeline이나 오래된 Build의 뒤늦은 배포를 막을 때 유용하다.

## 문제 상황별 확인 위치

---

### Webhook은 성공했지만 Build가 시작되지 않음

- Webhook Event 종류가 Push 또는 PR/MR Event로 설정되어 있는지 확인한다.
- Jenkins System Log와 Multibranch Scan Log를 확인한다.
- Repository URL이 Branch Source 설정과 일치하는지 확인한다.
- 해당 Branch에 Jenkinsfile이 존재하는지 확인한다.
- Branch 탐색 Filter에 의해 제외되지 않았는지 확인한다.

### PR Job이 두 개 생김

- Branch Build와 PR Build가 동시에 탐색되고 있는지 확인한다.
- Only branches that are not also filed as PRs 전략을 검토한다.

### Status Check가 PR에 표시되지 않음

- Jenkins Credential의 Status/Checks 권한을 확인한다.
- Build 대상 SHA와 PR Head SHA가 일치하는지 확인한다.
- GitHub Branch Source 대신 일반 Git SCM으로 임시 Merge Commit을 Checkout하고 있지 않은지 확인한다.

## 확인 질문

---

1. 일반 Pipeline과 Multibranch Pipeline은 Job 생성 책임이 어떻게 다른가?
    - **답변:** 일반 Pipeline은 관리자가 Repository와 Branch를 지정하고 Job을 직접 구성한다. 반면 Multibranch Pipeline은 SCM을 Scan하여 `Jenkinsfile`이 존재하는 Branch와 PR/MR을 발견하고 각각의 Pipeline Job을 자동으로 생성·관리한다.
2. Webhook과 정기 SCM Scan을 함께 사용하는 이유는 무엇인가?
    - **답변:** Webhook은 Push나 PR/MR 변경에 즉시 반응하기 위한 주 실행 수단이고, 정기 SCM Scan은 Webhook 누락이나 Jenkins 일시 장애 등으로 이벤트를 놓쳤을 때 Branch·PR 상태를 다시 탐색해 복구하기 위한 보완 수단이다.
3. PR Head Build와 Target Branch Merge Build는 무엇을 각각 검증하는가?
    - **답변:** PR Head Build는 PR의 Source Branch 자체가 정상적으로 빌드·테스트되는지를 검증한다. Target Branch Merge Build는 해당 변경 사항을 `main` 같은 Target Branch에 합쳤을 때 충돌이나 통합 테스트 실패가 발생하지 않는지를 검증한다.
4. disableConcurrentBuilds와 milestone은 취소 시점이 어떻게 다른가?
    - **답변:** `disableConcurrentBuilds(abortPrevious: true)`는 새로운 빌드가 시작될 때 같은 Job의 이전 실행을 즉시 중단한다. `milestone`은 여러 빌드의 동시 실행을 허용하되, 더 최신 빌드가 특정 Milestone을 먼저 통과하면 오래된 빌드가 그 지점을 이후로 진행하지 못하게 한다.
5. Fork PR에 Credential을 제공하면 왜 위험한가?
    - **답변:** Fork PR의 `Jenkinsfile`과 실행 코드는 외부 작성자가 수정할 수 있으므로, Credential이 주입되면 악의적인 코드가 Secret, 배포 키, 토큰 등을 출력하거나 외부로 전송할 수 있다. 따라서 신뢰되지 않은 Fork PR에는 운영·배포 Credential을 제공하지 않는 것이 원칙이다.

## 참고 자료

---

- [Jenkins 공식 문서 - Branches and Pull Requests[1]](https://www.jenkins.io/doc/book/pipeline/multibranch/)
- [GitHub Branch Source Plugin[2]](https://plugins.jenkins.io/github-branch-source/)
- [GitHub Plugin Webhook[3]](https://plugins.jenkins.io/github/)
- [GitHub Checks Plugin[4]](https://plugins.jenkins.io/github-checks/)
- [GitHub Commit Status API[5]](https://docs.github.com/en/rest/commits/statuses)
- [GitLab Branch Source Plugin[6]](https://plugins.jenkins.io/gitlab-branch-source/)
- [GitLab Webhook Events[7]](https://docs.gitlab.com/user/project/integrations/webhook_events/)
- [Pipeline Milestone Step[8]](https://plugins.jenkins.io/pipeline-milestone-step/)