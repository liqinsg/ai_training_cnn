# AI Quantitative Trading & Agent Sprints Framework

A lightweight, robust framework integrating **DeepSeek API**, **Markdown-based Agent Skills**, and **Pytest-driven automation** for quantitative forex trading and local AI agent workflows.

## 📁 Project Architecture

```text
ai_training_cnn/
├── .env                      # API keys and sensitive configurations
├── agent_skills/             # Modular agent skill database (Markdown prompts)
│   ├── tools_guild.md        # Tool definitions & execution rules
│   └── forex_analysis_skill.md # Forex strategy & quantitative logic
├── src/                      # Core business logic
│   ├── agent_core.py         # Reusable agent execution loop
│   └── fx_trade_bot_utils.py # Oanda API & trading utility modules
└── tests/                    # Pytest integration and unit test suite
    ├── test_deepseek_agent.py# Agent tool-calling tests
    └── test_standardized_skill.py # Skill compliance & output schema validation
