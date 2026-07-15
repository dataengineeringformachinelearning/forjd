"""First Prefect flow stub.

This is intentionally tiny. Calling `hello()` talks to Prefect API
(PREFECT_API_URL). With Compose: `docker compose up` then:

  uv run python -c "from app.pipelines.hello import hello; print(hello())"

Without a server, import the flow only — do not call it yet.
Deploy / schedule comes later.
"""

from prefect import flow, task


@task
def greet(name: str) -> str:
    return f"hello, {name}"


@flow(name="forjd-hello", log_prints=True)
def hello(name: str = "forjd") -> str:
    message = greet(name)
    print(message)
    return message
