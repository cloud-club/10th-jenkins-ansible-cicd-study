# Configuration as Code (JCasC)

## 문제 정의

- Jenkins 설정은 기본적으로 Web UI에서 수동으로 한다. 플러그인 설치, 계정 생성, Global Tool 경로, Credential 등록이 모두 클릭 기반이다.
- 이 방식의 한계는 세 가지다.
  * **재현 불가**: 서버가 손실되면 처음부터 다시 클릭해야 한다. 어떤 설정을 했는지 기록도 남지 않는다.
  * **추적 불가**: 누가 언제 어떤 설정을 바꿨는지 알기 어렵다.
  * **롤백 불가**: 설정을 잘못 바꿨을 때 이전 상태로 되돌릴 방법이 없다.
- 과거에는 Groovy init script로 이를 해결했지만, Jenkins 내부 API를 직접 호출하는 방식이라 진입 장벽이 높고 위험했다.

## JCasC의 접근

- Configuration as Code 플러그인은 Jenkins 설정을 사람이 읽을 수 있는 선언형 YAML로 정의한다.
- Controller가 기동될 때 YAML을 읽어 설정을 적용한다. Setup Wizard 없이 원하는 상태로 바로 시작할 수 있다.
- 파일명은 관례적으로 `jenkins.yaml`을 사용하며, 위치는 환경 변수 `CASC_JENKINS_CONFIG`로 지정한다.
- 여러 YAML 파일로 나누어 관리할 수도 있다.

## 얻는 것

- **재현성**: 같은 YAML이면 같은 Jenkins가 뜬다. 컨테이너 기반 운영과 특히 잘 맞는다.
- **감사 추적**: YAML을 SCM에 넣으면 설정 변경이 커밋 이력으로 남는다. 누가 언제 무엇을 바꿨는지 확인할 수 있다.
- **롤백**: 이전 커밋으로 되돌리고 재기동하면 이전 설정 상태로 복구된다.
- **검토 가능**: 설정 변경도 코드 리뷰 대상이 된다. Jenkins 관리자 권한 없이도 변경 내용을 확인할 수 있다.

## 관리 대상

- `jenkins:` — 시스템 메시지, Executor 수, Security Realm, Authorization Strategy, Node 정의
- `credentials:` — Credential 정의 (값 자체는 환경 변수나 외부 Secret으로 주입)
- `tool:` — JDK, Maven, Gradle 등 Global Tool 경로
- `unclassified:` — 플러그인별 전역 설정
- `jobs:` — Job DSL을 통한 Job 정의

## 최소 예시

```yaml
jenkins:
  systemMessage: "Configured by JCasC"
  numExecutors: 0
  securityRealm:
    local:
      allowsSignup: false
      users:
        - id: "admin"
          password: "${ADMIN_PASSWORD}"
  authorizationStrategy:
    globalMatrix:
      permissions:
        - "Overall/Administer:admin"
```

- `numExecutors: 0`으로 Controller에서 빌드가 실행되지 않도록 한다.
- 비밀번호 같은 값은 `${VAR}` 형태로 환경 변수에서 주입한다.

## Secret 처리 — 보안 관점의 핵심

- **YAML 자체에 Secret을 하드코딩하면 안 된다.** JCasC 파일은 SCM에 들어가는 것이 목적이므로, 값을 직접 적으면 저장소에 비밀값이 남는다.
- JCasC는 변수 치환을 지원한다.
  * 환경 변수: `${SOME_VAR}`
  * 파일에서 읽기: `${readFile:/run/secrets/token}`
  * base64 디코드: `${base64:...}`
- Docker Secret이나 Kubernetes Secret을 마운트하고 파일 경로로 참조하는 방식이 일반적이다.
- 즉 JCasC는 "설정의 구조"를 코드로 관리하고, "값"은 외부에서 주입하는 분리 구조를 전제로 한다.

## 운영 시 참고

- 설정을 이미 UI로 해둔 인스턴스에서는 **Export** 기능으로 현재 상태를 YAML로 뽑아낼 수 있다. 마이그레이션 출발점으로 쓸 수 있다.
- **Validate** 기능으로 적용 전 YAML 유효성을 검사할 수 있다.
- 기동 후에도 설정을 다시 읽어들이는 **Reload** 트리거가 있다.
- 모든 플러그인이 JCasC를 지원하는 것은 아니다. 지원 플러그인 목록을 확인해야 한다.
- Merge Strategy 설정으로 여러 YAML을 병합할 때의 우선순위를 정할 수 있다.

## 참고 자료

- [Jenkins 공식 문서 - Configuration as Code](https://www.jenkins.io/doc/book/managing/casc/)
- [Jenkins 프로젝트 페이지 - JCasC](https://www.jenkins.io/projects/jcasc/)
- [Configuration as Code Plugin](https://plugins.jenkins.io/configuration-as-code/)
