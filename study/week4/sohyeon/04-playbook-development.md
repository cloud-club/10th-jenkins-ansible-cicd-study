## **4. Playbook Development**

### 4-1) Play / Task / Module 기반 Playbook 구조 이해

```yaml
Playbook
 └── Play
      ├── 대상 hosts
      ├── Task
      │    └── Module
      ├── Task
      │    └── Module
      └── Task
           └── Module
```

**플레이북 구조**

| playbook | 전체 목표를 달성하기 위해 Ansible이 위에서 아래로 수행하는 작업의 순서를 정의한 play 목록 |
| --- | --- |
| play | 인벤토리의 managed node에 매핑되는 task의 정렬된 목록 |
| task | Ansible이 실행할 작업을 정의하는 단일 모듈에 대한 참조 |
| module | managed node에서 실행되는 코드 또는 바이너리의 단위 |

```yaml
# playbook.yaml

- name: My first play          # [Play] Play의 이름
  hosts: myhosts               # [Play] 대상 노드 매핑
  tasks:                       # [Play] Task들의 목록 시작
    - name: Ping my hosts      # [Task 1] Task의 이름
      ansible.builtin.ping:    # [Module 1] 사용된 모듈 (ansible.builtin.ping)

    - name: Print message      # [Task 2] Task의 이름
      ansible.builtin.debug:   # [Module 2] 사용된 모듈 (ansible.builtin.debug)
        msg: Hello world       # [Module 2] 모듈에 전달되는 매개변수
```

```yaml
ansible-playbook -i inventory.ini playbook.yaml
```

```yaml
PLAY [My first play] ****************************************************************************

TASK [Gathering Facts] **************************************************************************
ok: [192.0.2.50]
ok: [192.0.2.51]
ok: [192.0.2.52]

TASK [Ping my hosts] ****************************************************************************
ok: [192.0.2.50]
ok: [192.0.2.51]
ok: [192.0.2.52]

TASK [Print message] ****************************************************************************
ok: [192.0.2.50] => {
    "msg": "Hello world"
}
ok: [192.0.2.51] => {
    "msg": "Hello world"
}
ok: [192.0.2.52] => {
    "msg": "Hello world"
}

PLAY RECAP **************************************************************************************
192.0.2.50: ok=3    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
192.0.2.51: ok=3    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
192.0.2.52: ok=3    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0
```

**플레이북 실행**

- “Gathering Facts” task가 암시적으로 실행되며 Ansible이 플레이북에서 사용할 수 있는 인벤토리 정보를 수집한다.
- 각 task의 상태가 ok 임을 확인하여 성공적으로 실행되었음을 확인할 수 있다.
- Play recap에서는 호스트 별로 플레이북 내 모든 task의 결과를 요약한다.

### 4-2) `vars`, `register`, `when`, `loop`을 활용한 실행 흐름 구성

**Ansible의 변수(vars)**

- Ansible은 리스트와 딕셔너리를 포함한 표준 YAML 구문으로 변수를 생성할 수 있다.
- 변수는 플레이북, 인벤토리, 재사용 가능한 파일이나 역할, 명령줄에서 정의할 수 있다.
- 플레이북 실행 중 작업의 반환값을 새 변수로 등록(register)하여 변수를 생성할 수도 있다.
- 변수를 생성한 후에는 모듈 인자, 조건문(when), 템플릿, 반복문(loop)에서 사용할 수 있다.
- Simple variables
    - 표준 YAML 구문을 사용하여 단순 변수를 정의할 수 있다.
        
        ```yaml
        remote_install_path: /opt/my_app_config
        ```
        
        ```yaml
        ansible.builtin.template:
          src: foo.cfg.j2
          dest: '{{ remote_install_path }}/foo.cfg'
        ```
        
        - 값이 {{ foo }}로 시작하는 경우, 전체 표현식을 따옴표로 감싸야 한다.
            
            ```yaml
            app_path: "{{ base_path }}/22"
            ```
            
- List variables
    - 하나의 변수에 여러 값을 저장한다.
        
        ```yaml
        region:
          - northeast
          - southeast
          - midwest
        ```
        
        ```yaml
        region: "{{ region[0] }}" # 결과: "northeast"
        ```
        
- Dictionary variables
    - 키-값 쌍으로 데이터를 저장한다.
        
        ```yaml
        foo:
          field1: one
          field2: two
        ```
        
- 변수 결합
    - set_fact 모듈을 사용한다.
        
        ```yaml
        vars:
          list1:
            - apple
            - banana
            - fig
          list2:
            - peach
            - plum
            - pear
        tasks:
          - name: Combine list1 and list2 into a merged_list var
            ansible.builtin.set_fact:
              merged_list: "{{ list1 + list2 }}"
        ```
        
- 딕셔너리 결합
    - combine 필터를 사용한다.
        
        ```yaml
        vars:
          dict1:
            name: Leeroy Jenkins
            age: 25
          dict2:
            location: Galway
            country: Ireland
        tasks:
          - name: Combine dict1 and dict2
            ansible.builtin.set_fact:
              merged_dict: "{{ dict1 | ansible.builtin.combine(dict2) }}"
        ```
        
- 변수 등록하기
    - `register` 키워드를 사용하여 task의 실행 결과를 변수로 저장하고, 이후 다른 작업에서 활용할 수 있다.
        
        ```yaml
        - hosts: web_servers
          tasks:
            - name: Run a shell command and register its output as a variable
              ansible.builtin.shell: /usr/bin/foo
              register: foo_result
              ignore_errors: true
        
            - name: Run a shell command using output of the previous task
              ansible.builtin.shell: /usr/bin/bar
              when: foo_result.rc == 5
        ```
        
    - 다중 변수 등록 (Version 2.21 신기능)
        - register 에서 맵 형태로 여러 변수를 프로젝션할 수 있으며, _task.result를 사용하여 작업 결과 데이터에 접근한다.
    - 등록된 변수는 메모리에 저장되며 플레이북이 실행되는 동안 해당 호스트에서 계속 유효하다.
    - 작업이 실패하거나 건너뛰어져도 상태 정보가 변수에 등록된다.
    - `loop`와 함께 사용하면 각 항목별 시행 결과가 results라는 리스트 속성에 저장된다.
- 변수 우선순위
    - 동일한 변수가 여러 곳에 정의된 경우 Ansible은 정해진 우선순위 규칙에 따라 값을 결정한다.
    - 복잡성을 줄이기 위해서는 변수를 한 곳에서만 명확하게 정의하는 것이 좋다.

**Loops**

- 단순 목록 반복
    - 반복되는 작업은 단순한 문자열 목록을 순회하는 표준 루프로 작성한다.
    - 작업에 직접 목록을 정의할 수도 있다.
        
        ```yaml
        - name: Add several users
          ansible.builtin.user:
            name: "{{ item }}"
            state: present
            groups: "wheel"
          loop:
            - testuser1
            - testuser2
        ```
        
    - 변수 파일이나 플레이의 vars 섹션에 목록을 정의한 다음, 작업에서 해당 목록의 이름을 참조할 수 있다.
        
        ```yaml
        loop: "{{ somelist }}"
        ```
        
    - 일부 플러그인의 매개변수에는 목록을 직접 전달할 수도 있으며, 이는 작업에 루프를 돌리는 것보다 효율적이다.
- 해시 목록 반복
    - 해시 목록이 있는 경우 루프 내에서 하위 키를 참조할 수 있다.
    - 조건문(`when`)을 루프와 조합할 때, `when:` 문은 각 항목별로 개별 처리된다.
        
        ```yaml
        - name: Add several users
          ansible.builtin.user:
            name: "{{ item.name }}"
            state: present
            groups: "{{ item.groups }}"
          loop:
            - { name: 'testuser1', groups: 'wheel' }
            - { name: 'testuser2', groups: 'root' }
        ```
        
- 딕셔너리 반복
    - 딕셔너리를 루프 처리하려면 `dict2items` 필터를 사용한다.
        
        ```yaml
        - name: Using dict2items
          ansible.builtin.debug:
            msg: "{{ item.key }} : {{ item.value.ip_address }} {{ item.value.role }}"
          loop: "{{ server_configs | dict2items }}"
          vars:
            server_configs:
              web_01:
                ip_address: "10.1.1.50"
                role: "frontend"
              db_01:
                ip_address: "10.1.1.100"
                role: "backend_db"
        ```
        
- 루프 결과를 변수로 등록
    - 루프의 실행 결과를 변수로 등록할 수 있다.
    - 루프와 함께 `register`를 사용하면 변수에 모듈의 모든 응답 목록인 `results` 속성이 포함된다.
        
        ```yaml
        - name: Register loop output as a variable
          ansible.builtin.shell: "echo {{ item }}"
          loop:
            - "one"
            - "two"
          register: echo
        ```
        

**조건문**

- `when`을 사용한 기본 조건문
    - 이중 중괄호 없이 작성하는 순수 Jinja2 표현식
    - 태스크나 플레이북을 실행할 때 Ansible은 모든 호스트에 대해 이 테스트를 평가한다.
    - 테스트를 통과한(True 값을 반환하는) 모든 호스트에서 해당 태스크가 실행된다.
        
        ```yaml
        tasks:
          - name: Configure SELinux to start mysql on any port
            ansible.posix.seboolean:
              name: mysql_connect_any
              state: true
              persistent: true
            when: ansible_selinux.status == "enabled" # 모든 변수는 이중 중괄호 없이 조건문에서 직접 사용할 수 있습니다.
        ```
        
- ansible_facts 기반 조건문
    - 팩트(IP 주소, 운영체제, 파일 시스템 상태 등 개별 호스트의 속성)를 기준으로 태스크를 실행하거나 건너뛸 수 있다.
        
        ```yaml
        tasks:
          - name: Shut down Debian flavored systems
            ansible.builtin.command: /sbin/shutdown -t now
            when: ansible_facts['os_family'] == "Debian"
        ```
        
- 등록된 변수 기반 조건문
    - 이전 태스크의 실행 결과를 `register` 키워드로 변수에 저장하고, 이를 조건문에서 활용할 수 있다.
        
        ```yaml
        - name: Test play
          hosts: all
          tasks:
            - name: Register a variable
              ansible.builtin.shell: cat /etc/motd
              register: motd_contents
        
            - name: Use the variable in conditional statement
              ansible.builtin.shell: echo "motd contains the word hi"
              when: motd_contents.stdout.find('hi') != -1
        ```
        
- 변수 기반 조건문
    - 플레이북이나 인벤토리에 정의된 변수를 기준으로 조건문을 생성할 수 있다.
        
        ```yaml
        vars:
          epic: true
          monumental: "yes"
        
        tasks:
          - name: Run the command if "epic" or "monumental" is true
            ansible.builtin.shell: echo "This certainly is epic!"
            when: epic or monumental | bool
        
          - name: Run the command if "epic" is false
            ansible.builtin.shell: echo "This certainly isn't epic!"
            when: not epic
        ```
        
- 반복문에서의 조건문
    - `when` 문을 `loop`와 결합하면 Ansible은 반복되는 각 항목별로 조건을 개별 평가한다.
        
        ```yaml
        tasks:
          - name: Run with items greater than 5
            ansible.builtin.command: echo {{ item }}
            loop: [0, 2, 4, 6, 8, 10]
            when: item > 5
        ```
        
    - 반복 대상 목록이 정의되어 있지 않을 때 전체 태스크를 건너뛰려면 `| default([])` 필터를 사용한다.
        
        ```yaml
        - name: Skip the whole task when a loop variable is undefined
          ansible.builtin.command: echo {{ item }}
          loop: "{{ mylist|default([]) }}"
          when: item > 5
        ```
        

### 4-3) `notify` / `handlers`를 활용한 변경 기반 작업 실행

**`notify`** 

- 작업(Task) 또는 블록(Block)이 실행된 후 결과 상태가 'changed=True'를 반환할 때 알림을 보낼 대상 핸들러(Handler) 목록을 지정한다.
- 사용 예시
    - **`changed_when`**
        - 작업의 기본 'changed' 상태 판단 기준을 사용자 정의 조건식으로 재정의한다.
        - `notify`가 호출되는 조건('changed=True')을 인위적으로 제어할 때 조합할 수 있다.
    - **`force_handlers`**
        - 플레이 도중 다른 작업에서 오류가 발생하더라도, 이미 이전 작업에서 알림(`notify`)을 받은 핸들러가 있다면 강제로 실행되도록 보장한다.
        - 단, 플레이 자체의 오류/중단 시에는 작동하지 않는다.

**`handlers`** 

- `notify`에 의해 알림을 받은 경우에만 실행되는 작업 섹션이다.
- 일반적인 작업 흐름 중에는 실행되지 않으며, 각 작업 섹션이 모두 완료된 후에 알림을 받은 핸들러들만 모아서 실행된다.
- 작업이 변경(changed)을 일으켜 핸들러에 알림을 보냈더라도, 이후 작업 중 실패가 발생하면 기본적으로 핸들러가 실행되지 않는다.
    - 구성 파일은 변경되었으나 서비스는 재시작되지 않는 등의 상태 불일치 문제가 발생할 수 있다.

### 4-4) `pre_tasks`, `tasks`, `post_tasks` 실행 순서 이해

**Continuous Delivery**

- 소프트웨어 애플리케이션에 대한 업데이트를 자주 제공하는 것
- 더 자주 업데이트하여 특정 정해진 기간을 기다릴 필요가 없고, 조직이 변화에 대응하는 프로세스를 더욱 잘 다르게 된다.
- 매시간 단위로, 혹은 승인된 코드 변경이 있을 때마다 서비스 중단 없이(zero-downtime) 빠르게 업데이트를 적용할 수 있는 도구가 필요할 때
- 웹 애플리케이션의 정교한 무중단 롤링 업그레이드 오케스트레이션 과정

```yaml
pre_tasks -> (roles) -> tasks -> post_tasks
```

- **`pre_tasks`**
    - 메인 역할(`roles`)이나 일반 작업(`tasks`)이 실행되기 전에 가장 먼저 수행되는 작업
- **`tasks`**
    - 플레이에서 실행되는 메인 작업 목록
        - 메인 업데이트 및 구성 작업(예: 웹 애플리케이션 코드 업데이트, 서버 설정 변경 등)을 수행한다.
    - `roles` 이후 및 `post_tasks` 이전에 실행
- **`post_tasks`**
    - `tasks` 섹션 이후에 실행되는 작업 목록
    - 메인 역할/작업이 완료된 후에 실행되는 마무리 작업

```yaml
# rolling_update.yml

pre_tasks:
- name: disable nagios alerts for this host webserver service
  nagios:
    action: disable_alerts
    host: "{{ inventory_hostname }}"
    services: webserver
  delegate_to: "{{ item }}"
  loop: "{{ groups.monitoring }}"

- name: disable the server in haproxy
  shell: echo "disable server myapplb/{{ inventory_hostname }}" | socat stdio /var/lib/haproxy/stats
  delegate_to: "{{ item }}"
  loop: "{{ groups.lbservers }}"
```

1. pre_tasks
    - 대상 서버에 실제 업데이트 작업을 적용하기 전에 서비스 영향도를 없애기 위해 사전 작업을 진행한다.
    - 안전하게 web01을 업데이트할 준비
        - Nagios 모니터링 알림 비활성화
        - HAProxy 로드 밸런싱 풀에서 해당 웹 서버를 제거(Disable)하여 트래픽 차단
2. roles / tasks
    - 트래픽이 차단된 상태에서 대상 서버의 시스템 구성을 변경하고 코드를 업데이트
    - 실제 업데이트 진행
        - `common`, `base-apache`, `web` 역할을 재적용하여 애플리케이션 업데이트 진행
3. post_tasks
    - 업데이트가 정상적으로 완료된 후 서버를 다시 정상 서비스 상태로 복구
        - HAProxy 로드 밸런싱 풀에 웹 서버를 다시 투입(Enable)
        - Nagios 모니터링 알림 재활성화

### 4-5) `block`, `rescue`, `always`를 활용한 예외 처리 및 복구 흐름

**block**

- 블록은 태스크들의 논리적 그룹을 생성한다.
- 블록 내의 모든 태스크는 블록 수준에서 적용된 지시문(directives)을 상속받는다.
- 지시문은 블록 자체에 영향을 주지 않으며, 블록에 둘러싸인 태스크에만 상속된다.
    - 예를 들어 `when` 문은 블록 자체가 아니라 블록 내부의 태스크들에 적용된다.
    
    ```yaml
    tasks:
      - name: Install, configure, and start Apache
        when: ansible_facts['distribution'] == 'CentOS'
        block:
          - name: Install httpd and memcached
            ansible.builtin.yum:
              name:
                - httpd
                - memcached
              state: present
          - name: Apply the foo config template
            ansible.builtin.template:
              src: templates/src.j2
              dest: /etc/foo.conf
          - name: Start service bar and enable it
            ansible.builtin.service:
              name: bar
              state: started
              enabled: True
        become: true
        become_user: root
        ignore_errors: true
    ```
    
    - `rescue` 및 `always` 섹션이 포함된 블록을 사용하여 태스크 에러에 대한 Ansible의 반응을 제어할 수 있다.
        
        ```yaml
                      block
                        │
                  메인 작업 실행
                        │
                ┌───────┴───────┐
                │               │
               성공            실패
                │               │
                │               ▼
                │            rescue
                │          복구 작업 수행
                │               │
                └───────┬───────┘
                        ▼
                      always
                 무조건 실행되는 작업
        ```
        
        - `rescue` 블록은 블록 내의 이전 태스크가 실패했을 때 실행할 태스크를 지정한다.
        - Ansible은 태스크가 'failed' 상태를 반환한 후에만 `rescue` 블록을 실행한다.
            
            ```yaml
            block 시작
                │
                ├─ task 1 → 성공
                │
                ├─ task 2 → FAILED
                │
                ├─ task 3 → 실행 안 함
                │
                ▼
              rescue
                │
                └─ 복구 작업 실행
            ```
            
            ```yaml
            tasks:
              - name: Handle the error
                block:
                  - name: Print a message
                    ansible.builtin.debug:
                      msg: 'I execute normally'
                  - name: Force a failure
                    ansible.builtin.command: /bin/false
                  - name: Never print this
                    ansible.builtin.debug:
                      msg: 'I never execute, due to the above task failing, :-('
                rescue:
                  - name: Print when errors
                    ansible.builtin.debug:
                      msg: 'I caught an error, can do stuff here to fix it, :-)'
            ```
            
        - `always`섹션의 태스크는 이전 블록 태스크들의 상태와 관계없이 항상 실행된다.
            
            ```yaml
            block
              │
              ├─ task 1 → 성공
              ├─ task 2 → 실패
              └─ task 3 → 실행 X
                   │
                   ▼
                 always
                   │
                   └─ 실행 O
            
            block
              │
              ├─ task 1 → 성공
              ├─ task 2 → 성공
              └─ task 3 → 성공
                   │
                   ▼
                 always
                   │
                   └─ 실행 O
            ```
            
            ```yaml
            tasks:
              - name: Always do X
                block:
                  - name: Print a message
                    ansible.builtin.debug:
                      msg: 'I execute normally'
                  - name: Force a failure
                    ansible.builtin.command: /bin/false
                  - name: Never print this
                    ansible.builtin.debug:
                      msg: 'I never execute :-('
                always:
                  - name: Always do this
                    ansible.builtin.debug:
                      msg: "This always executes, :-)"
            ```
            
        - `block` 내의 태스크 중 하나라도 failed를 반환하면, `rescue` 섹션이 에러를 복구하기 위한 태스크를 실행한다.
        - `always` 섹션은 `block` 및 `rescue` 섹션의 결과와 관계없이 실행된다.
        - `rescue` 부분에 있는 태스크들을 위해 두 가지 변수를 제공한다.
            - `ansible_failed_task`: failed 상태를 반환하여 복구(rescue)를 트리거한 태스크 정보
            - `ansible_failed_result`: 복구를 트리거한 실패한 태스크의 캡처된 반환 결과 (`register` 키워드를 사용했을 때 얻는 변수와 동일)
            
            ```yaml
            tasks:
              - name: Attempt and graceful roll back demo
                block:
                  - name: Do Something
                    ansible.builtin.shell: grep $(whoami) /etc/hosts
                  - name: Force a failure, if previous one succeeds
                    ansible.builtin.command: /bin/false
                rescue:
                  - name: All is good if the first task failed
                    when: ansible_failed_task.name == 'Do Something'
                    ansible.builtin.debug:
                      msg: All is good, ignore error as grep could not find 'me' in hosts
                  - name: All is good if the second task failed
                    when: "'/bin/false' in ansible_failed_result.cmd | d([])"
                    ansible.builtin.fail:
                      msg: It is still false!!!
            ```
            

### 4-6) `tags`, `-limit`을 활용한 선택적 실행

**tags**

- 대규모 플레이북을 실행할 때 전체를 실행하는 대신 특정 부분만 선별하여 실행하거나 건너뛸 수 있다.
- 태스크 개별 단위뿐만 아니라 블록, 플레이, 역할, 임포트/인클루드 수준에서 `tags` 키워드를 정의할 수 있다.
- `tags` 키워드는 대상 작업에 태그를 정의하고 추가하는 역할만 수행하며, 실행할 작업을 결정하는 것은 플레이북 실행 시 명령줄에서 이루어진다.
- CLI 실행 시 `-tags` 또는 `-skip-tags` 옵션을 사용하여 실행 대상 태그를 지정하거나 제외한다.

```yaml
# configuration 또는 packages 태그가 포함된 작업만 실행
ansible-playbook example.yml --tags "configuration,packages"

# packages 태그가 포함된 작업을 제외하고 실행
ansible-playbook example.yml --skip-tags "packages"
```

- 태그의 적용 및 상속 구조
    - 개별 태스크: 태스크 단위로 하나 이상의 태그를 지정할 수 있다.
        
        ```yaml
        tasks:
          - name: Install the servers
            ansible.builtin.yum:
              name:
                - httpd
                - memcached
              state: present
            tags:
              - packages
              - webservers
        ```
        
    - 블록 및 플레이: 상위 수준에서 지정된 태그는 하위 태스크 전체에 상속된다.
        
        ```yaml
        - hosts: all
          tags: ntp
          tasks:
            - name: Install ntp
              ansible.builtin.yum:
                name: ntp
                state: present
        ```
        
    - 임포트 vs 인클루드
        - 정적 임포트(`import_*`): 지정한 태그가 임포트 대상 파일/역할 내부의 모든 태스크로 상속된다.
            
            ```yaml
            import_tasks [tag: web]
                   │
                   ├─ task A ← web
                   ├─ task B ← web
                   └─ task C ← web
            ```
            
        - 동적 인클루드(`include_*`): 기본적으로 태그 상속이 적용되지 않으며, 태그는 인클루드 태스크 자체에만 적용된다. (내부 태스크 상속이 필요한 경우 `apply` 키워드나 `block` 구문을 활용한다.)
            
            ```yaml
            include_tasks [tag: web]
                   │
                   ├─ task A
                   ├─ task B
                   └─ task C
            ```
            
- 특수 태그
    - `always`: 명시적으로 건너뛰지 않는 한(`-skip-tags always`) 플레이북 실행 시 지정된 태그 조건과 관계없이 항상 실행된다.
    - `never`: 명시적으로 태그를 요청하지 않는 한(`-tags never` 또는 해당 작업의 다른 태그 지정) 기본 실행 목록에서 항상 제외된다.
    - `tagged` / `untagged`: CLI에서 최소 하나 이상의 태그가 있는 작업만 선별(`-tags tagged`)하거나 태그가 없는 작업만 선별(`-tags untagged`)하여 실행할 때 사용한다.
- 우선순위 및 결과 미리보기
    - 태그 우선순위: 건너뛰기(`-skip-tags`) 옵션은 항상 명시적 선택(`-tags`)보다 우선하여 적용된다.
    - 미리보기 옵션
        - `-list-tags`: 플레이북 내에서 사용 가능한 모든 태그 목록을 확인한다.
        - `-list-tasks`: `-tags` 또는 `-skip-tags` 옵션과 조합하여 실제 실행될 태스크 목록을 미리 확인한다.

### 4-7) 실습

- playbook.yml
    
    ```yaml
    ---
    - name: Simple Ansible Playbook Lab
      hosts: managed
      gather_facts: false
    
      tasks:
        - name: Check lab directory
          ansible.builtin.stat:
            path: /tmp/ansible-lab
          register: lab_dir
    
        - name: Create server information file
          ansible.builtin.copy:
            content: |
              Managed by Ansible
              Host: {{ inventory_hostname }}
              Role: {{ server_role }}
            dest: /tmp/ansible-lab/server-info.txt
          when: lab_dir.stat.exists
          notify: Report configuration change
    
      handlers:
        - name: Report configuration change
          ansible.builtin.debug:
            msg: "{{ inventory_hostname }} configuration was changed."
    ```
    
- 1차 실행
    
    ```yaml
    soso@DESKTOP-JM4DKDH:~/ansible-practice/ansible-study1$ ansible-playbook -i inventory.ini playbook.yml
    
    PLAY [Simple Ansible Playbook Lab] *********************************************
    
    TASK [Check lab directory] *****************************************************
    ok: [node2]
    ok: [node5]
    ok: [node1]
    ok: [node4]
    ok: [node3]
    ok: [node6]
    
    TASK [Create server information file] ******************************************
    changed: [node2]
    changed: [node5]
    changed: [node4]
    changed: [node1]
    changed: [node3]
    changed: [node6]
    
    RUNNING HANDLER [Report configuration change] **********************************
    ok: [node1] => {
        "msg": "node1 configuration was changed."
    }
    ok: [node2] => {
        "msg": "node2 configuration was changed."
    }
    ok: [node3] => {
        "msg": "node3 configuration was changed."
    }
    ok: [node5] => {
        "msg": "node5 configuration was changed."
    }
    ok: [node4] => {
        "msg": "node4 configuration was changed."
    }
    ok: [node6] => {
        "msg": "node6 configuration was changed."
    }
    
    PLAY RECAP *********************************************************************
    node1                      : ok=3    changed=1    unreachable=0   failed=0    skipped=0    rescued=0    ignored=0   
    node2                      : ok=3    changed=1    unreachable=0   failed=0    skipped=0    rescued=0    ignored=0   
    node3                      : ok=3    changed=1    unreachable=0   failed=0    skipped=0    rescued=0    ignored=0   
    node4                      : ok=3    changed=1    unreachable=0   failed=0    skipped=0    rescued=0    ignored=0   
    node5                      : ok=3    changed=1    unreachable=0   failed=0    skipped=0    rescued=0    ignored=0   
    node6                      : ok=3    changed=1    unreachable=0   failed=0    skipped=0    rescued=0    ignored=0    
    ```
    
- 2차 실행
    
    ```yaml
    soso@DESKTOP-JM4DKDH:~/ansible-practice/ansible-study1$ ansible-playbook -i inventory.ini playbook.yml
    
    PLAY [Simple Ansible Playbook Lab] *********************************************
    
    TASK [Check lab directory] *****************************************************
    ok: [node2]
    ok: [node5]
    ok: [node1]
    ok: [node4]
    ok: [node3]
    ok: [node6]
    
    TASK [Create server information file] ******************************************
    ok: [node2]
    ok: [node5]
    ok: [node4]
    ok: [node1]
    ok: [node3]
    ok: [node6]
    
    PLAY RECAP *********************************************************************
    node1                      : ok=2    changed=0    unreachable=0   failed=0    skipped=0    rescued=0    ignored=0   
    node2                      : ok=2    changed=0    unreachable=0   failed=0    skipped=0    rescued=0    ignored=0   
    node3                      : ok=2    changed=0    unreachable=0   failed=0    skipped=0    rescued=0    ignored=0   
    node4                      : ok=2    changed=0    unreachable=0   failed=0    skipped=0    rescued=0    ignored=0   
    node5                      : ok=2    changed=0    unreachable=0   failed=0    skipped=0    rescued=0    ignored=0   
    node6                      : ok=2    changed=0    unreachable=0   failed=0    skipped=0    rescued=0    ignored=0  
    ```
    
- 실행 설명
    - 1차 : 실습 3에서 /tmp/ansible-lab을 만들었기 때문에 when 조건이 참이다.
        
        ```yaml
        stat
         ↓
        디렉터리가 있는가?
         ↓
        register: lab_dir
         ↓
        when: lab_dir.stat.exists
         ↓ YES
        copy 실행
         ↓
        changed
         ↓
        notify
         ↓
        handler 실행
        ```
        
    - 2차 : 파일 내용이 이미 동일하여 copy가 ok가 되고 핸들러도 실행되지 않는다.

### 4-8) 참고 문헌

- https://docs.ansible.com/projects/ansible/latest/getting_started/get_started_playbook.html
- https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_variables.html
- https://docs.ansible.com/projects/ansible-core/devel/playbook_guide/playbooks_loops.html
- https://docs.ansible.com/projects/ansible-core/devel/playbook_guide/playbooks_conditionals.html
- https://docs.ansible.com/projects/ansible/latest/reference_appendices/playbooks_keywords.html
- https://docs.ansible.com/projects/ansible/latest/playbook_guide/guide_rolling_upgrade.html
- https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_blocks.html
- https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_tags.html