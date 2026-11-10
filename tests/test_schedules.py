from app.app import app
from app.schemas.schedule import RecommendationCreateRequest


def test_schedule_routes_are_registered() -> None:
    paths = app.openapi()["paths"]

    assert "/api/v1/stores/{store_id}/schedule-recommendations" not in paths
    assert "/api/v1/stores/{store_id}/schedules" not in paths
    assert "/api/v1/stores/{store_id}/shift-templates" in paths
    assert "/api/v1/stores/{store_id}/fixed-schedule" in paths
    assert "/api/v1/stores/{store_id}/schedule-calendar" in paths
    assert "/api/v1/stores/{store_id}/schedule-workers" in paths
    assert "/api/v1/stores/{store_id}/substitute-requests" in paths
    assert "/api/v1/stores/{store_id}/substitute-requests/{request_id}/accept" in paths


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
