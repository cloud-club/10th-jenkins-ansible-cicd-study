# Multi-Host Execution & Orchestration

## strategy와 forks

호스트마다 대기 시간을 엇갈리게 준 playbook으로 `linear`/`free` 전략과 `forks` 값을 조합해 총 소요 시간을 측정했다. apt 같은 네트워크 작업은 시간이 흔들리므로 `sleep`만 썼다.

| | Step 1 | Step 2 | 합계 |
|---|---|---|---|
| node1 | 5초 | 1초 | 6초 |
| node2 | 3초 | 3초 | 6초 |
| node3 | 1초 | 5초 | 6초 |

| | 전략 / 병렬 | 예상 | 실측 |
|---|---|---|---|
| A | linear, forks=5 | 10초 | 11초 |
| B | free, forks=5 | 6초 | 7초 |
| C | linear, forks=1 | 18초 | 20초 |
| D | free, forks=1 | 18초 | 19초 |

- linear는 단계마다 가장 느린 호스트를 기다린다(5 + 5). free는 호스트마다 자기 속도로 끝까지 간다(모두 6초). B가 A보다 4초 빠르다.
- forks가 1이면 전략과 무관하게 한 번에 한 대씩이라 free의 이점이 사라진다(C와 D가 거의 같다).
- 실측이 예상보다 1~2초씩 큰 것은 SSH 연결 수립 비용이다.

### 완료 순서

시간만으로는 free의 동작이 안 보이므로, 각 서버가 자기 이름과 단계를 출력하게 해 끝난 순서를 봤다. Step 2를 모두 1초로 통일했다.

```
linear: node3-step1 node2-step1 node1-step1 node3-step2 node1-step2 node2-step2
free:   node3-step1 node3-step2 node2-step1 node2-step2 node1-step1 node1-step2
```

linear는 Step 1 세 대가 전부 끝난 뒤에 Step 2가 시작된다. 가장 느린 node1이 Step 1을 끝낼 때까지 아무도 Step 2로 넘어가지 못한다. free는 node3이 node1의 Step 1이 끝나기도 전에 Step 2까지 마친다.

free는 빠르지만 어떤 서버가 어느 단계에 있는지 보장하지 않는다. 롤링 배포에서 "LB에서 빼기 → 배포 → 확인 → 넣기" 순서가 서버마다 제각각이 되면 곤란하므로, 04는 linear에 `serial`을 조합한다.

## throttle, run_once, delegate_to

```
$ ansible-playbook orch_ctrl.yml ... | grep -E 'Throttled step -'
Throttled step ---------------------------------------------------------- 4.46s
```

- **throttle**: forks가 5인데도 `throttle: 1`을 건 task는 한 번에 한 대씩 실행됐다(2초 × 2대 = 4.46초). forks는 전체 병렬 수를 정하고, throttle은 특정 task 하나만 제한한다. DB 마이그레이션처럼 동시에 돌면 안 되는 작업에 쓴다.
- **run_once**: `hostname`을 node1에서 한 번만 실행했는데 결과는 node1과 node2 둘 다 공유했다.

```
"msg": "node1 sees result from node1"
"msg": "node2 sees result from node1"
```

- **delegate_to**: task는 node1·node2에 대해 각각 실행되지만 실제 명령은 node3에서 돈다.

```
ok: [node1 -> node3(127.0.0.1)]
"msg": "node1 via node3: ok 1.0"
```

delegate_to에서 네트워크 경로 차이가 드러났다. Ansible은 node3에 컨트롤 노드 기준 주소(127.0.0.1:2223)로 접속했는데, node3 안에서 실행된 curl은 컨테이너 네트워크 이름(node1)으로 접근해 `ok 1.0`을 받았다. 같은 헬스체크라도 어디서 보느냐에 따라 경로가 다르다. 04의 헬스체크를 LB에서 하는 이유가 이것이다. 사용자 트래픽이 지나가는 경로와 같은 경로로 확인해야 의미가 있다.

## any_errors_fatal

node2에서만 일부러 실패시키고, 설정 하나로 나머지 서버의 동작이 어떻게 달라지는지 봤다.

| any_errors_fatal | node1 | node2 | node3 |
|---|---|---|---|
| false (기본값) | ok=2 | failed=1 | ok=2 |
| true | ok=1 | failed=1 | ok=1 |

- **false**: node2만 멈추고 node1·node3은 Step 2까지 간다.
- **true**: node2가 실패하는 순간 전체가 Step 1에서 멈춘다.

기본값은 일부 서버만 새 버전인 채로 배포가 끝날 수 있다는 뜻이다. `max_fail_percentage`는 `serial`과 묶여야 의미가 있어 04에서 다룬다.

## 참고 자료

- [Ansible - Controlling playbook execution: strategies and more](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_strategies.html)
- [Ansible - Controlling where tasks run: delegation and local actions](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_delegation.html)
