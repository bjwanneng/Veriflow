"""Lint Checker for Verilog RTL (Stage 3)."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional


@dataclass
class LintIssue:
    """A single lint issue."""
    severity: str  # error, warning, info
    rule_id: str
    message: str
    line_number: int = 0
    column: int = 0
    suggestion: str = ""


@dataclass
class LintResult:
    """Result of lint checking."""
    file_path: str
    issues: List[LintIssue] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return len([i for i in self.issues if i.severity == 'error'])

    @property
    def warning_count(self) -> int:
        return len([i for i in self.issues if i.severity == 'warning'])

    @property
    def info_count(self) -> int:
        return len([i for i in self.issues if i.severity == 'info'])

    @property
    def passed(self) -> bool:
        return self.error_count == 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "passed": self.passed,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "issues": [
                {
                    "severity": i.severity,
                    "rule_id": i.rule_id,
                    "message": i.message,
                    "line_number": i.line_number,
                    "column": i.column,
                    "suggestion": i.suggestion
                }
                for i in self.issues
            ]
        }


class LintChecker:
    """Check Verilog code for common issues and style violations."""

    def __init__(self):
        self.rules = [
            self._check_module_declaration,
            self._check_sensitivity_list,
            self._check_blocking_nonblocking,
            self._check_full_case,
            self._check_synchronous_reset,
            self._check_unused_signals,
            self._check_naming_conventions,
            self._check_magic_numbers,
            self._check_inferred_latches,
            self._check_multi_driver_reset,
            self._check_unpacked_array_port,
            # v3.2 rules — derived from real-project bug patterns
            self._check_reg_driven_by_assign,
            self._check_forward_reference,
            self._check_nba_as_combinational,
            self._check_multi_driver_conflict,
            self._check_axis_handshake_pulse,
        ]

    def check(self, verilog_code: str, file_path: str = "<unknown>") -> LintResult:
        """Run all lint rules on Verilog code."""
        result = LintResult(file_path=file_path)

        for rule in self.rules:
            issues = rule(verilog_code)
            result.issues.extend(issues)

        return result

    def check_file(self, file_path: Path) -> LintResult:
        """Run lint on a file."""
        if not file_path.exists():
            result = LintResult(file_path=str(file_path))
            result.issues.append(LintIssue(
                severity='error',
                rule_id='FILE_NOT_FOUND',
                message=f'File does not exist: {file_path}',
                line_number=0,
                suggestion='Check the file path and ensure the file was generated correctly',
            ))
            return result
        verilog_code = file_path.read_text(encoding='utf-8')
        return self.check(verilog_code, str(file_path))

    def _check_module_declaration(self, code: str) -> List[LintIssue]:
        """Check for proper module declaration."""
        issues = []
        lines = code.split('\n')

        has_module = False
        has_endmodule = False

        for i, line in enumerate(lines, 1):
            if re.search(r'\bmodule\s+\w+', line):
                has_module = True
            if re.search(r'\bendmodule\b', line):
                has_endmodule = True

        if not has_module:
            issues.append(LintIssue(
                severity='error',
                rule_id='MODULE_MISSING',
                message='No module declaration found',
                line_number=0,
                suggestion='Add a module declaration: module <name> (port_list);'
            ))

        if has_module and not has_endmodule:
            issues.append(LintIssue(
                severity='error',
                rule_id='ENDMODULE_MISSING',
                message='Module declaration without endmodule',
                line_number=0,
                suggestion='Add endmodule at the end of the module'
            ))

        return issues

    def _check_sensitivity_list(self, code: str) -> List[LintIssue]:
        """Check for proper sensitivity lists."""
        issues = []

        # Find always blocks with incomplete sensitivity lists
        pattern = r'always\s*@\s*\(\s*\*\s*\)'
        matches = list(re.finditer(pattern, code, re.IGNORECASE))

        # Using @(*) is actually good practice, so no issue there
        # Check for missing signals in explicit sensitivity lists
        pattern = r'always\s*@\s*\(([^)]+)\)'
        matches = list(re.finditer(pattern, code, re.IGNORECASE))

        for match in matches:
            sensitivity = match.group(1)
            line_number = code[:match.start()].count('\n') + 1

            if 'posedge' in sensitivity or 'negedge' in sensitivity:
                # Clocked block - should have reset too if using sync logic
                pass
            else:
                # Combinational block - should use @(*) instead
                issues.append(LintIssue(
                    severity='warning',
                    rule_id='SENSITIVITY_LIST',
                    message=f'Explicit sensitivity list: {sensitivity.strip()}',
                    line_number=line_number,
                    suggestion='Use @(*) for combinational logic to avoid missing signals'
                ))

        return issues

    def _check_blocking_nonblocking(self, code: str) -> List[LintIssue]:
        """Check for proper blocking vs non-blocking assignments."""
        issues = []

        # Find clocked always blocks
        clocked_pattern = r'always\s*@\s*\([^)]*(?:posedge|negedge)[^)]*\)(.*?)(?=always|endmodule|$)'

        for match in re.finditer(clocked_pattern, code, re.IGNORECASE | re.DOTALL):
            block = match.group(1)
            start_pos = match.start(1)

            # Look for blocking assignments in clocked block
            for assign_match in re.finditer(r'(?<![=<>])=(?=[^=])', block):
                # Skip conditions inside if statements
                line_start = block.rfind('\n', 0, assign_match.start())
                line = block[line_start:assign_match.start()].strip()

                if not line.startswith('if') and not line.startswith('else'):
                    abs_pos = start_pos + assign_match.start()
                    line_number = code[:abs_pos].count('\n') + 1

                    issues.append(LintIssue(
                        severity='warning',
                        rule_id='BLOCKING_IN_CLOCKED',
                        message='Blocking assignment (=) in clocked always block',
                        line_number=line_number,
                        suggestion='Use non-blocking assignment (<=) for sequential logic'
                    ))

        return issues

    def _check_full_case(self, code: str) -> List[LintIssue]:
        """Check for full case statements."""
        issues = []

        # Find case statements
        case_pattern = r'case[zx]?\s*\([^)]+\)(.*?)(?=endcase)'

        for match in re.finditer(case_pattern, code, re.IGNORECASE | re.DOTALL):
            case_block = match.group(1)
            line_number = code[:match.start()].count('\n') + 1

            # Check for default case
            if not re.search(r'default\s*:', case_block, re.IGNORECASE):
                issues.append(LintIssue(
                    severity='warning',
                    rule_id='NO_DEFAULT_CASE',
                    message='Case statement without default case',
                    line_number=line_number,
                    suggestion='Add a default case to handle all input combinations'
                ))

        return issues

    def _check_synchronous_reset(self, code: str) -> List[LintIssue]:
        """Check reset usage patterns."""
        issues = []

        # Check for asynchronous reset pattern
        if re.search(r'always\s*@\s*\([^)]*posedge\s+\w+[^)]*or[^)]*\w+', code, re.IGNORECASE):
            # Has async reset - this is fine
            pass
        elif re.search(r'always\s*@\s*\([^)]*posedge\s+clk[^)]*\)', code, re.IGNORECASE):
            # Synchronous only - check for reset inside
            pass

        return issues

    def _check_unused_signals(self, code: str) -> List[LintIssue]:
        """Check for potentially unused signals."""
        issues = []

        # Find declared reg/wire signals
        signal_pattern = r'\b(?:reg|wire|logic)\s+(?:\[\d+:\d+\]\s+)?(\w+)'
        declared = set()

        for match in re.finditer(signal_pattern, code, re.IGNORECASE):
            signal_name = match.group(1)
            if signal_name not in ['module', 'endmodule']:
                declared.add(signal_name)

        # Find used signals (simplified)
        used = set()
        for match in re.finditer(r'\b(\w+)\b', code):
            word = match.group(1)
            if word in declared:
                used.add(word)

        # Check for declared but not used
        # This is a simplified check and may have false positives
        for signal in declared - used:
            if not signal.startswith('__'):  # Skip internal signals
                # Find declaration line
                for i, line in enumerate(code.split('\n'), 1):
                    if re.search(rf'\b{signal}\b', line):
                        issues.append(LintIssue(
                            severity='info',
                            rule_id='POTENTIALLY_UNUSED',
                            message=f'Signal "{signal}" may be unused',
                            line_number=i,
                            suggestion='Verify signal usage or remove if not needed'
                        ))
                        break

        return issues

    def _check_naming_conventions(self, code: str) -> List[LintIssue]:
        """Check naming conventions."""
        issues = []
        lines = code.split('\n')

        # Check module names (should be snake_case or PascalCase)
        for i, line in enumerate(lines, 1):
            match = re.search(r'module\s+(\w+)', line)
            if match:
                name = match.group(1)
                # Check for camelCase (mixed case without underscore)
                if re.match(r'^[a-z]+[A-Z]', name):
                    issues.append(LintIssue(
                        severity='info',
                        rule_id='NAMING_CONVENTION',
                        message=f'Module name "{name}" uses camelCase',
                        line_number=i,
                        suggestion='Use snake_case or PascalCase for module names'
                    ))

        return issues

    def _check_magic_numbers(self, code: str) -> List[LintIssue]:
        """Check for magic numbers."""
        issues = []

        # Find numeric literals that might be magic numbers
        # Skip common ones like 0, 1, power of 2 minus 1
        magic_pattern = r'(?<!\w)([2-9]\d?|[1-9]\d{2,})(?!\w)'

        for match in re.finditer(magic_pattern, code):
            line_number = code[:match.start()].count('\n') + 1
            number = match.group(1)

            # Skip if in a comment or if already defined as parameter
            line = code.split('\n')[line_number - 1]
            if '//' in line and line.index('//') < match.start() - code[:match.start()].rfind('\n'):
                continue

            # Skip power of 2 boundaries
            n = int(number)
            if n & (n - 1) == 0:  # Power of 2
                continue
            if n & (n + 1) == 0:  # Power of 2 minus 1
                continue

            issues.append(LintIssue(
                severity='info',
                rule_id='MAGIC_NUMBER',
                message=f'Magic number {number} detected',
                line_number=line_number,
                suggestion='Consider defining as a named parameter or localparam'
            ))

        return issues

    def _check_inferred_latches(self, code: str) -> List[LintIssue]:
        """Check for potential inferred latches."""
        issues = []

        # Find combinational always blocks
        pattern = r'always\s*@\s*\(\s*\*\s*\)(.*?)(?=always|endmodule|$)'

        for match in re.finditer(pattern, code, re.IGNORECASE | re.DOTALL):
            block = match.group(1)
            block_start = match.start(1)

            # Look for if statements without else
            if_match = re.search(r'if\s*\([^)]+\)\s*begin', block, re.IGNORECASE)
            if if_match:
                # Check if there's an else
                after_if = block[if_match.end():]
                if not re.search(r'\belse\b', after_if[:after_if.find('end')], re.IGNORECASE):
                    line_number = code[:block_start + if_match.start()].count('\n') + 1

                    issues.append(LintIssue(
                        severity='warning',
                        rule_id='POTENTIAL_LATCH',
                        message='If statement without else in combinational block may infer latch',
                        line_number=line_number,
                        suggestion='Add else clause or ensure all outputs assigned in all branches'
                    ))

        return issues

    def _check_multi_driver_reset(self, code: str) -> List[LintIssue]:
        """Check for multiple top-level reset branches in a single always block.

        Detects patterns like:
            always @(posedge clk or negedge rst_n) begin
                if (!rst_n) ...
                if (!rst_n) ...   // second reset branch — likely multi-driver bug
            end
        """
        issues = []

        # Match clocked always blocks with async reset
        block_pattern = re.compile(
            r'always\s*@\s*\([^)]*(?:posedge|negedge)\s+\w+[^)]*(?:or|,)[^)]*(?:posedge|negedge)\s+(\w+)[^)]*\)',
            re.IGNORECASE,
        )

        for block_match in block_pattern.finditer(code):
            reset_sig = block_match.group(1)
            block_start = block_match.end()

            # Find the extent of this always block (up to next always/endmodule)
            rest = code[block_start:]
            block_end_match = re.search(r'\b(?:always\b|endmodule\b)', rest)
            block_body = rest[:block_end_match.start()] if block_end_match else rest

            # Count top-level `if (!rst_n)` or `if (rst_n == 0)` occurrences
            reset_if_pattern = re.compile(
                rf'(?:^|\n)\s*if\s*\(\s*!{re.escape(reset_sig)}\s*\)'
                rf'|(?:^|\n)\s*if\s*\(\s*{re.escape(reset_sig)}\s*==\s*[01]\s*\)',
                re.IGNORECASE,
            )
            reset_ifs = list(reset_if_pattern.finditer(block_body))

            if len(reset_ifs) > 1:
                abs_pos = block_start + reset_ifs[1].start()
                line_number = code[:abs_pos].count('\n') + 1
                issues.append(LintIssue(
                    severity='error',
                    rule_id='MULTI_RESET_BRANCH',
                    message=f'Multiple top-level reset branches for "{reset_sig}" in one always block',
                    line_number=line_number,
                    suggestion='Merge reset logic into a single if/else-if chain to avoid multi-driver conflicts',
                ))

        return issues

    def _check_unpacked_array_port(self, code: str) -> List[LintIssue]:
        """Check for unpacked array port declarations (Yosys-incompatible).

        Detects patterns like:
            input [127:0] data [0:9]
            output [7:0] result [3:0]
        """
        issues = []

        # Pattern: direction [packed_range] name [unpacked_range]
        pattern = re.compile(
            r'\b(input|output|inout)\s+'
            r'(?:reg\s+|wire\s+)?'
            r'\[\s*\d+\s*:\s*\d+\s*\]\s+'
            r'(\w+)\s*'
            r'\[\s*\d+\s*:\s*\d+\s*\]',
            re.IGNORECASE,
        )

        for match in pattern.finditer(code):
            line_number = code[:match.start()].count('\n') + 1
            port_name = match.group(2)
            issues.append(LintIssue(
                severity='warning',
                rule_id='UNPACKED_ARRAY_PORT',
                message=f'Unpacked array port "{port_name}" is not supported by Yosys',
                line_number=line_number,
                suggestion='Use a flat bus instead: [N*W-1:0] name',
            ))

        return issues

    # ── v3.2 rules — real-project bug patterns ───────────────────────

    def _check_reg_driven_by_assign(self, code: str) -> List[LintIssue]:
        """Detect reg signals driven by continuous assign (Bug #1 pattern).

        In Verilog-2005, `assign` targets must be `wire`. A `reg` driven by
        `assign` causes iverilog error and is always a design mistake.
        """
        issues = []
        reg_names: Dict[str, int] = {}
        for i, line in enumerate(code.split('\n'), 1):
            stripped = line.strip()
            if stripped.startswith('//'):
                continue
            for m in re.finditer(r'\breg\b\s+(?:signed\s+)?(?:\[[^\]]*\]\s+)?(\w+)', stripped):
                reg_names[m.group(1)] = i

        for m in re.finditer(r'\bassign\s+(\w+)', code):
            sig = m.group(1)
            if sig in reg_names:
                line_number = code[:m.start()].count('\n') + 1
                issues.append(LintIssue(
                    severity='error',
                    rule_id='REG_DRIVEN_BY_ASSIGN',
                    message=f'Signal "{sig}" declared as reg (line {reg_names[sig]}) but driven by assign',
                    line_number=line_number,
                    suggestion=f'Change "reg" to "wire" for "{sig}", or use an always block instead of assign',
                ))
        return issues

    def _check_forward_reference(self, code: str) -> List[LintIssue]:
        """Detect signals used before declaration (Bug #6 pattern).

        iverilog -g2005 enforces strict declaration-before-use.
        """
        issues = []
        lines = code.split('\n')
        decl_line: Dict[str, int] = {}
        decl_re = re.compile(
            r'\b(?:wire|reg|integer|localparam|parameter|genvar)\b'
            r'\s+(?:signed\s+)?(?:\[[^\]]*\]\s+)?(\w+)'
        )
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('`'):
                continue
            for m in decl_re.finditer(stripped):
                name = m.group(1)
                if name not in decl_line:
                    decl_line[name] = i

        _KEYWORDS = {'and', 'or', 'not', 'xor', 'nand', 'nor', 'xnor',
                     'if', 'else', 'begin', 'end', 'wire', 'reg'}
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith('//'):
                continue
            if not re.match(r'\bassign\b', stripped):
                continue
            assign_m = re.match(r'assign\s+\w+\s*=\s*(.+);', stripped)
            if not assign_m:
                continue
            rhs = assign_m.group(1)
            for ident_m in re.finditer(r'\b([a-zA-Z_]\w*)\b', rhs):
                name = ident_m.group(1)
                if name in _KEYWORDS:
                    continue
                if name in decl_line and decl_line[name] > i:
                    issues.append(LintIssue(
                        severity='error',
                        rule_id='FORWARD_REFERENCE',
                        message=f'Signal "{name}" used on line {i} before declaration on line {decl_line[name]}',
                        line_number=i,
                        suggestion=f'Move the declaration of "{name}" before line {i}',
                    ))
        return issues

    def _check_nba_as_combinational(self, code: str) -> List[LintIssue]:
        """Detect non-blocking assignment consumed combinationally in same block (Bug #3).

        `sig <= expr;` then `... = ... + sig` in the same clocked always block
        reads the PREVIOUS cycle's value — almost always a bug.
        """
        issues = []
        clocked_re = re.compile(
            r'always\s*@\s*\([^)]*(?:posedge|negedge)[^)]*\)(.*?)(?=\balways\b|\bendmodule\b|$)',
            re.IGNORECASE | re.DOTALL,
        )
        for block_m in clocked_re.finditer(code):
            block = block_m.group(1)
            block_start = block_m.start(1)
            nba_targets: set = set()
            for nba_m in re.finditer(r'(\w+)\s*<=\s*', block):
                nba_targets.add(nba_m.group(1))
            for ba_m in re.finditer(r'(\w+)\s*=\s*([^;]+);', block):
                lhs = ba_m.group(1)
                rhs = ba_m.group(2)
                for target in nba_targets:
                    if target == lhs:
                        continue
                    if re.search(rf'\b{re.escape(target)}\b', rhs):
                        abs_pos = block_start + ba_m.start()
                        line_number = code[:abs_pos].count('\n') + 1
                        issues.append(LintIssue(
                            severity='warning',
                            rule_id='NBA_AS_COMBINATIONAL',
                            message=f'Signal "{target}" written with <= but read combinationally (=) in same block',
                            line_number=line_number,
                            suggestion=f'Use a combinational wire for "{target}" or restructure the pipeline staging',
                        ))
        return issues

    def _check_multi_driver_conflict(self, code: str) -> List[LintIssue]:
        """Detect signals driven by both always blocks and assign statements (Bug #7).

        A signal can only have ONE driver type — either always (reg) or assign (wire).
        """
        issues = []
        lines = code.split('\n')
        always_driven: Dict[str, int] = {}
        in_always = False
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if re.match(r'always\s*@', stripped):
                in_always = True
            if in_always:
                for m in re.finditer(r'(\w+)\s*<?=\s*', stripped):
                    sig = m.group(1)
                    if sig not in ('if', 'else', 'case', 'begin', 'end',
                                   'for', 'while', 'assign'):
                        if sig not in always_driven:
                            always_driven[sig] = i
            if re.match(r'\bendmodule\b', stripped):
                in_always = False

        assign_driven: Dict[str, int] = {}
        for i, line in enumerate(lines, 1):
            m = re.match(r'\s*assign\s+(\w+)', line)
            if m:
                assign_driven[m.group(1)] = i

        for sig in set(always_driven) & set(assign_driven):
            issues.append(LintIssue(
                severity='error',
                rule_id='MULTI_DRIVER_CONFLICT',
                message=f'Signal "{sig}" driven by both always (line {always_driven[sig]}) and assign (line {assign_driven[sig]})',
                line_number=assign_driven[sig],
                suggestion=f'Use only one driver type for "{sig}": either always block (reg) or assign (wire)',
            ))
        return issues

    def _check_axis_handshake_pulse(self, code: str) -> List[LintIssue]:
        """Detect AXI-Stream valid pulsed without checking ready (Bug #5).

        AXI-Stream requires valid held HIGH until ready acknowledges.
        Pulsing valid for one cycle without checking ready loses data.
        """
        issues = []
        lines = code.split('\n')
        valid_sigs = set()
        for line in lines:
            for m in re.finditer(r'(\w*(?:valid|tvalid)\w*)', line, re.IGNORECASE):
                valid_sigs.add(m.group(1))
        if not valid_sigs:
            return issues

        for sig in valid_sigs:
            clear_lines = []
            for i, line in enumerate(lines, 1):
                if re.search(rf'\b{re.escape(sig)}\s*<=\s*(?:1\'b)?0\s*;', line.strip()):
                    clear_lines.append(i)
            ready_sig = sig.replace('valid', 'ready').replace('tvalid', 'tready')
            for cl in clear_lines:
                ctx_start = max(0, cl - 6)
                context = '\n'.join(lines[ctx_start:cl])
                if not re.search(rf'\b{re.escape(ready_sig)}\b', context):
                    issues.append(LintIssue(
                        severity='warning',
                        rule_id='AXIS_HANDSHAKE_PULSE',
                        message=f'"{sig}" cleared without checking "{ready_sig}" — data may be lost',
                        line_number=cl,
                        suggestion=f'Hold "{sig}" high until "{ready_sig}" acknowledges',
                    ))
        return issues
