## **1. Role-Based Architecture**

---

### 1-1)Role 구조 이해 (`tasks/`, `handlers/`, `templates/`, `defaults/`, `vars/`, `files/`, `meta/`)

```
roles/
└── common/               # "Role"을 나타내는 디렉토리 계층 구조
    ├── tasks/
    │   └── main.yml      # 주요 실행 작업 파일 (필요 시 더 작은 파일 포함 가능)
    ├── handlers/
    │   └── main.yml      # 핸들러 정의 파일
    ├── templates/
    │   └── ntp.conf.j2   # template 모듈에서 사용하는 Jinja2 템플릿 (.j2)
    ├── files/
    │   ├── bar.txt       # copy 모듈에서 사용하는 정적 파일
    │   └── foo.sh        # script 모듈에서 사용하는 스크립트 파일
    ├── vars/
    │   └── main.yml      # 해당 Role과 관련된 고우선순위 변수
    ├── defaults/
    │   └── main.yml      # 해당 Role의 기본 저우선순위 변수
    ├── meta/
    │   └── main.yml      # Role 의존성 및 선택적 Galaxy 정보
    ├── library/          # Role 내 커스텀 모듈 (선택 사항)
    ├── module_utils/     # 모듈 지원용 커스텀 module_utils (선택 사항)
    └── lookup_plugins/   # 커스텀 플러그인 (예: lookup 등, 선택 사항)
```

**Role (역할)**

- Playbook 아티팩트(변수, 파일, 태스크, 핸들러 등)를 특정 표준 디렉토리 구조에 맞춰 모듈화하고 재사용 가능하게 그룹화한 구조.
- 웹 서비스 등의 자동화 작업을 기능별로 깔끔하게 조직화하여 관리 및 공유를 용이하게 만든다.
- **특정 기능을 구현하는 데 필요한 Task, 변수, 설정파일, Handler 등을 하나의 재사용 가능한 패키지처럼 묶는 것**

**디렉토리 및 주요 파일 역할**

- **자동 로딩 파일 (`main.yml`)**
    - Ansible은 각 서브 디렉토리 내에 있는 `main.yml` 파일을 기본적으로 로드하여 실행한다.
- **`tasks/`**
    - Role이 실행할 주요 작업(Task) 목록을 정의한다. (`tasks/main.yml`)
    - 필요한 경우 더 작은 Task 파일들을 포함(include)하여 구성할 수 있다.
- **`handlers/`**
    - 다른 Task의 작업 결과 변경사항이 생겨 트리거(`notify`)되었을 때 실행되는 작업(예: `restart ntpd`)을 정의한다.
    - Handlers는 Play가 끝나는 시점에 실행된다.
- **`templates/`**
    - `template` 리소스와 함께 사용하는 Jinja2 템플릿 파일들을 저장하며, 확장자는 `.j2`를 사용한다. (예: `ntp.conf.j2`)
- **`files/`**
    - `copy` 리소스용 정적 파일(예: `bar.txt`)이나 `script` 리소스용 스크립트 파일(예: `foo.sh`)을 저장한다.
- **`defaults/`**
    - Role에서 사용할 기본 변수를 정의한다. (`defaults/main.yml`)
    - 우선순위가 가장 낮은(lower priority) 변수로 제공되어 쉽게 오버라이드할 수 있다.
- **`vars/`**
    - Role과 관련된 일반 변수들을 정의한다. (`vars/main.yml`)
- **`meta/`**
    - Role 간의 의존성(Role dependencies) 및 선택적인 Galaxy 정보를 작성한다. (`meta/main.yml`)
- **기타 확장 디렉토리 (선택 사항)**
    - **`library/`**: Role 전용 커스텀 모듈을 포함할 수 있다.
    - **`module_utils/`**: 모듈을 지원하는 커스텀 모듈 유틸리티를 저장한다.
    - **`lookup_plugins/`** 등: Lookup 플러그인을 비롯한 다양한 유형의 Ansible 플러그인을 Role 내부에서 포함하여 사용할 수 있다.

**Role 및 플레이북 배치 및 구성 시 유의사항**

- 기본적으로 Ansible은 플레이북과 동일한 디렉토리 내의 `roles/` 서브 디렉토리에서 Role을 찾는다.
- 자동화할 태스크가 많아져 플레이북들을 별도의 `playbooks/` 서브 디렉토리로 이동할 경우, `ansible.cfg` 파일의 `roles_path` 설정을 통해 `roles/` 디렉토리 경로를 별도로 지정해야 한다.

---

### 1-2) `defaults/main.yml`과 `vars/main.yml`의 역할 및 Override 전략

```
[ Override 가능 여부 비교 ]

Command Line (--extra-vars)  ──► 최우선 적용 (모든 설정 덮어씀)
          │
     vars/main.yml           ──► 높은 우선순위 (역할 내부 변수 고정)
          │
    defaults/main.yml        ──► 최저 우선순위 (쉽게 재정의 가능)
```

**defaults/main.yml**

- Role(역할)에서 사용하는 기본값(Default Variables)을 정의하는 파일
- 변수 우선순위(Variable Precedence)에서 **가장 낮은 우선순위**를 가진다.
- 기본 구성값을 제공하면서, 외부(Playbook, Inventory, CLI 등)에서 사용자가 원하는 값으로 **언제든지 쉽게 덮어쓸 수 있도록(Override)** 설계할 수 있다.

**vars/main.yml**

- Role(역할) 내부에서 사용되는 고정성/중요 변수(Role Variables)를 정의하는 파일
- 변수 우선순위에서 **상당히 높은 우선순위**를 가진다.
- 해당 Role의 작동에 핵심적이고, 외부에서 쉽게 변경되면 안 되는 정적 매개변수나 내부 로직용 값을 정의할 때 사용한다.

**defaults와 vars의 역할 차이점**

- 재정의 유연성 (Override Flexibility)
    - `defaults/main.yml`: 사용자나 상위 Playbook에서 변수를 정의하면 즉시 Overridden되어 해당 새 값으로 대체된다.
    - `vars/main.yml`: 외부 Playbook이나 Inventory에서 동일한 변수를 정의하더라도 `vars/main.yml`의 값이 우선하므로 쉽게 변경되지 않는다.
- 사용 목적
    - `defaults`: "기본 설정은 제공하되, 원한다면 얼마든지 바꾸어 쓰세요"라는 유연한 인터페이스용.
    - `vars`: "Role 내부 실행 시 반드시 보장되어야 하는 고정 데이터"용.

**Override 전략 및 Best Practice**

- 기본값 활용 (Defaults-First Approach)
    - Role 제작 시 변경 가능성이 조금이라도 있는 설정값(포트 번호, 설치 경로, 계정명 등)은 `defaults/main.yml`에 우선 배치한다.
- 명확한 우선순위 통제
    - 절대 변경되지 말아야 하는 내부 파라미터는 `vars/main.yml`에 작성하여 외부 설정에 의한 예기치 못한 오작동을 방지한다.
- 최상위 강제 재정의 (Extra Vars)
    - 배포 시점이나 런타임 시에 임시로 변수를 강제 적용해야 하는 경우 CLI 실행 시 `--extra-vars` (`e`) 옵션을 사용하여 최우선으로 Override한다.

---

### 1-3) Role 기반 Playbook 모듈화 및 재사용

```
playbooks/
└── site.yml
roles/
└── common/
    ├── tasks/main.yml
    ├── handlers/main.yml
    ├── vars/main.yml
    ├── defaults/main.yml
    ├── meta/main.yml
    ├── files/
    └── templates/
```

**Ansible Role**

- Ansible artifacts(변수, 파일, 태스크, 핸들러 등)를 정의된 디렉토리 구조에 맞춰 그룹화하는 표준화된 단위
- 플레이북 작성 시 코드 중복을 줄이고 여러 프로젝트/호스트 간에 작업을 쉽고 재사용 가능하게 만들어 준다.

**Role의 표준 디렉토리 구조**

- roles 디렉토리 내에 개별 역할(예: `common`, `webtier`)별로 구조를 구성하며, 필요하지 않은 디렉토리는 생략 가능하다.
    - `tasks/main.yml`: Role 실행 시 실행될 핵심 태스크 목록
    - `handlers/main.yml`: 태스크 조건 충족 시 알림(notify)을 받아 실행되는 핸들러
    - `defaults/main.yml`: 우선순위가 가장 낮게 설정된 기본 변수 정의
    - `vars/main.yml`: Role 내에서 우선순위가 높게 적용되는 변수 정의
    - `files/` & `templates/`: Copy 또는 Template 태스크에서 참조할 파일 및 Jinja2 템플릿 저장
    - `meta/main.yml`: 의존성(Dependencies) 및 메타데이터 정의

**Role 재사용 방식**

- **Play 수준에서의 사용 (`roles:`)**
    - Playbook 상단에 정적으로 정의하여 사용하는 고전적 방식
    - Playbook 파싱 시점에 해석되며, `pre_tasks` -> `roles` -> `tasks` -> `post_tasks` 순서로 정해진 워크플로우에 따라 실행된다.
- **Dynamic Reuse (`include_role`)**
    - `tasks` 섹션 내 어디서든 동적으로 Role을 불러와 실행
    - 조건문(`when`)이나 반복문과 조합하여 특정 조건에서만 동작하도록 유연하게 제어 가능
- **Static Reuse (`import_role`)**
    - `tasks` 섹션 내에서 정적으로 Role을 가져와 정해진 순서대로 실행
    - Playbook 파싱 단계에서 포함되어 전체 태스크 태그 inheritance 등에 영향을 줌

**Role 활용 및 장점**

- **모듈화 및 관심사 분리**: 기능별(웹 서버, DB 서버, 공통 설정 등)로 역할을 나눌 수 있어 유지 보수 부담을 줄임
- **공유 및 확장성**: [Ansible Galaxy]를 통해 잘 만들어진 Role을 배포하고 커뮤니티 플레이북을 손쉽게 다운로드받아 재사용 가능
- **변수 파라미터화**: Role을 호출할 때 변수(`vars`)를 다르게 전달하여 동일한 Role을 목적에 맞게 재사용

---

### 1-4) `include_role`, `import_role` 기본 개념

```yaml
Playbook Execution
│
├──── include_role (Dynamic)  ──► Executed at runtime (task-by-task)
│
└──── import_role  (Static)   ──► Parsed at playbook parsing time

include_role
= 프로그램 실행 중 필요한 모듈을 가져오는 느낌

import_role
= 프로그램 실행 전에 코드 구조에 미리 합쳐놓는 느낌
```

**ansible.builtin.include_role**

- 역할(Role)을 동적(Dynamic)으로 로드하고 실행하는 모듈.
- 플레이북 실행 시점(Runtime)에 해당 태스크에 도달해야 역할을 불러와 실행함.
    
    ```yaml
    Playbook 실행
          ↓
    Task 1
          ↓
    Task 2
          ↓
    include_role 만남
          ↓
    그때 nginx Role 로드
          ↓
    nginx Task 실행
    ```
    

**ansible.builtin.import_role**

- 역할(Role)을 정적(Static)으로 로드하고 실행하는 모듈.
- 플레이북이 파싱되는 시점(Parsing time)에 미리 역할을 불러와 플레이북 전체 구조에 포함시킴.

```yaml
실행 중 조건에 따라 Role 호출 여부가 달라져야 한다
                ↓
          include_role

Role 구조를 실행 전에 정적으로 확정한다
                ↓
          import_role
```

**동적 및 정적 처리 방식의 주요 차이점**

- **실행 및 파싱 시점 (Execution Time)**
    - include_role: 플레이북이 실행되는 도중에 동적으로 역할을 평가하고 호출함.
    - import_role: 플레이북을 실행하기 전, 파싱 단계에서 미리 정적으로 역할을 불러옴.
- **조건문 및 루프 적용 (Conditionals & Loops)**
    - include_role: `when` 조건문이나 `loop`와 같은 키워드가 `include_role` 문 자체에 적용되며, 루프 내부에서 변수를 넘겨 역할을 반복 호출하는 데 유용함.
    - import_role: 문장 자체에는 조건을 적용하지 않고, 하위의 각 태스크(imported tasks)로 조건과 루프가 전달(Inherit)되어 individual task 단위로 동작함.
- **변수 노출 범위 (Variable Exposure)**
    - include_role: 기본적으로 역할의 변수(`vars`, `defaults`)는 실행 이후의 태스크에만 영향을 주며, `public: true` 옵션을 통해 플레이에 노출 가능함.
    - import_role: 파싱 시점에 로드되므로, 역할의 변수가 플레이 전체에 고정으로 노출됨. 따라서 해당 `import_role` 태스크 **이전에 실행되는 역할 및 태스크에서도 해당 변수에 접근 가능**함.

**사용 시 주요 파라미터 (Parameters)**

- name (필수)
    - 실행할 역할(Role)의 이름을 지정.
- tasks_from / vars_from / defaults_from / handlers_from
    - 역할 내부 디렉토리에서 기본 파일(`main.yml`) 대신 로드할 특정 파일명을 지정 (`Default: main`).
- allow_duplicates
    - 동일한 파라미터로 동일한 역할을 한 플레이 내에서 여러 번 실행할 수 있게 허용할지 여부 설정 (`Default: true`).
- rolespec_validate
    - 역할에 인자 규격(`argument_spec`)이 정의된 경우, 실행 전 검증 수행 여부를 설정 (`Default: true`).

**주요 특징 및 사용 제약 사항**

- **실행 위치 제약 및 핸들러 동작**
    - `pre_tasks`, `tasks`, `post_tasks` 영역에서만 사용할 수 있으며, `handlers` 영역에서는 직접 호출할 수 없음.
    - 단, `import_role`을 통해 불러온 역할 내의 핸들러는 플레이 전체에서 사용 가능한 상태로 등록됨.
- **키워드 제한**
    - `until`, `retries`, `poll`, `async` 등 일부 키워드는 `import_role` 문 자체에 적용되지 않음.
- **FQCN 사용 권장**
    - 모듈 이름 충돌을 방지하고 명확한 참조를 위해 `ansible.builtin.import_role` 형태의 풀 네임(FQCN) 사용을 권장함.

---

### 1-5) Ansible Galaxy 및 `requirements.yml`을 활용한 Role / Collection 의존성 관리

```
Ansible Control Node
    │
    ├─► ansible-galaxy CLI / requirements.yml
    │         │
    │         ▼ (Download & Install)
    ├─► Ansible Galaxy / Git Repository / Web Server
    │         │
    │         ▼
    └─► Local Environment (~/.ansible/roles 또는 collections)
```

**Ansible Galaxy**

- **Community 개발자들이 제작한 Collection 및 Role을 공유하고 찾아서 다운로드할 수 있는 무료 웹사이트 및 중앙 허브.**
- 프로젝트 시작 시 검증된 구성요소를 활용하여 자동화 구축을 빠르게 시작할 수 있도록 지원.
- 기본적으로 CLI 명령어 실행 시 `https://galaxy.ansible.com` 서버 API와 통신하며, `ansible.cfg` 설정을 통해 사내 자체 Galaxy 서버 주소로 변경 가능.

**Role과 Collection의 구분**

- **Role**: 재사용 가능한 작업, 변수, 파일, 핸들러 등의 디렉터리 구조 묶음.
- **Collection**: Role뿐만 아니라 Playbook, Module, Plugin 등 종합적인 자동화 패키지를 포함하는 표준 배포 형식.

**ansible-galaxy CLI 기본 명령어**

- **Role 검색 및 정보 확인**
    - `ansible-galaxy role search <keyword>`: Galaxy 웹사이트 상의 Role 검색.
    - `ansible-galaxy role info <namespace.role_name>`: 특정 Role의 버전, 작성자, 리포지토리 등 세부 정보 조회.
- **Role 설치 및 관리**
    - `ansible-galaxy role install <namespace.role_name>`: 단일 Role 설치.
    - `ansible-galaxy role list`: 현재 시스템에 설치된 Role 목록 및 버전 확인.
    - `ansible-galaxy role remove <namespace.role_name>`: 설치된 Role 삭제.
- **설치 경로 지정**
    - 기본 설치 경로: `~/.ansible/roles`, `/usr/share/ansible/roles`, `/etc/ansible/roles` 중 쓰기 권한이 있는 첫 번째 경로.
    - `-roles-path` 옵션이나 `ANSIBLE_ROLES_PATH` 환경 변수를 사용해 현재 작업 디렉터리 등 특정 위치로 변경 가능.

**requirements.yml을 통한 의존성 일괄 관리**

- 프로젝트에 필요한 여러 Role과 Collection을 `requirements.yml` (또는 `.yaml`) 파일에 선언하여 일괄 설치 및 버전 관리.
- 실행 명령어: `ansible-galaxy install -r requirements.yml`

**requirements.yml 작성 주요 속성**

- `src`: Role의 출처 (Galaxy의 `namespace.role_name`, Git URL, 또는 웹서버 파일 링크). 필수 항목.
- `name`: 로컬에 다운로드되어 저장될 Role 이름 재정의.
- `version`: 다운로드할 특정 버전 지정 (Release Tag, Commit Hash, Branch 이름).
- `scm`: SCM 종류 지정 (`git` 또는 `hg`, 기본값은 `git`).

**Role 및 Collection 혼합 선언 예시**

- 단일 `requirements.yml` 파일 내에서 `roles`와 `collections` 항목을 구분하여 동시에 관리 가능.

```
---
roles:
  # Ansible Galaxy에서 설치
  - name: geerlingguy.java
    version: "1.9.6"

  # Git 리포지토리에서 설치
  - src: https://github.com/bennojoy/nginx
    version: main
    name: nginx_role

collections:
  # Ansible Galaxy에서 Collection 설치
  - name: community.general
    version: ">=7.0.0"
    source: https://galaxy.ansible.com
```

**Role 의존성 자동 처리 (Role Dependencies)**

- 특정 Role이 실행되기 위해 선행되어야 하는 의존성을 자체 파일 내에 정의하여 자동 설치 및 실행 관리.
- **`meta/requirements.yml` 활용**: `requirements.yml`과 동일한 형식으로 의존 대상 작성.
- **`meta/main.yml` 활용**: `dependencies` 섹션 하위에 필요한 Role 목록 명시. Playbook 실행 시 메인 Role보다 먼저 순차적으로 실행됨.

---

### 참고 문헌

- https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_reuse_roles.html
- https://docs.ansible.com/projects/ansible/latest/tips_tricks/sample_setup.html
- https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_variables.html
- https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_reuse_roles.html
- https://docs.ansible.com/projects/ansible-core/2.17/collections/ansible/builtin/include_role_module.html
- https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/import_role_module.html
- https://docs.ansible.com/projects/ansible-core/devel/galaxy/user_guide.html