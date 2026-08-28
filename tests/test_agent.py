import json
import os
import subprocess
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# 1. 初始化客户端
if api_key := os.getenv("DEEPSEEK_API_KEY", ""):
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
else:
    raise ValueError("未找到 DEEPSEEK_API_KEY，请检查 .env 文件配置！")

client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

# ==================== 定义本地真实工具（Tools 实际执行函数） ====================
def run_python_script(script_path: str) -> str:
  """实际运行指定的 Python 脚本并返回终端输出"""
  print(f"\n[Agent 正在执行工具] 运行脚本: {script_path}")
  try:
    # 使用当前的 python 环境执行
    result = subprocess.run(
        ["python", script_path],
        capture_output=True,
        text=True,
        timeout=30,
        encoding="utf-8",
    )
    output = f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    return output
  except Exception as e:
    return f"执行出错: {str(e)}"


# 映射表：把模型调用的函数名对应到本地 Python 函数
available_tools = {"run_python_script": run_python_script}


# ==================== 注册给大模型的 Tool Schema ====================
tools_definition = [
    {
        "type": "function",
        "function": {
            "name": "run_python_script",
            "description": (
                "运行指定的 Python 脚本并返回结果。当你需要测试或检查脚本输出时使用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "script_path": {
                        "type": "string",
                        "description": "Python脚本的路径，例如 tests/test_openai.py",
                    }
                },
                "required": ["script_path"],
            },
        },
    }
]


# ==================== 运行 Agent 循环 ====================
def run_agent(user_prompt: str):
  messages = [{"role": "user", "content": user_prompt}]

  print(f"[用户指令]: {user_prompt}")
  print("-" * 50)

  # 第一次请求：让模型思考并决定是否调用工具
  response = client.chat.completions.create(
      model="deepseek-chat", messages=messages, tools=tools_definition
  )

  response_message = response.choices[0].message
  messages.append(response_message)  # 将模型的回复加入对话历史

  # 检查模型是否想要调用工具
  if response_message.tool_calls:
    print(
        f"[模型决策]: 需要调用工具 ->"
        f" {response_message.tool_calls[0].function.name}"
    )

    for tool_call in response_message.tool_calls:
      function_name = tool_call.function.name
      function_args = json.loads(tool_call.function.arguments)

      if function_name in available_tools:
        # 1. 执行本地真实的 Python 函数
        tool_function = available_tools[function_name]
        tool_output = tool_function(**function_args)

        # 2. 把工具的执行结果包装成 tool 角色喂回给大模型
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": tool_output,
        })

    # 第二次请求：把工具的执行结果再交还给模型，让它给出最终答复
    print("[Agent 正在汇总结果并生成最终分析...]")
    final_response = client.chat.completions.create(
        model="deepseek-chat", messages=messages
    )
    print("\n[最终回复]:")
    print(final_response.choices[0].message.content)
  else:
    # 如果模型不需要调用工具，直接打印它的回复
    print("\n[最终回复]:")
    print(response_message.content)


if __name__ == "__main__":
  # 测试让 Agent 检查并运行一个脚本
  run_agent("请帮我运行一下 tests/test_openai.py，并告诉我运行结果有没有报错。")