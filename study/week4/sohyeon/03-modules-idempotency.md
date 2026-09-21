## **3. Modules & Idempotency**

### 3-1) Ad-hoc Command 기본 사용법

**Ansible ad hoc command**

- `ad hoc command`는 플레이북을 작성하지 않고 Ansible 명령어 하나를 바로 실행하는 방식
- 지금 당장 필요한 단발성 작업을 빠르게 실행하는 방법
- ad hoc 명령은 쉽고 빠르지만 재사용할 수는 없다.
- 플레이북과 마찬가지로 선언적 모델을 사용하여 지정된 최종 상태에 도달하는 데 필요한 작업을 계산하고 실행한다.
- 실행 시작 전 현재 상태를 확인하고, 지정된 최종 상태와 다를 때만 작업을 수행하여 멱등성을 보장한다.
    
    ```yaml
    # 기본 형태
    $ ansible [pattern] -m [module] -a "[module options]"
    ```
    
    - -a : 모듈에 전달할 옵션 지정
    - -m : 실행할 모듈 이름 지정

**ad hoc 작업의 사용 사례 ([atlanta] 라는 예시의 그룹)**

- 서버 재부팅
    - ansible 명령줄 유틸리티의 기본 모듈은 ansible.builtin.command 모듈이다.
    - ad hoc 작업을 사용해 command 모듈을 호출하고, Atalanta에 있는 모든 웹 서버를 한 번에 10대씩 재부팅할 수 있다.
    - 조건 : [atlanta] 그룹에 서버가 등록되어 있어야 하며, 각 머신에 작동하는 ssh 자격 증명이 있어야 한다.
        
        ```yaml
        # [atalanta] 그룹의 모든 서버 재부팅
        $ ansible atlanta -a "/sbin/reboot"
        
        # 10개의 병렬 포크로 재부팅 (Ansible은 5개의 동시 프로세스만 사용)
        $ ansible atlanta -a "/sbin/reboot" -f 10
        
        # 다른 사용자 연결
        $ ansible atlanta -a "/sbin/reboot" -f 10 -u username
        
        # 권한 상승
        $ ansible atlanta -a "/sbin/reboot" -f 10 -u username --become [--ask-become-pass]
        ```
        
- 파일 관리
    - ad hoc 작업과 SCP를 활용해 수많은 파일을 여러 머신에 병렬로 전송할 수 있다.
    - 파일 전송, 파일 소유권 및 권한 변경, 디렉토리 생성, 디렉토리/파일 삭제
        
        ```yaml
        # 모든 서버에 파일 직접 전송
        $ ansible atlanta -m ansible.builtin.copy -a "src=/etc/hosts dest=/tmp/hosts"
        ```
        
- 패키지 관리
    - yum과 같은 패키지 관리 모듈을 사용하여 패키지를 설치, 업데이트, 제거할 수 있다.
        
        ```yaml
        # 업데이트 없이 패키지 설치 확인
        $ ansible webservers -m ansible.builtin.yum -a "name=acme state=present"
        
        # 특정 버전 설치
        $ ansible webservers -m ansible.builtin.yum -a "name=acme-1.5 state=present"
        
        # 최신 버전 업데이트
        $ ansible webservers -m ansible.builtin.yum -a "name=acme state=latest"
        
        # 패키지 삭제
        $ ansible webservers -m ansible.builtin.yum -a "name=acme state=absent"
        ```
        
- 사용자 및 그룹 관리
    - 계정 생성, 관리, 삭제
        
        ```yaml
        $ ansible all -m ansible.builtin.user -a "name=foo password=<암호화된 비밀번호>"
        $ ansible all -m ansible.builtin.user -a "name=foo state=absent"
        ```
        
- 서비스 관리
    - 서비스 시작/재시작/중지
        
        ```yaml
        $ ansible webservers -m ansible.builtin.service -a "name=httpd state=started"
        $ ansible webservers -m ansible.builtin.service -a "name=httpd state=restarted"
        $ ansible webservers -m ansible.builtin.service -a "name=httpd state=stopped"
        ```
        
- 팩트 수집
    - 시스템에서 수집된 정보(팩트)를 조회
        
        ```yaml
        $ ansible all -m ansible.builtin.setup
        ```
        
- 체크 모드
    - 원격 시스템에 변경 사항을 적용하지 않고 실행될 명령만 확인
        
        ```yaml
        $ ansible all -m copy -a "content=foo dest=/root/bar.txt" -C
        ```
        

### 3-2) `command`, `shell`, `copy`, `file`, `template`, `package`, `service/systemd` 등 주요 모듈 활용

**모듈이란**

- 커맨드 라인이나 플레이북 태스크에서 사용할 수 있는 독립된 코드 단위
    
    ```yaml
    파일 복사하고 싶다
    → copy
    
    서비스 관리하고 싶다
    → service
    
    사용자 관리하고 싶다
    → user
    
    명령어 실행하고 싶다
    → command
    ```
    
- Ansible에서는 각 모듈을 실행하고 반환 값을 수집한다.
- 각 모듈은 key=value 형태의 인자를 지원한다.
- 모든 모듈은 JSON 형식의 데이터를 반환한다. (모듈을 어떤 프로그래밍 언어로든 작성할 수 있다.)
- 모듈은 멱등성을 가져야 하며, 현재 상태가 원하는 최종 상태와 일치함을 감지하면 어떠한 변경도 수행하지 않아야 한다.
- 모듈은 핸들러에 알림을 전달하여 추가 태스크를 실행하는 형태의 변경 이벤트를 발생시킬 수 있다.
    
    ```yaml
    # 모듈 실행 예시
    
    ansible webservers -m service -a "name=httpd state=started"
    ansible webservers -m ping
    ansible webservers -m command -a "/sbin/reboot -t now"
    ```
    
    ```yaml
    # 플레이북 모듈 예시
    
    - name: restart webserver
      service:
        name: httpd
        state: restarted
    ```
    

**주요 모델**

- 명령어 기반 모듈 : `command`, `shell`등
    - 단순히 실행하려는 명령어 문자열만 인자로 받는다.
        
        ```yaml
        # 커맨드 라인 실행
        ansible webservers -m command -a "/sbin/reboot -t now"
        
        # 플레이북 실행
        - name: reboot the servers
          command: /sbin/reboot -t now
        ```
        
- 서비스 빛 데몬 관리 모듈 : `service`, `systemd` 등
    - key=value 인자 형태나 YAML 구문(복합 인자)을 사용하여 서비스의 상태를 지정한다.
        
        ```yaml
        # 커맨드 라인 실행
        ansible webservers -m service -a "name=httpd state=started"
        
        # 플레이북 실행
        - name: restart webserver
          service:
            name: httpd
            state: restarted
        ```
        
- 패키지 관리 모듈 : `yum` 등
    - ansible-doc <모듈명> 형태로 개별 모듈의 상세 사용법 및 문서를 바로 확인하여 활용할 수 있다.
        
        ```yaml
        # 커맨드 라인 실행
        ansible-doc yum
        ```
        

### 3-3) FQCN (`ansible.builtin.*`) 기반 모듈 사용 방식

**FQCN**

- Ansible 2.10 이후 대부분의 모듈은 Collection 단위로 제공되며 각 모듈은 Fully Qualified Collection Name, 즉 FQCN을 갖는다.
- 충돌 방지와 문서 연결의 명확성을 위해 FQCN 사용이 권장된다.
    - 서로 다른 개발자나 기관이 만든 컬렉션에 동일한 이름의 모듈(예: `ping`)이 존재하더라도, `ansible.builtin.ping`과 `community.general.ping`처럼 명확히 구분하여 충돌을 막을 수 있다.
    - 해당 모듈이 내장 모듈인지, 아니면 별도의 외부 커뮤니티 컬렉션인지 직관적으로 알 수 있다.
    - Ansible 최신 버전들은 공식적으로 FQCN 방식을 표준으로 채택 중이기에 향후에도 안전하게 플레이북을 유지 관리 할 수 있다.
    
    ```yaml
    - name: FQCN 기반 모듈 사용 예시
      hosts: localhost
      tasks:
        # 기존 방식 (Short Name)
        - name: 레거시 방식으로 파일 복사
          copy:
            src: file.txt
            dest: /tmp/file.txt
    
        #  권장 방식 (FQCN)
        - name: FQCN 방식으로 파일 복사
          ansible.builtin.copy:
            src: file.txt
            dest: /tmp/file.txt
    
        # 내장 모듈 외의 외부 컬렉션 사용 예시
        - name: AWS S3 버킷 생성 (외부 커뮤니티 컬렉션)
          amazon.aws.s3_bucket:
            name: my-bucket
            state: present
    ```
    
    ```yaml
    # collections 키워드를 정의한 예시
    
    - name: 플레이북 수준에서 컬렉션 정의
      hosts: localhost
      collections:
        - ansible.builtin
        - community.general
      tasks:
        # collections에 등록했으므로 ansible.builtin.copy 대신 copy만 써도 동작합니다.
        - name: 기본 컬렉션을 지정한 단축 모듈 사용
          copy:
            src: file.txt
            dest: /tmp/file.txt
    ```
    

### 3-4) Ansible의 멱등성(Idempotency) 개념 및 `ok`, `changed`, `failed` 상태 이해

**멱등성이란**

- 시스템이 이미 플레이북에 기술된 상태와 일치한다면, 플레이북을 여러 번 실행하더라도 Ansible은 아무것도 변경하지 않는다.
- 사용자가 작업을 매번 어떻게 수행할지가 아니라, 시스템이 어떤 상태여야 하는지를 플레이북에 선언하고, Ansible은 시스템의 현재 상태를 확인한 뒤 플레이북에 선언된 상태와 일치하도록 보장한다.
- 반복 실행에 따른 불필요한 시스템 변경이나 오류를 방지하여 예측 가능성을 제공한다.

**Ansible의 작업 상태값**

- `ok` (성공/미변경)
    - 태스크가 정상 실행되었으나 대상 시스템에 아무런 변경 사항이 발생하지 않은 상태이다. (시스템이 이미 원하는 상태일 때이다.)
- `changed` (변경됨)
    - 태스크 실행 결과 대상 시스템의 상태가 실제 변경된 경우이다.
    - changed_when 조건을 활용해 변경 여부를 제어할 수 있으며, 이 상태일 때 연결된 핸들러가 호출된다.
- `failed` (실패)
    - 모듈 실행 실패 또는 명령어가 0이 아닌 반환 코드를 반환한 상태이다.
    - 기본적으로 실패가 발생하면 해당 호스트에 대한 이후 태스크 실행이 즉시 중단된다.

**상태 및 오류 제어**

- `force_handlers`
    - 핸들러 동작 제어
    - 플레이 도중 다른 태스크가 실패하면 changed 상태가 발생했더라도 핸들러가 실행되지 않는다.
    - `force_handlers: True` 설정을 통해서 강제로 실행할 수 있다.
    - 핸들러가 강제 실행되도록 설정되면 Ansible은 태스크가 실패한 호스트를 포함하여 모든 알림을 받은 핸들러를 실행한다.
- `ignore_errors`
    - 오류 무시
    - 특정 태스크가 failed 상태가 되더라도 전체 프로세스를 중단하지 않고 다음 태스크로 진행하게 만든다.
        
        ```yaml
        - name: Do not count this as a failure
          ansible.builtin.command: /bin/false
          ignore_errors: true
        ```
        
- `any_errors_fatal` / `max_fail_percentage`
    - 치명적 오류 및 전체 중단
    - 일부 호스트의 failed가 전체 인프라 영향으로 퍼지지 않도록 배치 단위로 실행을 일괄 중단시킬 수 있다.

### 3-5) `changed_when`, `failed_when`을 활용한 실행 결과 제어

**멱등성 관점에서의 문제점과 해결**

- 문제
    - Ansible의 일반적인 모듈은 자체적으로 멱등성을 보장한다.
    - 그러나 shell이나 command 모듈은 단순히 명령을 수행하므로 매번 실행할 때마다 changed로 인식되거나 의도치 않게 failed 처리되어 멱등성이 깨질 수도 있다.
- 해결 1) `changed_when`을 통한 멱등성 및 상태 명시
    - command / shell 명령어는 기본적으로 항상 changed를 발생시킨다.
    - 반환 코드나 출력을 바탕으로 변경 사항을 통계에 반영할지, 핸들러를 트리거할지 결정한다.
    - 정확한 멱등성 통계를 얻기 위해 changed_when을 설정한다.
        
        ```yaml
        tasks:
          - name: Report 'changed' when the return code is not equal to 2
            ansible.builtin.shell: /usr/bin/billybass --mode="take me to the river"
            register: bass_result
            changed_when: "bass_result.rc != 2"
        
          - name: This will never report 'changed' status
            ansible.builtin.shell: wall 'beep'
            changed_when: False
        
          - name: This task will always report 'changed' status
            ansible.builtin.command: /path/to/command
            changed_when: True
        ```
        
        ```yaml
        # 여러 조건을 조합하여 changed 재정의
        
        - name: Combine multiple conditions to override 'changed' result
          ansible.builtin.command: /bin/fake_command
          register: result
          ignore_errors: True
          changed_when:
            - '"ERROR" in result.stderr'
            - result.rc == 2
        ```
        
- 해결 2) `failed_when`을 통한 실패 조건 정의
    - 명령어의 실패 기준을 커스텀 정의하여, 단순 비정상 종료 코드라도 실제 시스템에 영향이 없다면 실패로 처리하지 않고 흐름을 유지시킨다.
    - failed_when 조건의 목록은 암시적인 and로 연결되므로, 모든 조건이 충족될 때만 태스크가 실패한다.
    - 조건 중 하나라도 충족될 때 실패하도록 하려면 명시적인 or 연산자를 사용해야 한다.
        
        ```yaml
        # 두 조건 중 하나라도 참일 때 실패
        - name: Fail task when either condition is met
          ansible.builtin.command: /usr/bin/example-command
          register: command_result
          failed_when: command_result.rc != 0 or 'ERROR' in command_result.stdout
        ```
        
        ```yaml
        # 명령어 오류 출력에 특정 단어가 포함될 때 실패
        - name: Fail task when the command error output prints FAILED
          ansible.builtin.command: /usr/bin/example-command -x -y -z
          register: command_result
          failed_when: "'FAILED' in command_result.stderr"
        ```
        
        ```yaml
        # 반환 코드를 기반으로 실패 지정
        - name: Fail task when both files are identical
          ansible.builtin.raw: diff foo/file1 bar/file2
          register: diff_cmd
          failed_when: diff_cmd.rc == 0 or diff_cmd.rc >= 2
        ```
        
        ```yaml
        # 두 조건이 모두 참일 때 실패 (AND 조건)
        - name: Check if a file exists in temp and fail task if it does
          ansible.builtin.command: ls /tmp/this_should_not_be_here
          register: result
          failed_when:
            - result.rc == 0
            - '"No such" not in result.stderr'
        ```
        
        ```yaml
        # 여러 조건을 줄바꿈(OR)으로 작성
        - name: example of many failed_when conditions with OR
          ansible.builtin.shell: "./myBinary"
          register: ret
          failed_when: >
            ("No such file or directory" in ret.stdout) or
            (ret.stderr != '') or
            (ret.rc == 10)
        ```
        
        ```yaml
        # 암시적 변수 _task 활용 (변수 등록 생략)
        - name: Fail task when either condition is met
          ansible.builtin.command: /usr/bin/example-command
          failed_when: _task.result.rc != 0 or 'ERROR' in _task.result.stdout
        ```
        

### 3-6) 실습

```yaml
soso@DESKTOP-JM4DKDH:~/ansible-practice/ansible-study1$ ansible managed -i inventory.ini \
  -m ansible.builtin.file \
  -a "path=/tmp/ansible-lab state=directory"
node5 | CHANGED => {
    "ansible_facts": {
        "discovered_interpreter_python": "/usr/bin/python3"
    },
    "changed": true,
    "gid": 1002,
    "group": "sohyeon",
    "mode": "0775",
    "owner": "sohyeon",
    "path": "/tmp/ansible-lab",
    "size": 4096,
    "state": "directory",
    "uid": 1002
}
node4 | CHANGED => {
    "ansible_facts": {
        "discovered_interpreter_python": "/usr/bin/python3"
    },
    "changed": true,
    "gid": 1002,
    "group": "sohyeon",
    "mode": "0775",
    "owner": "sohyeon",
    "path": "/tmp/ansible-lab",
    "size": 4096,
    "state": "directory",
    "uid": 1002
}
node2 | CHANGED => {
    "ansible_facts": {
        "discovered_interpreter_python": "/usr/bin/python3"
    },
    "changed": true,
    "gid": 1002,
    "group": "sohyeon",
    "mode": "0775",
    "owner": "sohyeon",
    "path": "/tmp/ansible-lab",
    "size": 4096,
    "state": "directory",
    "uid": 1002
}
node1 | CHANGED => {
    "ansible_facts": {
        "discovered_interpreter_python": "/usr/bin/python3"
    },
    "changed": true,
    "gid": 1003,
    "group": "sohyeon",
    "mode": "0775",
    "owner": "sohyeon",
    "path": "/tmp/ansible-lab",
    "size": 4096,
    "state": "directory",
    "uid": 1003
}
node3 | CHANGED => {
    "ansible_facts": {
        "discovered_interpreter_python": "/usr/bin/python3"
    },
    "changed": true,
    "gid": 1002,
    "group": "sohyeon",
    "mode": "0775",
    "owner": "sohyeon",
    "path": "/tmp/ansible-lab",
    "size": 4096,
    "state": "directory",
    "uid": 1002
}
node6 | CHANGED => {
    "ansible_facts": {
        "discovered_interpreter_python": "/usr/bin/python3"
    },
    "changed": true,
    "gid": 1002,
    "group": "sohyeon",
    "mode": "0775",
    "owner": "sohyeon",
    "path": "/tmp/ansible-lab",
    "size": 4096,
    "state": "directory",
    "uid": 1002
}
soso@DESKTOP-JM4DKDH:~/ansible-practice/ansible-study1$ ansible managed -i inventory.ini   -m ansible.builtin.file   -a "path=/tmp/ansible-lab state=directory"
node5 | SUCCESS => {
    "ansible_facts": {
        "discovered_interpreter_python": "/usr/bin/python3"
    },
    "changed": false,
    "gid": 1002,
    "group": "sohyeon",
    "mode": "0775",
    "owner": "sohyeon",
    "path": "/tmp/ansible-lab",
    "size": 4096,
    "state": "directory",
    "uid": 1002
}
node2 | SUCCESS => {
    "ansible_facts": {
        "discovered_interpreter_python": "/usr/bin/python3"
    },
    "changed": false,
    "gid": 1002,
    "group": "sohyeon",
    "mode": "0775",
    "owner": "sohyeon",
    "path": "/tmp/ansible-lab",
    "size": 4096,
    "state": "directory",
    "uid": 1002
}
node4 | SUCCESS => {
    "ansible_facts": {
        "discovered_interpreter_python": "/usr/bin/python3"
    },
    "changed": false,
    "gid": 1002,
    "group": "sohyeon",
    "mode": "0775",
    "owner": "sohyeon",
    "path": "/tmp/ansible-lab",
    "size": 4096,
    "state": "directory",
    "uid": 1002
}
node1 | SUCCESS => {
    "ansible_facts": {
        "discovered_interpreter_python": "/usr/bin/python3"
    },
    "changed": false,
    "gid": 1003,
    "group": "sohyeon",
    "mode": "0775",
    "owner": "sohyeon",
    "path": "/tmp/ansible-lab",
    "size": 4096,
    "state": "directory",
    "uid": 1003
}
node3 | SUCCESS => {
    "ansible_facts": {
        "discovered_interpreter_python": "/usr/bin/python3"
    },
    "changed": false,
    "gid": 1002,
    "group": "sohyeon",
    "mode": "0775",
    "owner": "sohyeon",
    "path": "/tmp/ansible-lab",
    "size": 4096,
    "state": "directory",
    "uid": 1002
}
node6 | SUCCESS => {
    "ansible_facts": {
        "discovered_interpreter_python": "/usr/bin/python3"
    },
    "changed": false,
    "gid": 1002,
    "group": "sohyeon",
    "mode": "0775",
    "owner": "sohyeon",
    "path": "/tmp/ansible-lab",
    "size": 4096,
    "state": "directory",
    "uid": 1002
}
soso@DESKTOP-JM4DKDH:~/ansible-practice/ansible-study1$ ssh sohyeon@1.201.117.194
Welcome to Ubuntu 24.04.4 LTS (GNU/Linux 6.8.0-106-generic x86_64)

 * Documentation:  https://help.ubuntu.com
 * Management:     https://landscape.canonical.com
 * Support:        https://ubuntu.com/pro

 System information as of Mon Sep 21 09:36:56 KST 2026

  System load:  0.0               Processes:             118
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
Last login: Mon Sep 21 09:37:28 2026 from 163.239.255.155
sohyeon@server-260916200044-0:~$ ls -ld /tmp/ansible-lab
drwxrwxr-x 2 sohyeon sohyeon 4096 Sep 21 09:36 /tmp/ansible-lab
sohyeon@server-260916200044-0:~$ exit
logout
Connection to 1.201.117.194 closed.
```

- 처음 디렉토리 생성 시 CHANGED
    
    ```yaml
    현재 상태
    /tmp/ansible-lab 없음
    
    원하는 상태
    /tmp/ansible-lab 있음
    
    → 상태가 다름
    → 생성
    → changed
    ```
    
- 두 번째 디렉토리 생성 시
    
    ```yaml
    1회차
    없음 → 생성
    changed
    
    2회차
    이미 있음
    ok
    ```
    
- 멱등성 확인 가능

### 3-7) 참고 문헌

- https://docs.ansible.com/projects/ansible/latest/command_guide/intro_adhoc.html
- https://docs.ansible.com/projects/ansible/latest/module_plugin_guide/modules_intro.html
- https://docs.ansible.com/projects/ansible/latest/getting_started/introduction.html
- https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_error_handling.html