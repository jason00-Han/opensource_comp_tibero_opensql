.PHONY: test test-unit test-integration test-rabbitmq test-openproxy test-e2e

test:
	python -m pytest -m "not rabbitmq and not openproxy" -q

test-unit:
	python -m pytest -m unit -q

test-integration:
	python -m pytest -m "integration and not rabbitmq and not openproxy" -q

test-rabbitmq:
	RUN_RABBITMQ_TESTS=1 python -m pytest -m rabbitmq -q

test-openproxy:
	@test -n "$(OPENPROXY_TEST_DSN)" || (echo "OPENPROXY_TEST_DSN is required" && exit 1)
	python -m pytest -m openproxy -q

test-e2e:
	RUN_RABBITMQ_TESTS=1 python -m pytest -m e2e -q
