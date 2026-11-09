import os

TRACING_VARIABLES = (
    "LANGSMITH_TRACING",
    "LANGSMITH_TRACING_V2",
    "LANGCHAIN_TRACING",
    "LANGCHAIN_TRACING_V2",
)


def tracing_off() -> None:
    for name in TRACING_VARIABLES:
        os.environ[name] = "false"


tracing_off()
