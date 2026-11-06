from fastapi import FastAPI, HTTPException
from openai import RateLimitError
from pydantic import BaseModel, Field

from answer import AskResponse, answer_question
from db import connect
from llm import chat_model

app = FastAPI()
model = chat_model()


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


@app.post("/svc/api/ask")
def ask(request: AskRequest) -> AskResponse:
    try:
        with connect() as conn:
            return answer_question(conn, request.question, model)
    except RateLimitError:
        raise HTTPException(status_code=429, detail="Busy, try again in a minute.") from None
