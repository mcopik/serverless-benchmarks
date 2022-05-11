import uuid
from typing import Dict, Union, List

from sebs.faas.fsm import Generator, State, Task, Switch, Map


class GCPGenerator(Generator):
    def __init__(self, workflow_name: str, func_triggers: Dict[str, str]):
        super().__init__()
        self._workflow_name = workflow_name
        self._func_triggers = func_triggers
        self._map_funcs: Dict[str, str] = dict()

    def postprocess(self, states: List[State], payloads: List[dict]) -> dict:
        payloads.append({"final": {"return": ["${res}"]}})

        definition = {"main": {"params": ["res"], "steps": payloads}}

        return definition

    def encode_task(self, state: Task) -> Union[dict, List[dict]]:
        url = self._func_triggers[state.func_name]

        return [
            {
                state.name: {
                    "call": "http.post",
                    "args": {"url": url, "body": "${res}"},
                    "result": "res",
                }
            },
            {"assign_res_" + state.name: {"assign": [{"res": "${res.body}"}]}},
        ]

    def encode_switch(self, state: Switch) -> Union[dict, List[dict]]:
        return {
            state.name: {
                "switch": [self._encode_case(c) for c in state.cases],
                "next": state.default,
            }
        }

    def _encode_case(self, case: Switch.Case) -> dict:
        cond = "res." + case.var + " " + case.op + " " + str(case.val)
        return {"condition": "${" + cond + "}", "next": case.next}

    def encode_map(self, state: Map) -> Union[dict, List[dict]]:
        id = self._workflow_name + "_" + "map" + str(uuid.uuid4())[0:8]
        self._map_funcs[id] = self._func_triggers[state.func_name]

        return {
            state.name: {
                "call": "experimental.executions.map",
                "args": {"workflow_id": id, "arguments": "${res." + state.array + "}"},
                "result": "res",
            }
        }

    def generate_maps(self):
        for workflow_id, url in self._map_funcs.items():
            yield (
                workflow_id,
                self._export_func(
                    {
                        "main": {
                            "params": ["elem"],
                            "steps": [
                                {
                                    "map": {
                                        "call": "http.post",
                                        "args": {"url": url, "body": "${elem}"},
                                        "result": "elem",
                                    }
                                },
                                {"ret": {"return": "${elem.body}"}},
                            ],
                        }
                    }
                ),
            )
