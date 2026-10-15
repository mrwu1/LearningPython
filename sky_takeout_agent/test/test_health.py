

def test_health_check_endpoint(client):
    """测试健康探针是否正常返回，并验证 TraceID 闭环"""
    custom_trace_id = "test-ci-999"

    # 模拟前端携带 X-Request-ID 发送请求
    response = client.get("/api/v1/healthz", headers={"X-Request-ID": custom_trace_id})

    # 1. 断言 HTTP 状态码必须是 200
    assert response.status_code == 200

    # 2. 断言业务返回数据
    data = response.json()
    assert data["status"] == "ok"
    assert "env" in data

    # 3. 断言响应头里成功透传了 TraceID
    assert response.headers.get("x-request-id") == custom_trace_id