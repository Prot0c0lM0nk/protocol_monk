#!/usr/bin/env python3
"""
Interfaces for Protocol Monk Agent-UI Separation
Defines contracts between layers without implementation details
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass


@dataclass
class CommandResult:
    """Result of executing a command"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None


@dataclass
class AgentResponse:
    """Response from agent processing"""
    type: str  # "text", "tool_calls", "error"
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class ToolExecutionRequest:
    """Request to execute a tool"""
    tool_name: str
    parameters: Dict[str, Any]
    tool_call_id: Optional[str] = None


@dataclass
class ToolExecutionResult:
    """Result of tool execution"""
    success: bool
    tool_name: str
    output: str
    error: Optional[str] = None
    tool_call_id: Optional[str] = None


@dataclass
class ToolResult:
    """Result of a tool execution"""
    success: bool
    output: str
    error: Optional[str] = None
    tool_name: Optional[str] = None

class AgentInterface(ABC):
    """Interface that UI layers can use to interact with agent"""

    @abstractmethod
    async def process_request(self, user_input: str) -> AgentResponse:
        """Process a user request and return response"""
        pass

    @abstractmethod
    async def execute_command(self, command: str, args: Dict[str, Any]) -> CommandResult:
        """Execute a slash command"""
        pass

    @abstractmethod
    async def execute_tool(self, tool_request: ToolExecutionRequest) -> ToolExecutionResult:
        """Execute a single tool with user approval"""
        pass

    @abstractmethod
    async def clear_conversation(self) -> None:
        """Clear conversation context"""
        pass

    @abstractmethod
    async def get_status(self) -> Dict[str, Any]:
        """Get current agent status"""
        pass


class UIEventHandler(ABC):
    """Interface that agent can use to handle UI events"""

    @abstractmethod
    async def handle_tool_confirmation(self, tool_request: ToolExecutionRequest) -> bool:
        """Handle tool execution confirmation"""
        pass

    @abstractmethod
    async def handle_tool_modification(self, tool_request: ToolExecutionRequest) -> ToolExecutionRequest:
        """Handle tool parameter modification"""
        pass


@dataclass
class UserInputRequest:
    """Request for user input"""
    prompt: str = "> "
    multiline: bool = False


@dataclass  
class UserInputResponse:
    """Response containing user input"""
    text: str
    cancelled: bool = False



class AgentInterface(ABC):
    """Interface that UI layers can use to interact with agent"""

    @abstractmethod
    async def get_user_input(self, request: UserInputRequest) -> UserInputResponse:
        """Get user input"""
        pass