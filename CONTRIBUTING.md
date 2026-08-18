# Contributing

Contributions are welcome. Read this before opening a pull request, because the first section is a condition of merging and cannot be waived after the fact.

## Contributor License Agreement

By submitting a contribution you agree to the following.

1. **You grant the project a license to your contribution.** You grant Tim Thomas and the Eviction Research Network a perpetual, worldwide, non-exclusive, royalty-free, irrevocable license to reproduce, modify, publicly display, sublicense, and distribute your contribution and works derived from it, under any license terms, including terms different from the AGPL-3.0 that currently governs this project.

2. **You keep your copyright.** This is a license, not an assignment. You remain free to use your own contribution however you like, including in other projects.

3. **You have the right to grant it.** You represent that the contribution is your original work, or that you have the rights to submit it under these terms. If your employer or institution holds rights in work you do, you represent that you have their permission. If you are contributing as part of employment at a university, check your institution's copyright policy before submitting.

4. **No warranty.** Contributions are provided as-is.

### Why this exists

Without a CLA, every contributor holds copyright in their own patch. That means the project cannot be relicensed, cannot be dual-licensed, and cannot grant a proprietary exception, without tracking down and getting written consent from every person who ever merged a commit. In practice that makes those options permanently unavailable. The CLA keeps them open.

Concretely, it lets the project offer a commercial exception to a party whose use we support but whose lawyers will not accept AGPL, and it lets us move to a different license if the AGPL turns out to be the wrong fit. It does not let anyone take your contribution proprietary while cutting you out of your own work, because clause 2 leaves your rights intact.

If you are not willing to grant this, say so in the pull request. We can usually still take the idea, and one of the maintainers will write the implementation.

## Before you open a pull request

- **Never commit real court records.** No party names, no addresses, no case numbers from live filings, not in tests, not in fixtures, not in a docstring example. Test fixtures use synthetic documents. This is the one rule with no exceptions.
- **Never commit credentials.** API keys go in the environment. `.env` is gitignored; keep it that way.
- Add a test for anything that changes extraction behavior.
- Run the checks: `pytest` in `python/`, `R CMD check` in `r/`.

## Scope of the schema

The field schema in `schema/court_record.schema.json` is the contract between the Python engine, the R wrapper, and every downstream state pipeline. Changing it breaks callers. Open an issue describing the field and the jurisdictions that need it before writing the change.

## Reporting a security or privacy problem

Do not open a public issue. Write to timthomas@berkeley.edu.
