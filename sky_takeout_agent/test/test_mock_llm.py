import httpx
import pytest
import respx


@pytest.mark.asyncio
@respx.mock
async def  test_mock_openai_chat_completion():
    """
            模拟大模型返回，耗时 0 毫秒，消耗 0 Token！
            对标 Java: Mockito.when(...)
            """
    mock_url = "https://api.openai.com/v1/chat/completions"
    mocked_llm_response = {
        "id": "chatcmpl-mock-123",
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "您好！我是苍穹外卖虚拟点餐助手，今天推荐招牌烤鸭！"
            }
        }]
    }

    # 1. 注册拦截桩（Stubbing）：只要有人向 mock_url 发送 POST 请求，立刻拦截并返回假数据
    respx.post(mock_url).mock(
        return_value=httpx.Response(200, json=mocked_llm_response)
    )

    # 2. 模拟业务客户端调用
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            mock_url,
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "推荐个菜"}]}
        )

    # 3. 校验业务逻辑是否成功消费了 Mock 结果
    assert resp.status_code == 200
    result = resp.json()
    content = result["choices"][0]["message"]["content"]
    assert "招牌烤鸭" in content
    print("\n✅ 大模型 Mock 拦截成功！毫秒级跑通，消耗 0 Token！")