# 2. Multibranch Pipeline

## 2-1) SCM(GitHub/GitLab) Organization scanning 및 `Jenkinsfile` 자동 감지

### Jenkinsfile을 활성화하는 작업

- Multibranch Pipeline : 단일 레포지토리의 여러 브랜치를 자동으로 빌드
- Organization Folders : Github Organization 또는 Bitbucket Team을 스캔하여 조직의 레포지토리를 탐색하고 이에 대한 관리형 Multibranch Pipeline 작업을 자동으로 생성
- Pipeline :  일반 Pipeline 작업에서 파이프라인을 지정할 때 “Use SCM”을 선택
- 레포지토리의 루트에 Jenkinsfile이 존재하는지 여부에 따라 Jenkins가 해당 레포지토리 브랜치를 작업 관리 및 실행 대상으로 자동 인식한다.

### Multibranch Pipeline & GitHub Organization Folders

- 하위 항목을 동적으로 생성하고 업데이트하여 콘텐츠를 자동으로 관리하는 computed folder 개념을 도입하여 Jenkins의 폴더 기능을 확장했다.
- 해당 기능을 사용하기 위해서는 Github Branch Source 플러그인이 설치되어 있어야 한다.

    **Multibranch Pipeline**

    - 브랜치나 PR의 루트 디렉토리에 있는 Jenkinsfile을 통해 Multibranch 프로젝트를 식별한다.
    - computed folder 기능에는 파이프라인 항목을 동적으로 관리하는 Scan Multibrannch Pipeline Log 및 Scan Multibranch Pipeline Now 옵션이 포함된다.
        - 레포지토리 스캔
        - 조건에 맞는 브랜치에 대해 하위 항목 생성
        - 변경 사항에 따라 파이프라인 목록 자동 업데이트
    - 빌드 또는 배포 절차의 변경 사항이 프로젝트 요구사항에 맞도록 함께 진화할 수 있어, 작업이 항상 프로젝트의 현재 상태를 반영한다.
    - 동일한 프로젝트의 서로 다른 브랜치에 대해 각기 다른 작업을 구성하거나 필요하다면 특정 브랜치의 작업을 생략할 수도 있다.
    - New Item → Multibranch Pipeline에서 SCM 소스를 상황에 맞게 설정하여 Multibranch Pipeline을 생성할 수 있다.
        - Git, Mercurial, Bitbucket, GitHub를 포함해 다양한 유형의 레포지토리 및 서비스에 대한 옵션이 제공된다.
        - API endpoint, Checkout credentials, Include branches, Exclude branches, Property strategy 등의 기타 옵션이 존재한다.
        - 위의 항목들을 구성하고 설정을 저장하면 Jenkins가 레포지토리를 자동으로 스캔하여 조건에 맞는 브랜치들을 가져온다.

    **Github Organization**

    - computed folder 기능에는 Scan Organization Log와 Scan Organization Now 옵션이 포함된다.
        - 레포지토리를 개별 Multibranch Pipeline으로 채우기
        - 브랜치 및 레포지토리 스캔에 대한 통찰
    - **Organization Folders**
        - Jenkins가 자동으로 포함될 레포지토리를 편하게 관리할 수 있는 방법을 제공한다.
        - 특히 Github Orgaizations나 Bitbucket Teams를 사용하는 경우에는 Jenkinsfile이 포함된 새 레포지토리를 생성할 때마다 Jenkins가 이를 자동으로 감지하여 해당 레포지토리에 대한 Multibranch Pipeline 프로젝트를 생성한다.
        - New Item → Organization Folder 또는 New Item → Bitbucket Team으로 이동하여 각 항목을 설정하고 저장하면 Jenkins가 조직을 자동으로 스캔하여 조건에 맞는 레포지토리와 그 결과 브랜치들을 가져온다.
            - Repository name pattern, API endpoint, Checkout credentials 등 설정 가능

        ```text
        # 흐름
        
        Organization Folder가 레포지토리 스캔
        -> Jenkinsfile 발견
        -> Multibranch Pipeline 생성
        ```

- 폴더 스캔은 브랜치나 레포지토리가 생성되거나 삭제될 때마다 웹훅 콜백혹은 Build Triggers를 통해 자동으로 트리거될 수 있다.
- 가장 최근에 organization을 스캔하려 했던 시도의 로그는 Scan Organization Log에서 확인할 수 있다.
    - 스캔 결과 예상한 레포지토리 목록이 생성되지 않으면 해당 로그에 문제 진단에 유용한 정보가 포함되어 있을 수 있다.
- (Multibranch Pipelines와 Organization Folders가 SCM과 상호작용하기 위해서는 scan credentials를 제공해야 한다.
    - Controller에서의 credential : Organization 폴더 스캔, Multibranch Pipeline 브랜치 색인 생성, 웹훅 수정, 커밋 상태 업데이트 등과 같은 플러그인 작업을 수행하며 상당한 권한이 필요할 수 있는 SCM 공급 API와 상호작용한다.
    - Node에서의 credential : 하위 파이프라인 작업에 의해 빌드되는 레포지토리를 체크아웃하는 데 사용된다.

## 2-2) Pull Request (PR) 빌드/검증 파이프라인 구성 및 Status Check Feedback API 연동

- Multibranch pipeline 작업에서 jenkins는 소스 제어 내에 Jenkinsfile이 포함된 브랜치, Merge Request, 태그에 대한 파이프라인을 자동으로 발견, 관리 및 실행한다.

### Jenkins와 GitLab 연동 과정

```text
GitLab Access Token을 Jenkins설정에 저장
+ Multibranch pipeline을 저장

-> GitLab 서버에 새로운 웹훅 생성

-> 선택한 옵션 동작에 따라 브랜치 인덱싱

-> 루트 디렉토리에 Jenkinsfile이 있는 각 브랜치에 대해 새 작업 시작 및 대기열에 추가
(최초 빌드 실행)

-> 작업 결과는 파이프라인 상태로 GitLab 서버에 통보
(포크된 MR의 빌드는 보안 상의 이유로 통보X)

-> GitLab 서버에 의해 Jenkins CI에 웹훅 설정 완료

-> 푸시, MR, 태그 이벤트 등이 Jenkins에서 관련 빌드 트리거
```

### GitHub Checks

- Checks API 플러그인의 상태 체크 기능을 구현하여 Github에 대기 중, 진행 중, 완료와 같은 상태를 게시한다.
- Github SCM Source/Git SCM 프로젝트의 Status Checks Properties 동작을 설정하여 커스터마이징 할 수 있다.
- Github는 하나의 커밋 SHA에 체크 실행을 첨부한다.
    - SHA (Secure Hash Algorithm) : Git에서 모든 데이터를 고유하게 식별하기 위해 생성하는 40자리의 해시값
- GitHub Checks가 SHA를 선택하는 방식
    - GitHub Branch Source : PR head의 SHA 사용 (PR 화면에 정상 피드백됨)
    - Git 플러그인 (GitSCM) : 실제 체크아웃한 커밋 SHA 사용 (/merge 참조 시 PR 화면 피드백 누락 주의)

### GitLab vs GitHub

- 상태 피드백 API: GitHub는 단순 Status API 외에도 상세 리포팅이 가능한 Checks API를 추가 지원한다. (GitLab은 Commit Status API 활용)
- SHA 대상 피드백 처리: PR/MR 검증 시 임시 머지 커밋이 생성되더라도, GitHub의 필수 상태 체크를 통과하려면 피드백이 PR Head 커밋 SHA에 남아야 한다.

## 2-3) Concurrency & Branch Strategies

### disabaleConcurrentBuilds

- 파이프라인의 동시 실행을 허용하지 않는다.
- 공유 자원에 대한 동시 접근 등을 방지하는 데에 유용할 수 있다.
- 예시

    `options { disableConcurrentBuilds() }`

    - 파이프라인의 빌드가 이미 실행 중일 때 새로운 빌드 요청이 들어오면 이를 대기열(queue)에 넣는다.

    `options { disableConcurrentBuilds(abortPrevious: true) }`

    - 현재 실행 중인 빌드를 중단하고 새로운 빌드를 바로 시작한다.
- 정리하자면, 동일한 파이프라인이 여러 개 동시에 실행되는 것을 방지해주는 옵션이라고 볼 수 있다.

### milestone

- 기본적으로 파이프라인 빌드는 동시에 실행될 수 있다.
- 모든 빌드가 순서대로 진행되도록 강제하여, 최신 빌드가 이미 마일스톤을 통과했다면 이전 빌드가 마일스톤을 통과하짐 못하게 중단시킨다.
- 규칙
    - 순서대로 통과 (빌드 번호를 기준으로 순서대로 마일스톤 통과)
    - 이전 빌드 자동 중단
    - 마일스톤을 통과한 빌드는 아직 마일스톤에 도달하지 못한 최신 빌드에 의해 중단X

## 2-4) 참고 문헌

- <https://www.jenkins.io/doc/book/pipeline/pipeline-as-code/>
- <https://www.jenkins.io/doc/book/security/securing-org-folders-and-multibranch-pipelines/>
- <https://plugins.jenkins.io/gitlab-branch-source/>
- <https://plugins.jenkins.io/github-checks/>
- <https://www.jenkins.io/doc/book/pipeline/syntax/>
- <https://www.jenkins.io/doc/pipeline/steps/pipeline-milestone-step/>
