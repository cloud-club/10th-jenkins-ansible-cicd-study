## **5. Jinja2 & Safe Execution**

### 5-1) `template` 모듈과 Jinja2를 활용한 동적 설정 파일 생성

**Jinja2란**

- Python 프로그램 언어 환경에서 가장 널리 쓰이는 템플릿 엔진
- 정적인 텍스트 틀 속에 변수나 제어문(루프/조건문)을 넣어 동적인 결과물을 만들어내는 도구
- 설정 파일, HTML, 이메일 본문 등 형태는 고정되어 있지만 들어가는 값이 IP 주소, 사용자 이름, 경로 등 매번 바뀔 때 활용한다.
    - 틀은 하나인데 들어가는 값만 동적으로 바뀌게 만드는 것
- 문법
    - 변수 출력 **(`{{ ... }}`)**: 변수의 값을 읽어와 그 자리에 삽입한다.
        - `{{ remote_install_path }}`
    - 제어문 **(`{% ... %}`)**: 조건문(`if`), 반복문(`for`) 등 로직을 처리합니다.
    - 주석 **(`{# ... #}`)**: 템플릿 내에 설명이나 메모를 남길 때 사용합니다.
    - 필터 기능 : 변수의 값을 가공할 때 | 기호를 사용한다.

**Ansible에서 Jinja2의 사용**

- Ansible은 여러 서버에 동일한 프로그램이나 설정 파일을 배포할 때, 서버마다 달라져야 하는 값(예: IP 주소, 호스트명, 메모리 설정치 등)을 처리하기 위해 Jinja2를 도입했다.
- Jinja2를 이용한 단순 변수 치환 및 `template` 모듈 적용
    - 정의된 변수를 Jinja2 구문인 이중 중괄호(`{{ variable_name }}`)를 사용하여 참조한다.
    - `ansible.builtin.template` 모듈을 이용해 각 시스템 환경에 맞는 경로나 설정값으로 파일 내용을 동적으로 생성한다.
        
        ```yaml
        ansible.builtin.template:
          src: foo.cfg.j2
          dest: '{{ remote_install_path }}/foo.cfg'
        ```
        
- Jinja2 제어문(루프 및 조건문) 사용 시 주의사항
    - Ansible은 .j2 템플릿 파일 내부에서는 Jinja2 루프와 조건문을 사용하는 것을 허용하지만, 플레이북 내부에서는 Jinja2 루프나 조건문을 이용한 작업 반복 생성이 불가능하며 단순 순수 YAML로 구성되어야 한다.
- YAML 문법 및 따옴표 처리 규칙
    - 템플릿 참조값이 표현식의 시작인 경우(`{{ foo }}` 형태), 전체 표현식을 따옴표(`"` 또는 `'`)로 감싸야 올바른 YAML 문법으로 인식된다.
        - 감싸지 않으면 YAML 딕셔너리의 시작인지 구분하지 못해 구문 에러가 발생한다.
        
        ```yaml
        vars:
          app_path: "{{ base_path }}/22"
        ```
        

**`template` 모듈**

- `template` 모듈은 단순히 파일을 넘겨주는 것을 넘어 원격 호스트의 파일 권한, 줄바꿈 표준, 유효성 검증 등을 동적으로 제어할 수 있는 매개변수를 제공합니다.
    - 인코딩 규격 (`src`, `output_encoding`)
        - src는 반드시 UTF-8로 인코딩 되어 있어야 한다.
            
            ```yaml
            src: nginx.conf.j2
            ```
            
        - 원격 호스트에 생성되는 결과물의 인코딩은 output_encoding 옵션으로 변경할 수 있다. (기본값 : utf-8)
    - 파일 권한 및 소유권 제어 (`owner`, `group`, `mode`)
        - owner 및 group을 지정할 수 있다.
        - mode를 사용해 파일권한을 8진수 문자열이나 심볼릭 모드로 명시적으로 지정하는 것이 권장된다.
    - 줄바꿈 제어 (`newline_sequence`)
        - 운영체제 환경에 맞춰 파일 생성 시 적용할 줄바꿈 문자를 \n, \r, \r\n 중에서 선택할 수 있다.
    - 설정 파일 안전 검증 (`validate`)
        - 템플릿이 렌더링된 임시 파일을 최종 목적지로 복사하기 전, 지정한 검증 명령어를 통해 설정 구문의 이상 여부를 먼저 확인할 수 있다.
        - 명령어 내 %s 위치에 임시 파일 경로가 전달되어 실행된다.
    - 덮어쓰기 방지 및 백업  (`backup`)
        - backup: yes로 설정하면 기존 설정 파일을 덮어쓰기 전 타임스탬프가 포함된 백업 파일을 원격 시스템에 자동으로 생성한다.
- `template` 전용 내장 변수
    - Jinja2 템플릿 내부에서는 별도의 변수 정의 없이도 모듈이 자동 제공하는 특수 변수들을 가져와 설정 파일 주석 등에 활용할 수 있다.
        - `ansible_managed`: ansible.cfg 설정에 기반하여 템플릿 이름, 호스트, 수정 시간, 소유자 UID 등의 정보를 담은 안내 문자열.
        - `template_host`: 템플릿 렌더링 작업을 수행한 컨트롤 노드의 호스트명.
        - `template_path` / `template_fullpath`: 컨트롤 노드 내 템플릿 파일의 상대/절대 경로.
        - `template_destpath`: 원격 대상 호스트에 생성될 파일의 경로.
        - `template_run_date`: 템플릿이 렌더링된 시점의 날짜/시간 정보.

### 5-2) 변수 치환 및 기본 Filter 활용

```yaml
{{ variable | filter }}
```

**Jinja2 필터를 활용한 변수 변환**

- Jinja2 필터를 적용하여 템플릿 내에서 표현되는 변수의 값을 변환할 수 있다.
    - `capitalize`: 문자열의 첫 글자를 대문자로 변환
    - `to_yaml`, `to_json`: 변수의 데이터 형식을 YAML 또는 JSON 문자열 형식으로 변환
- 정의되지 않은 변수 처리
    - 정의되지 않은 변수로 인해 에러가 발생하는 것을 방지하거나 명시적으로 필수를 지정할 수 있다.
    - 기본값 제공 (`default`)
        - 변수가 정의되지 않았을 때 기본값을 할당
        
        ```yaml
        {{ http_port | default(80) }}
        ```
        
    - 선택적 모듈 변수 설정 (`omit`)
        - 값이 없을 경우 해당 모듈 인자 자체를 전달하지 않는 방식
    - 필수 변수 정의 (`mandatory` 및 `undef()`)
        - 변수가 반드시 정의되어 있어야 하도록 지정
        - 미정의 시 에러를 발생
- 조건부 변수 치환
    - 조건 검사 결과(참/거짓/null)에 따라 서로 다른 값을 치환
    - `ternary`
        - 참/거짓
            - `{{ (status == 'needs_restart') | ternary('restart', 'continue') }}`
        - 참/거짓/null
            - `{{ enabled | ternary('no shutdown', 'shutdown', omit) }}`
- 데이터 타입 확인 및 형변환
    - 변수의 타입을 확인하거나 원하는 타입으로 강제 변환
    - 타입 확인 (`type_debug`)
        - 변수의 디버깅을 위해 underlying Python 데이터 타입을 출력
    - 문자열 리스트 변환 (`split`)
        - 구분자를 기준으로 문자열을 리스트로 분할
    - 딕셔너리 리스트 변환 (`dict2items`, `item2dict`)
    - 데이터 타입 강제 캐스팅
- 데이터 포맷 변환
    - 데이터 구조를 JSON이나 YAML 형식으로 변환하거나 파싱
    - 구조체 JSON/YAML 문자열 변환
        - 데이터 구조를 JSON/YAML로 변환한다.
        - `nice` 필터를 붙이면 읽기 쉬운 형태로 정렬된다.
            
            ```yaml
            {{ some_variable | to_nice_yaml(indent=8, width=1337) }}
            ```
            
    - 문자열 구조체 파싱
        - 이미 포맷팅되어 있는 JSON/YAML 문자열을 파싱하여 변수로 재등록 및 활용한다.

### 5-3) `-check`, `-diff`를 활용한 변경 사항 사전 검증

**Validating tasks**

- Ansible은 플레이북이나 역할을 작성·수정할 때 사전 검증을 위한 두 가지 실행 모드(Check Mode, Diff Mode)를 제공한다.
- 두 모드는 단독으로 사용하거나 함께 조합하여 더욱 상세하게 변경 사항을 사전 검증할 수 있다.

**Check Mode (`--check`)**

- 원격 시스템에 실제로 아무런 변경을 가하지 않고 시뮬레이션으로만 동작하는 실행 모드
- Check Mode를 지원하는 모듈은 실행 시 변경되었을 내용(가상 변경 사항)을 보고하고, 지원하지 않는 모듈은 아무런 작업 및 보고를 수행하지 않는다.
    
    ```
    ansible-playbook foo.yml --check
    ```
    
- 특징 및 주의사항
    - 시뮬레이션 동작 특성 상, 이전 작업의 등록 변수(`registered variables`) 결과에 의존하는 조건문이 포함된 작업은 결과를 생성하지 못할 수 있다.
    - 단일 노드 단위로 실행되는 구성 관리 플레이북 검증에 유용하다.
- 태스크 단위의 Check Mode
    - 플레이북 전체 실행 옵션과 상관없이 특정 작업 단위로 Check Mode 동작을 강제하거나 방지할 수 있다.
    - `check_mode: true`
        - 명령어에 `-check`를 붙이지 않아도 해당 작업은 항상 실제 변경 없이 시뮬레이션으로 실행된다.
    - `check_mode: false`
        - 명령어에 `-check` 옵션을 부여하더라도 해당 작업은 Check Mode를 무시하고 실제 시스템에 변경을 적용한다.
        
        ```
        tasks:
          - name: This task will always make changes to the system
            ansible.builtin.command: /something/to/run --even-in-check-mode
            check_mode: false
        
          - name: This task will never make changes to the system
            ansible.builtin.lineinfile:
              line: "important config"
              dest: /path/to/myconfig.conf
              state: present
            check_mode: true
            register: changes_to_important_config
        ```
        
- Check Mode에서의 제어 및 예외 처리
    - Check Mode로 실행 중일 때 `True` 값을 가지는 매직 변수 `ansible_check_mode`를 활용하여 조건부 로직을 구성할 수 있다.
    - 특정 작업 스킵 (`when: not ansible_check_mode`)
        - Check Mode 실행 시 해당 작업을 건너뛰도록 처리한다.
    - 에러 무시 (`ignore_errors: "{{ ansible_check_mode }}"`)
        - Check Mode 실행 시 발생하는 작업 에러를 무시하도록 설정한다.
        
        ```
        tasks:
          - name: This task will be skipped in check mode
            ansible.builtin.git:
              repo: ssh://git@github.com/mylogin/hello.git
              dest: /home/mylogin/hello
            when: not ansible_check_mode
        
          - name: This task will ignore errors in check mode
            ansible.builtin.git:
              repo: ssh://git@github.com/mylogin/hello.git
              dest: /home/mylogin/hello
            ignore_errors: "{{ ansible_check_mode }}"
        ```
        

**Diff Mode (`--diff`)**

- 작업 실행 전후의 상세한 차이점을 출력해 주는 모드
- 파일 조작 모듈(`template` 등)이나 `user` 모듈처럼 변경 사항 비교를 지원하는 모듈에서 주로 사용된다.
    
    ```
    ansible-playbook foo.yml --check --diff --limit foo.example.com
    ```
    
    - `-diff` 단독 사용 또는 `-check`와 조합하여 사전 검증할 수 있다.
    - 출력이 매우 길어질 수 있으므로 `-limit` 옵션을 사용해 단일 호스트 단위로 검증하는 것이 권장된다.
- 작업 단위 민감 정보 보호 (`diff: false`)
    - Diff Mode는 변경 사항을 그대로 보여주므로 민감한 정보가 노출될 수 있다.
    - 특정 작업에 `diff: false`를 지정하여 해당 작업의 차이점 출력을 차단할 수 있다.
    
    ```
    tasks:
      - name: This task will not report a diff when the file changes
        ansible.builtin.template:
          src: secret.conf.j2
          dest: /etc/secret.conf
          owner: root
          group: root
          mode: '0600'
        diff: false
    ```
    

### 5-4) 특정 Host만 대상으로 안전하게 변경을 검증하는 방법 (`-limit`)

**특정 Host 대상 안전 변경 검증 (`-l`, `--limit`)**

- 대상 Host 범위 제한 (`-l`, `--limit`)
    - 플레이북을 실행할 특정 호스트나 호스트 패턴을 지정하여 실행 범위를 제한
    - `ansible-playbook -l <SUBSET> playbook.yml`
- 실행 대상 사전 검증 (`--list-hosts`)
    - 플레이북이나 태스크를 실제 실행하지 않고, 제한된 조건(`l` 등)에 매칭되는 대상 호스트 목록만 확인
    - `ansible-playbook -l webserver --list-hosts playbook.yml`
- 드라이 런을 통한 안전 검증 (`-C`, `--check`)
    - 대상 서버에 실제로 변경을 적용하지 않고, 실행 시 발생할 변경 사항을 예측 및 검증
    - `ansible-playbook -l web01 -C playbook.yml`
- 변경 사항 차이점 확인 (`-D`, `--diff`)
    - 파일이나 템플릿 수정 시 변경 전후의 파일 차이점을 출력
    - `C` (`-check`) 옵션과 조합하여 안전하게 사전 변경 내역 확인
    - `ansible-playbook -l web01 -C -D playbook.yml`
- 태스크 및 문법 단계별 검증
    - 문법 오류 검사 (`-syntax-check`)
        - 플레이북의 문법 오류 여부만 체크하고 실행은 하지 않음
    - 실행 예정 태스크 확인 (`-list-tasks`)
        - 실제 실행될 태스크의 전체 목록을 미리 출력하여 확인
    - 단계별 대화형 실행 (`-step`)
        - 각 태스크를 실행하기 전에 사용자 확인/승인 절차를 거치며 한 단계씩 진행

### 5-5) 실습

- templates/server.conf.j2
    
    ```yaml
    # Managed by Ansible
    
    hostname={{ inventory_hostname }}
    role={{ server_role }}
    port={{ service_port | default(8080) }}
    ```
    
- template.yml
    
    ```yaml
    ---
    - name: Jinja2 Template Lab
      hosts: managed
      gather_facts: false
    
      tasks:
        - name: Deploy server configuration
          ansible.builtin.template:
            src: templates/server.conf.j2
            dest: /tmp/ansible-lab/server.conf
    ```
    
- 실행
    
    ```yaml
    soso@DESKTOP-JM4DKDH:~/ansible-practice/ansible-study1$ ansible-playbook -i inventory.ini template.yml \
      --limit node1 \
      --check \
      --diff
    
    PLAY [Jinja2 Template Lab] *****************************************************
    
    TASK [Deploy server configuration] *********************************************
    --- before
    +++ after: /home/soso/.ansible/tmp/ansible-local-12693d05b21w7/tmpmbgq7zsq/server.conf.j2
    @@ -0,0 +1,5 @@
    +# Managed by Ansible
    +
    +hostname=node1
    +role=web
    +port=80
    \ No newline at end of file
    
    changed: [node1]
    
    PLAY RECAP *********************************************************************
    node1                      : ok=1    changed=1    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
    
    soso@DESKTOP-JM4DKDH:~/ansible-practice/ansible-study1$ ansible-playbook -i inventory.ini template.yml \
      --limit node1
    
    PLAY [Jinja2 Template Lab] **************************************************************
    
    TASK [Deploy server configuration] ******************************************************
    changed: [node1]
    
    PLAY RECAP ******************************************************************************
    node1                      : ok=1    changed=1    unreachable=0    failed=0    skipped=0   rescued=0    ignored=0   
    
    soso@DESKTOP-JM4DKDH:~/ansible-practice/ansible-study1$ ssh sohyeon@1.201.117.194
    Welcome to Ubuntu 24.04.4 LTS (GNU/Linux 6.8.0-106-generic x86_64)
    
     * Documentation:  https://help.ubuntu.com
     * Management:     https://landscape.canonical.com
     * Support:        https://ubuntu.com/pro
    
     System information as of Mon Sep 21 09:51:32 KST 2026
    
      System load:  0.16              Processes:             118
      Usage of /:   4.9% of 47.39GB   Users logged in:       0
      Memory usage: 9%                IPv4 address for eth0: 192.168.0.11
      Swap usage:   0%
    
     * Canonical Workshop gives developers fast, composable, reproducible, and
       secure developer environments that are perfect for agentic workflows.
    
       https://ubuntu.com/workshop
    
    Expanded Security Maintenance for Applications is not enabled.
    
    39 updates can be applied immediately.
    1 of these updates is a standard security update.
    To see these additional updates run: apt list --upgradable
    
    Enable ESM Apps to receive additional future security updates.
    See https://ubuntu.com/esm or run: sudo pro status
    
    1 updates could not be installed automatically. For more details,
    see /var/log/unattended-upgrades/unattended-upgrades.log
    
    *** System restart required ***
    Last login: Mon Sep 21 09:51:59 2026 from 163.239.255.155
    sohyeon@server-260916200044-0:~$ cat /tmp/ansible-lab/server.conf
    # Managed by Ansible
    
    hostname=node1
    role=web
    port=80sohyeon@server-260916200044-0:~$ exit
    logout
    Connection to 1.201.117.194 closed.
    soso@DESKTOP-JM4DKDH:~/ansible-practice/ansible-study1$ ansible-playbook -i inventory.ini template.yml \
      --check \
      --diff
    
    PLAY [Jinja2 Template Lab] **************************************************************
    
    TASK [Deploy server configuration] ******************************************************
    ok: [node1]
    --- before
    +++ after: /home/soso/.ansible/tmp/ansible-local-13124m0jcmqum/tmp4pdxdwei/server.conf.j2
    @@ -0,0 +1,5 @@
    +# Managed by Ansible
    +
    +hostname=node2
    +role=web
    +port=80
    \ No newline at end of file
    
    changed: [node2]
    --- before
    +++ after: /home/soso/.ansible/tmp/ansible-local-13124m0jcmqum/tmpt0_uceyh/server.conf.j2
    @@ -0,0 +1,5 @@
    +# Managed by Ansible
    +
    +hostname=node5
    +role=database
    +port=3306
    \ No newline at end of file
    
    changed: [node5]
    --- before
    +++ after: /home/soso/.ansible/tmp/ansible-local-13124m0jcmqum/tmpv19vquz3/server.conf.j2
    @@ -0,0 +1,5 @@
    +# Managed by Ansible
    +
    +hostname=node4
    +role=database
    +port=3306
    \ No newline at end of file
    
    changed: [node4]
    --- before
    +++ after: /home/soso/.ansible/tmp/ansible-local-13124m0jcmqum/tmpqj4qt_7k/server.conf.j2
    @@ -0,0 +1,5 @@
    +# Managed by Ansible
    +
    +hostname=node3
    +role=web
    +port=80
    \ No newline at end of file
    
    changed: [node3]
    --- before
    +++ after: /home/soso/.ansible/tmp/ansible-local-13124m0jcmqum/tmp2hgodo5i/server.conf.j2
    @@ -0,0 +1,5 @@
    +# Managed by Ansible
    +
    +hostname=node6
    +role=database
    +port=3306
    \ No newline at end of file
    
    changed: [node6]
    
    PLAY RECAP ******************************************************************************
    node1                      : ok=1    changed=0    unreachable=0    failed=0    skipped=0   rescued=0    ignored=0   
    node2                      : ok=1    changed=1    unreachable=0    failed=0    skipped=0   rescued=0    ignored=0   
    node3                      : ok=1    changed=1    unreachable=0    failed=0    skipped=0   rescued=0    ignored=0   
    node4                      : ok=1    changed=1    unreachable=0    failed=0    skipped=0   rescued=0    ignored=0   
    node5                      : ok=1    changed=1    unreachable=0    failed=0    skipped=0   rescued=0    ignored=0   
    node6                      : ok=1    changed=1    unreachable=0    failed=0    skipped=0   rescued=0    ignored=0   
    
    soso@DESKTOP-JM4DKDH:~/ansible-practice/ansible-study1$ ansible-playbook -i inventory.ini template.yml
    
    PLAY [Jinja2 Template Lab] **************************************************************
    
    TASK [Deploy server configuration] ******************************************************
    ok: [node1]
    changed: [node2]
    changed: [node5]
    changed: [node4]
    changed: [node3]
    changed: [node6]
    
    PLAY RECAP ******************************************************************************
    node1                      : ok=1    changed=0    unreachable=0    failed=0    skipped=0   rescued=0    ignored=0   
    node2                      : ok=1    changed=1    unreachable=0    failed=0    skipped=0   rescued=0    ignored=0   
    node3                      : ok=1    changed=1    unreachable=0    failed=0    skipped=0   rescued=0    ignored=0   
    node4                      : ok=1    changed=1    unreachable=0    failed=0    skipped=0   rescued=0    ignored=0   
    node5                      : ok=1    changed=1    unreachable=0    failed=0    skipped=0   rescued=0    ignored=0   
    node6                      : ok=1    changed=1    unreachable=0    failed=0    skipped=0   rescued=0    ignored=0   
    ```
    
- 실행 설명
    - 실제 파일은 만들지 않는 대신 diff에 무엇이 바뀔 것인지 표시한다.
        
        ```yaml
        ansible-playbook -i inventory.ini template.yml \
          --limit node1 \
          --check \
          --diff
        ```
        
    - node1에만 적용해본다.
        
        ```yaml
        ansible-playbook -i inventory.ini template.yml \
          --limit node1
        ```
        
    - node1에서 정상 작동하는 것을 확인한 뒤 전체 변경 예정 사항을 확인한다.
        
        ```yaml
        ansible-playbook -i inventory.ini template.yml \
          --check \
          --diff
        ```
        
    - 문제가 없다면 전체에 적용한다.
        
        ```yaml
        ansible-playbook -i inventory.ini template.yml
        ```
        
    - Control Node 구조
        
        ```yaml
        ~/ansible-study/
        │
        ├── inventory.ini
        │
        ├── group_vars/
        │   ├── web.yml
        │   └── db.yml
        │
        ├── templates/
        │   └── server.conf.j2
        │
        ├── playbook.yml
        └── template.yml
        ```
        
    - Managed Node 구조
        
        ```yaml
        /tmp/ansible-lab/
        ├── server-info.txt
        └── server.conf
        ```
        

### 5-6) 참고 문헌

- https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_variables.html
- https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/template_module.html
- https://docs.ansible.com/projects/ansible-core/2.19/playbook_guide/playbooks_filters.html
- https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_checkmode.html
- https://docs.ansible.com/projects/ansible/latest/cli/ansible-playbook.html