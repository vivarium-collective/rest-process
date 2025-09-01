


from rest_process.server import start_server
from rest_process.processes.grow import GrowProcess

import uvicorn

from process_bigraph import ProcessTypes


def test_server():
    core = ProcessTypes()
    server = start_server(core, GrowProcess)
    uvicorn.run(server, host='0.0.0.0', port=22222)


if __name__ == '__main__':
    test_server()
