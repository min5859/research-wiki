# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

매주 트렌딩 AI 논문 2편을 자동 수집·분석하여 GitHub Wiki에 한국어 리포트로 발행하는 파이프라인.

- Wiki: https://github.com/min5859/research-wiki/wiki
- Cron: 매주 월요일 00:00 UTC (09:00 KST)

## Commands

```bash
# 전체 파이프라인 실행
bash run.sh

# 개별 단계 실행
python3 src/discover.py    # 논문 검색 → data/papers.json
python3 src/download.py    # PDF 다운로드 → data/pdfs/
python3 src/convert.py     # PDF→Markdown → data/markdown/
bash src/analyze.sh        # Claude 분석 → data/analysis/
python3 src/publish.py     # Wiki 발행

# 의존성 설치
pip install -r requirements.txt
```

## Architecture

5단계 선형 파이프라인. 각 단계는 `data/` 내 파일을 읽고 쓰며 다음 단계에 전달한다.

```
discover → papers.json → download → pdfs/ → convert → markdown/ → analyze → analysis/ → publish → Wiki
```

- **papers.json**: 모든 단계가 참조하는 중심 메타데이터 (각 단계에서 pdf_path, md_path 등 필드 추가)
- **history.json**: 이전에 분석한 논문 ID 기록 (중복 방지)
- **config.yaml**: 논문 수, 검색 기간, 소스 가중치, Wiki repo 설정

## Key Design Decisions

- **스코어링**: `(upvotes/max) * 0.7 + (citations/max) * 0.3`으로 HF와 S2 합산
- **Fallback**: PDF 다운로드 실패 시 S2 openAccessPdf → 변환 실패 시 abstract로 대체
- **멱등성**: 각 단계에서 출력 파일이 이미 존재하면 스킵
- **분석 호출**: `env -u CLAUDECODE claude -p` — 중첩 세션 방지를 위해 CLAUDECODE 환경변수 해제 필요
- **bkit footer 제거**: analyze.sh에서 Claude 출력의 bkit 보고 블록을 sed로 자동 제거
- **Paper 최대 길이**: 80,000자 초과 시 truncate (Claude 컨텍스트 제한)

## Conventions

- 모든 Python 스크립트는 stdout + `logs/{module}.log` 이중 로깅
- 분석 리포트 언어: 한국어 (prompts/analyze.md 템플릿)
- Wiki 페이지 명명: `YYYY-MM-DD-Weekly-AI-Paper-Review.md`
- data/, logs/ 디렉토리는 gitignore 대상 (런타임 생성)
