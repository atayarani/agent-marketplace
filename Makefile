# agent-marketplace build/install driver.
#
# No per-harness logic lives here — every target dispatches to
# bin/adapters/<harness>.sh. Single source of truth for all manifests:
# plugins/<name>/meta.yaml. Generated manifests are build artifacts.

SHELL     := /bin/bash
HARNESSES := claude codex gemini pi

.PHONY: help build install validate clean \
        $(addprefix install-,$(HARNESSES)) \
        $(addprefix uninstall-,$(HARNESSES))

help:
	@echo "agent-marketplace — canonical content + per-harness adapters"
	@echo
	@echo "Targets:"
	@echo "  build                Regenerate every harness manifest from meta.yaml (no \$$HOME writes)"
	@echo "  install              Install into every harness that has an adapter"
	@echo "  install-<harness>    Install one harness: $(HARNESSES)"
	@echo "  uninstall-<harness>  Remove one harness's install (never touches plugins/)"
	@echo "  validate             build, then run available manifest validators"
	@echo "  clean                Remove generated manifest artifacts from the working tree"
	@echo
	@echo "Sandboxed dry run:        PREFIX=/tmp/mp make install-claude"
	@echo "Copy instead of symlink:  COPY=1 make install-claude"

build:
	@for h in $(HARNESSES); do \
	  if [ -x bin/adapters/$$h.sh ]; then \
	    echo "==> build $$h"; bin/adapters/$$h.sh build; \
	  fi; \
	done

install:
	@for h in $(HARNESSES); do \
	  if [ -x bin/adapters/$$h.sh ]; then \
	    $(MAKE) --no-print-directory install-$$h; \
	  fi; \
	done

install-%:
	@test -x bin/adapters/$*.sh || { echo "make: no adapter bin/adapters/$*.sh (not built yet)"; exit 1; }
	@bin/adapters/$*.sh install

uninstall-%:
	@test -x bin/adapters/$*.sh || { echo "make: no adapter bin/adapters/$*.sh"; exit 1; }
	@bin/adapters/$*.sh uninstall

validate: build
	@if command -v claude >/dev/null 2>&1; then \
	  echo "==> claude plugin validate ."; claude plugin validate .; \
	else \
	  echo "validate: 'claude' CLI not found; skipping"; \
	fi

clean:
	@rm -rf plugins/*/.claude-plugin/plugin.json \
	        plugins/*/.codex-plugin/plugin.json \
	        .agents/plugins/marketplace.json \
	        .claude-plugin/marketplace.json \
	        gemini-extension.json \
	        gemini/
	@echo "clean: removed generated manifest artifacts"
