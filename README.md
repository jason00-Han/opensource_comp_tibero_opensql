<div align="center">

# Tibero Doc

### 멈추지 않는 OpenSQL 위에서, 문서를 이해하고 답하는 AI 문서 플랫폼

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-REST_API-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/OpenSQL-pgvector-4169E1?logo=postgresql&logoColor=white)](docs/development-guide.md)
[![MCP](https://img.shields.io/badge/MCP-ready-7C3AED)](docs/development-guide.md)
[![License](https://img.shields.io/badge/License-Open_Source-22C55E)](#라이선스)

문서를 올리면 자동으로 내용을 분석하고, 키워드·의미·관계를 함께 검색합니다.<br>
사용자는 데이터베이스 접속 정보를 몰라도 CLI와 웹에서 안전하게 문서를 찾고 질문할 수 있습니다.

**[빠른 시작](#-빠른-시작)** · **[사용자 가이드](#-사용자-가이드)** · **[관리자 가이드](#-관리자-가이드)** · **[개발자 문서](#-개발자-문서)**

</div>

---

## 왜 Tibero Doc인가요?

| 기존 문서 관리 | Tibero Doc |
|---|---|
| 파일명과 정확한 단어를 알아야 검색 | 표현이 달라도 의미가 가까운 문서 검색 |
| 같은 문서의 긴 본문을 일일이 확인 | 관련 문장과 PDF 페이지를 근거로 표시 |
| 문서 추가 후 별도 색인 작업 | 업로드 즉시 추출·청킹·임베딩·그래프 색인 |
| 사용자마다 DB 접속 정보 필요 | 사용자는 API 주소와 계정만으로 이용 |
| 서버 장애 시 수동 대응 | OpenSQL 고가용성과 Worker 기반 분산 처리 |
| 검색 결과만 제공 | 자연어 답변과 인용 문서를 함께 제공 |

## ✨ 핵심 기능

| 기능 | 사용자가 얻는 가치 |
|---|---|
| **통합 문서 수집** | PDF, DOCX, TXT, HTML 파일 또는 폴더를 한 번에 업로드 |
| **의미 기반 검색** | `bge-m3`로 문장의 의미가 비슷한 문서 탐색 |
| **Graph + Vector 검색** | 인물·조직·시스템·정책·프로젝트 관계까지 함께 검색 |
| **근거 중심 결과** | 문서별 상위 근거 3개, 일치 단어, PDF 페이지 표시 |
| **문서 질의응답** | 질문에 답하고 사용한 문서와 청크를 인용 |
| **안전한 공유** | 워크스페이스, 역할, 사용자·그룹별 문서 ACL 적용 |
| **변경 추적** | 문서 버전 이력과 변경 파일 증분 동기화 |
| **운영 관리** | 감사 로그, Rate Limit, Redis 캐시, MinIO/S3 원본 저장 |
| **다양한 연결 방식** | Web UI, CLI, REST API, MCP 지원 |

## 🧭 서비스 이용 흐름

```mermaid
flowchart LR
    A["문서 업로드"] --> B["자동 분석·색인"]
    B --> C["키워드 + 벡터 + 그래프 검색"]
    C --> D["문서별 근거 확인"]
    D --> E["자연어 질문·답변"]
```

## 🚀 빠른 시작

### 1. 설치

<details open>
<summary><strong>Windows PowerShell</strong></summary>

```powershell
cd C:\path\to\tibero-doc
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e services\api -e cli
```

</details>

<details>
<summary><strong>WSL / Linux</strong></summary>

```bash
sudo apt install -y python3-venv
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e services/api -e cli
```

</details>

### 2. 시작 마법사

서버 관리자가 최초 한 번 실행합니다.

```powershell
tibero-doc setup
```

마법사가 OpenProxy 연결, 저장 위치, 임베딩 모델과 최초 관리자 계정을 설정합니다. DB 비밀번호는 설정 파일에 평문으로 기록하지 않습니다.

### 3. 서버 실행

```powershell
tibero-doc serve
```

| 접속 대상 | 주소 또는 명령 |
|---|---|
| Web UI | <http://localhost:8000/ui/> |
| API 문서 | <http://localhost:8000/docs> |
| 상태 확인 | `tibero-doc status` |
| 자동 진단 | `tibero-doc doctor` |

### 4. 첫 문서 검색

새 터미널에서 가상환경을 활성화한 뒤 실행합니다.

```powershell
tibero-doc ingest .\documents
tibero-doc search "장애 복구 절차"
tibero-doc ask "장애가 발생하면 어떻게 복구해야 하는지 근거와 함께 알려줘"
```

> [!TIP]
> 일반 사용자는 OpenSQL 호스트와 DB 비밀번호가 필요하지 않습니다. 관리자가 전달한 서버 주소와 초대 토큰만 사용합니다.

## 👤 사용자 가이드

### 로그인과 계정 확인

```powershell
tibero-doc login --email user@example.com
tibero-doc whoami
tibero-doc refresh
```

초대받은 사용자는 다음 명령으로 가입합니다.

```powershell
tibero-doc join INVITE_TOKEN `
  --email user@example.com `
  --name "홍길동" `
  --server http://docs-server:8000
```

### 문서 업로드와 처리 상태

```powershell
# 파일 하나
tibero-doc ingest .\documents\policy.pdf

# 폴더 전체
tibero-doc ingest .\documents

# 비동기 작업 상태
tibero-doc job <JOB_ID>
```

지원 형식: **PDF · DOCX · TXT · HTML**

### 문서 조회

```powershell
tibero-doc list
tibero-doc show <DOCUMENT_ID>
tibero-doc versions <DOCUMENT_ID>
tibero-doc download <DOCUMENT_ID> --output report.pdf
```

### 문서 검색

기본 `hybrid` 검색은 키워드, 의미 유사도와 지식 그래프 결과를 함께 사용합니다. 같은 문서의 여러 청크는 하나의 카드로 묶이고 가장 관련 있는 근거만 표시됩니다.

```powershell
tibero-doc search "OpenSQL 장애 정책"
tibero-doc search "OpenSQL 고가용성" --top-k 10
```

| 모드 | 설명 | 예시 |
|---|---|---|
| `keyword` | 질문 단어가 등장하는 문서 | `--mode keyword` |
| `vector` | 표현은 달라도 의미가 비슷한 문서 | `--mode vector` |
| `graph` | 인물·조직·시스템·정책 관계 | `--mode graph` |
| `hybrid` | 세 결과를 통합하는 기본 모드 | `--mode hybrid` |

검색 점수를 확인하려면 `--explain`을 추가합니다.

```powershell
tibero-doc search "OpenSQL 장애 정책" --mode hybrid --explain
```

관련도가 기준보다 낮으면 무관한 문서를 억지로 보여주지 않고 다음과 같이 안내합니다.

```text
관련성이 높은 문서를 찾지 못했습니다.
```

### 문서에 질문하기

```powershell
tibero-doc ask "고가용성과 관련된 문서를 찾아서 핵심 내용을 설명해줘"
```

답변과 함께 참고 문서, 근거 청크와 관련 엔티티가 표시됩니다.

### 동기화와 삭제

```powershell
tibero-doc sync
tibero-doc delete <DOCUMENT_ID>
```

## 🧠 실제 의미 검색 사용

로컬에서 API 키 없이 다국어 의미 검색을 사용하려면 Ollama와 `bge-m3`를 실행합니다.

```powershell
docker compose --profile ai up -d ollama
docker exec opensource_comp_tibero_opensql-ollama-1 ollama pull bge-m3
```

`tibero-doc setup`에서 다음 값을 선택합니다.

```text
임베딩 방식: ollama
임베딩 모델: bge-m3
```

모델을 변경했다면 기존 문서를 한 번 다시 임베딩합니다.

```powershell
tibero-doc embedding-reindex
```

> [!NOTE]
> 데모용 `local-hash-384`는 의미 검색 순위에서 제외됩니다. 실제 의미 검색에는 `bge-m3` 같은 임베딩 모델을 사용하세요.

## 🔗 문서 관계와 지식 그래프

문서에서 인물, 조직, 시스템, 정책, 프로젝트와 주제를 추출하고, 문서·청크 단위 근거와 함께 관계를 저장합니다.

```powershell
# 문서의 엔티티와 관계 조회
tibero-doc graph <DOCUMENT_ID>

# 기존 문서 전체 그래프 재색인
tibero-doc graph-reindex

# 관계 기반 검색
tibero-doc search "OpenSQL을 사용하는 프로젝트" --mode graph
```

## 👥 협업과 권한

### 워크스페이스

```powershell
tibero-doc workspace list
tibero-doc workspace use <WORKSPACE_ID>
```

### 그룹

```powershell
tibero-doc group create Readers
tibero-doc group list
tibero-doc group add-member <GROUP_ID> <USER_ID>
tibero-doc group remove-member <GROUP_ID> <USER_ID>
```

### 문서 ACL

```powershell
tibero-doc acl grant <DOCUMENT_ID> <PRINCIPAL_ID> --type group --permission read
tibero-doc acl list <DOCUMENT_ID>
tibero-doc acl revoke <DOCUMENT_ID> <PRINCIPAL_ID> --type group
```

검색, 질문, 본문 조회와 다운로드는 모두 문서 ACL을 먼저 확인합니다.

## 🛡️ 관리자 가이드

### 사용자 초대와 관리

```powershell
tibero-doc invite user@example.com --role editor
tibero-doc user list
tibero-doc user change-role <USER_ID> editor
tibero-doc user disable <USER_ID>
```

역할은 `viewer`, `editor`, `manager`, `owner`로 구분됩니다.

<details>
<summary><strong>서비스와 Worker 관리 명령 보기</strong></summary>

```powershell
tibero-doc status
tibero-doc doctor

tibero-doc worker serve ingest
tibero-doc worker serve embedding
tibero-doc worker serve sync
tibero-doc worker status

tibero-doc storage status
tibero-doc deploy check
tibero-doc audit --limit 100
```

</details>

<details>
<summary><strong>보관 정책과 OpenSQL Failover 명령 보기</strong></summary>

```powershell
tibero-doc retention plan --hot-days 30 --cold-days 180 --delete-days 365
tibero-doc failover demo
```

보관 계획은 삭제 후보만 표시하며 자동 삭제하지 않습니다. Failover 시연은 다중 노드 OpenSQL 환경에서 사용합니다.

</details>

## 🔌 MCP 연결

로컬 stdio 서버:

```powershell
tibero-doc mcp serve
```

Streamable HTTP 서버:

```powershell
tibero-doc mcp serve --transport streamable-http --port 8001
tibero-doc mcp status
```

MCP 클라이언트는 문서 검색·조회, 지식 그래프, 작업 상태와 문서 통계를 사용할 수 있습니다. 로컬 MCP와 Ollama에는 API 키가 필요하지 않습니다.

> [!WARNING]
> MCP HTTP 서버를 외부에 공개할 때는 Nginx/API Gateway에서 TLS와 별도 접근 인증을 적용하세요.

## 🩺 문제 해결

문제가 생기면 가장 먼저 자동 진단을 실행합니다.

```powershell
tibero-doc doctor
```

| 증상 | 확인할 항목 |
|---|---|
| API 연결 실패 | `tibero-doc serve`가 실행 중인지 확인 |
| 업로드 작업이 계속 대기 | RabbitMQ와 `ingest`, `embedding` Worker 확인 |
| 의미 검색 결과 없음 | Ollama, `bge-m3`, `embedding-reindex` 확인 |
| 문서가 보이지 않음 | 현재 워크스페이스와 문서 ACL 확인 |
| OpenSQL 로그인 실패 | OpenProxy 호스트·포트와 DB 비밀번호 확인 |

설정 확인과 초기화:

```powershell
tibero-doc config show
tibero-doc config path
tibero-doc config reset
```

## 📚 개발자 문서

README는 사용자 사용법에 집중합니다. 구현 구조와 운영 상세는 다음 문서에서 확인할 수 있습니다.

- [개발 및 아키텍처 가이드](docs/development-guide.md)
- [데이터 플랫폼 운영 가이드](docs/data-platform-operations.md)
- [전체 코드 리뷰 가이드](docs/code-review-guide.md)
- [비정형 데이터 수명주기](docs/unstructured-data-lifecycle.md)

## 라이선스

오픈소스 대회 제출 전 프로젝트에 적용할 라이선스를 확정하고 `LICENSE` 파일을 추가해 주세요.

---

<div align="center">

**Tibero Doc — 기업 문서를 안전하게 연결하고, 근거와 함께 답합니다.**

</div>
