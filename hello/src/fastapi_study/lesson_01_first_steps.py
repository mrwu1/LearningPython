from fastapi import FastAPI

app = FastAPI(title="AI Agent gate-away system",version="1.0")


# declare three practical interfaces

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/models/{model_name}")
async def get_model(model_name: str):
    return {"model_name":model_name,"status":"available","max_tokens":12800}

@app.get("/agent/ping")
async def ping_model():
    return {"pong": True, "message": "Agent 引擎就绪"}

if __name__=="__main__":
    import  uvicorn
    uvicorn.run("lesson_01_first_steps:app", host="127.0.0.1", port=8000, reload=True)