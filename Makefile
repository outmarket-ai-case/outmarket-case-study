# Thin wrappers over the real commands -- everything here is copy-pasteable.
.DEFAULT_GOAL := help
SHELL := /bin/bash

CLOUD ?= aws
ENV   ?= dev
STACK := infra/terraform/stacks/$(CLOUD)
VARS  := $(abspath infra/terraform/envs/$(CLOUD)-$(ENV).tfvars)

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

## --- local ---
.PHONY: up down logs rebuild
up: ## Start the full stack locally (http://localhost:8080)
	docker compose up --build -d
	@echo "frontend -> http://localhost:8080   api -> http://localhost:8000/docs"

down: ## Stop the stack and drop the volume
	docker compose down -v

logs: ## Tail all service logs
	docker compose logs -f

rebuild: down up ## Full clean restart

## --- test ---
.PHONY: test test-backend test-frontend test-ai lint
test: test-backend test-frontend test-ai ## Run every test suite

test-backend:
	cd backend && .venv/bin/python -m pytest -q

test-frontend:
	cd frontend && npx vitest run

test-ai:
	cd ai && ../backend/.venv/bin/python -m pytest -q

lint: ## Lint python + typecheck the frontend
	cd backend && .venv/bin/ruff check app migrations tests
	cd ai && ../backend/.venv/bin/ruff check aiops tests
	cd frontend && npm run lint

## --- infrastructure ---
.PHONY: tf-init tf-plan tf-apply tf-destroy platform-json
tf-init: ## terraform init for CLOUD=aws|gcp
	terraform -chdir=$(STACK) init

tf-plan: ## terraform plan for CLOUD/ENV
	terraform -chdir=$(STACK) plan -var-file=$(VARS)

tf-apply: ## terraform apply for CLOUD/ENV
	terraform -chdir=$(STACK) apply -var-file=$(VARS)

tf-destroy: ## Tear the environment down
	terraform -chdir=$(STACK) destroy -var-file=$(VARS)

platform-json: ## Emit the cloud-neutral platform contract for CLOUD/ENV
	@terraform -chdir=$(STACK) output -json platform

## --- ai platform ---
.PHONY: ai-plan-env ai-gate
ai-plan-env: ## Compile platform.yaml intent -> tfvars + helm values (AI + policy)
	cd ai && ../backend/.venv/bin/python -m aiops plan-env --spec ../platform.yaml --env $(ENV) --cloud $(CLOUD) --out ../.aiops

ai-gate: ## Run the AI release gate against the current release
	cd ai && ../backend/.venv/bin/python -m aiops gate --release idea-board --namespace idea-board-$(ENV)
