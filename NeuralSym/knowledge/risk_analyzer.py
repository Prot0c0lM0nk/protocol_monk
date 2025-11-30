"""
Predictive failure analysis and verification suggestions.

Analyzes historical failures and current assumptions to anticipate risks.
"""

from collections import deque

import ast
import re
import time
from typing import Any, Dict, List, Tuple

from .base import EvidenceStrength, Fact, FactStatus


class RiskAnalyzer:
    """Predictive risk analysis based on historical evidence."""

    def __init__(self, facts, fact_index):
        self._facts = facts
        self._fact_index = fact_index
        # Failure embeddings for Pattern Analyzer clustering
        self._failure_embeddings: deque = deque(maxlen=10_000)

    def should_retry(self, tool_name: str, arguments: dict) -> Tuple[bool, str]:
        """Determine if a tool should be retried based on recent failures.

        Args:
            tool_name: Name of the tool to check
            arguments: Arguments that were passed to the tool

        Returns:
            Tuple of (should_retry: bool, reason: str)
        """
        # Simple implementation for now: allow retry unless recent repeated failures
        failures = [
            f
            for f in self._facts.values()
            if f.status == FactStatus.REFUTED
            and isinstance(f.value, dict)
            and f.value.get("tool") == tool_name
        ]
        if len(failures) >= 3:
            return False, f"Too many recent failures ({len(failures)}) for {tool_name}"
        return True, "No recent failures found"

    def record_failure_embedding(
        self, tool_name: str, arguments: dict, error_message: str
    ) -> None:
        """Record vectorized failure representation for Pattern Analyzer clustering."""
        failure_vec = {
            "tool": tool_name,
            "arg_keys": sorted(arguments.keys()) if arguments else [],
            "error_type": (
                error_message.split(":")[0]
                if ":" in error_message
                else error_message[:50]
            ),
            "timestamp": time.time(),
        }
        self._failure_embeddings.append(failure_vec)

    def _get_relevant_fact_types(self, intent: str) -> List[str]:
        """Get relevant fact types based on the intent.

        Args:
            intent: The intent string to analyze

        Returns:
            List of relevant fact types
        """
        intent_map = {
            "FILE_READ_INTENT": ["file_exists", "file_permissions", "file_location"],
            "FILE_WRITE_INTENT": [
                "file_exists",
                "directory_exists",
                "write_permissions",
            ],
            "FILE_SEARCH_INTENT": [
                "directory_structure",
                "file_location",
                "search_path",
            ],
            "COMMAND_EXECUTION_INTENT": [
                "command_available",
                "dependencies_installed",
                "environment_ready",
            ],
            "CODE_ANALYSIS_INTENT": [
                "file_exists",
                "syntax_valid",
                "dependencies_resolved",
            ],
            "CODE_WRITE_INTENT": [
                "file_exists",
                "backup_exists",
                "syntax_valid",
                "write_permissions",
            ],
            "PACKAGE_INSTALL_INTENT": [
                "package_available",
                "dependencies_compatible",
                "environment_ready",
                "network_available",
            ],
        }
        return intent_map.get(intent, [])

    def relevant_context(self, intent: str) -> Dict[str, Any]:
        """Extract relevant context information based on the intent.

        Maps intents to relevant fact types and returns current state,
        potential issues, known failures, and verified assumptions.

        Args:
            intent: The intent string to analyze

        Returns:
            Dictionary containing context information with keys:
            - current_state: Verified facts relevant to the intent
            - potential_issues: Assumed/uncertain facts
            - known_failures: Recent refuted facts
            - verified_assumptions: High-confidence verified facts
        """
        relevant_types = self._get_relevant_fact_types(intent)
        
        # Initialize context
        context = {
            "current_state": {},
            "potential_issues": [],
            "known_failures": [],
            "verified_assumptions": [],
        }
        
        # Populate current verified state
        for ft in relevant_types:
            facts = [
                f
                for f in self._facts.values()
                if f.fact_type == ft and f.status == FactStatus.VERIFIED
            ]
            if facts:
                latest = max(facts, key=lambda f: f.updated_at)
                context["current_state"][ft] = latest.value
        
        # Populate potential issues (assumed/uncertain)
        for fact in self._facts.values():
            if fact.status in (FactStatus.ASSUMED, FactStatus.UNCERTAIN):
                context["potential_issues"].append(
                    {
                        "type": fact.fact_type,
                        "assumption": fact.value,
                        "confidence": fact.confidence,
                        "warning": f"Unverified: {fact.fact_type}",
                    }
                )
        
        # Populate recent failures
        refuted = [f for f in self._facts.values() if f.status == FactStatus.REFUTED]
        refuted.sort(key=lambda f: f.updated_at, reverse=True)
        for fact in refuted[:5]:
            if isinstance(fact.value, dict):
                context["known_failures"].append(
                    {
                        "tool": fact.value.get("tool", "unknown"),
                        "reason": fact.value.get("reason", ""),
                        "args": fact.value.get("args", {}),
                    }
                )
        
        # Populate verified assumptions (high-confidence)
        verified = [f for f in self._facts.values() if f.status == FactStatus.VERIFIED]
        verified.sort(key=lambda f: f.confidence, reverse=True)
        for fact in verified[:3]:
            context["verified_assumptions"].append(
                {
                    "type": fact.fact_type,
                    "value": fact.value,
                    "confidence": fact.confidence,
                }
            )
        
        return context

    def _analyze_file_path_risks(
        self, tool_name: str, args: Dict[str, Any]
    ) -> List[str]:
        """Analyze risks related to file paths.

        Args:
            tool_name: Name of the tool being analyzed
            args: Arguments passed to the tool

        Returns:
            List of risk descriptions
        """
        risks = []

        # Check file path existence verification
        filepath_risks = self._check_file_path_verification(args)
        risks.extend(filepath_risks)

        # Check for similar failure patterns
        failure_risks = self._check_similar_file_failures(tool_name, args)
        risks.extend(failure_risks)

        return risks

    def _check_file_path_verification(self, args: Dict[str, Any]) -> List[str]:
        """Check if file path existence has been verified.

        Args:
            args: Arguments containing potential file paths

        Returns:
            List of risk descriptions
        """
        risks = []

        if "filepath" in args or "file" in args:
            filepath = args.get("filepath") or args.get("file", "")
            exists_facts = [
                f for f in self._facts.values() if f.fact_type == "file_exists"
            ]
            verified = any(
                f.value == filepath and f.status == FactStatus.VERIFIED
                for f in exists_facts
            )
            if not verified:
                risks.append(
                    f"File path assumption - '{filepath}' existence not verified"
                )

        return risks

    def _check_similar_file_failures(self, tool_name: str, args: Dict[str, Any]) -> List[str]:
        """Check for similar file path failure patterns.

        Args:
            tool_name: Name of the tool being analyzed
            args: Arguments containing potential file paths

        Returns:
            List of risk descriptions
        """
        risks = []

        if "filepath" in args or "file" in args:
            filepath = args.get("filepath") or args.get("file", "")
            similar_failures = [
                f
                for f in self._facts.values()
                if f.status == FactStatus.REFUTED
                and isinstance(f.value, dict)
                and f.value.get("tool") == tool_name
                and filepath in str(f.value.get("args", {}))
            ]
            if similar_failures:
                risks.append(
                    f"This file path failed {len(similar_failures)}x in recent attempts"
                )

        return risks

    def _analyze_tool_failure_patterns(self, tool_name: str) -> List[str]:
        """Analyze tool-specific failure patterns."""
        risks = []

        # Tool-specific failure patterns
        tool_failures = [
            f
            for f in self._facts.values()
            if f.status == FactStatus.REFUTED
            and isinstance(f.value, dict)
            and f.value.get("tool") == tool_name
        ]
        if len(tool_failures) >= 3:
            risks.append(f"Tool '{tool_name}' has {len(tool_failures)} recent failures")
            reasons = [f.value.get("reason", "") for f in tool_failures]
            if reasons:
                most_common = max(set(reasons), key=reasons.count)
                if reasons.count(most_common) >= 2:
                    risks.append(f"Common failure: {most_common}")

        return risks

    def _analyze_general_assumptions(self) -> List[str]:
        """Analyze general unverified assumptions."""
        risks = []

        # General assumed facts
        assumed_count = len(
            [f for f in self._facts.values() if f.status == FactStatus.ASSUMED]
        )
        if assumed_count:
            risks.append(f"{assumed_count} unverified assumptions in knowledge base")

        return risks

    def predict_failure_risks(self, proposed_action: str) -> List[str]:
        """Predict potential failure risks for a proposed action."""
        parts = self._parse_action(proposed_action)
        tool_name = parts.get("tool", "")
        args = parts.get("args", {})

        # Analyze different types of risks
        file_risks = self._analyze_file_path_risks(tool_name, args)
        tool_risks = self._analyze_tool_failure_patterns(tool_name)
        assumption_risks = self._analyze_general_assumptions()

        # Combine all risks
        risks = file_risks + tool_risks + assumption_risks

        return risks

    def suggest_verification_steps(self, proposed_action: str) -> List[str]:
        """Suggest verification steps for a proposed action.

        Based on the action's tool and arguments, generates a list of
        verification steps to prevent common failures.

        Args:
            proposed_action: String representation of the proposed action

        Returns:
            List of verification steps as strings
        """
        parts = self._parse_action(proposed_action)
        tool_name = parts.get("tool", "")
        args = parts.get("args", {})

        # Generate verification steps based on action type
        steps = []
        steps.extend(self._generate_file_verification_steps(args))
        steps.extend(self._generate_directory_verification_steps(args))
        steps.extend(self._generate_command_verification_steps(tool_name, args))
        
        # Add default steps if no specific ones were generated
        if not steps:
            steps.extend(self._generate_default_verification_steps())

        return steps

    def _generate_file_verification_steps(self, args: Dict[str, Any]) -> List[str]:
        """Generate verification steps for file-related actions.

        Args:
            args: Arguments that may contain file paths

        Returns:
            List of file verification steps
        """
        steps = []

        if "filepath" in args or "file" in args:
            filepath = args.get("filepath") or args.get("file", "")
            steps.append(f"1. Verify file exists: execute_command('ls {filepath}')")
            if "/" not in filepath:
                steps.append(
                    f"2. Search for file: execute_command('find . -name {filepath}')"
                )
            else:
                directory = "/".join(filepath.split("/")[:-1])
                steps.append(f"2. Verify directory: execute_command('ls {directory}')")

        return steps

    def _generate_directory_verification_steps(self, args: Dict[str, Any]) -> List[str]:
        """Generate verification steps for directory-related actions.

        Args:
            args: Arguments that may contain directory paths

        Returns:
            List of directory verification steps
        """
        steps = []

        if "directory" in args or "dir" in args:
            directory = args.get("directory") or args.get("dir", "")
            steps.append(f"1. Verify directory: execute_command('ls {directory}')")
            steps.append(f"2. Check permissions: execute_command('ls -ld {directory}')")

        return steps

    def _generate_command_verification_steps(self, tool_name: str, args: Dict[str, Any]) -> List[str]:
        """Generate verification steps for command execution actions.

        Args:
            tool_name: Name of the tool being executed
            args: Arguments for the tool

        Returns:
            List of command verification steps
        """
        steps = []

        if tool_name == "execute_command":
            command = args.get("command", "") or args.get("filepath", "")
            cmd_name = command.split()[0] if command.split() else command
            if cmd_name:
                steps.append(
                    f"1. Verify command available: execute_command('which {cmd_name}')"
                )

        return steps

    def _generate_default_verification_steps(self) -> List[str]:
        """Generate default verification steps.

        Returns:
            List of default verification steps
        """
        return [
            "1. Verify current directory: execute_command('pwd')",
            "2. Review verified facts"
        ]

    # ---------- Internal ----------
    def _parse_action(self, action_str: str) -> Dict[str, Any]:
        """Parse action string using ast.literal_eval for robustness."""
        match = re.match(r"(\w+)\((.*)\)", action_str)
        if not match:
            return {"tool": action_str, "args": {}}

        tool_name = match.group(1)
        args_str = match.group(2).strip()
        args = {}

        # Try ast.literal_eval first for proper Python syntax
        try:
            # Wrap in dict call format for literal_eval
            if "=" in args_str:
                # keyword args: tool(a=1, b="x") -> dict(a=1, b="x")
                dict_str = f"dict({args_str})"
                args = ast.literal_eval(dict_str)
            elif args_str:
                # Single positional arg: tool("path") -> assume filepath
                value = ast.literal_eval(args_str)
                args["filepath"] = value
        except (SyntaxError, ValueError):
            # Fallback to regex parsing for malformed input
            for match in re.finditer(r'(\w+)\s*=\s*["\']([^"\']+) ["\']', args_str):
                key, value = match.groups()
                args[key] = value
            if not args and args_str:
                cleaned = args_str.strip("\"'")
                if cleaned:
                    args["filepath"] = cleaned

        return {"tool": tool_name, "args": args}
