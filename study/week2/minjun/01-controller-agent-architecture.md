# Controller / Agent Architecture

## 핵심 개념

- Jenkins는 Controller 한 대만으로도 동작하지만, 실무 환경에서는 Controller와 Agent를 분리해서 운영한다.
- Controller는 설정 관리, Job 스케줄링, Web UI 제공, 빌드 결과 저장을 담당한다.
- Agent는 실제 빌드를 실행하는 노드이며, Controller의 지시를 받아 작업을 수행한다.
- 분리하는 이유는 크게 세 가지다.
  * 빌드는 자원을 많이 쓰고 실패 시 프로세스가 죽을 수 있는데, 이것이 Controller에서 일어나면 Jenkins 전체가 영향을 받는다.
  * 언어, OS, 라이브러리 버전이 다른 빌드 환경이 필요할 때 Agent를 목적별로 나눌 수 있다.
  * 빌드가 Controller에서 실행되면 Jenkins 파일 시스템과 Credential에 접근할 위험이 생긴다.

## 구성 요소

- Controller (구 Master)
  * Jenkins 설정, 플러그인, Job 정의, 빌드 이력을 `$JENKINS_HOME`에 보관한다.
  * 빌드를 어느 Agent에 배정할지 결정한다.
  * Web UI와 REST API를 제공한다.

- Agent (구 Slave)
  * Controller와 연결되어 빌드를 실행하는 노드다.
  * 물리 서버, VM, 컨테이너 어느 형태든 될 수 있다.
  * Java 실행 환경(JRE/JDK)과 Controller로의 네트워크 경로가 필요하다.

- Executor
  * Agent(또는 Controller) 위에서 빌드를 실행하는 슬롯이다.
  * Executor 수가 곧 해당 노드의 동시 빌드 개수다.
  * Built-in Node의 Executor를 0으로 두면 Controller에서는 빌드가 실행되지 않는다.

- Node
  * Executor를 가진 실행 단위를 통칭한다. Controller의 Built-in Node도 Node의 하나다.

- Label
  * Node에 붙이는 태그다. Pipeline에서 `agent { label 'docker' }` 처럼 지정하면 해당 라벨을 가진 Node에서 실행된다.

## Agent 연결 방식

### Inbound (Agent → Controller)

- Agent 쪽에서 Controller로 접속을 시작한다.
- Agent가 NAT 뒤나 방화벽 안에 있어 Controller가 직접 접근할 수 없을 때 사용한다.
- 전송 방식이 두 가지다.
  * TCP: 별도의 Agent용 TCP 포트를 열어야 한다. Jenkins 2.0부터 이 포트는 기본 비활성화이며, Random Port 또는 Fixed Port 중 선택한다. Fixed Port는 재시작해도 포트가 유지되어 방화벽 규칙 관리가 쉽다.
  * WebSocket: Jenkins 2.217부터 지원한다. HTTP(S) 포트를 그대로 사용하므로 별도 포트 개방이 어려운 환경에서 유리하다.
- Agent는 secret 값으로 Controller에 인증한다.

### Outbound (Controller → Agent)

- Controller가 SSH로 Agent에 접속해 Agent 프로세스를 실행한다.
- Controller가 Agent의 주소에 접근할 수 있어야 한다.
- SSH 접속용 Credential이 필요하며, 이는 Credentials Store의 **System 스코프**에 저장된다.
- Agent 쪽에 별도 설정을 거의 하지 않아도 되는 것이 장점이다.

## Dynamic Agent Provisioning

- 고정된 Agent를 계속 띄워두는 대신, 빌드가 필요할 때 Agent를 만들고 끝나면 없애는 방식이다.
- 장점
  * 빌드마다 깨끗한 환경에서 시작하므로 이전 빌드의 잔여물에 영향받지 않는다.
  * 유휴 자원을 낭비하지 않는다.
- Docker Agent
  * Pipeline에서 `agent { docker { image 'node:18' } }` 처럼 선언하면 해당 이미지로 컨테이너를 띄워 그 안에서 빌드한다.
  * 빌드마다 필요한 언어·버전을 이미지로 지정할 수 있어 Agent를 언어별로 미리 준비할 필요가 없다.
- Kubernetes Plugin을 쓰면 Pod 단위로 Agent를 동적 생성할 수도 있다.

## 보안 관점에서 본 아키텍처

- Controller와 Agent 분리는 성능 문제만이 아니라 보안 통제이기도 하다.
- 제한된 권한을 가진 사용자가 Controller에서 실행되는 Job을 설정할 수 있으면, 해당 Job을 통해 Jenkins 파일 시스템·환경 변수·Credential에 접근할 여지가 생긴다.
- 따라서 운영 환경에서는 Built-in Node의 Executor를 0으로 설정하고 모든 빌드를 Agent에서 실행하는 것이 권장된다.
- Agent 연결용 Credential(SSH Key 등)이 System 스코프에 저장되는 이유도 같은 맥락이다. 일반 Pipeline에서 그 값을 쓸 수 없도록 격리하는 것이다.

## 참고 자료

- [Jenkins 공식 문서 - Managing Nodes](https://www.jenkins.io/doc/book/managing/nodes/)
- [Jenkins 공식 문서 - Using Docker with Pipeline](https://www.jenkins.io/doc/book/pipeline/docker/)
- [Jenkins 공식 문서 - Distributed builds](https://www.jenkins.io/doc/book/scaling/)
