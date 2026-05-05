"""
IBM WatsonX.ai Chat Bot Implementation

This module provides IBM WatsonX.ai-specific implementation using IBM Cloud IAM authentication.
WatsonX.ai requires IAM token-based authentication, not simple API key auth.
"""

import os
import json
import requests
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime, timedelta

from .base import BaseChatBot
from chatbots.tool_executor import ToolExecutor
from common.pylogger import get_python_logger
from core.model_config_manager import get_model_config

logger = get_python_logger()


class IBMBobChatBot(BaseChatBot):
    """IBM WatsonX.ai implementation with IBM Cloud IAM authentication."""

    def _get_api_key(self) -> Optional[str]:
        """Get IBM Cloud IAM API key from environment."""
        return os.getenv("IBM_BOB_API_KEY")

    def _get_max_tool_result_length(self) -> int:
        """IBM WatsonX.ai supports large context - 10K chars is reasonable."""
        return 10000
    
    def _get_iam_token(self, api_key: str) -> tuple[str, datetime]:
        """
        Get IBM Cloud IAM access token from API key.
        
        Returns:
            Tuple of (access_token, expiration_time)
        """
        try:
            url = "https://iam.cloud.ibm.com/identity/token"
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            data = {
                "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
                "apikey": api_key
            }
            
            logger.info("Requesting IAM token from IBM Cloud...")
            response = requests.post(url, headers=headers, data=data, timeout=10)
            response.raise_for_status()
            
            token_data = response.json()
            access_token = token_data["access_token"]
            expires_in = token_data.get("expires_in", 3600)  # Default 1 hour
            expiration = datetime.now() + timedelta(seconds=expires_in - 300)  # Refresh 5 min early
            
            logger.info(f"✅ IAM token obtained, expires in {expires_in} seconds")
            return access_token, expiration
            
        except Exception as e:
            logger.error(f"Failed to get IAM token: {e}")
            raise ValueError(f"Failed to authenticate with IBM Cloud: {e}")

    def __init__(
        self,
        model_name: str,
        api_key: Optional[str] = None,
        tool_executor: ToolExecutor = None,
        api_url: Optional[str] = None,
        project_id: Optional[str] = None):
        super().__init__(model_name, api_key, tool_executor)

        # IBM WatsonX.ai uses IAM token authentication
        self._sdk_import_failed = False
        self.project_id = None  # WatsonX.ai project ID
        self.iam_token = None  # IAM access token
        self.token_expiration = None  # Token expiration time
        self.api_base = None  # API endpoint
        
        # Get API endpoint from parameter, environment, or model config
        api_base = api_url
        if not api_base:
            api_base = os.getenv("IBM_BOB_API_BASE")
        if not api_base:
            # Try to get from model config
            from core.model_config_manager import get_model_config
            all_configs = get_model_config()
            model_config = all_configs.get(model_name)
            if model_config and "apiUrl" in model_config:
                api_base = model_config["apiUrl"]
                logger.info(f"Using API URL from model config: {api_base}")
        if not api_base:
            api_base = "https://us-south.ml.cloud.ibm.com/ml/v1/text/chat"  # WatsonX.ai default
        
        self.api_base = api_base
        
        # Get WatsonX.ai project ID from parameter or environment
        self.project_id = project_id or os.getenv("WATSONX_PROJECT_ID")
        if self.project_id:
            logger.info(f"WatsonX.ai project ID configured: {self.project_id[:8]}...")
            # Set as environment variable for the bot instance
            os.environ["WATSONX_PROJECT_ID"] = self.project_id
        else:
            logger.warning("WatsonX.ai project ID not found. API calls may fail.")
        
        # Get IAM token if API key is provided
        if self.api_key:
            try:
                self.iam_token, self.token_expiration = self._get_iam_token(self.api_key)
                logger.info(f"✅ IBM WatsonX.ai initialized with endpoint: {api_base}")
            except Exception as e:
                logger.error(f"Failed to initialize IBM WatsonX.ai: {e}")
                self._sdk_import_failed = True
        else:
            logger.warning("No API key provided for IBM WatsonX.ai")

    def _extract_model_name(self) -> str:
        """WatsonX.ai expects the full model name including vendor prefix.
        
        Override the base class method to return the modelName from config,
        which includes the full path like 'meta-llama/llama-3-3-70b-instruct'.
        """
        # Get full model config dict (all models)
        all_configs = get_model_config()
        
        # Extract the specific model's config
        model_config = all_configs.get(self.model_name)
        
        if model_config and "modelName" in model_config:
            return model_config["modelName"]
        
        # Fallback: return as-is (don't strip prefix)
        return self.model_name
    
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

    def _refresh_token_if_needed(self):
        """Refresh IAM token if it's expired or about to expire."""
        if not self.iam_token or not self.token_expiration:
            if self.api_key:
                self.iam_token, self.token_expiration = self._get_iam_token(self.api_key)
            return
        
        # Refresh if token expires in less than 5 minutes
        if datetime.now() >= self.token_expiration:
            logger.info("IAM token expired, refreshing...")
            self.iam_token, self.token_expiration = self._get_iam_token(self.api_key)
    
    def _call_watsonx_api(self, messages: List[Dict], tools: List[Dict]) -> Dict:
        """
        Call WatsonX.ai API with IAM token authentication.
        
        Args:
            messages: List of conversation messages
            tools: List of available tools
            
        Returns:
            API response as dict
        """
        # Refresh token if needed
        self._refresh_token_if_needed()
        
        # Get model name
        model_name = self._extract_model_name()
        
        # Prepare request
        url = f"{self.api_base}?version=2023-05-29"
        headers = {
            "Authorization": f"Bearer {self.iam_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        payload = {
            "model_id": model_name,
            "messages": messages,
            "project_id": self.project_id,
            "temperature": 0
        }
        
        # Add tools if provided
        if tools:
            payload["tools"] = tools
        
        logger.info(f"Calling WatsonX.ai API: {url}")
        logger.info(f"Request payload: {json.dumps(payload, indent=2)}")
        logger.info(f"Request headers: Authorization=Bearer *****, Content-Type={headers.get('Content-Type')}")
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            logger.info(f"Response status: {response.status_code}")
            logger.info(f"Response headers: {dict(response.headers)}")
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"WatsonX.ai API error: {e}")
            logger.error(f"Response status code: {e.response.status_code if e.response else 'No response'}")
            logger.error(f"Response text: {e.response.text if e.response else 'No response'}")
            logger.error(f"Response headers: {dict(e.response.headers) if e.response else 'No headers'}")
            raise
        except Exception as e:
            logger.error(f"Failed to call WatsonX.ai API: {e}")
            raise

    def chat(
        self,
        user_question: str,
        namespace: Optional[str] = None,
        progress_callback: Optional[Callable] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """Chat with IBM WatsonX.ai using tool calling."""
        if not self.api_key:
            return f"Error: API key required for IBM WatsonX.ai model {self.model_name}. Please configure an IBM Cloud IAM API key in Settings."
        
        if not self.project_id:
            return f"Error: Project ID required for IBM WatsonX.ai. Please configure project-id in the ai-ibm-credentials secret."
        
        if self._sdk_import_failed:
            return "Error: Failed to initialize IBM WatsonX.ai. Check logs for details."

        logger.info(f"🎯 IBMBobChatBot.chat() - Using IBM WatsonX.ai API with model: {self.model_name}")

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

                # Call WatsonX.ai API with IAM token
                response_data = self._call_watsonx_api(messages, openai_tools)

                # Extract response
                choices = response_data.get("choices", [])
                if not choices:
                    logger.error("No choices in WatsonX.ai response")
                    return "Error: No response from WatsonX.ai"
                
                choice = choices[0]
                finish_reason = choice.get("finish_reason")
                message = choice.get("message", {})

                # Convert message to dict for conversation history
                message_dict = {
                    "role": message.get("role", "assistant"),
                    "content": message.get("content") or ""
                }

                # Handle tool calls
                tool_calls = message.get("tool_calls", [])
                if tool_calls:
                    message_dict["tool_calls"] = tool_calls

                messages.append(message_dict)

                # Check finish reason
                if finish_reason == "stop":
                    logger.info("✅ WatsonX.ai finished with stop reason")
                    return message.get("content") or "No response generated"

                elif finish_reason == "tool_calls":
                    logger.info(f"🔧 WatsonX.ai requested {len(tool_calls)} tool calls")

                    # Execute each tool call
                    for tool_call in tool_calls:
                        function_data = tool_call.get("function", {})
                        tool_name = function_data.get("name")
                        tool_args_str = function_data.get("arguments", "{}")
                        tool_call_id = tool_call.get("id", "unknown")

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
                                "tool_call_id": tool_call_id,
                                "content": error_msg
                            })
                            continue

                        logger.info(f"🔧 Executing tool: {tool_name} with args: {tool_args}")

                        if progress_callback:
                            progress_callback(f"🔧 Executing: {tool_name}")

                        # Execute tool using tool executor
                        try:
                            tool_result = self.tool_executor.call_tool(tool_name, tool_args)
                        except Exception as e:
                            tool_result = f"Error executing tool: {str(e)}"
                            logger.error(f"Tool execution error: {e}")

                        # Truncate large results
                        max_length = self._get_max_tool_result_length()
                        if len(tool_result) > max_length:
                            tool_result = tool_result[:max_length] + f"\n\n[Result truncated to {max_length} characters]"

                        # Add tool result to messages
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": tool_result
                        })

                        logger.info(f"✅ Tool {tool_name} executed successfully")

                elif finish_reason == "length":
                    logger.warning("⚠️ WatsonX.ai response truncated due to length")
                    return message.get("content") or "Response truncated due to length limit"

                else:
                    logger.warning(f"⚠️ Unexpected finish reason: {finish_reason}")
                    return message.get("content") or f"Unexpected finish reason: {finish_reason}"

            # Max iterations reached
            logger.warning(f"⚠️ Max iterations ({max_iterations}) reached")
            return "Maximum iterations reached. Please try rephrasing your question or breaking it into smaller parts."

        except Exception as e:
            error_msg = f"Error in IBM WatsonX.ai chat: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return f"Error: {error_msg}"

# Made with Bob
