from typing import Any, Dict, Union
import uuid

from fastapi import FastAPI
from fastapi_utils.cbv import cbv
from fastapi_utils.inferring_router import InferringRouter


def make_router(core):
    router = InferringRouter()
    processes = {}

    @cbv(router)
    class ProcessRouter():
        def __init__(self):
            self.core = core
            self.processes = processes

        def find_process_class(self, process):
            return self.core.process_registry.access(process)

        @router.get('/process/{process}/config-schema')
        def read_config_schema(self, process: str):
            process_class = self.find_process_class(process)
            if process_class is None:
                return {'process-not-found': 'true'}
            else:
                return process_class.config_schema

        @router.post('/process/{process}/initialize')
        def post_initialize(self, process: str, config: dict):
            process_id = uuid.uuid4()
            process_class = self.find_process_class(process)
            process_instance = process_class(
                config,
                core=self.core)
            self.processes[str(process_id)] = process_instance

            print(self.processes)
            print(process_id)
            return process_id

        @router.get('/process/{process}/inputs/{process_id}')
        def read_inputs(self, process: str, process_id: str):
            print(self.processes)
            return self.processes[process_id].inputs()

        @router.get('/process/{process}/outputs/{process_id}')
        def read_outputs(self, process: str, process_id: str):
            return self.processes[process_id].outputs()

        @router.post('/process/{process}/update/{process_id}')
        def post_update(self, process: str, process_id: str, data: dict):
            state = data['state']
            interval = data['interval']

            return self.processes[process_id].update(
                state,
                interval)

        @router.post('/process/{process}/end/{process_id}')
        def post_end(self, process: str, process_id: str):
            del self.processes[process_id]

    return router


def start_server(core):
    app = FastAPI()
    router = make_router(core)
    app.include_router(router)

    return app
