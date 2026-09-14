# 1. Declarative Pipeline Syntax (Deep Dive)

## 1-1) Core Directives

### Jenkins Pipeline이란

- Jenkins에 지속적 배포 파이프라인을 구현하고 통합하는 것을 지원하는 플러그인 모음
- Pipeline은 Pipeline DSL을 통해 배포 파이프라인을 코드로 모델링하기 위한 확장 가능한 도구 세트를 제공한다.
- 선언적 파이프라인 vs 스크립트 파이프라인
    - 선언적 파이프라인 : 파이프라인 코드의 작성과 가독성을 높이기 위해 설계 & 스크립트 기반 파이프라인 구문보다 더 풍부한 구문적 기능 제공
    - 파이프라인에 작성되는 개별 구문 구성 요소 중 상당수는 두 가지 모두에서 공통적으로 사용 가능
- 파이프라인의 기능 : 코드 구현, 내구성 유지, 일시 중지 가능, 다양한 CD 요구 사항 지원, 확장 가능성
- 파이프라인 구문
    - pipeline : 전체 빌드 프로세스로, 애플리케이션 빌드~테스트 및 배포 단계를 포함한다.
    - node : 파이프라인을 실행할 수 있는 머신
    - stage : 전체 파이프라인을 통해 수행되는 작업의 하위 집합 (빌드, 테스트, 배포 등의 단계)
    - step : Jenkins의 특정 시점에서 무엇을 해야 하는지 명령

```groovy
# 선언적 파이프라인
# pipeline 블록은 파이프라인 전체에서 수행되는 모든 작업의 정의

pipeline {
    agent any
    stages {
        stage('Build') {
            steps {
                //
            }
        }
        stage('Test') {
            steps {
                //
            }
        }
        stage('Deploy') {
            steps {
                //
            }
        }
    }
}
```

```groovy
# 스크립트 기반 파이프라인
# 하나 이상의 node 블록이 파이프라인 전체의 핵심 작업을 수행

node {
    stage('Build') {
        //
    }
    stage('Test') {
        //
    }
    stage('Deploy') {
        //
    }
}
```

### Pipeline Syntax

- 선언적 파이프라인은 pipeline 블록 안에 모두 포함되어야 한다.

### 용어 정리

- **agent**
    - 전체 파이프라인 또는 특정 스테이지가 어떤 agent에서 실행될지 지정한다.
    - top agent : agent 할당 → timeout 옵션 적용
    - stage agent : timeout 적용 (있다면) → agent 할당
    - 차이점 : stage agent의 timeout은 agent가 할당되기 전에 시작되기 때문에 agent 할당이 지연된다면 파이프라인 실행 자체가 실패할 수도 있다.
    - parameters
        - agent 섹션에서 제공하는 몇 가지 종류의 매개 변수.

        | any | 사용 가능한 모든 agent/파이프라인 |
        | --- | --- |
        | none | 글로벌 agent 할당X, 각 stage에서 agent 지정 |
        | label | 지정된 label이 있는 환경의 사용 가능한 agent |
        | node | customWorkspace와 같은 추가적인 선택지 입력 가능 |
        | docker | docker 기반 파이프라인을 수용하도록 미리 정의되었거나 label에 매칭이 되는 노도에서 컨테이너를 사용하여 파이프라인/stage를 실행 |
        | dockerfile | 소스 레포지토리에 포함된 Dockerfile에서 빌드된 컨테이너를 사용하여 파이프라인/stage 실행 (이때, Jenkinsfile을 Multibranch Pipeline 또는 Pipeline from SCM 방식으로 불러와야 함) |
        | kubernetes | kubernetes 클러스터에 배포된 파드 내부에서 파이프라인/stage 실행 |
- **stages**
    - 파이프라인에서 설명하는 실제 작업의 대부분이 위치하는 공간

    ```groovy
    pipeline {
        agent any
        stages {
            stage('Example') { # 개별 단계를 나타내는 지시어 권장
                steps {
                    echo 'Hello World'
                }
            }
        }
    }
    ```

- **steps**
    - stage 내부에서 실행되는 하나 이상의 스텝들

    ```groovy
    pipeline {
        agent any
        stages {
            stage('Example') {
                steps {
                    echo 'Hello World'
                }
            }
        }
    }
    ```

- **post**
    - 파이프라인/stage 실행 완료 후 실행될 하나 이상의 추가 스텝
- **environment**
    - environment 지시어가 위치하는 파트에 따라 해당 스텝에 적용하는 환경 변수 세트를 지정
- **options**
    - 파이프라인 내부에서 파이프라인 전용 옵션 구성
    - buildDiscarder와 같은 여러 기본 옵션 및 timestamps와 같은 플러그인 등
- **parameters**
    - 사용자가 파이프라인을 실행할 때 제공해야 하는 매개변수 목록
    - params 객체를 통해 스텝에서 사용 가능

    ```groovy
    pipeline {
        agent any
        parameters {
            string(name: 'PERSON', defaultValue: 'Mr Jenkins', description: 'Who should I say hello to?')
    
            text(name: 'BIOGRAPHY', defaultValue: '', description: 'Enter some information about the person')
    
            booleanParam(name: 'TOGGLE', defaultValue: true, description: 'Toggle this value')
    
            choice(name: 'CHOICE', choices: ['One', 'Two', 'Three'], description: 'Pick something')
    
            password(name: 'PASSWORD', defaultValue: 'SECRET', description: 'Enter a password')
        }
        stages {
            stage('Example') {
                steps {
                    echo "Hello ${params.PERSON}"
    
                    echo "Biography: ${params.BIOGRAPHY}"
    
                    echo "Toggle: ${params.TOGGLE}"
    
                    echo "Choice: ${params.CHOICE}"
    
                    echo "Password: ${params.PASSWORD}"
                }
            }
        }
    }
    ```

- **triggers**
    - 파이프라인이 자동으로 다시 실행되는 방식

    | cron | 재실행의 정기적인 주기 정의 |
    | --- | --- |
    | pollSCM | 새로운 소스 변경 사항을 확인해야 하는 정기적인 주기를 정의 (새로운 변경 사항이 존재하면 트리거) |
    | upstream | 지정 작업 중 하나가 임계값 조건에 맞춰 종료될 때 파이프라인 실행 |

    ```groovy
    // Declarative //
    pipeline {
        agent any
        triggers {
            cron('H */4 * * 1-5')
        }
        stages {
            stage('Example') {
                steps {
                    echo 'Hello World'
                }
            }
        }
    }
    ```

- **when**
    - 파이프라인이 주어진 조건에 따라 해당 스테이지를 실행할지 결정

    ```groovy
    pipeline {
        agent any
        stages {
            stage('Example Build') {
                steps {
                    echo 'Hello World'
                }
            }
            stage('Example Deploy') {
                when {
                    branch 'production'
                }
                steps {
                    echo 'Deploying'
                }
            }
        }
    }
    ```

## 1-2) Parallel execution, Matrix builds, Error handling

### Parallel execution

- Parallel 섹션은 중첩된 stage들의 목록을 포함하여 서로 의존하지 않는 작업을 병렬화하여 전체 빌드 시간을 줄일 수 있다.
- 하나의 stage는 steps, stages, parallel, matrix 중 단 하나만 가져야 한다.
- parallel 내부에 parallel를 넣는 식의 중첩은 불가능하다.
- 병렬로 돌아가는 각 작업 안에서도 독립된 agent, tools, when 등을 설정할 수 있다.
- 병렬 작업 중 하나라도 실패했을 때 나머지 작업들도 즉시 취소되게 하려면 `failFast true` 설정이나 `parallelsAlwaysFailFast()` 옵션을 붙이면 된다.
    - agent 수, 라이선스, DB 등 공유 자원을 고려할 시

### Matrix builds

- 여러 조합의 테스트 환경을 자동으로 만들어 동시 실행할 때 사용
- 필수 요소 : 조합 값을 만드는 axes, 각 조합에서 실행할 stages 블록

    ```groovy
    matrix {
        axes {
            axis {
                name 'PLATFORM'
                values 'linux', 'mac', 'windows'
            }
        }
        stages {
            stage('build') {
                // ...
            }
            stage('test') {
                // ...
            }
            stage('deploy') {
                // ...
            }
        }
    }
    ```

- axes에 지정한 값들의 모든 조합을 만들어 동시에 실행
    - ex) OS 3개 $\times$ Java 버전 2개 = 총 6개 환경 동시 테스트
- 한 stage에서 steps, stages, parallel, matrix 중 단 하나만 쓸 수 있으며, 매트릭스 안에 또 매트릭스를 중첩할 수 없다.
- 각 실행 환경 마다 독립된 agent, tools, when 등의 조건을 설정할 수 있다.
- 하나라도 실패하면 전체를 즉시 중단하는 `failFast true` 설정도 가능하다.
- excludes : matrix cell 세트에서 제외할 cell을 선택하는 표현식을 지정
    - 제외할 axis의 이름과 값 지정 → 해당 조건 조합 제외
    - 제외할 값 목록이 길다면 → notValues 사용 가능

    ```groovy
    matrix {
        axes {
            axis {
                name 'PLATFORM'
                values 'linux', 'mac', 'windows'
            }
            axis {
                name 'BROWSER'
                values 'chrome', 'edge', 'firefox', 'safari'
            }
            axis {
                name 'ARCHITECTURE'
                values '32-bit', '64-bit'
            }
        }
        excludes {
            exclude {
                axis {
                    name 'PLATFORM'
                    values 'mac'
                }
                axis {
                    name 'ARCHITECTURE'
                    values '32-bit'
                }
            }
        }
        // ...
    }
    ```

- **Matrix cell-level directives**
    - 단계별 지침을 추가하여 각 cell의 전체적인 환경을 설정할 수 있다.
- axis&exclude (정적 집합) vs per-cell (동적 평가)
    - 정적 : 파이프라인 실행 전 어떤 조합을 만들지 정적으로 확정
    - 동적 : 파이프라인이 실행되는 시점에 각 조합의 값에 맞춰 동적으로 적용

### Error handling (`catchError`, `unstable`)

- catchError : 본문에서 예외가 발생하면 빌드 상태를 실패로 표시하지만, catchError 단계 다음 문장부터 파이프라인을 계속 실행한다.
    - 예외가 발생했을 때 메시지 출력, 실패 외의 다른 빌드 결과 설정, 스테이지 결과 변경, 빌드 중단 시 특정 종류의 예외 무시 등의 작업 설정 가능
    - 선언적 파이프라인에서 사용, 혹은 스테이지 결과를 설정하고 빌드 중단을 무시하는 옵션과 함께 사용
    - 대체 가능한 표현 방식 : try-catch

    ```groovy
    node {
        catchError {
            sh 'might fail'
        }
        step([$class: 'Mailer', recipients: 'admin@somewhere'])
    }
    ```

- unstable : 스테이지 결과를 unstable로 설정
    - 콘솔 로그에 메시지를 출력하고, 전체 빌드 결과와 해당 스테이지의 결과를 UNSTABLE 상태로 변경
    - 작성한 메시지는 시각화 도구 등에 표시 가능
- error : 의도적으로 에러 신호 발생 → 프로그램의 특정 파트 중단
- warnError : 실행 중 예외가 발생하면 전체 빌드 결과와 해당 스테이지 결과를 UNSTABLE로 변경 후 지정 메시지와 예외 로그를 출력하고 실행 지속
- retry : 본문 실행 중 예외가 발생할 경우 지정 횟수 만큼 재시도 → 마지막 시도에서도 실패하면 빌드 중단
- timeout : 지정한 시간 제한을 초과하면 예외를 발생시켜 빌드를 중단

## 1-3) Triggers & Webhooks: GitHub/GitLab Webhook 연동 및 SCM 이벤트 기반 트리거ing

### Github hook trigger for GITScm polling

- Github 레포지토리의 post-receive hook이 작동한 후 빌드가 실행되도록 한다.
- 수신되는 이벤트와 일치하는 레포지토리에 대해 git-plugin 내부 polling 알고리즘만 동작시킨다.
- **Usage - manual mode ver**
    - 각 프로젝트에 hook URL을 직접 등록한다.
    - Jenkins 관리 > 시스템 설정 > GitHub 항목에서 post-commit POST 요청을 수신하는 Jenkins URL을 확인하고 이를 관련 Github 레포지토리에 Webhook으로 추가한다.
- **Usage - automatic mode ver**
    - Jenkins가 모든 프로젝트에 대한 Webhook을 자동 등록한다.
    - Jenkins가 사용자를 대신해 로그인할 수 있도록 Github OAuth 토큰을 지정해야 한다.
- 보안 : 가짜 요청을 막기 위해 Jenkins가 요청 수신 후 Github에 실제 푸시를 한 것인지 재확인 한다.
- 방화벽 내 사용 : 리버스 프록시 등을 통해 외부 POST 요청을 라우팅할 엔드포인트 URL을 지정할 수 있다.
- 문제 해결 : 빌드가 미실행될 경우 Github의 Test hook 실행, Jenkins 자격 증명 재확인, 관련 클래스 로그 활성화 등을 통해 원인을 파악한다.

### Webhook 설정 및 관리

- Manage Web Hook : 플러그인이 GitLab 프로젝트에 webhook을 설정하여 push, MR, tag, note 등의 이벤트를 수신
    - `<jenkins_url>/gitlab-webhook/post`
- Manage System Hook : 플러그인이 GitLab 프로젝트에 시스템 hook을 설정하여 프로젝트 삭제 여부를 감지 (관리자 권한 필요)
    - `<jenkins_url>/gitlab-systemhook/post`
- Secret Token : GitLab 서버로부터 수신한 webhook payload를 인증할 때 필요

### SCM Trait APIs

- **Default Traits**
    - 브랜치 탐색
        - MR로 제출되지 않은 브랜치만, MR로 제출된 브랜치만, 모든 브랜치
    - 원본 프로젝트의 MR 탐색
        - 현재 수정 버전과 병합된 MR 병합, 현재 MR 수정 버전, 현재 MR 수정 버전 및 현재 수정 버전과 병합된 MR 둘 다
    - 포크된 프로젝트의 MR 탐색
        - 현재 수정 버전과 병합된 MR 병합, 현재 MR 수정 버전, 현재 MR 수정 버전 및 현재 수정 버전과 병합된 MR 둘 다
    - 신뢰 수준
        - Members : 작성자가 원본 프로젝트의 멤버인 포크된 프로젝트의 MR 탐색
        - Trusted Members : 작성자가 원본 프로젝트에서 Developer/Maintainer/Owner 접근 권한을 가진 포크된 프로젝트의 MR 탐색
        - Everyone : 아무나 제출한 포크된 프로젝트의 MR 탐색
        - Nobody : 포크된 프로젝트에서 어떤 MR도 탐색X
- **Additional Traits**
    - Trigger build on merge request comment
        - 원하는 comment가 작성되었을 때 MR의 빌드가 재실행되도록 활성화하는 옵션
        - Trusted Members만 주로 트리거 가능
        - 옵션 비활성화 시 해당 프로젝트에 접근 권한이 있는 모든 사용자가 MR 댓글을 통해 빌드 트리거 가능
    - Override hook management modes
        - Webhook 및 System hook의 기본 관리 모드를 재정의
        - 현재 webhook에 대한 ITEM credentials는 지원되지 않는다.
    - Webhook Listener Conditions
        - Webhook 내용에 기반하여 빌드가 트리거되어야 하는 시점에 대한 조건을 설정

### JCasC에서 설정

```yaml
# jenkins.yaml로 GitLab 서버 구성

credentials:
  system:
    domainCredentials:
      - credentials:
          - gitlabPersonalAccessToken:
              scope: SYSTEM
              id: "i<3GitLab"
              token: "***" # gitlab personal access token
          - gitlabGroupAccessToken:
              scope: SYSTEM
              id: "i<3GitLab"
              token: "***" # gitlab group access token

unclassified:
  gitLabServers:
    servers:
      - credentialsId: "i<3GitLab" # same as id specified for gitlab personal access token credentials
        manageWebHooks: true
        manageSystemHooks: true # access token should have admin access to set system hooks
        name: "gitlab-3214"
        serverUrl: "https://gitlab.com"
        hooksRootUrl: ""
        secretToken: ""
```

## 1-4) 참고 문헌

- <https://www.jenkins.io/doc/book/pipeline/>
- <https://www.jenkins.io/doc/book/pipeline/getting-started/>
- <https://www.jenkins.io/doc/book/pipeline/syntax/>
- <https://www.jenkins.io/doc/pipeline/steps/workflow-basic-steps/>
- <https://plugins.jenkins.io/github/>
- <https://plugins.jenkins.io/gitlab-branch-source/>
