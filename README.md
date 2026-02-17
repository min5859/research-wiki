# Research Wiki Pipeline

매주 트렌딩 AI 논문 2편을 자동 수집, 분석하여 [GitHub Wiki](https://github.com/min5859/research-wiki/wiki)에 발행하는 파이프라인.

## 동작 흐름

```
run.sh (cron 매주 월 09:00 KST)
  │
  ├─ 1. discover.py   → HF Daily Papers + Semantic Scholar에서 상위 2편 선정
  ├─ 2. download.py   → arXiv PDF 다운로드
  ├─ 3. convert.py    → PDF → Markdown 변환 (pymupdf4llm)
  ├─ 4. analyze.sh    → Claude Code CLI로 한국어 분석 리포트 생성
  └─ 5. publish.py    → GitHub Wiki에 자동 발행
```

## 사전 요구사항

- Python 3.10+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) (인증 완료 상태)
- Git + SSH Key (GitHub push용)

## 설치

```bash
git clone git@github.com:min5859/research-wiki.git
cd research-wiki
pip install -r requirements.txt
```

## 실행

```bash
# 수동 실행
bash run.sh

# cron 등록 (매주 월요일 09:00 KST = 00:00 UTC)
crontab -e
# 아래 한 줄 추가:
# 0 0 * * 1 cd /path/to/research-wiki-pipeline && bash run.sh >> logs/cron.log 2>&1
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
