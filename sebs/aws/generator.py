from typing import Dict, List, Union, Any
import numbers
import uuid
import json

from sebs.faas.fsm import Generator, State, Task, Switch, Map, Repeat, Loop, Parallel

def list2dict(lst, key):
    dct = {}
    for item in lst:
        keyvalue = item[key]
        del item[key]
        dct[keyvalue] = item
    return dct

class SFNGenerator(Generator):
    def __init__(self, func_arns: Dict[str, str]):
        super().__init__()
        self._func_arns = func_arns

    def postprocess(self, payloads: List[dict]) -> dict:

        state_payloads = list2dict(payloads, "Name")
        #replace Name entry for parallel states
        #FIXME parallel states could also contain parallel states --> make recursive
        for name in state_payloads:
            if "Branches" in state_payloads[name]:
                for branch in state_payloads[name]["Branches"]:
                    branch["States"] = list2dict(branch["States"], "Name")

        definition = {
            "Comment": "SeBS auto-generated benchmark",
            "StartAt": self.root.name,
            "States": state_payloads,
        }

        return definition

    def encode_task(self, state: Task) -> Union[dict, List[dict]]:
        payload: Dict[str, Any] = {
            "Name": state.name,
            "Type": "Task",
            "Resource": self._func_arns[state.func_name],
            "Parameters": {
                "request_id.$": "$.request_id",
                "payload.$": "$.payload",
            },
            "ResultPath": "$.payload"
        }

        if state.next:
            payload["Next"] = state.next
        else:
            payload["End"] = True

        return payload
    
    def encode_parallel(self, state: Parallel) -> Union[dict, List[dict]]:
        states = {n: State.deserialize(n, s) for n, s in state.funcs.items()}
        parallel_funcs = [self.encode_state(t) for t in states.values()]
        
        #FIXME: support more than two branches
        for func in parallel_funcs:
            func["ResultPath"] = "$." + func["Name"]

        payload: Dict[str, Any] = {
            "Name": state.name,
            "Type": "Parallel",
            "Branches": [
                {
                    "StartAt": parallel_funcs[0]["Name"],
                    "States": [ parallel_funcs[0] ], 
                },
                {
                    "StartAt": parallel_funcs[1]["Name"],
                    "States": [ parallel_funcs[1] ], 
                },
            ],
            "ResultSelector": {
                "payload": {
                    parallel_funcs[0]["Name"] + ".$": "$[0]." + parallel_funcs[0]["Name"],
                    parallel_funcs[1]["Name"] + ".$": "$[1]." + parallel_funcs[1]["Name"],
                },
                "request_id.$": "$[0].request_id",
            }
        }
        
        if state.next:
            payload["Next"] = state.next
        else:
            payload["End"] = True

        return payload



    def encode_switch(self, state: Switch) -> Union[dict, List[dict]]:
        choises = [self._encode_case(c) for c in state.cases]
        return {"Name": state.name, "Type": "Choice", "Choices": choises, "Default": state.default}

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

        return {"Variable": "$.payload" + case.var, cond: case.val, "Next": case.next}

    def encode_map(self, state: Map) -> Union[dict, List[dict]]:
        map_func_name = "func_" + str(uuid.uuid4())[:8]

        payload: Dict[str, Any] = {
            "Name": state.name,
            "Type": "Map",
            "ItemsPath": "$.payload." + state.array,
            "Parameters": {
                "request_id.$": "$.request_id",
                #"payload.$": "$$.Map.Item.Value",
            },
            "Iterator": {
                "StartAt": map_func_name,
                "States": {
                    map_func_name: {
                        "Type": "Task",
                        "Resource": self._func_arns[state.func_name],
                        "End": True,
                    }
                },
            },
            "ResultPath": "$.payload." + state.array
        }

        if state.common_params:
            entries = {}
            entries["array_element.$"] = "$$.Map.Item.Value"
            params = state.common_params.split(",")
            for param in params:
                entries[param + ".$"] = "$.payload." + param
                #payload["Parameters"]["payload.$"] += "$.payload." + param

            payload["Parameters"]["payload"] = entries
        else: 
            payload["Parameters"]["payload.$"] = "$$.Map.Item.Value"


        if state.next:
            payload["Next"] = state.next
        else:
            payload["End"] = True

        return payload

    def encode_loop(self, state: Loop) -> Union[dict, List[dict]]:
        map_state = Map(state.name, state.func_name, state.array, state.next)
        payload = self.encode_map(map_state)
        payload["MaxConcurrency"] = 1
        payload["ResultSelector"] = dict()
        payload["ResultPath"] = "$." + str(uuid.uuid4())[:8]

        return payload
