PYTHON_HOSHINO := .venv-hoshino/bin/python
PYTHON_AUTOPCR := .venv-autopcr/bin/python
AUTOPCR_ROOT ?= ../ref/autopcr_latest
HOSHINO_ROOT ?= ../ref/HoshinoBot

.PHONY: help lint test test-autopcr test-provision check venv-autopcr venv-hoshino compile clean

help:
	@echo "lint          静态检查"
	@echo "compile       在两套环境下分别做语法检查"
	@echo "test          运行不依赖 autopcr 的测试"
	@echo "test-autopcr  拉起真实的 autopcr 并验证网页端与转发"
	@echo "test-provision 从零取得源码、建环境并拉起 wrapper"
	@echo "check         lint + compile + test"
	@echo "venv-autopcr  创建运行 autopcr 的环境（部署所需）"
	@echo "venv-hoshino  创建模拟宿主框架的环境（仅验证所需）"

# 显式限定检查范围：即使从其他目录调用，也不会波及本项目之外的代码。
lint:
	ruff check $(CURDIR)

compile:
	$(PYTHON_HOSHINO) -m compileall -q hbot protocol catalog.py entry.py __init__.py tests
	$(PYTHON_AUTOPCR) -m compileall -q wrapper protocol catalog.py __init__.py

# 把参考源码位置传给需要它们的测试；未提供时相应测试会自行跳过。
test: export AUTOPCR_HOSHINO_TEST_HOSHINO = $(abspath $(HOSHINO_ROOT))
test:
	$(PYTHON_HOSHINO) tests/settings_check.py
	$(PYTHON_HOSHINO) tests/source_check.py
	$(PYTHON_HOSHINO) tests/session_check.py
	$(PYTHON_HOSHINO) tests/cross_env_check.py
	$(PYTHON_HOSHINO) tests/proxy_check.py
	$(PYTHON_HOSHINO) tests/hoshino_load_check.py
	$(PYTHON_HOSHINO) tests/orphan_check.py

test-provision:
	$(PYTHON_HOSHINO) tests/provision_check.py

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
