import asyncio
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.agents import create_agent

from mcp.types import TextContent
from langchain.messages import ToolMessage
from langchain_mcp_adapters.interceptors import MCPToolCallRequest
from langchain_openai import ChatOpenAI
import json

api_key= "sk-f251200940a745da936595522d6fbebb"
base_url= "https://api.deepseek.com/v1"
model= "deepseek-chat"
llm = ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=0.7,
            max_tokens=2000,
            timeout=60.0,  # 增加到60秒
            max_retries=3
        )
async def append_structured_content(request: MCPToolCallRequest, handler):
    """Append structured content from artifact to tool message."""
    result = await handler(request)
    runtime = request.runtime
    # print(type(result))
    # print("========================result.content:", result.content[-1].text)
    if result.structuredContent:
        result.content += [
            TextContent(type="text", text=json.dumps(result.structuredContent)),
        ]
    return ToolMessage(content=result.content, tool_call_id=runtime.tool_call_id)


async def main():
    client = MultiServerMCPClient(
        {
            "ping": {
                "transport": "stdio",  # Local subprocess communication
                "command": "python",
                # Absolute path to your math_server.py file
                "args": ["F:\\LangGraph-trip-planner-main\\learn\\docker_net_server.py"]
            },
            "wireShark":{
                "transport":"stdio",
                "command":"python",
                "args": ["F:\\LangGraph-trip-planner-main\\learn\\linux_tools_server.py"]
            }
        }, tool_interceptors=[append_structured_content]
    )


    tools = await client.get_tools()

    agent = create_agent(
        model=llm,
        tools=tools,
        debug=False  # 设置为 True 可启用详细日志
    )


    math_response = await agent.ainvoke(
        {"messages": [{"role": "user", "content": "请帮我追踪一下到 www.baidu.com 的路由路径"}]}
    )
    print(math_response)

if __name__ == "__main__":
    asyncio.run(main())