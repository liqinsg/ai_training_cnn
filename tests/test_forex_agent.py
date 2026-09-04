import os
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
def load_forex_skill():
  """Load the forex analysis skill guidelines from markdown."""
  skill_path = "agent_skills/forex_analysis_skill.md"
  if os.path.exists(skill_path):
    with open(skill_path, "r", encoding="utf-8") as f:
      return f.read()
  return "No specific forex skill guidelines found."


def test_forex_market_strategy_agent(ds_client, load_forex_skill):
  """Test the DeepSeek agent providing forex strategy guidance based on custom skills."""
  system_instruction = (
      "You are an expert quantitative forex trading assistant. "
      "Adhere strictly to the operational rules defined in your skill guide:\n\n"
      f"{load_forex_skill}"
  )

  user_prompt = (
      "Based on current macroeconomic conditions and recent Bank of Japan "
      "policy directions, how should we approach trading USD/JPY today? "
      "Provide a structured operational strategy with risk considerations."
  )

  messages = [
      {"role": "system", "content": system_instruction},
      {"role": "user", "content": user_prompt},
  ]

  print(f"\n[Loaded Forex Skill into System Prompt]")
  print(f"[User Prompt]: {user_prompt}")
  print("-" * 50)

  # Request analysis from DeepSeek
  response = ds_client.chat.completions.create(
      model="deepseek-chat", messages=messages
  )

  analysis_content = response.choices[0].message.content
  print("\n[DeepSeek Forex Strategy Analysis]:")
  print(analysis_content)

  # Basic assertions to ensure a valid response
  assert analysis_content is not None
  assert len(analysis_content) > 0