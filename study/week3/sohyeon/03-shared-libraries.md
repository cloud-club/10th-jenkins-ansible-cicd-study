# 3. Shared Libraries

## 3-1) Shared Library 구조화

```text
(root)
+- src                     # Groovy source files
|   +- org
|       +- foo
|           +- Bar.groovy  # for org.foo.Bar class
+- vars
|   +- foo.groovy          # for global 'foo' variable
|   +- foo.txt             # help for 'foo' variable
+- resources               # resource files (external libraries only)
|   +- org
|       +- foo
|           +- bar.json    # static helper data for org.foo.Bar
```

- 파이프라인은 외부 버전 관리 레포지토리에 정의하고 기존 파이프라인으로 불러와서 사용할 수 있는 Shared Libraries 생성 기능을 지원한다.
- 아래 디렉토리는 shared libraries 레포지토리의 루트에 위치한다.

### src/

- 표준 Java 소스 디렉토리 구조와 같은 형태
- 파이프라인을 실행할 때 classpath에 추가된다.
- 재사용 가능한 클래스 및 복잡한 비즈니스 로직을 객체지향 방식으로 작성할 때 사용된다.

### vars/

- 파이프라인에서 변수로 노출되는 스크립트 파일 저장
- 파일의 이름이 곧 파이프라인 내에서의 변수 이름이 된다.
- .groovy 파일의 기본 이름은 Groovy 식별자여야 하며, 매칭되는 .txt 파일에 설명을 넣을 수 있다.
- 해당 디렉토리에 있는 Groovy 소스 파일들은 CPS transformation을 적용받는다.

### resources/

- 외부 라이프러리에서 관련 non-Groovy 파일들을 로드하기 위해 libraryResource 스텝을 사용할 수 있다.
- 현재 이 기능은 내부 라이브러리에서는 지원하지 않는다.

## 3-2) Groovy 기반 커스텀 글로벌 함수 및 클래스 모듈화 (DRY 원칙)

- DRY : Don’t Repeat Yourself
- 중복을 줄이고 코드를 DRY하게 유지하기 위해 여러 프로젝트 간에 파이프라인의 일부를 공유하는 것이 유용한 경우가 많다.

### Shared Library 호출

- **Load implicitly**
    - 해당 방법으로 표시된 shared library는 파이프라인이 해당 라이브러리에 정의된 클래스나 글로벌 변수를 즉시 사용할 수 있도록 허용한다.
    - jenkins가 빌드를 시작할 때 자동으로 해당 라이브러리를 로딩한다.
- @Library (정적 호출)
    - 자동 로드 설정이 되어 있지 않은 다른 shared library에 접근하기 위한 어노테이션이며 관례적으로 import 문 위에 작성한다.
    - 직접 지정해서 명시적으로 가져오는 방식
    - 글로벌 변수(vars/)만 정의하는 shared library이거나 글로벌 변수가 필요한 Jenkinsfile의 경우, `@Library('my-shared-library') _` 형태의 어노테이션 패턴을 사용하면 코드를 간결하게 유지하는 데 유용하다.
- 동적 호출
    - vars/ 디렉토리에 있는 글로벌 변수나 함수만 사용하는 것이 목적이라면 `library 'my-shared-library’` 와 같은 방식으로 로드하여 해당 라이브러리의 모든 글로벌 변수를 스크립트에서 자유롭게 사용할 수 있다.
    - src/ 디렉토리의 클래스는 컴파일 시점이 지나 정적 import가 불가능하여, `library('my-shared-library').com.mycorp.pipeline.Utils.someStaticMethod()` 와 같은 형태와 같이 전체 패키지 경로로 동적 접근해야 한다.

### 라이브러리 클래스

- sh나 git과 같은 파이프라인 스텝을 직접 호출할 수는 없다.
- 클래스 범위를 벗어난 영역에 메서드를 구현하여 파이프라인 스텝을 호출하게 만들 수는 있다.

    ```groovy
    // src/org/foo/Zot.groovy
    package org.foo
    
    def checkOutFrom(repo) {
      git url: "git@github.com:jenkinsci/${repo}"
    }
    
    return this
    
    // 이를 scripted pipeline에서 아래와 같이 호출할 수 있다.
    def z = new org.foo.Zot()
    z.checkOutFrom(repo)
    ```

- 위 방법의 한계는 상위 클래스 선언을 막게 된다.
- 대안으로, this를 사용하여 생성자나 단일 메서드 내로 스텝 집합을 라이브러리 클래스에 명시적으로 전달할 수 있다.

    → **파이프라인 실행 주체(this)를 클래스 내부로 전달받아 처리하는 기법**

    - this를 사용하여 스텝 전달하기

        ```groovy
        package org.foo
        class Utilities implements Serializable {
            def steps
            Utilities(steps) {this.steps = steps}
            def mvn(args) {
                steps.sh "${steps.tool 'Maven'}/bin/mvn -o ${args}"
            }
        }
        ```

    - 위와 같이 클래스 내에 상태를 저장할 때는 클래스가 반드시 Serializable 인터페이스를 구현해야 한다.
        - Serializable : 파일로 저장하거나 네트워크로 전송 가능한 형태로 변환하는 메커니즘
        - jenkins가 빌드 도중 일시 정지되거나 컨트롤러가 재시작된 후 재개될 때 객체 상태를 저장하기 위해서이다.
    - 라이브러리가 env와 같은 글로벌 변수에 접근해야 하는 경우에도 유사한 방식을 사용해야 한다.

## 3-3) Unit Testing for Shared Libraries (JenkinsPipelineUnit 프레임워크 기초)

### 앞의 내용과 연계

- shared libraries를 사용하면 jenkins를 통해 서로 다른 레포지토리의 파이프라인에서 공통 코드를 공유할 수 있다.
- Jenkins 설정에서 @Library 어노테이션이나 library 단계를 통해 가져온다.
- 외부 라이브러리를 사용하는 파이프라인 스크립트를 테스트하는 것은 shared library 코드가 별도의 레포지토리에 있기 때문에 간단하지 않다.

    → **JenkinsPipelineUnit**을 사용하면 shared library와 이 라이브러리에 의존하는 파이프라인을 단위 테스트할 수 있다.

### JenkinsPipelineUnit

- 라이브러리 정의 방식 (Fluent API)
    - 라이브러리 정의는 Jenkins Global Pipeline Libraries에서와 동일한 설정을 지정할 수 있는 fluent API를 통해 수행된다.
    - retriever 및 targetPath 필드를 지정하여 소스 수집 방식과 로컬에 저장될 경로를 설정한다.
    - defaultVersion (기본값: master), allowOverride (기본값: true), implicit (기본값: false)과 같은 속성을 설정할 수 있다.
- 소스 수집기 (Source Retrievers)
    - 이 프레임워크는 기본적이지만 유용한 두 가지 소스 수집기(gitSource, localSource)를 제공한다.
    - 또한 SourceRetriever 인터페이스를 구현하여 사용자 정의 수집기를 직접 작성할 수도 있다.
    - 라이브러리 자체를 단위 테스트할 때는 projectSource 수집기를 활용하여 프로젝트 루트 폴더(src 및 vars가 위치한 곳)에서 라이브러리 파일을 직접 로드할 수 있다.
- 테스트 실행
    - 테스트를 실행하면 프레임워크가 Git 레포지토리 등에서 소스를 가져와 라이브러리 내의 클래스, 스크립트, 글로벌 변수 및 리소스를 로드한다.

## 3-4) 참고 문헌

- <https://www.jenkins.io/doc/book/pipeline/shared-libraries/>
- <https://github.com/jenkinsci/JenkinsPipelineUnit/blob/master/README.md>
