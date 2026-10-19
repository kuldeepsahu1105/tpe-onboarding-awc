# ace-engines top-level targets

PYTHON ?= python3
ONBOARDING := tools/engine-onboarding
WEB_PORT ?= 8766
AWC_OCI_REGISTER ?= awc-oci-register
AWC_ONBOARDING_REPO ?=
ONBOARDING_AWC := $(ONBOARDING)/scripts/awc_onboarding.sh

.PHONY: help scaffold-engine validate-form serve-engine-form build-ui-schema \
	mirror-engine publish-engine register-partner-registry \
	discover-images onboarding-wizard onboarding-ui onboarding-mcp onboarding-mcp-config

help:
	@echo "ACE engine onboarding:"
	@echo "  make scaffold-engine FORM=path/to.input_form.yaml [FORCE=1] [DRY_RUN=1]"
	@echo "  make validate-form FORM=path/to.input_form.yaml"
	@echo "  make mirror-engine DIR=neo4j"
	@echo "  make publish-engine DIR=neo4j [PUSH=1 APPROVE_PUBLISH=1]"
	@echo "  make register-partner-registry CONFIG=neo4j/oci-register.config.example.yaml"
	@echo "  make serve-engine-form [WEB_PORT=8766]   # JSON Schema HTML form"
	@echo "  make build-ui-schema                   # refresh web/input_form.ui.schema.json"
	@echo "  make discover-images REPO_URL=... CHART=... VERSION=... [FORM=... WRITE=1]"
	@echo "  make onboarding-wizard|onboarding-ui|onboarding-mcp  # needs AWC_ONBOARDING_REPO"

scaffold-engine:
ifndef FORM
	$(error FORM is required. Example: make scaffold-engine FORM=$(ONBOARDING)/input_form.minimal.example.yaml FORCE=1)
endif
	$(PYTHON) $(ONBOARDING)/generate_engine.py --form $(FORM) --repo-root . \
		$(if $(FORCE),--force,) $(if $(DRY_RUN),--dry-run,)

validate-form:
ifndef FORM
	$(error FORM is required)
endif
	$(PYTHON) $(ONBOARDING)/validate_form.py --form $(FORM)

serve-engine-form:
	@echo "Open http://127.0.0.1:$(WEB_PORT)/"
	$(PYTHON) -m http.server $(WEB_PORT) --directory $(ONBOARDING)/web

build-ui-schema:
	$(PYTHON) $(ONBOARDING)/scripts/build_ui_schema.py

mirror-engine:
ifndef DIR
	$(error DIR is required, e.g. make mirror-engine DIR=neo4j)
endif
	bash $(ONBOARDING)/scripts/mirror_engine.sh $(DIR)

publish-engine:
ifndef DIR
	$(error DIR is required, e.g. make publish-engine DIR=neo4j PUSH=1)
endif
	bash $(ONBOARDING)/scripts/publish_engine.sh $(DIR) $(if $(PUSH),--push,)

register-partner-registry:
ifndef CONFIG
	$(error CONFIG is required — use generated oci-register.config.example.yaml)
endif
	AWC_OCI_REGISTER=$(AWC_OCI_REGISTER) bash $(ONBOARDING)/scripts/register_partner_registry.sh $(CONFIG)

discover-images:
ifdef RENDERED
	$(PYTHON) $(ONBOARDING)/discover_images.py --rendered $(RENDERED) \
		$(foreach f,$(VALUES),--values $(f)) \
		$(foreach s,$(SET),--set $(s)) \
		$(if $(and $(FORM),$(WRITE)),--write $(FORM),)
else
ifndef REPO_URL
	$(error REPO_URL, CHART, and VERSION are required (or set RENDERED=))
endif
ifndef CHART
	$(error CHART is required)
endif
ifndef VERSION
	$(error VERSION is required)
endif
	$(PYTHON) $(ONBOARDING)/discover_images.py \
		--repo-url $(REPO_URL) --chart $(CHART) --version $(VERSION) \
		$(foreach f,$(VALUES),--values $(f)) \
		$(foreach s,$(SET),--set $(s)) \
		$(if $(and $(FORM),$(WRITE)),--write $(FORM),)
endif

onboarding-wizard:
	AWC_ONBOARDING_REPO=$(AWC_ONBOARDING_REPO) bash $(ONBOARDING_AWC) wizard

onboarding-ui:
	AWC_ONBOARDING_REPO=$(AWC_ONBOARDING_REPO) bash $(ONBOARDING_AWC) ui

onboarding-mcp:
	AWC_ONBOARDING_REPO=$(AWC_ONBOARDING_REPO) bash $(ONBOARDING_AWC) mcp

onboarding-mcp-config:
	AWC_ONBOARDING_REPO=$(AWC_ONBOARDING_REPO) bash $(ONBOARDING_AWC) mcp config
