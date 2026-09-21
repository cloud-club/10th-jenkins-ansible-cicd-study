## **2. Inventory & Variables**

### 2-1) Static Inventory 구성 및 Host / Group 관리

**인벤토리란**

- Managed node의 목록과 접속 정보를 정의하는 파일로, Ansible이 관리할 서버와 서버 별 정보를 정리해 둔 목록이라고 볼 수 있다.
- 관리할 서버의 IP 주소 또는 FQDN을 등록한다.
- INI 파일 혹은 YAML 형식으로 작성할 수 있다.
    - managed node가 적다면 INI, 늘어나면 YAML로 만들기
- 명령어로도 호스트 이름을 전달할 수도 있지만 편리성과 지속성을 위해서는 인벤토리 파일을 생성하는 것이 좋다.

**인벤토리의 그룹 사용법**

- 그룹을 사용할 수 있고, 그룹을 통해서 연관된 여러 호스트를 묶어서 지정하거나 변수를 일괄 정의할 수 있다.
- 그룹 이름은 의미 있고 유니크 해야 하며, 공백, 하이픈, 숫자로 시작하는 명칭은 피해야 한다.
- 역할, 위치, 시기에 따라 호스트를 논리적으로 그룹화한다.
    - 역할 : db, web, …
    - 위치 : datacenter, region, …
    - 시기 : development, test, production, …
    - 기본 그룹 : 모든 호스트가 포함되는 all 그룹, 다른 그룹에 속하지 않은 호스트를 모은 ungrouped 그룹
    
    ```yaml
    ungrouped:
      hosts:
        mail.example.com:
    webservers:
      hosts:
        foo.example.com:
        bar.example.com:
    dbservers:
      hosts:
        one.example.com:
        two.example.com:
        three.example.com:
    east:
      hosts:
        foo.example.com:
        one.example.com:
        two.example.com:
    west:
      hosts:
        bar.example.com:
        three.example.com:
    prod:
      hosts:
        foo.example.com:
        one.example.com:
        two.example.com:
    test:
      hosts:
        bar.example.com:
        three.example.com: 
    ```
    
- 호스트 범위
    
    ```yaml
    [webservers]
    www[01:50].example.com
    ```
    
    ```yaml
    [webservers]
    www[01:50:2].example.com
    
    # 2씩 증가하여 www01, www03, www05와 같은 형식으로 매칭된다.
    ```
    
- `ansible-playbook get_logs.yml -i staging -i production` 와 같은 명령어처럼 -i 옵션을 여러 번 사용하면 복수의 인벤토리를 함께 지정할 수 있다.

**메타그룹**

```yaml
metagroupname:
  children:
```

- 메타그룹이란? 여러 하위 그룹을 하나로 묶어 놓은 상위 그룹을 뜻한다. (그룹들의 집합)
- 하나의 그룹이 여러 메타그룹에 속할 수도 있다.
- 상위 그룹의 group_vars에 정의된 변수는 하위 그룹의 호스트에도 적용되지만, 하위 그룹의 group_vars에 정의된 값이 상위의 값을 오버라이드한다.
    - 하위 그룹(자식)의 변수가 상위 그룹(부모)의 변수보다 우선순위가 높다.
- 예측 가능한 상속을 위해서는 각 그룹의 하나의 상위 그룹 아래에만 정의하는 것이 좋다.
    
    ```yaml
    leafs:
      hosts:
        leaf01:
          ansible_host: 192.0.2.100
        leaf02:
          ansible_host: 192.0.2.110
    spines:
      hosts:
        spine01:
          ansible_host: 192.0.2.120
        spine02:
          ansible_host: 192.0.2.130
    network:
      children:
        leafs:
        spines:
    datacenter:
      children:
        network:
    ops:
      children:
        network: 
    ```
    
- 변수는 IP 주소, FQDN, 운영체제, SSH 사용자 등 managed node의 값을 설정하여 명령마다 매번 새롭게 전달할 필요가 없도록 한다.
    - 변수는 특정 호스트 또는 그룹의 모든 호스트에도 적용할 수 있다.

**디렉토리 구조로 인벤토리 구성**

- 인벤토리 파일이 길어지면 관리하기 어렵기 때문에, 개별 인벤토리 파일로 구분해서 하나의 디렉토리로 모으면 관리하기 훨씬 쉬워진다.
- INI, YAML 등 다양한 형식을 섞어서 디렉토리를 구성할 수 있고, Ansible은 해당 디렉토리를 하나의 단일 인벤토리 소스로 취급하여 하나로 합쳐 로드한다.
    
    ```yaml
    inventory/
      openstack.yml          # configure inventory plugin to get hosts from OpenStack cloud
      dynamic-inventory.py   # add additional hosts with dynamic inventory script
      on-prem                # add static hosts and groups
      parent-groups          # add static hosts and groups
    ```
    
- Ansible은 일보 디렉토리와 확장자를 무시하지만, INVENTORY_IGNORE_PATTERNS나 INVENTORY_IGNORE_EXTS와 같은 구성 설정에서 동작을 변경할 수 있다.
- 로드 순서
    - 제공된 순서대로 인벤토리 소스 로드
    - 소스 파일에서 호스트, 그룹, 변수를 만나는 순서대로 정의하며, 필요한 경우 마지막에 all 및 ungrouped 그룹을 추가한다.
    - 부모/자식 관계의 그룹이나 호스트가 사용하는 플러그인의 예상대로 존재하도록 소스 로드  순서를 조정해야 할 수도 있다.
        - 구문 분석 오류가 발생할 수도 있다.

**inventory alias**

- inventory_hostname은 Ansible에서 호스트를 식별하는 고유한 식별자이다.
- IP 주소나 호스트 이름일 수도 있지만, alias나 단축 이름일 수도 있다.
    
    ```yaml
    jumper ansible_port=5555 ansible_host=192.0.2.50
    ```
    
- 위의 예시에서는 alias로 jumper를 지정하였고, Ansible을 실행하면 192.0.2.50 IP의 5555 포트로 연결된다.

### 2-2) `group_vars/`, `host_vars/`를 활용한 환경별 변수 관리

**변수 할당**

- host variables
    
    ```yaml
    [atlanta]
    host1 http_port=80 maxRequestsPerChild=808
    host2 http_port=303 maxRequestsPerChild=909
    ```
    
    ```yaml
    atlanta:
      hosts:
        host1:
          http_port: 80
          maxRequestsPerChild: 808
        host2:
          http_port: 303
          maxRequestsPerChild: 909
    ```
    
    - 호스트 변수를 사용하여 연결 변수를 정의할 수도 있다.
    
    ```yaml
    [targets]
    
    localhost              ansible_connection=local
    other1.example.com     ansible_connection=ssh        ansible_user=myuser
    other2.example.com     ansible_connection=ssh        ansible_user=myotheruser
    ```
    
- group variables
    - 그룹에 속한 모든 호스트가 동일한 변수 값을 공유하는 경우, 해당 변수를 그룹 전체에 한 번에 적용할 수 있다.
    
    ```yaml
    [atlanta]
    host1
    host2
    
    [atlanta:vars]
    ntp_server=ntp.atlanta.example.com
    proxy=proxy.atlanta.example.com
    ```
    
    ```yaml
    atlanta:
      hosts:
        host1:
        host2:
      vars:
        ntp_server: ntp.atlanta.example.com
        proxy: proxy.atlanta.example.com
    ```
    
    - Ansible은 인벤토리 변수를 포함한 모든 변수를 호스트 수준으로 병합한다. 이때, 서로 다른 그룹에서 동일한 변수에 서로 다른 값을 할당한 경우, 내부 병합 규칙에 따라 사용할 값을 선택하게 된다.

**변수 값 상속**

- 상위 그룹에도 변수를 적용할 수 있다.
- 하위 그룹의 변수는 상위 그룹의 변수보다 우선 순위가 높다.

**host_group_vars 플러그인**

- Ansible에서 기본으로 제공하는 플러그인으로, 호스트 및 그룹 변수를 별도의 파일로 정의할 수 있다.
    - 별도의 파일에 변수를 정의하는 것이 인벤토리 소스 내에 작성하는 것보다 시스템 정책을 명확하게 설명할 수 있다.
- 반드시 YAML 구문을 사용해야 한다.
- host_group_vars는 인벤토리 소스/플레이북 파일 기준의 상대 경로를 탐색하여 호스트 및 그룹 변수 파일을 로드한다.
- 예시1
    - `/etc/ansible/hosts` 위치에 있는 인벤토리 파일에 `raleigh` 및 `webservers` 그룹에 속한 `foosball`이라는 이름의 호스트가 존재한다면, `/etc/ansible/group_vars/raleigh`, `/etc/ansible/group_vars/webservers`, `/etc/ansible/host_vars/foosball` 위치의 YAML 파일의 변수를 사용하게 된다.
    - raleigh 그룹에 속한 모든 호스트는 `/etc/ansible/group_vars/raleigh` 위치에 속한 파일들에 정의된 변수를 사용할 수 있다.
- 예시2
    
    ```yaml
    inventory/
    ├── hosts.yml
    ├── group_vars/
    │   ├── all.yml
    │   ├── web.yml
    │   └── db.yml
    └── host_vars/
        ├── web01.yml
        └── db01.yml
    ```
    
    ```yaml
    group_vars/web.yml
           ↓
    모든 web 그룹 서버
    
    host_vars/web01.yml
           ↓
    web01에만 적용
    ```
    

### 2-3) `inventory_hostname`, `groups`, `hostvars` 등 Inventory 관련 변수 활용

**매직 변수**

- 매직 변수를 이용하면 사용 중인 python 버전, 인벤토리의 호스트 및 그룹, 플레이북 및 역할의 디렉토리를 포함한 Ansible 작업에 대한 정보에 접근할 수 있다.
- 매직 변수 이름은 이미 다 예약되어 있다.

`hostvars`

- 플레이북 내 어떤 지점에서든 플레이에 포함된 다른 호스트에 정의된 변수에 접근할 수 있다.
- Fact를 수집했거나 캐시한 이후에는 Ansible facts에도 접근할 수 있다.
- 단, 플레이 개체 레벨에서 정의된 변수는 특정 호스트에 정의된 것이 아니기 때문에 hostvars에 매핑되지 않는다.
- 다른 노드의 fact 값이나 인벤토리 변수 값을 사용하여 데이터베이스 서버를 설정하려는 경우, 실행에서 hostvars를 활용할 수 있다.
    
    ```yaml
    {{ hostvars['test.example.com']['ansible_facts']['distribution'] }}
    ```
    

`groups`

- 인벤토리에 있는 모든 그룹과 호스트의 목록
    
    ```yaml
    groups
     │
     ├── webservers
     │    ├── web01
     │    └── web02
     │
     └── dbservers
          └── db01
    
          
    {{ groups['webservers'] }}
    -> ['web01', 'web02'] 
    ```
    
- 그룹에 속한 모든 호스트를 순회할 수 있다.
    
    ```yaml
    {% for host in groups['app_servers'] %}
       {{ hostvars[host]['ansible_facts']['eth0']['ipv4']['address'] }}
    {% endfor %}
    ```
    

`group_names`

- 현재 호스트가 속해 있는 모든 그룹의 목록
    - groups : 그룹에 속해 있는 호스트는?
    - group_names : 호스트가 속한 그룹은?
- 현재 호스트의 그룹 소속 여부에 따라 건너뛰거나 인스턴스화할 작업을 결정하는 조건문에서 이 변수를 사용할 수 있다.
    
    ```yaml
    {% if 'webserver' in group_names %}
       # some part of a configuration file that only applies to webservers
    {% endif %}
    ```
    

`inventory_hostname`

- 인벤토리에 구성되어 있는 현재 호스트의 이름
- Fact 수집 문제로 인해 `ansible_facts['hostname']`을 사용할 수 없거나 원하지 않는 경우 이 변수를 사용할 수 있다.
    - `ansible_facts['hostname']` 는 서버에 실제로 접속해서 운영체제에서 수집한 호스트의 이름으로 `inventory_hostname`과 다를 수 있다.
- `inventory_hostname_short` 변수에는 호스트 이름의 첫 번째 도메인 부분만 포함된다.

### 2-4) Variable Precedence 기본 원칙 및 변수 관리 전략

**Variable Precedence**

- 여러 위치에서 동일한 이름을 가진 변수가 여러 개 있다면, ansible은 찾을 수 있는 모든 변수를 로드하고 variable precedence에 따라 적용할 변수를 선택한다.
- 서로 다른 변수들이 정해진 순서에 따라 기존 값을 덮어쓰게 된다.
- 일반적으로는 각 변수는 단 한 곳에만 정의해야 하기 때문에 변수 우선순위에 대한 문제는 피할 수 있다.

**변수 우선순위의 순서**

1. command line values
2. role defaults
3. inventory file or script group vars
4. inventory group_vars/all
5. playbook group_vars/all
6. inventory group_vars/*
7. playbook group_vars/*
8. inventory file or script host vars
9. inventory host_vars/*
10. playbook host_vars/*
11. host facts and cached set_facts
12. play vars
13. play vars_prompt
14. play vars_files
15. role vars (as defined in role directory structure)
16. block vars (for tasks in block only)
17. task vars (for the task only)
18. include_vars
19. registered vars and set_facts
20. role (and include_role) params
21. include params
22. extra vars

**변수 관리 전략**

- 변수의 범위를 가능한 명확하게 한다.
    - 다양한 위치에서 동일한 이름을 가진 변수를 재정의하는 것은 변수의 실제 값을 추적하기 어렵게 만든다.
- 인벤토리에 변수를 정의하는 것을 피한다.
    - 인벤토리 파일이나 디렉토리는 주로 호스트를 정의하는 용도로 사용해야 한다.
    - 인벤토리에는 호스트 고유의 변수만 포함하도록 한다.
- 플레이북 전체에 적용되는 변수는 `group_vars/all`에 정의한다.
- 특정 호스트 그룹에 대한 변수는 `group_vars/group_name`에 정의한다.
- 호스트 전용 변수는 `host_vars/hostname`에 정의한다.
- 롤 내부의 기본값은 `roles/x/defaults/main.yml`에 정의한다.
- 롤에서 변경되면 안 되는 상수는 `roles/x/vars/main.yml`에 정의한다.
- 명령줄 옵션(`-e` 또는 `--extra-vars`)으로 넘기는 변수는 가장 높은 우선순위를 갖는다.

### 2-5) Dynamic Inventory 개념 및 AWS EC2 등 외부 인프라 연동 방식 이해

**Dynamic Inventory**

- 정적 인벤토리 파일에 IP 주소나 호스트명을 직접 관리하는 대신, AWS, Azure, GCP 등의 외부 데이터 소스를 조회하여 현재 관리 대상 호스트 목록을 동적으로 가져오는 방식이다.
- 서버의 생성과 삭제가 빈번하여 인벤토리가 계속 변경되는 환경에서 유용하다.
    - 예시) AWS 환경에서 Auto Scaling을 사용하는 경우 트래픽 증가에 따라 EC2 인스턴스가 추가되고, 트래픽 감소에 따라 다시 제거될 수 있다.
    - 이러한 환경에서는 사람이 직접 hosts 파일을 계속 수정하기 어렵기 때문에 Dynamic Inventory를 사용할 수 있다.
    
    ```
    Static Inventory
    
    사람 → hosts 파일 작성 → Ansible
    ```
    
    ```
    Dynamic Inventory
    
    Ansible → 외부 데이터 소스 조회 → 현재 호스트 목록 구성
    ```
    
- Dynamic Inventory를 구성하는 대표적인 방법으로 Inventory Plugin과 Inventory Script가 있다.
    - Inventory Plugin
        - 외부 데이터 소스에서 호스트 정보를 가져오기 위해 사용하는 Ansible의 플러그인 방식이다.
        - Ansible의 최신 기능과 업데이트를 활용할 수 있기 때문에 Dynamic Inventory 구성 시 권장되는 방식이다.
        - AWS EC2, Azure, GCP, OpenStack 등 다양한 외부 인프라와 연동할 수 있다.
        - 필요한 데이터 소스가 기본적으로 지원되지 않는다면 Custom Inventory Plugin을 직접 작성할 수도 있다.
        
        ```
        Ansible
           ↓
        Inventory Plugin
           ↓
        AWS / Azure / GCP / OpenStack 등
           ↓
        현재 호스트 정보 조회
           ↓
        Dynamic Inventory 구성
        ```
        
    - Inventory Script
        - 외부 시스템에서 호스트 정보를 조회한 뒤 Ansible이 사용할 수 있는 형식으로 반환하는 실행 가능한 스크립트 방식이다.
        - Inventory Plugin이 널리 사용되기 이전부터 사용된 방식이며, 현재는 가능한 경우 Inventory Plugin 사용이 권장된다.

**AWS EC2와 Dynamic Inventory 연동**

- AWS 환경에서는 고정된 EC2 IP 주소나 호스트명을 인벤토리에 직접 작성하는 대신, AWS API를 조회하여 현재 존재하는 EC2 인스턴스를 동적으로 수집할 수 있다.
- AWS EC2 Inventory Plugin인 `amazon.aws.aws_ec2`를 사용할 수 있다.
- 일반적으로 파일 이름을 `.aws_ec2.yml` 또는 `.aws_ec2.yaml`로 만들고 다음과 같이 플러그인을 지정한다.
    
    ```yaml
    plugin: amazon.aws.aws_ec2
    
    regions:
      - ap-northeast-2
    ```
    
    ```
    Ansible
       ↓
    amazon.aws.aws_ec2
       ↓
    AWS API
       ↓
    현재 EC2 인스턴스 조회
       ↓
    필터링 및 그룹화
       ↓
    Dynamic Inventory 생성
    ```
    

**외부 인프라 연동 시 주요 설정**

- 인증 설정
    - AWS 자격 증명이나 IAM Role 등을 이용하여 AWS API에 접근한다.
- 리전 및 대상 지정
    - `regions` 등을 이용하여 조회할 AWS 리전을 지정한다.
    - 태그, 인스턴스 상태 등의 조건을 이용하여 필요한 EC2 인스턴스만 선별할 수 있다.
- 그룹화
    - EC2의 태그나 기타 속성을 이용하여 조회된 인스턴스를 동적으로 그룹화할 수 있다.
    - 예를 들어 `Role=web`, `Role=db` 등의 태그를 기준으로 웹 서버와 DB 서버를 구분할 수 있다.

```
                   AWS EC2
                      │
              Inventory Plugin
                      │
              EC2 정보 동적 조회
                      │
           ┌──────────┴──────────┐
           ▼                     ▼
      Role = web             Role = db
           │                     │
     ┌─────┴─────┐               │
     ▼           ▼               ▼
   web01       web02            db01
```

### 2-6) 실습

- inventory.ini
    
    ```yaml
    [web]
    node1 ansible_host=1.201.117.194
    node2 ansible_host=1.201.116.180
    node3 ansible_host=1.201.116.156
    
    [db]
    node4 ansible_host=1.201.118.202
    node5 ansible_host=1.201.118.10
    node6 ansible_host=1.201.118.90
    
    [managed:children]
    web
    db
    
    [managed:vars]
    ansible_user=sohyeon
    ```
    
- 그룹화 및 그룹별 변수 적용
    - group_vars/web.yml
        
        ```yaml
        server_role: web
        service_port: 80
        ```
        
    - group_vars/db.yml
        
        ```yaml
        server_role: database
        service_port: 3306
        ```
        
    
    ```yaml
    soso@DESKTOP-JM4DKDH:~/ansible-practice/ansible-study1$ ansible managed -i inventory.ini   -m ansible.builtin.debug   -a 'msg="host={{ inventory_hostname }}, role={{ server_role }}, port={{ service_port }}"'
    node1 | SUCCESS => {
        "msg": "host=node1, role=web, port=80"
    }
    node2 | SUCCESS => {
        "msg": "host=node2, role=web, port=80"
    }
    node4 | SUCCESS => {
        "msg": "host=node4, role=database, port=3306"
    }
    node5 | SUCCESS => {
        "msg": "host=node5, role=database, port=3306"
    }
    node3 | SUCCESS => {
        "msg": "host=node3, role=web, port=80"
    }
    node6 | SUCCESS => {
        "msg": "host=node6, role=database, port=3306"
    }
    ```
    

### 2-7) 참고 문헌

- https://docs.ansible.com/projects/ansible/latest/getting_started/get_started_inventory.html
- https://docs.ansible.com/projects/ansible/latest/inventory_guide/intro_inventory.html
- https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_vars_facts.html
- https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_variables.html
- https://docs.ansible.com/projects/ansible/latest/inventory_guide/intro_dynamic_inventory.html
- https://docs.ansible.com/projects/ansible/latest/collections/amazon/aws/aws_ec2_inventory.html
- https://docs.ansible.com/projects/ansible/latest/collections/amazon/aws/docsite/aws_ec2_guide.html