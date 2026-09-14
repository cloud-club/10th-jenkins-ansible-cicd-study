# Shared Libraries (핵심)

## Shared Library가 필요한 이유

---

여러 Repository의 Jenkinsfile에 같은 Build, Test, Notification 코드가 반복되면 변경할 때마다 모든 Repository를 수정해야 한다. 시간이 지나면 서비스마다 Pipeline 동작도 달라진다.

```
service-a/Jenkinsfile ─┐
service-b/Jenkinsfile ─┼──▶ company-pipeline-library
service-c/Jenkinsfile ─┘
```

Shared Library를 사용하면 공통 실행 로직과 조직 정책을 별도의 SCM Repository에서 관리할 수 있다.

### 무엇을 공통화하는가?

Shared Library는 단순히 Jenkinsfile을 복사해 두는 템플릿이 아니라, **여러 Pipeline에서 반복되는 CI/CD 로직을 함수와 Class 형태로 모듈화하여 재사용하는 구조**다.

예를 들어 여러 Spring 서비스가 다음과 같은 공통 흐름을 가진다고 가정한다.

```
Checkout
→ Gradle Build
→ Test
→ Docker Build
→ Image Push
→ Deploy
→ Health Check
→ 실패 시 Slack 알림
```

서비스마다 이 로직을 Jenkinsfile에 반복해서 작성하는 대신 공통 부분을 Shared Library로 분리한다.

```
Jenkinsfile                     Shared Library
서비스별 Pipeline 흐름/설정  →  springBuild()
                              dockerBuild()
                              deploy()
                              healthCheck()
                              notifySlack()
```

따라서 Application의 Jenkinsfile에는 **해당 서비스의 흐름과 차이점**을 남기고, Shared Library에는 **조직 전체에서 재사용할 공통 구현과 정책**을 둔다.

대표적인 공통화 대상:

- Spring/Gradle Build 및 Test
- Docker Image Build / Tagging / Registry Push
- 개발·운영 환경별 Deploy
- Health Check 및 Rollback
- 실패·성공 시 Slack/Teams 알림
- Test Result 발행
- SonarQube 또는 정적 분석
- 공통 Timeout, Retry, Credential 처리 정책

<aside>
💡

Shared Library를 "회사에서 사용할 CI/CD 템플릿과 공통 함수 모음"으로 이해하면 쉽다. 다만 정적인 템플릿보다는 Parameter를 받아 동작을 바꿀 수 있는 **재사용 가능한 Groovy 코드 모듈**에 더 가깝다.

</aside>

# 3-1. Shared Library 구조 (`vars`, `src`, `resources`)

---

```
jenkins-shared-library/
├── vars/
│   ├── gradleBuild.groovy
│   ├── gradleBuild.txt
│   └── notifyBuild.groovy
├── src/
│   └── com/
│       └── study/
│           └── ci/
│               └── BuildPolicy.groovy
├── resources/
│   └── com/
│       └── study/
│           └── ci/
│               └── notification.json
├── test/
│   └── GradleBuildTest.groovy
├── build.gradle
└── settings.gradle
```

- **vars/**: Jenkinsfile에서 Global Function 또는 Custom Step처럼 호출할 Groovy Script
- **src/**: Package 구조를 가진 재사용 가능한 Groovy Class
- **resources/**: JSON, YAML, Shell Template 같은 비-Groovy 리소스
- **test/**: Shared Library Unit Test
- **vars/name.txt**: Global Variable Reference에 표시할 사용 설명

# 3-2. Groovy Global 함수와 Class 모듈화 (DRY)

---

vars/gradleBuild.groovy:

```groovy
def call(Map config = [:]) {
    boolean skipTests = config.get('skipTests', false)
    boolean useBuildCache = config.get('useBuildCache', true)

    String command = './gradlew --no-daemon clean build'

    if (skipTests) {
        command += ' -x test'
    }

    if (useBuildCache) {
        command += ' --build-cache'
    }

    sh command
}
```

Jenkinsfile:

```groovy
@Library('company-ci@v1.0.0') _

pipeline {
    agent {
        label 'java21'
    }

    stages {
        stage('Build') {
            steps {
                gradleBuild(
                    skipTests: false,
                    useBuildCache: true
                )
            }
        }
    }
}
```

파일명이 gradleBuild.groovy이므로 Jenkinsfile에서는 gradleBuild로 호출한다. call 메서드를 정의하면 Jenkins 기본 Step과 비슷한 사용법을 제공할 수 있다.

### vars 작성 원칙

- 하나의 파일은 하나의 명확한 책임을 갖는다.
- Global Variable에 Build 실행 상태를 저장하지 않는다.
- 기본값과 입력값의 의미를 문서화한다.
- Shell 명령에 연결되는 외부 입력을 검증한다.
- sh, timeout 같은 Jenkins 기본 Step 이름을 덮어쓰지 않는다.
- 거대한 common.groovy 하나에 모든 함수를 몰아넣지 않는다.

## src: Class 모듈화

---

src/com/study/ci/BuildPolicy.groovy:

```groovy
package com.study.ci

class BuildPolicy implements Serializable {

    static boolean shouldDeploy(
        String branchName,
        boolean changeRequest
    ) {
        return branchName == 'main' && !changeRequest
    }
}
```

Jenkinsfile:

```groovy
@Library('company-ci@v1.0.0') _

import com.study.ci.BuildPolicy

pipeline {
    agent any

    stages {
        stage('Deploy') {
            when {
                expression {
                    return BuildPolicy.shouldDeploy(
                        env.BRANCH_NAME,
                        env.CHANGE_ID != null
                    )
                }
            }

            steps {
                sh './scripts/deploy.sh'
            }
        }
    }
}
```

src에 적합한 로직:

- 배포 가능 여부와 같은 정책 판단
- 설정 검증
- 문자열과 데이터 가공
- 여러 Global Step이 공유하는 로직
- Jenkins 없이 독립적으로 Unit Test할 수 있는 로직

Jenkins Step을 Class에서 호출해야 한다면 Pipeline Script를 주입할 수 있다.

```groovy
package com.study.ci

class DockerBuilder implements Serializable {
    private final def steps

    DockerBuilder(def steps) {
        this.steps = steps
    }

    void build(String imageName) {
        steps.sh "docker build -t '${imageName}' ."
    }
}
```

사용:

```groovy
script {
    def builder = new DockerBuilder(this)
    builder.build('sample-api:latest')
}
```

## resources: 정적 파일

---

resources/com/study/ci/notification.json:

```json
{
  "service": "${SERVICE_NAME}",
  "status": "${BUILD_STATUS}",
  "buildUrl": "${BUILD_URL}"
}
```

리소스 로딩:

```groovy
String template = libraryResource(
    'com/study/ci/notification.json'
)

writeFile(
    file: 'notification.json',
    text: template
)
```

resources는 외부 Shared Library에서 libraryResource Step으로 읽을 수 있다. 충돌을 피하기 위해 Package와 비슷한 고유 경로를 사용한다.

## Jenkins에 Library 등록

---

일반적인 구성 위치:

```
Manage Jenkins
    ↓
System
    ↓
Global Trusted Pipeline Libraries
또는
Global Untrusted Pipeline Libraries
```

주요 설정:

- Name: company-ci
- Default version: main 또는 안정화 Tag
- Load implicitly: 명시적 로딩 없이 모든 Pipeline에 제공할지 결정
- Allow default version to be overridden: Jenkinsfile에서 Version을 바꿀 수 있는지 결정
- Retrieval method: Modern SCM 권장
- Repository URL과 Credential 설정

Folder 단위 Library도 구성할 수 있다. Folder Library는 해당 Folder와 하위 Job에만 적용되며 Untrusted로 실행된다.

## Library 로딩과 Version

---

기본 Version:

```groovy
@Library('company-ci') _
```

Release Tag:

```groovy
@Library('company-ci@v1.2.0') _
```

Feature Branch:

```groovy
@Library('company-ci@feature/new-build') _
```

동적 로딩:

```groovy
library "company-ci@${params.LIBRARY_VERSION}"
```

@Library는 Jenkinsfile이 Compile되기 전에 Library를 Classpath에 올리므로 src Class를 import할 수 있다. library Step은 Pipeline 실행 중 동적으로 로드되므로 이미 Compile된 코드에서 Class를 정적으로 import할 수는 없다.

### Version 운영 권장

```
Library main
    ↓ Test
v1.0.0
    ↓
일부 서비스에서 검증
    ↓
전체 서비스가 순차적으로 Upgrade
```

모든 서비스가 변경 가능한 main을 그대로 참조하면 Library의 한 번의 변경으로 여러 서비스 Pipeline이 동시에 깨질 수 있다. 안정적인 Release Tag를 기본으로 사용하고 Upgrade 절차를 두는 방식을 검토한다.

## Trusted와 Untrusted

---

### Trusted Library

- Groovy Sandbox 밖의 API와 Jenkins 내부 기능에 접근할 수 있다.
- 강력하지만 Library Repository의 변경 권한이 곧 Jenkins의 높은 실행 권한으로 이어질 수 있다.
- Merge 권한, Branch Protection, Code Review가 중요하다.

### Untrusted Library

- Groovy Sandbox 제한을 받는다.
- Folder 단위 Shared Library는 항상 Untrusted다.
- 허용되지 않은 API 사용은 Script Approval이 필요할 수 있다.

<aside>
⚠️

Trusted Shared Library Repository에 Push할 수 있는 사용자는 Jenkins Controller에 매우 강한 권한을 가질 수 있다. Application Repository와 같은 수준으로 느슨하게 관리하면 안 된다.

</aside>

## Shared Library 설계 원칙

---

### 좋은 구조

- Jenkinsfile에서 전체 Stage 흐름을 파악할 수 있다.
- Library Step의 입력과 출력이 명확하다.
- vars는 얇게 유지하고 복잡한 정책은 src Class로 분리한다.
- 각 Step은 독립적으로 Test할 수 있다.
- 변경 사항은 Semantic Version 또는 명확한 Tag로 배포한다.
- 하위 호환성이 깨지는 변경은 Major Version으로 분리한다.
- Pipeline에서 수행할 작업은 가능한 한 Repository의 Script나 Build Tool로 위임한다.

### 피해야 할 구조

- 하나의 Global Step이 Checkout부터 운영 배포까지 모든 것을 숨긴다.
- 사용하지 않는 기능까지 포함된 거대한 Library를 모든 Job이 로드한다.
- Jenkins 내장 Step을 같은 이름으로 재정의한다.
- Global Variable에 변경 가능한 상태를 보관한다.
- @Grab으로 실행 시점에 외부 Dependency를 다운로드한다.
- Secret을 Library 소스나 resources에 저장한다.

# 3-3. Shared Library Unit Test (JenkinsPipelineUnit)

---

JenkinsPipelineUnit은 실제 Jenkins Controller를 실행하지 않고 Pipeline과 Shared Library의 제어 로직을 Mock 기반으로 Test한다.

검증할 수 있는 항목:

- 특정 sh 명령이 호출됐는가?
- Parameter에 따라 올바른 분기가 선택됐는가?
- Shared Library Step에 올바른 인자가 전달됐는가?
- Pipeline 결과가 SUCCESS, UNSTABLE, FAILURE 중 무엇인가?
- Jenkins Step의 호출 순서가 의도와 일치하는가?

2026년 9월 13일 기준 GitHub 최신 Release는 1.29이며 현재 문서는 Java 21을 요구한다. 실제 적용 시 선택한 Version의 Release Note와 호환성을 다시 확인한다.

build.gradle:

```groovy
plugins {
    id 'groovy'
}

repositories {
    mavenCentral()
    maven {
        url = uri('https://repo.jenkins-ci.org/releases/')
    }
}

dependencies {
    testImplementation 'com.lesfurets:jenkins-pipeline-unit:1.29'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
}

test {
    useJUnitPlatform()
}
```

test/GradleBuildTest.groovy:

```groovy
import com.lesfurets.jenkins.unit.BasePipelineTest
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test

import static org.junit.jupiter.api.Assertions.assertTrue

class GradleBuildTest extends BasePipelineTest {

    private final List<String> commands = []
    private def gradleBuild

    @Override
    @BeforeEach
    void setUp() {
        super.setUp()

        helper.registerAllowedMethod('sh', [String]) {
            String command -> commands.add(command)
        }

        gradleBuild = loadScript('vars/gradleBuild.groovy')
    }

    @Test
    void runsTestsByDefault() {
        gradleBuild.call()

        assertTrue(
            commands.any {
                it.contains('clean build') &&
                !it.contains('-x test')
            }
        )
    }

    @Test
    void canSkipTests() {
        gradleBuild.call(skipTests: true)

        assertTrue(
            commands.any {
                it.contains('-x test')
            }
        )
    }
}
```

실행:

```bash
./gradlew test
```

JenkinsPipelineUnit은 Pipeline의 제어 흐름을 검증한다. 실제 Docker Build, Network, Credential, Plugin 간 연동은 별도의 통합 Test Pipeline으로 검증해야 한다.

## Library 변경 배포 흐름

---

```
Feature Branch
    ↓
Unit Test / Static Analysis
    ↓
Pull Request Review
    ↓
Consumer Test Pipeline
    ↓
Release Tag 생성
    ↓
일부 Application에서 Version Upgrade
    ↓
전체 Application에 확산
```

GitHub에 Library가 있다면 GitHub Branch Source의 PR Ref를 이용해 Library PR 변경을 Consumer Pipeline에서 미리 시험하는 방식도 사용할 수 있다.

```groovy
@Library('company-ci@pull/123/head') _
```

## 실습

---

- [ ]  Shared Library Repository를 생성한다.
- [ ]  vars/gradleBuild.groovy를 작성한다.
- [ ]  vars/publishTestResult.groovy를 작성한다.
- [ ]  vars/notifyBuild.groovy를 작성한다.
- [ ]  src에 배포 정책 Class를 만든다.
- [ ]  resources에 알림 Template을 추가한다.
- [ ]  Jenkins에 Global 또는 Folder Library로 등록한다.
- [ ]  Application Jenkinsfile에서 @Library로 불러온다.
- [ ]  기본 동작과 Option 동작을 검사하는 Unit Test를 작성한다.
- [ ]  v1.0.0 Tag를 생성하고 Jenkinsfile에서 Version을 고정한다.

## 확인 질문

---

1. vars와 src의 책임은 어떻게 나누는 것이 좋은가?
2. Global Variable에 상태를 저장하면 Controller 재시작 후 어떤 문제가 생길 수 있는가?
3. Trusted Library 변경 권한을 엄격하게 관리해야 하는 이유는 무엇인가?
4. Application Jenkinsfile이 Library main을 직접 참조하면 어떤 위험이 있는가?
5. JenkinsPipelineUnit으로 검증할 수 없는 항목은 무엇인가?

## 참고 자료

---

- [Jenkins 공식 문서 - Shared Libraries[1]](https://www.jenkins.io/doc/book/pipeline/shared-libraries/)
- [Jenkins 공식 문서 - Pipeline Best Practices[2]](https://www.jenkins.io/doc/book/pipeline/pipeline-best-practices/)
- [JenkinsPipelineUnit[3]](https://github.com/jenkinsci/JenkinsPipelineUnit)
- [JenkinsPipelineUnit Releases[4]](https://github.com/jenkinsci/JenkinsPipelineUnit/releases)