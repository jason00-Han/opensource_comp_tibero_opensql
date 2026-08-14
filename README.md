  # OpenSQL AI Document Platform

OpenSQL 기반에서 문서 업로드, 자동 파싱·청킹, 임베딩 생성, 벡터 검색, 동기화, MCP 연동까지 하나의 흐름으로 제공하는 오픈소스 AI 문서 데이터 플랫폼입니다.

현재 PoC는 단일 OpenSQL 노드를 기준으로 개발하고 있으며, 애플리케이션 계층은 OpenProxy를 단일 DB 진입점으로 사용하도록 설계하여 향후 다중 노드 HA 환경으로 확장할 수 있도록 구성합니다.

---

## 주요 기능

- 문서 업로드 및 자동 처리
- PDF / DOCX / TXT / HTML 파싱
- 문서 Chunk 자동 생성
- 임베딩 자동 생성
- pgvector / pgvectorscale 기반 벡터 검색
- PostgreSQL Full Text Search 기반 키워드 검색
- Hybrid Search
- 문서 변경 감지 및 동기화
- MCP 기반 AI Agent 검색
- CLI 기반 관리
- OpenProxy를 통한 OpenSQL 연결
- Patroni 기반 DB 프로세스 복구
- Worker 수평 확장
- SBOM 생성 및 공급망 정보 관리

---

## Architecture

```text
                         User
               ┌────────┴────────┐
                 │                 │
                CLI             MCP Client
                 │                 │
                 ▼                 ▼
          ┌─────────────┐   ┌─────────────┐
          │ API Service │   │ MCP Server  │
          └──────┬──────┘   └──────┬──────┘
                 │                 │
                 └────────┬────────┘
                          │
                   Document Pipeline
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
      Ingest Worker   Embedding Worker   Sync Worker
          │               │               │
          └───────────────┼───────────────┘
                          │
                          ▼
                   Shared Packages
                Database / Search /
               Embedding / Storage
                          │
                          ▼
                     OpenProxy
                       :6432
                          │
                          ▼
                       OpenSQL
          ┌────────────────────────────┐
          │ PostgreSQL 17.8            │
          │ pgvector 0.8.1             │
          │ pgvectorscale 0.9.0        │
          │ Patroni                    │
          │ etcd                       │
          └────────────────────────────┘

          S

## Local CLI MVP

Python 3.11 이상에서 API와 CLI를 함께 설치합니다.

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -e 'services/api[test]'
python -m pip install -e cli
```

RabbitMQ를 시작합니다. 관리 UI는 `http://localhost:15672`이며 로컬 기본 계정은
`guest` / `guest`입니다.

```bash
docker compose up -d rabbitmq
```

터미널 하나에서 API 서버를 실행합니다.

```bash
uvicorn services.api.main:app --reload
```

각각 다른 터미널에서 ingest worker와 sync worker를 실행합니다. API와 worker는 같은
`TIBERO_DOC_DATA_DIR` 경로를 사용해야 합니다.

```bash
source .venv/bin/activate
export RABBITMQ_URL=amqp://guest:guest@localhost:5672/%2F
python -m workers.ingest.main
```

```bash
source .venv/bin/activate
export RABBITMQ_URL=amqp://guest:guest@localhost:5672/%2F
python -m workers.sync.main
```

OpenAI-compatible embedding endpoint(Ollama의 `/v1` 호환 endpoint 포함)을 설정하고
embedding worker를 실행합니다.

```bash
export EMBEDDING_API_URL=http://127.0.0.1:11434/v1
export EMBEDDING_MODEL=nomic-embed-text
python -m workers.embedding.main
```

MCP Server는 로컬 client용 stdio가 기본값입니다. 원격 client에는 Streamable HTTP를
사용할 수 있습니다.

```bash
python -m services.mcp_server.main
MCP_TRANSPORT=streamable-http MCP_PORT=8001 python -m services.mcp_server.main
```

각 명령을 여러 프로세스나 컨테이너에서 실행하면 RabbitMQ가 ingest와 sync의
독립 durable queue에서 작업을 해당 Worker들에 분배합니다. 로컬 JSON 인덱스
갱신에는 프로세스 잠금을 적용하므로 단일 호스트의 여러 Worker가 안전하게 같은
데이터 경로를 공유할 수 있습니다. Ingest Worker가 청킹을 완료하면 embedding 작업을
발행하고 Embedding Worker가 벡터를 생성합니다. 로컬 기본 repository는
`embeddings.json`이며 배포 시 OpenSQL repository로 교체하는 경계가 분리돼 있습니다.

다른 터미널에서 CLI 전체 흐름을 실행합니다.

```bash
source .venv/bin/activate
tibero-doc init --api-url http://127.0.0.1:8000
tibero-doc status
tibero-doc ingest ./sample.txt
tibero-doc search "검색할 문장" --top-k 5
tibero-doc sync
```

업로드와 sync 요청은 `202 Accepted`와 `job_id`를 즉시 반환합니다. 문서 추출,
청킹, 인덱싱은 worker가 수행하며 `GET /v1/jobs/{job_id}`에서 `queued`, `running`,
`completed`, `failed` 상태와 결과를 확인할 수 있습니다. 키워드 검색은 계속
동기식입니다. 작업 상태는 데이터 디렉터리의 `jobs.json`에 원자적으로 저장됩니다.

작업 모델, 상태 전이, queue routing, RabbitMQ publisher는 API나 개별 Worker가 아닌
`packages/core/pipeline`에 있습니다. `JsonJobRepository`는 로컬 MVP 기본 구현이며,
동일한 `JobRepository` 계약으로 OpenSQL 기반 작업 저장소를 주입할 수 있습니다.

환경 변수는 `TIBERO_DOC_DATA_DIR`, `RABBITMQ_URL`, `RABBITMQ_INGEST_QUEUE`
(기본값 `tibero-doc.ingest`), `RABBITMQ_EMBEDDING_QUEUE` (기본값
`tibero-doc.embedding`), `RABBITMQ_SYNC_QUEUE` (기본값 `tibero-doc.sync`),
`WORKER_PREFETCH` (기본값 `1`)를 지원합니다. Embedding endpoint는
`EMBEDDING_API_URL`, `EMBEDDING_MODEL`, `EMBEDDING_API_KEY`로 설정합니다.


API 문서는 서버 실행 후 `http://127.0.0.1:8000/docs`에서 확인할 수 있습니다.
로컬 MVP의 원본 문서와 JSON 인덱스는 기본적으로 `~/.tibero-doc/data`에 저장됩니다.

테스트는 다음 명령으로 실행합니다.

```bash
python -m pytest services/api/tests -q
```