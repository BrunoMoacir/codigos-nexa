"""
Testa importação e inicialização do runner.
"""

from app.runner import NexaRunner


def test_runner_import():
    runner = NexaRunner(mode="dev")
    assert runner is not None

    print("\n✅ Runner Import OK")
