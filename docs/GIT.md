# FORJD git conventions

Meaningful commits and a readable history. Enforced locally by the `commit-msg` hook (`npm run install-hooks`).

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/) with an imperative subject that states **why** the change exists (not a file list).

```text
<type>(<optional-scope>)!: <subject>

<optional body — why, trade-offs, follow-ups>
```

| Part | Rule |
|------|------|
| **type** | One of: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, `ci`, `build`, `style`, `revert` |
| **scope** | Optional area: `backend`, `engine`, `frontend`, `forjd-ui`, `sql`, `docs`, `ci`, … |
| **`!`** | Breaking change (also describe in body with `BREAKING CHANGE:`) |
| **subject** | Imperative, ≤72 chars, no trailing period, no `WIP` / `tmp` |
| **body** | Optional; blank line after subject; wrap ~72; focus on motivation |

### Examples

```text
feat(engine): scale workers with advisory leases

Avoid overlapping analytics-rollup ticks across replicas.
```

```text
fix(sql): correct migration 028 index for Postgres 17
```

```text
docs: document commit message and history practice
```

```text
chore(ci): run prettier and typecheck before frontend tests
```

### Allowed exceptions (machine / git)

- `Merge …` / `Revert …` (GitHub merge & revert commits)
- `fixup! …` / `squash! …` (temporary; squash before merge)

### Rejected

- Empty or subject-only noise (`asdf`, `updates`, `wip`)
- Past tense / noun phrases as the whole message (`Fixed bug`, `Changes`)
- Subjects longer than 72 characters
- Trailing period on the subject line

Validate a draft message:

```bash
echo 'feat(frontend): add preferences store' | python3 scripts/check_commit_msg.py
# or: python3 scripts/check_commit_msg.py .git/COMMIT_EDITMSG
```

## Clean history practice

| Practice | Do |
|----------|----|
| **One intent per commit** | Each commit should build, document, or fix one coherent change. Split unrelated edits. |
| **Branch off latest main** | `git fetch origin && git switch -c topic origin/main` |
| **Keep the branch rebaseable** | Prefer `git rebase origin/main` before opening/updating a PR (never rewrite published shared history without coordination). |
| **Squash merge feature PRs** | Default on GitHub: **Squash and merge** so `main` gets one conventional commit per PR. Use the PR title as the commit subject. |
| **Merge commit only when needed** | Reserve merge commits for release trains or intentional multi-commit integrations — not every Cursor agent branch. |
| **No secrets / noise** | Never commit `.env`, tokens, or generated junk (`dist/`, `.angular/`, `target/`). Prefer `npm run format` before commit. |
| **Protect `main`** | No force-push to `main`/`master`. Fix forward with a new commit; amend only unpushed local commits you own. |
| **WIP stays local** | Use `git commit --fixup` / draft PRs; squash before merge. Do not land `WIP` on `main`. |
| **Hooks stay on** | Do not `--no-verify` unless recovering from a broken hook; fix the underlying issue instead. |

### Suggested flow

```bash
npm run install-hooks          # once per clone
git switch -c fix/ready-probe
# … edit …
npm run quality                # before push (includes validate:workflows)
npm run validate:workflows     # when touching backend/workflows/ or detectors
git add -p                     # stage intentional hunks
git commit                     # commit-msg hook checks the message
git push -u origin HEAD
gh pr create                   # title = conventional subject for squash merge
```

### PR titles

PR title should itself be a valid conventional subject (it becomes the squash commit on `main`). Body: short summary + test plan (see user/agent PR template habits).

## Related

- Local quality gates: [`DEV.md`](DEV.md)
- Tests / CI map: [`TESTING.md`](TESTING.md)
- Product constraints: [`../AGENTS.md`](../AGENTS.md)
