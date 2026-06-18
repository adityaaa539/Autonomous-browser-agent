from fastapi import FastAPI

app = FastAPI(title="Autonomous Browser Agent API")

@app.get("/")
async def health_check():
    return {"status": "ok", "message": "Autonomous Browser Agent API is running"}
