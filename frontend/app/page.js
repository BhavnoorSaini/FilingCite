"use client";

import { useState } from "react";

// Four it answers, and one it should refuse.
const EXAMPLES = [
  "What was 3M's capital expenditure in FY2018?",
  "What is Coca Cola's FY2021 COGS % margin?",
  "What was Amazon's revenue growth from FY2016 to FY2017?",
  "What were Nike's total current assets at the end of FY2019?",
  "Will Tesla stock go up next week?",
];

const SIGNS = { ratio: "÷", percentage: "÷", difference: "−", sum: "+", product: "×" };

// How Python worked out a result; "{c1}" as an input means the result of step 1.
function describe({ operation, inputs, result }) {
  const values = inputs.map((v) => v.replace(/^\{c(\d+)\}$/, "result $1"));
  if (operation === "percent_change") return `Change from ${values[0]} to ${values[1]} = ${result}`;
  if (operation === "cagr") return `Yearly growth from ${values[0]} to ${values[1]} over ${values[2]} years = ${result}`;
  if (operation === "average") return `Average of ${values.join(", ")} = ${result}`;
  const times100 = operation === "percentage" ? " × 100" : "";
  return `${values.join(` ${SIGNS[operation]} `)}${times100} = ${result}`;
}

export default function Home() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  async function ask(text) {
    setQuestion(text);
    setLoading(true);
    setResult(null);
    try {
      const response = await fetch("/svc/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: text.trim() }),
      });
      setResult(response.ok ? await response.json() : { error: true });
    } catch {
      setResult({ error: true });
    }
    setLoading(false);
  }

  return (
    <main>
      <h1>FilingCite</h1>
      <p className="muted">
        Answers about public companies&apos; SEC filings. Every number is traced to a cited page,
        or FilingCite says it doesn&apos;t know.
      </p>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          ask(question);
        }}
      >
        <input
          aria-label="Your question"
          maxLength={500}
          value={question}
          placeholder="e.g. What was 3M's capital expenditure in FY2018?"
          onChange={(event) => setQuestion(event.target.value)}
        />
        <button type="submit" disabled={loading || !question.trim()}>
          {loading ? "Checking the filings…" : "Ask"}
        </button>
      </form>

      <div className="examples">
        {EXAMPLES.map((example) => (
          <button key={example} type="button" disabled={loading} onClick={() => ask(example)}>
            {example}
          </button>
        ))}
      </div>

      <section aria-live="polite">{result && <Result result={result} />}</section>

      <p className="muted">
        Covers 84 filings from 32 companies in the FinanceBench dataset. Not investment advice.
      </p>
    </main>
  );
}

function Result({ result }) {
  if (result.error) {
    return <p className="card">Something went wrong. Try again in a minute.</p>;
  }
  if (!result.answered) {
    return <p className="card refusal">{result.message}</p>;
  }
  return (
    <article className="card">
      <p className="answer">{result.answer}</p>

      {result.calculations.length > 0 && (
        <>
          <h3>Calculated by FilingCite</h3>
          <ol>
            {result.calculations.map((calc, i) => (
              <li key={i}>{describe(calc)}</li>
            ))}
          </ol>
        </>
      )}

      <h3>Sources</h3>
      <ol>
        {result.citations.map((c) => (
          <li key={c.number}>
            [{c.number}] {c.company} {c.doc_type.toUpperCase()} {c.doc_period},{" "}
            <a href={`${c.doc_link}#page=${c.page}`} target="_blank" rel="noopener noreferrer">
              page {c.page}
            </a>
          </li>
        ))}
      </ol>
    </article>
  );
}
