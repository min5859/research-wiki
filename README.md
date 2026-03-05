# Research Wiki Pipeline

매주 트렌딩 AI 논문 2편을 자동 수집, 분석하여 [GitHub Wiki](https://github.com/min5859/research-wiki/wiki)에 발행하는 파이프라인.

## 동작 흐름

```
run.sh (macOS launchd 매일 08:00)
  │
  ├─ 1. discover.py   → HF Daily Papers + Semantic Scholar에서 상위 2편 선정
  ├─ 2. download.py   → arXiv PDF 다운로드
  ├─ 3. convert.py    → PDF → Markdown 변환 (pymupdf4llm)
  ├─ 4. analyze.sh    → Claude Code CLI로 한국어 분석 리포트 생성
  └─ 5. publish.py    → GitHub Wiki에 자동 발행
```

## 새 PC 셋업 가이드

### 1. 시스템 요구사항 설치

```bash
# Python 3.10+ 확인
python3 --version

# Node.js (Claude Code CLI 설치에 필요)
node --version

# Claude Code CLI 설치 및 인증
npm install -g @anthropic-ai/claude-code
claude  # 최초 실행 시 인증 진행
```

### 2. SSH Key 설정 (GitHub push용)

```bash
# 이미 있으면 스킵
ssh-keygen -t ed25519
cat ~/.ssh/id_ed25519.pub
# → https://github.com/settings/keys 에 등록

# 연결 확인
ssh -T git@github.com
```

### 3. 프로젝트 클론 및 의존성 설치

```bash
git clone git@github.com:min5859/research-wiki.git
cd research-wiki
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Wiki 레포 클론 (publish에 필요)

`publish.py`가 첫 실행 시 자동으로 clone하지만, 미리 준비하려면:

```bash
mkdir -p data
git clone git@github.com:min5859/research-wiki.wiki.git data/wiki_clone
```

### 5. 수동 실행 테스트

```bash
source .venv/bin/activate
bash run.sh
```

### 6. 자동 실행 등록 (macOS launchd)

macOS에서는 cron 대신 **launchd**를 사용합니다. launchd는 사용자 세션에서 실행되어 Claude CLI의 OAuth 인증이 안정적으로 동작합니다.

```bash
# 심볼릭 링크 생성
ln -s /path/to/research-wiki/config/com.wooki.research-wiki.plist ~/Library/LaunchAgents/

# 에이전트 등록
launchctl load ~/Library/LaunchAgents/com.wooki.research-wiki.plist
```

주요 launchctl 명령어:

```bash
# 상태 확인
launchctl list | grep research-wiki

# 즉시 실행 (테스트용)
launchctl start com.wooki.research-wiki

# 중지 (등록 해제)
launchctl unload ~/Library/LaunchAgents/com.wooki.research-wiki.plist

# plist 수정 후 재등록
launchctl unload ~/Library/LaunchAgents/com.wooki.research-wiki.plist
launchctl load ~/Library/LaunchAgents/com.wooki.research-wiki.plist
```

> **참고**: plist 파일은 `config/com.wooki.research-wiki.plist`에 있으며 매일 08:00에 실행됩니다. 스케줄 변경은 plist의 `StartCalendarInterval`을 수정 후 재등록하세요.

#### launchd vs systemd 비교 (Linux 사용자 참고)

| systemd (Linux) | launchd (macOS) | 설명 |
|---|---|---|
| `systemctl enable` | `launchctl load` | 등록 (재부팅 후에도 유지) |
| `systemctl disable` | `launchctl unload` | 등록 해제 |
| `systemctl start` | `launchctl start` | 수동 1회 실행 |

- `load` 상태에서는 매일 08:00에 **자동 실행**되고, 재부팅 후 로그인 시에도 스케줄이 유지됩니다.
- 자동 실행 없이 **수동으로만** 실행하려면 `unload`로 해제 후 필요할 때 `bash run.sh`를 직접 실행하세요.
- launchd는 `load` 없이 `start`만 하는 것은 지원되지 않습니다. 반드시 `load` → `start` 순서로 실행해야 합니다.

### 7. 로그 확인

```bash
# 파이프라인 전체 로그 (실시간 모니터링)
tail -f logs/cron.log

# 최근 로그 확인
tail -50 logs/cron.log

# 각 단계별 상세 로그
tail -50 logs/discover.log   # 논문 검색
tail -50 logs/analyze.log    # Claude 분석 (인증 실패, 재시도 등)
tail -50 logs/publish.log    # Wiki 발행

# launchd 시스템 로그 (plist 로드 실패 등)
log show --predicate 'senderImagePath contains "launchd"' --info --last 1h | grep research-wiki
```

## 설정

`config.yaml`에서 논문 수, 검색 기간, 소스 가중치 등을 조정할 수 있습니다.

```yaml
papers:
  count: 2            # 주당 분석 논문 수
  lookback_days: 7    # 검색 기간

sources:
  huggingface:
    weight: 0.7       # upvote 기반 스코어 가중치
  semantic_scholar:
    weight: 0.3       # citation 기반 스코어 가중치
```

## 프로젝트 구조

```
├── src/
│   ├── discover.py      # 트렌딩 논문 검색 및 스코어링
│   ├── download.py      # PDF 다운로드 (arXiv + S2 fallback)
│   ├── convert.py       # PDF → Markdown 변환
│   ├── analyze.sh       # Claude Code CLI 분석
│   └── publish.py       # GitHub Wiki 발행
├── prompts/
│   └── analyze.md       # 분석 프롬프트 템플릿
├── config/
│   └── com.wooki.research-wiki.plist  # macOS launchd 스케줄 설정
├── config.yaml          # 설정
├── requirements.txt     # Python 의존성
├── run.sh               # 파이프라인 오케스트레이터
├── data/                # 런타임 데이터 (gitignore)
│   ├── papers.json      # 선정된 논문 목록
│   ├── history.json     # 분석 완료 논문 ID (중복 방지)
│   ├── pdfs/            # 다운로드된 PDF
│   ├── markdown/        # 변환된 Markdown
│   └── analysis/        # Claude 분석 결과
└── logs/                # 실행 로그 (gitignore)
```
