# FORJD AGENTS.md

## Project Overview
FORJD is a pure data streaming pipeline platform with configurable workflows. 
Backend: FastAPI + Prefect 3 + Pathway. 
Frontend: Angular with custom forjd-ui library built from scratch.

## Core Principles
- Stability and security over bleeding edge.
- Lightweight and observable.
- Precision Over Chance.
- Build for learning and long-term maintainability.

## Coding Standards
- Backend: Clean FastAPI structure, async where beneficial, strong typing.
- Frontend: Angular standalone components, Signals, custom forjd-ui primitives.
- Docker: Multi-stage, distroless where possible, non-root.
- Always log significant changes to LOG.md with very short lines.

## When Making Changes
- Keep LOG.md entries extremely short.
- Prefer configuration over hardcoding.
- Make workflows configurable via YAML/JSON.

## Tech Stack Priority
1. FastAPI
2. Prefect 3
3. Pathway (streaming)
4. Angular + forjd-ui (from scratch)
5. Dragonfly + Postgres

## Development Flow
- Work in small, testable increments.
- Update LOG.md after meaningful progress.
- Keep dependencies minimal.

Last updated: 2026-07-14