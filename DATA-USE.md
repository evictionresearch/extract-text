# Data use policy

The AGPL governs the code in this repository. It does not govern court records, and it cannot. A copyright license reaches the software, not the output of running it, and under US law facts and non-creative compilations of facts are not copyrightable at all. A case number, a filing date, and a party name extracted from a public document are not something this project can license to you.

What this project can control is access. This document sets the terms for any dataset published by the Eviction Research Network under this repository, any data made available through a request process, and any collaboration that involves us handing over extracted records. Those terms are contract, not copyright, and they reach where the license does not.

## Scope

This policy applies to:

1. Datasets published in or alongside this repository
2. Extracted records supplied to a collaborator by ERN or CiDR Lab
3. Any hosted service or API built on this code by the maintainers

It does not apply to records you extract yourself from public sources using this software. Those are yours. `ETHICS.md` states what we ask of you anyway.

## Prohibited uses

By accessing data under this policy you agree not to use it, in whole or in part, directly or through a third party, to:

1. Produce, sell, or contribute to a tenant screening report, a consumer report as defined by the Fair Credit Reporting Act, or any product that scores, ranks, flags, or filters rental applicants
2. Compile or distribute a list of individuals for the purpose of denying, conditioning, or pricing housing
3. Identify or locate individuals for debt collection
4. Identify or locate individuals for immigration enforcement or any other enforcement action
5. Sell, license, or otherwise transfer the data to a data broker, credit bureau, or screening company
6. Attempt to re-identify individuals in any aggregated or de-identified extract
7. Train, fine-tune, or evaluate a model whose purpose is any of the above

These are specific on purpose. A term a court cannot interpret is a term that binds nobody, so "do not use this for evil" is not written here.

## Required practices

1. **Cite the source.** Publications and products using this data cite the dataset and this repository.
2. **Do not republish record-level data with names.** Aggregate to a geography, or strip party names, before publishing. If your work requires record-level identified data to be public, talk to us first.
3. **Store it like it identifies people, because it does.** Access controls appropriate to personally identifying information, no shared credentials, no public buckets.
4. **Report leaks.** If identified data is exposed, tell the maintainer within 72 hours.
5. **Delete on request.** If access is revoked, delete the supplied data and confirm in writing.

## Derived data

Aggregates, model outputs, and statistics computed from data supplied under this policy inherit it. Publishing a county-level filing rate is fine and encouraged. Publishing a table that lets a reader recover who was filed against is not.

## Enforcement

Breach ends access immediately. We may also state publicly what happened, notify affected institutions and funders, and pursue the ordinary remedies available for breach of an access agreement.

## Contact

Tim Thomas, Eviction Research Network, timthomas@berkeley.edu.
