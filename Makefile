.PHONY: test test-cov build shell typecheck

IMAGE := electricity-price-tests

build:
	docker build -f Dockerfile.test -t $(IMAGE) .

test: build
	docker run --rm $(IMAGE)

test-cov: build
	docker run --rm $(IMAGE) python -m pytest tests/ -v \
		--cov=custom_components/electricity_price \
		--cov-report=term-missing

shell: build
	docker run --rm -it $(IMAGE) bash

typecheck:
	docker run --rm -v $(CURDIR):/code python:3.13-slim sh -c \
		"pip install mypy --quiet --root-user-action=ignore 2>/dev/null && \
		mypy --strict --ignore-missing-imports /code/custom_components/electricity_price/"
