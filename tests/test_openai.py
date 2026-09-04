import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# 方案 1：如果你已经在 .env 里面配好了 DEEPSEEK_API_KEY
api_key = os.getenv("DEEPSEEK_API_KEY", "")

# 方案 2：或者直接填入你真实的英文/数字 Key 字符串
# api_key = "sk-xxxxxxxxxxxxxxxxxxxxxxxx"

# 初始化客户端，指向 DeepSeek 的服务器
client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

# 定义一个给 Agent 调用的工具
tools = [
    {
        "type": "function",
        "function": {
            "name": "run_python_script",
            "description": "运行指定的 Python 脚本并返回结果",
            "parameters": {
                "type": "object",
                "properties": {
                    "script_path": {
                        "type": "string",
                        "description": "Python脚本的路径",
                    }
                },
                "required": ["script_path"],
            },
        },
    }
]

# 发送测试请求
response = client.chat.completions.create(
    model="deepseek-chat",
    messages=[{"role": "user", "content": "帮我检查一下 test.py 的代码"}],
    tools=tools,
)

print(response.choices[0].message.content)