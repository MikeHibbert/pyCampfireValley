#!/usr/bin/env bash
set -euo pipefail
APP=campfirevalley

MUTED='\033[0;2m'
RED='\033[0;31m'
GREEN='\033[0;32m'
ORANGE='\033[38;5;214m'
NC='\033[0m' # No Color

usage() {
    cat <<EOF
CampfireValley Onboarding

Usage: onboard.sh [options]

Options:
    -h, --help              Display this help message
        --no-install        Skip pip install (assume already installed)
        --no-docker         Skip the Docker UI stack (local demo only)
        --workspace <dir>   Workspace directory (default: demo_workspace)
        --provider <name>   LLM provider: ollama | openrouter (default: auto)
        --model <name>      LLM model name (default: provider default)

Examples:
    curl -fsSL https://raw.githubusercontent.com/MikeHibbert/pyCampfireValley/main/onboard.sh | bash
    ./onboard.sh --no-docker --provider ollama
    ./onboard.sh --workspace my_workspace --provider openrouter
EOF
}

no_install=false
no_docker=false
workspace="demo_workspace"
provider=""
model=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;
        --no-install)
            no_install=true
            shift
            ;;
        --no-docker)
            no_docker=true
            shift
            ;;
        --workspace)
            if [[ -n "${2:-}" ]]; then
                workspace="$2"
                shift 2
            else
                echo -e "${RED}Error: --workspace requires a directory argument${NC}"
                exit 1
            fi
            ;;
        --provider)
            if [[ -n "${2:-}" ]]; then
                provider="$2"
                shift 2
            else
                echo -e "${RED}Error: --provider requires an argument${NC}"
                exit 1
            fi
            ;;
        --model)
            if [[ -n "${2:-}" ]]; then
                model="$2"
                shift 2
            else
                echo -e "${RED}Error: --model requires an argument${NC}"
                exit 1
            fi
            ;;
        *)
            echo -e "${ORANGE}Warning: Unknown option '$1'${NC}" >&2
            shift
            ;;
    esac
done

print_message() {
    local level=$1
    local message=$2
    local color=""
    case $level in
        info) color="${NC}" ;;
        ok) color="${GREEN}" ;;
        warning) color="${ORANGE}" ;;
        error) color="${RED}" ;;
    esac
    echo -e "${color}${message}${NC}"
}

check_cmd() {
    local cmd=$1
    if command -v "$cmd" >/dev/null 2>&1; then
        return 0
    fi
    return 1
}

require() {
    local cmd=$1
    local hint=$2
    if ! check_cmd "$cmd"; then
        echo -e "${RED}Error: '$cmd' is required but not installed.${NC}"
        echo -e "${MUTED}  $hint${NC}"
        exit 1
    fi
}

echo -e ""
echo -e "${MUTED}  █▀▀█ █▀▀█ █▀▀█ █▀▀▄ █▀▀▀ █▀▀█ █▀▀█ █▀▀█${NC}"
echo -e "${MUTED}  █░░█ █░░█ █▀▀▀ █░░█ █░░░ █░░█ █░░█ █▀▀▀${NC}"
echo -e "${MUTED}  ▀▀▀▀ █▀▀▀ ▀▀▀▀ ▀  ▀ ▀▀▀▀ ▀▀▀▀ ▀▀▀▀ ▀▀▀▀${NC}"
echo -e ""
echo -e "${MUTED}  CampfireValley onboarding${NC}"
echo -e ""

# ── 1. Prerequisites ────────────────────────────────────────────────────────
print_message info "\n${MUTED}Checking prerequisites...${NC}"
require python3 "Install Python 3.8+ from https://www.python.org/downloads/"
require pip3 "Install pip: python3 -m ensurepip --upgrade"

PYTHON_OK=$(python3 -c 'import sys; print(1 if sys.version_info >= (3,8) else 0)' 2>/dev/null || echo 0)
if [ "$PYTHON_OK" != "1" ]; then
    echo -e "${RED}Error: Python 3.8+ required.${NC}"
    exit 1
fi
print_message ok "  Python: $(python3 --version)"

# ── 2. Install package ───────────────────────────────────────────────────────
if [ "$no_install" = "true" ]; then
    print_message info "${MUTED}Skipping install (--no-install)${NC}"
else
    print_message info "\n${MUTED}Installing CampfireValley...${NC}"
    pip3 install -e ".[dev]" 2>&1 | tail -n 3
    print_message ok "  Installed"
fi

# ── 3. LLM provider detection ─────────────────────────────────────────────────
if [ -z "$provider" ]; then
    if [ -n "${OPENROUTER_API_KEY:-}" ]; then
        provider="openrouter"
    elif check_cmd ollama; then
        provider="ollama"
    else
        provider="ollama"
    fi
fi

if [ "$provider" = "ollama" ]; then
    if ! check_cmd ollama; then
        print_message warning "  Ollama not found. Install from https://ollama.com/download"
        print_message warning "  Then: ollama pull llama3.2"
    else
        print_message ok "  Ollama: $(ollama --version 2>/dev/null | head -n1 || echo 'installed')"
        if [ -z "$model" ]; then
            model=$(ollama list 2>/dev/null | awk 'NR==2{print $1}' || echo "")
        fi
        if [ -z "$model" ]; then
            print_message warning "  No local model found. Pull one: ollama pull llama3.2"
        else
            print_message ok "  Model: $model"
        fi
    fi
elif [ "$provider" = "openrouter" ]; then
    if [ -z "${OPENROUTER_API_KEY:-}" ]; then
        print_message warning "  OPENROUTER_API_KEY not set. Export it before running the demo."
    else
        print_message ok "  OpenRouter: key detected"
    fi
    if [ -z "$model" ]; then
        model="openrouter/auto"
    fi
fi

# ── 4. Smoke test (setup-only, no LLM needed) ────────────────────────────────
print_message info "\n${MUTED}Running setup-only smoke test...${NC}"
if python3 examples/legal_team_demo.py --setup-only --workspace "$workspace" 2>&1 | tail -n 5; then
    print_message ok "  Smoke test passed"
else
    print_message warning "  Smoke test had issues (see output above)"
fi

# ── 5. Docker UI stack (optional) ───────────────────────────────────────────
if [ "$no_docker" = "true" ]; then
    print_message info "${MUTED}Skipping Docker UI stack (--no-docker)${NC}"
else
    if check_cmd docker; then
        print_message info "\n${MUTED}Starting Docker UI stack...${NC}"
        docker compose up -d --build 2>&1 | tail -n 5
        print_message ok "  UI: http://localhost:8000 (local) / http://localhost:8001 (remote)"
    else
        print_message warning "  Docker not found. Install from https://www.docker.com/products/docker-desktop"
        print_message warning "  Or re-run with --no-docker for a local-only demo."
    fi
fi

# ── 6. Next steps ─────────────────────────────────────────────────────────────
echo -e ""
echo -e "${MUTED}CampfireValley is ready. To start:${NC}"
echo -e ""
echo -e "  python3 examples/legal_team_demo.py --workspace $workspace --provider $provider ${model:+--model $model}"
echo -e ""
echo -e "${MUTED}For the full walkthrough see ${NC}DEMO_GUIDE.md"
echo -e "${MUTED}For more information visit ${NC}https://github.com/MikeHibbert/pyCampfireValley"
echo -e ""
