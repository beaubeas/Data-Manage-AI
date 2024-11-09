root_path := justfile_directory()

export PYTHONPATH := root_path + "/ashared:" + root_path + "/engine:" + root_path + "/dashboard"

set dotenv-load := true

install:
    #!/usr/bin/env bash
    set -euxo pipefail
    uv venv -p 3.11
    . .venv/bin/activate
    uv pip install poetry
    pushd engine
    poetry install
    popd
    pushd dashboard
    poetry install
    popd
    pushd ashared
    poetry install
    popd

engine:
    #!/usr/bin/env bash
    set -euxo pipefail
    . .venv/bin/activate
    cd engine
    ./agents.sh

dashboard:
    #!/usr/bin/env bash
    set -euxo pipefail
    . .venv/bin/activate
    cd dashboard
    ./dashboard.sh
