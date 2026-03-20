import subprocess
from typing import Any, Dict, List, Optional, Sequence, Tuple

from protocol_monk.config.settings import Settings
from protocol_monk.exceptions.tools import ToolError
from protocol_monk.tools.base import BaseTool
from protocol_monk.tools.output_contract import build_git_operation_output
from protocol_monk.tools.shell_operations.process_runner import run_exec_command


class GitOperationTool(BaseTool):
    """Tool for executing specific git operations."""

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self.working_dir = settings.workspace_root
        self._git_commands = {
            "status": ["git", "status", "--porcelain=v1", "--branch"],
            "add": ["git", "add", "."],
            "commit": ["git", "commit", "-m", "AI assistant changes"],
            "push": ["git", "push"],
            "pull": ["git", "pull"],
            "log": [
                "git",
                "log",
                "-10",
                "--date=iso-strict",
                "--pretty=format:%H%x1f%h%x1f%s%x1f%an%x1f%aI",
            ],
        }

    @property
    def name(self) -> str:
        return "git_operation"

    @property
    def description(self) -> str:
        return "Execute git operations (status, add, commit, push, pull, log)"

    @property
    def parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": list(self._git_commands.keys()),
                    "description": "Git operation to perform",
                },
                "commit_message": {
                    "type": "string",
                    "description": "Message for commit operation",
                    "default": "AI assistant changes",
                },
            },
            "required": ["operation"],
        }

    async def run(self, **kwargs) -> Any:
        operation = kwargs.get("operation")
        commit_msg = kwargs.get("commit_message")

        if operation not in self._git_commands:
            raise ToolError(
                f"Unknown operation '{operation}'",
                user_hint=f"Unknown git operation '{operation}'.",
                details={"operation": operation},
            )

        command = self._git_commands[operation].copy()
        if operation == "commit" and commit_msg:
            command[-1] = commit_msg

        before_state = await self._capture_before_state(operation)

        try:
            result = await self._run_git(command, timeout=60)

            if result.returncode != 0:
                raise ToolError(
                    f"Git command failed with exit code {result.returncode}",
                    user_hint=f"Git {operation} failed (exit {result.returncode}).",
                    details={
                        "operation": operation,
                        "command": command,
                        "exit_code": result.returncode,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                    },
                )

            git_result, summary = await self._build_git_result(
                operation=operation,
                primary_result=result,
                before_state=before_state,
            )

            return build_git_operation_output(
                summary=summary,
                operation=operation,
                command=command,
                cwd=str(self.working_dir),
                exit_code=result.returncode,
                git_result=git_result,
                stdout=result.stdout,
                stderr=result.stderr,
            )

        except Exception as e:
            if isinstance(e, ToolError):
                raise
            raise ToolError(
                f"Git Error: {str(e)}",
                user_hint=f"Git {operation} failed unexpectedly.",
                details={"operation": operation, "error": str(e)},
            )

    async def _build_git_result(
        self,
        *,
        operation: str,
        primary_result: subprocess.CompletedProcess[str],
        before_state: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], str]:
        if operation == "status":
            git_result = self._parse_status_output(primary_result.stdout)
            changed_files = len(git_result["files"])
            branch_name = git_result["branch"]["name"] or "unknown"
            if git_result["working_tree"]["clean"]:
                summary = f"Repository is clean on branch {branch_name}."
            else:
                summary = (
                    f"Repository status includes {changed_files} changed files on branch "
                    f"{branch_name}."
                )
            return git_result, summary

        if operation == "log":
            commits = self._parse_log_output(primary_result.stdout)
            return (
                {"commits": commits},
                f"Retrieved {len(commits)} recent commits from git log.",
            )

        if operation == "add":
            staged_files = self._parse_name_status_output(
                await self._optional_stdout(
                    ["git", "diff", "--cached", "--name-status", "-M"]
                )
            )
            staged_count = len(staged_files)
            return (
                {
                    "staged_count": staged_count,
                    "staged_files": staged_files,
                },
                f"Staged {staged_count} files with git add.",
            )

        if operation == "commit":
            commit_record = await self._get_commit_record("HEAD")
            stats = await self._get_commit_stats("HEAD")
            short_hash = commit_record.get("short_hash") if commit_record else None
            subject = commit_record.get("subject") if commit_record else None
            summary = (
                f"Created commit {short_hash}: {subject}."
                if short_hash and subject
                else "Created a git commit."
            )
            return (
                {
                    "commit": commit_record,
                    "stats": stats,
                },
                summary,
            )

        if operation == "pull":
            git_result = await self._build_pull_result(before_state)
            if git_result["updated"]:
                summary = f"Pulled updates for {git_result['branch'] or 'current branch'}."
            else:
                summary = "Git pull completed without changing HEAD."
            return git_result, summary

        if operation == "push":
            git_result = await self._build_push_result(before_state)
            if git_result["updated_remote"] is True:
                summary = (
                    f"Pushed {git_result['branch'] or 'current branch'} to "
                    f"{git_result['remote'] or 'remote'}."
                )
            else:
                summary = "Git push completed."
            return git_result, summary

        return {}, f"Completed git {operation}."

    async def _capture_before_state(self, operation: str) -> Dict[str, Any]:
        state: Dict[str, Any] = {}
        if operation not in {"pull", "push"}:
            return state

        branch = await self._get_current_branch()
        upstream = await self._get_upstream_ref()
        remote, remote_branch = self._split_upstream_ref(upstream)
        state.update(
            {
                "branch": branch,
                "upstream": upstream,
                "before_head": await self._get_head_commit(),
                "remote": remote,
                "remote_branch": remote_branch or branch,
            }
        )

        if operation == "push":
            state["before_remote_head"] = await self._get_remote_head(
                remote,
                remote_branch or branch,
            )

        return state

    async def _build_pull_result(self, before_state: Dict[str, Any]) -> Dict[str, Any]:
        before_head = before_state.get("before_head")
        after_head = await self._get_head_commit()
        upstream = before_state.get("upstream") or await self._get_upstream_ref()
        remote, upstream_branch = self._split_upstream_ref(upstream)
        branch = before_state.get("branch") or await self._get_current_branch()
        observed_branch = branch or upstream_branch
        conflicts = await self._has_unmerged_paths()

        updated: Optional[bool]
        if before_head is None and after_head is None:
            updated = None
        else:
            updated = before_head != after_head

        fast_forward: Optional[bool]
        if updated is False:
            fast_forward = False
        elif before_head and after_head:
            fast_forward = await self._is_ancestor(before_head, after_head)
        else:
            fast_forward = None

        return {
            "remote": remote,
            "branch": observed_branch,
            "before_head": before_head,
            "after_head": after_head,
            "updated": updated,
            "fast_forward": fast_forward,
            "conflicts": conflicts,
        }

    async def _build_push_result(self, before_state: Dict[str, Any]) -> Dict[str, Any]:
        upstream = before_state.get("upstream") or await self._get_upstream_ref()
        remote, upstream_branch = self._split_upstream_ref(upstream)
        branch = (
            before_state.get("branch")
            or await self._get_current_branch()
            or upstream_branch
        )
        observed_remote_branch = before_state.get("remote_branch") or upstream_branch or branch
        before_remote_head = before_state.get("before_remote_head")
        pushed_head = await self._get_head_commit()
        after_remote_head = await self._get_remote_head(remote, observed_remote_branch)

        if pushed_head is None or after_remote_head is None:
            updated_remote: Optional[bool] = None
        else:
            updated_remote = after_remote_head == pushed_head

        if remote is None or observed_remote_branch is None:
            new_remote_branch: Optional[bool] = None
        else:
            new_remote_branch = before_remote_head is None and after_remote_head is not None

        return {
            "remote": remote,
            "branch": branch,
            "pushed_head": pushed_head,
            "updated_remote": updated_remote,
            "new_remote_branch": new_remote_branch,
        }

    async def _run_git(
        self,
        command: Sequence[str],
        *,
        timeout: int = 30,
    ) -> subprocess.CompletedProcess[str]:
        result = await run_exec_command(
            list(command),
            cwd=self.working_dir,
            timeout_seconds=timeout,
        )
        return subprocess.CompletedProcess(
            args=list(command),
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    async def _optional_stdout(
        self,
        command: Sequence[str],
        *,
        timeout: int = 30,
    ) -> str:
        try:
            result = await self._run_git(command, timeout=timeout)
        except Exception:
            return ""
        if result.returncode != 0:
            return ""
        return result.stdout

    async def _get_head_commit(self) -> Optional[str]:
        result = await self._optional_stdout(["git", "rev-parse", "HEAD"])
        head = result.strip()
        return head or None

    async def _get_current_branch(self) -> Optional[str]:
        branch = (await self._optional_stdout(["git", "branch", "--show-current"])).strip()
        return branch or None

    async def _get_upstream_ref(self) -> Optional[str]:
        upstream = (
            await self._optional_stdout(
            ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"]
            )
        ).strip()
        return upstream or None

    def _split_upstream_ref(self, upstream: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
        if not upstream or "/" not in upstream:
            return None, None
        remote, branch = upstream.split("/", 1)
        return remote or None, branch or None

    async def _get_remote_head(
        self, remote: Optional[str], branch: Optional[str]
    ) -> Optional[str]:
        if not remote or not branch:
            return None
        output = await self._optional_stdout(
            ["git", "ls-remote", "--heads", remote, f"refs/heads/{branch}"],
            timeout=60,
        )
        line = next((raw for raw in output.splitlines() if raw.strip()), "")
        if not line:
            return None
        return line.split()[0]

    async def _has_unmerged_paths(self) -> Optional[bool]:
        output = await self._optional_stdout(
            ["git", "diff", "--name-only", "--diff-filter=U"]
        )
        if output == "":
            return False
        return bool(output.splitlines())

    async def _is_ancestor(self, ancestor: str, descendant: str) -> Optional[bool]:
        if not ancestor or not descendant:
            return None
        try:
            result = await self._run_git(
                ["git", "merge-base", "--is-ancestor", ancestor, descendant],
                timeout=30,
            )
        except Exception:
            return None
        if result.returncode == 0:
            return True
        if result.returncode == 1:
            return False
        return None

    def _parse_status_output(self, stdout: str) -> Dict[str, Any]:
        branch = {
            "name": None,
            "detached": False,
            "upstream": None,
            "ahead": 0,
            "behind": 0,
        }
        files: List[Dict[str, Any]] = []

        for line in str(stdout or "").splitlines():
            if line.startswith("## "):
                branch = self._parse_branch_header(line[3:])
                continue
            file_entry = self._parse_status_line(line)
            if file_entry is not None:
                files.append(file_entry)

        return {
            "branch": branch,
            "working_tree": {
                "clean": len(files) == 0,
                "staged_count": sum(1 for item in files if item["staged"]),
                "unstaged_count": sum(1 for item in files if item["unstaged"]),
                "untracked_count": sum(1 for item in files if item["untracked"]),
            },
            "files": files,
        }

    def _parse_branch_header(self, header: str) -> Dict[str, Any]:
        branch = {
            "name": None,
            "detached": False,
            "upstream": None,
            "ahead": 0,
            "behind": 0,
        }
        raw_header = str(header or "").strip()

        if raw_header.startswith("No commits yet on "):
            branch["name"] = raw_header.removeprefix("No commits yet on ").strip() or None
            return branch

        if raw_header.startswith("HEAD ("):
            branch["name"] = "HEAD"
            branch["detached"] = True
            return branch

        ref_part = raw_header
        detail_part = ""
        if " [" in raw_header and raw_header.endswith("]"):
            ref_part, detail_part = raw_header.rsplit(" [", 1)
            detail_part = detail_part[:-1]

        if "..." in ref_part:
            branch_name, upstream = ref_part.split("...", 1)
            branch["name"] = branch_name.strip() or None
            branch["upstream"] = upstream.strip() or None
        else:
            branch["name"] = ref_part.strip() or None

        for token in detail_part.split(","):
            token = token.strip()
            if token.startswith("ahead "):
                branch["ahead"] = int(token.split(" ", 1)[1])
            elif token.startswith("behind "):
                branch["behind"] = int(token.split(" ", 1)[1])

        return branch

    def _parse_status_line(self, line: str) -> Optional[Dict[str, Any]]:
        raw_line = str(line or "")
        if len(raw_line) < 3:
            return None

        status = raw_line[:2]
        path_part = raw_line[3:]
        if not path_part:
            return None

        if status == "??":
            return {
                "path": path_part,
                "change_type": "untracked",
                "staged": False,
                "unstaged": False,
                "untracked": True,
                "renamed_from": None,
            }

        renamed_from = None
        path = path_part
        if " -> " in path_part and ("R" in status or "C" in status):
            renamed_from, path = path_part.split(" -> ", 1)

        staged = status[0] not in {" ", "?", "!"}
        unstaged = status[1] not in {" ", "?", "!"}

        return {
            "path": path,
            "change_type": self._status_code_to_change_type(status[0], status[1]),
            "staged": staged,
            "unstaged": unstaged,
            "untracked": False,
            "renamed_from": renamed_from,
        }

    def _status_code_to_change_type(self, first: str, second: str) -> str:
        if first == "?" and second == "?":
            return "untracked"
        if first == "!" and second == "!":
            return "ignored"
        if (
            first == "U"
            or second == "U"
            or (first == "A" and second == "A")
            or (first == "D" and second == "D")
        ):
            return "unmerged"

        mapping = {
            "M": "modified",
            "A": "added",
            "D": "deleted",
            "R": "renamed",
            "C": "copied",
            "T": "type_changed",
        }
        for code in (first, second):
            if code in mapping:
                return mapping[code]
        return "unknown"

    def _parse_log_output(self, stdout: str) -> List[Dict[str, Any]]:
        commits: List[Dict[str, Any]] = []
        for line in str(stdout or "").splitlines():
            if not line.strip():
                continue
            parts = line.split("\x1f")
            if len(parts) != 5:
                continue
            commits.append(
                {
                    "hash": parts[0],
                    "short_hash": parts[1],
                    "subject": parts[2],
                    "author_name": parts[3],
                    "authored_at": parts[4],
                }
            )
        return commits

    def _parse_name_status_output(self, stdout: str) -> List[Dict[str, Any]]:
        files: List[Dict[str, Any]] = []
        for line in str(stdout or "").splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            code = parts[0]
            renamed_from = parts[1] if code.startswith(("R", "C")) and len(parts) > 2 else None
            path = parts[2] if renamed_from is not None else parts[1]
            files.append(
                {
                    "path": path,
                    "change_type": self._name_status_code_to_change_type(code),
                    "renamed_from": renamed_from,
                }
            )
        return files

    def _name_status_code_to_change_type(self, code: str) -> str:
        if not code:
            return "unknown"
        return self._status_code_to_change_type(code[0], " ")

    async def _get_commit_record(self, rev: str) -> Optional[Dict[str, Any]]:
        output = (
            await self._optional_stdout(
            [
                "git",
                "show",
                "-s",
                "--date=iso-strict",
                "--format=%H%x1f%h%x1f%s%x1f%an%x1f%aI",
                rev,
            ]
            )
        ).strip()
        if not output:
            return None
        parts = output.split("\x1f")
        if len(parts) != 5:
            return None
        return {
            "hash": parts[0],
            "short_hash": parts[1],
            "subject": parts[2],
            "author_name": parts[3],
            "authored_at": parts[4],
        }

    async def _get_commit_stats(self, rev: str) -> Dict[str, int]:
        output = await self._optional_stdout(["git", "show", "--format=", "--numstat", rev])
        files_changed = 0
        insertions = 0
        deletions = 0

        for line in output.splitlines():
            parts = line.split("\t", 2)
            if len(parts) != 3:
                continue
            files_changed += 1
            added, removed = parts[0], parts[1]
            if added.isdigit():
                insertions += int(added)
            if removed.isdigit():
                deletions += int(removed)

        return {
            "files_changed": files_changed,
            "insertions": insertions,
            "deletions": deletions,
        }
