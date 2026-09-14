# Pipeline Best Practices & Operations

## CPS 변환과 Controller 부하

### CPS란

Jenkins Pipeline은 실행 도중 컨트롤러가 재시작되어도 이어서 진행될 수 있어야 한다. 그러려면 실행 상태를 매 단계 저장해야 하는데, 이를 위해 Groovy 코드를 **CPS(Continuation Passing Style)로 변환**해서 실행한다.

일반적인 실행은 호출 스택에 상태가 쌓이지만, CPS는 "다음에 할 일"을 값으로 들고 다니는 방식이라 중간 상태를 직렬화해 디스크에 저장할 수 있다.

### 부작용

- 변환된 코드는 **Jenkins 컨트롤러 위에서** 한 단계씩 상태를 저장하며 실행된다.
- 따라서 Groovy로 큰 컬렉션을 순회하거나 문자열을 대량 처리하면 컨트롤러 메모리를 빠르게 소모한다. 심하면 OOM으로 Jenkins 전체가 멈춘다.
- 일부 Groovy 문법(일부 클로저, `.each` 대신 `for` 권장 등)이 CPS 환경에서 예상과 다르게 동작한다.

### 원칙

**Groovy는 흐름 제어만, 실제 연산은 `sh` 스텝으로 에이전트에서.**

```groovy
// 나쁜 예 — 컨트롤러에서 대량 처리
script {
    def lines = readFile('huge.log').split('\n')
    def errors = lines.findAll { it.contains('ERROR') }
    echo "에러 ${errors.size()}건"
}

// 좋은 예 — 에이전트에서 처리
sh 'grep -c ERROR huge.log > error_count.txt'
def count = readFile('error_count.txt').trim()
```

이는 Week 2의 Controller/Agent 분리와 같은 원칙이다. 컨트롤러는 조율하고 에이전트는 실행한다. CPS OOM 문제도 결국 이 경계를 지키지 않아서 생긴다.

`@NonCPS` 애노테이션을 붙이면 해당 메서드는 CPS 변환에서 제외되어 일반 Groovy로 실행된다. 다만 그 안에서는 Pipeline step을 호출할 수 없고, 중단·재개도 불가능하다.

## 파일 전달과 성능

### `stash` / `unstash`

같은 Pipeline 실행 안에서 stage 간에 파일을 넘긴다. 서로 다른 에이전트에서 실행되는 stage 사이에도 동작한다.

```groovy
stage('Build') {
    agent { label 'builder' }
    steps {
        sh './gradlew build'
        stash name: 'app-jar', includes: 'build/libs/*.jar'
    }
}
stage('Deploy') {
    agent { label 'deployer' }
    steps {
        unstash 'app-jar'
        sh './deploy.sh build/libs/*.jar'
    }
}
```

stash 데이터는 컨트롤러에 저장되므로 **큰 파일에는 적합하지 않다.** 대용량 산출물은 아티팩트 저장소나 오브젝트 스토리지를 쓴다.

`options { preserveStashes() }`를 주면 특정 stage부터 재시작할 때를 위해 stash를 보관한다.

### 캐싱

의존성 디렉터리를 에이전트 호스트에 마운트해 컨테이너가 사라져도 재사용한다.

```groovy
agent {
    docker {
        image 'maven:3.9-eclipse-temurin-21'
        args '-v $HOME/.m2:/root/.m2'
    }
}
```

### 빌드 기록 관리

```groovy
options {
    buildDiscarder(logRotator(numToKeepStr: '10', daysToKeepStr: '30'))
}
```

빌드 로그와 아티팩트는 컨트롤러 디스크를 차지한다. 보관 정책을 명시하지 않으면 무한히 쌓인다.

## 알림

```groovy
post {
    failure {
        slackSend(
            color: 'danger',
            message: "빌드 실패: ${env.JOB_NAME} #${env.BUILD_NUMBER} (${env.BUILD_URL})"
        )
    }
    fixed {
        slackSend(color: 'good', message: "빌드 복구: ${env.JOB_NAME}")
    }
}
```

`fixed` 조건은 실패 상태에서 성공으로 회복됐을 때만 실행되므로, 성공할 때마다 알림이 오는 소음을 피할 수 있다.

알림 로직은 여러 저장소에서 반복되므로 Shared Library의 `vars/`로 분리하기 좋은 대상이다.

### 알림과 로그 노출

알림 메시지에 빌드 로그 일부를 포함시키는 구성은 흔하다. 이때 Week 2에서 확인한 문제가 다시 나타난다. Credential이 로그에 마스킹되어 있어도, 마스킹을 우회한 형태로 찍혀 있으면 그대로 외부 채널로 전송된다. 알림 채널의 접근 범위는 대개 빌드 권한보다 넓다.

## Shared Library 테스트

Shared Library는 여러 파이프라인이 의존하는 코드이므로 테스트 대상이 된다. JenkinsPipelineUnit 프레임워크로 단위 테스트를 붙일 수 있다.

- Pipeline step을 모킹해서 Groovy 코드 자체를 검증한다.
- 실제 Jenkins 인스턴스 없이 실행된다.
- 라이브러리를 "코드처럼 관리한다"는 것의 마지막 조각이다.

## `script` 블록 사용 기준

Declarative Pipeline 안에서 복잡한 Groovy가 필요하면 `script` 블록을 쓴다. 다만 길어지면 Declarative의 장점이 사라진다.

| 코드 상태 | 권장 |
|---|---|
| 5~10줄 정도의 분기 | `script` 허용 |
| 여러 stage/저장소에서 반복 | Shared Library로 분리 |
| 테스트가 필요한 복잡한 로직 | Shared Library + 단위 테스트 |
| Pipeline 전체가 매우 동적 | Scripted Pipeline 검토 |

## Week 3 전체 정리

이번 주 네 주제를 관통하는 것은 **역할 분리**다.

- `parallel`은 작업을 시간 축에서 분리한다.
- Multibranch는 실행 맥락을 브랜치 단위로 분리한다.
- Shared Library는 공통 로직을 파이프라인 밖으로 분리한다.
- CPS 원칙은 연산을 컨트롤러에서 에이전트로 분리한다.

그리고 분리한 경계마다 **신뢰 경계가 함께 생긴다.** 브랜치를 푸시할 수 있는 사람, 라이브러리에 커밋할 수 있는 사람, 컨트롤러 기동 옵션을 바꿀 수 있는 사람이 각각 다른 수준의 권한을 갖는다. 구조를 나누는 일과 권한을 설계하는 일이 분리되지 않는다는 것이 이번 주에 남은 부분이다.

## 참고 자료

- [Jenkins 공식 문서 - Pipeline Best Practices](https://www.jenkins.io/doc/book/pipeline/pipeline-best-practices/)
- [Jenkins 공식 문서 - Pipeline: Basic Steps](https://www.jenkins.io/doc/pipeline/steps/workflow-basic-steps/)
- [JenkinsPipelineUnit](https://github.com/jenkinsci/JenkinsPipelineUnit)
