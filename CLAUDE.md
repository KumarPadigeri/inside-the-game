# Inside the Game — Microsoft x Premier League Developer Hackathon

## Goal
Build an AI multi-agent app that turns SYNTHETIC football match events into explainable match recaps.
Deadline: submit by Oct 26, 2026 (official close Oct 27). Target prizes: Best Multi-Agent Orchestration,
Best Azure Cloud Native Integration, and the grand prize if polished.

## Hard rules
- Synthetic data only. Never use real Premier League data, club names, player names, or logos.
- Repo will be PUBLIC: never commit .env, keys, or secrets.
- Numbers come from code, words come from AI: the LLM never calculates statistics itself;
  it calls deterministic Python functions (tools).

## Architecture (Microsoft Agent Framework workflow)
1. Analyst agent   — calls Python stats tools (possession, shots, counterattacks).
2. Retrieval agent — vector search finds similar moments in other synthetic matches.
3. Narrator agent  — writes the recap in fan / analyst / broadcaster style.
4. Verifier agent  — checks every claim against the events; unproven claims go back to Narrator for rewrite.
Each recap sentence must link to the event_ids that prove it (shown in the UI: click a sentence -> see its events).

## Stack
- Python 3.11 + agent-framework (Microsoft Agent Framework), azure-identity, python-dotenv
- Microsoft Foundry: model gpt-5.4-mini, auth via AzureCliCredential (az login), settings in .env
  (FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_MODEL)
- Azure: resource group rg-inside-the-game, region eastus2: Cosmos DB (free tier; matches, recaps, moment
  vectors), Container Apps (FastAPI backend, managed identity), Static Web Apps (React UI, deployed by
  GitHub Actions), Container Registry, Application Insights (tracing). Subscription is a FREE TRIAL: keep
  everything free. Azure Functions (live event replay) not built.
- Frontend: React. Tests: pytest. CI: GitHub Actions.

## Match event format (draft — to be finalized)
{"event_id": 1042, "minute": 63, "team": "Home", "player": "H9", "type": "shot",
 "x": 88, "y": 41, "outcome": "goal", "possession_id": 211}
x, y = pitch position 0-100. possession_id groups the events of one attack.

## Plan
- Week 1 (Oct 2-5): setup  [DONE: tools, Azure, Foundry, hello_agent.py works]
- Week 2 (Oct 6-12): data generator, stats tools + tests, Analyst + Narrator, workflow end to end locally  [DONE]
- Week 3 (Oct 13-19): Verifier loop, Cosmos DB + vector search, Retrieval agent, deploy to Container Apps  [DONE]
  (Azure Function for live replay: skipped unless time allows)
- Week 4 (Oct 20-24): React UI, three styles, Foundry tracing, CI, README + architecture diagram  [DONE early]
- Oct 25-26: demo video (<2 min), pitch, submit

## How to work with me
- I'm learning Microsoft tools: explain changes in simple words before making them.
- Small steps: one feature at a time, run it, then move on.
- Keep code clean, typed, documented; add pytest tests for every stats function.
