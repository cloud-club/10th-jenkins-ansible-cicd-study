# Pipeline Best Practices & Operations

## 1. 문서 범위

다음 내용을 다룬다.

- Pipeline Groovy를 glue code로만 사용하는 이유
- controller에서 무거운 연산, 파싱, 네트워크 호출을 피해야 하는 이유
- `sh`/`bat` step과 외부 script로 작업을 위임하는 패턴
- step 수, log 양, build 기록, shared library 크기 관리
- concurrency와 workspace 충돌 방지
- `NotSerializableException`과 Groovy CPS 개념
- `@NonCPS` 사용 기준과 주의사항
- Pipeline durability 설정과 speed/durability trade-off
- controller OOM, disk I/O, CPU 부하를 줄이는 운영 체크리스트

## 2. 한 장 요약

Jenkins Pipeline 운영의 핵심은 controller와 agent의 역할을 분리하는 것이다.

| 구분 | 해야 할 일 |
| --- | --- |
| Jenkins controller | Pipeline 상태 관리, stage/step orchestration, build 기록 관리 |
| Jenkins agent | build, test, package, deploy, 파일 파싱, 외부 API 호출, 무거운 계산 |

Pipeline Groovy는 controller에서 실행된다. 따라서 Jenkinsfile 안에서 복잡한 Groovy 로직을 많이 돌리면 controller CPU, memory, disk I/O를 직접 사용하게 된다.

좋은 Pipeline은 다음 성격을 가진다.

- Jenkinsfile은 흐름을 연결하는 glue code에 가깝다.
- 무거운 작업은 `sh`, `bat`, 외부 script, build tool, agent container로 위임한다.
- step 수를 불필요하게 늘리지 않는다.
- 큰 JSON/XML/log를 controller 메모리에 올리지 않는다.
- build 기록, artifact, stash, workspace를 관리한다.
- Pipeline durability는 업무 중요도에 맞게 선택한다.
- 복잡한 Groovy 로직은 Shared Library 또는 외부 script로 분리하고 테스트한다.

## 3. 왜 Pipeline Best Practices가 중요한가?

Pipeline은 단순히 Jenkinsfile 한 개가 실행되는 것처럼 보이지만, 내부적으로는 controller가 Pipeline 상태를 저장하고, step 실행을 관리하고, restart 후 재개할 수 있도록 중간 상태를 disk에 기록한다.

Pipeline이 복잡해질수록 다음 자원을 더 많이 쓴다.

- controller CPU
- controller heap memory
- controller disk I/O
- build directory 저장 공간
- Pipeline state serialization 비용
- agent와 controller 사이 통신 비용

공식 문서의 핵심 메시지는 간단하다.

> Pipeline은 build 자체를 수행하는 도구라기보다 build 작업들을 연결하는 도구로 써야 한다.

즉 Jenkinsfile은 "무엇을 어떤 순서로 실행할지"를 표현하고, 실제 build/test/deploy 세부 작업은 agent 위의 script나 build tool이 수행하게 해야 한다.

## 4. Controller와 Agent 역할 분리

### 4.1 Controller에서 실행되는 것

다음은 controller에서 부담을 유발할 수 있다.

- Jenkinsfile의 Groovy 코드
- Shared Library의 Groovy 코드
- `JsonSlurper`, `XmlSlurper` 같은 Groovy 파싱
- `readFile`로 큰 파일을 읽고 변수에 저장
- 큰 `Map`, `List`, summary object 유지
- 복잡한 closure, collection transformation
- Pipeline step이 많아서 상태 저장이 자주 발생하는 경우

### 4.2 Agent에서 실행되어야 하는 것

다음 작업은 agent 쪽으로 넘기는 것이 좋다.

- source build
- test execution
- packaging
- Docker build/push
- 대용량 파일 읽기/가공
- JSON/XML/YAML 파싱
- HTTP API 호출
- report 생성
- 복잡한 계산
- 압축/해제
- log 가공

예를 들어 JSON을 controller에서 `JsonSlurper`로 파싱하는 대신 agent에서 `jq`로 필요한 값만 추출하고, 작은 결과만 Jenkinsfile 변수로 받는 식이다.

```groovy
def version = sh(
    script: "jq -r '.version' package.json",
    returnStdout: true
).trim()
```

이 방식은 파일 전체와 JSON object를 controller heap에 올리지 않고, agent에서 필요한 문자열만 반환한다.

## 5. Groovy는 Glue Code로 사용하기

### 5.1 권장 방향

Jenkinsfile의 Groovy는 다음 정도에 머무는 것이 좋다.

- stage 순서 정의
- parameter와 branch 조건 분기
- step 호출 연결
- 작은 문자열 조합
- build result에 따른 후처리
- Shared Library wrapper 호출

예시는 다음과 같다.

```groovy
pipeline {
    agent any

    stages {
        stage('Build and Test') {
            steps {
                sh './ci/build-and-test.sh'
            }
        }
    }
}
```

여러 명령을 Jenkinsfile에 잘게 나열하기보다 script 하나로 묶으면 Pipeline engine이 관리해야 하는 step 수가 줄어든다.

### 5.2 피해야 할 방향

Jenkinsfile이 다음처럼 변하면 위험 신호다.

- Groovy로 큰 파일을 읽고 파싱한다.
- Jenkinsfile 안에 긴 business logic이 들어간다.
- 수십, 수백 개 `sh` step이 반복된다.
- 대량 데이터를 `Map`이나 `List`에 쌓아두고 여러 stage에서 공유한다.
- 외부 API 호출 결과 전체를 변수에 저장한다.
- controller API를 직접 호출한다.

좋지 않은 예시는 다음과 같다.

```groovy
def json = readFile('large-report.json')
def report = new groovy.json.JsonSlurper().parseText(json)

for (item in report.items) {
    echo "${item.name}: ${item.status}"
}
```

더 나은 방향은 agent에서 필요한 결과만 만들게 하는 것이다.

```groovy
sh '''
  jq -r '.items[] | "\\(.name): \\(.status)"' large-report.json > report-summary.txt
'''

archiveArtifacts artifacts: 'report-summary.txt'
```

## 6. 무거운 파싱과 네트워크 호출 피하기

### 6.1 `JsonSlurper`, `XmlSlurper`, `readFile`

공식 Best Practices 문서는 `JsonSlurper`, `XmlSlurper`, `readFile` 조합을 주의하라고 설명한다. 큰 파일을 읽어서 controller 메모리에 올리고, 다시 JSON/XML object로 만들면 controller memory를 많이 쓴다.

| 안 좋은 패턴 | 문제 |
| --- | --- |
| `readFile('large.json')` | 파일 내용을 controller 변수로 가져옴 |
| `JsonSlurper().parseText(...)` | JSON object를 controller heap에 생성 |
| 큰 object를 여러 stage에서 유지 | CPS serialization 대상이 커짐 |

권장 패턴은 다음과 같다.

```groovy
def value = sh(
    script: "jq -r '.target.value' large.json",
    returnStdout: true
).trim()
```

큰 파일 자체가 필요하다면 변수에 보관하지 말고 artifact로 보관한다.

```groovy
sh './generate-large-report.sh'
archiveArtifacts artifacts: 'build/reports/**'
```

### 6.2 HTTP 요청

Pipeline에서 HTTP 요청을 직접 수행하고 응답 전체를 변수로 들고 있는 것도 controller 부담이 될 수 있다.

안 좋은 예시는 다음과 같다.

```groovy
def response = httpRequest 'https://api.example.com/large-response'
def data = new groovy.json.JsonSlurper().parseText(response.content)
```

더 나은 방향은 agent에서 `curl`과 `jq`로 필요한 결과만 추출하는 것이다.

```groovy
def status = sh(
    script: "curl -fsS https://api.example.com/status | jq -r '.status'",
    returnStdout: true
).trim()
```

HTTP request가 agent에서 실행되면 agent의 network/certificate 환경 기준으로 동작한다. controller에서 직접 외부 API를 호출하는 것보다 네트워크 경계와 책임이 명확해진다.

## 7. Step 수 줄이기

Pipeline step은 하나 실행될 때마다 Jenkins Pipeline engine이 상태를 관리하고 agent/controller 간 통신과 persistence를 처리한다. 따라서 매우 많은 step을 잘게 나누면 overhead가 커진다.

### 7.1 비효율적인 예시

```groovy
steps {
    sh 'echo start'
    sh './gradlew clean'
    sh './gradlew compileJava'
    sh './gradlew test'
    sh './gradlew jar'
    sh 'echo done'
}
```

### 7.2 개선 예시

```groovy
steps {
    sh '''
      set -e
      echo start
      ./gradlew clean compileJava test jar
      echo done
    '''
}
```

또는 repository 안에 script를 두는 방식이 더 좋다.

```groovy
steps {
    sh './ci/build.sh'
}
```

이 방식의 장점은 다음과 같다.

- Jenkinsfile이 짧아진다.
- Pipeline step 수가 줄어든다.
- build script를 로컬에서도 실행할 수 있다.
- shell script lint/test가 가능하다.
- Jenkinsfile 변경 없이 build command를 수정할 수 있다.

## 8. Shared Library Best Practices

Shared Library는 강력하지만 잘못 쓰면 Pipeline 전체 성능과 안정성에 영향을 준다.

### 8.1 built-in step을 override하지 않기

공식 문서는 `sh`, `timeout` 같은 built-in Pipeline step을 Shared Library에서 덮어쓰지 말라고 권장한다.

예를 들어 이런 방식은 피한다.

```groovy
// vars/sh.groovy
def call(String command) {
    echo "custom sh wrapper"
    steps.sh command
}
```

위험한 이유는 다음과 같다.

- Jenkins Pipeline API가 바뀌면 custom override가 깨질 수 있다.
- 모든 Jenkinsfile에서 흔히 쓰는 step이라 장애 영향 범위가 크다.
- troubleshooting할 때 실제 built-in step인지 custom wrapper인지 혼란스럽다.
- 잘못 구현하면 Jenkins 전체 build 성능에 큰 영향을 준다.

대신 명확한 이름의 wrapper를 만든다.

```groovy
// vars/runShell.groovy
def call(String command) {
    sh """#!/usr/bin/env bash
      set -euo pipefail
      ${command}
    """
}
```

### 8.2 큰 global variable 파일 피하기

`vars/` 아래의 큰 global variable 파일은 Pipeline마다 로드될 수 있고, 필요 없는 내용까지 memory에 올라갈 수 있다.

권장 방향은 다음과 같다.

| 안 좋은 구조 | 좋은 구조 |
| --- | --- |
| `vars/common.groovy` 하나에 모든 함수 | 기능별 `vars/buildApp.groovy`, `vars/dockerPublish.groovy` |
| 많은 상태를 global variable에 저장 | `src/` class의 local instance 사용 |
| 수백 줄 DSL 파일 | 얇은 wrapper + `src/` class |

### 8.3 너무 큰 Shared Library 피하기

Shared Library가 매우 크면 Pipeline 시작 전에 checkout/load 비용이 커진다. 동시에 많은 job이 같은 큰 library를 사용하면 controller memory와 disk I/O 부담도 커진다.

권장 기준은 다음과 같다.

- 공통성이 낮은 기능은 별도 library로 분리한다.
- 사용하지 않는 legacy 함수는 제거한다.
- 큰 template이나 binary를 library에 넣지 않는다.
- dependency가 많은 로직은 외부 CLI 또는 container image로 분리한다.
- library API는 안정적으로 유지하고 내부 구현만 바꾸는 방향으로 관리한다.

## 9. Jenkins API 직접 호출 피하기

Pipeline이나 Shared Library에서 `Jenkins.instance`, `Jenkins.getInstance()` 같은 Jenkins 내부 API를 직접 호출하는 것은 위험하다.

문제는 크게 두 가지다.

| 문제 | 설명 |
| --- | --- |
| 보안 | sandbox whitelist를 통해 개발자에게 과도한 권한이 열릴 수 있음 |
| 운영 안정성 | Jenkins 내부 API는 Pipeline step API처럼 안정적 사용을 전제로 하지 않음 |

안 좋은 예시는 다음과 같다.

```groovy
def jenkins = Jenkins.getInstance()
def job = jenkins.getItemByFullName('some-job')
```

정말 Jenkins 내부 정보가 필요하다면 다음을 검토한다.

- 공식 Pipeline step으로 해결 가능한지 확인한다.
- REST API 또는 CLI로 대체 가능한지 확인한다.
- 관리자용 별도 job으로 분리한다.
- 꼭 필요하면 최소 기능만 제공하는 Jenkins plugin을 Java로 만든다.

공식 문서의 권장 방향도 unsafe Jenkins API를 Pipeline에서 직접 쓰기보다 안전한 wrapper를 제공하는 plugin을 만드는 것이다.

## 10. Build 기록과 Artifact 정리

오래된 build, artifact, console log가 계속 쌓이면 controller disk를 압박한다. disk full은 Jenkins 운영 장애로 직결될 수 있다.

Pipeline에서는 `buildDiscarder`를 사용한다.

```groovy
pipeline {
    agent any

    options {
        buildDiscarder(logRotator(
            numToKeepStr: '30',
            artifactNumToKeepStr: '10'
        ))
    }

    stages {
        stage('Build') {
            steps {
                sh './gradlew build'
            }
        }
    }
}
```

정리 기준 예시는 다음과 같다.

| 대상 | 기준 예시 |
| --- | --- |
| PR build | 최근 10~20개 |
| main branch CI | 최근 30~50개 |
| release build | 기간 또는 tag 기준으로 장기 보관 |
| 대용량 artifact | artifact repository로 이동 |
| console log | 과도한 verbose log 줄이기 |

## 11. Concurrency와 Workspace

동시에 여러 Pipeline이 같은 workspace나 shared directory를 사용하면 예상치 못한 파일 변경, workspace rename, race condition이 생길 수 있다.

### 11.1 피해야 할 패턴

- 여러 job이 같은 absolute path에 checkout한다.
- 같은 workspace에서 동시에 build한다.
- shared volume에 직접 build output을 쓴다.
- 같은 Docker tag나 temp file 이름을 동시에 사용한다.

### 11.2 권장 패턴

| 상황 | 권장 |
| --- | --- |
| 같은 job 동시 실행 불필요 | `disableConcurrentBuilds()` |
| 특정 자원을 반드시 하나씩 써야 함 | Lockable Resources Plugin |
| build 환경 격리 필요 | container/cloud agent 사용 |
| shared volume 필요 | 별도 위치에서 copy in/out |
| 반복 가능한 build 필요 | 매 build마다 clean workspace/container 사용 |

예시는 다음과 같다.

```groovy
pipeline {
    agent any

    options {
        disableConcurrentBuilds()
    }

    stages {
        stage('Build') {
            steps {
                sh './gradlew build'
            }
        }
    }
}
```

단, concurrency를 끄거나 lock을 걸면 대기 시간이 길어질 수 있다. 가능한 경우에는 각 build가 독립된 workspace, container, cloud agent를 갖도록 만드는 것이 더 좋다.

## 12. CPS와 Pipeline 상태 저장

Jenkins Pipeline은 Groovy CPS 변환을 사용한다. CPS는 Continuation Passing Style의 약자이며, Pipeline 실행 중 현재 상태를 저장했다가 Jenkins restart 후 이어서 실행할 수 있게 해준다.

Pipeline이 restart 후 이어질 수 있는 이유는 Jenkins가 실행 상태를 build directory의 `program.dat` 같은 파일에 저장하기 때문이다.

이 구조 때문에 Pipeline Groovy는 일반 Groovy와 다르게 동작할 수 있다.

| 구분 | 설명 |
| --- | --- |
| CPS-transformed | 대부분의 Jenkinsfile 코드, Shared Library 코드, block을 받는 Pipeline step |
| Non-CPS | Java bytecode, Jenkins core/plugin code, Groovy runtime, constructor body, `@NonCPS` 메서드 |

중요한 규칙은 다음과 같다.

> Non-CPS 코드에서 CPS-transformed 코드를 호출하면 안 된다.

예를 들어 `@NonCPS` 메서드 안에서 `sh`, `node`, `sleep` 같은 Pipeline step을 호출하면 안 된다.

## 13. `NotSerializableException`

Pipeline은 중간 상태를 저장하기 위해 현재 local variable 등을 serialization한다. 이때 serializable하지 않은 object를 변수에 보관하고 있으면 `NotSerializableException`이 발생할 수 있다.

### 13.1 문제 예시

```groovy
def matcher = ('release-1.2.3' =~ /release-(\d+\.\d+\.\d+)/)

stage('Build') {
    steps {
        sh './gradlew build'
    }
}

echo matcher[0][1]
```

정규식 matcher 같은 object는 serializable하지 않을 수 있다. Pipeline이 `sh` step을 만나 상태를 저장하려 할 때 문제가 발생할 수 있다.

### 13.2 개선 방향

필요한 값만 문자열로 뽑아두고 non-serializable object는 오래 보관하지 않는다.

```groovy
def version = ('release-1.2.3' =~ /release-(\d+\.\d+\.\d+)/)[0][1].toString()

stage('Build') {
    steps {
        sh './gradlew build'
    }
}

echo version
```

더 안전한 기준은 다음과 같다.

- Pipeline step 사이에 큰 object를 들고 있지 않는다.
- `Map`, `List`도 너무 크게 만들지 않는다.
- matcher, stream, parser object를 stage 밖 변수로 오래 유지하지 않는다.
- 필요한 값은 primitive/string/simple serializable value로 변환한다.
- 복잡한 계산은 `@NonCPS` 메서드 또는 agent script에서 끝내고 작은 결과만 반환한다.

## 14. `@NonCPS`

`@NonCPS`는 특정 메서드에 CPS 변환을 적용하지 않도록 하는 annotation이다. 복잡한 Groovy collection 처리나 CPS가 잘 다루지 못하는 로직을 처리할 때 사용할 수 있다.

### 14.1 적합한 사용

```groovy
@NonCPS
String findLatestVersion(List<String> versions) {
    return versions.sort { a, b ->
        a <=> b
    }.last()
}
```

이런 함수는 다음 조건을 만족해야 한다.

- Pipeline step을 호출하지 않는다.
- controller에서 실행되므로 너무 무겁지 않다.
- parameter와 return value가 serializable하다.
- 내부에서만 non-serializable object를 쓰고 밖으로 내보내지 않는다.

### 14.2 잘못된 사용

```groovy
@NonCPS
def build() {
    node {
        sh './gradlew build'
    }
}
```

`node`, `sh`는 CPS-transformed Pipeline step이다. `@NonCPS` 메서드 안에서 호출하면 이상한 결과나 CPS method mismatch warning이 발생할 수 있다.

### 14.3 판단 기준

| 상황 | `@NonCPS` 사용 |
| --- | --- |
| 복잡한 list/map 변환 | 가능 |
| 정렬/필터링 함수가 CPS와 충돌 | 가능 |
| Pipeline step 호출 필요 | 사용하면 안 됨 |
| 외부 command 실행 | `sh`로 agent에 위임 |
| 큰 파일 파싱 | 가능하더라도 agent script가 더 좋음 |

`@NonCPS`는 성능 개선 도구이기도 하지만, controller에서 실행된다는 점은 변하지 않는다. CPU를 많이 쓰는 작업이라면 `@NonCPS`보다 agent script로 넘기는 것이 더 낫다.

## 15. CPS Method Mismatch

Pipeline CPS Method Mismatches 문서는 CPS 코드와 Non-CPS 코드가 잘못 섞일 때 생기는 문제를 설명한다.

대표적인 문제는 다음과 같다.

| 문제 | 설명 |
| --- | --- |
| `@NonCPS` 안에서 Pipeline step 호출 | `sh`, `node`, `sleep` 등을 호출하면 안 됨 |
| Non-CPS method에 CPS closure 전달 | `toSorted { ... }` 같은 일부 Groovy method에서 문제 가능 |
| constructor 안에서 Pipeline step 또는 CPS method 호출 | constructor body는 CPS 변환되지 않음 |
| non-CPS method override에서 CPS 코드 사용 | `toString` 같은 override에 주의 |
| GString 안에 closure 사용 | CPS closure가 예상과 다르게 동작 가능 |

### 15.1 Groovy sort 예시

일부 Groovy collection method는 closure와 CPS 변환이 섞여 이상한 결과를 낼 수 있다.

```groovy
def sorted = ['333', '1', '4444', '22'].toSorted { a, b ->
    a.length() <=> b.length()
}
```

문제가 발생한다면 정렬 로직을 `@NonCPS` 메서드 안으로 옮긴다.

```groovy
@NonCPS
List<String> sortByLength(List<String> values) {
    return values.toSorted { a, b ->
        a.length() <=> b.length()
    }
}

def sorted = sortByLength(['333', '1', '4444', '22'])
echo sorted.toString()
```

### 15.2 Constructor 주의

Pipeline step은 constructor 안에서 호출하지 않는다.

```groovy
class Builder {
    Builder(script) {
        script.sh './gradlew build' // 피해야 함
    }
}
```

대신 constructor는 값만 받고, Pipeline step은 일반 method에서 호출한다.

```groovy
class Builder implements Serializable {
    def script

    Builder(script) {
        this.script = script
    }

    void build() {
        script.sh './gradlew build'
    }
}
```

## 16. Pipeline Durability

Pipeline durability는 Pipeline 실행 상태를 얼마나 자주, 얼마나 안전하게 disk에 기록할지를 정하는 설정이다.

Jenkins Pipeline은 restart 후 resume을 위해 실행 상태를 자주 disk에 쓴다. 이 durability는 유용하지만, step이 많고 동시 실행이 많고 storage가 느리면 disk I/O 병목이 된다.

Scaling Pipelines 문서는 speed/durability 설정이 성능과 복구 가능성 사이의 trade-off라고 설명한다.

## 17. Durability 설정 방법

공식 문서 기준 durability는 세 수준에서 설정할 수 있다.

| 설정 위치 | 설명 |
| --- | --- |
| Global | `Manage Jenkins -> System -> Pipeline Speed/Durability Settings` |
| Pipeline job | job 설정의 `Custom Pipeline Speed/Durability Level` |
| Multibranch branch | Branch Property Strategy로 branch별 설정 |

`properties` step으로도 설정할 수 있지만, 이 경우 다음 build부터 적용된다는 점을 기억해야 한다.

Durability 설정은 즉시 현재 실행 중인 build를 바꾸지 않고, 다음 적용 가능한 Pipeline run부터 반영된다.

## 18. Durability Level 비교

| Level | 특징 | 추천 |
| --- | --- | --- |
| `MAX_SURVIVABILITY` | 가장 강한 durability. 가장 느림 | production deploy, audit가 중요한 job |
| `SURVIVABLE_NONATOMIC` | step마다 기록하지만 atomic write는 피함 | 어느 정도 기록이 필요하지만 성능도 필요한 job |
| `PERFORMANCE_OPTIMIZED` | disk I/O를 크게 줄임. durability 낮음 | 다시 실행 가능한 build/test Pipeline |

### 18.1 `PERFORMANCE_OPTIMIZED`

장점은 disk I/O를 크게 줄일 수 있다는 것이다. 많은 일반 CI job, feature branch build, PR validation처럼 실패하면 다시 실행하면 되는 job에 적합하다.

단점은 Jenkins가 dirty shutdown되면 실행 중이던 Pipeline이 resume되지 않거나 Stage View/Graph View 표시가 깨질 수 있다는 점이다.

### 18.2 `MAX_SURVIVABILITY`

가장 안전하지만 가장 느리다. 모든 step 실행 기록이 중요하거나 production deploy처럼 audit trail이 필요한 job에 적합하다.

### 18.3 `SURVIVABLE_NONATOMIC`

중간 선택지다. step마다 기록하지만 atomic write를 피해서 네트워크 파일 시스템 등에서 성능이 나을 수 있다. 다만 OS/storage 장애 시 buffered data가 유실될 작은 위험이 있다.

## 19. Durability가 도움이 되는 경우와 아닌 경우

### 19.1 도움이 되는 경우

Scaling Pipelines 문서 기준으로 고성능 durability 설정이 도움이 되는 상황은 다음과 같다.

- controller storage가 NFS 또는 magnetic disk다.
- 동시에 많은 Pipeline이 실행된다.
- controller의 iowait가 높다.
- Pipeline step 수가 수백 개 이상이다.
- Pipeline 변수가 큰 file data, 큰 map/list, summary object를 오래 들고 있다.
- build directory disk I/O가 병목이다.

### 19.2 도움이 적은 경우

다음 상황에서는 durability 설정만으로 큰 개선을 기대하기 어렵다.

- Pipeline 대부분이 몇 개의 긴 shell script를 기다리는 구조다.
- log를 엄청나게 많이 출력한다.
- Pipeline이 아니라 다른 Jenkins 구성 요소가 병목이다.
- controller heap 부족이 주된 문제인데 Pipeline 코드가 큰 object를 계속 들고 있다.
- agent의 CPU나 network가 병목이다.

Durability는 만능 성능 버튼이 아니다. 병목이 disk I/O인지, memory인지, agent인지 먼저 구분해야 한다.

## 20. Graceful Shutdown과 Dirty Shutdown

Durability trade-off를 이해하려면 shutdown 종류를 구분해야 한다.

| 구분 | 설명 |
| --- | --- |
| graceful shutdown | Jenkins가 정상 종료 절차를 거침. 예: service stop, SIGTERM/SIGINT |
| dirty shutdown | Jenkins가 정상 종료 절차 없이 종료됨. 예: SIGKILL, container 강제 종료, OS 장애, OOMKiller |

성능 최적화 durability는 Jenkins 자체 안정성을 낮추는 설정은 아니다. 다만 dirty shutdown 시 실행 중인 Pipeline의 resume 정보가 부족할 수 있다.

중요한 운영 포인트는 다음과 같다.

- Jenkins 종료는 가능한 graceful shutdown으로 한다.
- Kubernetes나 container 환경에서는 termination grace period를 충분히 준다.
- controller OOM으로 OOMKiller가 Jenkins process를 죽이는 상황을 막아야 한다.
- production deploy Pipeline은 높은 durability를 고려한다.

## 21. Controller OOM 방지

Controller OOM은 Pipeline 코드, 플러그인, build 기록, 로그, queue, executor 설정 등 여러 요인이 겹쳐 발생할 수 있다. 이 문서의 범위에서는 Pipeline 작성/운영 관점의 OOM 방지를 다룬다.

### 21.1 OOM을 유발하기 쉬운 Pipeline 패턴

| 패턴 | 문제 |
| --- | --- |
| 큰 파일을 `readFile`로 읽음 | controller heap에 파일 내용 저장 |
| JSON/XML 전체를 Groovy object로 파싱 | object graph가 커짐 |
| summary `Map`에 많은 branch 결과 누적 | serialization 대상 증가 |
| 대량 log를 console에 출력 | log 저장/전송/렌더링 비용 증가 |
| 너무 많은 parallel branch | Pipeline state와 executor 관리 비용 증가 |
| 큰 Shared Library | load/compile/cache 비용 증가 |
| stash에 큰 파일 사용 | controller를 경유하며 압축/저장 비용 발생 가능 |

### 21.2 개선 기준

- 큰 파일은 agent에서 처리하고 작은 결과만 반환한다.
- 대량 결과는 artifact로 저장한다.
- summary data는 파일로 쓰고 archive한다.
- console log는 필요한 수준으로 줄인다.
- parallel branch 수를 제한한다.
- stash는 작은 파일 묶음에만 사용한다.
- controller heap을 늘리기 전에 Pipeline 코드 구조를 점검한다.

## 22. Log와 Artifact 운영

console log는 편리하지만 대량 출력은 Jenkins 성능과 저장 공간에 부담이 된다.

### 22.1 피해야 할 패턴

```groovy
sh 'cat huge-test-report.json'
sh './gradlew test --debug'
```

### 22.2 권장 패턴

```groovy
sh './gradlew test --info > build/test.log 2>&1'
archiveArtifacts artifacts: 'build/test.log'
junit 'build/test-results/**/*.xml'
```

기준은 다음과 같다.

| 데이터 | 권장 처리 |
| --- | --- |
| 사람이 바로 봐야 하는 핵심 상태 | console log |
| 긴 build output | file 저장 후 artifact |
| test result | `junit` |
| coverage/report HTML | `publishHTML` 또는 artifact |
| 대용량 binary | artifact repository 또는 object storage |

## 23. Stash 사용 주의

`stash`/`unstash`는 stage 간 파일 전달에 유용하지만, 큰 artifact 전달에는 적합하지 않다. stash는 압축과 저장/전송 비용이 있고 controller나 artifact manager 설정에 따라 부담이 커질 수 있다.

권장 기준은 다음과 같다.

| 상황 | 권장 |
| --- | --- |
| 작은 metadata, config, build manifest | `stash` 가능 |
| 수십 MB 이상의 artifact | artifact repository 고려 |
| stage 간 jar 전달 | 작으면 stash, 크면 archive/artifact storage |
| build cache 공유 | 전용 cache volume/tool 사용 |

예시는 다음과 같다.

```groovy
stash name: 'manifest', includes: 'build/manifest.json'
```

대용량 산출물은 다음처럼 외부 저장소를 고려한다.

```groovy
sh './gradlew publish'
```

## 24. Parallel과 Matrix 운영 기준

Parallel과 Matrix는 전체 시간을 줄일 수 있지만 controller와 agent 자원을 동시에 많이 사용한다.

주의할 점은 다음과 같다.

- branch 수가 많을수록 Pipeline state가 커진다.
- 각 branch가 많은 step을 실행하면 overhead가 커진다.
- log가 동시에 많이 쏟아질 수 있다.
- agent capacity가 부족하면 queue만 길어진다.
- shared resource 접근 충돌이 생길 수 있다.

권장 기준은 다음과 같다.

| 상황 | 권장 |
| --- | --- |
| 빠른 독립 테스트 여러 개 | parallel 적합 |
| OS/JDK/browser 조합 검증 | matrix 적합 |
| 수십~수백 조합 | 조합 축소, exclude, split job 고려 |
| shared DB나 환경 사용 | lock 또는 환경 분리 |
| 실패 시 나머지 중단 | `failFast true` 또는 `parallelsAlwaysFailFast()` |

## 25. 운영 관점 체크리스트

### 25.1 Jenkinsfile 리뷰 체크리스트

- Jenkinsfile이 너무 긴 Groovy program처럼 변하지 않았는가?
- 큰 JSON/XML 파일을 Groovy로 파싱하지 않는가?
- 외부 API 응답 전체를 controller 변수로 들고 있지 않은가?
- `sh` step을 과도하게 잘게 나누지 않았는가?
- build/test/deploy 로직이 agent script나 build tool로 위임되어 있는가?
- `Jenkins.getInstance()` 같은 내부 API 호출이 없는가?
- `@NonCPS` 안에서 Pipeline step을 호출하지 않는가?
- non-serializable object를 stage 사이에 들고 있지 않은가?
- log 출력량이 과도하지 않은가?

### 25.2 Jenkins 운영 체크리스트

- build discard policy가 설정되어 있는가?
- controller disk 사용량을 모니터링하는가?
- controller heap과 GC 상태를 모니터링하는가?
- Pipeline durability 설정이 job 중요도에 맞는가?
- production deploy job은 높은 durability 또는 audit 정책을 갖는가?
- feature/PR build는 다시 실행 가능한 구조인가?
- controller storage가 느린 경우 SSD 또는 storage 개선을 검토했는가?
- Pipeline plugin과 Script Security plugin이 최신 안정 버전인가?
- 동시 실행 수와 agent capacity가 균형이 맞는가?

## 26. 안티패턴과 개선 요약

| 안티패턴 | 문제 | 개선 |
| --- | --- | --- |
| Jenkinsfile에 복잡한 Groovy 로직 | controller CPU/memory 사용 | Shared Library 또는 외부 script |
| 큰 JSON을 `readFile` + `JsonSlurper` | controller heap 증가 | agent에서 `jq`로 필요한 값만 추출 |
| 수십 개 연속 `sh` step | Pipeline overhead 증가 | 하나의 script로 묶기 |
| `Jenkins.getInstance()` 사용 | 보안/성능 위험 | 공식 step, REST, plugin wrapper |
| built-in step override | API 변경 시 위험 | 명확한 이름의 wrapper |
| 큰 global variable file | 불필요한 memory 사용 | 기능별 작은 `vars/` |
| shared workspace | race condition | 독립 workspace/container |
| 큰 log console 출력 | disk/log 렌더링 부담 | file artifact로 저장 |
| 큰 stash | 저장/전송 부담 | artifact repository |
| dirty shutdown 잦음 | Pipeline resume 위험 | graceful shutdown, OOM 방지 |

## 27. Troubleshooting 체크리스트

### 27.1 Controller memory가 부족할 때

- 최근 Jenkinsfile 변경에서 `readFile`, `JsonSlurper`, 큰 `Map/List` 사용이 늘었는지 확인한다.
- 동시 실행 Pipeline 수와 parallel branch 수를 확인한다.
- 큰 Shared Library가 여러 job에서 로드되는지 확인한다.
- console log 폭증 job을 찾는다.
- stash/archive 대상 크기를 확인한다.
- heap dump와 GC log를 확인한다.

### 27.2 Pipeline이 느려졌을 때

- step 수가 급격히 늘었는지 확인한다.
- controller disk I/O와 iowait를 확인한다.
- durability 설정이 job 성격에 비해 너무 보수적인지 확인한다.
- NFS나 느린 disk를 사용하는지 확인한다.
- agent queue가 길어져 실제로는 agent 부족인지 확인한다.
- Shared Library checkout/load 시간이 늘었는지 확인한다.

### 27.3 `NotSerializableException`이 날 때

- stage 사이에 보관하는 변수를 확인한다.
- matcher, stream, parser, large object를 변수에 저장했는지 확인한다.
- 필요한 값만 String/Map/List의 단순 구조로 변환한다.
- 복잡한 계산은 `@NonCPS`로 분리하되 Pipeline step은 호출하지 않는다.
- 성능 최적화 durability로 예외가 가려질 수 있으므로 근본 원인을 수정한다.

### 27.4 CPS method mismatch warning이 날 때

- `@NonCPS` 안에서 `sh`, `node`, `sleep` 같은 step을 호출했는지 확인한다.
- Groovy collection method에 closure를 넘기는 코드가 있는지 확인한다.
- constructor 안에서 Pipeline step이나 CPS method를 호출했는지 확인한다.
- `toString`, comparator 등 non-CPS context에서 호출되는 override method를 확인한다.
- 문제 로직을 `@NonCPS` 함수로 감싸거나 agent script로 옮긴다.

### 27.5 Durability 설정을 바꿨는데 효과가 없을 때

- 설정이 다음 build부터 적용된다는 점을 확인한다.
- job-level 또는 branch-level 설정이 global 설정을 override하는지 확인한다.
- 병목이 disk I/O가 아니라 agent capacity나 log 출력인지 확인한다.
- Pipeline plugin 버전이 요구사항을 만족하는지 확인한다.
- Jenkins log에 적용된 durability level이 표시되는지 확인한다.

## 28. 실전 권장 기본값

기본 정책 예시는 다음과 같다.

| Pipeline 종류 | 권장 방향 |
| --- | --- |
| PR validation | `PERFORMANCE_OPTIMIZED`, 다시 실행 가능하게 설계 |
| feature branch CI | `PERFORMANCE_OPTIMIZED` |
| main branch CI | 조직 정책에 따라 `PERFORMANCE_OPTIMIZED` 또는 `SURVIVABLE_NONATOMIC` |
| release build | artifact 보존 강화, durability 상향 검토 |
| production deploy | `MAX_SURVIVABILITY` 또는 `SURVIVABLE_NONATOMIC`, audit/log 보존 |
| infrastructure 변경 | 높은 durability, 수동 승인, lock 적용 |

Jenkinsfile 작성 기본값은 다음과 같다.

- Jenkinsfile은 orchestration에 집중한다.
- build/test/deploy는 script 또는 build tool로 위임한다.
- 큰 데이터는 controller variable에 넣지 않는다.
- stage는 의미 있게 나누되 step은 과도하게 쪼개지 않는다.
- build 기록과 artifact retention을 명시한다.
- concurrency와 workspace 사용 방식을 명시한다.

## 29. 핵심 요약

- Pipeline Groovy는 controller에서 실행되므로 무거운 연산에 적합하지 않다.
- Jenkinsfile은 build logic 자체가 아니라 build orchestration을 표현해야 한다.
- 큰 파일 파싱, HTTP 호출, 데이터 가공은 agent에서 `sh`/`bat` 또는 외부 script로 처리한다.
- step 수가 많을수록 Pipeline engine overhead와 disk persistence 비용이 커진다.
- Shared Library는 built-in step override, 거대한 `vars/`, 거대한 library를 피해야 한다.
- `Jenkins.getInstance()` 같은 내부 API 직접 호출은 보안과 운영 위험이 크다.
- Pipeline CPS는 restart/resume을 위해 상태를 저장하며, 이 때문에 serialization 문제가 생길 수 있다.
- `@NonCPS` 안에서는 Pipeline step을 호출하면 안 된다.
- Durability 설정은 속도와 복구 가능성의 trade-off다.
- 다시 실행 가능한 CI는 성능 최적화를, production/audit job은 높은 durability를 고려한다.
- controller OOM 방지는 Pipeline 코드 구조, log, stash, parallel, retention 정책까지 함께 봐야 한다.

## 참고 자료

- Jenkins 공식 문서 - Pipeline Best Practices: https://www.jenkins.io/doc/book/pipeline/pipeline-best-practices/
- Jenkins 공식 문서 - Scaling Pipelines: https://www.jenkins.io/doc/book/pipeline/scaling-pipeline/
- Jenkins 공식 문서 - Pipeline CPS Method Mismatches: https://www.jenkins.io/doc/book/pipeline/cps-method-mismatches/
