from typing import Any, Dict, Union
import uuid

from fastapi import FastAPI
from fastapi_utils.cbv import cbv
from fastapi_utils.inferring_router import InferringRouter


def make_router(core, process_class):
    router = InferringRouter()
    processes = {}

    @cbv(router)
    class ProcessRouter():
        def __init__(self):
            self.core = core
            self.process_class = process_class
            self.processes = processes

        @router.get('/config-schema')
        def read_config_schema(self):
            return self.process_class.config_schema

        @router.get('/initialize')
        def post_initialize(self, config):
            process_id = uuid.uuid4()
            process_instance = self.process_class(
                config,
                core=self.core)
            self.processes[str(process_id)] = process_instance

            print(self.processes)
            print(process_id)
            return process_id

        @router.get('/inputs')
        def read_inputs(self, process_id: str):
            print(self.processes)
            return self.processes[process_id].inputs()

        @router.get('/outputs')
        def read_outputs(self, process_id: str):
            return self.processes[process_id].outputs()

        @router.get('/update')
        def post_update(self, process_id: str, state: dict[str, Any], interval: float):
            return self.processes[process_id].update(
                state,
                interval)

    return router


def start_server(core, process_class):
    app = FastAPI()
    router = make_router(core, process_class)
    app.include_router(router)

    return app
