from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from accounts.models import User
from desk.management.commands.seed_demo_data import CLIENTS, EPISODE_IDS
from desk.models import (
    Assignment,
    DatasetRequest,
    DemoSeedRecord,
    Episode,
    ExportJob,
    StatusHistory,
)
from desk.services import workflow

pytestmark = pytest.mark.django_db


def seed():
    output = StringIO()
    call_command("seed_demo_data", stdout=output)
    return output.getvalue()


@pytest.fixture
def demo_users():
    call_command("seed_users", stdout=StringIO())


def snapshot():
    return {
        model.__name__: list(model.objects.order_by("pk").values())
        for model in (User, DatasetRequest, Assignment, StatusHistory, ExportJob, DemoSeedRecord)
    }


def test_supplied_csv_workflow_counts_actors_and_rerun(demo_users):
    assert "10 created, 0 skipped, 0 conflicting" in seed()
    assert Episode.objects.count() == 172
    assert Assignment.objects.count() == ExportJob.objects.count() == 14
    assert Assignment.objects.values("episode").distinct().count() == 14
    assert not Assignment.objects.filter(episode__quality="bad").exists()
    assert set(ExportJob.objects.values_list("status", flat=True)) == {"pending"}
    for email in CLIENTS:
        requests = DatasetRequest.objects.filter(client__email=email)
        assert set(requests.values_list("status", flat=True)) == {
            "submitted", "in_progress", "delivered", "accepted", "rejected",
        }
        for request in requests:
            expected = ["submitted"]
            if request.status != "submitted":
                expected += ["in_progress"]
            if request.status in ("delivered", "accepted", "rejected"):
                expected += ["delivered"]
                assert request.assignments.count() >= request.episodes_requested
            if request.status in ("accepted", "rejected"):
                expected += [request.status]
            history = list(request.history.order_by("created_at", "id"))
            assert [entry.new_status for entry in history] == expected
            assert [entry.previous_status for entry in history] == [None, *expected[:-1]]
            for entry in history:
                assert entry.actor.email == (
                    email if entry.new_status in ("submitted", "accepted", "rejected")
                    else "ops1@example.com"
                )
    before = snapshot()
    assert "0 created, 10 skipped, 0 conflicting" in seed()
    assert snapshot() == before


def test_existing_work_passwords_and_later_transitions_preserved(demo_users, client_a, make_request):
    personal = make_request(client_a)
    seed()
    request = DatasetRequest.objects.get(client__email=CLIENTS[0], status="submitted")
    workflow.transition(request_id=request.pk, actor=User.objects.get(email="ops1@example.com"), target="in_progress")
    before = snapshot()
    seed()
    assert snapshot() == before
    personal.refresh_from_db()
    assert personal.status == "submitted"
    assert not DemoSeedRecord.objects.filter(request=personal).exists()


def test_unregistered_identifier_collision_is_not_adopted(demo_users, client_a, make_request):
    existing = make_request(client_a)
    existing.notes = f"Public demo: demo-v1/{CLIENTS[0]}/submitted"
    existing.save()
    before = list(existing.history.values())
    assert "9 created, 0 skipped, 1 conflicting" in seed()
    existing.refresh_from_db()
    assert existing.client == client_a
    assert list(existing.history.values()) == before
    assert not DemoSeedRecord.objects.filter(request=existing).exists()


def test_registry_owner_collision_is_reported(demo_users, client_a, make_request):
    existing = make_request(client_a)
    DemoSeedRecord.objects.create(key=f"demo-v1/{CLIENTS[0]}/submitted", request=existing)
    assert "9 created, 0 skipped, 1 conflicting" in seed()
    existing.refresh_from_db()
    assert existing.client == client_a


def test_episode_collisions_and_reservations_are_preserved(demo_users, make_episode, client_a, make_request):
    # Every candidate ID is existing, different user work. The importer reports
    # conflicts; the seed must not overwrite or allocate any of those rows.
    for episode_id in EPISODE_IDS:
        make_episode(episode_id=episode_id, duration_seconds="1.00")
    existing = make_request(client_a, status="in_progress")
    link = Assignment.objects.create(
        request=existing, episode=Episode.objects.first(),
        assigned_by=User.objects.get(email="ops1@example.com"),
    )
    assert "2 created, 0 skipped, 8 conflicting" in seed()
    assert Episode.objects.filter(episode_id__in=EPISODE_IDS, duration_seconds=1).count() == 16
    assert Assignment.objects.get(pk=link.pk).request == existing
    assert Assignment.objects.count() == 1
    assert StatusHistory.objects.filter(request__demoseedrecord__isnull=False).count() == 2


@pytest.mark.parametrize("change", ["role", "inactive", "name", "personal"])
def test_conflicting_demo_identity_aborts_without_changes(demo_users, settings, change):
    user = User.objects.get(email=CLIENTS[0])
    if change == "role":
        user.role = "admin"
    elif change == "inactive":
        user.is_active = False
    elif change == "name":
        user.name = "Personal work"
    else:
        settings.PERSONAL_ADMIN_EMAIL = user.email
    user.save()
    before = snapshot()
    with pytest.raises(CommandError, match="missing or conflicting"):
        seed()
    assert snapshot() == before
    assert Episode.objects.count() == 0


def test_seeded_requests_are_client_isolated(demo_users, api):
    seed()
    api.force_login(User.objects.get(email=CLIENTS[0]))
    response = api.get("/api/requests").json()
    assert response["count"] == 5
    other = DatasetRequest.objects.filter(client__email=CLIENTS[1]).first()
    for suffix in ("", "/history", "/assignments"):
        assert api.get(f"/api/requests/{other.pk}{suffix}").status_code == 404
