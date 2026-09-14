# Multibranch Pipeline

## 핵심 개념

- 일반 Pipeline Job은 브랜치 하나에 Job 하나가 대응한다. 브랜치가 늘어나면 Job을 사람이 직접 만들어야 한다.
- Multibranch Pipeline은 저장소를 스캔해서 **Jenkinsfile이 있는 브랜치마다 Job을 자동 생성**한다. 브랜치가 사라지면 Job도 함께 정리된다.
- 즉 파이프라인 대상 목록을 Jenkins 설정이 아니라 **저장소 자체가 선언**하는 구조다.

## 실습 구성

로컬 Git 저장소에 브랜치 3개를 만들고 Multibranch Pipeline으로 등록했다.

| 브랜치 | Jenkinsfile | 의도 |
|---|---|---|
| `main` | 있음 | 배포 stage 실행 대상 |
| `feature/login` | 있음 | 배포 stage 제외 대상 |
| `docs-only` | **없음** | 스캔에서 걸러지는지 확인 |

사용한 Jenkinsfile:

```groovy
pipeline {
    agent any
    stages {
        stage('Info') {
            steps {
                echo "브랜치: ${env.BRANCH_NAME}"
                echo "잡 이름: ${env.JOB_NAME}"
            }
        }
        stage('Test') {
            steps { sh 'echo "테스트는 모든 브랜치에서 실행"' }
        }
        stage('Deploy') {
            when { branch 'main' }
            steps { sh 'echo "배포는 main에서만"' }
        }
    }
}
```

## 1. 브랜치 스캔 (Branch Indexing)

스캔 로그:

```
Checking branches...
  Checking branch feature/login
      'Jenkinsfile' found
    Met criteria
Scheduled build for branch: feature/login
  Checking branch main
      'Jenkinsfile' found
    Met criteria
Scheduled build for branch: main
  Checking branch docs-only
      'Jenkinsfile' not found
    Does not meet criteria
Processed 3 branches
Indexing took 0.12 sec
```

### 확인한 것

- 기준은 단 하나, **Jenkinsfile의 존재 여부**다. 있으면 Job 생성 + 빌드 예약, 없으면 제외.
- `docs-only`는 실패한 것이 아니라 **애초에 파이프라인 대상이 아니라고 판단**된 것이다. Job 목록에 나타나지 않는다.
- 스캔은 0.12초로 끝났다. 저장소 전체를 체크아웃하는 것이 아니라 각 브랜치에 Jenkinsfile이 있는지만 확인하는 가벼운 작업이다.

## 2. 브랜치별 실행 결과

### main

```
Obtained Jenkinsfile from f36aa6cf69211ca45b0c3f73427de48231c3b3bb
Running on Jenkins in /var/jenkins_home/workspace/multibranch-demo_main
...
브랜치: main
잡 이름: multibranch-demo/main
+ echo 테스트는 모든 브랜치에서 실행
+ echo 배포는 main에서만        ← 실행됨
Finished: SUCCESS
```

### feature/login

```
Obtained Jenkinsfile from 376556f821d57505e25ae68576475c7aa46eb4d3
Running on Jenkins in /var/jenkins_home/workspace/multibranch-demo_feature_login
...
브랜치: feature/login
잡 이름: multibranch-demo/feature%2Flogin
+ echo 테스트는 모든 브랜치에서 실행
Stage "Deploy" skipped due to when conditional    ← 건너뜀
Finished: SUCCESS
```

### 로그에서 확인한 것

**브랜치마다 자기 커밋의 Jenkinsfile을 쓴다.** `Obtained Jenkinsfile from <커밋해시>` 줄이 서로 다르다(`f36aa6c` vs `376556f`). 즉 feature 브랜치에서 파이프라인을 수정하면 그 브랜치의 빌드만 바뀐 파이프라인으로 돈다. 파이프라인 변경이 코드 리뷰 대상이 되는 이유다.

**워크스페이스가 브랜치별로 분리된다.** `multibranch-demo_main`과 `multibranch-demo_feature_login`이 별도 디렉터리다. 브랜치 간 빌드 산출물이 섞이지 않는다.

**`JOB_NAME`에 URL 인코딩이 들어간다.** `feature/login`이 `feature%2Flogin`이 됐다. 슬래시가 Job 계층 구분자와 충돌하기 때문이다. Job 이름을 스크립트에서 문자열로 다룰 때 걸릴 수 있는 부분이다.

**`when { branch 'main' }`은 Multibranch에서만 의미가 있다.** 일반 Pipeline Job에는 `BRANCH_NAME` 환경 변수가 없기 때문이다.

## 3. Pull Request 빌드

이번 실습은 로컬 Git 저장소를 사용해 PR 빌드까지는 확인하지 못했다. 공식 문서 기준으로 정리하면 다음과 같다.

- GitHub/GitLab Branch Source Plugin을 쓰면 브랜치뿐 아니라 **PR도 Job으로 잡힌다.**
- PR Job은 머지 전 상태를 빌드하므로 머지 후 깨지는 것을 사전에 잡을 수 있다.
- 결과는 Status Check API를 통해 PR 화면에 체크 표시로 돌아간다.
- Webhook을 쓰면 이벤트 기반으로 스캔이 트리거된다. 로컬 환경처럼 Webhook을 받을 수 없으면 `Periodically if not otherwise run` 옵션으로 주기 스캔을 설정한다(이번 실습은 1분 주기).

### 동시 빌드 문제

PR에 커밋을 연달아 푸시하면 이전 빌드가 아직 도는 중에 새 빌드가 쌓인다. 이미 의미 없는 빌드가 자원을 점유하는 것이다.

| 방법 | 동작 |
|---|---|
| `options { disableConcurrentBuilds() }` | 같은 Job의 동시 실행 자체를 막음 |
| `milestone` step | 뒤 빌드가 마일스톤을 통과하면 앞 빌드를 자동 취소 |

## 4. 보안 관점

Multibranch의 구조는 **브랜치를 푸시할 수 있는 사람이 파이프라인을 정의할 수 있다**는 뜻이다.

- 브랜치에 Jenkinsfile을 넣으면 다음 스캔에서 Job이 생기고 그 코드가 Jenkins에서 실행된다.
- PR 빌드를 자동으로 도는 설정이라면, 외부 기여자의 PR에 포함된 Jenkinsfile이 그대로 실행될 수 있다.
- 따라서 실무에서는 PR 빌드에 신뢰 정책(승인된 사용자만 빌드, 또는 관리자 승인 후 빌드)을 걸고, 브랜치 보호 규칙으로 Jenkinsfile 변경 경로를 제한한다.

이는 앞선 주차에서 확인한 "Jenkinsfile을 수정할 수 있는 사람은 그 Job의 Credential을 유출할 수 있다"와 같은 문제다. Multibranch는 그 수정 경로를 **브랜치 푸시 권한**까지 넓힌 것이다.

## 참고 자료

- [Jenkins 공식 문서 - Branches and Pull Requests](https://www.jenkins.io/doc/book/pipeline/multibranch/)
- [Jenkins 공식 문서 - Pipeline Syntax: when](https://www.jenkins.io/doc/book/pipeline/syntax/#when)
