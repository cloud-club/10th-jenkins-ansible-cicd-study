# Shared Libraries

## 1. 문서 범위

다음 내용을 다룬다.

- Shared Library가 필요한 이유와 역할
- Shared Library repository 구조: `vars/`, `src/`, `resources/`
- Global Library, Folder-level Library, Automatic Library 차이
- `@Library` annotation과 `library` step 사용법
- library version, Modern SCM, Legacy SCM, caching 개념
- `vars/` global variable과 custom step 작성 방법
- `src/` Groovy class 모듈화와 Pipeline step 접근 방식
- `resources/`와 `libraryResource`
- Declarative Pipeline에서 Shared Library를 사용할 때의 제약
- JenkinsPipelineUnit을 이용한 Shared Library 단위 테스트

## 2. Shared Library란?

Shared Library는 여러 Jenkins Pipeline에서 공통으로 쓰는 로직을 별도 SCM repository로 분리하고, Jenkinsfile에서 불러와 재사용하는 기능이다.

Pipeline을 여러 프로젝트에 적용하다 보면 다음 코드가 반복된다.

- checkout 규칙
- Gradle/Maven build 규칙
- Docker build/push 규칙
- Slack/메일 알림
- 배포 승인 절차
- 공통 quality gate
- branch/tag/PR 조건 처리

이런 로직을 Jenkinsfile마다 복사하면 수정 비용이 커지고, 프로젝트마다 구현이 조금씩 달라진다. Shared Library는 이런 반복을 줄이고, 조직 단위 CI/CD 표준을 코드로 관리하게 해준다.

| 구분 | Jenkinsfile 안에 직접 작성 | Shared Library로 분리 |
| --- | --- | --- |
| 재사용 | 어려움 | 쉬움 |
| 변경 전파 | 각 repository 수정 필요 | library 수정 후 version 정책에 따라 반영 |
| 테스트 | Jenkins에서 돌려봐야 알기 쉬움 | JenkinsPipelineUnit 등으로 단위 테스트 가능 |
| 책임 분리 | app build와 CI/CD 공통 로직이 섞임 | Jenkinsfile은 얇게, 공통 로직은 library로 분리 |
| 위험 | 복붙과 drift 발생 | 중앙화에 따른 영향 범위 관리 필요 |

핵심은 Jenkinsfile을 "프로젝트별 설정" 중심으로 얇게 만들고, 복잡한 공통 로직은 Shared Library에서 관리하는 것이다.

## 3. Repository 구조

Jenkins Shared Library repository는 공식적으로 다음 구조를 사용한다.

```text
(root)
├── src
│   └── org
│       └── example
│           └── PipelineUtils.groovy
├── vars
│   ├── buildApp.groovy
│   ├── buildApp.txt
│   └── notifySlack.groovy
└── resources
    └── org
        └── example
            └── request.json
```

각 디렉터리의 역할은 다음과 같다.

| 디렉터리 | 역할 |
| --- | --- |
| `vars/` | Jenkinsfile에서 직접 호출할 global variable 또는 custom step 정의 |
| `src/` | 일반 Groovy class를 Java package 구조처럼 작성 |
| `resources/` | JSON, YAML, template 같은 정적 resource 저장 |

공식 문서 기준으로 `src/`와 `vars/`의 Groovy 파일은 Scripted Pipeline과 같은 CPS transformation을 받는다. Pipeline이 중단/재개될 수 있기 때문에 class state를 저장한다면 `Serializable`도 고려해야 한다.

## 4. `vars/`, `src/`, `resources/` 역할 구분

### 4.1 `vars/`

`vars/` 아래의 `.groovy` 파일은 Jenkinsfile에서 전역 변수처럼 보인다. 파일 이름이 곧 Jenkinsfile에서 호출하는 이름이 된다.

예를 들어 `vars/sayHello.groovy`가 있으면 Jenkinsfile에서는 `sayHello`로 호출한다.

```groovy
// vars/sayHello.groovy
def call(String name = 'human') {
    echo "Hello, ${name}."
}
```

```groovy
// Jenkinsfile
@Library('my-shared-library') _

pipeline {
    agent any

    stages {
        stage('Example') {
            steps {
                sayHello 'Jenkins'
            }
        }
    }
}
```

`call` 메서드를 정의하면 Jenkinsfile에서 built-in step처럼 호출할 수 있다.

| 파일 | Jenkinsfile 사용 |
| --- | --- |
| `vars/sayHello.groovy` | `sayHello 'Jenkins'` |
| `vars/dockerBuild.groovy` | `dockerBuild image: 'app', tag: '1.0.0'` |
| `vars/notifySlack.groovy` | `notifySlack status: currentBuild.currentResult` |

`vars/`에는 `.txt` 도움말 파일도 둘 수 있다. 예를 들어 `vars/buildApp.groovy`와 짝이 되는 `vars/buildApp.txt`를 만들면 Global Variable Reference에 문서가 노출된다. 단, 해당 library를 사용하는 Pipeline이 한 번 성공적으로 실행된 뒤에 문서가 생성된다.

공식 문서는 `vars/` global variable에 상태를 저장하지 말라고 안내한다. Jenkins controller가 재시작되거나 Pipeline이 suspend/resume되는 과정에서 상태가 사라질 수 있기 때문이다. `vars/`는 함수 모음 또는 얇은 wrapper로 두고, 상태가 필요한 로직은 `src/` class의 local instance로 다루는 편이 안전하다.

### 4.2 `src/`

`src/`는 일반 Groovy class를 두는 곳이다. Java source directory처럼 package 구조를 사용한다.

```groovy
// src/org/example/PipelineUtils.groovy
package org.example

class PipelineUtils implements Serializable {
    def steps

    PipelineUtils(steps) {
        this.steps = steps
    }

    void runGradle(String task) {
        steps.sh "./gradlew ${task}"
    }
}
```

이 class는 Jenkinsfile 또는 `vars/` 파일에서 import해서 사용할 수 있다.

```groovy
// vars/gradleBuild.groovy
import org.example.PipelineUtils

def call(String task = 'build') {
    new PipelineUtils(this).runGradle(task)
}
```

`src/`는 다음 상황에 적합하다.

- 조건 분기와 계산 로직이 복잡하다.
- 단위 테스트 대상이 필요하다.
- 여러 `vars/` step에서 같은 class를 공유한다.
- 객체 지향적으로 상태나 helper를 묶고 싶다.

### 4.3 `resources/`

`resources/`는 Shared Library와 함께 배포되는 정적 파일을 저장한다. 외부 Shared Library에서 `libraryResource` step으로 읽을 수 있다.

```text
resources/org/example/payload.json
```

```groovy
def payload = libraryResource 'org/example/payload.json'
writeFile file: 'payload.json', text: payload
```

사용 예시는 다음과 같다.

- API request JSON template
- Kubernetes YAML template
- Dockerfile template
- shell script template
- static configuration sample

공식 문서는 충돌을 피하기 위해 Java package처럼 고유한 경로를 쓰는 것을 권장한다.

## 5. Library 정의 방식

Shared Library는 Jenkins에 이름, SCM retrieval method, default version 등을 설정해서 정의한다.

### 5.1 Global Shared Libraries

Global Library는 Jenkins 전체에서 사용할 수 있는 library다. 보통 `Manage Jenkins -> System -> Global Trusted Pipeline Libraries` 또는 Global Untrusted Library 영역에서 설정한다.

| 종류 | 설명 |
| --- | --- |
| Trusted Library | Groovy sandbox 밖에서 실행 가능. Jenkins 내부 API나 unsafe API 사용 가능 |
| Untrusted Library | 일반 Pipeline처럼 Groovy sandbox 안에서 실행 |

Trusted Library는 매우 강력하다. 공식 문서도 이 library repository에 commit할 수 있는 사람은 Jenkins에 사실상 무제한 접근할 수 있다고 경고한다. 따라서 trusted library는 관리자나 신뢰된 CI/CD 플랫폼 팀만 관리해야 한다.

### 5.2 Folder-level Shared Libraries

Folder-level Library는 특정 Jenkins Folder 아래의 Pipeline에서만 사용할 수 있다.

특징은 다음과 같다.

- 특정 팀/서비스 그룹에만 library scope를 제한할 수 있다.
- 하위 folder와 job에서 사용할 수 있다.
- 공식 문서 기준 folder-scoped library는 항상 untrusted로 동작한다.

팀별 공통 로직이 있지만 Jenkins 전체 global로 열기에는 부담스러운 경우에 적합하다.

### 5.3 Automatic Shared Libraries

일부 plugin은 Jenkins 관리자가 미리 등록하지 않아도 library를 동적으로 정의할 수 있게 해준다. 예를 들어 Pipeline: GitHub Groovy Libraries plugin은 `github.com/org/repo` 같은 이름으로 GitHub repository를 library처럼 불러오는 방식을 제공한다.

Global 또는 Folder-level Library를 먼저 이해하는 것이 중요하다.

## 6. Library 불러오기

### 6.1 `@Library` annotation

가장 일반적인 방식은 Jenkinsfile 상단에 `@Library` annotation을 붙이는 것이다.

```groovy
@Library('my-shared-library') _

pipeline {
    agent any

    stages {
        stage('Build') {
            steps {
                buildApp()
            }
        }
    }
}
```

version을 지정할 수도 있다.

```groovy
@Library('my-shared-library@1.0.0') _
```

여러 library를 한 번에 불러올 수도 있다.

```groovy
@Library(['ci-lib@main', 'deploy-lib@2.1.0']) _
```

`@Library('lib') _`에서 `_`는 annotation을 붙이기 위한 dummy target이다. `vars/`의 global variable만 쓰는 경우 이 형태가 간단하다.

`src/` class를 정적 타입으로 import하려면 import statement에 annotation을 붙일 수 있다.

```groovy
@Library('ci-lib')
import org.example.PipelineUtils
```

주의할 점은 global variable 자체를 import하는 것은 권장되지 않는다는 것이다. `vars/` global variable은 runtime에 해석되고, import하면 Groovy compiler가 static처럼 해석해 혼란스러운 오류가 날 수 있다.

### 6.2 `library` step

`library` step은 build 실행 중 동적으로 library를 load한다.

```groovy
library 'my-shared-library'
```

version을 동적으로 계산할 수 있다.

```groovy
library "my-shared-library@${env.BRANCH_NAME}"
```

`@Library`는 script가 compile되기 전에 classpath에 library를 올린다. 반면 `library` step은 script가 이미 compile된 뒤 실행된다. 그래서 `library` step으로 load한 library의 `src/` class는 정적 import나 타입 선언에 쓰기 어렵고, 동적 접근 방식이 필요하다.

```groovy
def lib = library('my-shared-library').org.example
lib.PipelineUtils.new(this).runGradle('build')
```

정리하면 다음과 같다.

| 방식 | 특징 | 추천 사용 |
| --- | --- | --- |
| `@Library` | compile 전에 load | 일반적인 Jenkinsfile |
| `library` step | runtime에 load | version을 동적으로 고를 때 |
| Load implicitly | Jenkinsfile 선언 없이 자동 load | 정말 공통이고 안정적인 library |

## 7. Library Version과 SCM 설정

Shared Library는 SCM branch, tag, commit hash 등을 version으로 사용할 수 있다.

```groovy
@Library('ci-lib@main') _
@Library('ci-lib@v1.2.0') _
@Library('ci-lib@abc1234') _
```

Jenkins 설정에는 default version을 둘 수 있다.

| 설정 | 의미 |
| --- | --- |
| Default version | version을 생략했을 때 사용할 branch/tag/ref |
| Allow default version to be overridden | Jenkinsfile에서 `@Library('lib@x')`로 override 허용 |
| Load implicitly | Jenkinsfile에서 선언하지 않아도 자동 load |

실무에서는 다음 기준으로 version 전략을 잡을 수 있다.

| 전략 | 장점 | 단점 |
| --- | --- | --- |
| `@main` | 항상 최신 공통 로직 사용 | library 변경이 여러 job에 즉시 영향 |
| tag version | 안정적이고 재현 가능 | library 수정 반영을 위해 각 Jenkinsfile 수정 필요 |
| commit hash | 완전한 재현성 | 관리가 번거로움 |
| branch별 matching | app branch와 library branch를 함께 테스트 가능 | library branch 관리가 필요 |

Multibranch Pipeline에서는 다음처럼 app branch와 같은 이름의 library branch를 불러오는 패턴도 가능하다.

```groovy
library "ci-lib@${env.BRANCH_NAME}"
```

단, 이 방식은 runtime load이므로 `src/` class를 정적 import해야 하는 구조에는 맞지 않을 수 있다.

### 7.1 Modern SCM과 Legacy SCM

공식 문서는 Modern SCM 사용을 권장한다. Modern SCM은 SCM plugin이 임의의 version을 checkout하는 API를 지원하는 방식이다. Git, Subversion plugin은 이 방식을 지원한다.

Legacy SCM은 SCM plugin이 Shared Library version API를 직접 지원하지 않을 때 사용하는 방식이다. 이 경우 SCM 설정에 `${library.libraryName.version}` 변수를 포함해 checkout할 version을 Jenkins가 치환하게 만든다.

```text
svn://svn.example.com/pipeline-library/branches/${library.my-lib.version}
```

일반적으로 Git 기반 Shared Library라면 Modern SCM을 우선 고려하면 된다.

### 7.2 Library Caching

Shared Groovy Libraries plugin은 library checkout을 빠르게 하기 위해 caching을 지원한다. include/exclude 규칙으로 특정 version만 cache하거나 특정 version을 cache에서 제외할 수 있다.

주의할 점은 exclude가 include보다 우선한다는 것이다.

## 8. Library 작성 패턴

### 8.1 간단한 custom step

가장 단순한 Shared Library는 `vars/`에 `call` 메서드를 정의하는 방식이다.

```groovy
// vars/notifyBuild.groovy
def call(Map config = [:]) {
    def status = config.status ?: currentBuild.currentResult
    echo "Build status: ${status}"
}
```

```groovy
// Jenkinsfile
notifyBuild status: 'SUCCESS'
```

이 방식은 짧고 직관적이다. 다만 로직이 커지면 테스트와 유지보수가 어려워진다.

### 8.2 `vars/` + `src/` 조합

JenkinsPipelineUnit README도 테스트하기 쉬운 구조로 `src/` class에 대부분의 로직을 두고, `vars/`는 얇은 wrapper로 두는 방식을 권장한다.

```groovy
// src/org/example/BuildService.groovy
package org.example

class BuildService implements Serializable {
    def script

    BuildService(script) {
        this.script = script
    }

    void gradle(String task) {
        script.sh "./gradlew ${task}"
    }
}
```

```groovy
// vars/buildApp.groovy
import org.example.BuildService

def call(Map config = [:]) {
    def task = config.task ?: 'build'
    new BuildService(this).gradle(task)
}
```

```groovy
// Jenkinsfile
@Library('ci-lib') _

pipeline {
    agent any
    stages {
        stage('Build') {
            steps {
                buildApp task: 'clean build'
            }
        }
    }
}
```

이 구조의 장점은 다음과 같다.

- `vars/`는 Jenkinsfile에서 보기 좋은 API만 제공한다.
- 복잡한 로직은 `src/` class에서 테스트할 수 있다.
- Pipeline step 접근은 `script.sh`, `script.echo`처럼 명시된다.
- 여러 global step이 같은 class를 재사용할 수 있다.

### 8.3 Pipeline step 접근

`src/` class는 `sh`, `git`, `echo` 같은 Pipeline step을 직접 호출할 수 없다. 보통 Jenkinsfile 또는 `vars/` script context인 `this`를 class에 주입한다.

```groovy
class DockerService implements Serializable {
    def script

    DockerService(script) {
        this.script = script
    }

    void build(String image, String tag) {
        script.sh "docker build -t ${image}:${tag} ."
    }
}
```

`env`, `params`, `currentBuild` 같은 전역 변수도 class 안에서 바로 쓰기보다 `script.env`, `script.params`, `script.currentBuild`처럼 접근하거나 필요한 값만 명시적으로 전달하는 편이 테스트하기 쉽다.

### 8.4 Closure를 받는 custom step

`call` 메서드는 `Closure`를 받을 수 있다. built-in step처럼 block을 감싸는 DSL을 만들 수 있다.

```groovy
// vars/linuxNode.groovy
def call(Closure body) {
    node('linux') {
        body()
    }
}
```

```groovy
linuxNode {
    sh './gradlew test'
}
```

다만 지나치게 복잡한 DSL은 읽기 어려워질 수 있다. 공식 문서도 builder pattern을 사용한 복잡한 DSL은 오류가 생기기 쉬워 권장하지 않는다고 설명한다.

## 9. Declarative Pipeline에서의 제약

Declarative Pipeline에서는 `vars/` global variable을 step처럼 호출하는 것은 자연스럽지만, 객체 method 호출은 `script` 블록이 필요할 수 있다.

예를 들어 `vars/log.groovy`가 다음처럼 여러 method를 제공한다고 하자.

```groovy
// vars/log.groovy
def info(String message) {
    echo "INFO: ${message}"
}

def warning(String message) {
    echo "WARNING: ${message}"
}
```

Declarative Pipeline에서는 다음처럼 `script` 블록 안에서 호출하는 것이 안전하다.

```groovy
@Library('ci-lib') _

pipeline {
    agent any

    stages {
        stage('Example') {
            steps {
                script {
                    log.info 'Start'
                    log.warning 'Something to check'
                }
            }
        }
    }
}
```

반면 `vars/sayHello.groovy`처럼 `call` 메서드로 custom step을 만든 경우에는 `steps` 안에서 step처럼 호출할 수 있다.

```groovy
steps {
    sayHello 'Jenkins'
}
```

## 10. Shared Library에서 Declarative Pipeline 정의

공식 문서에 따르면 Declarative 1.2 이후에는 Shared Library 안에서도 Declarative Pipeline 전체를 정의할 수 있다.

예시는 다음과 같다.

```groovy
// vars/standardPipeline.groovy
def call(Map config = [:]) {
    pipeline {
        agent any

        stages {
            stage('Build') {
                steps {
                    sh config.buildCommand ?: './gradlew build'
                }
            }
        }
    }
}
```

```groovy
// Jenkinsfile
@Library('ci-lib') _

standardPipeline buildCommand: './gradlew clean build'
```

중요한 제약은 다음과 같다.

- Shared Library에서 Declarative Pipeline 전체를 정의하는 것은 `vars/*.groovy`의 `call` 메서드에서만 가능하다.
- 한 build에서 실행 가능한 Declarative `pipeline {}`은 하나뿐이다.
- 두 번째 `pipeline {}`을 실행하려고 하면 build가 실패한다.

이 방식은 Jenkinsfile을 극단적으로 얇게 만들 수 있지만, 각 repository에서 Pipeline 흐름이 보이지 않게 되는 단점도 있다. 조직 표준 Pipeline에는 유용하지만, 프로젝트별 변형이 많다면 config 기반 wrapper가 너무 복잡해질 수 있다.

## 11. 보안과 운영 주의사항

### 11.1 Trusted Library 주의

Trusted Library는 Groovy sandbox 밖에서 실행될 수 있다. Jenkins 내부 API, plugin API, Java/Groovy API를 사용할 수 있으므로 강력하지만 위험하다.

공식 문서의 핵심 경고는 다음과 같이 이해하면 된다.

- trusted library repository에 push할 수 있는 사람은 Jenkins에서 매우 큰 권한을 얻을 수 있다.
- trusted library는 관리자 또는 신뢰된 플랫폼 팀만 관리해야 한다.
- unsafe API는 trusted library 내부에서 안전한 wrapper로 감싸고, Jenkinsfile 사용자에게는 안전한 API만 제공하는 것이 좋다.

### 11.2 Library 변경 영향 범위

Shared Library는 중앙화된 공통 로직이다. 한 번 수정하면 많은 job에 영향을 줄 수 있다.

운영 시에는 다음 전략이 필요하다.

| 항목 | 권장 |
| --- | --- |
| breaking change | major version 또는 별도 branch/tag로 분리 |
| 공통 library main branch | 충분한 테스트 후 merge |
| 중요한 서비스 | tag version pinning 고려 |
| 새 기능 검증 | library branch와 Jenkinsfile branch를 함께 테스트 |
| rollback | 이전 tag 또는 commit hash로 되돌릴 수 있게 관리 |

### 11.3 Third-party library 사용

공식 문서는 trusted library에서 `@Grab`으로 third-party Java library를 가져오는 것이 가능하지만 권장하지 않는다. dependency resolution, controller cache, 보안/재현성 문제가 생길 수 있기 때문이다.

추천 방향은 다음과 같다.

- 복잡한 third-party dependency가 필요한 로직은 별도 실행 파일이나 CLI로 만든다.
- Jenkins agent에 설치하거나 container image에 포함한다.
- Pipeline에서는 `sh` 또는 `bat`으로 해당 도구를 호출한다.

### 11.4 Library 변경 사전 검증

공식 문서는 untrusted library에서 문제가 보이면 Jenkins build의 `Replay` 기능으로 library source를 임시 수정해 동작을 확인할 수 있다고 설명한다. 확인이 끝나면 Replay diff를 library repository에 반영하는 식이다.

제약도 있다.

- trusted library는 Replay 수정이 지원되지 않는다.
- resource 파일 수정은 Replay에서 지원되지 않는다.
- Replay는 원래 build에서 사용한 library revision을 기준으로 한다.

GitHub에 있는 library PR을 실제 consumer Pipeline에서 검증할 때는 provider의 PR ref naming을 이용할 수 있다.

```groovy
@Library('pipeline-library@pull/123/head') _
```

provider마다 PR/MR ref 이름은 다를 수 있으므로 GitHub 외에는 해당 SCM의 branch/ref 규칙을 확인해야 한다.

## 12. JenkinsPipelineUnit

JenkinsPipelineUnit은 Jenkins Pipeline과 Shared Library를 Jenkins 없이 단위 테스트할 수 있게 해주는 Groovy 기반 테스트 프레임워크다.

README 기준으로 이 프레임워크는 다음을 제공한다.

- Pipeline script mock execution
- built-in Jenkins step mock 등록
- call stack 출력
- job status 검증
- exception 검증
- Shared Library 등록과 load
- `libraryResource` 테스트
- regression test를 위한 call stack 비교
- Declarative Pipeline 테스트 지원

주의할 점은 현재 README 기준으로 Java 21이 필요하고, Groovy 4와는 호환성 이슈가 안내되어 있다는 것이다. 실제 프로젝트에 도입할 때는 README의 최신 요구사항을 확인해야 한다.

## 13. 기본 테스트 구조

### 13.1 `BasePipelineTest`

Scripted Pipeline이나 일반 Shared Library 테스트는 보통 `BasePipelineTest`를 상속한다.

```groovy
import com.lesfurets.jenkins.unit.BasePipelineTest
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test

class BuildAppTest extends BasePipelineTest {
    @Override
    @BeforeEach
    void setUp() {
        super.setUp()

        helper.registerAllowedMethod('sh', [String]) { String command ->
            println "mock sh: ${command}"
        }
    }

    @Test
    void buildAppRunsGradleBuild() {
        def script = loadScript('vars/buildApp.groovy')
        script.call(task: 'build')

        printCallStack()
        assertJobStatusSuccess()
    }
}
```

실제 테스트에서는 `runScript`보다 library를 등록한 뒤 Jenkinsfile이나 `vars/` wrapper를 호출하는 식으로 구성하는 경우가 많다.

### 13.2 Declarative Pipeline 테스트

Declarative Pipeline을 테스트할 때는 `DeclarativePipelineTest`를 상속한다.

```groovy
import com.lesfurets.jenkins.unit.declarative.DeclarativePipelineTest
import org.junit.jupiter.api.Test

class JenkinsfileTest extends DeclarativePipelineTest {
    @Test
    void shouldRunWithoutErrors() {
        runScript('Jenkinsfile')

        assertJobStatusSuccess()
        printCallStack()
    }
}
```

`DeclarativePipelineTest`는 `BasePipelineTest`를 확장하므로 call stack 확인, method mock, job status 검증 같은 방식은 비슷하게 사용할 수 있다.

### 13.3 Pipeline step mock

JenkinsPipelineUnit은 Jenkins step을 실제로 실행하지 않는다. 테스트에서 필요한 step은 mock으로 등록한다.

```groovy
helper.registerAllowedMethod('sh', [String]) { String command ->
    if (command.contains('fail')) {
        binding.getVariable('currentBuild').result = 'FAILURE'
    }
}
```

build 결과는 다음처럼 검증할 수 있다.

```groovy
assertJobStatusSuccess()
assertJobStatusFailure()
```

특정 예외가 발생하는지도 JUnit의 `assertThrows` 등으로 검증할 수 있다.

## 14. Shared Library 테스트

### 14.1 Library 등록

JenkinsPipelineUnit은 Jenkins에 등록된 Shared Library처럼 테스트 helper에 library 설정을 등록할 수 있다.

```groovy
import static com.lesfurets.jenkins.unit.global.lib.LibraryConfiguration.library
import static com.lesfurets.jenkins.unit.global.lib.ProjectSource.projectSource

class SharedLibraryTest extends BasePipelineTest {
    @Override
    @BeforeEach
    void setUp() {
        super.setUp()

        def lib = library()
            .name('ci-lib')
            .defaultVersion('<notNeeded>')
            .allowOverride(true)
            .implicit(true)
            .targetPath('<notNeeded>')
            .retriever(projectSource())
            .build()

        helper.registerSharedLibrary(lib)
    }
}
```

`projectSource()`는 library 자체를 테스트할 때 유용하다. 현재 project root에서 `src/`, `vars/`, `resources/`를 찾아 load한다.

### 14.2 Source Retriever 종류

JenkinsPipelineUnit README는 여러 SourceRetriever를 설명한다.

| retriever | 용도 |
| --- | --- |
| `projectSource()` | Shared Library repository 자체를 테스트 |
| `localSource(path)` | local path에 복사된 library를 사용 |
| `gitSource(url)` | Git repository에서 library source를 가져옴 |

Library 자체를 테스트할 때는 `projectSource()`가 가장 단순하다. 다른 project의 Jenkinsfile이 외부 library와 잘 통합되는지 확인하려면 `localSource`나 `gitSource`를 고려할 수 있다.

### 14.3 테스트하기 쉬운 구조

JenkinsPipelineUnit README가 권장하는 방향은 다음과 같다.

- Jenkinsfile에 복잡한 로직을 많이 넣지 않는다.
- 가능하면 복잡한 build logic은 외부 script로 분리한다.
- Pipeline library에서는 대부분의 로직을 `src/` class에 둔다.
- `vars/` singleton은 `src/` class를 생성하고 호출하는 얇은 wrapper로 둔다.

예시는 다음과 같다.

```groovy
// src/com/example/HardMath.groovy
package com.example

class HardMath implements Serializable {
    Object script

    int add(int a, int b) {
        script.echo "Adding ${a} and ${b}"
        return a + b
    }
}
```

```groovy
// vars/hardmath.groovy
import com.example.HardMath

int add(int a, int b) {
    return new HardMath(script: this).add(a, b)
}
```

```groovy
// test/com/example/HardMathTest.groovy
package com.example

import com.lesfurets.jenkins.unit.BasePipelineTest
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test

import static org.junit.jupiter.api.Assertions.assertEquals

class HardMathTest extends BasePipelineTest {
    Object script

    @Override
    @BeforeEach
    void setUp() {
        super.setUp()
        script = loadScript('test/resources/EmptyPipeline.groovy')
    }

    @Test
    void addReturnsSum() {
        assertEquals(4, new HardMath(script: script).add(1, 3))
    }
}
```

```groovy
// test/resources/EmptyPipeline.groovy
return this
```

이 구조는 `src/` class를 일반 단위 테스트처럼 검증할 수 있게 만든다. Jenkins step이 필요한 경우에도 `script.echo`, `script.sh`를 mock하거나 call stack으로 검증하면 된다.

## 15. 추천 프로젝트 구조

기본 구조 예시는 다음과 같다.

```text
jenkins-shared-library/
├── src
│   └── com
│       └── company
│           └── cicd
│               ├── BuildService.groovy
│               ├── DockerService.groovy
│               └── NotifyService.groovy
├── vars
│   ├── buildApp.groovy
│   ├── buildApp.txt
│   ├── dockerPublish.groovy
│   └── notifyBuild.groovy
├── resources
│   └── com
│       └── company
│           └── cicd
│               └── slack-payload.json
├── test
│   ├── groovy
│   │   └── com
│   │       └── company
│   │           └── cicd
│   │               └── BuildServiceTest.groovy
│   └── resources
│       └── EmptyPipeline.groovy
└── build.gradle
```

역할 기준은 다음과 같다.

| 위치 | 책임 |
| --- | --- |
| Jenkinsfile | 프로젝트별 stage 흐름과 최소 설정 |
| `vars/*.groovy` | 사용자에게 노출되는 Pipeline API |
| `src/**/*.groovy` | 테스트 가능한 실제 로직 |
| `resources/**` | library와 함께 배포되는 template/static file |
| `test/**` | JenkinsPipelineUnit 기반 단위 테스트 |

## 16. 실전 예시

### 16.1 Shared Library

```groovy
// vars/standardGradlePipeline.groovy
def call(Map config = [:]) {
    pipeline {
        agent any

        options {
            timestamps()
            disableConcurrentBuilds()
        }

        stages {
            stage('Build') {
                steps {
                    sh "./gradlew ${config.buildTask ?: 'clean build'}"
                }
            }

            stage('Test') {
                steps {
                    sh "./gradlew ${config.testTask ?: 'test'}"
                }
                post {
                    always {
                        junit config.testReport ?: 'build/test-results/**/*.xml'
                    }
                }
            }
        }
    }
}
```

```groovy
// Jenkinsfile
@Library('ci-lib@v1') _

standardGradlePipeline(
    buildTask: 'clean assemble',
    testTask: 'test'
)
```

이 방식은 Jenkinsfile을 매우 간단하게 만들 수 있다. 다만 각 repository가 어떤 stage를 실행하는지 Jenkinsfile만 보고 알기 어렵다는 단점도 있다.

### 16.2 얇은 Jenkinsfile + 공통 step

```groovy
// Jenkinsfile
@Library('ci-lib@v1') _

pipeline {
    agent any

    stages {
        stage('Build') {
            steps {
                buildApp task: 'clean build'
            }
        }

        stage('Docker Publish') {
            when {
                branch 'main'
            }
            steps {
                dockerPublish image: 'my-service'
            }
        }
    }
}
```

이 방식은 Jenkinsfile에서 흐름이 보이고, 반복 로직만 library로 빠져 구조를 파악하기 쉽다.

## 17. Troubleshooting 체크리스트

### 17.1 library를 찾지 못할 때

- Jenkins에 등록한 library 이름과 `@Library('name')`이 일치하는지 확인한다.
- default version이 없는데 version을 생략하지 않았는지 확인한다.
- SCM credentials가 library repository에 접근 가능한지 확인한다.
- Modern SCM 설정에서 repository URL과 branch/tag가 맞는지 확인한다.
- folder-level library라면 Pipeline이 해당 folder scope 안에 있는지 확인한다.

### 17.2 `vars/` step 호출이 실패할 때

- 파일명이 Jenkinsfile에서 호출한 이름과 같은지 확인한다.
- `vars/foo.groovy` 안에 `def call(...)`이 있는지 확인한다.
- 파일명이 Groovy identifier 규칙에 맞는지 확인한다.
- Declarative에서 `log.info`처럼 객체 method 호출을 했다면 `script { ... }` 안으로 옮긴다.

### 17.3 `src/` class에서 `sh`를 못 찾을 때

- `src/` class는 Pipeline step을 직접 호출할 수 없다고 생각한다.
- `new MyClass(this)`처럼 script context를 주입한다.
- class 안에서는 `steps.sh`, `script.sh`처럼 접근한다.
- class가 state를 가진다면 `implements Serializable`을 고려한다.

### 17.4 `libraryResource`가 실패할 때

- resource path가 `resources/` 기준 상대 경로인지 확인한다.
- package 구조처럼 고유 경로를 사용했는지 확인한다.
- internal library에서는 `resources/` 지원이 제한될 수 있음을 확인한다.
- binary나 큰 파일을 resource로 넣는 것은 피한다.

### 17.5 JenkinsPipelineUnit 테스트가 실패할 때

- 필요한 Jenkins step을 `helper.registerAllowedMethod`로 mock했는지 확인한다.
- Shared Library를 `helper.registerSharedLibrary`로 등록했는지 확인한다.
- library 자체 테스트라면 `projectSource()`를 사용했는지 확인한다.
- Declarative Pipeline이라면 `DeclarativePipelineTest`를 상속했는지 확인한다.
- call stack을 출력해 실제 호출 흐름이 기대와 같은지 확인한다.

## 18. 핵심 요약

- Shared Library는 여러 Jenkinsfile의 공통 로직을 별도 repository로 분리하는 기능이다.
- repository 구조는 `vars/`, `src/`, `resources/`가 핵심이다.
- `vars/`는 Jenkinsfile에서 호출할 API, `src/`는 테스트 가능한 Groovy class, `resources/`는 정적 파일을 담당한다.
- `@Library('lib') _`는 compile 전에 library를 load하는 일반적인 방식이다.
- `library` step은 runtime에 library를 load하므로 동적 version 선택에는 좋지만 static import에는 맞지 않는다.
- Trusted Library는 매우 강력하므로 repository write 권한을 엄격하게 관리해야 한다.
- `src/` class에서 Pipeline step을 쓰려면 `this` 또는 script context를 주입해야 한다.
- Declarative Pipeline에서 global variable의 method 호출은 `script` 블록이 필요할 수 있다.
- JenkinsPipelineUnit을 사용하면 Shared Library와 Jenkinsfile을 Jenkins 없이 단위 테스트할 수 있다.
- 테스트하기 쉬운 library는 `vars/`가 얇고, 실제 로직이 `src/` class에 들어간 구조다.

## 참고 자료

- Jenkins 공식 문서 - Extending with Shared Libraries: https://www.jenkins.io/doc/book/pipeline/shared-libraries/
- JenkinsPipelineUnit GitHub Repository: https://github.com/jenkinsci/JenkinsPipelineUnit
