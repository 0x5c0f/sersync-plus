# Sersync Plus Makefile

.PHONY: help install test build clean binary docker

# 默认目标
help:
	@echo "Sersync Plus 构建工具"
	@echo "===================="
	@echo ""
	@echo "可用命令:"
	@echo "  install    - 安装依赖"
	@echo "  test       - 运行测试"
	@echo "  build      - 构建 Python 包"
	@echo "  binary     - 构建二进制文件"
	@echo "  clean      - 清理构建文件"
	@echo "  docker     - 构建 Docker 镜像"
	@echo "  help       - 显示此帮助信息"

# 安装依赖
install:
	@echo "📦 安装依赖..."
	poetry install --with dev

# 运行测试
test:
	@echo "🧪 运行测试..."
	poetry run pytest

# 构建 Python 包
build:
	@echo "🔨 构建 Python 包..."
	poetry build

# 构建二进制文件
binary:
	@echo "🚀 构建二进制文件..."
	python scripts/build.py

# 快速二进制构建
binary-fast:
	@echo "⚡ 快速构建二进制文件..."
	./scripts/build.sh

# 清理构建文件
clean:
	@echo "🧹 清理构建文件..."
	rm -rf build/ dist/ *.spec
	rm -rf sersync/__pycache__/ sersync/*/__pycache__/
	rm -rf .pytest_cache/ .coverage htmlcov/
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# 构建 Docker 镜像
docker:
	@echo "🐳 构建 Docker 镜像..."
	docker build -t sersync-plus:latest .

# 开发环境设置
dev-setup: install
	@echo "🛠️  设置开发环境..."
	poetry run pre-commit install || echo "pre-commit not available"

# 代码质量检查
lint:
	@echo "🔍 代码质量检查..."
	poetry run ruff check .
	poetry run mypy sersync/

# 格式化代码
format:
	@echo "✨ 格式化代码..."
	poetry run black .
	poetry run isort .

# 完整的 CI 流程
ci: lint test build

# 发布准备
release: clean ci binary
	@echo "🎉 发布准备完成!"
	@echo "   Python 包: dist/*.whl"
	@echo "   二进制文件: dist/sersync-plus"