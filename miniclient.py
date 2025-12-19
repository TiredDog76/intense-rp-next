import sys
import json
import asyncio
import httpx
import qasync
from PySide6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QWidget, 
                               QLabel, QLineEdit, QTextEdit, QPushButton, QCheckBox, QHBoxLayout)
from PySide6.QtCore import Slot

# This is just here to test the API server without needing a full-blown SillyTavern client.
# It sends requests to the local API server and displays responses.
# Just what we need, ain't it?

class MiniClient(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DeepSeek MiniClient")
        self.resize(600, 500)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        # API URL
        self.url_layout = QHBoxLayout()
        self.url_label = QLabel("API URL:")
        self.url_input = QLineEdit("http://localhost:8000/v1/chat/completions")
        self.url_layout.addWidget(self.url_label)
        self.url_layout.addWidget(self.url_input)
        self.layout.addLayout(self.url_layout)

        # Message Input
        self.message_label = QLabel("Message:")
        self.layout.addWidget(self.message_label)
        self.message_input = QTextEdit()
        self.message_input.setPlaceholderText("Enter your message here...")
        self.message_input.setMaximumHeight(100)
        self.layout.addWidget(self.message_input)

        # Options
        self.options_layout = QHBoxLayout()
        self.stream_checkbox = QCheckBox("Stream Response")
        self.stream_checkbox.setChecked(True)
        self.options_layout.addWidget(self.stream_checkbox)
        self.layout.addLayout(self.options_layout)

        # Send Button
        self.send_button = QPushButton("Send Request")
        self.send_button.clicked.connect(self.on_send_clicked)
        self.layout.addWidget(self.send_button)

        # Response Output
        self.response_label = QLabel("Response:")
        self.layout.addWidget(self.response_label)
        self.response_output = QTextEdit()
        self.response_output.setReadOnly(True)
        self.layout.addWidget(self.response_output)

    @Slot()
    def on_send_clicked(self):
        message = self.message_input.toPlainText()
        if not message:
            self.response_output.setText("Please enter a message.")
            return

        url = self.url_input.text()
        stream = self.stream_checkbox.isChecked()
        
        self.response_output.clear()
        self.send_button.setEnabled(False)
        self.response_output.append(f"Sending request to {url}...\n")

        asyncio.create_task(self.send_request(url, message, stream))

    async def send_request(self, url, message, stream):
        payload = {
            "messages": [{"role": "user", "content": message}],
            "stream": stream,
            "model": "deepseek-auto"
        }

        try:
            async with httpx.AsyncClient() as client:
                if stream:
                    async with client.stream("POST", url, json=payload, timeout=120.0) as response:
                        if response.status_code != 200:
                            self.response_output.append(f"Error: {response.status_code}\n")
                            return

                        async for line in response.aiter_lines():
                            if line.startswith("data: "):
                                data_str = line[6:].strip()
                                if data_str == "[DONE]":
                                    continue
                                try:
                                    data = json.loads(data_str)
                                    if "choices" in data and len(data["choices"]) > 0:
                                        delta = data["choices"][0].get("delta", {})
                                        if "content" in delta:
                                            self.response_output.insertPlainText(delta["content"])
                                            # Auto-scroll
                                            sb = self.response_output.verticalScrollBar()
                                            sb.setValue(sb.maximum())
                                except json.JSONDecodeError:
                                    pass
                else:
                    response = await client.post(url, json=payload, timeout=120.0)
                    if response.status_code == 200:
                        data = response.json()
                        if "choices" in data and len(data["choices"]) > 0:
                            content = data["choices"][0]["message"]["content"]
                            self.response_output.setText(content)
                    else:
                        self.response_output.setText(f"Error: {response.status_code}\n{response.text}")

        except Exception as e:
            self.response_output.append(f"\nError: {e}")
        finally:
            self.send_button.setEnabled(True)

def main():
    app = QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = MiniClient()
    window.show()

    with loop:
        loop.run_forever()

if __name__ == "__main__":
    main()
