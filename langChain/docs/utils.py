from langchain.chat_models import init_chat_model

model = init_chat_model(
    "deepseek-flash",
    model_provider="deepseek",
    # Kwargs passed to the model:
    base_url="https://api.deepseek.com",
    api_key="sk-f8f7bf1c05404adb96717f0c929a6c46",
    temperature=0.7,
    timeout=30,
    max_tokens=1000,
    max_retries=6,  # Default; increase for unreliable networks
)