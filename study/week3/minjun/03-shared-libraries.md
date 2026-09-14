# Shared Libraries

## 왜 필요한가

저장소가 여러 개면 Jenkinsfile도 여러 개이고, Slack 알림·Docker 빌드·배포 같은 공통 로직이 계속 복사된다. 하나를 고치면 전부 고쳐야 한다.

Shared Library는 이 공통 코드를 **별도 Git 저장소에 두고 여러 파이프라인이 불러다 쓰게** 한다. 파이프라인에 DRY 원칙을 적용한 것이다.

## 디렉터리 구조

```
(root)
+- src/                     # Groovy 클래스 (Java 소스 구조와 동일)
|   +- org/foo/Bar.groovy
+- vars/                    # 전역 변수·함수. 파일명이 곧 함수명
|   +- sayHello.groovy
|   +- sayHello.txt          # 선택. 해당 함수의 문서
+- resources/               # 정적 파일. libraryResource step으로 로드
    +- org/foo/config.json
```

- `vars/` 안의 `.groovy` 파일은 `call()` 메서드를 정의하면 Pipeline에서 함수처럼 호출된다.
- `src/`는 클래스패스에 추가된다. 구조화된 로직에 쓴다.
- `resources/`는 외부 라이브러리에서만 지원된다.

## 불러오기

```groovy
@Library('my-lib') _
@Library('my-lib@master') _        // 버전 지정
@Library(['lib-a', 'lib-b']) _     // 복수
```

`_`는 애노테이션 뒤에 대상이 필요해서 붙이는 관용 표현이다.

버전은 SCM이 이해하는 것이면 무엇이든 된다. 브랜치, 태그, 커밋 해시 모두 가능하다. Jenkins 설정에서 버전을 고정하고 스크립트가 다른 버전을 고르지 못하도록 막을 수도 있다.

`Load implicitly` 옵션을 켜면 `@Library` 없이도 모든 파이프라인에서 자동으로 로드된다.

## 등록 위치와 신뢰 모델

Shared Library는 세 곳에 등록할 수 있고, 각각 신뢰 수준이 다르다.

| 등록 위치 | 신뢰 | Sandbox | 필요 권한 |
|---|---|---|---|
| Global **Trusted** Pipeline Libraries | 신뢰 | **적용 안 됨** | `Overall/RunScripts` |
| Global **Untrusted** Pipeline Libraries | 비신뢰 | 적용됨 | `Overall/Manage` |
| Folder 레벨 라이브러리 | 비신뢰 (항상) | 적용됨 | Folder 설정 권한 |

공식 문서는 Trusted 라이브러리에 대해 이렇게 명시한다. Java, Groovy, Jenkins 내부 API, 플러그인, 서드파티 라이브러리의 **어떤 메서드든 실행할 수 있으며**, 이 SCM 저장소에 커밋을 푸시할 수 있는 사람은 누구든 Jenkins에 대한 무제한 접근 권한을 얻을 수 있다는 점에 주의해야 한다는 것이다.

---

## 실습: 같은 코드, 다른 등록 위치

이 신뢰 모델이 실제로 어떻게 작동하는지 직접 확인했다.

### 라이브러리 코드

`vars/sayHello.groovy` — Pipeline step만 사용
```groovy
def call(String name = 'World') {
    echo "Hello, ${name}! (from shared library)"
}
```

`vars/dangerousStep.groovy` — Jenkins 내부 API 직접 접근
```groovy
def call() {
    def jenkins = jenkins.model.Jenkins.instance
    echo "Jenkins 버전: ${jenkins.getVersion()}"
    echo "Job 개수: ${jenkins.getAllItems().size()}"
}
```

### 테스트 Pipeline

```groovy
@Library('my-lib') _

pipeline {
    agent any
    stages {
        stage('Safe Call')      { steps { sayHello('민준') } }
        stage('Dangerous Call') { steps { dangerousStep() } }
    }
}
```

---

### 결과 1 — Global **Untrusted** 등록

```
Loading library my-lib@master
Found match: refs/heads/master revision e2d63cd209dee86fd4af8136551142bf1a2f05cc
...
[Pipeline] { (Safe Call)
Hello, 민준! (from shared library)

[Pipeline] { (Dangerous Call)
Scripts not permitted to use staticMethod jenkins.model.Jenkins getInstance.
Administrators can decide whether to approve or reject this signature.

org.jenkinsci.plugins.scriptsecurity.sandbox.RejectedAccessException:
    Scripts not permitted to use staticMethod jenkins.model.Jenkins getInstance
	at dangerousStep.call(dangerousStep.groovy:3)
	at WorkflowScript.run(WorkflowScript:13)
Finished: FAILURE
```

### 결과 2 — Global **Trusted** 등록 (코드 변경 없음)

```
Loading library my-lib@master
Checking out Revision e2d63cd209dee86fd4af8136551142bf1a2f05cc (master)
...
[Pipeline] { (Safe Call)
Hello, 민준! (from shared library)

[Pipeline] { (Dangerous Call)
Jenkins 버전: 2.568.3
Job 개수: 3
Finished: SUCCESS
```

---

## 해석

### 같은 커밋, 정반대 결과

두 빌드 모두 `e2d63cd` 커밋을 체크아웃했다. 라이브러리 코드도, Jenkinsfile도, 저장소 경로도 동일하다. **바뀐 것은 Jenkins 설정에서 라이브러리를 어느 항목에 등록했는가뿐이다.**

Sandbox는 라이브러리의 내용을 검사해서 위험 여부를 판단하는 것이 아니라, **등록 위치로 결정되는 정책**이다.

### Sandbox는 메서드 호출 단위로 검사한다

같은 라이브러리 안의 두 함수가 결과가 갈렸다.

- `sayHello`는 `echo`만 사용 → 허용 목록 안
- `dangerousStep`은 `jenkins.model.Jenkins.getInstance` 호출 → 차단

스택트레이스의 `at dangerousStep.call(dangerousStep.groovy:3)`이 라이브러리 코드 내부에서 막혔음을 보여준다. 라이브러리 단위가 아니라 개별 호출 단위로 검사한다는 뜻이다.

### Sandbox는 절대 차단이 아니라 승인 게이트다

차단 메시지에 이어지는 문장이 핵심이다.

> Administrators can decide whether to approve or reject this signature.

관리자가 Script Security 플러그인의 In-process Script Approval에서 승인하면 이 호출은 통과한다. 즉 Sandbox는 "이 코드는 절대 실행 불가"가 아니라 **"관리자 판단이 필요하다"는 보류 상태**다.

### `Jenkins.instance`를 잡았다는 것의 의미

Trusted에서 출력된 값은 버전과 Job 개수였지만, 이는 예시에 불과하다. `Jenkins.instance`는 Jenkins 컨트롤러 객체 그 자체이므로, 같은 객체로 Credential 목록 조회, 사용자 권한 변경, 플러그인 조작이 모두 가능하다. 공식 문서의 "무제한 접근"이라는 표현이 과장이 아니다.

---

## 실습 중 발생한 문제 — 로컬 경로 체크아웃 차단

라이브러리를 로컬 디렉터리 경로로 등록했을 때 다음 오류가 발생했다.

```
Found match: refs/heads/master revision e2d63cd...
ERROR: Checkout of Git remote '/var/jenkins_home/shared-lib' aborted
because it references a local directory, which may be insecure.
You can allow local checkouts anyway by setting the system property
'hudson.plugins.git.GitSCM.ALLOW_LOCAL_CHECKOUT' to true.
```

저장소를 찾는 데까지는 성공했고(커밋 해시까지 확인됨), 체크아웃 단계에서 Git 플러그인이 거부했다.

### 왜 막는가

로컬 경로를 허용하면 Jenkins 컨트롤러 파일 시스템의 임의 경로를 저장소로 지정할 수 있게 된다. Job 설정 권한만 가진 사용자가 민감한 디렉터리를 가리켜 그 내용을 워크스페이스로 가져올 여지가 생긴다.

### 해제 방법과 그 의미

```bash
docker run -d --name jenkins \
  -e JAVA_OPTS="-Dhudson.plugins.git.GitSCM.ALLOW_LOCAL_CHECKOUT=true" \
  ... jenkins/jenkins:lts
```

시스템 프로퍼티는 Jenkins 기동 옵션이므로 **컨트롤러를 운영하는 사람만 바꿀 수 있다.** UI에서 Job을 설정하는 권한으로는 건드릴 수 없다. 기본값이 차단이고 해제 권한을 관리자에게만 둔 구조 자체가 설계 의도를 보여준다.

---

## 정리

| 항목 | Untrusted | Trusted |
|---|---|---|
| Groovy Sandbox | 적용 | 미적용 |
| Jenkins 내부 API | 차단 (관리자 승인 시 허용) | 전면 허용 |
| `@Grab` 외부 의존성 | 불가 | 가능 |
| Replay 기능 | 지원 | 미지원 |
| 설정 권한 | `Overall/Manage` | `Overall/RunScripts` |
| 저장소 푸시 권한의 의미 | 파이프라인 로직 변경 | **Jenkins 전체 제어** |

### 운영 원칙

- Trusted 라이브러리 저장소의 **푸시 권한은 Jenkins 관리자 권한과 동등하게** 취급한다.
- 라이브러리 버전을 브랜치(`@master`)가 아니라 태그나 커밋 해시로 고정하면, 저장소에 새 커밋이 들어와도 기존 파이프라인이 즉시 영향을 받지 않는다.
- 외부에서 가져온 코드나 검증되지 않은 라이브러리는 Untrusted 또는 Folder 레벨에 둔다.
- 필요한 메서드만 개별 승인하고, 편의를 위해 Trusted로 올리는 선택은 그 의미를 이해한 뒤에 한다.

### 3주간 반복된 구조

| 주차 | 실행 시점 방어 | 우회/해제 경로 | 실제 통제 지점 |
|---|---|---|---|
| Week 2 | Secret Masking | `rev`, `cut` 등 문자열 변형 | `Job/Configure` 권한 |
| Week 3 | Groovy Sandbox | 등록 위치를 Trusted로 변경 | **라이브러리 저장소 푸시 권한** |

두 번 모두 실행 시점의 방어 장치는 우회 가능하거나 설정으로 해제할 수 있었고, 실제 통제는 **누가 코드를 넣을 수 있는가**에 있었다. Week 3에서는 그것이 가장 명확하게 드러났다. Sandbox는 우회할 필요조차 없이, 등록 항목을 옮기는 것만으로 꺼지는 스위치였기 때문이다.

## 참고 자료

- [Jenkins 공식 문서 - Extending with Shared Libraries](https://www.jenkins.io/doc/book/pipeline/shared-libraries/)
- [Jenkins 공식 문서 - Script Security](https://www.jenkins.io/doc/book/security/securing-jenkins/)
- [Script Security Plugin](https://plugins.jenkins.io/script-security/)
