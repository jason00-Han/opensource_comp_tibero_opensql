# Tibero Doc 개발 및 아키텍처 가이드

이 문서는 Tibero Doc을 수정하거나 배포하는 개발자를 위한 문서다. 최종 사용자를 위한 명령어 설명은 프로젝트 루트의 `README.md`를 참고한다.

## 시스템 구성

```text
Web UI / CLI / MCP / REST Client
                |
                v
          FastAPI Service
                |
       +--------+---------+
       |        |         |
    Ingest    Search    Auth/ACL
       |        |         |
       +--------+---------+
                |
           OpenProxy
                |
        OpenSQL Primary
                |
        Patroni <-> etcd
```

운영 구성에서는 MinIO/S3가 원본 문서를 저장하고, Redis가 Rate Limit과 인기 문서 캐시를 공유한다. RabbitMQ는 API와 Ingest·Embedding·Sync Worker 사이에서 작업을 전달한다. Nginx는 TLS 종료와 여러 API 인스턴스의 로드 밸런싱을 담당한다.

## 문서 처리 흐름

1. API 또는 CLI가 업로드 요청을 받는다.
2. PDF, DOCX, TXT, HTML에서 텍스트를 추출한다.
3. 텍스트를 중첩 청크로 나누고 문서 메타데이터와 버전을 기록한다.
4. 임베딩을 생성해 `pgvector` 컬럼에 저장한다.
5. 청크에서 엔티티와 관계를 추출해 지식 그래프 테이블에 저장한다.
6. 변경 이벤트와 작업 상태를 OpenSQL에 기록한다.

`PIPELINE_MODE=inline`이면 API 프로세스가 즉시 처리한다. `PIPELINE_MODE=queue`이면 RabbitMQ에 작업을 발행하고 Worker가 처리한다.

## OpenSQL 데이터 모델

핵심 테이블:

- `documents`: 현재 문서 메타데이터
- `document_versions`: 문서 버전 이력
- `chunks`: 검색과 인용의 최소 단위
- `chunk_embeddings`: 모델별 청크 임베딩
- `pipeline_jobs`: 비동기 작업 상태
- `outbox_events`: 변경 이벤트
- `entities`: 인물·조직·시스템·정책·프로젝트·주제
- `document_entities`: 문서/청크와 엔티티 연결
- `relationships`: 엔티티 관계와 근거 문서/청크

전체 DDL은 `infra/opensql/init.sql`에 있다.

## 검색 구조

검색은 세 순위를 독립적으로 계산한다.

1. OpenSQL Full Text Search 키워드 순위
2. pgvector 거리 기반 의미 유사도 순위
3. 엔티티 직접 일치 및 1-hop 관계 탐색 순위

`hybrid` 모드는 RRF(Reciprocal Rank Fusion)로 순위를 합친다. 서로 다른 검색 방식의 원점수를 직접 정규화하지 않고 각 결과의 순위를 이용하므로 구현과 튜닝이 단순하다. 결과에는 `keyword_rank`, `vector_rank`, `graph_rank`, `entities`가 포함된다.

검색 SQL과 RRF 구현은 `services/api/store.py`, 그래프 추출과 색인은 `packages/core/knowledge_graph.py`에 있다.

## 지식 그래프 색인

기본 `RuleBasedEntityExtractor`는 외부 API 없이 동작한다.

- 엔티티 유형: `person`, `organization`, `system`, `policy`, `project`, `topic`
- 관계 유형: `uses`, `references`, `belongs_to`, `manages`, `supersedes`, `co_occurs_with`
- 모든 관계에 `document_id`와 `chunk_index`를 저장해 답변 근거를 추적한다.
- 청크당 엔티티는 기본 20개로 제한해 관계 조합 폭증을 방지한다.

`EntityExtractor` 프로토콜을 구현하면 Ollama 또는 OpenAI-compatible 구조화 추출기로 교체할 수 있다.

## 임베딩과 답변 모델

기본 임베딩은 `local-hash-384`이며 API 키가 필요 없다. 실제 모델은 환경 변수로 교체한다.

```bash
export EMBEDDING_PROVIDER=ollama
export EMBEDDING_API_URL=http://127.0.0.1:11434/v1
export EMBEDDING_MODEL=nomic-embed-text
```

OpenAI-compatible 서비스:

```bash
export EMBEDDING_PROVIDER=openai
export EMBEDDING_API_URL=https://provider.example/v1
export EMBEDDING_MODEL=model-name
export EMBEDDING_API_KEY=secret
```

생성형 답변도 `AGENT_PROVIDER`, `AGENT_MODEL`, `OPENAI_API_KEY`로 설정한다. 모델을 바꾸면 기존 문서 임베딩을 다시 생성해야 한다.

## 인증과 권한

- Argon2 비밀번호 해시
- 짧은 수명의 Access Token과 회전형 Refresh Token
- 조직·워크스페이스 격리
- Viewer/Editor/Manager/Owner RBAC
- 사용자·그룹 단위 문서 ACL
- 일회용 초대 토큰
- 감사 로그

캐시는 권한 계층으로 사용하지 않는다. 문서 캐시를 확인하기 전에 매 요청 OpenSQL ACL을 검사하며, ACL 변경 또는 문서 삭제 시 캐시를 무효화한다. REST와 MCP 모두 동일한 ACL 검사를 적용한다.

## 캐시와 Rate Limit

`REDIS_URL`이 있으면 여러 API 인스턴스가 Rate Limit과 인기 문서 캐시를 공유한다. Redis가 없으면 단일 프로세스 메모리 구현으로 대체된다.

- `RATE_LIMIT_PER_MINUTE`: 사용자/IP별 분당 요청 수
- `DOCUMENT_CACHE_THRESHOLD`: 캐시를 시작할 조회 횟수
- `DOCUMENT_CACHE_TTL_SECONDS`: 캐시 유지 시간

## 개발 환경 실행

### 스키마 적용

```bash
export PGPASSWORD='database-password'
psql -h 127.0.0.1 -p 16432 -U postgres -d opensql \
  -v ON_ERROR_STOP=1 -f infra/opensql/init.sql
```

### API 직접 실행

```bash
export TIBERO_DOC_DSN='postgresql://postgres:encoded-password@127.0.0.1:16432/opensql'
export PIPELINE_MODE=inline
export EMBEDDING_PROVIDER=local
uvicorn services.api.main:app --reload --host 127.0.0.1 --port 8000
```

### 비동기 Worker 실행

```bash
export PIPELINE_MODE=queue
export RABBITMQ_URL='amqp://guest:guest@127.0.0.1:5672/%2F'

python -m workers.ingest.main
python -m workers.embedding.main
python -m workers.sync.main
```

## 운영 배포

`infra/docker-compose.production.yml`은 RabbitMQ, Redis, MinIO, Nginx, API와 Worker를 구성한다.

```powershell
$env:TIBERO_DOC_DSN='postgresql://...'
$env:MINIO_ROOT_USER='tiberodoc'
$env:MINIO_ROOT_PASSWORD='long-password'
$env:PUBLIC_API_URL='https://localhost'

.\infra\scripts\generate-dev-cert.ps1
docker compose -f infra\docker-compose.production.yml up -d --build --scale api=3
```

운영 환경에서는 자체 서명 인증서 대신 공인 또는 사내 CA 인증서를 사용한다. SMTP 초대 메일에는 `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TLS`가 필요하다.

## OpenSQL 다중 노드

HA 예제는 etcd 3개, Patroni/OpenSQL 3개와 Primary 상태 기반 DB Router로 구성된다.

```powershell
$env:OPENSQL_BASE_IMAGE='opensql-build-v3:latest'
$env:OPENSQL_LICENSE_FILE='C:\secure\license.xml'
$env:OPENSQL_POSTGRES_PASSWORD='...'
$env:OPENSQL_REPLICATION_PASSWORD='...'
$env:OPENSQL_REWIND_PASSWORD='...'

docker compose -f infra\docker-compose.ha.yml up -d --build
.\infra\scripts\failover-demo.ps1
```

OpenSQL 노드별 라이선스와 이미지가 필요하다.

## 테스트

단위 테스트:

```bash
pytest tests/unit services/api/tests -q
```

실제 OpenSQL 통합 테스트:

```bash
export TIBERO_DOC_DSN='postgresql://postgres:encoded-password@127.0.0.1:16432/opensql'
export OPENPROXY_TEST_DSN="$TIBERO_DOC_DSN"
pytest tests/integration/database/test_opensql_platform.py -q
```

다중 사용자 격리, ACL, 그래프 검색, 문서 버전, 임베딩과 작업 상태를 통합 테스트에서 검증한다.

## 추가 문서

- `docs/code-review-guide.md`: 모듈, 클래스, 함수와 예외 처리 설명
- `docs/unstructured-data-lifecycle.md`: Hot/Warm/Cold/삭제 승인 전략
