# GitHub Workflow (Push/Pull Strategy)

Use this branching model for safe team scaling:

1. `main`
- Production-ready code only.
- Protected branch.

2. `develop`
- Integration branch for upcoming release.

3. Feature branches
- Naming: `feature/<area>-<short-description>`
- Example: `feature/payment-snippe-webhook`

4. Fix branches
- Naming: `fix/<area>-<issue>`
- Example: `fix/agent-heartbeat-timeout`

## Daily Flow

1. Pull latest:
- `git checkout develop`
- `git pull origin develop`
2. Create branch:
- `git checkout -b feature/backend-initial-scaffold`
3. Commit in small chunks:
- `git add .`
- `git commit -m "feat(backend): add initial FastAPI scaffold and migration"`
4. Push branch:
- `git push -u origin feature/backend-initial-scaffold`
5. Open PR to `develop`.
6. After review and CI pass, merge PR.

## Release Flow

1. Merge tested `develop` into `main` via PR.
2. Tag release:
- `git checkout main`
- `git pull origin main`
- `git tag v0.1.0`
- `git push origin v0.1.0`
3. Deploy from `main` tag.

## Rules

1. Never push directly to `main`.
2. Require at least 1 reviewer approval.
3. Require migration review for any DB schema changes.
4. Keep PRs focused and below ~500 lines whenever possible.

