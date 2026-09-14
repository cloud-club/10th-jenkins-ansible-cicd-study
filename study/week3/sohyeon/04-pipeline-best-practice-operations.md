# 4. Pipeline Best Practices & Operations

## 4-1) Controller OOM 방지

### OOM

- OOM = Out Of Memory
- 컴퓨터 시스템에서 사용 가능한 메모리가 부족하여 발생하는 문제

### Groovy 코드와의 연관성

- 파이프라인에서 Groovy 코드는 항상 컨트롤러에서 실행된다.

    → 컨트롤러 자원 (메모리 및 CPU)를 사용한다.

    → 파이프라인의 복잡성 증가(Groovy 코드의 양, 사용되는 스텝 수 등)에 따라 컨트롤러에서 더 많은 자원을 요구하게 된다.

- 파이프라인에 의해 실행되는 Groovy 코드의 양을 줄이는 것이 중요하다.
    - Groovy 코드를 파이프라인의 핵심 기능으로 사용하기보다 일련의 작업들을 연결하는 용도로 사용하기

### Groovy 코드 작업

- **JsonSlurper**
    - 디스크의 파일에서 데이터를 읽어와 JSON 객체로 파싱한 뒤 파이프라인에 해당 객체를 주입한다.
    - 로컬 파일을 컨트롤러의 메모리에 두 번 로드하기 때문에 파일이 매우 크거나 명령이 자주 실행되면 많은 메모리를 필요로 하게 된다.

        → JsonSlurper 대신 sh 쉘 스크립트를 사용하여 표준 출력을 반환하면 에이전트 자원을 사용하기 때문에 파일 크기를 더 작게 줄여서 파싱하는 데 도움이 된다.

- **HttpRequest**
    - 외부 소스에서 데이터를 가져와 변수에 저장한다.
    - 요청이 컨트롤러에서 직접 전송되고 요청에 대한 응답 데이터가 두 번 저장되기 때문에 모범적인 방법은 아니다.

        → sh 쉘 스텝을 사용하여 에이전트에서 HTTP 요청을 수행하여 최소한으로 필요한 정보만 젠킨스 컨트롤러로 전달되도록 한다.

- 데이터 파싱이나 HTTP 요청 등의 무거운 작업을 sh 쉘 명령을 통해 에이전트에서 대신 수행한다.

### Groovy CPS (Continuation-Passing Style)

- 파이프라인 코드는 jenkins가 재시작된 후에도 파이프라인을 재개할 수 있도록 CPS 변환이 적용된다.
    - 파이프라인이 스크립트를 실행하는 동안 jenkins를 종료학나 에이전트와의 연결이 끊어지더라도, 다시 돌아왔을 때 jenkins는 진행 중이던 작업을 기억하고 스크립트를 중단된 적이 없는 것처럼 계속 실행한다.
- CPS는 파이프라인 재개에 핵심적인 역할을 한다.
- 내부적으로 CPS는 파이프라인의 현재 상태와 실행될 남은 파이프라인을 직렬화할 수 있는 기능에 의존한다.
    - 직렬화할 수 없는 객체를 사용하게 되면 NotSerializableException이 발생하므로 필요한 시점에 즉시 값을 계산하거나 필요한 경우 **@NonCPS 어노테이션**을 활용해야 한다. (CPS 변환 우회)
    - @NonCPS 어노테이션은 Groovy 언어 지원의 한계를 우회하거나, 더 나은 성능을 얻기 위해 수행될 수 있다.
        - 메서드 본문이 네이티브 Groovy 의미 구조를 사용
        - 해석기가 상당한 오버헤드 발생
    - 이러한 메서드는 파이프라인 스텝과 같이 CPS 변환이 적용된 코드를 호출해서는 안 된다.

        ```groovy
        @NonCPS
        def compileOnPlatforms() {
          ['linux', 'windows'].each { arch ->
            node(arch) {
              sh 'make'
            }
          }
        }
        compileOnPlatforms()
        ```

    - 이 메서드에서 node 또는 sh 스텝을 사용하는 것은 허용되지 않으며, 비정상적인 동작이 발생한다. (해당 스텝들은 CPS 엔진 위에서 동작하도록 설계되어 있다.)

        → 어노테이션을 제거하면 된다.

## 4-2) Artifact Management & Pipeline Performance Tuning

### archieveArtifacts

- Jenkins 파이프라인 빌드 과정에서 생성된 주요 파일을 캡처하여 jenkins 컨트롤러에 저장하는 파이프라인 단계
    - 지정된 포함 패턴(`**/target/*.jar`)과 일치하도록 빌드된 파일 캡처

### stash (unstash)

- 동일한 파이프라인 실행 내의 모든 노드/작업 공간에서 나중에 사용할 수 있도록 파일 집합을 저장한다.
- unstash는 이전에 stash한 파일 집합을 현재 작업 공간으로 복원한다.
- 기본적으로 stash 처리된 파일은 파이프라인 실행이 끝나면 폐기된다.
    - 다른 플러그인을 통해 stash를 더 오래 유지하도록 동작을 변경할 수 있다.
- 한 파이프라인에서 실행된 stash는 다른 실행, 다른 파이프라인 또는 다른 작업에서 사용할 수 없다.

    → 단일 실행 외에 사용할 아티팩트를 영구 보관하려면 archiveArtifacts를 사용하는 것이 좋다.

- stash/unstash는 작은 크기의 파일을 처리하도록 설계되었다.
    - stash된 파일은 TAR 형태로 아카이빙되며, 파일 크기가 크면 컨트롤러의 자원을 상당히 소모한다.
    - 대용량이라면 External Workspace Manager 플러그인이나 Nexus, Artifactory와 같은 외부 레포지토리 관리자를 사용한다.
    - Artifact Manager on S3 플러그인이나 원격 아티팩트 관리자가 있는 다른 플러그인을 사용하면 stash가 에이전트에서 S3로 직접 전송되므로 컨트롤러의 성능에 영향을 주지 않는다.

## 4-3) Notifications & Log Summarization

### 파이프라인 관련 Notification 전송 방법

- **Email**

    ```groovy
    post {
        failure {
            mail to: 'team@example.com',
                 subject: "Failed Pipeline: ${currentBuild.fullDisplayName}",
                 body: "Something is wrong with ${env.BUILD_URL}"
        }
    }
    ```

- **Slack**

    ```groovy
    post {
        success {
            slackSend channel: '#ops-room',
                      color: 'good',
                      message: "The pipeline ${currentBuild.fullDisplayName} completed successfully."
        }
    }
    ```

### Slack 연동

- 과정
    - Slack API 페이지에서 앱을 생성한다. (아래의 YAML 코드 사용)

    ```yaml
    display_information:
      name: Jenkins
    features:
      bot_user:
        display_name: Jenkins
        always_online: true
    oauth_config:
      scopes:
        bot:
          - channels:read
          - chat:write
          - chat:write.customize
          - files:write
          - reactions:write
          - users:read
          - users:read.email
          - groups:read
    settings:
      org_deploy_enabled: false
      socket_mode_enabled: false
      token_rotation_enabled: false
    ```

    - 앱이 요구하는 권한을 승인하고 Bot User OAuth Access Token 값을 사용하여 Jenkins credential에 추가한다.
    - 알림 받고 싶은 Slack 채널에 jenkins 봇 사용자(/invite @Jenkins)를 초대한다.
- 모든 작업에 대해 Slack으로 알림이 전송되도록 설정하려면 추가 플러그인인 Global Slack Notifier 플러그인 설치를 고려하는 것이 좋다.
- JCasC를 사용하여 Slack 연동 토큰과 워크스페이스 도메인을 코드 형태로 사전 정의하고 자동 구성할 수 있다.

    ```yaml
    credentials:
      system:
        domainCredentials:
          - credentials:
              - string:
                  scope: GLOBAL
                  id: slack-token
                  secret: '${SLACK_TOKEN}'
                  description: Slack token
    
    unclassified:
      slackNotifier:
        teamDomain: <your-slack-workspace-name> # i.e. your-company (just the workspace name not the full url)
        tokenCredentialId: slack-token
        botUser: true
    ```

- 연동 연결 실패 문제

    ```text
    WARNING j.p.slack.StandardSlackService#publish: Response Code: 404
    ```

    - 봇 사용자 모드를 활성화했는가? → Slack 제작 기본 legacy 앱을 사용한다면 체크 해제
    - Override URL을 설정했는가? → 지우기
    - 추가 로깅 활성화
        - StandardSlackService 클래스에 대한 로그 리코더(log recorder)를 추가

### Teams 연동 (Office 365 Connector plugin)

- Outlook, Office 365 Groups 및 Microsoft Teams에 액션 실행이 가능한 메시지를 전송하는 데 사용되는 플러그인
- 해당 플러그인은 jenkins 서버에 설치 → jenkins 작업에서 이를 설정하고 가져온 웹후크 URL 추가

    ```groovy
    stage('Upload') {
        steps {
            // some instructions here
            office365ConnectorSend webhookUrl: 'https://outlook.office.com/webhook/123456...',
                message: 'Application has been deployed',
                status: 'Success'
        }
    }
    ```

    - 웹후크 URL을 통해 빌드/배포 상태 메시지 및 커스텀 알림을 파이프라인 단계에서 직접 전송한다.

    ```groovy
    pipeline {
    
        agent any
    
        stages {
            stage('Init') {
                steps {
                    echo 'Hello!'
                }
            }
        }
    
        post {
            failure {
                office365ConnectorSend webhookUrl: "https://prod.westeurope.logic.azure.com:443/workflows...",
                  message: 'Something went wrong', 
                  status: 'Failure',
                  adaptiveCards: true
            }
        }
    }
    ```

    - 빌드 실패 시 원인이나 관련 세부 정보를 포함하여 웹후크로 실패 로깅 알림을 전송한다.
- Jenkins -> Manage Jenkins -> Configure System 하위의 글로벌 설정을 통해서도 구성할 수 있다. (기본값 적용)
- 작업 개별 설정에서 override 할 수 있지만 글로벌 설정값을 변경하더라도 기존 존재하던 작업의 설정이 자동으로 업데이트 되지는 않는다.

## 4-4) 참고 문헌

- <https://www.jenkins.io/doc/book/pipeline/pipeline-best-practices/>
- <https://www.jenkins.io/doc/book/pipeline/cps-method-mismatches/>
- <https://www.jenkins.io/doc/pipeline/steps/workflow-basic-steps/>
- <https://www.jenkins.io/doc/pipeline/tour/post/>
- <https://plugins.jenkins.io/slack/>
- <https://plugins.jenkins.io/Office-365-Connector/>
