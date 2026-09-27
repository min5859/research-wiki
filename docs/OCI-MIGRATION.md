# Research Wiki OCI 마이그레이션 계획

## 1. 목적

macOS에서 매일 실행 중인 Research Wiki 게시 파이프라인을 OCI의 공용
`wiki-publisher` 서비스 계정으로 이전합니다.

```text
OCI research-wiki.timer (매일 04:00 KST)
  -> /srv/research-wiki/run.sh
  -> 논문 수집/PDF 변환/Cursor 분석
  -> min5859/research-wiki Wiki 게시
```

기존 실제 운영 주기인 매일 04:00 KST를 보존합니다. 문서에 남아 있는 매주 월요일
09:00 또는 매일 08:00 표기는 현재 설정과 맞지 않으므로 함께 정리합니다.

## 2. 현재 상태

2026-09-27 기준:

- 로컬 LaunchAgent가 매일 04:00 KST에 실행
- 마지막 정상 게시: 2026-09-27 04:01 KST
- 분석 provider: Codex, 현재 CLI 0.157.0
- 2026-09-14~25는 Codex 0.150.1과 `gpt-6-astra` 비호환으로 분석 실패
- `data/history.json`: 390개
- 실제 Wiki 게시 논문: 362개
- history에만 있는 미게시 논문: 32개
- Wiki에는 있으나 history에 없는 논문: 4개
- 작업 트리에 PDF 변환 후 원본을 삭제하는 `src/convert.py` 변경이 존재
- OCI `/srv/research-wiki`와 research-wiki systemd unit은 아직 없음
- OCI `wiki-publisher` 계정의 Cursor 로그인은 준비됨

## 3. 완료 조건

- 로컬 변경을 누락하지 않고 Git에 반영합니다.
- Cursor Agent와 `claude-sonnet-5-medium` 모델로 전체 dry-run이 성공합니다.
- history는 Wiki push 성공 후에만 갱신됩니다.
- 기존 history를 백업하고 실제 게시된 논문 기준으로 정리합니다.
- Wiki 토큰을 URL이나 명령 인자에 넣지 않습니다.
- pull/clone 실패 시 기존 Wiki clone을 자동 삭제하지 않습니다.
- OCI에서 테스트, Wiki push dry-run, 전체 dry-run이 성공합니다.
- Mac LaunchAgent와 OCI timer가 동시에 활성화되지 않습니다.
- 첫 2회 자동 실행과 Wiki 게시를 확인합니다.

## 4. 코드 준비 계획

### 4.1 기존 `convert.py` 변경

변환된 Markdown이 충분한 크기로 존재할 때 재다운로드 가능한 PDF를 삭제하는 변경을
회귀 테스트로 검증한 뒤 별도 commit으로 반영합니다. Markdown이 없거나 불완전하면
PDF를 보존해야 합니다.

### 4.2 Cursor provider

- `analysis.provider: cursor`
- `analysis.cursor.model: claude-sonnet-5-medium`
- `agent status`로 인증 사전 확인
- `agent -p --mode ask --trust`로 텍스트 분석
- CLI 실패 시 종료 코드와 stderr tail 기록

### 4.3 history 트랜잭션

기존에는 `discover.py`가 선정 즉시 history를 갱신합니다. 이를 제거하고 Wiki push가
성공한 뒤 `publish.py`가 선택 논문 ID를 원자적으로 추가하도록 변경합니다.

기존 history 복구는 Wiki 페이지의 arXiv ID를 기준으로 수행하고 원본을 타임스탬프
백업합니다.

### 4.4 게시 안전장치

- `publish.py --dry-run`
- `RESEARCH_WIKI_DRY_RUN=1` 전체 dry-run
- `GITHUB_WIKI_TOKEN`을 Git subprocess의 일시적 HTTP header로만 전달
- `RESEARCH_WIKI_URL`로 credential 없는 HTTPS remote 지정
- pull/clone 실패 시 기존 작업물을 보존하고 즉시 실패
- `git commit`이 nothing-to-commit이어도 push 단계는 확인

## 5. OCI 준비 계획

```text
사용자: wiki-publisher
코드: /srv/research-wiki
환경: /srv/research-wiki/config/.env
서비스: research-wiki.service
타이머: research-wiki.timer
```

프로젝트별 GitHub 자격증명은 OSS Radar와 분리합니다. `research-wiki` 저장소에만
쓰기 가능한 fine-grained PAT를 사용하거나 기존 token의 선택 저장소에
`research-wiki`를 명시적으로 추가합니다.

```env
GITHUB_WIKI_TOKEN=
RESEARCH_WIKI_URL=https://github.com/min5859/research-wiki.wiki.git
```

서버 준비 단계에서는 timer를 활성화하지 않습니다.

## 6. 검증 계획

1. Python 단위 테스트와 compileall
2. `bash -n run.sh`
3. Cursor 로그인과 모델 smoke test
4. 임시 Wiki clone에서 `git push --dry-run`
5. 전체 파이프라인 dry-run
6. history와 원격 Wiki commit 불변 확인
7. systemd unit 및 calendar 검증

## 7. 컷오버 조건과 순서

먼저 2026-09-28 05:00 KST의 OSS Radar 첫 정기 실행이 새
`wiki-publisher` 계정으로 성공했는지 확인합니다. 그 전에는 Research Wiki writer를
전환하지 않습니다.

조건을 만족하면 다음 순서로 진행합니다.

1. 당일 로컬 04:00 실행 완료 확인
2. Mac `com.wooki.research-wiki` LaunchAgent 중지·비활성화
3. 별도 cron 항목이 없는지 확인
4. OCI `research-wiki.timer` 활성화
5. 다음 04:00 KST 실행과 Wiki 게시 확인
6. 2회 연속 성공 후 완료 판정

## 8. 롤백

OCI writer를 먼저 중지합니다.

```bash
sudo systemctl disable --now research-wiki.timer
sudo systemctl stop research-wiki.service
```

worktree, Wiki clone, history와 미푸시 commit을 검사하며 자동으로 삭제하거나 reset하지
않습니다. OCI 중지를 확인한 뒤에만 Mac LaunchAgent를 복구합니다.

## 9. 실행 기록

### 2026-09-27 로컬 코드 준비

- 기존 PDF 삭제 변경에 회귀 테스트 3개 추가 후 별도 commit
- 분석 provider를 Cursor `claude-sonnet-5-medium`으로 전환
- Cursor 로그인 사전 검사와 ask mode 호출, CLI 오류 tail 기록 추가
- history 갱신을 Wiki push 성공 이후로 이동하고 원자적 저장 적용
- Wiki 인증, clone 보존, push 확인, dry-run 안전장치 추가
- 게시 날짜를 `Asia/Seoul`로 고정해 OCI UTC 서버의 전날 날짜 문제 방지
- history 원본을 `history.json.backup-20260927-212940`으로 백업
- history 390개를 실제 게시 362개로 정리; 양방향 차이 0 확인
- 단위 테스트 10개, compileall, `bash -n`, 게시 단독 dry-run 통과
- Cursor 기반 전체 dry-run 성공: 후보/다운로드/변환/분석 각 2개
- 전체 dry-run 중 history 362개와 원격 Wiki commit 불변 확인

다음 단계는 코드 commit/push 후 OCI 비활성 설치와 서버 dry-run입니다. 실제 writer
컷오버는 OSS Radar의 2026-09-28 05:00 KST 정기 실행 확인 뒤에만 진행합니다.

### 2026-09-27 OCI 비활성 설치

- `/srv/research-wiki`를 `wiki-publisher` 소유로 clone
- Python 3.12 venv와 ARM64 PyMuPDF/PyMuPDF4LLM 의존성 설치
- 정리된 history 362개를 SHA-256 일치 확인 후 전송
- Git 작성자를 `Wooki Min <min5859@gmail.com>`으로 설정
- systemd service/timer 설치와 `systemd-analyze verify` 통과
- `research-wiki.timer`는 `disabled`, `inactive` 상태로 유지
- Cursor 로그인, 단위 테스트 10개, compileall, `bash -n` 통과
- OCI 전체 dry-run 성공: 후보/다운로드/변환/분석 각 2개
- 변환 후 PDF 0개, 분석 2개, history 362개 유지
- dry-run은 Wiki clone을 만들거나 원격 Wiki를 변경하지 않음

설치 중 첫 clone은 `wiki-publisher`가 `/srv` 바로 아래 디렉터리를 생성할 권한이
없어 다음 오류로 중단됐습니다.

```text
fatal: could not create work tree dir '/srv/research-wiki': Permission denied
```

파일이나 timer 변경은 일어나지 않았습니다. root가 빈 `/srv/research-wiki`를
`wiki-publisher` 소유로 생성한 뒤 clone을 재실행해 정상 완료했습니다.

남은 준비 작업:

1. `research-wiki` 저장소 범위의 `GITHUB_WIKI_TOKEN` 입력
2. `scripts/check_wiki_access.py` push dry-run
3. 컷오버 직전 로컬 최신 history 재동기화
4. OSS Radar 첫 정기 실행 성공 확인 후 writer 전환
