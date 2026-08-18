# Tibero Doc — OpenSQL AI 문서 플랫폼

문서를 업로드하면 내용을 추출·청킹·임베딩하고 OpenSQL에 저장한 뒤, 키워드와 벡터를 결합해 검색하는 CLI 중심 오픈소스 프로젝트입니다. OpenProxy를 단일 DB 진입점으로 사용하고 Patroni/etcd가 Primary 상태를 관리합니다.

## 구현 기능

- PDF, DOCX, TXT, HTML 업로드와 본문 추출
- 중첩 청크 생성 및 메타데이터 저장
- 동일 파일명 변경 시 버전 증가와 이력 보존
- API 키가 필요 없는 384차원 로컬 임베딩
- Ollama/OpenAI-compatible 임베딩 교체 지원
- PostgreSQL FTS + pgvector RRF 하이브리드 검색
- 업로드 디렉터리 변경 감지 및 증분 동기화
- OpenSQL 기반 작업 상태 저장과 변경 이벤트(outbox)
- 문서 목록·본문·버전 조회 및 삭제
- REST API, CLI, MCP(stdio/Streamable HTTP)
- 즉시 처리(`inline`)와 RabbitMQ 워커(`queue`) 실행 방식
- 사용자·조직·워크스페이스 기반 다중 사용자 격리
- Bearer API 토큰과 Viewer/Editor/Manager/Owner 역할 권한
- 일회용 초대 토큰 가입과 감사 로그

## 3분 빠른 시작

설치 후 환경 변수를 직접 만들 필요가 없습니다.

```powershell
cd C:\Users\한경민\Desktop\opensource_comp_tibero_opensql
.\.venv\Scripts\Activate.ps1
python -m pip install -e services\api -e cli

tibero-doc setup
tibero-doc serve
```

`setup` 마법사는 OpenProxy 주소와 DB 계정을 질문하고 실제 연결까지 검사합니다. 비밀번호는 `config.toml`에 기록하지 않으며, 동의한 경우 Windows 자격 증명 관리자 등 운영체제 보안 저장소에 보관합니다. 비밀번호의 `@`, `#`, `%`, `^` 같은 문자도 자동으로 URL 인코딩합니다.

마법사는 최초 관리자, 조직, 기본 워크스페이스도 만들고 사용자 접근 토큰을 운영체제 자격 증명 저장소에 보관합니다. 일반 사용자는 DB 정보를 입력하지 않고 관리자가 전달한 초대 토큰으로 가입합니다.

서버를 켜둔 상태에서 새 터미널을 열어 사용합니다.

```powershell
tibero-doc status
tibero-doc ingest .\documents
tibero-doc search "장애 복구 절차"
tibero-doc list
```

다른 사용자 초대:

```powershell
# Manager 또는 Owner
tibero-doc invite user@example.com --role editor

# 초대받은 사용자: DB 주소나 비밀번호 불필요
tibero-doc join INVITE_TOKEN --email user@example.com --name "홍길동" --server http://docs-server:8000
tibero-doc whoami
```

일반 사용자는 HTTPS API에만 접근합니다. OpenProxy와 OpenSQL 접속 정보는 서버 관리자만 보유하며, 문서 목록·조회·검색·삭제는 현재 토큰의 `workspace_id` 조건으로 격리됩니다.

문제가 생기면 다음 명령이 설정, OpenProxy 포트, DB 로그인, API를 한 번에 검사하고 해결 명령을 안내합니다.

```powershell
tibero-doc doctor
```

설정 관리:

```powershell
tibero-doc config show
tibero-doc config path
tibero-doc config reset
```

## 1. OpenSQL 확인

현재 컨테이너 기준:

```bash
docker exec opensql-test /home/opensql/bin/patronictl \
  -c /home/opensql/etc/patroni/patroni.yml list
```

`Leader | running`이어야 합니다. 컨테이너 내부 직접 연결은 5432, OpenProxy는 6432이며 호스트에서는 각각 15432, 16432입니다.

```bash
psql -h 127.0.0.1 -p 6432 -U postgres -d opensql -W
```

## 2. WSL 가상환경과 설치

```bash
cd /mnt/c/Users/한경민/Desktop/opensource_comp_tibero_opensql

sudo apt update
sudo apt install -y python3.12-venv
python3 -m venv .venv-wsl
source .venv-wsl/bin/activate

python -m pip install -U pip
python -m pip install -e 'services/api[test]'
python -m pip install -e cli
```

## 3. OpenSQL 스키마 적용

호스트에서 OpenProxy로 적용합니다. 비밀번호에 특수문자가 있다면 DSN에서는 URL 인코딩해야 합니다.

```bash
export PGPASSWORD='실제-postgres-비밀번호'
psql -h 127.0.0.1 -p 16432 -U postgres -d opensql \
  -v ON_ERROR_STOP=1 -f infra/opensql/init.sql
```

스키마에는 `documents`, `document_versions`, `chunks`, `chunk_embeddings`, `pipeline_jobs`, `outbox_events`가 생성됩니다.

## 4. 가장 간단한 실행 — RabbitMQ 불필요

```bash
source .venv-wsl/bin/activate

export TIBERO_DOC_DSN='postgresql://postgres:URL인코딩된-비밀번호@127.0.0.1:16432/opensql'
export TIBERO_DOC_DATA_DIR="$PWD/.data"
export PIPELINE_MODE=inline
export EMBEDDING_PROVIDER=local
export EMBEDDING_MODEL=local-hash-384

uvicorn services.api.main:app --reload --host 127.0.0.1 --port 8000
```

API 문서는 <http://127.0.0.1:8000/docs>에서 볼 수 있습니다.

다른 WSL 터미널에서 CLI를 사용합니다.

```bash
source .venv-wsl/bin/activate
tibero-doc init --api-url http://127.0.0.1:8000
tibero-doc status
tibero-doc ingest ./tests/fixtures/sample.txt
tibero-doc list
tibero-doc search '문서 검색' --top-k 5
tibero-doc show DOCUMENT_ID
tibero-doc versions DOCUMENT_ID
tibero-doc job JOB_ID
tibero-doc sync
tibero-doc delete DOCUMENT_ID
```

## 5. 운영형 비동기 실행 — RabbitMQ

```bash
docker compose up -d rabbitmq
export PIPELINE_MODE=queue
export RABBITMQ_URL='amqp://guest:guest@127.0.0.1:5672/%2F'
```

API와 워커를 각각 별도 터미널에서 같은 환경 변수로 실행합니다.

```bash
uvicorn services.api.main:app --host 127.0.0.1 --port 8000
python -m workers.ingest.main
python -m workers.embedding.main
python -m workers.sync.main
```

Ingest 워커가 문서를 색인하고 embedding 작업을 발행합니다. Sync 워커도 변경 문서마다 embedding 작업을 발행합니다. 작업 상태는 OpenSQL의 `pipeline_jobs`에 저장되므로 프로세스가 달라도 공유됩니다.

## 6. 실제 임베딩 모델 사용

로컬 해시 임베딩은 API 키 없이 전체 흐름을 재현하기 위한 기본 구현입니다. 높은 검색 품질이 필요하면 Ollama 또는 OpenAI-compatible endpoint를 사용합니다.

```bash
export EMBEDDING_PROVIDER=ollama
export EMBEDDING_API_URL=http://127.0.0.1:11434/v1
export EMBEDDING_MODEL=nomic-embed-text
export EMBEDDING_API_KEY=''
```

외부 유료 API라면 다음 값만 추가합니다.

```bash
export EMBEDDING_PROVIDER=openai
export EMBEDDING_API_URL=https://서비스주소/v1
export EMBEDDING_MODEL=모델명
export EMBEDDING_API_KEY=발급받은키
```

모델을 변경한 뒤 기존 문서도 새 모델로 검색하려면 다시 업로드하거나 embedding 작업을 재실행해야 합니다.

## 7. MCP 서버

로컬 stdio MCP는 API 키가 필요 없습니다.

```bash
export TIBERO_DOC_DSN='postgresql://postgres:URL인코딩된-비밀번호@127.0.0.1:16432/opensql'
export EMBEDDING_PROVIDER=local
python -m services.mcp_server.main
```

제공 도구:

- `search_documents`
- `list_documents`
- `get_document`
- `get_job_status`
- `get_document_stats`

Streamable HTTP는 로컬 주소에만 바인딩해서 사용합니다.

```bash
MCP_TRANSPORT=streamable-http MCP_HOST=127.0.0.1 MCP_PORT=8001 \
  python -m services.mcp_server.main
```

현재 MCP HTTP 자체 인증은 포함하지 않았습니다. 인터넷이나 사내망에 공개할 때는 API Gateway/Nginx에서 TLS와 API 키 또는 OAuth 인증을 적용해야 합니다. 임베딩 API 키와 MCP 접근 인증은 서로 다른 개념입니다.

## 8. 테스트

```bash
pytest tests/unit services/api/tests -q

export TIBERO_DOC_DSN='postgresql://postgres:URL인코딩된-비밀번호@127.0.0.1:16432/opensql'
export OPENPROXY_TEST_DSN="$TIBERO_DOC_DSN"
pytest tests/integration/database/test_opensql_platform.py -q
```

## 처리 흐름

```text
CLI / MCP / REST
        |
        v
     API Service
        |
        +-- upload -> extract -> chunk -> metadata/version
        +-- embed  -> pgvector
        +-- search -> FTS + vector -> RRF merge
        |
        v
OpenProxy :16432 -> OpenSQL Primary
                   documents / versions / chunks
                   embeddings / jobs / outbox
                   Patroni <-> etcd
```

## 다중 사용자 운영 기능

- Argon2 비밀번호 로그인: `POST /v1/auth/login`
- 15분 Access Token과 30일 회전형 Refresh Token: `POST /v1/auth/refresh`
- 조직·워크스페이스 격리와 Viewer/Editor/Manager/Owner RBAC
- 사용자·그룹 단위 문서 ACL
- SMTP 일회용 초대 메일
- 감사 로그 API와 `tibero-doc audit`
- MinIO/S3 AES256 원본 저장과 Presigned Download
- Redis 분산 Rate Limit과 Nginx IP Rate Limit
- `/ui/` 사용자 웹 화면

```powershell
tibero-doc login --email admin@example.com
tibero-doc refresh
tibero-doc invite user@example.com --role editor
tibero-doc audit --limit 100
```

웹 UI는 서버 실행 후 <http://localhost:8000/ui/>에서 사용합니다.

## MinIO·Redis·다중 API·Nginx TLS 배포

`infra/docker-compose.production.yml`은 API 3개, Worker 3종, RabbitMQ, Redis, MinIO, Nginx를 구성합니다.

```powershell
$env:TIBERO_DOC_DSN='postgresql://...'
$env:MINIO_ROOT_USER='tiberodoc'
$env:MINIO_ROOT_PASSWORD='충분히-긴-비밀번호'
$env:PUBLIC_API_URL='https://localhost'

.\infra\scripts\generate-dev-cert.ps1
docker compose -f infra\docker-compose.production.yml up -d --build --scale api=3
```

운영 환경에서는 자체 서명 인증서 대신 공인 CA 또는 사내 CA 인증서를 다음 이름으로 배치합니다.

```text
infra/nginx/certs/fullchain.pem
infra/nginx/certs/privkey.pem
```

SMTP 환경 변수:

```text
SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM, SMTP_TLS
```

## OpenSQL 3노드 Failover 시연

이 구성은 노드별 라이선스 사용 권한과 OpenSQL 이미지가 필요합니다.

```powershell
$env:OPENSQL_BASE_IMAGE='opensql-build-v3:latest'
$env:OPENSQL_LICENSE_FILE='C:\secure\license.xml'
$env:OPENSQL_POSTGRES_PASSWORD='...'
$env:OPENSQL_REPLICATION_PASSWORD='...'
$env:OPENSQL_REWIND_PASSWORD='...'

docker compose -f infra\docker-compose.ha.yml up -d --build
.\infra\scripts\failover-demo.ps1
```

구성은 etcd 3개, Patroni/OpenSQL 3개와 Patroni `/primary` 상태를 검사하는 DB Router로 이루어집니다. 시연 스크립트는 현재 Leader를 찾아 중지하고 45초 내 새 Leader 선출 여부를 검증합니다.
