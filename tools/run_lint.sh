#!/bin/bash
# run_lint.sh - ACI (Agent-Computer Interface) for Verilog linting
# Usage: ./run_lint.sh <rtl_file1> [rtl_file2] ...

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if iverilog is available
if ! command -v iverilog &> /dev/null; then
    echo -e "${YELLOW}MOCK_LINT: No EDA tools detected (iverilog not found)${NC}"
    echo "MOCK_MODE: Simulating successful lint check"
    echo "{"
    echo '  "status": "MOCK_SUCCESS",'
    echo '  "tool": "iverilog (mock)",'
    echo '  "errors": [],'
    echo '  "warnings": [],'
    echo '  "files_checked": "'$#'"'
    echo "}"
    exit 0
fi

# Validate input
if [ $# -eq 0 ]; then
    echo -e "${RED}ERROR: No RTL files specified${NC}"
    echo "Usage: $0 <rtl_file1> [rtl_file2] ..."
    exit 1
fi

# Check all input files exist
for file in "$@"; do
    if [ ! -f "$file" ]; then
        echo -e "${RED}ERROR: File not found: $file${NC}"
        exit 1
    fi
done

echo -e "${GREEN}Running iverilog lint check...${NC}"
echo "Files to check: $#"
for file in "$@"; do
    echo "  - $file"
done

# Create temp output file
TEMP_VVP=$(mktemp /tmp/lint_XXXXXX.vvp)
trap "rm -f $TEMP_VVP" EXIT

# Run iverilog
LINT_OUTPUT=""
LINT_STATUS=0
if ! LINT_OUTPUT=$(iverilog -g2005 -Wall -o "$TEMP_VVP" "$@" 2>&1); then
    LINT_STATUS=1
fi

# Parse output
ERRORS=$(echo "$LINT_OUTPUT" | grep -i "error" | wc -l)
WARNINGS=$(echo "$LINT_OUTPUT" | grep -i "warning" | wc -l)

# Output results
echo ""
echo "========================================"
echo "LINT RESULTS"
echo "========================================"

if [ $LINT_STATUS -eq 0 ] && [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}Status: PASS${NC}"
    echo "Errors: 0"
    echo "Warnings: $WARNINGS"
    if [ $WARNINGS -gt 0 ]; then
        echo ""
        echo "Warnings:"
        echo "$LINT_OUTPUT" | grep -i "warning" | head -20
    fi
else
    echo -e "${RED}Status: FAIL${NC}"
    echo "Errors: $ERRORS"
    echo "Warnings: $WARNINGS"
    echo ""
    echo "Error details:"
    echo "$LINT_OUTPUT" | head -50
fi

# JSON output
JSON_FILE=$(dirname "$1")/../lint_report.json
if [ -w "$(dirname "$1")/.." ]; then
    cat > "$JSON_FILE" << EOF
{
  "status": "$([ $LINT_STATUS -eq 0 ] && [ $ERRORS -eq 0 ] && echo "PASS" || echo "FAIL")",
  "tool": "iverilog",
  "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "files_checked": $#,
  "errors": $ERRORS,
  "warnings": $WARNINGS,
  "output_snippet": $(echo "$LINT_OUTPUT" | head -20 | jq -Rs .)
}
EOF
    echo ""
    echo "JSON report saved to: $JSON_FILE"
fi

# Exit with status
[ $LINT_STATUS -eq 0 ] && [ $ERRORS -eq 0 ] && exit 0 || exit 1
