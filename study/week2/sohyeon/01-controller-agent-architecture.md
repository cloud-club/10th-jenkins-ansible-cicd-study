## 1. Controller / Agent Architecture

### 1-1) Controller-Agent 분리 및 통신 방식

**Controller**

- Jenkins Agent를 관리하고, Agent의 작업을 오케스트레이션하며, Agent에서의 작업을 예약하고 모니터링하는 노드

**Agent**

- Jenkins Controller의 요청에 따라 작업을 수행하는 노드
- Java가 설치되어 있어야 하며 Jenkins Controller와 네트워크가 연결되어 있어야 한다.

```jsx
# Controller-Agent 구조 예시

						      Controller
										  |
						--------------------
						|         |        |
					Agent1    Agent2   Agent3
					(Linux)  (Docker)  (ARM64)

# Controller : Agent에게 작업 할당
# Agent : 작업 수
```

**Agent의 목적**

- Jenkins 아키텍처는 분산 빌드 환경을 위해 설계되어 있으며, 각 빌드마다 서로 다른 환경을 사용할 수 있다. 이를 여러 Agent가 병렬로 작업을 실행하여 현실화 시켜준다.
- Agent에 label을 붙여서 작업을 분류하여 할당할 수 있다.

**Controller 격리**

- Jenkins에서의 빌드는 built-in 노드보다 Agent에서 실행되는 것이 권장된다.
- built-in 노드에서 실행되는 빌드는 Jenkins 프로세스와 동일한 수준의 파일 시스템 접근 권한을 가지게 되므로 보안의 측면에서 좋지 않다.
  - built-in 노드에서 실행되는 것을 방지하기 위해서 **Manage Jenkins → Nodes and Clouds** 탭으로 이동하여 built-in 노드의 executors의 수를 0으로 지정한다.
- Agent에서 Controller에게 어떠한 요청을 보내는 것도 가능하다. 이때 Agent가 악의적인 목적으로 프로세스를 탈취당할 가능성이 있기 때문에 이를 방지하기 위하여 Agent는 Controller에게 악의적인 명령을 전송하지 못하도록 차단되어 있다.

**Controller와 Agent의 연결**

Agent로 인식되기 위해서는 Controller와 양방향 통신을 설정하는 특정 Agent 프로그램을 실행시켜야 한다.

| 연결 방식         | 설명                                           |
| ----------------- | ---------------------------------------------- |
| **SSH Connector** | • Controller가 Agent로 접속하는 Outbound 방식. |

• Agent가 SSH connector를 사용하도록 구성한다.
• Jenkins에는 내장 SSH 클라이언트 구현이 있으므로 Jenkins Controller는 SSH 서버가 설치된 어떤 기계와도 쉽게 통신할 수 있다.
• Controller의 공개 키가 Agent의 승인된 키에 속하기만 하면 가능하다. |
| **Inbound Connector** | • Agent가 Controller에 연결하는 Inbound 형식으로, 과거에는 JNLP Agent라고 불렸다.
• TCP 포트를 활용하여 Inbound Agent와 통신하는 방식이다. (Jenkins 2.0부터 해당 포트는 기본적으로 비활성화 되어 있다).
• Jenkins 2.217 버전부터는 Inbound Agent가 WebSocket 전송 방식을 사용하여 Jenkins에 연결할 수 있으며, 이 경우에는 추가 TCP 포트를 활성화하거나 특별한 보안 설정을 할 필요 없다. |

### 1-2) Dynamic Agent Provisioning: Docker Agent 설정

**Docker Agent를 SSH를 사용해서 Jenkins에 연결하는 방법**

- 필요 환경: Java, Jenkins, Docker, SSH key pair
- `docker-ssh-agent` image를 사용하여 Agent 컨테이너 생성

```bash
docker run -d --rm --name=agent1 -p 22:22 \
-e "JENKINS_AGENT_SSH_PUBKEY=<your_public_key>" \
jenkins/ssh-agent:alpine-jdk21
```

- Jenkins 대시보드에서 새 노드를 생성 (Label Expression은 `agent1`으로)

**Jenkins Pipeline으로 Docker 사용하기**

- Pipeline으로 Docker의 이미지를 사용하는 방식
- `agent { docker { ... } }` 의 구문을 통해 특정 Docker 이미지를 실행환경으로 지정한다.
- `reuseNode`를 사용하면 기존 워크스페이스와 노드를 그대로 재사용할 수 있다.
  - Stage 간의 파일 동기화가 필요한 경우
- 데이터를 캐싱하여 컨테이너나 의존성 등의 반복 다운로드를 방지할 수 있다.
- 다중 컨테이너를 사용하여 여러 기술을 사용할 수 있다.
- Dockerfile을 직접 빌드할 수 있다.

### 1-3) Controller-Agent 분리 실습 (로컬 실습)

```jsx
Jenkins Controller
    │
    │ SSH
    ├──────────────→ wsl-agent
    │                 사용자: jenkins-agent
    │                 label: linux-1
    │
    └──────────────→ wsl-agent-2
                      사용자: jenkins-agent-2
                      label: linux-2
```

**1단계) Label을 이용해서 특정 Agent에서 실행하기**

```jsx
pipeline {
    agent {
        label 'wsl-agent'
    }

    stages {
        stage('Check Agent') {
            steps {
                sh '''
                    echo "=== Agent Information ==="
                    whoami
                    hostname
                    pwd
                    uname -a
                '''
            }
        }
    }
}
```

```jsx
Started by user Sohyeon Sim

[Pipeline] Start of Pipeline
[Pipeline] node
Running on wsl-agent
 in /home/jenkins-agent/workspace/agent-test-260907
[Pipeline] {
[Pipeline] stage
[Pipeline] { (Check Agent)
[Pipeline] sh
+ echo === Agent Information ===
=== Agent Information ===
+ whoami
jenkins-agent
+ hostname
DESKTOP-JM4DKDH
+ pwd
/home/jenkins-agent/workspace/agent-test-260907
+ uname -a
Linux DESKTOP-JM4DKDH 5.15.167.4-microsoft-standard-WSL2 #1 SMP Tue Nov 5 00:21:55 UTC 2024 x86_64 x86_64 x86_64 GNU/Linux
[Pipeline] }
[Pipeline] // stage
[Pipeline] }
[Pipeline] // node
[Pipeline] End of Pipeline
Finished: SUCCESS

```

**2단계) 두 번째 Agent 만들기 (jenkins-agent-2)**

```jsx
# WSL에서 두 번째 사용자 생성

soso@DESKTOP-JM4DKDH:~/jenkins-study$ sudo adduser jenkins-agent-2
[sudo] password for soso:
info: Adding user `jenkins-agent-2' ...
info: Selecting UID/GID from range 1000 to 59999 ...
info: Adding new group `jenkins-agent-2' (1003) ...
info: Adding new user `jenkins-agent-2' (1003) with group `jenkins-agent-2 (1003)' ...
info: Creating home directory `/home/jenkins-agent-2' ...
info: Copying files from `/etc/skel' ...
New password:
Retype new password:
passwd: password updated successfully
Changing the user information for jenkins-agent-2
Enter the new value, or press ENTER for the default
        Full Name []:
        Room Number []:
        Work Phone []:
        Home Phone []:
        Other []:
Is the information correct? [Y/n] Y
info: Adding new user `jenkins-agent-2' to supplemental / extra groups `users' ...
info: Adding user `jenkins-agent-2' to group `users' ...

soso@DESKTOP-JM4DKDH:~/jenkins-study$ id jenkins-agent-2
uid=1003(jenkins-agent-2) gid=1003(jenkins-agent-2) groups=1003(jenkins-agent-2),100(users)

soso@DESKTOP-JM4DKDH:~/jenkins-study$ ls -ld /home/jenkins-agent-2
drwxr-x--- 2 jenkins-agent-2 jenkins-agent-2 4096 Sep  7 13:10 /home/jenkins-agent-2

soso@DESKTOP-JM4DKDH:~/jenkins-study$ ssh jenkins-agent-2@localhost
jenkins-agent-2@localhost's password:
Welcome to Ubuntu 24.04.4 LTS (GNU/Linux 5.15.167.4-microsoft-standard-WSL2 x86_64)

 * Documentation:  https://help.ubuntu.com
 * Management:     https://landscape.canonical.com
 * Support:        https://ubuntu.com/pro

 System information as of Mon Sep  7 13:11:41 KST 2026

  System load:  0.29                Processes:             62
  Usage of /:   0.9% of 1006.85GB   Users logged in:       1
  Memory usage: 28%                 IPv4 address for eth0: 172.25.146.168
  Swap usage:   0%

 * Canonical Workshop gives developers fast, composable, reproducible, and
   secure developer environments that are perfect for agentic workflows.

   https://ubuntu.com/workshop

The programs included with the Ubuntu system are free software;
the exact distribution terms for each program are described in the
individual files in /usr/share/doc/*/copyright.

Ubuntu comes with ABSOLUTELY NO WARRANTY, to the extent permitted by
applicable law.

Welcome to Ubuntu 24.04.4 LTS (GNU/Linux 5.15.167.4-microsoft-standard-WSL2 x86_64)

 * Documentation:  https://help.ubuntu.com
 * Management:     https://landscape.canonical.com
 * Support:        https://ubuntu.com/pro

 System information as of Mon Sep  7 13:11:41 KST 2026

  System load:  0.29                Processes:             62
  Usage of /:   0.9% of 1006.85GB   Users logged in:       1
  Memory usage: 28%                 IPv4 address for eth0: 172.25.146.168
  Swap usage:   0%

 * Canonical Workshop gives developers fast, composable, reproducible, and
   secure developer environments that are perfect for agentic workflows.

   https://ubuntu.com/workshop

This message is shown once a day. To disable it please create the
/home/jenkins-agent-2/.hushlogin file.
jenkins-agent-2@DESKTOP-JM4DKDH:~$ whoami
jenkins-agent-2
jenkins-agent-2@DESKTOP-JM4DKDH:~$ pwd
/home/jenkins-agent-2
jenkins-agent-2@DESKTOP-JM4DKDH:~$ exit
logout
Connection to localhost closed.

*/
```

```jsx
# 두 번째 Agent용 SSH 키 만들기

soso@DESKTOP-JM4DKDH:~/jenkins-study$ sudo cat /var/lib/jenkins/.ssh/id_ed25519_agent2
cat: /var/lib/jenkins/.ssh/id_ed25519_agent2: No such file or directory

soso@DESKTOP-JM4DKDH:~/jenkins-study$ sudo ls -la /var/lib/jenkins/.ssh
total 24
drwxrwxr-x  2 jenkins jenkins 4096 Aug 31 17:27 .
drwxr-xr-x 23 jenkins jenkins 4096 Sep  7 13:12 ..
-rw-------  1 jenkins jenkins  419 Aug 31 17:27 id_ed25519
-rw-r--r--  1 jenkins jenkins  106 Aug 31 17:27 id_ed25519.pub
-rw-------  1 jenkins jenkins  978 Aug 31 17:03 known_hosts
-rw-r--r--  1 jenkins jenkins  142 Aug 31 17:03 known_hosts.old

soso@DESKTOP-JM4DKDH:~/jenkins-study$ sudo -u jenkins ssh-keygen -t ed25519 -f /var/lib/jenkins/.ssh/id_ed25519_agent2
Generating public/private ed25519 key pair.
Enter passphrase (empty for no passphrase):
Enter same passphrase again:
Your identification has been saved in /var/lib/jenkins/.ssh/id_ed25519_agent2
Your public key has been saved in /var/lib/jenkins/.ssh/id_ed25519_agent2.pub
The key fingerprint is:
SHA256:CeQvB2EkpDRIPyFfRAJuGNkNuPYStJcyqfPbcDd714w jenkins@DESKTOP-JM4DKDH
The key's randomart image is:
+--[ED25519 256]--+
|oO=*===          |
|*+=o== .         |
|o+++. +          |
|oB o.  + .       |
|o *   . S        |
|o. .   o         |
| oo . o    +     |
|  .+ . o. E o    |
|  ... .. .       |
+----[SHA256]-----+

soso@DESKTOP-JM4DKDH:~/jenkins-study$ sudo ls -l /var/lib/jenkins/.ssh/
total 24
-rw------- 1 jenkins jenkins 419 Aug 31 17:27 id_ed25519
-rw-r--r-- 1 jenkins jenkins 106 Aug 31 17:27 id_ed25519.pub
-rw------- 1 jenkins jenkins 419 Sep  7 13:16 id_ed25519_agent2
-rw-r--r-- 1 jenkins jenkins 105 Sep  7 13:16 id_ed25519_agent2.pub
-rw------- 1 jenkins jenkins 978 Aug 31 17:03 known_hosts
-rw-r--r-- 1 jenkins jenkins 142 Aug 31 17:03 known_hosts.old

soso@DESKTOP-JM4DKDH:~/jenkins-study$ sudo cat /var/lib/jenkins/.ssh/id_ed25519_agent2.pub
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHgaq9tXp3qFd/cSmHEXCqOIjVuof3SumARUDjdKjweV jenkins@DESKTOP-JM4DKDH

soso@DESKTOP-JM4DKDH:~/jenkins-study$ sudo mkdir -p /home/jenkins-agent-2/.ssh

soso@DESKTOP-JM4DKDH:~/jenkins-study$ sudo nano /home/jenkins-agent-2/.ssh/authorized_keys

soso@DESKTOP-JM4DKDH:~/jenkins-study$ sudo chown -R jenkins-agent-2:jenkins-agent-2 /home/jenkins-agent-2/.ssh
soso@DESKTOP-JM4DKDH:~/jenkins-study$ sudo chmod 700 /home/jenkins-agent-2/.ssh
soso@DESKTOP-JM4DKDH:~/jenkins-study$ sudo chmod 600 /home/jenkins-agent-2/.ssh/authorized_keys

soso@DESKTOP-JM4DKDH:~/jenkins-study$ ls -la /home/jenkins-agent-2/.ssh
ls: cannot access '/home/jenkins-agent-2/.ssh': Permission denied

soso@DESKTOP-JM4DKDH:~/jenkins-study$ sudo ls -la /home/jenkins-agent-2/.ssh
total 12
drwx------ 2 jenkins-agent-2 jenkins-agent-2 4096 Sep  7 13:19 .
drwxr-x--- 4 jenkins-agent-2 jenkins-agent-2 4096 Sep  7 13:17 ..
-rw------- 1 jenkins-agent-2 jenkins-agent-2  106 Sep  7 13:19 authorized_keys

soso@DESKTOP-JM4DKDH:~/jenkins-study$ sudo -u jenkins ssh -i /var/lib/jenkins/.ssh/id_ed25519_agent2 jenkins-agent-2@localhost
Welcome to Ubuntu 24.04.4 LTS (GNU/Linux 5.15.167.4-microsoft-standard-WSL2 x86_64)

 * Documentation:  https://help.ubuntu.com
 * Management:     https://landscape.canonical.com
 * Support:        https://ubuntu.com/pro

 System information as of Mon Sep  7 13:19:59 KST 2026

  System load:  0.04                Processes:             63
  Usage of /:   0.9% of 1006.85GB   Users logged in:       1
  Memory usage: 29%                 IPv4 address for eth0: 172.25.146.168
  Swap usage:   0%

 * Canonical Workshop gives developers fast, composable, reproducible, and
   secure developer environments that are perfect for agentic workflows.

   https://ubuntu.com/workshop
Last login: Mon Sep  7 13:11:42 2026 from 127.0.0.1
jenkins-agent-2@DESKTOP-JM4DKDH:~$ whoami
jenkins-agent-2
jenkins-agent-2@DESKTOP-JM4DKDH:~$ pwd
/home/jenkins-agent-2
jenkins-agent-2@DESKTOP-JM4DKDH:~$ exit
logout
Connection to localhost closed.

soso@DESKTOP-JM4DKDH:~/jenkins-study$ sudo cat /var/lib/jenkins/.ssh/id_ed25519_agent2
-----BEGIN OPENSSH PRIVATE KEY-----
***
-----END OPENSSH PRIVATE KEY-----
```

```jsx
Warning: no key algorithms provided; JENKINS-42959 disabled
SSHLauncher{host='localhost', port=22, credentialsId='jenkins-agent-2-ssh', jvmOptions='', javaPath='', prefixStartSlaveCmd='', suffixStartSlaveCmd='', launchTimeoutSeconds=60, maxNumRetries=10, retryWaitTime=15, sshHostKeyVerificationStrategy=hudson.plugins.sshslaves.verifiers.KnownHostsFileKeyVerificationStrategy, tcpNoDelay=true, trackCredentials=true}
[09/07/26 13:21:36] [SSH] Opening SSH connection to localhost:22.
Searching for localhost in /var/lib/jenkins/.ssh/known_hosts
Searching for localhost:22 in /var/lib/jenkins/.ssh/known_hosts
[09/07/26 13:21:36] [SSH] SSH host key matches key in Known Hosts file. Connection will be allowed.
[09/07/26 13:21:36] [SSH] Authentication successful.
[09/07/26 13:21:36] [SSH] The remote user's environment is:
BASH=/usr/bin/bash
BASHOPTS=checkwinsize:cmdhist:complete_fullquote:extquote:force_fignore:globasciiranges:globskipdots:hostcomplete:interactive_comments:patsub_replacement:progcomp:promptvars:sourcepath
BASH_ALIASES=()
BASH_ARGC=([0]="0")
BASH_ARGV=()
BASH_CMDS=()
BASH_EXECUTION_STRING=set
BASH_LINENO=()
BASH_LOADABLES_PATH=/usr/local/lib/bash:/usr/lib/bash:/opt/local/lib/bash:/usr/pkg/lib/bash:/opt/pkg/lib/bash:.
BASH_SOURCE=()
BASH_VERSINFO=([0]="5" [1]="2" [2]="21" [3]="1" [4]="release" [5]="x86_64-pc-linux-gnu")
BASH_VERSION='5.2.21(1)-release'
DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1003/bus
DIRSTACK=()
EUID=1003
GROUPS=()
HOME=/home/jenkins-agent-2
HOSTNAME=DESKTOP-JM4DKDH
HOSTTYPE=x86_64
IFS=$' \t\n'
LANG=C.UTF-8
LOGNAME=jenkins-agent-2
MACHTYPE=x86_64-pc-linux-gnu
OPTERR=1
OPTIND=1
OSTYPE=linux-gnu
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/games:/usr/local/games:/snap/bin
PIPESTATUS=([0]="0")
PPID=6219
PS4='+ '
PWD=/home/jenkins-agent-2
SHELL=/bin/bash
SHELLOPTS=braceexpand:hashall:interactive-comments
SHLVL=1
SSH_CLIENT='127.0.0.1 35070 22'
SSH_CONNECTION='127.0.0.1 35070 127.0.0.1 22'
TERM=dumb
UID=1003
USER=jenkins-agent-2
XDG_RUNTIME_DIR=/run/user/1003
XDG_SESSION_CLASS=user
XDG_SESSION_ID=10
XDG_SESSION_TYPE=tty
_=']'
[09/07/26 13:21:36] [SSH] Starting sftp client.
[09/07/26 13:21:36] [SSH] Copying latest remoting.jar...
[09/07/26 13:21:36] [SSH] Copied 1,406,408 bytes.
Expanded the channel window size to 4MB
[09/07/26 13:21:36] [SSH] Starting agent process: cd "/home/jenkins-agent-2" && java  -jar remoting.jar -workDir /home/jenkins-agent-2 -jar-cache /home/jenkins-agent-2/remoting/jarCache
Sep 07, 2026 1:21:36 PM org.jenkinsci.remoting.engine.WorkDirManager initializeWorkDir
INFO: Using /home/jenkins-agent-2/remoting as a remoting work directory
Sep 07, 2026 1:21:37 PM org.jenkinsci.remoting.engine.WorkDirManager setupLogging
INFO: Both error and output logs will be printed to /home/jenkins-agent-2/remoting
<===[JENKINS REMOTING CAPACITY]===>channel started
Remoting version: 3355.3357.v931d3c992987
Launcher: SSHLauncher
Communication Protocol: Standard in/out
This is a Unix agent
Agent successfully connected and online
```

**3단계) Label로 Agent 선택하기**

```jsx
wsl-agent의 label : linux-1
wsl-agent-2의 label : linux-2
```

```jsx
pipeline {
    agent {
        label 'linux-1'
    }

    stages {
        stage('Check Agent') {
            steps {
                sh '''
                    echo "===== Agent Information ====="
                    echo "USER:"
                    whoami

                    echo "HOSTNAME:"
                    hostname

                    echo "WORKSPACE:"
                    pwd

                    echo "KERNEL:"
                    uname -a
                '''
            }
        }
    }
}

/*
===== Agent Information =====
+ echo USER:
USER:
+ whoami
jenkins-agent
+ echo HOSTNAME:
HOSTNAME:
+ hostname
DESKTOP-JM4DKDH
+ echo WORKSPACE:
WORKSPACE:
+ pwd
/home/jenkins-agent/workspace/agent-label-test
*/
```

```jsx
pipeline {
    agent {
        label 'linux-2'
    }

    stages {
        stage('Check Agent') {
            steps {
                sh '''
                    echo "===== Agent Information ====="
                    echo "USER:"
                    whoami

                    echo "HOSTNAME:"
                    hostname

                    echo "WORKSPACE:"
                    pwd

                    echo "KERNEL:"
                    uname -a
                '''
            }
        }
    }
}

/*
===== Agent Information =====
+ echo USER:
USER:
+ whoami
jenkins-agent-2
+ echo HOSTNAME:
HOSTNAME:
+ hostname
DESKTOP-JM4DKDH
+ echo WORKSPACE:
WORKSPACE:
+ pwd
/home/jenkins-agent-2/workspace/agent-label-test
*/
```

```jsx
pipeline {
    agent {
        label 'linux-1'
    }

    stages {
        stage('Create File') {
            steps {
                sh '''
                    echo "Created by:" > agent-info.txt
                    whoami >> agent-info.txt

                    echo "Hostname:" >> agent-info.txt
                    hostname >> agent-info.txt

                    echo "Workspace:" >> agent-info.txt
                    pwd >> agent-info.txt

                    cat agent-info.txt
                '''
            }
        }
    }
}

/*
Created by:
jenkins-agent
Hostname:
DESKTOP-JM4DKDH
Workspace:
/home/jenkins-agent/workspace/agent-label-test
/*
```

```jsx
pipeline {
    agent {
        label 'linux-2'
    }

    stages {
        stage('Create File') {
            steps {
                sh '''
                    echo "Created by:" > agent-info.txt
                    whoami >> agent-info.txt

                    echo "Hostname:" >> agent-info.txt
                    hostname >> agent-info.txt

                    echo "Workspace:" >> agent-info.txt
                    pwd >> agent-info.txt

                    cat agent-info.txt
                '''
            }
        }
    }
}

/*
Created by:
jenkins-agent-2
Hostname:
DESKTOP-JM4DKDH
Workspace:
/home/jenkins-agent-2/workspace/agent-label-test
/*
```

**4단계) Executor 동시 실행**

```jsx
# wsl-agent의 Number of executors를 1로 변경하고 실행

pipeline {
    agent {
        label 'linux-1'
    }

    stages {
        stage('Long Running Task') {
            steps {
                sh '''
                    echo "START: $(date)"
                    echo "USER: $(whoami)"
                    echo "PID: $$"

                    sleep 30

                    echo "END: $(date)"
                '''
            }
        }
    }
}

# 첫 번째 빌드 실행 중일 때 두 번째 빌드 바로 실행
/* 첫 번째 빌드 console output
Started by user Sohyeon Sim

[Pipeline] Start of Pipeline
[Pipeline] node
Running on wsl-agent
 in /home/jenkins-agent/workspace/executor-test
[Pipeline] {
[Pipeline] stage
[Pipeline] { (Long Running Task)
[Pipeline] sh
+ date
+ echo START: Mon Sep  7 13:29:33 KST 2026
START: Mon Sep  7 13:29:33 KST 2026
+ whoami
+ echo USER: jenkins-agent
USER: jenkins-agent
+ echo PID: 7937
PID: 7937
+ sleep 30
+ date
+ echo END: Mon Sep  7 13:30:03 KST 2026
END: Mon Sep  7 13:30:03 KST 2026
[Pipeline] }
[Pipeline] // stage
[Pipeline] }
[Pipeline] // node
[Pipeline] End of Pipeline
Finished: SUCCESS
*/

/* 두 번째 빌드 console output
Started by user Sohyeon Sim

[Pipeline] Start of Pipeline
[Pipeline] node
Still waiting to schedule task
Waiting for next available executor on ‘wsl-agent
’
Running on wsl-agent
 in /home/jenkins-agent/workspace/executor-test
[Pipeline] {
[Pipeline] stage
[Pipeline] { (Long Running Task)
[Pipeline] sh
+ date
+ echo START: Mon Sep  7 13:30:06 KST 2026
START: Mon Sep  7 13:30:06 KST 2026
+ whoami
+ echo USER: jenkins-agent
USER: jenkins-agent
+ echo PID: 8097
PID: 8097
+ sleep 30
+ date
+ echo END: Mon Sep  7 13:30:36 KST 2026
END: Mon Sep  7 13:30:36 KST 2026
[Pipeline] }
[Pipeline] // stage
[Pipeline] }
[Pipeline] // node
[Pipeline] End of Pipeline
Finished: SUCCESS
*/

# 첫 번째 빌드 끝난 뒤에 두 번째 빌드 실행
```

```jsx
# wsl-agent의 Number of executors를 2로 변경하고 실행

pipeline {
    agent {
        label 'linux-1'
    }

    stages {
        stage('Long Running Task') {
            steps {
                sh '''
                    echo "START: $(date)"
                    echo "USER: $(whoami)"
                    echo "PID: $$"

                    sleep 30

                    echo "END: $(date)"
                '''
            }
        }
    }
}

# 첫 번째 빌드 실행 중일 때 두 번째 빌드 바로 실행
/* 첫 번째 빌드 console output
Started by user Sohyeon Sim

[Pipeline] Start of Pipeline
[Pipeline] node
Running on wsl-agent
 in /home/jenkins-agent/workspace/executor-test
[Pipeline] {
[Pipeline] stage
[Pipeline] { (Long Running Task)
[Pipeline] sh
+ date
+ echo START: Mon Sep  7 13:31:11 KST 2026
START: Mon Sep  7 13:31:11 KST 2026
+ whoami
+ echo USER: jenkins-agent
USER: jenkins-agent
+ echo PID: 8341
PID: 8341
+ sleep 30
+ date
+ echo END: Mon Sep  7 13:31:41 KST 2026
END: Mon Sep  7 13:31:41 KST 2026
[Pipeline] }
[Pipeline] // stage
[Pipeline] }
[Pipeline] // node
[Pipeline] End of Pipeline
Finished: SUCCESS
*/

/* 두 번째 빌드 console output
Started by user Sohyeon Sim

[Pipeline] Start of Pipeline
[Pipeline] node
Running on wsl-agent
 in /home/jenkins-agent/workspace/executor-test@2
[Pipeline] {
[Pipeline] stage
[Pipeline] { (Long Running Task)
[Pipeline] sh
+ date
+ echo START: Mon Sep  7 13:31:17 KST 2026
START: Mon Sep  7 13:31:17 KST 2026
+ whoami
+ echo USER: jenkins-agent
USER: jenkins-agent
+ echo PID: 8381
PID: 8381
+ sleep 30
+ date
+ echo END: Mon Sep  7 13:31:47 KST 2026
END: Mon Sep  7 13:31:47 KST 2026
[Pipeline] }
[Pipeline] // stage
[Pipeline] }
[Pipeline] // node
[Pipeline] End of Pipeline
Finished: SUCCESS
*/

# 동시에 파이프라인 실행
# executor를 너무 많이 설정 -> 여러 빌드가 동시에 CPU와 메모리를 사용하여 성능이 저하될 수도 있다.
```

**5단계) 하나의 파이프라인에서 Agent를 바꿔가며 실행**

```jsx
Stage 1: Build
    ↓
linux-1 (wsl-agent)

Stage 2: Test
    ↓
linux-2 (wsl-agent-2)

Stage 3: Deploy
    ↓
linux-1 (wsl-agent)
```

```jsx
pipeline {
    agent none

    stages {

        stage('Build') {
            agent {
                label 'linux-1'
            }

            steps {
                sh '''
                    echo "===== BUILD ====="
                    echo "USER: $(whoami)"
                    echo "HOST: $(hostname)"
                    echo "WORKSPACE: $(pwd)"

                    echo "Build result from linux-1" > build.txt

                    echo ""
                    cat build.txt
                '''

                stash name: 'build-result', includes: 'build.txt'
            }
        }

        stage('Test') {
            agent {
                label 'linux-2'
            }

            steps {
                unstash 'build-result'

                sh '''
                    echo "===== TEST ====="
                    echo "USER: $(whoami)"
                    echo "HOST: $(hostname)"
                    echo "WORKSPACE: $(pwd)"

                    echo ""
                    echo "Received build.txt:"
                    cat build.txt
                '''
            }
        }

        stage('Deploy') {
            agent {
                label 'linux-1'
            }

            steps {
                sh '''
                    echo "===== DEPLOY ====="
                    echo "USER: $(whoami)"
                    echo "HOST: $(hostname)"
                    echo "WORKSPACE: $(pwd)"
                '''
            }
        }
    }
}
```

```jsx
Started by user Sohyeon Sim

[Pipeline] Start of Pipeline
[Pipeline] stage
[Pipeline] { (Build)
[Pipeline] node
Running on wsl-agent
 in /home/jenkins-agent/workspace/multi-agent-pipeline
[Pipeline] {
[Pipeline] sh
+ echo ===== BUILD =====
===== BUILD =====
+ whoami
+ echo USER: jenkins-agent
USER: jenkins-agent
+ hostname
+ echo HOST: DESKTOP-JM4DKDH
HOST: DESKTOP-JM4DKDH
+ pwd
+ echo WORKSPACE: /home/jenkins-agent/workspace/multi-agent-pipeline
WORKSPACE: /home/jenkins-agent/workspace/multi-agent-pipeline
+ echo Build result from linux-1
+ echo

+ cat build.txt
Build result from linux-1
[Pipeline] stash
Stashed 1 file(s)
[Pipeline] }
[Pipeline] // node
[Pipeline] }
[Pipeline] // stage
[Pipeline] stage
[Pipeline] { (Test)
[Pipeline] node
Running on wsl-agent-2
 in /home/jenkins-agent-2/workspace/multi-agent-pipeline
[Pipeline] {
[Pipeline] unstash
[Pipeline] sh
+ echo ===== TEST =====
===== TEST =====
+ whoami
+ echo USER: jenkins-agent-2
USER: jenkins-agent-2
+ hostname
+ echo HOST: DESKTOP-JM4DKDH
HOST: DESKTOP-JM4DKDH
+ pwd
+ echo WORKSPACE: /home/jenkins-agent-2/workspace/multi-agent-pipeline
WORKSPACE: /home/jenkins-agent-2/workspace/multi-agent-pipeline
+ echo

+ echo Received build.txt:
Received build.txt:
+ cat build.txt
Build result from linux-1
[Pipeline] }
[Pipeline] // node
[Pipeline] }
[Pipeline] // stage
[Pipeline] stage
[Pipeline] { (Deploy)
[Pipeline] node
Running on wsl-agent
 in /home/jenkins-agent/workspace/multi-agent-pipeline
[Pipeline] {
[Pipeline] sh
+ echo ===== DEPLOY =====
===== DEPLOY =====
+ whoami
+ echo USER: jenkins-agent
USER: jenkins-agent
+ hostname
+ echo HOST: DESKTOP-JM4DKDH
HOST: DESKTOP-JM4DKDH
+ pwd
+ echo WORKSPACE: /home/jenkins-agent/workspace/multi-agent-pipeline
WORKSPACE: /home/jenkins-agent/workspace/multi-agent-pipeline
[Pipeline] }
[Pipeline] // node
[Pipeline] }
[Pipeline] // stage
[Pipeline] End of Pipeline
Finished: SUCCESS

```

```jsx
Build
  ↓
linux-1
jenkins-agent
  │
  │ stash
  ▼
Test
  ↓
linux-2
jenkins-agent-2
  │
  │ unstash
  ▼
Deploy
  ↓
linux-1
jenkins-agent

soso@DESKTOP-JM4DKDH:~/jenkins-study$ sudo cat /home/jenkins-agent/workspace/multi-agent-pipeline/build.txt
[sudo] password for soso:
Build result from linux-1
soso@DESKTOP-JM4DKDH:~/jenkins-study$ sudo cat /home/jenkins-agent-2/workspace/multi-agent-pipeline/build.txt
Build result from linux-1

# stash name: 'build-result', includes: 'build.txt'
# 현재 workspace의 build.txt를 build-result라는 이름으로 보관

# unstash 'build-result'
# Jenkins가 앞에서 저장해 놓은 build-result를 가져와서 현재 Agent의 workspace에 파일을 복원
```

### 1-4) 참고 문헌

- https://www.jenkins.io/doc/book/using/using-agents/
- https://www.jenkins.io/doc/book/security/controller-isolation/
- https://www.jenkins.io/doc/book/scaling/architecting-for-scale/
- https://www.jenkins.io/doc/book/security/managing-security/
- https://www.jenkins.io/doc/book/pipeline/docker/
