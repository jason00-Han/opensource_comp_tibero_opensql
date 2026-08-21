# Tibero Doc 데이터 플랫폼 운영 가이드

이 문서는 Queue 모드로 Tibero Doc을 실행하고, 대시보드에서 상태를 확인하며, 장애를 진단·복구하는 절차를 설명합니다.

## 목차

1. [구성요소와 책임](#1-구성요소와-책임)
2. [최초 실행](#2-최초-실행)
3. [일상 시작과 종료](#3-일상-시작과-종료)
4. [Dashboard와 관측성](#4-dashboard와-관측성)
5. [RabbitMQ Retry와 DLQ](#5-rabbitmq-retry와-dlq)
6. [Transactional Outbox](#6-transactional-outbox)
7. [Airflow 재색인](#7-airflow-재색인)
8. [MinIO Hot/Warm/Cold](#8-minio-hotwarmcold)
9. [검색 품질과 부하 테스트](#9-검색-품질과-부하-테스트)
10. [Failover 검증](#10-failover-검증)
11. [장애 대응표](#11-장애-대응표)

## 1. 구성요소와 책임

| 시스템 | 책임 | 장애 시 영향 |
|---|---|---|
| OpenSQL/OpenProxy | 문서, ACL, 벡터, Job, Outbox 영구 저장 | 쓰기·검색 불가, HA 환경은 자동 전환 |
| RabbitMQ | Ingest·Embedding·Sync 작업 전달 | 새 작업 대기, 메시지는 durable queue에 보존 |
| Redis | Cache, Rate Limit, Worker heartbeat | Cache miss 증가, Worker 상태 표시 중단 |
| MinIO/S3 | 원본 문서 바이너리 | 신규 업로드와 원본 다운로드 불가 |
| Ollama | `bge-m3` 임베딩 | Embedding 작업 재시도 또는 DLQ 이동 |
| Prometheus | 수치 메트릭 | Dashboard RPS·p95 미표시, 업무 처리에는 영향 없음 |
| Loki | 구조화 로그 | 통합 로그 미표시, API·Worker는 계속 동작 |
| Patroni/etcd | OpenSQL 리더 선출 | HA 상태 확인과 자동 Failover에 영향 |

## 2. 최초 실행

### 2.1 인프라

```powershell
docker compose up -d redis rabbitmq loki prometheus grafana
docker compose --profile ai up -d ollama
docker compose exec ollama ollama pull bge-m3
```

### 2.2 설정과 스키마

```powershell
tibero-doc setup
tibero-doc migrate
tibero-doc doctor
```

`migrate`는 `C:\Users\<사용자>\.tibero-doc\config.toml`과 운영체제 자격 증명 저장소를 사용합니다. 적용된 SQL 파일명과 checksum은 `schema_migrations`에 기록합니다.

### 2.3 핵심 환경변수

| 변수 | 개발 기본값 | 설명 |
|---|---|---|
| `PIPELINE_MODE` | `queue` | `inline` 또는 RabbitMQ `queue` |
| `RABBITMQ_URL` | `amqp://guest:guest@127.0.0.1:5672/%2F` | 작업 메시지 연결 |
| `RABBITMQ_MANAGEMENT_URL` | `http://127.0.0.1:15672` | Dashboard Queue 조회 |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` | Cache와 Worker heartbeat |
| `PROMETHEUS_URL` | `http://127.0.0.1:9090` | Dashboard 시계열 조회 |
| `LOKI_URL` | `http://127.0.0.1:3100` | 로그 전송·조회 |
| `PATRONI_API_URLS` | 비어 있음 | 쉼표로 구분한 Patroni REST 주소 |
| `EMBEDDING_API_URL` | `http://127.0.0.1:11434/v1` | Ollama OpenAI-compatible API |
| `EMBEDDING_MODEL` | `bge-m3` | 실제 의미 검색 모델 |

비밀번호와 실제 DSN은 `.env.example`에 기록하지 않습니다.

## 3. 일상 시작과 종료

### 안전한 시작 순서

```powershell
docker compose up -d redis rabbitmq loki prometheus grafana
docker compose --profile ai up -d ollama
tibero-doc migrate
tibero-doc serve
```

별도 터미널 4개:

```powershell
tibero-doc worker serve ingest
tibero-doc worker serve embedding
tibero-doc worker serve sync
tibero-doc worker serve outbox
```

### 상태 확인

```powershell
tibero-doc doctor
tibero-doc status
tibero-doc worker status
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/health/ready
```

### 안전한 종료

API·Worker 터미널에서 먼저 `Ctrl+C`를 누른 뒤 인프라를 멈춥니다.

```powershell
docker compose stop
```

`stop`은 Docker volume을 보존합니다. 데이터 초기화 목적이 아니라면 `docker compose down -v`를 사용하지 마세요.

### 8000 포트가 남았을 때

```powershell
$listener = Get-NetTCPConnection -LocalPort 8000 -State Listen
Get-Process -Id $listener.OwningProcess
Stop-Process -Id $listener.OwningProcess
tibero-doc serve
```

프로젝트와 무관한 프로세스인지 확인한 뒤 종료합니다.

## 4. Dashboard와 관측성

통합 대시보드: <http://127.0.0.1:8000>

Manager 이상 사용자만 운영 집계를 조회할 수 있습니다. 브라우저는 RabbitMQ·Redis·Prometheus·Loki·Patroni 비밀번호를 받지 않고 Dashboard API가 서버 측에서 상태를 통합합니다.

### Worker heartbeat

Worker는 Redis에 다음 키를 10초마다 갱신하고 기본 30초 TTL을 적용합니다.

```text
tibero-doc:worker:ingest-<host>-<pid>
tibero-doc:worker:embedding-<host>-<pid>
tibero-doc:worker:sync-<host>-<pid>
tibero-doc:worker:outbox-<host>-<pid>
```

확인:

```powershell
docker compose exec redis redis-cli --scan --pattern "tibero-doc:worker:*"
```

Worker 프로세스 하나가 CLI launcher와 Python child 두 개로 보이는 것은 정상입니다. Redis heartbeat는 실제 Worker당 하나만 존재해야 합니다.

### Prometheus

- API endpoint: `GET /metrics`
- API RPS: `sum(rate(tibero_doc_http_requests_total[5m]))`
- API p95: `histogram_quantile(0.95, sum(rate(tibero_doc_http_request_duration_seconds_bucket[5m])) by (le))`
- Worker 처리율: `sum(rate(tibero_doc_worker_jobs_total[5m]))`

### Loki

API와 Worker는 구조화 JSON 로그를 비동기 전송합니다. Loki 장애가 업무 처리를 막지 않도록 전송 오류는 애플리케이션 오류로 전파하지 않습니다. `httpx/httpcore` 내부 로그는 재귀 전송 방지를 위해 제외합니다.

## 5. RabbitMQ Retry와 DLQ

각 작업 유형은 세 종류의 durable queue를 사용합니다.

```text
tibero-doc.ingest
tibero-doc.ingest.retry
tibero-doc.ingest.dlq
```

Embedding과 Sync도 같은 규칙입니다. 실패 메시지는 `x-retry-count`를 증가시켜 Retry Queue로 보내고 TTL 이후 원래 Queue로 복귀합니다. 기본 3회 실패하면 DLQ로 이동합니다.

```powershell
$env:RABBITMQ_MAX_RETRIES="3"
$env:RABBITMQ_RETRY_DELAY_MS="5000"
```

RabbitMQ UI: <http://127.0.0.1:15672>

DLQ 메시지는 원인과 현재 문서 상태를 확인한 뒤 재발행해야 합니다. 원인을 해결하지 않고 반복 재발행하지 마세요.

## 6. Transactional Outbox

API가 Queue 작업을 만들 때 `pipeline_jobs`와 `pipeline.job.created` Outbox event를 같은 OpenSQL transaction에 기록합니다. Outbox Worker가 다음 순서로 발행합니다.

1. `FOR UPDATE SKIP LOCKED`로 미발행 event claim
2. RabbitMQ persistent message 발행
3. 성공 시 `published_at` 기록
4. 실패 시 `attempts`, `last_error` 기록
5. 비정상 종료 후 5분이 지난 lock은 다른 Publisher가 회수

```powershell
tibero-doc migrate
tibero-doc worker serve outbox
```

`column locked_at does not exist`는 코드보다 DB 스키마가 오래됐다는 뜻이며 `tibero-doc migrate`로 해결합니다.

## 7. Airflow 재색인

`tibero_doc_maintenance` DAG는 매일 02:00에 Embedding 재색인을 Queue에 넣고 MinIO 수명주기 API를 실행합니다.

```powershell
$env:TIBERO_DOC_MAINTENANCE_TOKEN="<manager-token>"
docker compose -f infra/docker-compose.production.yml --profile batch up -d airflow
```

Airflow UI: <http://127.0.0.1:8080>

## 8. MinIO Hot/Warm/Cold

| Tier | 기본 조건 | 동작 |
|---|---|---|
| Hot | 신규·최근 접근 | 즉시 검색·다운로드 |
| Warm | 30일 미접근 | Warm Bucket으로 검증 후 이동 |
| Cold | 90일 미접근 | Cold Bucket으로 검증 후 이동 |

```powershell
$env:LIFECYCLE_WARM_DAYS="30"
$env:LIFECYCLE_COLD_DAYS="90"
python scripts\lifecycle_move.py
```

이동은 대상 Bucket에 복사하고 `HEAD` 검증에 성공한 뒤 원본을 삭제합니다. 같은 MinIO 디스크의 Bucket 분리는 논리적 계층이며 실제 비용 차등은 별도 Tenant 또는 S3 Storage Class가 필요합니다.

## 9. 검색 품질과 부하 테스트

### 검색 품질

`evaluation/search_gold.jsonl`의 placeholder를 실제 정답 document ID로 교체합니다.

```powershell
python evaluation\evaluate_search.py --token <ACCESS_TOKEN> -k 5
```

- Recall@K: 정답 문서 회수율
- MRR: 첫 정답 문서 순위
- nDCG@K: 여러 정답의 전체 순위 품질

### 부하 테스트

```powershell
python -m pip install locust
$env:TIBERO_DOC_LOAD_TOKEN="<ACCESS_TOKEN>"
locust -f loadtests\locustfile.py --host http://127.0.0.1:8000 --headless -u 100 -r 10 -t 10m --csv loadtests\results
```

환경별 RPS, p50/p95/p99와 오류율을 기록하고, 실제 측정 전에는 성능 수치를 결과보고서에 확정값으로 적지 않습니다.

## 10. Failover 검증

개발용 HA Cluster에서만 실행합니다.

```powershell
.\infra\scripts\failover-pipeline-test.ps1 -Token <ACCESS_TOKEN>
```

테스트는 Failover 직전 문서를 Queue에 넣고 현재 Primary를 중지한 뒤 동일 Job이 제한 시간 안에 `completed`가 되는지 확인합니다. OpenSQL 라이선스 이미지와 Patroni 3노드 환경이 필요합니다.

## 11. 장애 대응표

| 증상 | 원인 | 조치 |
|---|---|---|
| Dashboard 상단 `Not Found` | 오래된 API가 8000 포트를 점유 | PID 확인 후 현재 가상환경에서 API 재시작 |
| Dashboard가 빈 Skeleton | Dashboard API 404/401/500 | 브라우저 Network보다 먼저 `/docs`에서 endpoint 존재 확인 |
| Worker `0 ONLINE` | Redis 미설정 또는 옛 Worker | `REDIS_URL` 설정 후 Worker 재시작, 30초 대기 |
| Worker가 여러 개 표시 | 중복 실행 | Redis heartbeat key와 실제 command line 확인 후 중복 종료 |
| `WinError 10048` | 8000 포트 중복 | 기존 API 프로세스 종료 |
| `locked_at` 컬럼 오류 | Migration 미적용 | `tibero-doc migrate` |
| RabbitMQ Queue 404 | Worker가 아직 Queue를 선언하지 않음 | 해당 Worker 1회 시작 |
| Embedding 계속 실패 | Ollama 또는 모델 미준비 | `docker compose exec ollama ollama pull bge-m3` |
| 검색 결과 없음 | 임베딩 모델 변경 후 재색인 누락 | `tibero-doc embedding-reindex` |
| 로그인 만료 | Access/Refresh Token 만료 | 자동 갱신 실패 시 다시 로그인 |

## CI

`.github/workflows/data-integration.yml`은 unit/API 테스트와 RabbitMQ·MinIO·pgvector 통합 테스트를 분리합니다. 실제 OpenSQL/Patroni Failover는 전용 self-hosted runner에서 `RUN_FAILOVER_TESTS=1`로 실행하는 것을 권장합니다.
