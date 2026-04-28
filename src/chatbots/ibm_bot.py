"""
IBM BOB Chat Bot Implementation

This module provides IBM BOB-specific implementation using OpenAI-compatible API.
IBM BOB is IBM's internal AI service that uses an OpenAI-compatible interface.
"""

import os
import json
from typing import Optional, List, Dict, Any, Callable

from .base import BaseChatBot
from chatbots.tool_executor import ToolExecutor
from common.pylogger import get_python_logger

logger = get_python_logger()


class IBMBobChatBot(BaseChatBot):
    """IBM BOB implementation with OpenAI-compatible API."""

    def _get_api_key(self) -> Optional[str]:
        """Get IBM BOB API key from environment."""
        return os.getenv("IBM_BOB_API_KEY")

    def _get_max_tool_result_length(self) -> int:
        """IBM BOB supports large context - 10K chars is reasonable."""
        return 10000

    def __init__(
        self,
        model_name: str,
        api_key: Optional[str] = None,
        tool_executor: ToolExecutor = None,
        api_url: Optional[str] = None,
        project_id: Optional[str] = None):
        super().__init__(model_name, api_key, tool_executor)

        # Import OpenAI SDK (IBM WatsonX.ai uses OpenAI-compatible API)
        self._sdk_import_failed = False
        self.project_id = None  # WatsonX.ai project ID
        
        try:
            from openai import OpenAI
            
            # Get API endpoint from parameter, environment, or model config
            api_base = api_url
            if not api_base:
                api_base = os.getenv("IBM_BOB_API_BASE")
            if not api_base:
                # Try to get from model config
                from core.model_config_manager import get_model_config
                model_config = get_model_config(model_name)
                if model_config and "apiUrl" in model_config:
                    api_base = model_config["apiUrl"]
                    logger.info(f"Using API URL from model config: {api_base}")
            if not api_base:
                api_base = "https://us-south.ml.cloud.ibm.com/ml/v1/text/chat"  # WatsonX.ai default
            
            # Get WatsonX.ai project ID from parameter or environment
            self.project_id = project_id or os.getenv("WATSONX_PROJECT_ID")
            if self.project_id:
                logger.info(f"WatsonX.ai project ID configured: {self.project_id[:8]}...")
                # Set as environment variable for the bot instance
                os.environ["WATSONX_PROJECT_ID"] = self.project_id
            else:
                logger.warning("WatsonX.ai project ID not found. API calls may fail.")
            
            # Only create client if API key is provided
            if self.api_key:
                # Add project_id as query parameter to base URL if provided
                if self.project_id:
                    separator = "&" if "?" in api_base else "?"
                    api_base_with_project = f"{api_base}{separator}project_id={self.project_id}"
                    logger.info(f"IBM WatsonX.ai client initialized with endpoint: {api_base} (with project_id)")
                else:
                    api_base_with_project = api_base
                    logger.info(f"IBM WatsonX.ai client initialized with endpoint: {api_base}")
                
                self.client = OpenAI(
                    api_key=self.api_key,
                    base_url=api_base_with_project
                )
            else:
                self.client = None
        except ImportError:
            logger.error("OpenAI SDK not installed. Install with: pip install openai")
            self._sdk_import_failed = True
            self.client = None

    def _get_model_specific_instructions(self) -> str:
        """IBM BOB-specific instructions."""
        return """---

**IBM BOB-SPECIFIC INSTRUCTIONS:**

**MANDATORY — Metric Discovery Before Queries:**
You MUST call `search_metrics` or `search_metrics_by_category` BEFORE calling
`execute_promql`. NEVER guess metric names — they are non-obvious
(e.g., `vllm:gpu_cache_usage_perc` not `vllm:kv_cache_usage_percentage`,
`DCGM_FI_DEV_GPU_TEMP` not `DCGM_FI_DEV_TEMP`).

Correct flow:
1. `search_metrics("GPU temperature")` → discover `DCGM_FI_DEV_GPU_TEMP`
2. `execute_promql("avg(DCGM_FI_DEV_GPU_TEMP) by (pod)")` → get data

Wrong flow:
1. `execute_promql("avg(DCGM_FI_DEV_TEMP)")` → no data (wrong name)

**Best Practices:**
- Provide detailed breakdowns by pod and namespace
- Balance comprehensiveness with conciseness"""

    def _convert_tools_to_openai_format(self) -> List[Dict[str, Any]]:
        """Convert MCP tools to OpenAI function calling format."""
        tools = self._get_mcp_tools()
        openai_tools = []
        for tool in tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["input_schema"]
                }
            })
        return openai_tools

    def chat(
        self,
        user_question: str,
        namespace: Optional[str] = None,
        progress_callback: Optional[Callable] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """Chat with IBM BOB using tool calling."""
        if not self.client:
            if self._sdk_import_failed:
                return "Error: OpenAI SDK not installed. Please install it with: pip install openai"
            else:
                return f"Error: API key required for IBM BOB model {self.model_name}. Please configure an IBM BOB API key in Settings."

        logger.info(f"🎯 IBMBobChatBot.chat() - Using IBM BOB API with model: {self.model_name}")

        try:
            # Create system prompt
            system_prompt = self._create_system_prompt(namespace)

            # Get model name suitable for IBM BOB API
            model_name = self._extract_model_name()

            # Prepare messages - start with system prompt
            messages = [{"role": "system", "content": system_prompt}]

            # Add conversation history if provided
            if conversation_history:
                logger.info(f"📜 Adding {len(conversation_history)} messages from conversation history")
                messages.extend(conversation_history)

            # Add current user question
            messages.append({"role": "user", "content": user_question})

            # Convert tools to OpenAI format
            openai_tools = self._convert_tools_to_openai_format()

            # Iterative tool calling loop
            max_iterations = 30
            iteration = 0
            consecutive_tool_tracker = {"name": None, "count": 0}

            while iteration < max_iterations:
                iteration += 1
                logger.info(f"🤖 IBM BOB tool calling iteration {iteration}")

                if progress_callback:
                    progress_callback(f"🤖 Thinking... (iteration {iteration})")

                # Call IBM BOB API (OpenAI-compatible)
                response = self.client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    tools=openai_tools,
                    temperature=0
                )

                choice = response.choices[0]
                finish_reason = choice.finish_reason
                message = choice.message

                # Convert message to dict for conversation history
                message_dict = {
                    "role": message.role,
                    "content": message.content or ""
                }

                # Handle tool calls
                if message.tool_calls:
                    message_dict["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": tc.type,
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        }
                        for tc in message.tool_calls
                    ]

                messages.append(message_dict)

                # Check finish reason
                if finish_reason == "stop":
                    logger.info("✅ IBM BOB finished with stop reason")
                    return message.content or "No response generated"

                elif finish_reason == "tool_calls":
                    logger.info(f"🔧 IBM BOB requested {len(message.tool_calls)} tool calls")

                    # Execute each tool call
                    for tool_call in message.tool_calls:
                        tool_name = tool_call.function.name
                        tool_args_str = tool_call.function.arguments

                        # Track consecutive tool calls
                        if consecutive_tool_tracker["name"] == tool_name:
                            consecutive_tool_tracker["count"] += 1
                        else:
                            consecutive_tool_tracker = {"name": tool_name, "count": 1}

                        # Prevent infinite loops
                        if consecutive_tool_tracker["count"] > 3:
                            error_msg = f"⚠️ Tool '{tool_name}' called {consecutive_tool_tracker['count']} times consecutively. Stopping to prevent infinite loop."
                            logger.warning(error_msg)
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": error_msg
                            })
                            continue

                        try:
                            tool_args = json.loads(tool_args_str)
                        except json.JSONDecodeError as e:
                            error_msg = f"Invalid JSON in tool arguments: {str(e)}"
                            logger.error(error_msg)
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": error_msg
                            })
                            continue

                        logger.info(f"🔧 Executing tool: {tool_name} with args: {tool_args}")

                        if progress_callback:
                            progress_callback(f"🔧 Executing: {tool_name}")

                        # Execute tool
                        tool_result = self._execute_tool(tool_name, tool_args)

                        # Truncate large results
                        max_length = self._get_max_tool_result_length()
                        if len(tool_result) > max_length:
                            tool_result = tool_result[:max_length] + f"\n\n[Result truncated to {max_length} characters]"

                        # Add tool result to messages
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": tool_result
                        })

                        logger.info(f"✅ Tool {tool_name} executed successfully")

                elif finish_reason == "length":
                    logger.warning("⚠️ IBM BOB response truncated due to length")
                    return message.content or "Response truncated due to length limit"

                else:
                    logger.warning(f"⚠️ Unexpected finish reason: {finish_reason}")
                    return message.content or f"Unexpected finish reason: {finish_reason}"

            # Max iterations reached
            logger.warning(f"⚠️ Max iterations ({max_iterations}) reached")
            return "Maximum iterations reached. Please try rephrasing your question or breaking it into smaller parts."

        except Exception as e:
            error_msg = f"Error in IBM BOB chat: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return f"Error: {error_msg}"

# Made with Bob
