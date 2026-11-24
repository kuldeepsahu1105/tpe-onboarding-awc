# ace-engines top-level targets

PYTHON ?= python3
ONBOARDING := engine-onboarding
WEB_PORT ?= 8766
AWC_OCI_REGISTER ?= awc-oci-register

.PHONY: help scaffold-engine validate-form serve-engine-form build-ui-schema \
	mirror-engine publish-engine register-partner-registry \
	discover-images onboarding-wizard onboarding-ui onboarding-mcp onboarding-mcp-config

help:
	@echo "TPE onboarding for Anywhere Cloud (AWC). One tool. From the repo root:"
	@echo "  ./awc ui                         workbench (start here)"
	@echo "  ./awc build <file.input.yaml>    generate and validate"
	@echo "  ./awc blueprint <file>           one install guide"
	@echo "  ./awc validate <form.yaml>       check an input form"
	@echo "  ./awc scaffold <form.yaml>       write a product folder"
	@echo "  ./awc mirror <folder>            copy charts and images"
	@echo "  ./awc publish <folder>           dry run; --push only to send"
	@echo "  ./awc registry <action> <config> init, plan, verify, or apply registry access"
	@echo "  ./awc help                       same list, plus wizard, mcp, examples"
	@echo "Make runs those same actions:"
	@echo "  make scaffold-engine FORM=path/to.input_form.yaml [FORCE=1] [DRY_RUN=1]"
	@echo "  make validate-form FORM=path/to.input_form.yaml"
	@echo "  make mirror-engine DIR=examples/neo4j"
	@echo "  make publish-engine DIR=examples/neo4j [PUSH=1 APPROVE_PUBLISH=1]"
	@echo "  make register-partner-registry CONFIG=examples/neo4j/oci-register.config.example.yaml"
	@echo "  make serve-engine-form [WEB_PORT=8766]"
	@echo "  make build-ui-schema"
	@echo "  make discover-images REPO_URL=... CHART=... VERSION=... [FORM=... WRITE=1]"
	@echo "  make onboarding-ui               same as ./awc ui"

scaffold-engine:
ifndef FORM
	$(error FORM is required. Example: make scaffold-engine FORM=$(ONBOARDING)/examples/input_form.minimal.example.yaml FORCE=1)
endif
	$(PYTHON) $(ONBOARDING)/generate_engine.py --form $(FORM) --repo-root . \
		$(if $(FORCE),--force,) $(if $(DRY_RUN),--dry-run,)

validate-form:
ifndef FORM
	$(error FORM is required)
endif
	$(PYTHON) $(ONBOARDING)/validate_form.py --form $(FORM)

serve-engine-form:
	@echo "Open http://127.0.0.1:$(WEB_PORT)/web/"
	$(PYTHON) -m http.server $(WEB_PORT) --bind 127.0.0.1 --directory $(ONBOARDING)

build-ui-schema:
	$(PYTHON) $(ONBOARDING)/scripts/build_ui_schema.py

mirror-engine:
ifndef DIR
	$(error DIR is required, e.g. make mirror-engine DIR=examples/neo4j)
endif
	bash $(ONBOARDING)/scripts/mirror_engine.sh $(DIR)

publish-engine:
ifndef DIR
	$(error DIR is required, e.g. make publish-engine DIR=examples/neo4j PUSH=1)
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
	./awc wizard

onboarding-ui:
	./awc ui

onboarding-mcp:
	./awc mcp

onboarding-mcp-config:
	./awc mcp config
