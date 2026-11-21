from typing import Annotated

from pydantic import Field

from conductor.registry import McpServer

SERVER = McpServer("finances", env=("FIN_DATA_DIR",))

Month = Annotated[str, Field(pattern=r"^([0-9]{4}-(0[1-9]|1[0-2]))?$")]
Label = Annotated[str, Field(max_length=100)]
