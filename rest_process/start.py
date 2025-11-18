import fire
import uvicorn

from process_bigraph import ProcessTypes, discover_packages

from rest_process.server import start_server


def start(host='0.0.0.0', port=22222):
    core = ProcessTypes()
    core = discover_packages(core)
    server = start_server(core)

    uvicorn.run(
        server,
        host=host,
        port=port)


if __name__ == '__main__':
    fire.Fire(start)
