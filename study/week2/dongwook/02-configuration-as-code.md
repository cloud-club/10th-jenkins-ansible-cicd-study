# Configuration as Code (JCasC)

## 핵심 개념

- Jenkins Configuration as Code(JCasC)는 Jenkins Controller 설정을 사람이 읽을 수 있는 YAML 파일로 선언하고 관리하는 방식이다.
- JCasC를 사용하면 Jenkins 웹 UI에서 설정하던 값을 코드 형태로 저장하고, 동일한 설정을 다른 Controller에도 재현할 수 있다.
- JCasC 설정 파일은 Git 같은 SCM에 저장할 수 있으므로 누가, 언제, 어떤 설정을 변경했는지 추적하기 쉽다.
- 설정 변경 이력이 남기 때문에 문제가 발생했을 때 이전 설정으로 되돌리기도 쉽다.
- JCasC를 사용하려면 Jenkins Controller에 `Configuration as Code` 플러그인이 설치되어 있어야 한다.

## JCasC를 사용하는 이유

- Jenkins 설정을 수동 UI 작업에 의존하지 않고 코드로 관리할 수 있다.
- Jenkins Controller를 새로 구성하거나 복구할 때 동일한 설정을 빠르게 재현할 수 있다.
- 설정 변경을 Pull Request와 코드 리뷰 대상으로 만들 수 있다.
- 운영 환경, 테스트 환경, 로컬 실습 환경의 Jenkins 설정 차이를 줄일 수 있다.
- Jenkins 관리자가 Groovy init script를 직접 작성하지 않아도 선언적인 YAML 파일로 설정을 관리할 수 있다.

## JCasC로 관리할 수 있는 항목

- Jenkins 기본 시스템 설정
- 보안 영역(Security Realm)
- 권한 전략(Authorization Strategy)
- 사용자 및 권한 설정
- Credentials 설정
- Global Tools 설정
- Agent/Node 설정
- 일부 플러그인 설정
- 기타 Jenkins 전역 설정

## JCasC로 관리하지 않는 항목

- JCasC는 Jenkins 설정을 관리하는 도구이며, 플러그인을 설치하는 도구는 아니다.
- 필요한 플러그인은 Docker 이미지 빌드 시 `plugins.txt`로 미리 설치하거나, Helm Chart, Plugin Installation Manager Tool 같은 별도 방법으로 설치해야 한다.
- Pipeline Job이나 Freestyle Job 같은 Job 정의는 JCasC만으로 관리하기보다 Job DSL, Pipeline 코드, Multibranch Pipeline 같은 방식과 함께 관리하는 경우가 많다.
- 빌드 기록, 워크스페이스, 아티팩트 같은 실행 결과 데이터는 JCasC 관리 대상이 아니다.

## 기본 YAML 구조

- JCasC 기본 YAML 파일은 주로 다음 섹션으로 구성된다.
- `jenkins`
  - Jenkins 루트 객체를 정의한다.
  - `Manage Jenkins` -> `System`, `Manage Jenkins` -> `Nodes and Clouds`에서 설정하는 값들이 포함된다.
- `tool`
  - 빌드 도구 설정을 정의한다.
  - `Manage Jenkins` -> `Tools`에서 설정하는 Git, JDK, Maven, Gradle 등의 도구 설정이 포함된다.
- `unclassified`
  - Jenkins 핵심 설정 외의 기타 전역 설정을 정의한다.
  - 설치된 플러그인의 전역 설정이 이 섹션에 포함되는 경우가 많다.
- `credentials`
  - Jenkins Credentials를 정의한다.
  - 민감한 값은 YAML에 직접 작성하지 말고 환경 변수나 별도 Secret 관리 방식과 연동하는 것이 좋다.

## YAML 작성 시 주의할 점

- YAML은 대소문자를 구분한다.
- 들여쓰기가 문법적으로 중요하다.
- 들여쓰기에는 탭이 아니라 공백을 사용한다.
- 키 뒤에는 콜론(`:`)과 공백을 작성한다.
- 리스트 항목은 하이픈(`-`)으로 표현하며, 같은 리스트의 항목은 같은 들여쓰기 수준에 있어야 한다.
- `true`, `false`, `Yes`, `No` 같은 값은 따옴표가 없으면 Boolean 값으로 해석될 수 있다.
- `2`, `3.0` 같은 값은 숫자 값으로 해석될 수 있다.
- 문자열 그대로 유지해야 하는 값은 따옴표로 감싸는 것이 안전하다.
- JCasC 설정 파일은 단순 YAML 문법뿐 아니라 Jenkins와 플러그인이 기대하는 설정 구조까지 맞아야 한다.

## 설정 파일 위치

- 기본적으로 JCasC 플러그인은 `$JENKINS_HOME/jenkins.yaml` 파일을 찾는다.
- 다른 위치를 사용하려면 `CASC_JENKINS_CONFIG` 환경 변수를 설정할 수 있다.
- `CASC_JENKINS_CONFIG`에는 다음 값을 지정할 수 있다.
  - 단일 YAML 파일 경로
  - YAML 파일들이 있는 디렉터리 경로
  - HTTP/HTTPS URL
- 디렉터리를 지정하면 플러그인은 `.yml`, `.yaml`, `.YML`, `.YAML` 확장자를 가진 파일을 재귀적으로 찾는다.
- 여러 설정 파일을 사용할 경우 각 파일은 서로 보완적인 설정이어야 한다.
- 서로 다른 파일이 같은 설정 값을 중복 정의하면 충돌이 발생하고 `ConfiguratorException`이 발생할 수 있다.
- 환경 변수 대신 Java 시스템 속성인 `casc.jenkins.config`로 설정 파일 위치를 지정할 수도 있다.

## JCasC 설정 예시

- 아래 예시는 Configuration as Code 플러그인 README의 기본 예시를 기반으로 한다.
- `jenkins` 섹션에서는 시스템 메시지, 전역 환경 변수, LDAP 인증, 정적 Agent, Agent 포트를 설정한다.
- `tool` 섹션에서는 Git 도구 위치를 설정한다.
- `credentials` 섹션에서는 SSH Private Key Credential을 설정한다.

```yaml
jenkins:
  systemMessage: "Jenkins configured automatically by Jenkins Configuration as Code plugin\n\n"
  globalNodeProperties:
    - envVars:
        env:
          - key: VARIABLE1
            value: foo
          - key: VARIABLE2
            value: bar
  securityRealm:
    ldap:
      configurations:
        - groupMembershipStrategy:
            fromUserRecord:
              attributeName: "memberOf"
          inhibitInferRootDN: false
          rootDN: "dc=acme,dc=org"
          server: "ldaps://ldap.acme.org:1636"

  nodes:
    - permanent:
        name: "static-agent"
        remoteFS: "/home/jenkins"
        launcher:
          inbound:
            workDirSettings:
              disabled: true
              failIfWorkDirIsMissing: false
              internalDir: "remoting"
              workDirPath: "/tmp"

  slaveAgentPort: 50000

tool:
  git:
    installations:
      - name: git
        home: /usr/local/bin/git

credentials:
  system:
    domainCredentials:
      - credentials:
          - basicSSHUserPrivateKey:
              scope: SYSTEM
              id: ssh_with_passphrase_provided
              username: ssh_root
              passphrase: ${SSH_KEY_PASSWORD}
              description: "SSH passphrase with private key file. Private key provided"
              privateKeySource:
                directEntry:
                  privateKey: ${SSH_PRIVATE_KEY}
```

- JCasC는 `${VAR}` 형식을 변수 보간 표현식으로 처리한다.
- 예시의 `${SSH_KEY_PASSWORD}`, `${SSH_PRIVATE_KEY}`는 Jenkins 설정 파일에 Secret 값을 직접 저장하지 않고 환경 변수에서 값을 주입받기 위한 형태이다.
- 실제 문자열로 `${...}` 값을 사용해야 한다면 `^${VAR}`처럼 이스케이프해야 한다.

## JCasC 기반 Jenkins 설정 관리 흐름

- JCasC의 핵심은 Jenkins 설정을 백업하는 것이 아니라 Jenkins Controller 설정을 선언적으로 관리하는 것이다.
- 실무에서는 Jenkins UI에서 설정을 변경한 뒤 주기적으로 YAML을 추출하는 방식보다, Git에 저장된 JCasC YAML을 설정의 기준(Source of Truth)으로 두는 방식이 권장된다.

```text
Git Repository
  |
  +-- jenkins.yaml
        |
        v
Pull Request / Code Review
        |
        v
JCasC 적용
        |
        v
Jenkins Controller 설정 반영
```

- 설정 변경이 필요하면 Jenkins UI를 직접 수정하기보다 먼저 `jenkins.yaml`을 수정한다.
- 변경 사항은 Pull Request와 리뷰를 거쳐 Git 이력에 남긴다.
- 검증된 YAML을 Jenkins Controller에 적용해 실제 설정을 반영한다.
- 이 흐름을 사용하면 Controller를 다시 구성해야 할 때도 같은 설정을 재현하기 쉽다.

## JCasC 적용 방식

- Jenkins UI에서 `Manage Jenkins` -> `Configuration as Code`로 이동하면 현재 설정 파일 경로를 확인할 수 있다.
- `View Configuration`을 통해 현재 Controller 설정을 YAML 형태로 확인할 수 있다.
- `Download Configuration`으로 현재 설정을 파일로 내려받을 수 있다.
- `Reload existing configuration`을 사용하면 Jenkins를 재시작하지 않고 기존 JCasC 설정 파일을 다시 읽어 적용할 수 있다.
- 단, 큰 설정 변경은 실제 재시작 상황에서도 정상적으로 적용되는지 테스트 환경에서 확인하는 것이 좋다.

## 초기 도입 흐름

- 기존 Jenkins를 UI 기반으로 운영하고 있었다면 현재 설정을 Export해서 초기 YAML을 만들 수 있다.
- Export 결과에는 기본값, 불필요한 설정, 플러그인별 세부 설정이 많이 포함될 수 있다.
- Export 파일을 그대로 운영 기준으로 삼기보다 필요한 설정만 정리해서 Git에 등록하는 것이 좋다.

```text
현재 Jenkins 설정
      |
      v
JCasC Export
      |
      v
YAML 검토 및 정리
      |
      v
Git Repository 등록
      |
      v
이후부터 Git 기준으로 관리
```

## UI 변경과 Configuration Drift

- Jenkins Controller 설정은 JCasC 또는 UI 중 하나를 기준으로 관리하는 것이 좋다.
- JCasC로 관리되는 설정을 Jenkins UI에서 직접 수정하면 Git의 YAML과 실제 Jenkins 설정이 달라진다.
- 이런 불일치 상태를 Configuration Drift라고 볼 수 있다.
- JCasC 설정이 다시 적용되거나 Controller가 재시작되면 UI에서 직접 바꾼 값이 JCasC 파일의 값으로 덮어써질 수 있다.

```text
Git의 JCasC 설정
        |
        | 불일치
        v
실제 Jenkins 설정
```

- 운영 중 긴급 대응으로 UI를 직접 수정했다면 이후 반드시 JCasC 설정에도 같은 내용을 반영해야 한다.
- 이때 Export 결과를 기존 `jenkins.yaml`에 그대로 덮어쓰기보다 `git diff`로 변경 내용을 확인하고 필요한 부분만 반영하는 것이 안전하다.

```text
UI에서 긴급 설정 변경
        |
        v
JCasC Export
        |
        v
기존 jenkins.yaml과 Diff 비교
        |
        v
필요한 변경 사항만 반영
        |
        v
Git Commit / Pull Request
        |
        v
설정 상태 동기화
```

## 보안 고려사항

- JCasC 설정 파일은 Jenkins의 보안 설정과 권한 설정을 변경할 수 있으므로 관리자 수준의 중요도를 가진다.
- 보안 영역이나 권한 전략을 잘못 수정하면 의도하지 않은 사용자에게 높은 권한을 줄 수 있다.
- JCasC 파일을 Git에 저장하더라도 모든 사용자가 자유롭게 수정할 수 있게 두면 안 된다.
- 관리자 외 사용자가 변경할 수 있는 구조라면 반드시 코드 리뷰를 통해 보안 영향을 검토해야 한다.
- Secret 값은 Git에 직접 저장하지 않는다.
- Secret은 환경 변수, Kubernetes Secret, Vault 같은 별도 Secret 관리 방식과 연동하는 것이 좋다.
- Secret 변수를 공개 위치에 보간하면 민감 정보가 노출될 수 있으므로 사용 위치를 주의해야 한다.

## 권장 운영 원칙

- JCasC YAML을 Jenkins 설정의 Source of Truth로 관리한다.
- Jenkins UI를 통한 직접 설정 변경은 최소화한다.
- 설정 변경은 Git Commit과 Pull Request를 통해 이력을 남긴다.
- JCasC 변경 사항은 가능하면 테스트 환경에서 먼저 검증한다.
- 운영 중 긴급하게 UI를 수정한 경우 반드시 JCasC YAML에도 동일한 내용을 반영한다.
- JCasC Export는 초기 설정 구성이나 실제 Jenkins 설정과의 비교 용도로 활용한다.
- Credential의 실제 Secret 값은 Git에 직접 저장하지 않는다.
- JCasC는 Jenkins 설정 관리 도구이며, 플러그인 설치와 Job 생성까지 모두 대신하는 도구로 이해하면 안 된다.

## 참고 자료

- [Jenkins 공식 문서 - Configuration as Code](https://www.jenkins.io/doc/book/managing/casc/)
- [Jenkins Plugin - Configuration as Code](https://plugins.jenkins.io/configuration-as-code/)
- [Configuration as Code Plugin README](https://github.com/jenkinsci/configuration-as-code-plugin/blob/master/README.md)
- [Buildkite - Jenkins Configuration as Code hands-on guide](https://buildkite.com/resources/blog/automating-jenkins-with-jcasc-configuration-as-code/)
