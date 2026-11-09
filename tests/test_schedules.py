from app.app import app
from app.schemas.schedule import RecommendationCreateRequest


def test_schedule_routes_are_registered() -> None:
    paths = app.openapi()["paths"]

    assert "/api/v1/stores/{store_id}/schedule-recommendations" in paths
    assert (
        "/api/v1/stores/{store_id}/schedule-recommendations/{recommendation_id}"
        in paths
    )
    assert "/api/v1/stores/{store_id}/schedules" in paths
    assert "/api/v1/stores/{store_id}/schedules/{schedule_id}" in paths
    assert "/api/v1/stores/{store_id}/schedules/me" in paths


def test_recommendation_request_rejects_shift_outside_period() -> None:
    try:
        RecommendationCreateRequest.model_validate(
            {
                "startDate": "2026-12-01",
                "endDate": "2026-12-07",
                "shifts": [
                    {
                        "date": "2026-12-08",
                        "start": "09:00",
                        "end": "15:00",
                    }
                ],
            }
        )
    except ValueError as exc:
        assert "every shift date" in str(exc)
    else:
        raise AssertionError("invalid request must fail")
