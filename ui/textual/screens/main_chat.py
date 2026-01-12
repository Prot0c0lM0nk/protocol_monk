# ui/textual/screens/main_chat.py

from textual.screen import Screen
from textual.widgets import Header, Footer
from ..widgets.chat_area import ChatArea
from ..widgets.input_bar import InputBar
from ..widgets.status_bar import StatusBar # Placeholder import for now

class MainChatScreen(Screen):
    def compose(self):
        # We can add a custom StatusBar later, using Header for now if you prefer
        yield Header() 
        yield ChatArea()
        yield InputBar()
        yield Footer()