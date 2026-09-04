import os
from dotenv import load_dotenv
from openai import OpenAI
import pytest

load_dotenv()


@pytest.fixture(scope="module")
def ds_client():
  api_key = os.getenv("DEEPSEEK_API_KEY", "")
  if not api_key:
    pytest.fail("DEEPSEEK_API_KEY is missing.")
  return OpenAI(api_key=api_key, base_url="https://api.deepseek.com")


def test_standardized_skill_execution(ds_client):
  # 1. Load the standardized skill document
  skill_path = "agent_skills/forex_analysis_skill.md"
  with open(skill_path, "r", encoding="utf-8") as f:
    skill_content = f.read()

  # 2. Inject into System Prompt with strict structural enforcement
  system_instruction = (
      "You are a disciplined AI agent. "
      "You must operate strictly under the rules and output schemas defined in the loaded skill:\n\n"
      f"{skill_content}"
  )

  user_prompt = "Give me a quick trading setup for USD/JPY for today."

  messages = [
      {"role": "system", "content": system_instruction},
      {"role": "user", "content": user_prompt},
  ]

  print(f"\n[Loading Standardized Skill Document]")
  print(f"[User Prompt]: {user_prompt}")
  print("-" * 50)

  response = ds_client.chat.completions.create(
      model="deepseek-chat", messages=messages
  )

  content = response.choices[0].message.content
  print("\n[Structured Agent Output]:")
  print(content)

  # 3. Assertions to ensure output compliance with the schema defined in the skill doc
  assert content is not None
  # Check if the model followed the Required Output Schema sections
  assert "Macro" in content or "Macro Environment" in content
  assert "Technical Levels" in content or "Support" in content