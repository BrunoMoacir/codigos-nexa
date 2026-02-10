from app.runner import NexaRunner


def test_full_runner_pipeline():
    runner = NexaRunner(mode="dev")

    result = runner.run(horizon_days=30)

    assert result["status"] == "success"
    assert result["projections"]["safe_to_spend"].safe_to_spend_total > 0

    print("\n✅ NexaRunner End-to-End OK")
