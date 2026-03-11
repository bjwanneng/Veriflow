#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "  Git Setup and Push Script"
echo "=========================================="
echo ""

# Check if git is installed
if ! command -v git &> /dev/null; then
    echo -e "${RED}Git is not installed. Please install git first.${NC}"
    exit 1
fi

echo "[1/7] Initializing Git repository..."
if ! git init; then
    echo -e "${RED}Git init failed.${NC}"
    exit 1
fi

echo ""
echo "[2/7] Adding files to staging area..."
git add README.md request.md QUICKSTART.md 2>/dev/null || true
git add example_project/ 2>/dev/null || true
git add verilog_flow/ 2>/dev/null || true
git add verilog-flow-skill/ 2>/dev/null || true
git add setup_git.sh 2>/dev/null || true

echo ""
echo "[3/7] Checking status..."
git status --short

echo ""
echo "[4/7] Committing changes..."
if git commit -m "Initial commit: VeriFlow Verilog code generation system

- Add 5-stage workflow (architecture to synthesis)
- Add RTL code generation with lint checking
- Add simulation with golden trace verification
- Add synthesis and timing analysis
- Add example project and documentation"; then
    echo -e "${GREEN}Commit successful${NC}"
else
    echo -e "${YELLOW}Nothing to commit or commit failed${NC}"
fi

echo ""
echo "[5/7] Renaming branch to main..."
git branch -M main 2>/dev/null || true

echo ""
echo "[6/7] Adding remote repository..."
git remote add origin https://github.com/bjwanneng/Veriflow.git 2>/dev/null || echo -e "${YELLOW}Remote already exists or error occurred${NC}"

echo ""
echo "[7/7] Pushing to GitHub..."
echo "=========================================="
echo "IMPORTANT: You may need to authenticate"
echo "with GitHub if this is your first push."
echo "=========================================="
echo ""

if git push -u origin main; then
    echo ""
    echo "=========================================="
    echo -e "${GREEN}Success! Code pushed to GitHub.${NC}"
    echo "https://github.com/bjwanneng/Veriflow"
    echo "=========================================="
else
    echo ""
    echo "=========================================="
    echo -e "${RED}Push failed. Common issues:${NC}"
    echo "1. Check your internet connection"
    echo "2. Verify the GitHub repo exists:"
    echo "   https://github.com/bjwanneng/Veriflow"
    echo "3. You may need to authenticate with GitHub"
    echo "=========================================="
    exit 1
fi
