# 펀치아웃!! (Wii) 한글 패치

*Punch-Out!!* (Wii, 일본판 `R7PJ01`) 비공식 한국어 팬 패치입니다.
일본판(『パンチアウト!!』) 원문을 기준으로 번역했습니다.

**제작: arqhive** · **최신 버전: [v1.0f](../../releases/tag/v1.0f)**

- 메뉴, 닥 루이스의 조언·응원 대사, 트레이닝 자막, 튜토리얼, 선수 소개·도전 과제, 갤러리·영상 설명, 밸런스 Wii 보드 안내, 세이브·오류 메시지를 한글화했습니다.
- 닥 루이스는 원작처럼 거친 노장 트레이너 말투로 옮겼습니다.
- 타이틀 로고, 포스터, 손목 스트랩 안내 화면, HOME 메뉴, Wii 메뉴 채널 이름·배너를 한글화했습니다.
- 튜토리얼·데모·인트로 영상 속 로고의 「パンチアウト!!」 글씨를 「펀치아웃!!」으로 바꿨습니다.
- 게임 글꼴 2벌에 한글을 넣고, 숫자·영문·기호도 같은 글꼴(G마켓 산스)로 다시 그렸습니다.
- 원작에서도 영어인 문구(PRESS START, KO, 엔딩 크레딧 등)는 영어 그대로 두었습니다.
- **파일 단위 패처**라서 덤프 형태(정본 ISO, WBFS, WBFS에서 변환한 ISO)가 달라도 게임 파일만 같으면 적용됩니다.

> 이 저장소에는 **게임 데이터(롬·디스크 이미지, 추출한 원문 대사, 원본 그래픽, 스크린샷)가 들어 있지 않습니다.**
> 패치를 만들거나 적용하려면 본인이 소유한 게임에서 직접 덤프한 원본이 필요합니다.

## 사용자용: 패치 적용

### 준비물

- 일본판 디스크 이미지(`R7PJ01`, Rev 1). 북미판·유럽판에는 적용할 수 없습니다.
- Windows 10 이상. 패처에 필요한 도구(wit, xdelta3)가 함께 들어 있어 따로 설치할 것은 없습니다.
- 빈 공간 약 10GB.

### 지원 형식

| 원본 | 결과 |
|---|---|
| ISO (정본 덤프, WBFS에서 변환한 ISO) | ISO |
| WBFS | WBFS |
| CISO, WIA, WDF | ISO |
| RVZ | 지원 안 함. Dolphin에서 ISO로 변환한 뒤 적용 |
| NKit | 지원 안 함. 원본 ISO로 복원한 뒤 적용 |

### 적용 방법

1. [릴리즈 페이지](../../releases/latest)에서 `R7PJ_KPatch_v<버전>.zip`을 받아 압축을 풉니다.
2. 원본 이미지를 `패치하기.bat` 위에 끌어다 놓습니다. 원본을 같은 폴더에 두고 더블클릭해도 됩니다.
3. "완료"가 나오면 원본과 같은 폴더에 `Punch-Out!! (Korean) [R7PJ01].iso`(WBFS 원본이면 `.wbfs`)가 생깁니다. 원본은 바뀌지 않습니다.

결과 형식을 바꾸려면 두 번째 인자로 결과 파일을 지정합니다.

```
powershell -ExecutionPolicy Bypass -File patch.ps1 "원본.iso" "결과.wbfs"
```

### 실행 환경

- **확인함**: Dolphin, Wii U vWii(USB Loader GX).

### 알려진 문제

- 실기(Wii·Wii U vWii)에서 메뉴를 뺀 대사·안내 글씨의 테두리가 조금 흐리게 보입니다. 일본어 원판도 똑같이 흐립니다.
  이 게임은 글자를 큰 그림(글자 칸 높이 57픽셀)으로 만들어 두고 화면에 그릴 때 약 0.6배로 줄여 그리는데, 실기는 이때 픽셀을 섞어 줄이기 때문에 테두리가 번져 보입니다. Dolphin에서 내부 해상도를 높이면 또렷하게 보입니다.

## 개발자용: 직접 빌드

### 요구 사항

- Python 3.11 이상. `pip install -r requirements.txt`로 numpy, Pillow, fontTools, OpenCV를 설치합니다.
- 일본판 ISO(`R7PJ01` Rev 1). DATA 파티션을 `work/jp/DATA`에 풀어 둡니다(`wit extract 원본.iso work/jp --psel data`).
- G마켓 산스 Bold(`GmarketSansBold.otf`). **저장소에 들어 있지 않으니** 따로 받아 Windows에 설치하거나 `tools/fonts`에 두세요.
- [wit](https://wit.wiimm.de/)(Wiimms ISO Tools)과 xdelta3. `tools/bin/wit-v3.05a-r8638-cygwin64/`, `tools/bin/xdelta3.exe`에 둡니다.

### 빌드

```bash
python tools/inspect_editions.py        # 원문 목록(work/translation/source-texts.json)
python tools/extract_system_assets.py   # HOME 메뉴·크레딧 원문
python tools/assemble_translation.py    # 번역 TSV를 원문 목록에 맞춰 조립·검사
python tools/build_korean_fonts.py      # 한글 글꼴 2벌
python tools/prepare_image_assets.py    # 그림 글씨
python tools/build_logo_videos.py       # 영상 속 로고 글씨
python tools/build_patch_files.py       # work/patched/DATA에 바뀐 파일 넣기

# 한글 ISO 만들기 (work/patched/DATA에서 실행)
wit copy . ../../../build/Punch-Out-KO.iso --iso --psel DATA

# 배포용 패처 만들기 (바뀐 파일만 work/release-build에 모은 뒤)
python tools/make_patcher.py --orig work/jp/DATA --build work/release-build --out release/R7PJ_KPatch_v1.0f \
  --id R7PJ01 --title "펀치아웃!!" --result "Punch-Out!! (Korean) [R7PJ01]" \
  --wit tools/bin/wit-v3.05a-r8638-cygwin64 --xdelta tools/bin/xdelta3.exe \
  --readme release/README_한국어.txt --templates patcher
```

Windows Git Bash에서는 `PYTHONIOENCODING=utf-8`을 붙이세요.

### 번역 수정

- 번역: [`work/translation/ko-*.tsv`](work/translation)의 `키<TAB>한국어`를 고친 뒤 빌드합니다. `{p}`는 줄바꿈, `{clr:…}` 등은 제어 태그라 그대로 둡니다.
- 버튼 문장의 `=`는 A 버튼 아이콘 자리입니다. 아이콘은 원문 줄을 가운데 정렬했을 때 `=`가 오는 화면 위치에 고정되므로, `=` 앞뒤 빈칸 수를 바꾸지 마세요.
- 그림 글씨 PNG는 원본 게임 그림을 고친 것이라 저장소에 넣지 않습니다.

`ko-*.tsv`에는 **번역문과 키만** 들어 있습니다. 일본어 원문은 게임 데이터라 넣지 않았습니다.

### 폴더 구조

```
tools/               빌드 도구
  bin/               (git 제외) wit, xdelta3
  fonts/             (git 제외) G마켓 산스
patcher/             사용자용 파일 단위 패처(패치하기.bat, patch.ps1)
release/             패처 설명서(README_한국어.txt), 패처 폴더·zip은 git 제외
work/translation/    번역 TSV (키, 한국어)
manifests/           파일·그림·영상 목록과 빌드 기록
docs/releases/       릴리즈 노트
work/                (git 제외) 추출본·빌드 결과
```

## 변경 내역

전체 내역은 [`CHANGELOG.md`](CHANGELOG.md)에 있습니다.

## 크레딧·라이선스

- 이 저장소의 도구 코드, 한국어 번역문, 문서: [MIT License](LICENSE) (© 2026 arqhive).
- 글꼴: G마켓 산스는 저장소에 포함하지 않음.

## 면책

비공식 팬 번역이며 Nintendo와 관련이 없습니다. 「펀치아웃!!」 관련 상표·저작권은 Nintendo와 Next Level Games에 있습니다.
패치를 적용한 게임 파일의 배포를 금지합니다.
