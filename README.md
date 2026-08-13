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