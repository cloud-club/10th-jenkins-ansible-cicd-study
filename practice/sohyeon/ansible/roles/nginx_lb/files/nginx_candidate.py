"""파일 역할: 공용 Nginx 구성에서 프로젝트 설정만 후보로 바꾸어 검사하고 실행 중인 설정 파일은 유지한다."""
import glob
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def validate(candidate, destination, main='/etc/nginx/nginx.conf'):
    """기존 main 구성의 프로젝트 include만 후보로 바꾼 임시 설정으로 nginx -t를 실행한다."""
    main = Path(main)
    pattern = r'(?m)^(\s*)include\s+/etc/nginx/conf\.d/\*\.conf\s*;'
    content = main.read_text()
    if len(re.findall(pattern, content)) != 1:
        raise ValueError('Expected exactly one include /etc/nginx/conf.d/*.conf in nginx.conf')
    configs = [p for p in sorted(glob.glob('/etc/nginx/conf.d/*.conf'))
               if Path(p).resolve() != Path(destination).resolve()]
    configs.append(str(Path(candidate).resolve()))
    replacement = '\n'.join(f'    include "{p}";' for p in configs)
    content = re.sub(pattern, lambda _: replacement, content)
    with tempfile.NamedTemporaryFile(mode='w', prefix='.sohyeon-check-', suffix='.conf',
                                     dir=main.parent) as temp:
        temp.write(content)
        temp.flush()
        subprocess.run(['nginx', '-t', '-c', temp.name], check=True)


# 직접 실행한 경우에만 명령행 처리 또는 테스트 실행을 시작한다.
if __name__ == '__main__':
    validate(*sys.argv[1:])
