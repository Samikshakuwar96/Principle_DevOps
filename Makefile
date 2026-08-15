.PHONY: generate test lint tf-fmt tf-validate

generate:
	python3 scripts/generate_tfvars.py config/dev.json -o terraform/environments/dev/dev.auto.tfvars.json
	python3 scripts/generate_tfvars.py config/prod.json -o terraform/environments/prod/prod.auto.tfvars.json

test:
	pytest -q

lint:
	ruff check scripts tests

tf-fmt:
	terraform fmt -recursive -check terraform

tf-validate:
	terraform -chdir=terraform/environments/dev init -backend=false
	terraform -chdir=terraform/environments/dev validate
	terraform -chdir=terraform/environments/prod init -backend=false
	terraform -chdir=terraform/environments/prod validate
