# Conductor

Conductor is a supervisor agent for one household. It runs on this Mac and uses a local model served by Ollama. This install provides settings, an append-only event log, and a check that this machine is ready.

## Install

From the repository root:

```zsh
/opt/homebrew/bin/python3.12 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

## Check this machine

```zsh
.venv/bin/conductor doctor
```

`doctor` checks the Python version, the data folder, whether Ollama answers on this machine, and whether the configured model is pulled. The default model is `qwen3.8:27b` and the default Ollama address is `http://127.0.0.1:11434`.
