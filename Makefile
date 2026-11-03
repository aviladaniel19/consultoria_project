.PHONY: up down validate init ingest sources dbt api test

up:            ## Levanta Postgres y la API
	docker compose up -d --build db api

down:
	docker compose down

validate:      ## Valida el registro de fuentes
	plataforma validate

init:          ## Crea esquemas y catálogo
	plataforma init-db

ingest:        ## Carga todas las fuentes activas
	plataforma ingest --all

sources:       ## Regenera las fuentes de dbt desde el registro
	plataforma dbt-sources

dbt: sources   ## Construye y prueba las capas estandarizada y analítica
	cd transform && DBT_PROFILES_DIR=. dbt build

api:           ## API en modo desarrollo
	uvicorn plataforma.api.main:app --reload

test:
	pytest -q
