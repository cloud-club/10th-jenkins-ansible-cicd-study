# Controller / Agent Architecture

## 핵심 개념

- Jenkins는 분산 빌드 환경을 지원하기 위해 Controller와 Agent 구조를 사용한다.
- Controller는 Jenkins의 중심 역할을 하며, 작업 설정, 인증/인가, HTTP 요청 처리, 빌드 스케줄링, Agent 관리와 모니터링을 담당한다.
- Agent는 Controller의 요청을 받아 실제 빌드, 테스트, 배포 작업을 실행한다.
- 빌드 작업은 Jenkins 관리자보다 신뢰 수준이 낮은 사용자, 빌드 스크립트 작성자, 코드 작성자에 의해 제어될 수 있다.
- 따라서 Controller의 안정성과 보안을 위해 실제 빌드는 Built-in Node가 아니라 별도의 Agent에서 실행하는 것이 권장된다.

## 구조 예시

```text
                         Jenkins Controller
              +--------------------------------------+
              | Web UI / API                         |
              | Job Configuration                    |
              | Authentication / Authorization       |
              | Scheduling / Agent Monitoring        |
              |                                      |
              | Built-in Node                        |
              | - Executor: 0 권장                   |
              +------------------+-------------------+
                                 |
               schedules jobs / monitors agents
                                 |
          +----------------------+----------------------+
          |                                             |
          v                                             v
+----------------------+                    +----------------------+
| Agent Node A         |                    | Agent Node B         |
| Label: linux, docker |                    | Label: windows       |
| Executor: 2          |                    | Executor: 1          |
|                      |                    |                      |
| +------------------+ |                    | +------------------+ |
| | Build / Test Job | |                    | | Build / Test Job | |
| +------------------+ |                    | +------------------+ |
+----------------------+                    +----------------------+

실제 빌드 실행 위치: Agent Node
Controller 역할: Job 관리, 스케줄링, Agent 상태 관리
```

## 용어 정리

- Controller
  - Jenkins 서비스가 실행되는 중심 노드이다.
  - 웹 UI와 API 요청을 처리하고, Job을 언제 어디서 실행할지 결정한다.
  - Agent를 관리하고, 각 Agent의 상태를 모니터링한다.
  - 빌드 실행보다는 Jenkins 운영, 스케줄링, 조정 역할에 집중하도록 구성하는 것이 좋다.

- Node
  - Jenkins가 작업 실행 대상으로 인식하는 머신 또는 실행 환경이다.
  - 물리 서버, VM, 컨테이너, 클라우드 인스턴스 등이 Node가 될 수 있다.
  - Jenkins는 연결된 Node의 디스크 공간, 임시 공간, 스왑 공간, 시간 동기화, 응답 시간 등을 모니터링한다.
  - Node가 Offline 상태라는 것은 Controller가 해당 Node에 새로운 Job을 할당하지 않는 상태를 의미한다.

- Agent
  - Node에서 실행되며 Controller와 통신하는 Java 프로세스이다.
  - Controller의 요청에 따라 Pipeline 단계, Freestyle Job 등 실제 작업을 실행한다.
  - Agent가 동작하려면 Java 설치와 Controller로 연결 가능한 네트워크 경로가 필요하다.
  - 실무에서는 Node와 Agent를 비슷한 의미로 부르는 경우가 많지만, 개념적으로 Node는 실행 환경이고 Agent는 그 환경에서 실행되는 프로세스이다.

- Executor
  - Node에서 동시에 실행할 수 있는 작업 슬롯이다.
  - Executor 수가 2이면 해당 Node에서 동시에 2개의 작업을 실행할 수 있다.
  - Executor 수는 CPU, 메모리, 디스크 I/O, 네트워크 사용량, 빌드 작업의 특성을 고려해서 정해야 한다.
  - Controller의 Executor는 0으로 설정하고, 실제 작업은 Agent의 Executor에서 실행하는 구성이 권장된다.

- Label
  - Agent를 특정 기준으로 그룹화하거나 식별하기 위한 이름이다.
  - 예를 들어 `linux`, `windows`, `docker`, `high-memory`, `java17` 같은 Label을 사용할 수 있다.
  - Job은 Label Expression을 통해 특정 조건을 만족하는 Agent에서만 실행되도록 제한할 수 있다.

## Controller Isolation

- Jenkins의 기본 설정은 Built-in Node에서도 빌드를 실행할 수 있는 형태이다.
- Built-in Node는 Controller 프로세스 내부에 존재하는 노드이다.
- Built-in Node에서 실행되는 빌드는 Jenkins 프로세스와 같은 수준의 파일 시스템 접근 권한을 가진다.
- 빌드 스크립트나 테스트 코드에 문제가 있거나 악의적인 명령이 포함된 경우 Controller의 파일, 설정, 인증 정보에 영향을 줄 수 있다.
- 장기적으로는 Built-in Node에서 빌드를 실행하지 않고 별도의 Agent를 사용하는 것이 권장된다.
- Built-in Node에서 작업 실행을 막으려면 `Manage Jenkins` -> `Nodes and Clouds` -> `Built-In Node` -> `Configure`에서 Executor 수를 `0`으로 설정한다.
- 단, Built-in Node Executor를 0으로 설정한 뒤에는 작업을 실행할 Agent 또는 Cloud 구성이 반드시 필요하다.

## Agent to Controller Access Control

- Controller와 Agent는 여러 프로세스와 머신에 걸쳐 동작하는 분산 프로세스로 볼 수 있다.
- Agent는 작업 실행 중 Controller에 필요한 정보를 요청할 수 있고, 일부 동작은 Controller 측에서 수행될 수 있다.
- Built-in Node를 사용하지 않는 것만으로는 Controller 보안이 완전히 보장되지 않는다.
- 악의적인 사용자가 Agent 프로세스를 장악하면 Controller에 민감한 정보를 요청하거나 위험한 명령 실행을 시도할 수 있다.
- Jenkins는 이를 막기 위해 Agent to Controller Access Control 기능을 제공한다.
- 이 기능은 Agent 프로세스가 Controller에 악의적인 명령을 보내지 못하도록 제한한다.
- Jenkins 2.326부터는 항상 활성화되어 있으며, 이전 버전에서도 기본적으로 활성화되어 있다.
- 공식 문서에서는 이 설정을 비활성화하지 않는 것을 강하게 권장한다.

## Agent 사용 방식

- Agent는 Controller와 별도의 머신, VM, 컨테이너, 클라우드 환경에서 실행할 수 있다.
- 프로젝트마다 필요한 운영체제, JDK, Docker, 빌드 도구, 테스트 도구가 다를 수 있으므로 Agent를 분리하면 빌드 환경을 더 유연하게 구성할 수 있다.
- 여러 Agent를 사용하면 빌드를 병렬로 실행할 수 있어 Jenkins 전체 워크로드를 분산할 수 있다.
- 특정 Job은 Label을 사용해 특정 Agent에서만 실행되도록 제한할 수 있다.

## Agent Usage 설정

- Jenkins Agent 설정에는 해당 Node에 Job을 어떻게 배정할지 정하는 Usage 옵션이 있다.
- `Use this node as much as possible`
  - Jenkins가 가능한 경우 해당 Node에 자유롭게 Job을 배정한다.
  - 범용 Agent에 적합하다.
- `Only build jobs with label expressions matching this node`
  - Job의 Label Expression이 해당 Node의 Label과 일치할 때만 작업을 실행한다.
  - 특정 도구, OS, 하드웨어, 보안 권한이 필요한 전용 Agent에 적합하다.

## Node 유형

- Built-in Node
  - Controller 프로세스 내부에 존재하는 기본 Node이다.
  - 초기 학습이나 간단한 테스트에는 편리하지만, 보안, 성능, 확장성 측면에서 운영 환경에는 권장되지 않는다.
  - Built-in Node에서 작업 실행을 비활성화하려면 Executor 수를 0으로 설정한다.

- 정적 Agent
  - 관리자가 미리 등록해 둔 고정 Agent이다.
  - 물리 서버, VM, 고정 컨테이너 등으로 구성할 수 있다.
  - 항상 준비되어 있어야 하는 빌드 환경이나 특정 도구가 설치된 전용 환경에 적합하다.

- 동적 Agent 또는 Cloud Agent
  - 필요할 때 생성되고, 작업이 끝나면 제거되는 Agent이다.
  - Kubernetes, Docker, 클라우드 VM 등과 연동해 사용할 수 있다.
  - 빌드 수요가 시간대별로 크게 달라지거나, 깨끗한 일회성 빌드 환경이 필요한 경우 유용하다.

## Executor 구성 기준

- Executor는 Node에서 동시에 실행할 수 있는 작업 수를 결정한다.
- Executor 수가 많을수록 동시에 많은 작업을 실행할 수 있지만, Node의 리소스 경합도 커진다.
- 가장 보수적인 구성은 Node당 Executor 1개를 사용하는 것이다.
- 작업이 가볍고 독립적이라면 CPU 코어 수에 맞춰 Executor를 늘릴 수 있다.
- 여러 Executor를 둘 때는 CPU 사용률, 메모리 사용량, 디스크 I/O, 네트워크 I/O, 빌드 대기열을 함께 모니터링해야 한다.
- Controller는 빌드 실행 리소스를 사용하지 않도록 Executor를 0으로 설정하는 것이 안정성과 성능 측면에서 유리하다.

## Controller와 Agent 연결 방식

- SSH 연결
  - Controller가 Agent 서버에 SSH로 접속해 Agent 프로세스를 실행하는 방식이다.
  - Agent 서버에는 SSH 서버가 열려 있어야 하고, Controller에는 SSH 인증 정보가 등록되어 있어야 한다.
  - 연결되면 Jenkins가 Agent 프로세스를 자동으로 시작한다.
  - 일반적인 Linux Agent 구성에서 많이 사용된다.

- Inbound 연결
  - Agent가 Controller로 먼저 접속하는 방식이다.
  - Controller가 Agent 서버에 직접 접근하기 어려운 방화벽 또는 NAT 환경에서 유용하다.
  - Agent 서버에서 `java -jar agent.jar ...` 형태로 Agent 프로세스를 실행한다.
  - 테스트나 일시적인 Agent 연결에는 수동 실행을 사용할 수 있다.
  - Windows 환경에서는 Agent를 Windows Service로 등록해 서버 재부팅 후에도 자동으로 실행되게 구성할 수 있다.

- Inbound HTTP 연결
  - Agent가 HTTP 또는 HTTPS를 통해 Controller로 접속하는 방식이다.
  - 별도의 Agent용 TCP 포트를 열기 어려운 환경에서 유용하다.
  - 실제 실행 명령은 Jenkins의 해당 Agent 설정 화면에서 확인할 수 있다.

- 사용자 지정 스크립트
  - Jenkins가 제공하는 기본 연결 방식만으로 부족할 때 직접 스크립트를 작성해 Agent를 실행하는 방식이다.
  - 핵심은 스크립트가 최종적으로 Jenkins Agent 프로세스를 실행해야 한다는 점이다.

## 확장 관점

- Jenkins 사용량 증가는 수직적 성장과 수평적 성장으로 나눌 수 있다.
- 수직적 성장은 하나의 Controller에 구성된 Job 수, 빌드 빈도, 사용자 수가 증가하는 것이다.
- 수평적 성장은 새로운 팀이나 프로젝트를 수용하기 위해 Jenkins Controller를 추가하는 것이다.
- 하나의 Controller가 빌드 실행과 스케줄링을 모두 담당하면 프로젝트 수가 늘어날수록 리소스가 부족해질 가능성이 높다.
- Agent를 분리하면 Controller는 HTTP 요청 처리, Job 관리, 빌드 스케줄링에 집중하고 실제 빌드 실행은 Agent에 위임할 수 있다.
- 이 구조는 Controller의 부하를 줄이고, 다양한 빌드 환경을 제공하며, Jenkins 인프라를 더 유연하게 확장할 수 있게 한다.

## 확장 전략 선택 시 고려할 점

- 분산 빌드 시스템을 운영할 리소스가 있는지 확인해야 한다.
- 가능하면 Controller와 별도로 실행되는 전용 빌드 Node를 구성하는 것이 좋다.
- 여러 Controller를 운영할 경우 각 Controller의 플러그인 업데이트, Jenkins 코어 업그레이드, 백업, 보안 설정을 별도로 관리해야 한다.
- 중요한 프로젝트는 별도의 Controller로 분리해 Controller 장애의 영향을 줄일 수 있다.
- Controller에 Job이 많을수록 업그레이드나 장애 복구 후 Jenkins 시작 시간이 길어질 수 있다.
- 폴더와 뷰를 사용해 Job을 정리하면 시작 시 렌더링해야 하는 Job 수를 줄이는 데 도움이 된다.

## Controller와 Executor 수 추정

- 공식 문서의 예시는 다음 전제를 기준으로 한다.
  - Jenkins Controller에 5개의 CPU 코어가 있다.
  - Job 100개당 Controller CPU 코어 1개를 할당한다.
  - Controller 1개당 최대 500개의 Job을 기준으로 한다.
  - 팀은 40명 단위로 나뉜다고 가정한다.

- 구성된 Job 수를 알고 있을 때 필요한 Controller와 Executor 수를 추정하는 공식은 다음과 같다.

```text
controllers = number of jobs / 500
executors = number of jobs * 0.03
```

- 개발자 수를 기준으로 필요한 Job 수, Controller 수, Executor 수를 추정하는 공식은 다음과 같다.

```text
number of jobs = number of developers * 3.333
number of controllers = number of jobs / 500
number of executors = number of jobs * 0.03
```

- 위 공식은 초기 산정을 위한 기준이며, 실제 운영에서는 Queue 길이, Executor 사용률, Controller CPU/Memory, 빌드 시간, Agent 리소스 사용량을 보고 조정해야 한다.

## 참고 자료

- [Jenkins 공식 문서 - Controller Isolation](https://www.jenkins.io/doc/book/security/controller-isolation/)
- [Jenkins 공식 문서 - Using Jenkins agents](https://www.jenkins.io/doc/book/using/using-agents/)
- [Jenkins 공식 문서 - Managing Nodes](https://www.jenkins.io/doc/book/managing/nodes/)
- [Jenkins 공식 문서 - Architecting for Scale](https://www.jenkins.io/doc/book/scaling/architecting-for-scale/)
