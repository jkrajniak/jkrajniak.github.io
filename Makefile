.PHONY: install serve build clean migrate migrate-text migrate-devto diagram-dagster-azure-io diagram-medioteka diagram-research-project-structure

SHELL := /bin/bash
RBENV := eval "$$(rbenv init - bash)" &&

MEDIUM_INPUT ?= _medium/posts
MIGRATION_DIR = blog-migration

# ── Jekyll ───────────────────────────────────────────────────────────
install:
	$(RBENV) bundle install

serve: install
	$(RBENV) bundle exec jekyll serve --livereload

serve-drafts: install
	$(RBENV) bundle exec jekyll serve --livereload --drafts

build: install
	$(RBENV) bundle exec jekyll build

clean:
	$(RBENV) bundle exec jekyll clean
	rm -rf _site .jekyll-cache .jekyll-metadata

# ── Diagrams ─────────────────────────────────────────────────────────
diagram-dagster-azure-io:
	npx --yes @mermaid-js/mermaid-cli \
		-i assets/images/posts/dagster-parallelism-in-azure-cloud/pipeline-flow.mmd \
		-o assets/images/posts/dagster-parallelism-in-azure-cloud/pipeline-flow.svg \
		-b transparent

MEDIOTEKA_DIAGRAMS := components usecase-watch usecase-add usecase-bandwidth
diagram-medioteka:
	@for name in $(MEDIOTEKA_DIAGRAMS); do \
		npx --yes @mermaid-js/mermaid-cli \
			-i assets/images/posts/old-laptop-jellyfin-media-server/$$name.mmd \
			-o assets/images/posts/old-laptop-jellyfin-media-server/$$name.svg \
			-b transparent; \
	done

diagram-research-project-structure:
	npx --yes @mermaid-js/mermaid-cli \
		-i assets/images/posts/structuring-a-computational-research-project/workspace-layout.mmd \
		-o assets/images/posts/structuring-a-computational-research-project/workspace-layout.svg \
		-b transparent

# ── Migration ────────────────────────────────────────────────────────
migrate:
	uv run --project $(MIGRATION_DIR) python $(MIGRATION_DIR)/migrate_medium.py \
		--input $(MEDIUM_INPUT) --output .

migrate-text:
	uv run --project $(MIGRATION_DIR) python $(MIGRATION_DIR)/migrate_medium.py \
		--input $(MEDIUM_INPUT) --output . --skip-images
