# Build Gridfinity containers from the screw-organiser layouts.
#
#   make            all containers from ../screw-organiser/layouts -> out/
#                   (existing files are skipped — the builder checks first)
#   make list       show the derived container list without building
#   make configs    generate editable manifest YAMLs -> configs/
#   make plates     pack everything onto build plates (multi-bed 3MFs)
#   make stl        all containers as single-colour STLs -> out/stl/
#   make force      rebuild everything, overwriting existing files
#   make clean      remove out/
#
# Point at other layouts with LAYOUTS_DIR=path/to/layouts.
# Magnets: MAGNETS=1 make   (or MAGNETS=0 to force off; also read from .env)
# Screw checkers: CHECKERS=1 make   (off by default; also read from .env)
# Printer preset for plates/configs: PRINTER=prusa-core-one make plates
#   (also read from the environment or .env; see --list-printers)
# Exclude containers: make plates EXTRA='--exclude "misc,m3n*"'
# Tools for parts: make EXTRA='--bin-tool 3 --label-tool 2'
#   (record what's loaded per printer with `uv run gridfinity-filaments`)

LAYOUTS_DIR ?= ../screw-organiser/layouts
PRINTER ?=
PRINTER_ARG := $(if $(PRINTER),--printer $(PRINTER),)
RUN := uv run gridfinity-container-builder --layouts-dir $(LAYOUTS_DIR)
EXTRA ?=

.PHONY: all list configs plates magnets stl force clean

all:
	$(RUN) --out out $(EXTRA)

list:
	$(RUN) --list

configs:
	uv run gridfinity-config-builder --layouts-dir $(LAYOUTS_DIR) --out configs $(PRINTER_ARG) $(EXTRA)

plates:
	$(RUN) --plates $(PRINTER_ARG) --out out/plates $(EXTRA)

magnets:
	$(RUN) --magnets --out out/magnets $(EXTRA)

stl:
	$(RUN) --format stl --out out/stl $(EXTRA)

force:
	$(RUN) --out out --force $(EXTRA)

clean:
	rm -rf out
