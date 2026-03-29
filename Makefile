.PHONY: test test-cov build shell

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
