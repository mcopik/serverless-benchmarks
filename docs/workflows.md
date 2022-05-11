## Workflows

### Installation

SeBS makes use of [redis](https://redis.io) in order to make reliable and accurate measurements during the execution of workflows. Ideally, the redis instance should be deployed in the same cloud region such that the write latency is minimal.
Because not all platforms allow connections from a workflow execution to a VPC cache, it proved to be easiest to just deploy a VM and have that machine host redis. Make sure to open port `6379` and admit connections in your VPC accordingly. Redis can be hosted as follows:
```bash
docker run --network=host --name redis -d redis redis-server --save 60 1 --loglevel warning
```

### Definition

All platforms accept different scheduling schemes which makes it cumbersome to run the same tests on different platforms. SeBS defines a workflow scheduling language that is transcribed to the desired platform's scheme.
The schedule is represented by a state machine and is encoded in a JSON file. It starts with the following keys:

```json
{
    "root": "first_state",
    "states": {
    }
}
```

`root` defines the initial state to start the workflow from, while `states` holds a dictionary of `(name, state)` tuples. The following state types are supported.

#### Task

A task state is the most basic state: it executes a serverless function.

```json
{
    "type": "task",
    "func_name": "a_very_useful_func",
    "next": "postprocess_the_useful_func"
},
```

`func_name` is the name of the file in the benchmark directory, `next` sets the state with which to follow.

#### Switch

A switch state makes it possible to encode basic control flow.

```json
{
    "type": "switch",
    "cases": [
        {
            "var": "people.number",
            "op": "<",
            "val": 10,
            "next": "few_people"
        },
        {
            "var": "people.number",
            "op": ">=",
            "val": 10,
            "next": "many_people"
        }
    ],
    "default": "few_people"
}
```

This state transcribes to the following Python expression:
```python
if people.number < 10:
    few_people()
elif people.number >= 10:
    many_people()
else:
    few_people()
```

#### Map

A map state takes a list as input and processes each element in parallel using the given function:

```json
{
    "type": "map",
    "array": "people",
    "func_name": "rename_person",
    "next": "save"
}
```

`array` defines the list to be processed, while `func_name` is the name of the file in the benchmark directory. Note that in contrast to a `task`'s function, this one receives only an element of the given array, not the entire running variable.
