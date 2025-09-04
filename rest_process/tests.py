import uvicorn

from process_bigraph import ProcessTypes, discover_packages

from rest_process.server import start_server
from rest_process.processes.grow import GrowProcess


def test_server():
    core = ProcessTypes()
    core = discover_packages(core, True)
    core.register_process('grow', GrowProcess)

    server = start_server(core)
    uvicorn.run(server, host='0.0.0.0', port=22222)


if __name__ == '__main__':
    test_server()
