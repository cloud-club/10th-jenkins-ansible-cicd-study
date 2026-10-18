// minjun - Week 3: Deploy / Rollback with a signed deploy ledger
//
// ACTION=deploy   Checkout → Ledger 검증(격리된 태그면 거부) → Build → Test → Package → Rolling Deploy → Verify → Ledger 기록
// ACTION=rollback Checkout → Ledger 검증 → 롤백 대상 결정 → 승인(input) → Rolling(로드 없이, 증거 수집) → Verify → Ledger 기록(ROLLBACK + QUARANTINE)
//
// 3주차 핵심
//  - 롤백 대상은 사람이 입력하지 않는다. 서명이 검증된 배포 기록(ledger)에서 "직전 정상 배포"를 고른다.
//    기록이 한 줄이라도 변조됐으면 롤백 자체를 거부한다. (롤백이 공격 경로가 되지 않게)
//  - 롤백은 다시 빌드하지 않는다. 다시 빌드하면 attestation 때문에 다른 이미지가 된다(2주차에서 확인).
//    서버에 남아 있는 이전 이미지를 쓰고, 그 ID가 서명된 기록의 ID와 같아야 한다.
//  - 서명 키(minjun-ledger-hmac)는 tools/ledger.py가 환경변수로만 읽는다. ansible-playbook 프로세스에는 넘기지 않는다.
//
// 이전 주차에서 이어지는 것
//  - 2주차: STRATEGY(drain/no-drain), DEMO_TAMPER=app2(같은 태그 변조 이미지), 무결성 게이트, 감사 로그
//  - 파라미터는 choice만. 3주차에 다른 사람이 실행해도 자유 입력이 명령 주입 경로가 되지 않게.
//  - sh 블록은 작은따옴표('''). Groovy가 아니라 셸이 실행 시점에 변수를 읽게 해서 비밀 값이 명령 문자열에 박히지 않게.

pipeline {
  agent { label 'ansible-control' }

  parameters {
    choice(name: 'ACTION', choices: ['deploy', 'rollback'],
           description: 'deploy: 현재 커밋을 빌드해서 배포 / rollback: 서명된 배포 기록의 직전 정상 버전으로 되돌림(빌드 안 함, 승인 필요)')
    choice(name: 'STRATEGY', choices: ['drain', 'no-drain'],
           description: 'drain: 한 대씩 Nginx에서 빼고 교체 / no-drain: 빼지 않고 교체 (2주차 비교 실험)')
    choice(name: 'DEMO_TAMPER', choices: ['none', 'app2', 'ledger', 'restore-ledger'],
           description: '시연용. app2: 같은 태그의 변조 이미지 심기 / ledger: LB의 배포 기록 한 줄 변조 / restore-ledger: 변조 되돌리기')
  }

  options {
    disableConcurrentBuilds()
    buildDiscarder(logRotator(numToKeepStr: '20'))
    timeout(time: 30, unit: 'MINUTES')
  }

  environment {
    APP_IMAGE   = 'minjun-app'
    ARCHIVE     = 'build/minjun-app.tar.gz'
    SSH_CRED    = 'SSH_KeyPair-cc10-cicd.pem'
    LEDGER_CRED = 'minjun-ledger-hmac'
    LEDGER      = 'build/ledger.jsonl'
    APPROVERS   = 'minjun'                    // 롤백 승인 가능한 Jenkins 사용자 ID
  }

  stages {

    stage('Checkout') {
      steps {
        checkout scm
        script {
          env.ACTION      = params.ACTION ?: 'deploy'
          env.STRATEGY    = params.STRATEGY ?: 'drain'
          env.DEMO_TAMPER = params.DEMO_TAMPER ?: 'none'
          env.GIT_SHA     = sh(script: 'git rev-parse --short HEAD', returnStdout: true).trim()
          env.APP_VERSION = readFile('app/VERSION').trim()
          env.IMAGE_TAG   = "${env.APP_VERSION}-${env.GIT_SHA}"
          currentBuild.displayName = "#${env.BUILD_NUMBER} ${env.ACTION} ${env.IMAGE_TAG}" +
                                     (env.DEMO_TAMPER != 'none' ? " DEMO:${env.DEMO_TAMPER}" : "")
        }
        sh 'mkdir -p build && echo "action=$ACTION version=$APP_VERSION sha=$GIT_SHA tag=$IMAGE_TAG"'
      }
    }

    stage('Demo: Tamper Ledger') {
      when { expression { return ['ledger', 'restore-ledger'].contains(env.DEMO_TAMPER) } }
      steps {
        withCredentials([sshUserPrivateKey(credentialsId: env.SSH_CRED, keyFileVariable: 'SSH_KEY', usernameVariable: 'SSH_USER')]) {
          dir('ansible') {
            sh '''
              if [ "$DEMO_TAMPER" = "ledger" ]; then MODE=tamper; else MODE=restore; fi
              ansible-playbook -i inventory.ini demo-tamper-ledger.yml \
                -u "$SSH_USER" --private-key "$SSH_KEY" -e ledger_demo="$MODE"
            '''
          }
        }
      }
    }

    stage('Ledger: Verify') {
      steps {
        withCredentials([sshUserPrivateKey(credentialsId: env.SSH_CRED, keyFileVariable: 'SSH_KEY', usernameVariable: 'SSH_USER')]) {
          dir('ansible') {
            sh '''
              ansible-playbook -i inventory.ini ledger.yml \
                -u "$SSH_USER" --private-key "$SSH_KEY" \
                -e ledger_mode=pull -e ledger_local="$WORKSPACE/$LEDGER"
            '''
          }
        }
        // 키는 이 블록 안의 python에만 보인다
        withCredentials([string(credentialsId: env.LEDGER_CRED, variable: 'LEDGER_KEY')]) {
          sh '''#!/bin/bash
            set -euo pipefail
            python3 tools/ledger.py verify "$LEDGER"
            if [ "$ACTION" = "deploy" ]; then
              python3 tools/ledger.py check-deployable "$LEDGER" "$IMAGE_TAG"
            else
              python3 tools/ledger.py rollback-target "$LEDGER" build/rollback-target.json
            fi
          '''
        }
        script {
          if (env.ACTION == 'rollback') {
            def field = { k -> sh(script: "python3 -c 'import json;print(json.load(open(\"build/rollback-target.json\"))[\"${k}\"])'", returnStdout: true).trim() }
            env.ROLLBACK_FROM = field('current_tag')
            env.IMAGE_TAG     = field('target_tag')
            env.APP_VERSION   = field('target_version')
            env.GIT_SHA       = field('target_git_sha')
            currentBuild.displayName = "#${env.BUILD_NUMBER} ROLLBACK ${env.ROLLBACK_FROM} → ${env.IMAGE_TAG}" +
                                       (env.DEMO_TAMPER != 'none' ? " DEMO:${env.DEMO_TAMPER}" : "")
          }
        }
      }
    }

    stage('Build') {
      when { expression { return env.ACTION == 'deploy' } }
      steps {
        sh '''
          docker build \
            --build-arg APP_VERSION="$APP_VERSION" \
            --build-arg GIT_SHA="$GIT_SHA" \
            -t "$APP_IMAGE:$IMAGE_TAG" .
        '''
      }
    }

    stage('Test') {
      when { expression { return env.ACTION == 'deploy' } }
      steps {
        sh 'bash scripts/test.sh "$APP_IMAGE:$IMAGE_TAG" "$APP_VERSION"'
      }
    }

    stage('Package') {
      when { expression { return env.ACTION == 'deploy' } }
      steps {
        sh '''
          docker save "$APP_IMAGE:$IMAGE_TAG" | gzip > "$ARCHIVE"
          ls -lh "$ARCHIVE"
        '''
      }
    }

    stage('Demo: Plant Tampered Image') {
      when { expression { return env.ACTION == 'deploy' && env.DEMO_TAMPER == 'app2' } }
      steps {
        sh '''
          docker build --label demo.tampered=true \
            --build-arg APP_VERSION="$APP_VERSION" \
            --build-arg GIT_SHA="$GIT_SHA" \
            -t "$APP_IMAGE:tampered-$IMAGE_TAG" .
          docker save "$APP_IMAGE:tampered-$IMAGE_TAG" | gzip > build/tampered.tar.gz
        '''
        withCredentials([sshUserPrivateKey(credentialsId: env.SSH_CRED, keyFileVariable: 'SSH_KEY', usernameVariable: 'SSH_USER')]) {
          dir('ansible') {
            sh '''
              ansible-playbook -i inventory.ini demo-tamper.yml \
                -u "$SSH_USER" --private-key "$SSH_KEY" \
                -l "$DEMO_TAMPER" \
                -e app_version="$APP_VERSION" \
                -e git_sha="$GIT_SHA" \
                -e tampered_archive="$WORKSPACE/build/tampered.tar.gz"
            '''
          }
        }
      }
    }

    stage('Approve Rollback') {
      when { expression { return env.ACTION == 'rollback' } }
      steps {
        script {
          timeout(time: 10, unit: 'MINUTES') {
            def r = input(
              message: "Rollback ${env.ROLLBACK_FROM} → ${env.IMAGE_TAG} on app1~3? (target chosen from the signed ledger)",
              ok: 'Rollback',
              submitter: env.APPROVERS,
              submitterParameter: 'APPROVER',
              parameters: [choice(name: 'REASON',
                                  choices: ['functional-failure', 'security-incident', 'performance', 'other'],
                                  description: '장애 유형 (기록과 감사 로그에 남는다)')])
            env.APPROVER = r['APPROVER']
            env.REASON   = r['REASON']
          }
        }
        sh 'echo "approved by=$APPROVER reason=$REASON"'
      }
    }

    stage('Rolling Deploy') {
      steps {
        withCredentials([sshUserPrivateKey(credentialsId: env.SSH_CRED, keyFileVariable: 'SSH_KEY', usernameVariable: 'SSH_USER')]) {
          dir('ansible') {
            // bash로 실행해야 pipefail이 된다 (tee 뒤에서 ansible 실패가 묻히지 않게)
            sh '''#!/bin/bash
              set -euo pipefail
              if [ "$STRATEGY" = "no-drain" ]; then DRAIN=false; else DRAIN=true; fi
              if [ "$ACTION" = "rollback" ]; then
                MODE_ARGS=(-e rollback_mode=true -e "@$WORKSPACE/build/rollback-target.json")
              else
                MODE_ARGS=(-e image_archive="$WORKSPACE/$ARCHIVE")
              fi
              echo "action=$ACTION strategy=$STRATEGY rolling_drain=$DRAIN tag=$IMAGE_TAG"

              ansible-playbook -i inventory.ini rolling.yml \
                -u "$SSH_USER" --private-key "$SSH_KEY" \
                -e app_version="$APP_VERSION" \
                -e git_sha="$GIT_SHA" \
                -e rolling_drain="$DRAIN" \
                -e build_id="$BUILD_NUMBER" \
                -e evidence_local="$WORKSPACE/build/evidence" \
                "${MODE_ARGS[@]}" \
                | tee "$WORKSPACE/build/rolling.log"

              echo "nginx reloads: $(grep -c '"msg": "NGINX_RELOADED' "$WORKSPACE/build/rolling.log" || true)"
            '''
          }
        }
      }
    }

    stage('Verify') {
      steps {
        withCredentials([sshUserPrivateKey(credentialsId: env.SSH_CRED, keyFileVariable: 'SSH_KEY', usernameVariable: 'SSH_USER')]) {
          dir('ansible') {
            sh '''
              ansible-playbook -i inventory.ini verify.yml \
                -u "$SSH_USER" --private-key "$SSH_KEY" \
                -e app_version="$APP_VERSION"
            '''
          }
        }
      }
    }

    stage('Ledger: Record') {
      steps {
        withCredentials([sshUserPrivateKey(credentialsId: env.SSH_CRED, keyFileVariable: 'SSH_KEY', usernameVariable: 'SSH_USER')]) {
          dir('ansible') {
            sh '''#!/bin/bash
              set -euo pipefail
              if [ "$ACTION" = "deploy" ]; then
                # 각 서버가 이번에 로드하며 기록한 이미지 ID
                ansible-playbook -i inventory.ini ledger.yml \
                  -u "$SSH_USER" --private-key "$SSH_KEY" \
                  -e ledger_mode=ids -e ids_tag="$IMAGE_TAG" -e ledger_local="$WORKSPACE/build/ids.json"
              else
                # 롤백: 서명된 기록에서 온 ID (게이트가 서버와 일치를 이미 확인함)
                python3 -c 'import json,os; w=os.environ["WORKSPACE"]; json.dump(json.load(open(w+"/build/rollback-target.json"))["expected_ids"], open(w+"/build/ids.json","w"))'
              fi
              cat "$WORKSPACE/build/ids.json"; echo
            '''
          }
        }
        withCredentials([string(credentialsId: env.LEDGER_CRED, variable: 'LEDGER_KEY')]) {
          sh '''#!/bin/bash
            set -euo pipefail
            if [ "$ACTION" = "deploy" ]; then
              python3 tools/ledger.py append "$LEDGER" --event DEPLOY --tag "$IMAGE_TAG" \
                --ids build/ids.json --build "$BUILD_NUMBER" --commit "$GIT_SHA"
            else
              python3 tools/ledger.py append "$LEDGER" --event ROLLBACK --tag "$IMAGE_TAG" \
                --ids build/ids.json --build "$BUILD_NUMBER" --commit "$GIT_SHA" \
                --from-tag "$ROLLBACK_FROM" --approver "$APPROVER" --reason "$REASON"
              python3 tools/ledger.py append "$LEDGER" --event QUARANTINE --tag "$ROLLBACK_FROM" \
                --build "$BUILD_NUMBER" --approver "$APPROVER" --reason "$REASON"
            fi
            python3 tools/ledger.py verify "$LEDGER"
            python3 tools/ledger.py head "$LEDGER" | tee build/ledger-head.txt
          '''
        }
        withCredentials([sshUserPrivateKey(credentialsId: env.SSH_CRED, keyFileVariable: 'SSH_KEY', usernameVariable: 'SSH_USER')]) {
          dir('ansible') {
            sh '''
              ansible-playbook -i inventory.ini ledger.yml \
                -u "$SSH_USER" --private-key "$SSH_KEY" \
                -e ledger_mode=push -e ledger_local="$WORKSPACE/$LEDGER"
            '''
          }
        }
      }
    }
  }

  post {
    always {
      // 배포 로그, 서명된 기록 사본·head, 롤백 대상, 증거 — 12시간 뒤에도 Jenkins에서 확인할 수 있게
      archiveArtifacts artifacts: 'build/rolling.log, build/ledger.jsonl, build/ledger-head.txt, build/rollback-target.json, build/evidence/**',
                       allowEmptyArchive: true
      withCredentials([sshUserPrivateKey(credentialsId: env.SSH_CRED, keyFileVariable: 'SSH_KEY', usernameVariable: 'SSH_USER')]) {
        dir('ansible') {
          sh '''
            echo "===== audit log (last 15) ====="
            ansible lb -i inventory.ini -u "$SSH_USER" --private-key "$SSH_KEY" -b \
              -m ansible.builtin.command -a "tail -n 15 /var/log/minjun-deploy.jsonl" || true
          '''
        }
      }
      // 공용 Agent 디스크 정리 (서버의 이전 이미지는 롤백용으로 남긴다)
      sh '''
        rm -f "$ARCHIVE" build/tampered.tar.gz || true
        if [ "$ACTION" = "deploy" ]; then
          docker image rm "$APP_IMAGE:$IMAGE_TAG" "$APP_IMAGE:tampered-$IMAGE_TAG" >/dev/null 2>&1 || true
        fi
      '''
    }
  }
}
