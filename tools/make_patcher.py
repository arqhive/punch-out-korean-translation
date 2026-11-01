"""파일 단위 디스크 패처 생성기 (Wii·GC 공용 템플릿).

바뀐 게임 파일마다 원본과의 xdelta 차분을 만들고, 사용자용 패처(패치하기.bat + patch.ps1)와
wit·xdelta3 를 한 폴더/zip 으로 묶는다. ISO 통째 xdelta와 달리 덤프·변환 형태(정본 ISO, WBFS,
WBFS에서 변환한 ISO 등)가 달라 MD5가 달라도 게임 파일만 같으면 적용된다.
gzip 파일은 압축을 푼 내용끼리 차분하고 패처가 다시 압축한다(게임이 풀어서 읽기만 할 때만 안전).

사용:
  python make_patcher.py --orig work/jp/DATA --build work/build --out release/Name_v0.1 \
      --id RBWJ01 --title "게임 이름" --result "Game (Korean) [RBWJ01]" \
      --wit tools/bin/wit-v3.05a-r8638-cygwin64 --xdelta tools/bin/xdelta3.exe [--readme release/README_한국어.txt]

  --orig  : 원본 파티션 추출본 루트(sys/, files/ 가 있는 곳)
  --build : 바뀐 파일만 같은 상대 경로로 모은 곳(sys/main.dol, files/... 등)
"""
import argparse
import gzip
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
WIT_FILES = ('bin/wit.exe', 'bin/cygwin1.dll', 'bin/cygz.dll', 'bin/cygcrypto-1.1.dll', 'bin/cygncursesw-10.dll')


def md5(b):
    return hashlib.md5(b).hexdigest()


def changed(orig, build):
    for dp, _, fs in os.walk(build):
        for f in sorted(fs):
            new = Path(dp) / f
            rel = new.relative_to(build).as_posix()
            old = orig / rel
            if not old.exists():
                raise SystemExit(f'원본에 없는 파일(추가 파일은 지원 안 함): {rel}')
            if old.read_bytes() != new.read_bytes():
                yield rel, old, new


def main():
    ap = argparse.ArgumentParser()
    for k in ('orig', 'build', 'out', 'id', 'title', 'result', 'wit', 'xdelta'):
        ap.add_argument('--' + k, required=True)
    ap.add_argument('--readme')
    ap.add_argument('--templates', default=str(HERE), help='patch.ps1·패치하기.bat 이 있는 폴더')
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    orig, build, out = Path(a.orig), Path(a.build), Path(a.out)
    a.xdelta = str(Path(a.xdelta).resolve())   # 상대경로 그대로면 Windows에서 실행 파일을 못 찾음

    if out.exists():
        shutil.rmtree(out)
    (out / 'data').mkdir(parents=True)
    tmp = Path(tempfile.mkdtemp())
    lines, n_gz = [], 0
    for i, (rel, old, new) in enumerate(changed(orig, build)):
        A, B = old.read_bytes(), new.read_bytes()
        mode = 'raw'
        if A[:2] == b'\x1f\x8b' and B[:2] == b'\x1f\x8b':
            A, B, mode = gzip.decompress(A), gzip.decompress(B), 'gz'
            n_gz += 1
        (tmp / 'a').write_bytes(A); (tmp / 'b').write_bytes(B)
        patch = f'{i:03d}.xdelta'
        # -A= : 헤더에 임시 파일 경로(PC 사용자 이름 포함)를 적지 않음
        subprocess.run([a.xdelta, '-e', '-f', '-9', '-S', 'djw', '-A=', '-s', str(tmp / 'a'), str(tmp / 'b'),
                        str(out / 'data' / patch)], check=True)
        # 모드, 차분 파일, 경로, 원본 MD5(디스크 속 파일 그대로), 결과 MD5(gz 는 푼 내용)
        lines.append('\t'.join((mode, patch, rel, md5(old.read_bytes()), md5(B))))
    shutil.rmtree(tmp)
    if not lines:
        raise SystemExit('바뀐 파일이 없습니다')
    (out / 'data' / 'manifest.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    (out / 'data' / 'config.txt').write_text(
        f'id={a.id}\ntitle={a.title}\nresult={a.result}\n', encoding='utf-8')

    tpl = Path(a.templates)
    shutil.copy2(tpl / 'patch.ps1', out / 'patch.ps1')
    shutil.copy2(tpl / '패치하기.bat', out / '패치하기.bat')
    if a.readme:
        shutil.copy2(a.readme, out / Path(a.readme).name)
    (out / 'bin').mkdir()
    for f in WIT_FILES:
        shutil.copy2(Path(a.wit) / f, out / 'bin' / Path(f).name)
    shutil.copy2(Path(a.wit) / 'gpl-2.0.txt', out / 'bin' / 'wit-gpl-2.0.txt')
    shutil.copy2(a.xdelta, out / 'bin' / 'xdelta3.exe')

    zpath = out.parent / (out.name + '.zip')   # with_suffix 는 버전의 점(v1.0f)을 확장자로 봄
    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for dp, _, fs in os.walk(out):
            for f in sorted(fs):
                p = Path(dp) / f
                z.write(p, Path(out.name) / p.relative_to(out))
    size = sum(f.stat().st_size for f in (out / 'data').iterdir())
    print(f'파일 {len(lines)}개(gz {n_gz}개), 차분 합계 {size / 1e6:.2f} MB, zip {zpath.stat().st_size / 1e6:.2f} MB')
    print(f'패처: {out}')


if __name__ == '__main__':
    main()
