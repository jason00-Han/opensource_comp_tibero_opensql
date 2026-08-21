# Tibero Doc 데이터 플랫폼 운영 가이드

## RabbitMQ 재시도와 DLQ

각 작업은 정상 큐, TTL 지연 큐(`*.retry`), 최종 실패 큐(`*.dlq`)를 사용합니다. Worker 실패 시 `x-retry-count`를 증가시켜 retry 큐로 보내며, TTL 이후 원래 큐로 돌아옵니다. 기본 3회 실패하면 DLQ에 보관합니다. 새 persistent 메시지가 기록된 후 원본을 ACK하므로 실패 메시지가 유실되지 않습니다.

```powershell
$env:RABBITMQ_MAX_RETRIES="3"
$env:RABBITMQ_RETRY_DELAY_MS="5000"
python -m workers.ingest.main
```

큐와 메시지 헤더는 RabbitMQ UI(`http://localhost:15672`)에서 확인합니다.

## Transactional Outbox

OpenSQL에서 pipeline job과 `pipeline.job.created` outbox row를 같은 transaction에 저장합니다. `outbox-publisher`는 `FOR UPDATE SKIP LOCKED`로 이벤트를 claim하여 여러 인스턴스 사이의 중복 처리를 막습니다. 성공 시 `published_at`, 실패 시 `attempts/last_error`를 기록하며 5분 이상 남은 lock은 회수합니다.

```powershell
python scripts/migrate.py
tibero-doc worker serve outbox
```

## Prometheus와 Grafana

API middleware는 endpoint별 요청 수와 지연시간 histogram을 `/metrics`에 제공합니다. Prometheus는 15초마다 수집하고 Grafana dashboard는 상태 코드별 요청률과 p95 지연시간을 표시합니다.

```powershell
docker compose -f infra/docker-compose.production.yml up -d prometheus grafana
```

- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000`

## 통합 운영 대시보드

`http://localhost:8000/`은 `/ui/`로 이동해 통합 운영 화면을 엽니다. Manager 이상만 Dashboard API를 사용할 수 있으며 브라우저에는 인프라 비밀번호를 전달하지 않습니다.

| 데이터 | 담당 시스템 | 대시보드 표시 |
|---|---|---|
| 영구 업무 상태 | OpenSQL | 문서·사용자·그룹·Job·Outbox |
| 작업 전달 | RabbitMQ | Ready·Processing·Retry·DLQ·Consumer |
| 현재 생존 상태 | Redis | Worker heartbeat·현재 Job·누적 처리량 |
| 수치 시계열 | Prometheus | RPS·p95·Worker 처리율 |
| 구조화 로그 | Loki | API·Worker 오류와 최근 이벤트 |
| HA 노드 | Patroni API | Primary·Replica·Lag·Timeline |

```powershell
docker compose up -d redis rabbitmq loki prometheus grafana
$env:REDIS_URL="redis://127.0.0.1:6379/0"
$env:RABBITMQ_MANAGEMENT_URL="http://127.0.0.1:15672"
$env:PROMETHEUS_URL="http://127.0.0.1:9090"
$env:LOKI_URL="http://127.0.0.1:3100"
$env:PATRONI_API_URLS="http://127.0.0.1:8008,http://127.0.0.1:8009,http://127.0.0.1:8010"
tibero-doc serve
```

Worker는 10초마다 Redis TTL heartbeat를 갱신합니다. Worker 프로세스가 종료되면 기본 30초 후 키가 사라져 대시보드에서 Offline으로 판단합니다. 설정을 적용한 뒤 기존 Worker는 재시작해야 합니다.

## Airflow 재색인 배치

`tibero_doc_maintenance` DAG는 매일 02:00에 임베딩 재색인을 queue에 넣고 MinIO 수명주기 작업을 실행합니다.

```powershell
$env:TIBERO_DOC_MAINTENANCE_TOKEN="<manager-token>"
docker compose -f infra/docker-compose.production.yml --profile batch up -d airflow
```

Airflow UI는 `http://localhost:8080`, DAG 소스는 `infra/airflow/dags/tibero_doc_maintenance.py`입니다.

## 데이터 계보와 스키마 버전

ingest/embedding Worker는 `data_lineage_events`에 object URI, 문서 버전, 모델, job ID, 산출 정보를 남깁니다. ACL을 통과한 사용자는 `GET /v1/documents/{document_id}/lineage`로 조회합니다.

Migration runner는 파일명과 SHA-256 checksum을 `schema_migrations`에 저장합니다. 적용된 파일이 변경되면 중단합니다.

```powershell
python scripts/migrate.py
```

## 검색 품질 평가

`evaluation/search_gold.jsonl`의 placeholder를 실제 정답 document ID로 교체한 다음 실행합니다.

```powershell
python evaluation/evaluate_search.py --token <access-token> -k 5
```

결과는 `evaluation/results.json`에 저장됩니다. Recall@K는 정답 회수율, MRR은 첫 정답 순위, nDCG@K는 전체 정답의 순서 품질입니다. 임베딩 모델이나 chunk 전략을 바꾸기 전후에 같은 gold set을 사용해야 합니다.

## 대용량 부하 테스트

Locust는 검색 80%, health 20%의 트래픽을 만들고 검색이 2초를 넘으면 실패로 집계합니다.

```powershell
pip install locust
$env:TIBERO_DOC_LOAD_TOKEN="<access-token>"
locust -f loadtests/locustfile.py --host http://127.0.0.1:8000 --headless -u 100 -r 10 -t 10m --csv loadtests/results
```

CSV에서 RPS, p50/p95/p99, failure rate를 확인합니다.

## MinIO Hot/Warm/Cold 이동

새 원본은 hot bucket에 등록됩니다. 기본 30일 미접근 객체는 warm, 90일 미접근 객체는 cold bucket으로 물리 복사합니다. 대상 객체의 `HEAD` 검증 후에만 원본을 삭제하며, 다운로드는 hot → warm → cold 순서로 탐색합니다.

```powershell
$env:LIFECYCLE_WARM_DAYS="30"
$env:LIFECYCLE_COLD_DAYS="90"
python scripts/lifecycle_move.py
```

Airflow에서는 같은 작업을 `POST /v1/admin/storage/lifecycle/run` 관리자 API로 실행합니다.

같은 MinIO 디스크에서는 논리적 tier입니다. 실제 비용 계층화는 bucket을 별도 tenant 또는 S3 storage class에 연결해야 합니다.

## OpenSQL Failover 파이프라인 검증

테스트가 문서를 queue에 넣고 현재 Primary를 중지한 후 동일 job이 3분 안에 `completed`가 되는지 검사합니다.

```powershell
./infra/scripts/failover-pipeline-test.ps1 -Token <access-token>
```

Primary 컨테이너를 실제 중지하므로 개발용 HA cluster에서만 실행합니다.

## CI 데이터 통합 테스트

`.github/workflows/data-integration.yml`은 unit/API 테스트와 RabbitMQ·MinIO·pgvector 통합 테스트를 분리해 실행합니다. OpenSQL/Patroni의 destructive failover는 전용 self-hosted runner에서 `RUN_FAILOVER_TESTS=1`로 실행하는 것이 안전합니다.

## 운영 시작 순서

```powershell
python scripts/migrate.py
docker compose -f infra/docker-compose.production.yml up -d
docker compose -f infra/docker-compose.production.yml --profile batch up -d airflow
```

기동 후 RabbitMQ DLQ, `/metrics`, Grafana dashboard, Airflow DAG를 순서대로 확인합니다.
