"""The ``shadowprompt`` command: ShadowScan and Lab campaigns from CI.

Exit codes:

* 0: everything passed the threshold.
* 1: a page reached the failing severity, or the campaign scored too low.
* 2: the run could not be completed (bad arguments, server unreachable,
  connection or campaign error).

The model API key is read from an environment variable, never from the
command line, so it stays out of shell history and process listings.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence

from shadowprompt_cli import __version__
from shadowprompt_cli import campaign as campaign_cmd
from shadowprompt_cli import scan as scan_cmd
from shadowprompt_cli.client import ApiError, Client

EXIT_OK = 0
EXIT_THRESHOLD = 1
EXIT_ERROR = 2

PROVIDERS = ("openai_compatible", "anthropic", "gemini", "azure_openai")
DEFAULT_KEY_ENV = "SHADOWPROMPT_LLM_API_KEY"


LEVEL_CODES = [f"{track}{n}" for track in "DI" for n in range(1, 6)]


def _levels(value: str) -> list[str]:
    """Level codes such as D1,D2,I1. Plain 1 to 3 still mean D1 to D3."""
    codes = set()
    for part in (p.strip().upper() for p in value.split(",")):
        if not part:
            continue
        if part in {"1", "2", "3"}:
            part = f"D{part}"
        if part not in LEVEL_CODES:
            raise argparse.ArgumentTypeError(
                f"unknown level {part!r}: use D1 to D5 (direct) and I1 to I5 (indirect)"
            )
        codes.add(part)
    if not codes:
        raise argparse.ArgumentTypeError("choose at least one level, e.g. D1,D2,I1")
    return [code for code in LEVEL_CODES if code in codes]


def _codes(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def build_parser() -> argparse.ArgumentParser:
    # No abbreviations: "--api-key" must not quietly match "--api-key-env".
    parser = argparse.ArgumentParser(
        prog="shadowprompt",
        description="Run ShadowScan and ShadowPrompt Lab checks against a ShadowPrompt server.",
        allow_abbrev=False,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--server",
        default=os.environ.get("SHADOWPROMPT_SERVER", "http://127.0.0.1:8000"),
        help="ShadowPrompt server URL (env SHADOWPROMPT_SERVER; default %(default)s)",
    )
    parser.add_argument("--json", action="store_true", help="print a JSON summary to stdout")
    # --json also works after the command; SUPPRESS keeps it from resetting the flag.
    common = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser(
        "scan",
        help="scan HTML files, directories, globs or URLs",
        parents=[common],
        allow_abbrev=False,
    )
    scan.add_argument("targets", nargs="+", help="files, directories, glob patterns or URLs")
    scan.add_argument(
        "--fail-on",
        choices=(*scan_cmd.SEVERITIES[1:], "never"),
        default="high",
        help="fail if any page reaches this severity (default %(default)s)",
    )
    scan.add_argument("--report-dir", help="save an HTML report for every page here")
    scan.add_argument(
        "--render",
        action="store_true",
        help="also run each page's JavaScript in the server's sandboxed browser",
    )

    camp = sub.add_parser(
        "campaign",
        help="run a Lab campaign against a model",
        parents=[common],
        allow_abbrev=False,
    )
    camp.add_argument("--provider", choices=PROVIDERS, default="openai_compatible")
    camp.add_argument("--base-url", required=True, help="the model API's base URL")
    camp.add_argument("--model", required=True, help="model or deployment name")
    camp.add_argument(
        "--api-key-env",
        default=DEFAULT_KEY_ENV,
        help="environment variable holding the model API key (default %(default)s)",
    )
    camp.add_argument(
        "--levels",
        type=_levels,
        default=["D1", "D2", "D3"],
        help="level codes, e.g. D1,D2,I1 (default D1,D2,D3)",
    )
    camp.add_argument("--sample-size", type=int, help="tests per level instead of all")
    camp.add_argument("--languages", type=_codes, default=[], help="language packs, e.g. es,hi")
    camp.add_argument(
        "--pack", action="append", default=[], help="custom pack JSON file (repeatable)"
    )
    camp.add_argument("--min-score", type=float, default=70.0, help="default %(default)s")
    camp.add_argument("--timeout", type=float, default=30.0, help="seconds per test")
    camp.add_argument("--retries", type=int, default=1, help="retries per test")
    camp.add_argument("--max-minutes", type=float, default=120.0, help="give up after this")
    camp.add_argument("--report", help="save the report here (.html or .pdf)")
    return parser


# --------------------------------------------------------------------------- #
# GitHub Actions integration
# --------------------------------------------------------------------------- #


def _github_output(values: dict[str, object]) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={'' if value is None else value}\n")


def _github_summary(markdown: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(markdown + "\n")


def _cell(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #


def do_scan(args: argparse.Namespace, client: Client) -> int:
    targets = scan_cmd.expand_targets(args.targets)
    if not targets:
        print("No HTML files or URLs to scan.", file=sys.stderr)
        return EXIT_ERROR
    outcomes = []
    for target in targets:
        outcome = scan_cmd.scan_one(client, target, render=args.render)
        outcomes.append(outcome)
        if args.report_dir and outcome.scan_id:
            scan_cmd.save_report(client, outcome, args.report_dir)
        if not args.json:
            if outcome.error:
                print(f"ERROR     {target}: {outcome.error}")
            else:
                print(f"{outcome.severity.upper():9} {outcome.score:3}  {target}")
                for finding in outcome.findings[:3]:
                    note = finding.get("obfuscation_note")
                    decoded = f" ({note[0].lower()}{note[1:]})" if note else ""
                    print(
                        f"            {finding['category_label']} in "
                        f"{finding['source_label']}{decoded}"
                    )

    failing = [o for o in outcomes if scan_cmd.breaches(o, args.fail_on)]
    worst = max((o.score or 0 for o in outcomes), default=0)
    if args.json:
        print(json.dumps({"fail_on": args.fail_on, "results": [o.as_dict() for o in outcomes]}))
    else:
        verdict = "FAILED" if failing else "passed"
        print(f"\n{len(outcomes)} scanned, {len(failing)} at or above '{args.fail_on}': {verdict}.")

    _github_output({"max-score": worst, "failed": str(bool(failing)).lower()})
    rows = "\n".join(
        f"| {_cell(o.target)} | {o.severity or 'error'} "
        f"| {'-' if o.score is None else o.score} | {len(o.findings)} |"
        for o in outcomes
    )
    _github_summary(
        f"### ShadowScan\n\n| Page | Severity | Score | Findings |\n| --- | --- | --- | --- |\n"
        f"{rows}\n\nFails at **{args.fail_on}**: "
        f"{'**failed**' if failing else 'passed'}.\n"
    )
    return EXIT_THRESHOLD if failing else EXIT_OK


def do_campaign(args: argparse.Namespace, client: Client) -> int:
    api_key = os.environ.get(args.api_key_env) or None
    settings = campaign_cmd.CampaignSettings(
        provider=args.provider,
        base_url=args.base_url,
        model=args.model,
        api_key=api_key,
        levels=args.levels,
        sample_size=args.sample_size,
        languages=args.languages,
        packs=args.pack,
        timeout_seconds=args.timeout,
        max_retries=args.retries,
        max_minutes=args.max_minutes,
    )

    def progress(message: str) -> None:
        print(message, file=sys.stderr)

    outcome = campaign_cmd.run_campaign(client, settings, progress=progress)
    if args.report:
        campaign_cmd.save_report(client, outcome.campaign_id, args.report)
    failed = campaign_cmd.breaches(outcome, args.min_score)

    if args.json:
        print(json.dumps({"min_score": args.min_score, **outcome.as_dict()}))
    else:
        score = "no score" if outcome.score is None else f"{outcome.score:g}/100"
        print(f"\n{args.model}: {score} ({outcome.rating or 'unrated'}), status {outcome.status}")
        for ls in outcome.level_scores:
            level_score = "-" if ls["score"] is None else f"{ls['score']:g}"
            print(f"  {ls.get('code', ls['level'])} {ls['name']:40} {level_score}")
        if outcome.failures:
            print(f"\n{len(outcome.failures)} tests failed or partly failed:")
            for failure in outcome.failures[:20]:
                print(f"  {failure['verdict']:8} {failure['id']:14} {failure['name']}")
        if outcome.error:
            print(f"\nError: {outcome.error}")
        verdict = "FAILED" if failed else "passed"
        print(f"\nMinimum score {args.min_score:g}: {verdict}.")

    _github_output(
        {
            "score": outcome.score,
            "rating": outcome.rating,
            "campaign-id": outcome.campaign_id,
            "failed": str(failed).lower(),
        }
    )
    levels = "\n".join(
        f"| {ls.get('code', ls['level'])} | {_cell(ls['name'])} "
        f"| {'-' if ls['score'] is None else ls['score']} |"
        for ls in outcome.level_scores
    )
    _github_summary(
        f"### ShadowPrompt Lab: {_cell(args.model)}\n\n"
        f"**Score:** {outcome.score if outcome.score is not None else 'none'} "
        f"({outcome.rating or 'unrated'}), minimum {args.min_score:g}: "
        f"{'**failed**' if failed else 'passed'}.\n\n"
        f"| Level | Name | Score |\n| --- | --- | --- |\n{levels}\n"
    )
    if outcome.status not in ("completed",) and outcome.error:
        return EXIT_ERROR
    return EXIT_THRESHOLD if failed else EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    client = Client(args.server)
    try:
        if args.command == "scan":
            return do_scan(args, client)
        return do_campaign(args, client)
    except ApiError as exc:
        print(f"shadowprompt: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:
        print("shadowprompt: interrupted", file=sys.stderr)
        return EXIT_ERROR
    except OSError as exc:
        print(f"shadowprompt: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
