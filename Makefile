version := v4

.PHONY: all
all:

.PHONY: release
release:
	git fetch origin main
	git tag --force ${version} origin/main
	git push --force origin ${version}
