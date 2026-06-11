.PHONY: dev seed coach-cli deploy help

help:
	@echo "make dev        - run the GAFFER server locally (http://localhost:8080)"
	@echo "make seed       - create the baseline playbook v1 in Phoenix + tag production"
	@echo "make deploy     - deploy to Cloud Run from source"

dev:
	uv run uvicorn server.app:app --reload --port 8080

seed:
	uv run python -m scripts.seed_playbook

deploy:
	gcloud run deploy gaffer --source . --region us-central1 --allow-unauthenticated \
	  --set-env-vars "GOOGLE_GENAI_USE_VERTEXAI=1,GOOGLE_CLOUD_PROJECT=$(GOOGLE_CLOUD_PROJECT),GOOGLE_CLOUD_LOCATION=global,GEMINI_MODEL=gemini-3.5-flash,PHOENIX_API_KEY=$(PHOENIX_API_KEY),PHOENIX_COLLECTOR_ENDPOINT=$(PHOENIX_COLLECTOR_ENDPOINT),PHOENIX_PROJECT_NAME=gaffer-pitch"
