# Contributing to QuantumCare

Follow [INSTALL.md](INSTALL.md) and use a separate local database with fictional
data. Review [the documentation index](docs/README.md) before changing a workflow.

## Propose and make a change

For bug reports, include expected and actual behavior, reproduction steps,
versions and redacted logs. Never include patient information, credentials or
private keys in a public issue.

```sh
git switch -c docs/describe-your-change
# Edit the relevant files.
git diff --check
git diff
```

Choose `fix/`, `feat/`, `test/` or `docs/` as appropriate. Keep changes focused
and document behavior changes. Test authorization refusals and cryptographic
failure cases as well as successful requests.

## Validate and submit

Use the affected component's test commands in [INSTALL.md](INSTALL.md).
The [CI workflow](.github/workflows/deploy.yml) defines the complete checks and
external test services. Report what actually ran, including skipped integrations.
For documentation-only changes, check links, commands and consistency rather
than running unrelated integration tests.

```sh
git add path/to/changed-file
git commit -m "docs: explain the installation prerequisites"
git push -u origin HEAD
```

Fork first if you do not have write access. Open a pull request against `main`
describing the problem, resulting behavior, validation and any migration steps.
Inspect the staged diff; do not stage `.env`, account credential lists, database
backups or generated build directories.

## History and maintenance

Commit meaningful increments with descriptive messages. Preserve published
history; do not create empty commits or rewrite dates to suggest activity.
Keep documentation with the change it describes. CI runs on pushes and pull
requests targeting `main`; maintainers should review its actual results.
Past history is evidence of past activity, not a guarantee of future maintenance.

## License and security reports

Contributions are distributed under the [MIT license](LICENSE). Retain
third-party notices; this license does not replace dependency licenses.
For vulnerabilities, use GitHub's private vulnerability-reporting option if
enabled, or arrange private contact with the maintainer before sharing exploit
details. Do not publish secrets or real patient data.
