PYTHON_HOSHINO := .venv-hoshino/bin/python
PYTHON_AUTOPCR := .venv-autopcr/bin/python
AUTOPCR_ROOT ?= ../ref/autopcr_latest
HOSHINO_ROOT ?= ../ref/HoshinoBot

.PHONY: help lint test test-autopcr check venv-autopcr venv-hoshino compile clean

help:
	@echo "lint          静态检查"
	@echo "compile       在两套环境下分别做语法检查"
	@echo "test          运行不依赖 autopcr 的实测"
	@echo "test-autopcr  拉起真实的 autopcr 并验证网页端与转发"
	@echo "check         lint + compile + test"
	@echo "venv-autopcr  创建运行 autopcr 的环境（部署所需）"
	@echo "venv-hoshino  创建模拟宿主框架的环境（仅验证所需）"

lint:
	ruff check .

compile:
	$(PYTHON_HOSHINO) -m compileall -q hbot protocol catalog.py entry.py __init__.py tests
	$(PYTHON_AUTOPCR) -m compileall -q wrapper protocol catalog.py __init__.py

test:
	$(PYTHON_HOSHINO) tests/session_check.py
	$(PYTHON_HOSHINO) tests/cross_env_check.py
	$(PYTHON_HOSHINO) tests/proxy_check.py
	$(PYTHON_HOSHINO) tests/hoshino_load_check.py
	$(PYTHON_HOSHINO) tests/orphan_check.py

test-autopcr:
	AUTOPCR_HOSHINO_AUTOPCR_ROOT=$(abspath $(AUTOPCR_ROOT)) \
		$(PYTHON_HOSHINO) tests/autopcr_boot_check.py

check: lint compile test

venv-autopcr:
	uv venv --python 3.10 .venv-autopcr
	uv pip install --python $(PYTHON_AUTOPCR) -r $(AUTOPCR_ROOT)/requirements.txt

venv-hoshino:
	uv venv --python 3.8 .venv-hoshino
	uv pip install --python $(PYTHON_HOSHINO) -r $(HOSHINO_ROOT)/requirements.txt

clean:
	find . -name '__pycache__' -type d -not -path './.venv-*' -exec rm -rf {} +
