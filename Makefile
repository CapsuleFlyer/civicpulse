# CivicPulse — the commands in the README, in one place, so that the README
# and the thing it documents cannot drift apart.
#
#     make help

SHELL := /bin/bash
COMPOSE ?= docker compose
NAMESPACE ?= civicpulse
CLUSTER ?= civicpulse
IMAGE_TAG ?= $(shell git rev-parse HEAD 2>/dev/null || echo dev)
REGISTRY ?= ghcr.io/your-org

.DEFAULT_GOAL := help
.PHONY: help up down logs seed reset ps shell-backend psql redis \
        test test-backend test-frontend lint fmt typecheck check \
        build images scan cluster deploy undeploy rollback k8s-logs \
        hpa-watch load smoke contract clean

## ----------------------------------------------------------------------
## Local stack
## ----------------------------------------------------------------------

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

up: .env ## Build and start the whole stack with migrations and seed data
	$(COMPOSE) up -d --build
	@echo "frontend  http://localhost:8080"
	@echo "backend   http://localhost:8000/docs"

down: ## Stop the stack, keeping volumes (rows survive)
	$(COMPOSE) down

reset: ## Stop the stack and destroy volumes (rows do not survive)
	$(COMPOSE) down -v

ps: ## Show container health
	$(COMPOSE) ps

logs: ## Tail structured JSON logs from the backend
	$(COMPOSE) logs -f backend

seed: ## Re-run the idempotent seed (safe to run repeatedly)
	$(COMPOSE) exec backend python -m app.seed

shell-backend: ## Shell into the backend container
	$(COMPOSE) exec backend /bin/bash

psql: ## Open psql inside the database container
	$(COMPOSE) exec database psql -U $${POSTGRES_USER:-civic} -d $${POSTGRES_DB:-civicpulse}

redis: ## Open redis-cli inside the cache container
	$(COMPOSE) exec cache redis-cli

.env:
	@echo "No .env found. Copying .env.example — edit it before going anywhere real."
	cp .env.example .env

## ----------------------------------------------------------------------
## Quality gates — the same commands CI runs
## ----------------------------------------------------------------------

test: test-backend test-frontend ## Run every test suite

test-backend: ## pytest with coverage (gate: 65%)
	cd backend && TRIAGE_PROVIDER=simulated python -m pytest

test-frontend: ## Vitest component tests
	cd frontend && npm run test

lint: ## ruff + eslint
	cd backend && ruff check .
	cd frontend && npm run lint

fmt: ## ruff format
	cd backend && ruff format .

typecheck: ## mypy + tsc
	cd backend && mypy app
	cd frontend && npx tsc --noEmit

check: lint typecheck test ## Everything CI checks, locally, before you push
	python scripts/check_submission.py

smoke: ## Run the end-to-end smoke test against a running stack
	python scripts/integration_smoke.py --base-url http://localhost:8000

contract: ## Check the frontend contract against the live OpenAPI schema
	python scripts/check_api_contract.py --base-url http://localhost:8000

## ----------------------------------------------------------------------
## Images
## ----------------------------------------------------------------------

build: images ## Alias for images

images: ## Build both images tagged with the current commit SHA
	docker build -t $(REGISTRY)/civicpulse-backend:$(IMAGE_TAG) ./backend
	docker build -t $(REGISTRY)/civicpulse-frontend:$(IMAGE_TAG) ./frontend
	@docker images --format '{{.Repository}}:{{.Tag}}\t{{.Size}}' \
	  | grep civicpulse | head -4

scan: ## Trivy scan both images, failing on fixable HIGH/CRITICAL
	trivy image --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 \
	  $(REGISTRY)/civicpulse-backend:$(IMAGE_TAG)
	trivy image --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 \
	  $(REGISTRY)/civicpulse-frontend:$(IMAGE_TAG)

## ----------------------------------------------------------------------
## Kubernetes
## ----------------------------------------------------------------------

cluster: ## Create a local k3d cluster with an ingress port mapping
	k3d cluster create $(CLUSTER) --agents 2 -p "8081:80@loadbalancer"
	kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
	kubectl -n kube-system patch deployment metrics-server --type=json \
	  -p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'

deploy: ## Apply the dev overlay to the current cluster context
	kubectl apply -k k8s/overlays/dev
	kubectl -n $(NAMESPACE) rollout status deployment/backend --timeout=180s
	kubectl -n $(NAMESPACE) rollout status deployment/frontend --timeout=180s

undeploy: ## Delete the namespace and everything in it
	kubectl delete namespace $(NAMESPACE) --ignore-not-found

rollback: ## The 3 a.m. answer: undo the last backend rollout
	kubectl -n $(NAMESPACE) rollout undo deployment/backend
	kubectl -n $(NAMESPACE) rollout status deployment/backend --timeout=120s

k8s-logs: ## Tail backend logs across all replicas
	kubectl -n $(NAMESPACE) logs -l app.kubernetes.io/name=backend -f --max-log-requests 10

hpa-watch: ## Capture HPA scale-out for docs/evidence/
	kubectl -n $(NAMESPACE) get hpa -w | tee docs/evidence/hpa-watch.txt

load: ## Run the k6 load profile against the ingress
	k6 run -e BASE_URL=$${BASE_URL:-http://localhost:8081} load/k6-script.js

clean: ## Remove local build and test artefacts
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf backend/.pytest_cache backend/.mypy_cache backend/.ruff_cache \
	       backend/.coverage backend/htmlcov frontend/dist frontend/.vite
