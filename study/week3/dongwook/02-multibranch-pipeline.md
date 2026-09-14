# Multibranch Pipeline

## 1. 문서 범위

다음 내용을 다룬다.

- Multibranch Pipeline의 개념과 동작 방식
- branch, pull request, merge request, tag를 Jenkins job으로 자동 관리하는 구조
- repository 안의 `Jenkinsfile` 자동 감지
- SCM Branch Source Plugin의 역할
- GitHub Branch Source Plugin 기반 PR 빌드와 status check 피드백
- GitLab Branch Source Plugin 기반 MR 빌드, webhook, pipeline status 피드백
- Organization Folder를 통한 GitHub Organization, GitLab Group/Subgroup 스캐닝

## 2. Multibranch Pipeline이란?

Multibranch Pipeline은 하나의 repository 안에 있는 여러 branch, PR, MR, tag를 Jenkins가 자동으로 발견하고, 각각을 별도의 Pipeline job처럼 관리하는 Jenkins job 유형이다.

일반 Pipeline job에서는 사용자가 job 하나를 만들고 SCM, branch, Jenkinsfile 위치를 직접 지정하는 경우가 많다. 반면 Multibranch Pipeline에서는 Jenkins가 repository를 스캔해서 `Jenkinsfile`이 있는 branch나 PR을 자동으로 찾아 하위 job을 만든다.

| 구분 | 일반 Pipeline | Multibranch Pipeline |
| --- | --- | --- |
| 관리 단위 | 보통 job 1개 | branch/PR/MR/tag별 하위 job |
| Jenkinsfile 감지 | job 설정에서 지정 | branch마다 자동 감지 |
| branch 추가/삭제 대응 | 수동 설정 필요 가능 | scan 결과에 따라 자동 생성/삭제 |
| PR/MR 검증 | 별도 플러그인/설정 필요 | Branch Source Plugin으로 자연스럽게 처리 |
| 추천 상황 | 단순 고정 branch 빌드 | 여러 branch/PR을 자동 검증해야 하는 프로젝트 |

핵심은 "repository 안에 `Jenkinsfile`이 있으면 Jenkins가 그 branch를 Pipeline으로 인식한다"는 점이다.

## 3. 왜 Multibranch Pipeline을 쓰는가?

Multibranch Pipeline을 쓰면 branch마다 Jenkins job을 따로 만들지 않아도 된다. 개발자가 새 branch를 만들고 `Jenkinsfile`을 push하면 Jenkins가 scan을 통해 이를 발견하고 자동으로 Pipeline을 만든다.

주요 장점은 다음과 같다.

- branch별로 서로 다른 `Jenkinsfile`을 사용할 수 있다.
- feature branch, release branch, main branch를 자동으로 분리 관리할 수 있다.
- PR/MR 생성 시 자동으로 검증 빌드를 실행할 수 있다.
- PR/MR 빌드 결과를 GitHub/GitLab에 status로 되돌려줄 수 있다.
- branch 삭제 또는 `Jenkinsfile` 제거 시 Jenkins job도 정리 대상이 된다.
- Organization Folder와 함께 쓰면 여러 repository도 자동 관리할 수 있다.

## 4. 기본 동작 흐름

Multibranch Pipeline의 기본 흐름은 다음과 같다.

1. Jenkins에 Multibranch Pipeline job을 만든다.
2. Branch Source에 GitHub, GitLab, Git 등을 연결한다.
3. Jenkins가 repository를 scan한다.
4. 각 branch, PR, MR, tag에 `Jenkinsfile`이 있는지 확인한다.
5. `Jenkinsfile`이 있으면 해당 항목을 하위 Pipeline job으로 만든다.
6. push, PR/MR 생성, tag push 같은 SCM 이벤트가 들어오면 다시 scan하거나 build를 시작한다.
7. build 결과를 Jenkins UI와 SCM provider의 commit status/status check로 표시한다.

간단히 표현하면 다음과 같다.

```text
SCM Repository
  ├─ main / Jenkinsfile       -> Jenkins job: main
  ├─ feature/login / Jenkinsfile -> Jenkins job: feature-login
  ├─ PR-15 / Jenkinsfile      -> Jenkins job: PR-15
  └─ tag v1.0.0 / Jenkinsfile -> Jenkins job: tag-v1.0.0
```

## 5. Jenkinsfile 자동 감지

Multibranch Pipeline은 기본적으로 branch의 root directory에 있는 `Jenkinsfile`을 찾는다. `Jenkinsfile`이 있는 branch만 Pipeline job으로 관리된다.

GitHub Branch Source 공식 가이드에서도 Multibranch Pipeline은 repository를 scan해서 branch, pull request, tag에 대해 Pipeline project를 만들며, branch마다 같은 Jenkinsfile을 반드시 사용할 필요는 없다고 설명한다.

즉, 아래처럼 branch별로 다른 Pipeline 흐름을 둘 수 있다.

```text
main
  └─ Jenkinsfile        -> 운영 배포 포함

develop
  └─ Jenkinsfile        -> 통합 테스트 포함

feature/login
  └─ Jenkinsfile        -> 빌드와 단위 테스트만 실행
```

`Jenkinsfile`이 삭제되면 해당 branch는 더 이상 Pipeline 대상으로 보지 않을 수 있고, orphaned item 전략에 따라 Jenkins 내부 job이 정리된다.

## 6. Multibranch Pipeline 생성 절차

Jenkins 공식 문서 기준 기본 생성 흐름은 다음과 같다.

1. Jenkins 홈에서 `New Item`을 선택한다.
2. 이름을 입력하고 `Multibranch Pipeline`을 선택한다.
3. `Branch Sources`에서 SCM source를 추가한다.
4. GitHub, GitLab, Git 등 사용할 provider를 선택한다.
5. repository URL, credentials, owner/project 등을 설정한다.
6. 필요한 Behaviours 또는 Traits를 설정한다.
7. 저장하면 Jenkins가 repository를 scan한다.
8. `Jenkinsfile`이 있는 branch/PR/MR/tag에 대해 하위 job이 생성된다.

주의할 점은 Jenkins job 이름에 공백이 있으면 일부 스크립트나 경로 처리에서 문제가 생길 수 있다는 것이다. 가능하면 `my-service-ci`처럼 단순한 이름을 쓰는 편이 안전하다.

## 7. 중요한 개념 정리

### 7.1 Branch Source

Branch Source는 Jenkins가 어느 SCM provider에서 branch, PR, MR, tag 정보를 가져올지 정의하는 설정이다.

예시는 다음과 같다.

| Branch Source | 설명 |
| --- | --- |
| Git | 일반 Git repository를 직접 scan |
| GitHub | GitHub repository/organization의 branch와 PR을 scan |
| GitLab Project | GitLab 단일 project의 branch/MR/tag를 scan |
| GitLab Group | GitLab user/group/subgroup 아래 project들을 scan |
| Bitbucket | Bitbucket repository/team/project를 scan |

### 7.2 Branch Indexing

Branch Indexing은 SCM을 스캔해서 현재 어떤 branch, PR, MR, tag가 있는지 확인하고 Jenkins 하위 job 목록을 갱신하는 작업이다.

Indexing이 일어나는 대표 상황은 다음과 같다.

- Multibranch Pipeline job을 처음 저장했을 때
- `Scan Multibranch Pipeline Now`를 수동 실행했을 때
- webhook 이벤트를 받았을 때
- periodic scan trigger가 실행되었을 때
- Organization Folder가 전체 repository 목록을 다시 scan했을 때

### 7.3 Organization Folder

Organization Folder는 GitHub Organization, Bitbucket Team/Project, GitLab Group/Subgroup처럼 여러 repository를 가진 SCM 단위를 Jenkins가 자동으로 모니터링하도록 하는 job 유형이다.

Multibranch Pipeline이 "단일 repository 안의 branch/PR/MR을 자동 관리"한다면, Organization Folder는 "조직 또는 그룹 안의 여러 repository를 자동 관리"한다.

```text
GitHub Organization / GitLab Group
  ├─ service-api repository
  │   ├─ main
  │   ├─ feature/a
  │   └─ PR-1
  ├─ service-worker repository
  │   ├─ main
  │   └─ PR-3
  └─ service-front repository
      ├─ main
      └─ release/1.0
```

Organization Folder는 repository마다 Multibranch Pipeline을 만들고, 각 repository 안에서는 branch/PR/MR별 job을 만든다.

## 8. Environment Variables

Multibranch Pipeline은 branch나 PR 정보를 환경 변수로 제공한다. Jenkinsfile에서는 이 값을 사용해 branch별 조건 처리를 할 수 있다.

### 8.1 Jenkins 기본 Multibranch 변수

| 변수 | 의미 |
| --- | --- |
| `BRANCH_NAME` | 현재 빌드 중인 branch 이름. 예: `main`, `develop`, `feature/login`, `PR-15` |
| `CHANGE_ID` | PR/MR 같은 change request 번호 또는 식별자 |
| `CHANGE_TARGET` | PR/MR의 target branch |
| `CHANGE_BRANCH` | PR/MR의 source branch |
| `CHANGE_FORK` | fork에서 온 PR/MR인 경우 fork 정보 |
| `CHANGE_URL` | PR/MR URL |
| `CHANGE_AUTHOR` | PR/MR 작성자 ID |
| `CHANGE_TITLE` | PR/MR 제목 |
| `TAG_NAME` | tag build일 때 tag 이름 |
| `TAG_TIMESTAMP` | tag timestamp |
| `TAG_DATE` | tag date |
| `TAG_UNIXTIME` | tag unix timestamp |

Jenkins 공식 `Branches and Pull Requests` 문서는 대표적으로 `BRANCH_NAME`, `CHANGE_ID`를 언급한다. GitLab Branch Source 문서는 Branch API Plugin이 제공하는 branch/change request/tag 변수들을 더 자세히 정리하고 있다.

### 8.2 예시: branch별 실행 제어

```groovy
pipeline {
    agent any

    stages {
        stage('Build') {
            steps {
                sh './gradlew build'
            }
        }

        stage('Deploy Dev') {
            when {
                branch 'develop'
            }
            steps {
                sh './deploy-dev.sh'
            }
        }

        stage('Deploy Prod') {
            when {
                branch 'main'
            }
            steps {
                sh './deploy-prod.sh'
            }
        }
    }
}
```

### 8.3 예시: PR/MR일 때만 실행

```groovy
pipeline {
    agent any

    stages {
        stage('PR Validation') {
            when {
                changeRequest()
            }
            steps {
                echo "Change Request: ${env.CHANGE_ID}"
                echo "Target Branch: ${env.CHANGE_TARGET}"
                sh './gradlew test'
            }
        }
    }
}
```

### 8.4 예시: `checkout scm`

Multibranch Pipeline에서는 `checkout scm`을 자주 사용한다. 이 step은 현재 Jenkinsfile이 온 바로 그 SCM revision을 checkout한다.

```groovy
pipeline {
    agent any

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Build') {
            steps {
                sh './gradlew clean build'
            }
        }
    }
}
```

PR/MR 빌드에서는 일반 branch checkout보다 `checkout scm`이 더 안전하다. Jenkins가 PR/MR의 source, target, merge revision 등을 Branch Source 설정에 맞게 알고 있기 때문이다.

## 9. GitHub Branch Source Plugin

GitHub Branch Source Plugin은 GitHub 사용자 또는 Organization의 repository 구조를 바탕으로 Jenkins project를 자동 생성할 수 있게 해주는 표준적인 Branch Source Plugin이다.

공식 플러그인 페이지는 핵심적으로 다음을 설명한다.

- GitHub 사용자 또는 Organization의 repository 구조 기반으로 project 생성
- Multibranch Pipeline으로 단일 repository의 branch, PR, tag import
- Organization Folder로 GitHub user/organization의 여러 repository import
- GitHub PR 빌드 결과를 GitHub status로 피드백

### 9.1 GitHub Multibranch Pipeline

GitHub repository 하나를 대상으로 Multibranch Pipeline을 만들면 Jenkins는 해당 repository를 scan해서 branch, pull request, tag를 Pipeline project로 만든다.

구성 흐름은 다음과 같다.

1. Jenkins에서 `New Item`을 선택한다.
2. `Multibranch Pipeline`을 선택한다.
3. `Branch Sources`에서 `GitHub`를 선택한다.
4. credentials를 선택한다.
5. repository URL을 입력한다.
6. 저장하면 Jenkins가 repository를 scan한다.
7. root에 `Jenkinsfile`이 있는 branch/PR/tag가 하위 job으로 생성된다.

GitHub Branch Source 문서의 중요한 포인트는 branch마다 같은 Jenkinsfile을 강제하지 않는다는 것이다. branch별로 서로 다른 Jenkinsfile을 둘 수도 있고, 필요에 따라 Jenkinsfile이 없는 branch는 빌드하지 않을 수도 있다.

### 9.2 GitHub Pull Request 빌드

GitHub Branch Source Plugin은 PR을 project처럼 취급할 수 있다. PR을 발견하면 Jenkins는 PR 전용 하위 job을 만들고, PR 상태에 따라 빌드를 실행한다.

PR 빌드 전략은 보통 다음 선택지가 있다.

| 전략 | 설명 |
| --- | --- |
| PR head revision 빌드 | PR source branch의 현재 commit을 그대로 빌드 |
| PR merge revision 빌드 | PR source branch를 target branch에 merge한 결과를 빌드 |
| 둘 다 빌드 | head와 merge 결과를 각각 검증 |

실무에서는 "merge했을 때 깨지는지"를 확인하기 위해 merge revision 빌드를 많이 사용한다. 다만 fork PR, 외부 기여자 PR처럼 신뢰 경계가 있는 경우 credentials와 secret 노출에 주의해야 한다.

### 9.3 GitHub Status Check 피드백

GitHub Branch Source 공식 가이드에 따르면 적절한 webhook이 설정되어 있을 때 Jenkins는 PR project의 build status를 GitHub에 보고한다.

상태는 보통 다음과 같이 해석된다.

| GitHub status | 의미 |
| --- | --- |
| `Pending` | Jenkins build가 queue에서 대기 중 |
| `Success` | Jenkins build 성공 |
| `Failure` | Jenkins build 실패. PR merge 준비가 되지 않은 상태로 볼 수 있음 |
| `Error` | Jenkins에서 abort 등 예상치 못한 문제가 발생 |

GitHub에서는 이 status를 branch protection rule이나 required checks와 연결해, Jenkins 검증이 통과해야 merge 가능하도록 구성할 수 있다.

### 9.4 GitHub Organization Folder

Organization Folder는 GitHub 사용자 또는 Organization 아래 repository들을 자동으로 가져온다. 가져온 각 repository는 Multibranch Pipeline처럼 동작한다.

구성 흐름은 다음과 같다.

1. Jenkins에서 `New Item`을 선택한다.
2. `Organization Folder`를 선택한다.
3. `Projects` 탭에서 GitHub Organization 정보를 설정한다.
4. credentials를 선택한다.
5. owner에 GitHub username 또는 organization 이름을 입력한다.
6. 저장하면 Scan Organization이 실행된다.
7. Jenkins가 repository를 import하고, repository마다 Multibranch Pipeline 구조를 만든다.

Organization Folder로 import된 repository 하위 설정은 상위 Organization Folder 설정으로 제어된다. 개별 repository folder 설정을 마음대로 수정하는 구조가 아니라, parent folder의 scan/trait 정책이 전체에 적용되는 방식으로 이해하면 된다.

### 9.5 GitHub credentials

GitHub Organization Folder에서는 credentials를 크게 두 종류로 나눠 생각한다.

| credentials | 용도 |
| --- | --- |
| scan credentials | GitHub API를 호출해 organization/repository/PR 정보를 가져오는 데 사용 |
| checkout credentials | repository를 clone/checkout하는 데 사용 |

두 credentials는 같을 수도 있고 다를 수도 있다. GitHub API rate limit이나 보안 관리를 고려하면 GitHub App 또는 token 기반 credentials를 사용하는 것이 일반적이다.

### 9.6 GitHub webhook과 scan

GitHub webhook을 설정하면 push나 PR 이벤트가 발생했을 때 Jenkins가 빠르게 반응할 수 있다. webhook이 없다면 Jenkins는 periodic scan을 통해 변경사항을 뒤늦게 발견한다.

GitHub Branch Source 문서는 기본적으로 하루 동안 GitHub change notification을 받지 못하면 repository 변경사항을 scan하는 식의 fallback scan을 설명한다. 또한 사용자는 `Scan Organization Now`로 수동 scan을 실행할 수 있다.

GitHub webhook 구성 흐름은 다음과 같다.

1. Jenkins `Manage Jenkins -> System`으로 이동한다.
2. GitHub section에 GitHub Server와 credentials를 추가한다.
3. 필요하면 token을 생성하거나 GitHub App credentials를 설정한다.
4. GitHub repository 또는 organization에 Jenkins webhook URL을 등록한다.
5. push/PR 이벤트가 Jenkins로 전달되면 scan 또는 build가 실행된다.

## 10. GitLab Branch Source Plugin

GitLab Branch Source Plugin은 GitLab project 또는 group/subgroup을 Jenkins Multibranch Pipeline/Organization Folder와 연결해주는 plugin이다.

공식 문서 기준 이 plugin은 크게 두 가지 job 유형을 지원한다.

| 유형 | 설명 |
| --- | --- |
| Multibranch Pipeline Jobs | 단일 GitLab project의 branch/MR/tag를 자동 관리 |
| Folder Organization | GitLab user/group/subgroup 안의 여러 project를 자동 관리 |

### 10.1 GitLab Server 설정

GitLab Branch Source Plugin을 제대로 사용하려면 Jenkins에 GitLab Server 설정을 먼저 추가해야 한다.

주요 설정 항목은 다음과 같다.

| 항목 | 설명 |
| --- | --- |
| `Name` | Jenkins 안에서 사용할 GitLab server 이름 |
| `Server URL` | GitLab 서버 주소. 예: `https://gitlab.com`, 사내 GitLab URL |
| `Credentials` | GitLab Personal Access Token 또는 String Credential |
| `Manage Web Hook` | project webhook을 plugin이 관리할지 여부 |
| `Manage System Hook` | system hook을 plugin이 관리할지 여부. admin 권한 필요 가능 |
| `Secret Token` | GitLab webhook payload 인증용 token |
| `Root URL for hooks` | webhook root URL. 기본은 Jenkins URL |

GitLab Personal Access Token은 보통 `api` scope가 필요하다. system hook까지 관리하려면 admin 수준 권한 또는 추가 scope가 필요할 수 있다.

### 10.2 GitLab webhook endpoint

GitLab Branch Source 문서에서 수동 hook 설정 시 사용하는 endpoint는 다음과 같다.

```text
<jenkins_url>/gitlab-webhook/post
<jenkins_url>/gitlab-systemhook/post
```

| endpoint | 용도 |
| --- | --- |
| `/gitlab-webhook/post` | push, tag push, merge request, note event 수신 |
| `/gitlab-systemhook/post` | repository update 같은 system hook 수신 |

Jenkins URL은 외부 GitLab이 접근 가능한 FQDN이어야 한다. `localhost`는 GitLab SaaS나 외부 GitLab 서버에서 접근할 수 없으므로 webhook 대상 URL로 적합하지 않다.

### 10.3 GitLab Multibranch Pipeline Job

GitLab 단일 project를 대상으로 Multibranch Pipeline을 구성하는 흐름은 다음과 같다.

1. Jenkins에서 `New Item`을 선택한다.
2. `Multibranch Pipeline`을 선택한다.
3. `Branch Sources`에서 `GitLab Project`를 선택한다.
4. 미리 설정한 GitLab Server를 선택한다.
5. private project라면 checkout credentials를 설정한다.
6. owner path를 입력한다. user, group, subgroup path를 사용할 수 있다.
7. 발견된 project 목록에서 대상 project를 선택한다.
8. `Behaviours` 또는 SCM Traits를 설정한다.
9. 저장하면 branch indexing이 시작된다.
10. `Jenkinsfile`이 있는 branch/MR/tag가 하위 job으로 생성된다.

GitLab Access Token이 server configuration에 있으면 저장 후 webhook이 생성되고, 선택한 behaviour에 맞춰 indexing이 진행된다.

### 10.4 GitLab Group / Folder Organization

GitLab Group Job은 GitLab user/group/subgroup 전체를 스캔해서 project들을 자동으로 가져온다. Jenkins UI에서는 Organization Folder 유형으로 만들고, Repository Source로 `GitLab Group`을 선택하는 방식이다.

구성 흐름은 다음과 같다.

1. Jenkins에서 `New Item`을 선택한다.
2. `Organization Folder`를 선택한다.
3. `Projects` 또는 Repository Sources에서 `GitLab Group`을 선택한다.
4. GitLab Server를 선택한다.
5. checkout credentials가 필요하면 추가한다.
6. owner path에 user/group/subgroup path를 입력한다.
7. Behaviours를 설정한다.
8. 저장하면 group 안의 project들이 scan된다.
9. 각 project 안에서 `Jenkinsfile`이 있는 branch/MR/tag가 하위 job으로 생성된다.

GitLab Group Job의 indexing log는 전체 project를 대표하는 일부 로그만 보일 수 있고, 상세 indexing은 각 project에서 확인해야 한다.

### 10.5 GitLab SCM Traits

GitLab Branch Source Plugin에서는 Behaviours 또는 SCM Traits로 어떤 대상을 발견하고 어떻게 빌드할지 제어한다.

기본 trait는 다음과 같다.

| Trait | 설명 |
| --- | --- |
| Discover branches | branch를 발견한다 |
| Discover merge requests from origin | 같은 project 안에서 열린 MR을 발견한다 |
| Discover merge requests from forks | fork project에서 온 MR을 발견한다 |

MR discovery 전략은 다음처럼 나뉜다.

| 전략 | 설명 |
| --- | --- |
| MR head revision | MR source branch의 현재 commit을 빌드 |
| MR merged with target revision | target branch와 merge한 결과를 빌드 |
| both | head와 merge 결과를 둘 다 빌드 |

fork MR trust 설정은 매우 중요하다.

| Trust 설정 | 의미 |
| --- | --- |
| Members | origin project member가 만든 fork MR만 신뢰 |
| Trusted Members | Developer/Maintainer/Owner 권한을 가진 사용자의 fork MR만 신뢰. 권장 |
| Everyone | 누구나 만든 fork MR을 신뢰. secret 노출 위험이 있어 피해야 함 |
| Nobody | fork MR을 발견하지 않음 |

GitLab 문서도 `Everyone`은 보안상 사용하지 말라고 안내한다. fork PR/MR은 외부 코드가 Jenkinsfile을 통해 실행될 수 있으므로 credentials와 secret 환경 변수 노출 위험을 항상 고려해야 한다.

### 10.6 GitLab 추가 Traits

추가할 수 있는 대표 trait는 다음과 같다.

| Trait | 설명 |
| --- | --- |
| Tag discovery | GitLab tag를 발견 |
| Discover group/subgroup projects | GitLab Group Job에서 subgroup project까지 발견 |
| Filter by name with wildcards | branch/MR/tag 이름 패턴으로 발견 대상 제한 |
| Skip pipeline status notifications | GitLab pipeline status 알림 비활성화 |
| Override hook management modes | webhook/system hook 관리 방식 override |
| Checkout over SSH | SSH checkout 사용. 문서상 Checkout Credentials 사용이 더 권장됨 |
| Webhook Listener Conditions | webhook payload 조건에 따라 build trigger 여부 제어 |

tag push를 자동 build하려면 tag discovery만으로 충분하지 않을 수 있고, Branch Build Strategy Plugin 같은 build strategy 설정이 필요할 수 있다.

### 10.7 GitLab Pipeline Status 피드백

GitLab Branch Source Plugin은 build 결과를 GitLab Server에 Pipeline Status로 알릴 수 있다. GitLab 문서 기준으로 각 branch HEAD commit에 대해 status가 전달된다.

다만 forked MR의 경우 GitLab 보안 정책상 MR pipeline status를 제공하지 못하는 제한이 있다. plugin은 trusted owner, 즉 Developer/Maintainer/Owner 권한을 가진 작성자의 MR을 빌드하는 방식으로 우회할 수 있다고 설명한다.

## 11. Scan, Webhook, Trigger 관계

Multibranch Pipeline에서 scan과 build trigger는 구분해서 이해해야 한다.

| 개념 | 의미 |
| --- | --- |
| Scan / Indexing | SCM을 살펴보고 branch/PR/MR/tag와 Jenkinsfile 존재 여부를 갱신 |
| Build | 특정 branch/PR/MR/tag의 Jenkinsfile을 실행 |
| Webhook | SCM 이벤트를 Jenkins로 전달 |
| Periodic Scan | webhook 누락에 대비해 주기적으로 SCM을 다시 확인 |

Webhook이 들어오면 Jenkins는 이벤트 내용을 보고 관련 branch나 PR을 갱신하고 필요한 build를 실행한다. 하지만 webhook이 누락될 수 있으므로 periodic scan을 fallback으로 두는 구성이 안전하다.

## 12. Orphaned Item Strategy

Orphaned Item은 더 이상 SCM에 존재하지 않거나 더 이상 `Jenkinsfile`이 없어 관리 대상에서 빠진 하위 job을 의미한다.

예를 들어 다음 상황에서 orphaned item이 생길 수 있다.

- feature branch가 삭제됨
- PR/MR이 닫힘
- branch에서 `Jenkinsfile`이 제거됨
- Organization Folder에서 repository가 제외됨

Orphaned Item Strategy를 사용하면 이런 job을 즉시 삭제할지, 며칠 동안 보관할지, 최대 몇 개까지 보관할지 정할 수 있다. 삭제된 branch의 마지막 build 결과를 잠시 확인해야 하는 팀이라면 일정 기간 보관하도록 설정하는 것이 좋다.

## 13. 실전 Jenkinsfile 예시

### 13.1 branch와 PR/MR을 구분하는 Jenkinsfile

```groovy
pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Build') {
            steps {
                sh './gradlew clean build'
            }
        }

        stage('PR Test') {
            when {
                changeRequest()
            }
            steps {
                echo "Change Request ${env.CHANGE_ID} -> ${env.CHANGE_TARGET}"
                sh './gradlew test'
            }
        }

        stage('Deploy Dev') {
            when {
                branch 'develop'
            }
            steps {
                sh './deploy-dev.sh'
            }
        }

        stage('Deploy Prod') {
            when {
                branch 'main'
            }
            steps {
                sh './deploy-prod.sh'
            }
        }
    }

    post {
        always {
            junit 'build/test-results/**/*.xml'
        }
    }
}
```

### 13.2 tag build 처리

```groovy
pipeline {
    agent any

    stages {
        stage('Release Build') {
            when {
                buildingTag()
            }
            steps {
                echo "Release tag: ${env.TAG_NAME}"
                sh './gradlew clean release'
            }
        }
    }
}
```

### 13.3 main branch만 배포

```groovy
pipeline {
    agent any

    stages {
        stage('Build') {
            steps {
                sh './gradlew build'
            }
        }

        stage('Deploy') {
            when {
                allOf {
                    branch 'main'
                    not {
                        changeRequest()
                    }
                }
            }
            steps {
                sh './deploy.sh'
            }
        }
    }
}
```

## 14. GitHub와 GitLab 구성 비교

| 항목 | GitHub Branch Source | GitLab Branch Source |
| --- | --- | --- |
| 단일 repository | Multibranch Pipeline + GitHub source | Multibranch Pipeline + GitLab Project source |
| 여러 repository | Organization Folder + GitHub owner/org | Organization Folder + GitLab Group |
| PR/MR | Pull Request | Merge Request |
| status 피드백 | GitHub PR/branch build status | GitLab Pipeline Status |
| API credentials | GitHub App 또는 token | GitLab Personal Access Token |
| webhook | GitHub webhook | `/gitlab-webhook/post` |
| system hook | 일반적으로 Organization/repo webhook 중심 | `/gitlab-systemhook/post` 지원 |
| 보안 포인트 | fork PR trust, token 권한, rate limit | fork MR trust, secret token, access token scope |

## 15. 보안 주의사항

Multibranch Pipeline은 PR/MR의 Jenkinsfile을 실행할 수 있기 때문에 보안 경계가 중요하다.

특히 fork PR/MR은 외부 사용자가 작성한 코드가 Jenkins agent에서 실행될 수 있다. Jenkinsfile 안에서 credentials를 읽거나 secret 환경 변수를 출력하도록 악용될 수 있으므로 다음을 조심해야 한다.

- fork PR/MR에 secret credentials를 주입하지 않는다.
- fork PR/MR trust policy를 신중하게 설정한다.
- GitLab의 `Everyone` trust 설정은 피한다.
- GitHub/GitLab token에는 필요한 최소 권한만 부여한다.
- public repository의 PR 빌드는 별도 agent나 격리된 환경에서 실행한다.
- 배포 stage는 `branch 'main'`, 승인 단계, credentials 제한 등으로 보호한다.

## 16. Troubleshooting 체크리스트

### 16.1 branch가 자동 생성되지 않을 때

- branch root에 `Jenkinsfile`이 있는지 확인한다.
- Jenkinsfile 이름과 script path 설정이 일치하는지 확인한다.
- Branch Source의 include/exclude filter에 걸리지 않았는지 확인한다.
- `Scan Multibranch Pipeline Now`를 수동 실행해 본다.
- scan log에서 인증 실패, API rate limit, repository 접근 오류를 확인한다.

### 16.2 PR/MR 빌드가 안 될 때

- PR/MR discovery trait가 활성화되어 있는지 확인한다.
- fork PR/MR trust 설정이 너무 제한적이지 않은지 확인한다.
- webhook이 Jenkins에 도달하는지 확인한다.
- Jenkins URL이 외부 SCM provider에서 접근 가능한지 확인한다.
- GitHub/GitLab credentials 권한이 충분한지 확인한다.

### 16.3 status check가 SCM에 안 보일 때

- GitHub/GitLab API credentials가 status 업데이트 권한을 가지는지 확인한다.
- webhook이 정상 등록되어 있는지 확인한다.
- GitLab에서는 `Skip pipeline status notifications` trait가 켜져 있지 않은지 확인한다.
- fork MR의 경우 status 피드백 제한이 있는지 확인한다.
- Jenkins build log와 branch indexing log를 확인한다.

### 16.4 webhook이 동작하지 않을 때

- Jenkins URL이 public 또는 SCM에서 접근 가능한 네트워크에 있는지 확인한다.
- GitHub/GitLab webhook delivery log를 확인한다.
- GitLab은 `/gitlab-webhook/post` endpoint를 사용했는지 확인한다.
- GitHub는 Jenkins GitHub Server 설정과 repository webhook 설정을 확인한다.
- secret token이 설정된 경우 GitLab/Jenkins 양쪽 값이 일치하는지 확인한다.

## 17. 핵심 요약

- Multibranch Pipeline은 branch/PR/MR/tag별 Jenkins job을 자동으로 관리한다.
- Jenkins는 SCM을 scan해서 `Jenkinsfile`이 있는 항목만 Pipeline 대상으로 삼는다.
- `BRANCH_NAME`, `CHANGE_ID`, `CHANGE_TARGET`, `TAG_NAME` 같은 환경 변수로 branch/PR/tag 조건 분기가 가능하다.
- `checkout scm`은 Multibranch Pipeline에서 현재 build 대상 revision을 checkout하는 표준 방식이다.
- GitHub Branch Source Plugin은 GitHub repository/organization을 Jenkins Multibranch/Organization Folder와 연결한다.
- GitLab Branch Source Plugin은 GitLab project/group/subgroup을 Jenkins Multibranch/Organization Folder와 연결한다.
- Organization Folder는 여러 repository를 자동 scan하고 repository별 Multibranch Pipeline을 만든다.
- webhook은 빠른 반응을 위한 장치이고, periodic scan은 webhook 누락에 대비한 fallback이다.
- PR/MR 빌드는 status check 또는 pipeline status로 SCM에 결과를 피드백할 수 있다.
- fork PR/MR은 secret 노출 위험이 있으므로 trust policy와 credentials 범위를 반드시 신중하게 설정해야 한다.

## 참고 자료

- Jenkins 공식 문서 - Branches and Pull Requests: https://www.jenkins.io/doc/book/pipeline/multibranch/
- Jenkins Plugin 문서 - GitHub Branch Source: https://plugins.jenkins.io/github-branch-source/
- CloudBees 문서 - GitHub Branch Source Plugin Guide: https://docs.cloudbees.com/docs/cloudbees-ci/latest/cloud-admin-guide/github-branch-source-plugin
- Jenkins Plugin 문서 - GitLab Branch Source: https://plugins.jenkins.io/gitlab-branch-source/
