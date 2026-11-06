"use client";

import { useEffect, useRef, useState } from "react";

const REPO = "https://github.com/BhavnoorSaini/FilingCite";

// Five it answers, and one it should refuse.
const EXAMPLES = [
  "What was 3M's capital expenditure in FY2018?",
  "What is Coca Cola's FY2021 COGS % margin?",
  "What was Amazon's revenue growth from FY2016 to FY2017?",
  "What were Nike's total current assets at the end of FY2019?",
  "How much cash did JnJ get from the Kenvue separation?",
  "Will Tesla stock go up next week?",
];

const SIGNS = { ratio: "÷", percentage: "÷", difference: "−", sum: "+", product: "×" };

// How Python got a result. "{c1}" means the result of step 1.
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
  const resultRef = useRef(null);

  // On small screens the answer appears below the fold, so bring it into view.
  useEffect(() => {
    if (result) resultRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [result]);

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
      if (response.status === 429) setResult({ busy: true });
      else setResult(response.ok ? await response.json() : { error: true });
    } catch {
      setResult({ error: true });
    }
    setLoading(false);
  }

  return (
    <main>
      <header>
        <h1>FilingCite</h1>
        <a className="github" href={REPO} target="_blank" rel="noopener noreferrer">
          <GitHubIcon />
          GitHub
        </a>
      </header>
      <p className="muted">
        Answers about public companies&apos; SEC filings, citing the exact page. If the filings
        don&apos;t support an answer, FilingCite says it doesn&apos;t know.
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

      <p className="label">Try an example</p>
      <div className="examples">
        {EXAMPLES.map((example) => (
          <button key={example} type="button" disabled={loading} onClick={() => ask(example)}>
            {example}
          </button>
        ))}
      </div>

      <section ref={resultRef} aria-live="polite">{result && <Result result={result} />}</section>

      <footer className="muted">
        Covers 84 filings from 32 companies in the FinanceBench dataset. Not investment advice.
      </footer>
    </main>
  );
}

function GitHubIcon() {
  return (
    <svg viewBox="0 0 16 16" width="18" height="18" aria-hidden="true" fill="currentColor">
      <path d="M8 0c4.42 0 8 3.58 8 8a8.013 8.013 0 0 1-5.45 7.59c-.4.08-.55-.17-.55-.38 0-.27.01-1.13.01-2.2 0-.75-.25-1.23-.54-1.48 1.78-.2 3.65-.88 3.65-3.95 0-.88-.31-1.59-.82-2.15.08-.2.36-1.02-.08-2.12 0 0-.67-.22-2.2.82-.64-.18-1.32-.27-2-.27-.68 0-1.36.09-2 .27-1.53-1.03-2.2-.82-2.2-.82-.44 1.1-.16 1.92-.08 2.12-.51.56-.82 1.28-.82 2.15 0 3.06 1.86 3.75 3.64 3.95-.23.2-.44.55-.51 1.07-.46.21-1.61.55-2.33-.66-.15-.24-.6-.83-1.23-.82-.67.01-.27.38.01.53.34.19.73.9.82 1.13.16.45.68 1.31 2.69.94 0 .67.01 1.3.01 1.49 0 .21-.15.45-.55.38A7.995 7.995 0 0 1 0 8c0-4.42 3.58-8 8-8Z" />
    </svg>
  );
}

function Result({ result }) {
  if (result.busy) {
    return <p className="card">Busy, try again in a minute.</p>;
  }
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
