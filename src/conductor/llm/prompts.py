import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from string import Template

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_NAME = re.compile(r"^[a-z][a-z0-9_]{0,31}\.v[1-9][0-9]{0,2}$")


class PromptError(Exception):
    pass


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    text: str
    sha256: str
    fields: tuple[str, ...]


def load_template(name: str, folder: Path | None = None) -> PromptTemplate:
    if _NAME.fullmatch(name) is None:
        raise PromptError(f"prompt {name}: not a valid template name")
    directory = PROMPTS_DIR if folder is None else folder
    path = directory / f"{name}.md"
    if not path.is_file():
        raise PromptError(f"prompt {name}: not found")
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise PromptError(f"prompt {name}: not UTF-8") from None
    template = Template(text)
    if not template.is_valid():
        raise PromptError(f"prompt {name}: not a valid template")
    return PromptTemplate(
        name,
        text,
        hashlib.sha256(raw).hexdigest(),
        tuple(sorted(template.get_identifiers())),
    )
