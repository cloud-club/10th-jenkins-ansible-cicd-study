# Week 1 — Architecture, Infrastructure & Security

## 1. Controller / Agent Architecture
- Controller: 설정, 잡 스케줄링, UI 제공
- Agent: 실제 빌드 실행
- 연결 방식: inbound(에이전트→컨트롤러, JNLP) vs outbound(컨트롤러→에이전트, SSH)

## 2. Configuration as Code (JCasC)
- UI 설정을 jenkins.yaml로 선언
- SCM에 넣어 변경 이력 추적 및 롤백 가능
- 설정은 컨트롤러 기동 시 적용

## 3. Security & Credentials

### Credentials Store
- Kind: Secret text / Username+Password / SSH Key / Secret file
- Scope: System(에이전트 연결 전용) / Global / Folder 단위

### 실습: Secret Masking 우회

Secret text `test-secret` 등록 후 아래 파이프라인 실행.

```groovy
withCredentials([string(credentialsId: 'test-secret', variable: 'SECRET')]) {
    sh 'echo "1. plain:  $SECRET"'
    sh 'echo "2. base64: $(echo $SECRET | base64)"'
    sh 'echo "3. rev:    $(echo $SECRET | rev)"'
    sh 'echo "4. cut:    $(echo $SECRET | cut -c1-6)"'
}
```

| 출력 방식 | 결과 | 마스킹 |
|---|---|---|
| `echo $SECRET` | `****` | O |
| base64 | `****Cg==` | 부분 |
| rev | `4321terceSyM` | X |
| cut -c1-6 | `MySecr` | X |

- base64는 Jenkins가 지원 패턴으로 처리해 마스킹됨. 다만 echo가 붙인 개행 때문에 마지막 블록 `Cg==`가 남음
- rev는 지원 패턴에 없어 전량 노출

### 결론
마스킹은 실수 방지 장치이지 접근 통제가 아니다.
변형 방법은 무한히 만들 수 있으므로, 실제 통제 지점은
"누가 Jenkinsfile을 수정할 수 있는가" = Matrix 기반 권한 설정이다.
