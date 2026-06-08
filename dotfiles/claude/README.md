# Claude Code 사용자 설정 dotfiles

`~/.claude/` 에 들어가는 사용자 단위 설정을 git으로 관리하기 위한 폴더. 노트북을 옮기거나 새로 세팅할 때 1회 실행으로 statusline + 기본 설정을 동기화한다.

## 포함 파일

| 파일 | 역할 |
|------|------|
| `settings.json` | `~/.claude/settings.json` 본체. statusLine 명령과 자동업데이트 채널 등 |
| `statusline.sh` | 모델 / CTX 사용률 / 5시간·7일 남은 한도 / 누적 비용 표시 (bash) |
| `skills/` | 사용자 정의 슬래시 커맨드 (`start-project`, `wrap-up` 등) |
| `bootstrap.bat` | 새 노트북에서 위 파일들을 `~/.claude/`로 복사 (Windows용) |

`statusline.sh` 컬러 코드:
- CTX 사용률: 0~25 녹색 / 25~50 노랑 / 50+ 빨강 (높으면 나쁨)
- 5h / 7d 남은 %: 60+ 녹색 / 30~60 노랑 / <30 빨강 (낮으면 나쁨)

## 새 노트북에서 적용

1. `D:\AX` 리포를 git clone (또는 이미 있으면 pull).
2. 탐색기에서 `D:\AX\dotfiles\claude\bootstrap.bat` 더블클릭.
3. 기존 `~/.claude/settings.json`·`statusline.sh` 가 있으면 자동으로 `.bak` 백업.
4. Claude Code 재시작.

bash가 필요하다 (Git Bash 또는 WSL). Git for Windows를 깔았으면 PATH에 이미 있을 가능성이 높음.

## 수정 흐름

1. `~/.claude/settings.json` 또는 `~/.claude/statusline.sh` 를 수정해서 동작 확인.
2. 만족하면 `D:\AX\dotfiles\claude\` 의 동명 파일을 같은 내용으로 갱신.
3. 커밋·푸시.
4. 다른 노트북에선 git pull 후 `bootstrap.bat` 재실행.

## 주의

- `.bat` 파일은 ASCII로만 작성. 한국어 Windows cmd는 CP949라 UTF-8 한국어/em-dash가 들어가면 exit 255로 즉사한다. 한국어 안내는 이 README에만.
- 백업본(`.bak`)은 덮어쓰기 방지용. 한 번 더 부트스트랩하면 직전 백업이 사라지니, 보존하고 싶으면 따로 옮길 것.
