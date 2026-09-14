# Playbook & Variable

## Playbook

- 모듈 호출을 YAML로 순서대로 기술한 파일이다. Ad-hoc 명령이 일회성이라면, Playbook은 재사용 가능한 작업 정의다.
- 구조는 Play → Task → Module 순이다.
  * **Play**: 어떤 호스트 그룹에 무엇을 할지 정의하는 단위
  * **Task**: Play 안의 개별 작업. 모듈 하나를 호출한다.
  * **Module**: 실제 실행되는 코드

## 실습에서 작성한 Playbook

```yaml
- name: 웹 서버 기본 구성
  hosts: webservers
  vars:
    app_dir: /opt/myapp

  tasks:
    - name: 패키지 목록 갱신
      apt:
        update_cache: yes

    - name: nginx 설치
      apt:
        name: nginx
        state: present

    - name: 애플리케이션 디렉터리 생성
      file:
        path: "{{ app_dir }}"
        state: directory
        mode: '0755'

    - name: 인덱스 파일 배포
      copy:
        content: "Hello from {{ inventory_hostname }}\n"
        dest: "{{ app_dir }}/index.html"
        mode: '0644'

    - name: 멱등하지 않은 예 (command 모듈)
      command: echo "always changed"
```

### 주요 키워드

- `hosts` — 대상 그룹. Inventory에 정의한 그룹명을 쓴다.
- `vars` — Play 범위 변수
- `tasks` — 실행할 작업 목록
- `name` — 실행 시 출력되는 설명. 생략 가능하지만 로그 가독성을 위해 붙이는 것이 좋다.
- `gather_facts` — 대상 서버 정보 수집 여부. 기본값은 `yes`이며, 불필요하면 `no`로 실행 시간을 줄일 수 있다.

### Gathering Facts

- Playbook 실행 시 첫 태스크로 자동 실행되어 대상 서버의 OS, IP, 메모리, 디스크 등의 정보를 수집한다.
- 수집된 값은 변수처럼 사용할 수 있다. 예: `ansible_distribution`, `ansible_default_ipv4.address`
- 조건부 실행(`when: ansible_distribution == "Ubuntu"`)의 근거가 된다.

## Variable

### 정의 위치

- **Inventory 변수**: `[all:vars]` 또는 호스트 행에 직접 지정
- **`group_vars/<그룹명>.yml`**: 해당 그룹의 모든 호스트에 적용
- **`host_vars/<호스트명>.yml`**: 특정 호스트에만 적용
- **Playbook `vars:`**: Play 범위
- **Task `vars:`**: 해당 태스크 범위
- **`--extra-vars`**: 명령줄 전달. 가장 높은 우선순위

### 특수 변수

- `inventory_hostname` — Inventory에 정의된 호스트 이름
- `group_names` — 해당 호스트가 속한 그룹 목록
- `hostvars` — 다른 호스트의 변수에 접근

### 실습: 우선순위 확인

`group_vars/all.yml`
```yaml
app_dir: /opt/default
env_name: study
```

`group_vars/webservers.yml`
```yaml
app_dir: /opt/webapp
app_port: 8080
```

확인용 Playbook
```yaml
- name: 변수 우선순위 확인
  hosts: webservers
  tasks:
    - name: 현재 값 출력
      debug:
        msg: "app_dir={{ app_dir }} env={{ env_name }}"
```

실행 결과
```
ok: [node1] => {
    "msg": "app_dir=/opt/webapp env=study"
}
ok: [node2] => {
    "msg": "app_dir=/opt/webapp env=study"
}
```

### 해석

- `app_dir`은 `all.yml`과 `webservers.yml` 양쪽에 정의되어 있는데, **더 구체적인 그룹인 `webservers` 쪽이 이겼다.**
- `env_name`은 `webservers.yml`에 없으므로 `all.yml`에서 올라왔다.
- 즉 변수는 덮어쓰기 방식이며, 범위가 좁을수록 우선한다.
- 다만 실제 우선순위 규칙은 20단계가 넘는다. 공식 문서에 전체 순서가 정리되어 있으며, 복잡한 구성에서는 `-e`(extra-vars)가 항상 최상위라는 점을 기준으로 삼는 편이 안전하다.

## Jinja2 템플릿

- `{{ }}` 안에서 변수를 참조하고 필터를 적용할 수 있다.
- `{{ app_dir }}/index.html` 처럼 문자열 조합이 가능하다.
- 필터 예: `{{ name | default('unknown') }}`, `{{ list | length }}`
- `when:` 조건절과 `loop:` 반복에서도 Jinja2 표현식을 쓴다.

## 변수와 보안

- 변수 파일은 대개 SCM에 함께 커밋된다. 따라서 `group_vars/`나 `host_vars/`에 비밀번호나 토큰을 평문으로 넣으면 저장소에 그대로 남는다.
- 이 문제를 다루는 것이 4주차 주제인 Ansible Vault다.
- 3주차 시점에서 확인한 것은, 변수 자체에는 아무런 보호 장치가 없다는 점이다. 이어지는 03번 문서에서 실제로 확인했다.

## 참고 자료

- [Ansible 공식 문서 - Intro to playbooks](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_intro.html)
- [Ansible 공식 문서 - Using Variables](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_variables.html)
- [Ansible 공식 문서 - Variable precedence](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_variables.html#variable-precedence-where-should-i-put-a-variable)
