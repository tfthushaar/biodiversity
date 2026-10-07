import { fmtDate } from "../lib/format";

/** Only http(s) links are rendered: URLs come from a database, so treat them as untrusted. */
export function safeUrl(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  try {
    const u = new URL(url);
    return u.protocol === "https:" || u.protocol === "http:" ? u.href : undefined;
  } catch {
    return undefined;
  }
}

export function Citation({
  text,
  url,
  verifiedOn,
}: {
  text: string;
  url: string | null | undefined;
  verifiedOn?: string | null;
}) {
  const href = safeUrl(url);
  return (
    <p className="where">
      Source:{" "}
      {href ? (
        <a href={href} target="_blank" rel="noopener noreferrer">
          {text}
        </a>
      ) : (
        text
      )}
      {verifiedOn && <span className="hint"> · quotes checked against the source {fmtDate(verifiedOn)}</span>}
    </p>
  );
}

/** The verbatim words the claim rests on. Rendered as text, never as markup. */
export function Quotes({ quotes }: { quotes: string[] }) {
  return (
    <>
      {quotes.map((q, i) => (
        <blockquote key={i}>“{q}”</blockquote>
      ))}
    </>
  );
}

export function EvidenceDetails({
  quotes,
  citation,
  url,
  verifiedOn,
}: {
  quotes: string[];
  citation: string;
  url: string | null | undefined;
  verifiedOn?: string | null;
}) {
  return (
    <details>
      <summary>
        Evidence ({quotes.length} verbatim {quotes.length === 1 ? "quote" : "quotes"})
      </summary>
      <Quotes quotes={quotes} />
      <Citation text={citation} url={url} verifiedOn={verifiedOn} />
    </details>
  );
}
