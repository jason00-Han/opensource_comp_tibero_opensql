# Tibero Doc 문서 안내

프로젝트 문서는 사용 목적에 따라 분리되어 있습니다.

| 문서 | 대상            | 내용 |
|---|-----------------|---|
| [프로젝트 README](../README.md) | 사용자          | 설치, 로그인, 업로드, 검색, 대시보드 |
| [개발 및 아키텍처 가이드](development-guide.md) | 개발자          | 구성요소, 데이터 모델, 요청 흐름, 확장 지점 |
| [데이터 플랫폼 운영 가이드](data-platform-operations.md) | 운영자          | 실행, Worker, Retry/DLQ, Outbox, 관측성, 장애 대응 |
| [코드 리뷰 가이드](code-review-guide.md) | 코드 리뷰어     | 주요 함수·클래스·예외 처리 경계 |
| [비정형 데이터 수명주기](unstructured-data-lifecycle.md) | 데이터 엔지니어 | Hot/Warm/Cold, 보존, 삭제 승인 |

## 처음 읽는 순서

1. 루트 `README.md`의 5분 빠른 시작으로 서비스를 실행합니다.
2. 이 프로젝트를 수정하려면 `development-guide.md`의 아키텍처와 데이터 흐름을 읽습니다.
3. 실제 운영과 장애 시연은 `data-platform-operations.md`를 따릅니다.
4. 함수 단위 검토가 필요할 때만 `code-review-guide.md`를 사용합니다.

## 문서 관리 원칙

- README에는 사용자가 실행할 명령과 얻는 결과만 둡니다.
- 구현 세부사항은 개발 가이드에 기록합니다.
- 환경변수, 복구 절차와 모니터링은 운영 가이드에 기록합니다.
- 아직 실제 검증하지 않은 성능 수치는 완료된 결과처럼 기록하지 않습니다.
- 비밀번호, API Key, 실제 DSN은 문서와 예제 파일에 커밋하지 않습니다.
