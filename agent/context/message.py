import time
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass
class Message:
    """
    Represents a single message in the conversation.
    Updated to support Native Tool Calling fields.
    """

    role: str
    content: Optional[str] = None
    
    # Native Tool Calling Fields
    tool_calls: Optional[List[Dict[str, Any]]] = None  # For Assistant role
    tool_call_id: Optional[str] = None       # For Tool role
    name: Optional[str] = None               # For Tool role
    
    # Internal Metadata (Not sent to API)
    timestamp: float = field(default_factory=time.time)
    importance: int = 3
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to a dictionary strictly compliant with LLM API specs.
        Removes internal fields like metadata and timestamp.
        """
        msg = {"role": self.role}
        
        # Handle Content
        if self.content is not None:
            msg["content"] = self.content
        elif self.role == "assistant" and self.tool_calls:
            # Assistant with tools often has empty/null content
            msg["content"] = ""
            
        # Handle Tool Calls (Assistant)
        if self.role == "assistant" and self.tool_calls:
            msg["tool_calls"] = self.tool_calls
            
        # Handle Tool Results (Tool)
        if self.role == "tool":
            if self.tool_call_id:
                msg["tool_call_id"] = self.tool_call_id
            if self.name:
                msg["name"] = self.name
                
        return msg