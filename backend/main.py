from fastapi import FastAPI
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
    with connect() as conn:
        return answer_question(conn, request.question, model)
