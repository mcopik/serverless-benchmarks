from typing import Dict, List, Union, Any
import numbers

from sebs.faas.fsm import Generator, State, Task, Switch, Map


class SFNGenerator(Generator):
    def __init__(self, func_arns: Dict[str, str]):
        super().__init__()
        self._func_arns = func_arns

    def postprocess(self, states: List[State], payloads: List[dict]) -> dict:
        state_payloads = super().postprocess(states, payloads)
        definition = {
            "Comment": "SeBS auto-generated benchmark",
            "StartAt": self.root.name,
            "States": state_payloads,
        }

        return definition

    def encode_task(self, state: Task) -> Union[dict, List[dict]]:
        payload: Dict[str, Any] = {"Type": "Task", "Resource": self._func_arns[state.func_name]}

        if state.next:
            payload["Next"] = state.next
        else:
            payload["End"] = True

        return payload

    def encode_switch(self, state: Switch) -> Union[dict, List[dict]]:
        choises = [self._encode_case(c) for c in state.cases]
        return {"Type": "Choice", "Choices": choises, "Default": state.default}

    def _encode_case(self, case: Switch.Case) -> dict:
        type = "Numeric" if isinstance(case.val, numbers.Number) else "String"
        comp = {
            "<": "LessThan",
            "<=": "LessThanEquals",
            "==": "Equals",
            ">=": "GreaterThanEquals",
            ">": "GreaterThan",
        }
        cond = type + comp[case.op]

        return {"Variable": "$." + case.var, cond: case.val, "Next": case.next}

    def encode_map(self, state: Map) -> Union[dict, List[dict]]:
        payload: Dict[str, Any] = {
            "Type": "Map",
            "ItemsPath": "$." + state.array,
            "Iterator": {
                "StartAt": "func",
                "States": {
                    "func": {
                        "Type": "Task",
                        "Resource": self._func_arns[state.func_name],
                        "End": True,
                    }
                },
            },
        }

        if state.next:
            payload["Next"] = state.next
        else:
            payload["End"] = True

        return payload
