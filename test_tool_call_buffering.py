
import asyncio
import json
import logging
from unittest.mock import AsyncMock, MagicMock
from typing import AsyncGenerator, List

# Import our components
from agent.model_client import ModelClient
from utils.json_parser import extract_json_with_feedback

# Set up logging to see what's happening
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class ToolCallBufferingTests:
    """Test suite for tool call buffering functionality."""

    def __init__(self):
        self.test_results = []

    async def test_streaming_tool_call_breakup(self):
        """Test the most common scenario: tool call broken across streaming chunks."""
        logger.info("🧪 Test 1: Streaming Tool Call Breakup")

        # Simulate a streaming response that breaks up the tool call
        broken_chunks = [
            "I'll help you read the file. Let me get",
            " the contents for you.\\n\\n",
            "```json\\n[",
            '{"action": "read_file",',
            ' "parameters": {"filepath": "test.txt"}',
            "}]\\n```\\n",
            "Here are the contents of the file:"
        ]

        # Test the complete flow through model client
        model_client = ModelClient("test-model")

        # Create mock response that simulates streaming
        async def mock_stream():
            for chunk in broken_chunks:
                yield chunk.encode('utf-8')
                await asyncio.sleep(0.01)  # Simulate network delay

        # Mock the session and response
        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.content = mock_stream()
        mock_response.status = 200

        # Collect the buffered response
        collected_chunks = []
        async for chunk in model_client._process_stream_response(mock_response):
            collected_chunks.append(chunk)
            logger.debug(f"Received chunk: {repr(chunk)}")

        # Verify the results
        complete_response = "".join(collected_chunks)
        logger.info(f"Complete response: {repr(complete_response)}")

        # Extract tool calls from the complete response
        actions, has_json = extract_json_with_feedback(complete_response)

        # Verify tool call was extracted correctly
        assert has_json, "Should have detected JSON content"
        assert len(actions) > 0, "Should have extracted at least one action"
        assert isinstance(actions, list), "Actions should be a list"

        if len(actions) > 0:
            action = actions[0]
            assert isinstance(action, dict), "Action should be a dictionary"
            assert "action" in action, "Action should have 'action' key"
            assert action["action"] == "read_file", f"Expected 'read_file', got {action.get('action')}"
            assert "parameters" in action, "Action should have 'parameters' key"
            assert action["parameters"]["filepath"] == "test.txt", "Filepath parameter incorrect"

        logger.info("✅ Test 1 PASSED: Tool call buffering works correctly")
        self.test_results.append("Test 1: Streaming Tool Call Breakup - PASSED")

    async def test_multiple_tool_calls_streaming(self):
        """Test multiple tool calls in a single streaming response."""
        logger.info("🧪 Test 2: Multiple Tool Calls Streaming")

        # Simulate multiple tool calls broken across chunks
        broken_chunks = [
            "I'll help you with both tasks. Let me start by",
            " reading the file and then execute a command.\\n\\n",
            "```json\\n[",
            '{"action": "read_file", "parameters": {"filepath": "config.txt"}},',
            ' {"action": "execute_command", "parameters": {"command": "ls -la"}}',
            "]\\n```\\n",
            "Both tasks completed successfully!"
        ]

        model_client = ModelClient("test-model")

        async def mock_stream():
            for chunk in broken_chunks:
                yield chunk.encode('utf-8')
                await asyncio.sleep(0.01)

        mock_response = AsyncMock()
        mock_response.content = mock_stream()
        mock_response.status = 200

        collected_chunks = []
        async for chunk in model_client._process_stream_response(mock_response):
            collected_chunks.append(chunk)

        complete_response = "".join(collected_chunks)
        actions, has_json = extract_json_with_feedback(complete_response)

        assert has_json, "Should have detected JSON content"
        assert len(actions) == 2, f"Should have extracted 2 actions, got {len(actions)}"

        # Verify first action
        assert actions[0]["action"] == "read_file"
        assert actions[0]["parameters"]["filepath"] == "config.txt"

        # Verify second action
        assert actions[1]["action"] == "execute_command"
        assert actions[1]["parameters"]["command"] == "ls -la"

        logger.info("✅ Test 2 PASSED: Multiple tool calls handled correctly")
        self.test_results.append("Test 2: Multiple Tool Calls Streaming - PASSED")

    async def test_incomplete_tool_call_handling(self):
        """Test handling of incomplete tool calls at end of stream."""
        logger.info("🧪 Test 3: Incomplete Tool Call Handling")

        # Simulate incomplete tool call (missing closing bracket)
        broken_chunks = [
            "I'll try to read the file for you.\\n\\n",
            "```json\\n[",
            '{"action": "read_file", "parameters": {"filepath": "test.txt"',
            # Missing closing } and ]
        ]

        model_client = ModelClient("test-model")

        async def mock_stream():
            for chunk in broken_chunks:
                yield chunk.encode('utf-8')
                await asyncio.sleep(0.01)

        mock_response = AsyncMock()
        mock_response.content = mock_stream()
        mock_response.status = 200

        collected_chunks = []
        async for chunk in model_client._process_stream_response(mock_response):
            collected_chunks.append(chunk)

        complete_response = "".join(collected_chunks)
        logger.info(f"Response with incomplete tool: {repr(complete_response)}")

        # Should still get some content, even if tool call is incomplete
        assert len(collected_chunks) > 0, "Should have received some content"

        # The incomplete tool call should be yielded as regular text
        assert "```json" in complete_response, "Should contain the incomplete tool call marker"

        logger.info("✅ Test 3 PASSED: Incomplete tool calls handled gracefully")
        self.test_results.append("Test 3: Incomplete Tool Call Handling - PASSED")

    async def test_mixed_content_and_tools(self):
        """Test mixing regular content with tool calls."""
        logger.info("🧪 Test 4: Mixed Content and Tools")

        # Simulate conversation with mixed content
        broken_chunks = [
            "Let me check the file contents for you.\\n\\n",
            "```json\\n",
            '[{"action": "read_file", "parameters": {"filepath": "data.txt"}}]',
            "\\n```\\n\\n",
            "The file contains important configuration data. Now let me",
            " also check the system status.\\n\\n",
            "```json\\n",
            '[{"action": "execute_command", "parameters": {"command": "uptime"}}]',
            "\\n```\\n\\n",
            "System is running normally."
        ]

        model_client = ModelClient("test-model")

        async def mock_stream():
            for chunk in broken_chunks:
                yield chunk.encode('utf-8')
                await asyncio.sleep(0.01)

        mock_response = AsyncMock()
        mock_response.content = mock_stream()
        mock_response.status = 200

        collected_chunks = []
        async for chunk in model_client._process_stream_response(mock_response):
            collected_chunks.append(chunk)

        complete_response = "".join(collected_chunks)
        logger.info(f"Mixed content response: {repr(complete_response)}")

        # Should have both tool calls and regular content
        actions, has_json = extract_json_with_feedback(complete_response)

        assert has_json, "Should have detected JSON content"
        assert len(actions) == 2, f"Should have extracted 2 actions, got {len(actions)}"

        # Verify regular content is preserved
        assert "The file contains important configuration data" in complete_response
        assert "System is running normally" in complete_response

        logger.info("✅ Test 4 PASSED: Mixed content handled correctly")
        self.test_results.append("Test 4: Mixed Content and Tools - PASSED")

    async def test_edge_case_json_in_content(self):
        """Test JSON-like content that isn't actually tool calls."""
        logger.info("🧪 Test 5: JSON-like Content in Regular Text")

        # Simulate content with JSON-like strings that aren't tool calls
        broken_chunks = [
            "Here's an example of JSON syntax: ",
            '{"name": "example", "value": 42}. ',
            "This is just regular text mentioning JSON, not a tool call.\\n\\n",
            "Now let me actually read a file for you.\\n\\n",
            "```json\\n",
            '[{"action": "read_file", "parameters": {"filepath": "real.txt"}}]',
            "\\n```\\n"
        ]

        model_client = ModelClient("test-model")

        async def mock_stream():
            for chunk in broken_chunks:
                yield chunk.encode('utf-8')
                await asyncio.sleep(0.01)

        mock_response = AsyncMock()
        mock_response.content = mock_stream()
        mock_response.status = 200

        collected_chunks = []
        async for chunk in model_client._process_stream_response(mock_response):
            collected_chunks.append(chunk)

        complete_response = "".join(collected_chunks)
        logger.info(f"JSON-like content response: {repr(complete_response)}")

        actions, has_json = extract_json_with_feedback(complete_response)

        # Should extract the actual tool call, not the JSON-like text
        assert len(actions) >= 1, "Should have extracted at least the real tool call"

        # Verify the real tool call was extracted
        real_tool_found = any(action.get("action") == "read_file" for action in actions)
        assert real_tool_found, "Should have found the real read_file tool call"

        logger.info("✅ Test 5 PASSED: JSON-like content distinguished from real tool calls")
        self.test_results.append("Test 5: JSON-like Content - PASSED")

    async def run_all_tests(self):
        """Run all tests and report results."""
        logger.info("🚀 Starting Tool Call Buffering Test Suite")
        logger.info("=" * 60)

        try:
            await self.test_streaming_tool_call_breakup()
            await self.test_multiple_tool_calls_streaming()
            await self.test_incomplete_tool_call_handling()
            await self.test_mixed_content_and_tools()
            await self.test_edge_case_json_in_content()

            logger.info("\n" + "=" * 60)
            logger.info("🎉 ALL TESTS COMPLETED!")
            logger.info("Test Results Summary:")
            for result in self.test_results:
                logger.info(f"  {result}")

            logger.info("\n✅ Tool call buffering is working correctly!")
            logger.info("The streaming issue has been resolved!")

        except Exception as e:
            logger.error(f"❌ Test suite failed: {e}")
            logger.exception("Test failure details:")
            raise

async def main():
    """Run the test suite."""
    tester = ToolCallBufferingTests()
    await tester.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())