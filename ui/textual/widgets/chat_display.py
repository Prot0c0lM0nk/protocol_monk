from textual.widgets import RichLog
from rich.markdown import Markdown

class ChatDisplay(RichLog):
    """
    A read-only log that renders Markdown and colored agent responses.
    """
    
    def __init__(self):
        # markup=True allows us to use [bold red] tags
        super().__init__(highlight=True, markup=True)

    def add_user_message(self, text: str):
        self.write("")  # Spacer
        self.write(f"[bold #ffaa44]User:[/]") 
        self.write(text)
        self.write("")

    def add_agent_message(self, text: str):
        # We can render simple text or full Markdown here
        self.write(text)
        
    def add_tool_result(self, tool_name: str, output: str):
        self.write(f"[bold #00d7ff]--- Tool: {tool_name} ---[/]")
        self.write(f"[dim]{output}[/]")
        self.write("[bold #00d7ff]-------------------------[/]")