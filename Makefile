# Root-level Makefile — delegates to infra/Makefile
# Run `make help` to see all available targets.

.DEFAULT_GOAL := help

%:
	@$(MAKE) -C infra $@
