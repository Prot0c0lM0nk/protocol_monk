# tools/_constants.py
"""
Tool Constants - Shared constants needed by tool base classes and specific tools.
Separated for clarity and to manage security patterns centrally.
"""

# File path security patterns (used by BaseTool)
DANGEROUS_FILE_PATTERNS = [
    # System directories (match as components)
    "/etc/",
    "/usr/",
    "/var/",
    "/root/",
    "/boot/",
    "/dev/",
    "/proc/",
    "/sys/",
    # Hidden system/config files/dirs (match anywhere in path)
    ".ssh/",
    ".bash",
    ".profile",
    ".bashrc",
    ".zshrc",
    ".vimrc",
    ".gitconfig",
    ".aws/",
    ".docker/",
    # Path traversal (match as component)
    "../",
    "..\\",
]

# Command security patterns (used by shell_operations tool)
DANGEROUS_COMMAND_PATTERNS = [
    # Destructive operations
    "rm -rf",
    "rm -fr",
    "rm -r /",
    "rm -rf /",
    "rmdir /s",
    "del /s",
    "format ",
    "fdisk",
    "mkfs",
    "dd ",
    "shred",
    "wipe",
    # System modification / Privilege Escalation
    "sudo",
    "su -",
    "chmod 777",
    "chmod +s",
    "chown",
    "passwd",
    "useradd",
    "userdel",
    "groupadd",
    "groupdel",
    "usermod",
    # Network operations (potential exfiltration or attack vectors)
    "wget",
    "curl http",
    "nc ",
    "netcat",
    "telnet",
    "ssh ",
    "scp ",
    "rsync",
    "ftp ",
    "sftp ",
    # Process/service control
    "kill -9",
    "killall",
    "pkill",
    "systemctl",
    "service ",
    "reboot",
    "shutdown",
    "halt",
    "poweroff",
    "init 0",
    "init 6",
    # Direct code execution / Command Injection Risks
    "eval",
    "exec",
    "python -c",
    "perl -e",
    "ruby -e",
    "php -r",
    "sh -c",
    "bash -c",
    "$(",
    "`",
    "source ",
    ". ",  # Shell source commands
    # Database operations (if shell access allows)
    "DROP TABLE",
    "DROP DATABASE",
    "DELETE FROM",
    "TRUNCATE TABLE",
    # Background/detached processes (can hide malicious activity)
    " &",
    "nohup",
    "disown",
    "screen -d",
    "tmux new",
    "at ",
    "batch",
    # Filesystem manipulation / Redirection to sensitive areas
    "> /dev/",
    ">> /dev/",
    "> /etc/",
    ">> /etc/",
    "> /root/",
    ">> /root/",
    "/dev/null",
    "/dev/zero",
    "/dev/random",
    "/dev/urandom",
    "mkfifo",
    "mknod",
    "mount",
    "umount",
    # Package managers (can install malicious code)
    "pip install",
    "npm install",
    "apt",
    "yum",
    "dnf",
    "brew install",
    "gem install",
    # Git operations (can pull malicious code or leak credentials)
    "git clone http",
    "git pull http",
    "git fetch http",  # Unencrypted
    # Be cautious even with https if the repo isn't trusted
    # Compiler/interpreter invocation with direct code
    "gcc -x c -",
    "g++ -x c++ -",
    "clang -x c -",  # Reading from stdin
    # History/logs manipulation
    "history -c",
    "> ~/.bash_history",
    "unset HISTFILE",
    "> /var/log",
]

# Python code security patterns (used by run_python tool)
DANGEROUS_PYTHON_PATTERNS = [
    # System access modules
    "import os",
    "import sys",
    "import subprocess",
    "import shutil",
    "import ctypes",
    "import _thread",
    "import threading",
    "from os import",
    "from sys import",
    "from subprocess import",
    "from shutil import",
    # Built-in functions for code execution/evaluation
    "__import__",
    "eval(",
    "exec(",
    "compile(",
    "breakpoint()",
    # File system access (writing, deleting, modifying outside allowed areas)
    "open(",
    "file(",
    "with open",  # Check mode later
    "pathlib",
    "glob.glob",  # Potentially dangerous listing
    "os.system",
    "os.popen",
    "os.spawn",
    "os.exec",
    "os.remove",
    "os.rmdir",
    "os.unlink",
    "os.makedirs",
    "os.chmod",
    "os.chown",
    "shutil.rmtree",
    "shutil.move",
    "shutil.copy",
    "shutil.copytree",
    "shutil.chown",
    # Network access modules
    "urllib",
    "requests",
    "http",
    "socket",
    "ftplib",
    "smtplib",
    "telnetlib",
    "asyncio",
    "aiohttp",
    "import urllib",
    "import requests",
    "import socket",
    # Process control / Exiting
    "subprocess.",
    "Popen",
    "call(",
    "check_call",
    "check_output",
    "run(",
    "sys.exit",
    "exit(",
    "quit()",
    "os._exit",
    "os.kill",
    "os.fork",
    "os.waitpid",
    # Dynamic imports / Module manipulation
    "importlib",
    "imp.",
    "pkgutil",
    "sys.modules",
    "setattr(",
    "getattr(",  # Can be used maliciously
    # Accessing sensitive information
    "os.environ",
    "os.getenv",  # Can leak keys
    "keyring",
]
