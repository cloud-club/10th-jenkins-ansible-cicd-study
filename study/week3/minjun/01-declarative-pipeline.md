# Declarative Pipeline 심화

## 문서 범위

Declarative Pipeline의 지시어 중 실행 흐름을 제어하는 것들을 중심으로 정리하고, 실제 빌드 로그로 동작을 확인한다.

- `options`, `parameters`, `environment`
- `parallel` 병렬 실행
- `when` 조건부 실행
- `catchError` 에러 처리와 빌드 결과 상태
- `post` 후처리 블록

## Pipeline-level 지시어

### `options`

Pipeline 또는 stage의 실행 방식을 설정한다.

| 옵션 | 설명 |
|---|---|
| `timestamps()` | 콘솔 로그 각 줄에 시각 표시 |
| `timeout(time:, unit:)` | 제한 시간 초과 시 중단 |
| `disableConcurrentBuilds()` | 같은 Job의 동시 실행 방지 |
| `buildDiscarder(logRotator(...))` | 오래된 빌드 기록 보관 정책 |
| `retry(n)` | 실패 시 재시도 |
| `parallelsAlwaysFailFast()` | 병렬 stage 중 하나 실패 시 나머지 중단 |

top-level `options`와 stage-level `options`는 적용 시점이 다르다. stage-level `timeout`은 agent 할당 전부터 시간을 재기 때문에, Docker/Kubernetes agent를 새로 띄우는 시간이 timeout에 포함될 수 있다.

### `parameters`

빌드 시작 시 입력받는 값을 정의한다. 실행 중에는 `params` 객체로 접근한다.

| 타입 | 용도 |
|---|---|
| `string` / `text` | 문자열 입력 |
| `booleanParam` | true/false |
| `choice` | 선택지 중 하나 |
| `password` | 비밀번호 입력 |

주의할 점은 **`parameters` 블록을 추가한 뒤 첫 빌드에는 파라미터 UI가 없다**는 것이다. Jenkins가 Jenkinsfile을 한 번 실행해야 파라미터 정의를 인식하므로, 첫 실행은 기본값으로 돌고 그 이후부터 "Build with Parameters" 메뉴가 나타난다.

### `environment`

환경 변수를 정의한다. Pipeline 범위와 stage 범위 모두 가능하다. Credential을 가져올 때는 `credentials()` 헬퍼를 쓴다.

```groovy
environment {
    APP_ENV = 'study'
    DOCKER_CREDS = credentials('docker-registry-login')
}
```

Username/Password 타입이면 `DOCKER_CREDS_USR`, `DOCKER_CREDS_PSW` 변수가 함께 생성된다.

---

## 실습 Pipeline

```groovy
pipeline {
    agent any
    options {
        timestamps()
        timeout(time: 10, unit: 'MINUTES')
    }
    parameters {
        choice(name: 'TARGET', choices: ['dev', 'prod'], description: '배포 대상')
        booleanParam(name: 'RUN_TESTS', defaultValue: true)
    }
    environment {
        APP_ENV = 'study'
    }
    stages {
        stage('Parallel Test') {
            parallel {
                stage('Unit') { steps { sh 'echo unit; sleep 2' } }
                stage('Lint') { steps { sh 'echo lint; sleep 3' } }
            }
        }
        stage('Conditional Deploy') {
            when { expression { params.TARGET == 'prod' } }
            steps { sh 'echo "prod 배포"' }
        }
        stage('Error Handling') {
            steps {
                catchError(buildResult: 'UNSTABLE', stageResult: 'UNSTABLE') {
                    sh 'exit 1'
                }
                sh 'echo "실패해도 여기까지 옵니다"'
            }
        }
    }
    post {
        always { echo "always: ${env.APP_ENV}" }
        unstable { echo 'unstable 블록 실행' }
        failure { echo 'failure 블록' }
    }
}
```

---

## 1. `parallel` — 병렬 실행

빌드 로그:

```
01:09:31  + echo lint
01:09:31  + echo unit
01:09:31  lint
01:09:31  unit
01:09:31  + sleep 3
01:09:31  + sleep 2
```

두 stage의 첫 명령이 **같은 초에 실행**됐다. 순차 실행이었다면 `sleep 2` + `sleep 3` = 5초가 걸렸겠지만, 전체 stage는 약 3초에 끝났다. 느린 쪽에 맞춰지는 것이다.

`failFast true`를 주면 병렬 stage 중 하나가 실패했을 때 나머지를 중단한다. 전체에 적용하려면 `options { parallelsAlwaysFailFast() }`를 쓴다.

`parallel` 또는 `matrix` 내부에서 다시 `parallel`/`matrix`를 중첩할 수는 없다.

## 2. `when` — 조건부 실행

동일한 Pipeline을 파라미터만 바꿔 두 번 실행했다.

**TARGET=dev**
```
[Pipeline] { (Conditional Deploy)
Stage "Conditional Deploy" skipped due to when conditional
```

**TARGET=prod**
```
[Pipeline] { (Conditional Deploy)
[Pipeline] sh
10:11:03  + echo prod 배포
10:11:03  prod 배포
```

같은 Jenkinsfile인데 파라미터 하나로 실행 경로가 갈렸다. 조건에 맞지 않은 stage는 **사라지는 것이 아니라 "건너뛴 것"으로 기록**된다. Jenkins UI의 stage view에서도 회색으로 표시되어 흐름 전체는 그대로 보인다.

자주 쓰는 조건은 `branch`, `expression`, `environment`, `changeRequest`, `allOf`/`anyOf`/`not` 조합이다.

무거운 agent를 쓰는 stage라면 `beforeAgent true`를 붙여 agent 할당 전에 조건을 평가하는 편이 자원을 아낀다.

## 3. `catchError` — 실패를 잡고 계속 진행

로그의 실행 순서가 동작을 그대로 보여준다.

```
01:09:35  + exit 1
01:09:35  ERROR: script returned exit code 1
01:09:35  Setting overall build result to UNSTABLE
[Pipeline] // catchError
[Pipeline] sh
01:09:35  + echo 실패해도 여기까지 옵니다
01:09:35  실패해도 여기까지 옵니다
```

`exit 1`로 명령이 실패했지만 Pipeline은 중단되지 않았다. 대신 **빌드 결과만 UNSTABLE로 낮춰졌고**, 다음 step이 정상 실행됐다.

실무에서는 테스트가 실패해도 리포트는 수집해야 하는 경우에 쓴다.

```groovy
catchError(buildResult: 'UNSTABLE', stageResult: 'UNSTABLE') {
    sh './gradlew test'
}
junit 'build/test-results/**/*.xml'
```

비슷한 step으로 `warnError`(실패를 UNSTABLE로 낮추고 진행), `unstable`(명시적으로 불안정 표시), `error`(의도적 실패)가 있다.

## 4. `post` — 후처리와 빌드 상태

```
[Pipeline] { (Declarative: Post Actions)
01:09:35  always: study
01:09:35  unstable 블록 실행
```

`always`와 `unstable`은 실행됐고 **`failure`는 실행되지 않았다.**

여기서 확인한 것은 **UNSTABLE과 FAILURE가 서로 다른 상태**라는 점이다. `catchError`에 `buildResult: 'FAILURE'`를 줬다면 반대 결과가 나왔을 것이다.

| 조건 | 실행 시점 |
|---|---|
| `always` | 결과와 무관하게 항상 |
| `success` | 성공 시 |
| `unstable` | UNSTABLE 상태일 때 |
| `failure` | FAILURE 상태일 때 |
| `unsuccessful` | 성공이 아닌 모든 상태 |
| `changed` | 이전 빌드와 결과가 달라졌을 때 |
| `fixed` | 실패/불안정에서 성공으로 회복됐을 때 |
| `cleanup` | 다른 post 조건 처리 후 마지막 |

Jenkins의 빌드 결과는 나빠지는 방향으로만 바뀐다. 한 번 UNSTABLE이 되면 이후 step이 성공해도 SUCCESS로 되돌아가지 않는다.

## 정리

| 지시어 | 역할 | 로그에서 확인한 것 |
|---|---|---|
| `parallel` | 동시 실행 | 두 stage가 같은 초에 시작 |
| `when` | 조건부 실행 | `skipped due to when conditional` |
| `catchError` | 실패 후 진행 | 결과만 UNSTABLE로 낮추고 다음 step 실행 |
| `post` | 후처리 | 상태에 따라 블록이 선택적으로 실행 |

## 참고 자료

- [Jenkins 공식 문서 - Pipeline Syntax](https://www.jenkins.io/doc/book/pipeline/syntax/)
- [Jenkins 공식 문서 - Pipeline: Basic Steps](https://www.jenkins.io/doc/pipeline/steps/workflow-basic-steps/)
