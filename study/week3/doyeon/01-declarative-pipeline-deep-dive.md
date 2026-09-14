# Week 3 실습 기록 — Declarative Pipeline Deep Dive

> **환경**: `jenkins-controller` + `jenkins-agent1`(Label: `linux`, Executor 1개)을 사용.
> Job `pipeline-syntax-lab`(Pipeline script 직접 입력) 하나를 계속 갈아 끼우면서 실습.

---

## 1. `environment`

```groovy
pipeline {
    agent { label 'linux' }
    environment {
        GREETING = "Hello Jenkins"
    }
    stages {
        stage('Print Env') {
            environment {
                STAGE_ONLY = "stage-level-var"
            }
            steps {
                sh 'echo $GREETING'
                sh 'echo $STAGE_ONLY'
            }
        }
    }
}
```

**결과**: `GREETING`, `STAGE_ONLY` 둘 다 정상 출력, `Finished: SUCCESS`.

**배운 점**:
- 콘솔 로그에 `[Pipeline] withEnv { ... }`가 **pipeline 레벨 / stage 레벨 두 겹으로 중첩**되어 찍힘 → `environment` 지시어는 내부적으로 `withEnv` step을 감싸는 문법 설탕이라는 게 로그로 직접 확인됨.
- stage 레벨 `environment`는 해당 stage 안에서만 유효한 스코프.

---

## 2. `parameters`

```groovy
pipeline {
    agent { label 'linux' }
    parameters {
        string(name: 'GREETING_NAME', defaultValue: 'World', description: '인사할 대상')
        booleanParam(name: 'FORCE_FAIL', defaultValue: false, description: '강제 실패 여부')
        choice(name: 'ENV_TARGET', choices: ['dev', 'staging', 'prod'], description: '배포 대상')
    }
    stages {
        stage('Greet') {
            steps {
                sh "echo Hello, ${params.GREETING_NAME}!"
                echo "ENV_TARGET=${params.ENV_TARGET}"
            }
        }
    }
}
```

**결과**: `Build with Parameters`로 `GREETING_NAME=도야무`, `ENV_TARGET=prod` 입력 → `Hello, 도야무!`, `ENV_TARGET=prod` 정상 출력.

**배운 점**:
- `parameters`가 처음 추가된 시점엔 **최초 1회를 기본값으로 먼저 실행해야** 그 다음부터 `Build with Parameters` 버튼이 생김.
- `params.XXX` 참조는 `environment`와 달리 별도 wrapper step(`withEnv` 같은) 없이 바로 값이 치환됨 — 로그 구조 자체가 `environment`보다 훨씬 단순함.

---

## 3. `when`

`ENV_TARGET` 파라미터를 재사용해서 조건부 stage 두 개 추가:

```groovy
stage('Deploy to Prod') {
    when { expression { params.ENV_TARGET == 'prod' } }
    steps { echo "prod 배포 실행!" }
}
stage('Deploy to Dev/Staging') {
    when { not { expression { params.ENV_TARGET == 'prod' } } }
    steps { echo "dev/staging 배포 실행" }
}
```

**결과**:
| ENV_TARGET | Deploy to Prod | Deploy to Dev/Staging |
|---|---|---|
| `prod` | 실행 (`prod 배포 실행!`) | `skipped due to when conditional` |
| `dev` | `skipped due to when conditional` | 실행 (`dev/staging 배포 실행`) |

**배운 점**:
- 조건이 안 맞는 stage는 실패가 아니라 **"skipped due to when conditional"** 메시지와 함께 건너뛰어짐. 실패(FAILURE)와 스킵(SKIPPED)은 로그 메시지부터 구분됨.
- 건너뛸 stage도 `[Pipeline] getContext`까지는 호출된 뒤 skip 처리됨 → `when` 조건은 stage 진입 직전에 평가된다는 뜻.

---

## 4. `post`

```groovy
pipeline {
    agent { label 'linux' }
    parameters {
        booleanParam(name: 'FORCE_FAIL', defaultValue: false, description: '강제 실패 여부')
    }
    stages {
        stage('Might Fail') {
            steps {
                script {
                    if (params.FORCE_FAIL) {
                        error("강제로 실패시킴")
                    }
                }
                echo "여기까지 왔으면 성공 처리"
            }
        }
    }
    post {
        always   { echo "★ always: 항상 실행" }
        success  { echo "★ success: 성공했을 때만" }
        failure  { echo "★ failure: 실패했을 때만" }
        unstable { echo "★ unstable: unstable일 때만" }
    }
}
```

**결과**:
| FORCE_FAIL | 찍힌 post 블록 | 최종 결과 |
|---|---|---|
| `false` | `always`, `success` | `SUCCESS` |
| `true` | `always`, `failure` | `FAILURE` |

**배운 점**:
- `post` 블록은 실제로는 `[Pipeline] stage { (Declarative: Post Actions) }`라는 **숨겨진 stage로 파이프라인 맨 끝에 자동으로 추가**되어 실행됨. `post`도 마법이 아니라 자동 생성되는 stage일 뿐.
- `always`는 성공/실패 여부와 무관하게 항상 찍히고, `success`/`failure`는 결과에 따라 배타적으로 갈림.

---

## 5. `options`

### 5-1. `timeout`

```groovy
pipeline {
    agent { label 'linux' }
    options {
        timeout(time: 10, unit: 'SECONDS')
        timestamps()
    }
    stages {
        stage('Sleep') {
            steps {
                echo "10초 넘게 걸리는 작업 시뮬레이션"
                sh 'sleep 30'
            }
        }
    }
}
```

**결과**: `23:31:28`에 시작 → `23:31:38`에 `Sending interrupt signal to process` / `Terminated`, `Finished: ABORTED`. 정확히 10초 만에 강제 종료됨.

**배운 점**:
- `[Pipeline] { timeout ... }`도 `environment`(`withEnv`)와 같은 패턴의 wrapper step. 내부 step들을 감싸고 있다가 시간 초과 시 강제로 인터럽트 시그널을 보냄.
- `timestamps()` 옵션으로 각 로그 줄에 시간이 찍혀서 "몇 초 만에 잘렸는지"를 직접 셀 수 있었음.
- `timeout`은 **선언된 범위의 작업이 완료될 수 있는 최대 시간**이다. Pipeline의 `options`에 선언하면 전체 Pipeline에, Stage의 `options`에 선언하면 해당 Stage에만 적용되며 Stage마다 시간이 새로 주어지는 것은 아니다.

### 5-2. `disableConcurrentBuilds`

```groovy
pipeline {
    agent { label 'linux' }
    options {
        disableConcurrentBuilds()
    }
    stages {
        stage('Long Task') {
            steps {
                echo "작업 시작"
                sh 'sleep 30'
                echo "작업 종료"
            }
        }
    }
}
```

**진행**: `#14` 실행 중에 바로 `#15`를 트리거 → Build Queue 화면에 `#15`가 **Pending** 상태로 뜨고, 사유로 `빌드 #14가 이미 진행중입니다 (ETA: 19 sec)` 표시됨.

**배운 점**:
- `disableConcurrentBuilds`로 인한 "대기"는 **Executor 배정 이전, 큐(Queue) 레벨에서 걸리는 것**. 그래서 `#15`의 콘솔 로그를 열어봐도 대기 흔적 없이 `Started by user admin`부터 평범하게 시작함 — 대기 여부는 파이프라인 실행 로그가 아니라 Queue 화면에서 확인해야 하는 정보라는 걸 실습으로 확인.

---

## 6. `catchError` / `unstable`

### 6-1. `catchError` 사용

```groovy
pipeline {
    agent { label 'linux' }
    stages {
        stage('Lint') {
            steps {
                catchError(buildResult: 'UNSTABLE', stageResult: 'UNSTABLE') {
                    sh 'exit 1'
                }
            }
        }
        stage('Test') {
            steps {
                echo "Lint이 실패해도 이 stage는 실행됨"
            }
        }
    }
    post {
        always {
            echo "최종 빌드 결과: ${currentBuild.currentResult}"
        }
    }
}
```

**결과**: `Lint`의 `exit 1` → `Setting overall build result to UNSTABLE` 로그 찍힘. `Test` stage 정상 실행. 최종 `Finished: UNSTABLE`.

### 6-2. `catchError` 없이 (비교)

```groovy
stage('Lint') {
    steps {
        sh 'exit 1'
    }
}
```

**결과**: `Test` stage가 `Stage "Test" skipped due to earlier failure(s)`로 아예 실행 안 됨. 최종 `Finished: FAILURE`.

**배운 점**:
- `catchError`는 stage 안의 실패를 "삼켜서" 빌드 결과만 `UNSTABLE`로 낮추고 **파이프라인 실행은 계속 이어지게** 만드는 안전장치.
- `catchError` 없이 실패하면 이후 모든 stage가 `skipped due to earlier failure(s)`로 연쇄 스킵됨 — 3번에서 본 `skipped due to when conditional`과는 **원인이 다른 별개의 skip 메시지**라는 것도 구분해서 확인.

---

## 7. `parallel`/`matrix` — Executor와 병렬 실행

```groovy
pipeline {
    agent none
    stages {
        stage('Parallel Stage') {
            parallel {
                stage('Branch A') {
                    agent { label 'linux' }
                    steps {
                        sh 'echo "A 시작: $(date +%T)"'
                        sh 'sleep 10'
                        sh 'echo "A 종료: $(date +%T)"'
                    }
                }
                stage('Branch B') {
                    agent { label 'linux' }
                    steps {
                        sh 'echo "B 시작: $(date +%T)"'
                        sh 'sleep 10'
                        sh 'echo "B 종료: $(date +%T)"'
                    }
                }
            }
        }
    }
}
```

### 7-1. Executor 1개

| Branch | 시작 | 종료 |
|---|---|---|
| A | 23:53:20 | 23:53:31 |
| B | 23:53:31 | 23:53:42 |

**총 소요 약 22초** — B는 A가 끝날 때까지 대기했다가 시작 → **완전 순차 실행**.

### 7-2. Executor 2개로 변경 후 재실행

`Manage Jenkins → Nodes → jenkins-agent1 → Configure`에서 `# of executors`를 `1 → 2`로 변경.

| Branch | 시작 | 종료 |
|---|---|---|
| A | 23:56:34 | 23:56:44 |
| B | 23:56:34 | 23:56:44 |

**총 소요 약 10초** — A/B가 완전히 같은 시각에 시작·종료 → **완전 동시 실행**.

콘솔 로그에서 워크스페이스 경로가 `.../pipeline-syntax-lab`와 `.../pipeline-syntax-lab@2`로 **자동 분리**된 것도 확인됨 — 같은 노드에서 두 브랜치가 동시에 돌 때 파일 충돌을 막기 위해 Jenkins가 브랜치별 워크스페이스를 따로 만들어줌 (`reuseNode`를 안 썼기 때문).

### 7-3. `matrix`

#### Matrix 개념 정리

`matrix`는 `axes`에 정의한 값의 모든 조합을 cell로 만들고, 각 cell에서 같은 `stages`를 실행하는 기능이다.

```text
axes의 값 조합 → cell 생성 → cell끼리 병렬 실행
                              └─ cell 내부 stages는 순차 실행
```

- `axes`: 조합에 사용할 축과 값을 정의한다. 예를 들어 JDK 2개와 OS 3개를 지정하면 `2 × 3 = 6`개의 cell이 생성된다.
- `stages`: 각 cell에서 실행할 작업을 정의하며, 여러 Stage가 있으면 cell 안에서 순서대로 실행된다.
- `excludes`: 지원하지 않거나 불필요한 조합을 실행 대상에서 제거한다. `notValues`를 사용하면 특정 값이 아닌 조합을 제외할 수 있다.
- `agent`, `environment`, `when`, `options`, `post` 등은 cell마다 적용할 수 있고 axis 값을 참조할 수 있다.

`axes`와 `excludes`는 Pipeline 시작 전에 cell 집합을 결정한다. 반면 `when` 같은 cell별 directive는 실행 중 평가되므로, 조건이 맞지 않는 cell은 삭제되는 것이 아니라 skipped 처리된다. 논리적으로 cell들은 병렬 실행되지만 실제 동시 실행 수는 사용 가능한 Executor 수에 제한된다.

#### 실습

```groovy
pipeline {
    agent none
    stages {
        stage('Matrix Build') {
            matrix {
                axes {
                    axis {
                        name 'JDK_VERSION'
                        values '17', '21'
                    }
                }
                stages {
                    stage('Build') {
                        agent { label 'linux' }
                        steps {
                            echo "Building with JDK ${JDK_VERSION}"
                        }
                    }
                }
            }
        }
    }
}
```

**결과**: `JDK_VERSION=17`, `JDK_VERSION=21` 두 cell이 각각 `Building with JDK 17` / `Building with JDK 21` 출력, 워크스페이스도 `@2`로 분리되어 동시 실행됨.

**배운 점 (7번 종합)**:
- `parallel`의 동시성 여부는 코드만으로 결정되지 않고 **사용 가능한 Executor 슬롯 개수**에도 영향을 받음. Executor 1개에서는 순차 실행(~22초), 2개에서는 동시 실행(~10초)됨.
- 콘솔 로그 구조를 뜯어보면 `matrix`는 **`parallel` + `environment`(`withEnv`)를 자동 생성해주는 문법 설탕**임이 드러남 (`[Pipeline] parallel { (Branch: Matrix - JDK_VERSION = '17') ... withEnv { ... } }` 패턴).
- 같은 노드에서 병렬로 여러 브랜치가 돌 때 Jenkins가 `@2`, `@3`... 식으로 워크스페이스를 자동 분리해서 파일 충돌을 방지함.

---

## Wrapper step 정리

Wrapper step은 내부의 여러 step에 공통 설정을 적용하고, 그 적용 범위를 블록 안으로 제한한다.

```groovy
timeout(time: 10, unit: 'SECONDS') {
    sh './build.sh'
    sh './test.sh'
}
```

위 예시에서는 두 명령 전체에 제한 시간이 적용되며, 완료 또는 시간 초과 후 관련 상태가 정리된다.

- `withEnv`: 블록 안에 환경변수 적용
- `withCredentials`: Credential 주입 및 로그 마스킹
- `timeout`: 블록 전체의 실행 시간 제한
- `timestamps`: 내부 로그에 시간 추가
- `node`: Executor와 Workspace를 할당하고 종료 후 반환

Declarative의 `environment`, `options`, `agent`도 실행 시 `withEnv`, `timeout`, `node` 같은 wrapper 구조로 변환되므로 콘솔 로그에서 중첩된 블록으로 나타난다.
