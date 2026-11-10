from app.app import app


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
