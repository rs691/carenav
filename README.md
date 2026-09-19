# ── Environment ───────────────────────────────────────────────────────────────
.env
.env.local
.env.*.local

# ── Python ────────────────────────────────────────────────────────────────────
__pycache__/
*.py[cod]
*.pyo
*.pyd
.Python
*.egg
*.egg-info/
dist/
build/
eggs/
parts/
var/
sdist/
develop-eggs/
.installed.cfg
lib/
lib64/

# ── Virtual environments ───────────────────────────────────────────────────────
.venv/
venv/
env/
ENV/

# ── uv ────────────────────────────────────────────────────────────────────────
.uv/
uv.lock

# ── Testing ───────────────────────────────────────────────────────────────────
.pytest_cache/
.coverage
coverage.xml
htmlcov/
*.coveragerc
/reports/

# ── Ruff / linting ────────────────────────────────────────────────────────────
.ruff_cache/

# ── Evals / golden sets ───────────────────────────────────────────────────────
evals/results/
evals/runs/
*.eval.json

# ── RAG / documents ───────────────────────────────────────────────────────────
# Never commit raw plan documents — PHI risk
rag/docs/
rag/raw/
rag/uploads/
*.pdf
*.csv
!evals/golden_set.csv

# ── Prompts — keep YAMLs, never compiled/cached versions ──────────────────────
prompts/__pycache__/
prompts/*.compiled

# ── Logs ──────────────────────────────────────────────────────────────────────
logs/
*.log
*.log.*

# ── IDEs ──────────────────────────────────────────────────────────────────────
.vscode/
.idea/
*.suo
*.ntvs*
*.njsproj
*.sln
*.sw?

# ── OS ────────────────────────────────────────────────────────────────────────
.DS_Store
Thumbs.db
desktop.ini

# ── Azure / cloud credentials ─────────────────────────────────────────────────
*.pem
*.key
*.pfx
*.cer
azureauth.json
local.settings.json