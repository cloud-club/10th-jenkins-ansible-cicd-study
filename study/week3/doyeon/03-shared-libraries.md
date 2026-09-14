# Week 3 개념 정리 — Shared Libraries


## Shared Library를 사용하는 이유

여러 프로젝트에 Jenkins Pipeline을 적용하면 Build, Test, Docker 이미지 생성, Deploy 같은 단계가 반복된다. 이를 각 Jenkinsfile에 직접 작성하면 같은 코드가 여러 저장소에 복사되고, 실행 방식이나 배포 정책이 바뀔 때 모든 Jenkinsfile을 각각 수정해야 한다.

Shared Library는 이러한 공통 Pipeline 코드를 별도 저장소에서 관리하고 여러 프로젝트가 함께 사용하도록 지원한다. 중복을 줄이는 것뿐 아니라 조직의 빌드·배포 절차를 한곳에서 일관되게 관리하는 것이 핵심이다.

```text
각 프로젝트의 Jenkinsfile
        ↓ Library 호출과 프로젝트별 설정
Shared Library
        ↓ 공통 Build / Test / Deploy 로직
Jenkins Pipeline 실행
```

Shared Library를 사용하면 다음과 같은 이점이 있다.

- 반복되는 Pipeline 코드 제거
- 공통 로직과 정책의 중앙 관리
- 수정 사항을 여러 프로젝트에 일관되게 적용
- Jenkinsfile에는 프로젝트별 차이와 설정만 유지

예를 들어 각 Jenkinsfile에 전체 Pipeline을 작성하는 대신 다음과 같이 공통 Step을 호출할 수 있다.

```groovy
@Library('company-ci') _

buildApp(
    name: 'order-service',
    javaVersion: 21,
    deploy: true
)
```

`buildApp` 내부의 Build, Test, Deploy 흐름은 Shared Library가 담당하고 Jenkinsfile은 서비스 이름, Java 버전, 배포 여부만 전달한다. 즉, **Jenkinsfile은 무엇을 실행할지 선언하고 Shared Library는 어떻게 실행할지 구현한다.**

---

## 등록과 버전

Shared Library를 등록할 때는 다음 정보가 필요하다.

| 항목 | 예시 |
|---|---|
| Name | `company-ci` |
| Repository | Shared Library Git 저장소 |
| Default version | `main` |

버전에는 branch, tag, commit hash를 사용할 수 있다. 프로젝트에서 안정적인 버전을 고정하려면 Library 이름 뒤에 버전을 지정한다.

```groovy
@Library('company-ci@v1.2.0') _
```

Git 기반 환경에서는 branch나 tag를 직접 인식하는 **Modern SCM**을 주로 사용한다. Legacy SCM의 상세 설정은 필요할 때 확인한다.

---

## 디렉터리 구조

```text
(root)
├── vars/
│   ├── buildApp.groovy
│   └── buildApp.txt
├── src/
│   └── com/mycompany/pipeline/BuildService.groovy
└── resources/
    └── com/mycompany/deployment.yaml
```

- **`vars/`**: Jenkinsfile에서 바로 호출할 전역 함수와 Custom Step
- **`src/`**: package 구조로 작성하는 일반 Groovy 클래스와 재사용 로직
- **`resources/`**: YAML, JSON, 스크립트 등의 정적 파일

```text
vars = Pipeline에 노출하는 인터페이스
src  = 재사용 가능한 구현 로직
```

### `vars/` — Global Variable과 Custom Step

`vars/`의 파일명은 Pipeline에서 사용하는 전역 이름이 된다. 파일명은 lowercase 또는 camelCase로 작성한다.

```groovy
// vars/sayHello.groovy
def call(String name = 'human') {
    echo "Hello, ${name}."
}
```

`call()`을 정의하면 파일명을 함수처럼 호출할 수 있다.

```groovy
// Jenkinsfile
sayHello 'Joe'
```

여러 메서드를 정의하면 전역 객체의 메서드처럼 사용한다.

```groovy
// vars/log.groovy
def info(String message) {
    echo "[INFO] ${message}"
}
```

```groovy
// Jenkinsfile
log.info('Build started')
```

같은 이름의 `.txt` 파일을 두면 Jenkins의 Global Variable Reference에 사용 설명을 제공할 수 있다.

### `src/` — Groovy 클래스

`src/`는 Pipeline 실행 시 classpath에 포함된다. 클래스는 package 경로에 맞춰 작성하고 Jenkinsfile이나 `vars/`에서 import해 사용한다.

```groovy
// src/com/mycompany/pipeline/BuildService.groovy
package com.mycompany.pipeline

class BuildService implements Serializable {
    private final def steps

    BuildService(steps) {
        this.steps = steps
    }

    void build(Map config = [:]) {
        steps.sh './gradlew build'
    }
}
```

`src/`의 일반 클래스에는 `sh`, `git`, `echo` 같은 Pipeline Step이 자동으로 제공되지 않는다. Pipeline 실행 컨텍스트를 생성자에 전달한 뒤 `steps.sh`처럼 호출해야 한다.

```groovy
import com.mycompany.pipeline.BuildService

def service = new BuildService(this)
service.build()
```

`Serializable`은 Pipeline이 중단되거나 Jenkins가 재시작될 때 실행 상태를 저장하고 복구하는 데 필요하다.

### `resources/` — 정적 파일

`resources/`의 파일은 `libraryResource`로 읽는다. 반환값은 문자열이다.

```groovy
def yaml = libraryResource('com/mycompany/deployment.yaml')
writeFile file: 'deployment.yaml', text: yaml
```

Library 간 파일명 충돌을 피하기 위해 package 형태의 고유 경로를 사용한다.

---

## `@Library` 사용법

`vars/`의 Custom Step만 사용할 때는 다음과 같이 Library를 불러온다.

```groovy
@Library('company-ci') _

buildApp(name: 'order-service')
```

`vars/` 항목은 Pipeline 전역에 노출되므로 import하지 않는다.

`src/`의 클래스를 사용할 때는 Library 선언과 import를 함께 작성할 수 있다.

```groovy
@Library('company-ci')
import com.mycompany.pipeline.BuildService

def service = new BuildService(this)
```

---

## 권장 구조: `vars/`는 얇게, 로직은 `src/`로

`vars/`는 Jenkinsfile이 쉽게 호출할 수 있도록 **입구 역할**만 맡기는 것이 좋다. 실제 빌드나 배포 로직은 `src/`의 클래스가 담당한다.

예를 들어 Jenkinsfile에서 다음과 같이 호출한다고 하자.

```groovy
buildApp(name: 'order-service')
```

이 호출은 먼저 `vars/buildApp.groovy`로 전달된다. `vars/`는 전달받은 설정을 직접 처리하지 않고 `src/`의 `BuildService`에 넘긴다.

```groovy
// vars/buildApp.groovy
import com.mycompany.pipeline.BuildService

def call(Map config = [:]) {
    new BuildService(this).build(config)
}
```

실행 순서는 다음과 같다.

```text
Jenkinsfile에서 buildApp(...) 호출
    ↓
vars/buildApp.groovy가 호출을 받음
    ↓
src/.../BuildService.groovy에 설정을 전달
    ↓
BuildService가 실제 Build 로직을 실행
```

즉, 역할은 다음처럼 나뉜다.

- `vars/`: Jenkinsfile에서 사용할 이름과 입력값을 정의
- `src/`: 실제 Build, Test, Deploy 로직을 구현

`vars/` 안에 실행 중인 값이나 변경되는 상태를 오래 보관하는 것은 피한다. Jenkins가 재시작되면 Global Variable의 상태가 유지되지 않을 수 있기 때문이다. 필요한 값은 Jenkinsfile에서 인자로 받아 `src/`에 전달한다.

이렇게 분리하면 Jenkinsfile은 짧게 유지되고, 실제 로직은 여러 Custom Step에서 재사용하거나 클래스 단위로 테스트하기 쉬워진다.

---

## CPS와 `Serializable`

Jenkins Pipeline은 몇 분에서 몇 시간 동안 실행되거나 중간에 사용자 입력을 기다릴 수 있다. 그동안 Jenkins가 재시작되더라도 Pipeline을 처음부터 다시 실행하지 않고 멈춘 지점부터 이어가야 한다.

이를 위해 Jenkins는 Pipeline 코드를 CPS(Continuation Passing Style) 형태로 변환하고, 현재 실행 위치와 변수 상태를 저장한다.

```text
Build 실행 → input에서 승인 대기 → Jenkins 재시작
                                  ↓
                         저장된 상태를 불러옴
                                  ↓
                         승인 대기부터 계속 실행
```

### 왜 `Serializable`이 필요한가

Jenkins가 Pipeline 상태를 저장할 때는 실행 중 사용하던 객체도 함께 저장해야 한다. 객체를 저장 가능한 형태로 바꾸는 것을 **직렬화(Serialization)**라고 한다.

따라서 `src/`의 클래스가 Pipeline 실행 중 유지되는 경우 `Serializable`을 구현한다.

```groovy
class BuildService implements Serializable {
    def steps

    BuildService(steps) {
        this.steps = steps
    }
}
```

즉, `Serializable`은 해당 객체를 Jenkins가 저장했다가 Pipeline 재개 시 다시 복원할 수 있다는 의미다.

### `@NonCPS`

모든 메서드가 CPS 변환을 필요로 하는 것은 아니다. 문자열 가공이나 정렬처럼 Jenkins Pipeline Step과 관계없는 순수 계산 메서드는 `@NonCPS`를 사용해 일반 Groovy 코드로 실행할 수 있다.

```groovy
@NonCPS
def sortNames(List<String> names) {
    names.sort()
}
```

`@NonCPS` 메서드는 Jenkins가 실행 상태를 추적하지 않으므로 그 안에서 `sh`, `echo`, `input` 같은 Pipeline Step을 호출하면 안 된다.

---

## Library 등록 범위와 신뢰 수준

| 구분 | 적용 범위 | 신뢰 수준 |
|---|---|---|
| Global Library | Jenkins 전체 | Trusted 또는 Untrusted |
| Folder Library | 해당 Folder와 하위 Folder | 항상 Untrusted |

Global Library는 `Manage Jenkins → System → Global Trusted/Untrusted Pipeline Libraries`에서 등록한다.

### Groovy Sandbox란

Groovy Sandbox는 Pipeline의 Groovy 코드가 Jenkins 내부 객체와 Java API를 마음대로 호출하지 못하도록 제한하는 보안 장치다. Docker와 같은 완전한 격리 환경은 아니며, **Jenkins가 허용한 Pipeline Step과 API만 사용하게 만드는 검사 계층**에 가깝다.

```text
Untrusted Library
코드 실행 → Sandbox 검사 → 허용된 기능만 실행

Trusted Library
코드 실행 → Sandbox 검사 없음 → Jenkins 내부 API까지 실행 가능
```

### Untrusted Library

Untrusted Library는 Groovy Sandbox 안에서 실행된다. 일반적인 CI/CD에 필요한 Pipeline Step은 대부분 사용할 수 있다.

```groovy
echo 'Build started'
sh './gradlew build'
git url: 'https://github.com/example/app.git'
junit 'build/test-results/**/*.xml'
```

반면 Groovy나 Java API로 Jenkins Controller에 직접 접근하는 코드는 기본적으로 차단된다.

```groovy
Jenkins.get()                         // Jenkins 내부 객체 접근
new File('/etc/passwd').text          // 파일 시스템 직접 접근
'curl example.com'.execute()          // 외부 프로세스 직접 실행
System.setProperty('key', 'value')    // 시스템 속성 변경
```

허용되지 않은 메서드를 호출하면 `Scripts not permitted to use method ...` 오류가 발생한다. 필요한 경우 관리자가 Script Approval로 승인할 수 있지만, 위험한 API를 계속 승인하면 Sandbox의 보호 효과가 약해질 수 있다.

### `sh`는 왜 사용할 수 있는가

`sh`도 OS 명령을 실행하지만 Jenkins가 제공하는 Pipeline Step을 거치며, 일반적으로 지정된 Agent의 Workspace에서 실행된다. 반면 `new File(...)`이나 `.execute()`는 Pipeline Step을 거치지 않고 Jenkins JVM에서 Java/Groovy 기능을 직접 호출할 수 있어 제한된다.

```text
sh '...'
→ Jenkins가 관리하는 Pipeline Step
→ 일반적으로 Agent에서 실행

new File(...), command.execute()
→ Java/Groovy API 직접 호출
→ Jenkins Controller 자원에 접근할 위험
```

Groovy Sandbox가 `sh` 내부 명령까지 안전하게 만들어 주는 것은 아니다. Agent의 OS 권한, Credentials 접근 범위 등은 별도로 제한해야 한다.

### Trusted Library

Trusted Library는 Jenkins가 Library 저장소의 코드를 신뢰한다고 보고 Sandbox 검사 없이 실행한다. Pipeline Step뿐 아니라 Jenkins 내부 API, 플러그인 API, Java API 등을 사용할 수 있어 Jenkins 자체를 관리하는 기능도 구현할 수 있다.

여기서 Jenkins 내부 API는 배포할 Java 서비스의 API가 아니라, **Jenkins의 Job, Agent, 설정, 플러그인 등을 조작하는 Jenkins 자체의 API**를 의미한다.

```groovy
import jenkins.model.Jenkins

def call() {
    Jenkins.get().nodes.each { node ->
        echo node.nodeName
    }
}
```

### Trusted Library의 위험성

Trusted Library를 사용하는 Job을 실행했다고 해서 사용자에게 Jenkins 관리자 권한이 직접 부여되는 것은 아니다. 하지만 Library가 관리자급 기능을 제공하면 Job 실행자가 그 기능을 간접적으로 실행할 수 있다.

```groovy
// Trusted Library
import jenkins.model.Jenkins

def call() {
    Jenkins.get().safeRestart()
}
```

Controller 재시작 권한이 없는 사용자도 위 Step을 포함한 Job을 실행할 수 있다면, Trusted Library를 통해 재시작을 요청할 가능성이 있다.

특히 사용자 입력을 검증하지 않고 내부 API나 명령에 전달하는 코드는 위험하다.

```groovy
def call(String methodName) {
    Jenkins.get()."${methodName}"()
}
```

따라서 Trusted Library는 미리 정해진 좁은 기능만 제공해야 하며, 다음 권한을 함께 관리해야 한다.

- Trusted Library 저장소를 수정할 수 있는 사람
- 해당 Library를 사용하는 Jenkinsfile을 수정할 수 있는 사람
- Job을 실행하고 파라미터를 입력할 수 있는 사람
- Library가 접근하는 Credentials와 Agent의 권한

### Trusted와 Untrusted 비교

| 구분 | Trusted Library | Untrusted Library |
|---|---|---|
| 실행 환경 | Groovy Sandbox 제한 없이 실행 | Groovy Sandbox 안에서 실행 |
| 주요 기능 | Jenkins 내부 API와 Java API까지 사용 가능 | 허용된 API와 Pipeline Step 사용 |
| 주요 용도 | Jenkins 자체의 관리 자동화 | 일반적인 Build, Test, Deploy |
| Script Approval | 일반적인 Sandbox 승인 불필요 | 허용되지 않은 메서드는 승인 필요 |
| 보안 영향 | Jenkins Controller 전체에 영향을 줄 수 있음 | 허용된 범위 안에서만 실행되어 상대적으로 안전 |
| 저장소 관리 | 관리자·플랫폼 팀으로 엄격히 제한 | 일반 개발팀의 Library에 적합 |
| 등록 위치 | Global Library에서 설정 가능 | Global 또는 Folder Library에서 사용 가능 |

### 어떤 설정을 선택해야 하는가

대부분의 Shared Library는 **Untrusted를 기본으로 사용**한다. `sh`, `git`, `junit`, `withCredentials` 같은 Pipeline Step으로 구현할 수 있는 Build/Test/Deploy Library라면 Untrusted로 충분하다.

Jenkins 내부 API가 반드시 필요하고 일반 Pipeline Step으로 대체할 수 없을 때만 Trusted를 고려한다. 이 경우 관리자나 플랫폼 팀만 저장소를 수정하도록 제한하고, Pull Request 검토와 보호 브랜치를 적용해야 한다.

```text
company-ci
└─ Untrusted: 일반 Build / Test / Deploy 로직

jenkins-admin-library
└─ Trusted: 꼭 필요한 Jenkins 관리 기능만 포함
```

> **Pipeline Step으로 구현할 수 있으면 Untrusted를 사용하고, Jenkins 자체를 직접 조작해야 할 때만 별도로 통제된 Trusted Library를 사용한다.**

---

## JenkinsPipelineUnit

### 필요성

Shared Library는 여러 프로젝트가 함께 쓰는 공통 코드이기 때문에, 일반 프로젝트의 Jenkinsfile 하나보다 **버그의 영향 범위(blast radius)가 훨씬 크다**.

```
              company-ci-library
                     │
       ┌─────────────┼─────────────┐
       ↓             ↓             ↓
   Service A     Service B     Service C
```

Library 코드 한 줄이 잘못되면 이걸 쓰는 모든 프로젝트의 CI가 동시에 깨질 수 있다. 그래서 배포 전에 검증하는 절차가 일반 Pipeline보다 더 필요하다.

실제 Jenkins에서 매번 확인하는 방식은 느리다:
```
Library 코드 수정 → git push → Jenkins가 변경 감지(폴링/웹훅) → 빌드 실행 → 콘솔 로그 확인
```
이 한 바퀴가 수십 초~몇 분씩 걸리고, 함수를 여러 개 고칠수록 반복 비용이 누적된다. JenkinsPipelineUnit은 이 과정을 아래처럼 줄인다:
```
Library 코드 수정 → (로컬) 단위 테스트 실행 — 수 초
```

정리하면 필요한 이유는 세 가지다:

1. **영향 범위가 넓은 코드일수록 배포 전 검증이 중요함** — 한 곳의 버그가 여러 프로젝트를 동시에 망가뜨릴 수 있음
2. **빠른 피드백 루프** — 실제 Jenkins 빌드 없이 로컬에서 수 초 안에 로직을 확인
3. **안전한 리팩토링** — Library가 커질수록 "이걸 고치면 다른 함수도 깨지는지"를 테스트로 즉시 확인 가능. Library 저장소 자체의 PR 파이프라인에 테스트를 걸어두면, 잘못된 코드가 merge되기 전에 자동으로 막을 수도 있음

### 어떻게 Jenkins 없이 가능한가

`sh`, `echo`, `git` 같은 step은 원래 Jenkins가 제공하는 기능이라 Jenkins 밖에서는 존재하지 않는다. JenkinsPipelineUnit은 이 step들을 **mock(가짜 구현)으로 대체**해서, Jenkins 없이도 `vars/`, `src/`의 Groovy 코드를 그냥 실행할 수 있게 해준다.

```groovy
helper.registerAllowedMethod('echo', [String.class]) { String msg -> echoedLines << msg }
```

일반 소프트웨어에서 "진짜 DB 없이 Mock DB로 로직을 테스트하는 것"과 같은 원리다.

| | 실제 환경 | 테스트 환경 |
|---|---|---|
| 일반 앱 | 진짜 DB 연결 | Mock DB |
| Jenkins Pipeline | 진짜 Jenkins Controller/Agent | JenkinsPipelineUnit이 흉내낸 가짜 step |

### Spring 테스트 코드와 같은 관계

`SayHelloTest`는 `vars/sayHello.groovy`를 **대체하지 않는다** — 둘 다 존재하고, `SayHelloTest`는 "`sayHello.groovy`가 배포 전에 정상 동작하는지 미리 검증하는 별도 코드"다. Spring의 `@Service` 클래스와 그걸 검증하는 테스트 클래스의 관계와 동일하다.

| | Spring | Jenkins |
|---|---|---|
| 실제로 배포되는 것 | `@Service` 클래스 | `vars/sayHello.groovy` (Shared Library) |
| 진짜 인프라 | 진짜 DB, 진짜 HTTP 서버 | 진짜 Jenkins Controller/Agent |
| 테스트할 때 | Mockito로 DB 없이 Service 로직만 검증 | `BasePipelineTest`로 Jenkins 없이 `vars/` 로직만 검증 |
| 관계 | 원본 코드를 대체하지 않고, 미리 검증하는 별도 코드 | 원본 코드를 대체하지 않고, 미리 검증하는 별도 코드 |

```
src/main/java/UserService.java       ← 실제 배포되는 코드 (= vars/sayHello.groovy)
src/test/java/UserServiceTest.java   ← 그걸 검증하는 테스트 (= SayHelloTest.groovy)
```

### Replay와의 관계

Jenkins 공식 Shared Library 문서의 **Pretesting library changes**는 Replay를 이용한 사전 검증으로, JenkinsPipelineUnit을 사용한 단위 테스트와는 다른 접근이다.

| 구분 | 목적 |
|---|---|
| Replay | 실제 Jenkins에서 Library 변경을 수동으로 시험 |
| JenkinsPipelineUnit | Pipeline Step을 mock하고 호출 결과를 로컬에서 단위 테스트 |

### 실습 참고 — 의존성 버전

`com.lesfurets:jenkins-pipeline-unit`은 Maven Central에 **1.1까지만** 존재한다 (이후 버전은 JCenter에만 배포되었는데 JCenter가 셔터다운되어 소실). 최신 버전이 필요하면 GitHub 저장소(`jenkinsci/JenkinsPipelineUnit`)의 태그를 **JitPack**으로 빌드해서 받아야 하고, 전이 의존성(`com.cloudbees:groovy-cps`)은 **Jenkins 전용 Maven 저장소**(`repo.jenkins-ci.org`)에만 있으므로 별도로 등록해야 한다.

---

## 핵심 정리

1. `vars/*.groovy`의 `call()`은 파일명을 Custom Step처럼 사용할 수 있게 한다.
2. `src/`에는 package 기반의 재사용 가능한 Groovy 클래스를 작성한다.
3. `src/` 클래스에서 Pipeline Step을 사용하려면 `this` 또는 `steps`를 전달해야 한다.
4. Pipeline 상태 저장과 복구를 고려해 관련 클래스는 `Serializable`을 구현한다.
5. `vars/`는 stateless한 인터페이스로 유지하고 구현 로직은 `src/`로 분리한다.
6. `resources/`의 파일은 `libraryResource`로 읽는다.
7. Shared Library로 공통 Pipeline을 구조화해 Jenkinsfile에는 프로젝트별 설정만 남긴다.

---

## 참고 자료

- [Jenkins 공식 문서 - Extending with Shared Libraries](https://www.jenkins.io/doc/book/pipeline/shared-libraries/): Shared Library의 구조, 등록, 사용법을 다루는 기본 문서
- [Pipeline: Groovy Libraries - Step Reference](https://www.jenkins.io/doc/pipeline/steps/pipeline-groovy-lib/): `@Library` 정적 선언 대신 실행 중 조건에 따라 Library나 버전을 불러오는 `library` Step 문서. 실행 시점의 파라미터에 따라 다른 Library를 사용해야 할 때 참고한다.
- [Jenkins Blog - Pipeline Templates with Shared Libraries](https://www.jenkins.io/blog/2017/10/02/pipeline-templates-with-shared-libraries/): `vars/`에 전체 Pipeline을 캡슐화하고 각 프로젝트의 Jenkinsfile에는 설정값만 남기는 고급 패턴
- [JenkinsPipelineUnit - GitHub README](https://github.com/jenkinsci/JenkinsPipelineUnit): `loadScript`, `registerAllowedMethod`, `addShMock`, `assertJobStatusSuccess` 등 테스트 API 레퍼런스
