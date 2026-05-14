# Dev container image for predictive-mcdm-defi.
#
# Base: official Microsoft devcontainers Python image (Debian Bookworm,
# Python 3.12 — matches the project's pinned interpreter). The base
# already includes git, curl, ca-certificates, and the `vscode` non-root
# user, so we only add the LaTeX toolchain (whitepaper compile) and a
# small set of build deps for any C-extension wheels that might miss a
# manylinux build.
#
# Multi-stage isn't useful here because the LaTeX install accounts for
# nearly all of the image weight and we need it at runtime; single
# stage with `--no-install-recommends` keeps the final image under
# ~1.5 GB.

FROM mcr.microsoft.com/devcontainers/python:3.12-bookworm

ENV DEBIAN_FRONTEND=noninteractive

# System dependencies:
#   build-essential: fallback for any pure-source pip installs
#   texlive-* + biber + latexmk: whitepaper compile (mirrors CI test.yml)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        texlive-latex-extra \
        texlive-bibtex-extra \
        texlive-fonts-recommended \
        texlive-science \
        latexmk \
        biber \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Pre-upgrade pip so the postCreateCommand `pip install -r requirements.txt`
# resolves wheels via the modern resolver from the start.
RUN python -m pip install --upgrade pip

# Note: we deliberately do NOT `pip install -r requirements.txt` here.
# Doing it at image-build time would bake fractal-defi @ git+... into the
# layer, which makes the image stale the moment the tag moves. The
# devcontainer.json `postCreateCommand` runs install on every container
# create, which is the right granularity for a research repo.
