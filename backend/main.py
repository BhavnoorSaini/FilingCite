from functools import cache
from typing import Annotated

import openai
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from answer import AskResponse, answer_question
from db import connect
from llm import Model, chat_model

app = FastAPI(
    title="FilingCite API",
    docs_url="/svc/api/docs",
    openapi_url="/svc/api/openapi.json",
)


class AskRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=500)


@cache
def get_model() -> Model:
    return chat_model()  # tests override this dependency with a fake model


@app.get("/svc/api/status")
def get_status():
    return {"status": "ok"}


@app.post("/svc/api/ask")
def ask(request: AskRequest, model: Annotated[Model, Depends(get_model)]) -> AskResponse:
    try:
        with connect() as conn:
            return answer_question(conn, request.question, model)
    except openai.APIError as error:
        # Rate limits and outages are not "I don't know": say the service is unavailable.
        raise HTTPException(503, "The answer service is unavailable. Try again shortly.") from error
