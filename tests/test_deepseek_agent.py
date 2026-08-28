import json
import os
import subprocess
from dotenv import load_dotenv
from openai import OpenAI
import pytest

load_dotenv()


@pytest.fixture(scope="module")
def ds_client():
  """Initialize and return the DeepSeek OpenAI client."""
  api_key = os.getenv("DEEPSEEK_API_KEY", "")
  if not api_key:
    pytest.fail("DEEPSEEK_API_KEY is missing from environment variables.")
  return OpenAI(api_key=api_key, base_url="https://api.deepseek.com")


@pytest.fixture(scope="module")
def load_skills_guide():
  """Read the tools guide and skill definitions from markdown."""
  skills_path = "agent_skills/tools_guild.md"
  if os.path.exists(skills_path):
    with open(skills_path, "r", encoding="utf-8") as f:
      return f.read()
  return "No explicit skills guide found."


def run_python_script(script_path: str) -> str:
  """Execute a specified Python script and return its standard output and error."""
  print(f"\n[Agent Tool Execution] Running script: {script_path}")
  try:
    result = subprocess.run(
        ["python", script_path],
        capture_output=True,
        text=True,
        timeout=30,
        encoding="utf-8",
    )
    return f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
  except Exception as e:
    return f"Execution error: {str(e)}"


@pytest.fixture
def available_tools():
  """Mapping of tool names to Python executable functions."""
  return {"run_python_script": run_python_script}


@pytest.fixture
def tools_definition():
  """Tool schema definitions for the model."""
  return [
      {
          "type": "function",
          "function": {
              "name": "run_python_script",
              "description": (
                  "Run a specified Python script and return the results based"
                  " on the project's tools guide."
              ),
              "parameters": {
                  "type": "object",
                  "properties": {
                      "script_path": {
                          "type": "string",
                          "description": (
                              "Path to the Python script, e.g.,"
                              " tests/test_openai.py"
                          ),
                      }
                  },
                  "required": ["script_path"],
              },
          },
      }
  ]


def test_deepseek_agent_with_skills(
    ds_client, load_skills_guide, available_tools, tools_definition
):
  """Test the agent utilizing system instructions loaded from the skills guide."""
  system_instruction = (
      "You are a professional Python development agent. "
      "Adhere strictly to the guidelines and tools provided below:\n\n"
      f"{load_skills_guide}"
  )

  user_prompt = (
      "Please run 'tests/test_openai.py' and verify its execution status."
  )

  messages = [
      {"role": "system", "content": system_instruction},
      {"role": "user", "content": user_prompt},
  ]

  print(f"\n[System Instruction Loaded from Guide]")
  print(f"[User Prompt]: {user_prompt}")
  print("-" * 50)

  # First API call with system context and tools
  response = ds_client.chat.completions.create(
      model="deepseek-chat", messages=messages, tools=tools_definition
  )

  response_message = response.choices[0].message
  messages.append(response_message)

  assert response_message.tool_calls, "Model failed to trigger a tool call."

  # Process tool execution loop
  for tool_call in response_message.tool_calls:
    function_name = tool_call.function.name
    function_args = json.loads(tool_call.function.arguments)

    assert (
        function_name in available_tools
    ), f"Unknown tool requested: {function_name}"

    tool_function = available_tools[function_name]
    tool_output = tool_function(**function_args)

    messages.append({
        "role": "tool",
        "tool_call_id": tool_call.id,
        "content": tool_output,
    })

  # Second API call to formulate final output
  final_response = ds_client.chat.completions.create(
      model="deepseek-chat", messages=messages
  )

  final_content = final_response.choices[0].message.content
  print("\n[Final Model Response with Skills Context]:")
  print(final_content)

  assert final_content is not None
  assert len(final_content) > 0