"use client";

import { useState } from "react";

const EXAMPLES = [
  "What production rate changes is Boeing forecasting for FY2023?",
  "What is Coca Cola's FY2021 COGS % margin? Calculate what was asked by utilizing the line items clearly shown in the income statement.",
  "Will Tesla stock go up next week?",
];

const DOC_TYPES = { "10k": "10-K", "10q": "10-Q", "8k": "8-K", earnings: "Earnings release" };

function docType(type) {
  return DOC_TYPES[type.toLowerCase()] ?? type;
}

// "{c1}" as a calculation input means the result of calculation 1.
function input(value) {
  const step = value.match(/^\{c(\d+)\}$/);
  return step ? `result ${step[1]}` : value;
}

function describe({ operation, inputs, result }) {
  const values = inputs.map(input);
  const [a, b] = values;
  switch (operation) {
    case "percent_change":
      return `Change from ${a} to ${b} = ${result}`;
    case "ratio":
      return `${a} ÷ ${b} = ${result}`;
    case "percentage":
      return `${a} ÷ ${b} × 100 = ${result}`;
    case "difference":
      return `${a} − ${b} = ${result}`;
    case "average":
      return `Average of ${values.join(", ")} = ${result}`;
    case "product":
      return `${values.join(" × ")} = ${result}`;
    default:
      return `${values.join(" + ")} = ${result}`;
  }
}

async function ask(question) {
  try {
    const response = await fetch("/svc/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    if (response.ok) return { kind: "result", ...(await response.json()) };
    if (response.status === 503) {
      return { kind: "error", message: "The answer service is busy or unavailable. Try again in a minute." };
    }
    return { kind: "error", message: "Something went wrong answering that question." };
  } catch {
    return { kind: "error", message: "Couldn't reach FilingCite. Check your connection and try again." };
  }
}

export default function Home() {
  const [question, setQuestion] = useState("");
  const [asked, setAsked] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  async function submit(text) {
    const trimmed = text.trim();
    if (!trimmed || loading) return;
    setQuestion(trimmed);
    setAsked(trimmed);
    setLoading(true);
    setResult(null);
    setResult(await ask(trimmed));
    setLoading(false);
  }

  return (
    <main>
      <header>
        <h1>FilingCite</h1>
        <p className="tagline">
          Answers about public companies&apos; SEC filings. Every number is traced to a cited
          page, or FilingCite says it doesn&apos;t know.
        </p>
      </header>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          submit(question);
        }}
      >
        <label htmlFor="question">Your question</label>
        <textarea
          id="question"
          rows={3}
          maxLength={500}
          value={question}
          placeholder="e.g. What was 3M's capital expenditure in FY2018?"
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              submit(question);
            }
          }}
        />
        <button type="submit" disabled={loading || !question.trim()}>
          {loading ? "Checking the filings…" : "Ask"}
        </button>
      </form>

      <div className="examples">
        <span>Try:</span>
        {EXAMPLES.map((example) => (
          <button
            key={example}
            type="button"
            className="example"
            disabled={loading}
            onClick={() => submit(example)}
          >
            {example.length > 70 ? `${example.slice(0, 67)}…` : example}
          </button>
        ))}
      </div>

      <section aria-live="polite">
        {result && <Result question={asked} result={result} />}
      </section>

      <footer>
        Covers 84 filings (10-Ks, 10-Qs, 8-Ks and earnings releases) from 32 companies,
        2015–2024, from the FinanceBench dataset. Not investment advice.
      </footer>
    </main>
  );
}

function Result({ question, result }) {
  if (result.kind === "error") {
    return (
      <article className="card error">
        <p>{result.message}</p>
      </article>
    );
  }

  if (!result.answered) {
    return (
      <article className="card refusal">
        <p className="asked">{question}</p>
        <h2>I don&apos;t know</h2>
        <p>{result.message.replace(/^I don't know\.\s*/, "")}</p>
      </article>
    );
  }

  return (
    <article className="card">
      <p className="asked">{question}</p>
      <p className="answer">{result.answer}</p>

      {result.calculations.length > 0 && (
        <>
          <h3>Calculated by FilingCite</h3>
          <ol className="calculations">
            {result.calculations.map((calc, i) => (
              <li key={i}>{describe(calc)}</li>
            ))}
          </ol>
        </>
      )}

      <h3>Sources</h3>
      <ol className="citations">
        {result.citations.map((c) => (
          <li key={c.number}>
            <span className="number">{c.number}</span>
            <span>
              {c.company} · {docType(c.doc_type)} {c.doc_period} ·{" "}
              {c.doc_link ? (
                <a href={`${c.doc_link}#page=${c.page}`} target="_blank" rel="noopener noreferrer">
                  page {c.page}
                </a>
              ) : (
                `page ${c.page}`
              )}
            </span>
          </li>
        ))}
      </ol>
    </article>
  );
}
