# Tibero Doc

Tibero Doc은 팀 문서를 안전하게 모으고, 필요한 내용을 검색하거나 질문할 수 있는 OpenSQL 기반 문서 관리 서비스입니다.

사용자는 데이터베이스 주소를 알 필요 없이 CLI 또는 웹 브라우저로 문서를 업로드하고 검색할 수 있습니다. 관리자는 사용자, 그룹, 문서 권한과 감사 기록을 관리할 수 있습니다.

## 사용자가 할 수 있는 일

- PDF, DOCX, TXT, HTML 문서 업로드
- 제목·본문을 이용한 문서 검색
- 의미가 비슷한 문서와 관련 엔티티 검색
- 자연어로 질문하고 근거 문서와 함께 답변받기
- 문서 목록, 본문, 버전 이력 조회
- 권한이 있는 원본 문서 다운로드
- 변경된 문서 자동 동기화
- 개인 또는 그룹별 문서 공유
- 여러 워크스페이스 전환
- 웹 UI, CLI, MCP 클라이언트 사용

## 빠른 시작

### 1. 설치

Windows PowerShell:

```powershell
cd C:\path\to\tibero-doc
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e services\api -e cli
```

WSL/Linux:

```bash
sudo apt install -y python3-venv
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e services/api -e cli
```

### 2. 최초 관리자 설정

서버 관리자가 한 번만 실행합니다.

```powershell
tibero-doc setup
```

마법사가 API 주소, OpenProxy 접속 정보, 문서 저장 위치, 임베딩 방식과 최초 관리자 계정을 설정하고 연결 상태를 검사합니다. 비밀번호는 설정 파일에 평문으로 저장하지 않습니다.

설정에 문제가 있다면 다음 명령으로 원인과 해결 방법을 확인합니다.

```powershell
tibero-doc doctor
```

### 3. 서버 실행

```powershell
tibero-doc serve
```

기본 접속 주소:

- 웹 UI: <http://localhost:8000/ui/>
- API 문서: <http://localhost:8000/docs>
- 상태 확인: `tibero-doc status`

서버는 실행한 터미널을 종료할 때까지 동작합니다. CLI를 사용할 때는 새 터미널을 열어 가상환경을 활성화합니다.

## 로그인과 초대

### 기존 사용자 로그인

```powershell
tibero-doc login --email user@example.com
tibero-doc whoami
```

### 새 사용자 초대

Manager 또는 Owner가 초대를 생성합니다.

```powershell
tibero-doc invite user@example.com --role editor
```

초대받은 사용자는 전달받은 토큰과 서버 주소만 입력합니다. OpenSQL 주소와 DB 비밀번호는 필요하지 않습니다.

```powershell
tibero-doc join INVITE_TOKEN `
  --email user@example.com `
  --name "홍길동" `
  --server http://docs-server:8000
```

Access Token을 갱신하려면 다음 명령을 사용합니다.

```powershell
tibero-doc refresh
```

## 문서 사용법

### 문서 업로드

파일 하나 또는 디렉터리를 업로드할 수 있습니다.

```powershell
tibero-doc ingest .\documents\policy.pdf
tibero-doc ingest .\documents
```

업로드 결과로 표시되는 `JOB_ID`는 처리 상태를 확인할 때 사용합니다.

```powershell
tibero-doc job <JOB_ID>
```

### 문서 목록과 본문 조회

```powershell
tibero-doc list
tibero-doc show <DOCUMENT_ID>
tibero-doc versions <DOCUMENT_ID>
```

### 문서 검색

별도 옵션 없이 검색하면 키워드, 의미 유사도, 문서 관계를 함께 사용합니다.

```powershell
tibero-doc search "장애 복구 절차"
tibero-doc search "OpenSQL 고가용성" --top-k 10
```

필요하면 검색 방식을 선택할 수 있습니다.

```powershell
tibero-doc search "접근 통제 정책" --mode keyword
tibero-doc search "비슷한 보안 규정" --mode vector
tibero-doc search "OpenSQL을 사용하는 프로젝트" --mode graph
tibero-doc search "OpenSQL 장애 정책" --mode hybrid
```

- `keyword`: 질문에 포함된 단어가 등장하는 문서 검색
- `vector`: 표현이 달라도 의미가 비슷한 문서 검색
- `graph`: 인물·조직·시스템·정책·프로젝트와 그 관계 검색
- `hybrid`: 세 검색 결과를 함께 사용하며 기본값

### 문서에 질문하기

```powershell
tibero-doc ask "고가용성과 관련된 문서를 찾아서 핵심 내용을 설명해줘"
```

답변에는 참고한 문서와 근거 청크가 함께 표시됩니다. 기본 설정은 외부 API 키가 필요 없는 로컬 답변 방식입니다.

### 원본 다운로드와 삭제

```powershell
tibero-doc download <DOCUMENT_ID> --output report.pdf
tibero-doc delete <DOCUMENT_ID>
```

삭제는 권한이 있는 사용자만 실행할 수 있습니다.

### 변경 문서 동기화

```powershell
tibero-doc sync
```

설정된 문서 디렉터리에서 추가되거나 수정된 파일만 다시 처리합니다.

## 문서 관계 확인

업로드한 문서에서 추출된 인물, 조직, 시스템, 정책, 프로젝트와 관계를 확인할 수 있습니다.

```powershell
tibero-doc graph <DOCUMENT_ID>
```

기존 문서를 새로운 그래프 검색에 포함해야 할 때 Manager가 전체 재색인을 실행합니다.

```powershell
tibero-doc graph-reindex
```

## 그룹과 문서 공유

### 그룹 관리

```powershell
tibero-doc group create Readers
tibero-doc group list
tibero-doc group add-member <GROUP_ID> <USER_ID>
tibero-doc group remove-member <GROUP_ID> <USER_ID>
```

### 문서 권한 부여

사용자나 그룹에 문서별 권한을 부여할 수 있습니다.

```powershell
tibero-doc acl grant <DOCUMENT_ID> <PRINCIPAL_ID> --type group --permission read
tibero-doc acl list <DOCUMENT_ID>
tibero-doc acl revoke <DOCUMENT_ID> <PRINCIPAL_ID> --type group
```

검색, 질문, 본문 조회, 다운로드 모두 이 권한을 따릅니다.

## 워크스페이스 사용

```powershell
tibero-doc workspace list
tibero-doc workspace use <WORKSPACE_ID>
```

워크스페이스를 바꾸면 문서, 검색 결과, 그룹과 권한도 선택한 워크스페이스 기준으로 전환됩니다.

## 관리자 명령

### 사용자 관리

```powershell
tibero-doc user list
tibero-doc user change-role <USER_ID> editor
tibero-doc user disable <USER_ID>
```

역할은 `viewer`, `editor`, `manager`, `owner`로 구분됩니다.

### 감사 로그

```powershell
tibero-doc audit --limit 100
```

로그인, 문서 조회, 권한 변경, 다운로드 등 주요 활동을 확인할 수 있습니다.

### 서비스 상태 진단

```powershell
tibero-doc status
tibero-doc worker status
tibero-doc storage status
tibero-doc mcp status
tibero-doc deploy check
```

### 데이터 보관 계획 확인

```powershell
tibero-doc retention plan --hot-days 30 --cold-days 180 --delete-days 365
```

이 명령은 보관 계획을 보여줍니다. 실제 삭제 정책을 적용하기 전에는 조직의 보안·법무 기준을 확인해야 합니다.

### OpenSQL Failover 시연

```powershell
tibero-doc failover demo
```

다중 노드 OpenSQL 환경이 준비된 경우 현재 Primary 중단과 새 Primary 선출 과정을 확인합니다.

## MCP 사용

로컬 MCP 서버를 실행합니다.

```powershell
tibero-doc mcp serve
```

HTTP 방식으로 실행하려면 다음과 같이 지정합니다.

```powershell
tibero-doc mcp serve --transport streamable-http --port 8001
```

MCP 클라이언트에서는 다음 기능을 사용할 수 있습니다.

- 문서 검색
- 문서 목록 및 본문 조회
- 문서 엔티티·관계 조회
- 작업 상태 확인
- 문서 통계 조회

로컬 MCP와 기본 로컬 임베딩에는 API 키가 필요하지 않습니다. 외부에 MCP HTTP 서버를 공개할 때는 TLS와 별도 접근 인증을 설정해야 합니다.

## 설정 관리

```powershell
tibero-doc config show
tibero-doc config path
tibero-doc config reset
```

`config reset`은 현재 CLI 설정을 초기화하므로 다시 `tibero-doc setup` 또는 `tibero-doc join`을 실행해야 합니다.

## 문제가 생겼을 때

먼저 자동 진단을 실행합니다.

```powershell
tibero-doc doctor
```

자주 확인할 항목:

- API 서버를 실행한 터미널이 열려 있는지
- 일반 사용자가 DB 주소 대신 서비스 API 주소를 입력했는지
- 관리자 설정의 OpenProxy 호스트와 포트가 올바른지
- 문서 조회 권한이 사용자 또는 소속 그룹에 부여되었는지
- 비동기 모드라면 Worker와 RabbitMQ가 실행 중인지

## 개발자 문서

서비스 내부 구조와 개발 방법은 README에서 분리했습니다.

- [개발 및 아키텍처 가이드](docs/development-guide.md)
- [전체 코드 리뷰 가이드](docs/code-review-guide.md)
- [비정형 데이터 수명주기](docs/unstructured-data-lifecycle.md)
