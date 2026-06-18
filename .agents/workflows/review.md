# Review changes against the constitution

Act as the harness reviewer. **Annotate, do not block** — surface findings and
let me decide.

1. Run the guardrails in annotate mode and read the output:

   ```bash
   python3 tools/checks/run_checks.py --annotate
   ```

2. For the files I changed, also check the things the scripts can't fully verify,
   citing [AGENTS.md](../../AGENTS.md):
   - **Rule 6 (language):** are all dataset/table/column descriptions written in
     **Portuguese** and business-meaningful (categorical values, currency,
     source)? The validator only checks they *exist* — you check the language.
   - **Rule 4:** are `uniqueKey` / `nonNull` assertions actually correct for the
     business key, not just present?
   - **Naming & placement:** `{layer}_{domain}` datasets, `{domain}__{pipeline}`
     DAGs, `ingest-{domain}-{source}` jobs, correct mono-repo paths.
   - **Layering:** no cross-layer imports; staging consumed only within its layer.
   - **Dev/prod:** work targets `_dev`; no manual writes to production.

3. Report a concise list: file → issue → suggested fix → severity. Recommend, but
   leave the call to me.
