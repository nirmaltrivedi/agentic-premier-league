from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from routers import recap, chat, meta

app = FastAPI(
    title="Cricket Recap API",
    description="Personalized match recaps powered by LangGraph + Gemini",
    version="1.0.0",
)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(recap.router)
app.include_router(chat.router)
app.include_router(meta.router)


@app.get("/", include_in_schema=False)
def ui():
    return FileResponse("static/index.html")
