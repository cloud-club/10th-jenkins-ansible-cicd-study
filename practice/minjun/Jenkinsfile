// minjun - Week 1: Build / Test / Deploy / Verify
//
// 공용 인프라 전제:
//  - Agent 라벨: ansible-control (스터디장 connection-test에서 검증된 라벨)
//  - SSH: 공용 Credential 'SSH_KeyPair-cc10-cicd.pem' (user: ubuntu)
//  - App 서버 docker / LB nginx 작업은 become(sudo)으로 수행
//
// sh 블록은 전부 작은따옴표('''). Groovy가 아니라 셸이 실행 시점에 변수를 읽게 해서
// 비밀 값(키 경로 등)이 명령 문자열에 박히지 않게 한다.

pipeline {
  agent { label 'ansible-control' }

  options {
    disableConcurrentBuilds()                      // 내 배포끼리 겹치지 않게
    buildDiscarder(logRotator(numToKeepStr: '20'))
    timeout(time: 20, unit: 'MINUTES')
  }

  environment {
    APP_IMAGE = 'minjun-app'
    ARCHIVE   = 'build/minjun-app.tar.gz'
    SSH_CRED  = 'SSH_KeyPair-cc10-cicd.pem'
  }

  stages {

    stage('Checkout') {
      steps {
        checkout scm
        script {
          env.GIT_SHA     = sh(script: 'git rev-parse --short HEAD', returnStdout: true).trim()
          env.APP_VERSION = readFile('app/VERSION').trim()
          env.IMAGE_TAG   = "${env.APP_VERSION}-${env.GIT_SHA}"
          currentBuild.displayName = "#${env.BUILD_NUMBER} ${env.IMAGE_TAG}"
        }
        sh 'echo "version=$APP_VERSION sha=$GIT_SHA tag=$IMAGE_TAG"'
      }
    }

    stage('Build') {
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
      steps {
        sh 'bash scripts/test.sh "$APP_IMAGE:$IMAGE_TAG" "$APP_VERSION"'
      }
    }

    stage('Package') {
      steps {
        // 레지스트리가 없으니 이미지를 파일로 만들어 Ansible이 복사한다.
        // 파일은 내 workspace 안에만 둔다 (공용 Agent 규칙).
        sh '''
          mkdir -p build
          docker save "$APP_IMAGE:$IMAGE_TAG" | gzip > "$ARCHIVE"
          ls -lh "$ARCHIVE"
        '''
      }
    }

    stage('Deploy') {
      steps {
        withCredentials([sshUserPrivateKey(credentialsId: env.SSH_CRED,
                                           keyFileVariable: 'SSH_KEY',
                                           usernameVariable: 'SSH_USER')]) {
          dir('ansible') {
            sh '''
              ansible-playbook -i inventory.ini site.yml \
                -u "$SSH_USER" --private-key "$SSH_KEY" \
                -e app_version="$APP_VERSION" \
                -e git_sha="$GIT_SHA" \
                -e image_archive="$WORKSPACE/$ARCHIVE"
            '''
          }
        }
      }
    }

    stage('Verify') {
      steps {
        withCredentials([sshUserPrivateKey(credentialsId: env.SSH_CRED,
                                           keyFileVariable: 'SSH_KEY',
                                           usernameVariable: 'SSH_USER')]) {
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
  }

  post {
    always {
      // 공용 Agent 디스크를 채우지 않도록 정리
      sh '''
        rm -f "$ARCHIVE" || true
        docker image rm "$APP_IMAGE:$IMAGE_TAG" >/dev/null 2>&1 || true
      '''
    }
  }
}
