/**
 * Methodology and disclaimer.
 *
 * The blueprint requires the limitations notice to be available at all times,
 * so this page carries real content from Phase 0 rather than a placeholder.
 */

const NOT_DONE = [
  "It does not attack real users, real websites, or production systems.",
  "It does not retain your LLM API key after a session ends.",
  "It does not use real malware or exploit code. All payloads are educational.",
  "A clean result does not mean your LLM is safe. It means it passed the configured test suite.",
  "It is not a replacement for a full red-team engagement. It is a first-pass automated check.",
];

const LIMITATIONS = [
  "Rule-based detection cannot catch every paraphrase or non-English injection.",
  "Static HTML scanning misses content that JavaScript generates after page load.",
  "The evaluation engine cannot perfectly judge every response. Some verdicts need human review.",
  "Level 5 attacks span multiple turns, so models with very short context windows may behave differently.",
  "Passing every level of both tracks does not certify a model against all possible attacks.",
  "Only the model's API interface is tested. Attacks needing fine-tuning or white-box access are out of scope.",
  "The nuanced-judgment evaluator is itself a language model, so its blind spots can bias those verdicts.",
];

function Section({ title, items }: { title: string; items: string[] }) {
  return (
    <section>
      <h2 className="text-xl font-semibold">{title}</h2>
      <ul className="mt-3 list-inside list-disc space-y-1.5 text-sm text-slate-600 dark:text-slate-300">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

export default function About() {
  return (
    <div className="max-w-3xl space-y-8">
      <section>
        <h1 className="text-3xl font-bold tracking-tight">Methodology and limitations</h1>
        <p className="mt-2 text-slate-600 dark:text-slate-300">
          ShadowPrompt tests two things that are widely underestimated: direct
          jailbreaking, where crafted prompts make a model ignore its own rules, and
          indirect prompt injection, where instructions hidden in content the model reads
          hijack its behaviour without the user knowing.
        </p>
      </section>

      <section>
        <h2 className="text-xl font-semibold">How evaluation works</h2>
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
          A response cannot be judged by keyword matching alone, because a model can
          refuse in a hundred different ways. Each response passes through keyword
          signals, then a heuristic classifier, and only where those two disagree does a
          separate model act as a tie-breaking judge. Each test resolves to pass, fail,
          partial, or unclear.
        </p>
      </section>

      <Section title="What ShadowPrompt does not do" items={NOT_DONE} />
      <Section title="Known limitations" items={LIMITATIONS} />

      <section className="rounded-md border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
        <h2 className="font-semibold">Disclaimer</h2>
        <p className="mt-1">
          For authorized, educational, and defensive security research only. Test only
          models and pages you own or have permission to assess.
        </p>
      </section>
    </div>
  );
}
