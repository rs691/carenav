# OpenCode — personal guide

A short note for you: what OpenCode is, how to use it on your machine, and what it’s good for (vs Cursor / Codex / CareNav).

---

## What it is

**OpenCode** is an open-source **AI coding agent**. It lives mainly in the terminal (also desktop / IDE extensions). You point it at a folder, ask it to do coding work, and it can:

- Read and edit files  
- Run shell commands  
- Use LSP / project context  
- Open multiple agent sessions  

Think of it as **Claude Code / Cursor Agent / Codex CLI**, but open-source and model-agnostic: free Zen models, ChatGPT login, Copilot, OpenRouter, **local Ollama**, etc.

Website: [https://opencode.ai](https://opencode.ai)  
Docs: [https://opencode.ai/docs](https://opencode.ai/docs)

---

## What it is *not*

| Thing | OpenCode? |
|---|---|
| ChatGPT Pro / Edu “included coding” | No — separate app; may *log in* with that account for usage |
| CareNav member chat (`/chat`) | No — that’s your FastAPI + Ollama/OpenAI stack |
| Automatic API credits for CareNav | No — same rule as Codex: ChatGPT ≠ Platform API billing |
| A replacement for Cursor | Overlap, not a full IDE; often used *alongside* Cursor |

Use **Cursor** for day-to-day editing in the IDE.  
Use **OpenCode** when you want a terminal agent on a repo (or a second agent in parallel).  
Use **CareNav + Ollama** for the product’s member answers.

---

## What you can do with it (personally)

Practical jobs that fit how you work:

1. **Scaffold or refactor** a feature in `carenav` (“add an agent”, “wire this env var”, “fix this ingest script”).  
2. **Explore a repo** you didn’t write: “where is JWT verified?”, “trace POST /chat”.  
3. **Write tests / docs** from the CLI without living in the editor.  
4. **Run commands** (tests, ingest, docker) as part of an agent loop.  
5. **Work offline / cheap** with **Ollama** (you already have `llama3.2:3b` and `qwen2.5-coder:3b`).  
6. **Use ChatGPT Plus/Pro login** inside OpenCode for stronger models when local isn’t enough — still not the same as CareNav’s `OPENAI_API_KEY`.  
7. **Share a session link** when you want a transcript for later (if that feature is enabled on your build).

Good fits: focused coding tasks, CLI-heavy workflows, local-model experiments.  
Weaker fits: pixel-perfect frontend polish (Cursor + preview is nicer), long product design chats (stay in Cursor).

---

## Install / fix on your Windows machine

You already have an `opencode` npm shim, but the binary failed with *“not a valid application for this OS platform”* — usually a bad/wrong-arch global install. Prefer one of these:

### Option A — Ollama launcher (nice if you stay local)

```powershell
# Ollama running, then:
ollama launch opencode
# or config only:
ollama launch opencode --config
```

### Option B — Official install

Follow current install steps on [opencode.ai](https://opencode.ai) (they change; use their docs). After install:

```powershell
opencode --version
cd F:\carenav
opencode
```

If the old npm global is broken:

```powershell
npm uninstall -g opencode-ai
```

Then reinstall via the official method so the Windows binary matches your machine.

---

## How to use it day to day

### 1. Open a project

```powershell
cd F:\carenav
opencode
```

You’re in a chat with tools. Ask in plain English, e.g.:

- “Summarize how auth works in `middleware/auth.py` and the frontend login flow.”  
- “Add a smoke script that hits `/health` and prints the result.”  
- “Find why RAG returns no chunks and fix the Qdrant client call.”

### 2. Pick a model

Inside OpenCode, use `/models` (or the model picker) and choose:

- **Local / free:** Ollama models you pulled  
- **Cloud:** Zen (OpenCode’s curated free/paid routes), ChatGPT login, Copilot, OpenRouter, etc.

For **coding** on your laptop, prefer a **coder** model (e.g. `qwen2.5-coder:3b`) over a general chat model (`llama3.2:3b`).

### 3. Useful mental model for prompts

Be specific about scope and constraints:

> In `F:\carenav`, only touch `rag/` and `core/llm.py`. Don’t change frontend. Explain the diff when done.

Same habits as Cursor Agent: small scope → fewer bad edits.

### 4. Parallel sessions

You can run more than one OpenCode session on the same repo (e.g. one fixing ingest, one drafting README). Don’t let two agents edit the same files at once.

---

## Using it with your Ollama setup

You already run Ollama for CareNav (`LLM_PROVIDER=ollama`). OpenCode can share that server.

### Context length (important)

OpenCode does tool loops (read → edit → run). Ollama’s default context (~4k) is often **too small**, which shows up as broken tool calls / weird failures.

Before starting Ollama (or as a user/system env var):

```powershell
$env:OLLAMA_CONTEXT_LENGTH = "65536"
```

Then restart the Ollama app/service. OpenCode docs recommend **64k+** for agent work.

### Example project config

Create `F:\carenav\opencode.json` (or user config under `%USERPROFILE%\.config\opencode\opencode.json`):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "ollama": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Ollama",
      "options": {
        "baseURL": "http://127.0.0.1:11434/v1"
      },
      "models": {
        "qwen2.5-coder:3b": { "name": "Qwen2.5 Coder 3B" },
        "llama3.2:3b": { "name": "Llama 3.2 3B" }
      }
    }
  },
  "model": "ollama/qwen2.5-coder:3b"
}
```

On Windows, prefer `127.0.0.1` over `localhost` if anything flakes.

Pull models if needed:

```powershell
ollama pull qwen2.5-coder:3b
ollama pull llama3.2:3b
```

---

## Auth options (quick map)

| Sign-in / provider | What you get | Notes for you |
|---|---|---|
| **Ollama (local)** | Free, private, offline-ish | Best match to CareNav free path; weaker than big cloud models |
| **OpenCode Zen** | Curated models for agents | Easy “just works” cloud option from OpenCode |
| **ChatGPT Plus/Pro** | Use that subscription inside OpenCode | Edu/Pro helps *OpenCode*, not CareNav API credits |
| **GitHub Copilot** | Use Copilot entitlement | If you already pay for Copilot |
| **OpenRouter / other APIs** | Pay-per-token variety | Separate keys/billing |

None of these fill CareNav’s `OPENAI_API_KEY` quota. Product runtime stays on `LLM_PROVIDER=ollama` (or OpenAI Platform billing).

---

## How this fits *your* stack

```
You personally
├── Cursor          → main IDE + agent in the editor
├── OpenCode        → optional terminal coding agent (same or other models)
├── ChatGPT Pro/Edu → chat app + (if linked) OpenCode cloud usage
└── CareNav runtime
    ├── Frontend (Next)  → auth/UI
    ├── FastAPI agents   → member answers
    └── Ollama / OpenAI  → LLM_PROVIDER in .env
```

Suggested habit:

- Building CareNav features → Cursor (and OpenCode if you want a second agent).  
- Testing member answers → browser + API with Ollama.  
- When OpenAI credits exist again → `LLM_PROVIDER=openai` only for CareNav, not required for OpenCode.

---

## Privacy / safety (short)

- OpenCode markets itself as not storing your code for their cloud product path; **local Ollama keeps prompts on your machine**.  
- Don’t paste production secrets into any agent chat. Your `.env` should stay gitignored.  
- Review diffs before committing — agents still hallucinate.

---

## Minimal “start today” checklist

1. Fix OpenCode install (or `ollama launch opencode`).  
2. Set `OLLAMA_CONTEXT_LENGTH=65536` and restart Ollama.  
3. `cd F:\carenav` → start OpenCode → pick `qwen2.5-coder:3b`.  
4. Ask one small task (“explain `core/llm.py` and how to switch providers”).  
5. Keep Cursor for UI work; keep CareNav chat on Ollama until you buy API credits.

---

## Links

- [opencode.ai](https://opencode.ai)  
- [Ollama ↔ OpenCode integration](https://docs.ollama.com/integrations/opencode)  
- CareNav free LLM path: `LLM_PROVIDER=ollama` in `.env`, models `llama3.2:3b` + `nomic-embed-text`
