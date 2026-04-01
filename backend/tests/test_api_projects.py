"""
Tests for app/api/v1/endpoints/projects.py

Covers:
- create_project: successful creation
- read_projects: listing with/without deleted, pagination
- read_project: get by ID, 404, 403
- update_project: success, 404, 403
- delete_project: soft delete, 404, 403
- restore_project: success, 404, 403
- permanently_delete_project: success, 404, 403
"""

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from app.api.v1.endpoints.projects import (
    create_project,
    read_projects,
    read_project,
    update_project,
    delete_project,
    restore_project,
    permanently_delete_project,
    ProjectCreate,
    ProjectUpdate,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

USER_ID = "user-001"
OTHER_USER_ID = "user-002"


def _make_user(user_id=USER_ID, is_superuser=False):
    user = MagicMock()
    user.id = user_id
    user.is_superuser = is_superuser
    return user


def _make_project(
    project_id="proj-001",
    owner_id=USER_ID,
    is_active=True,
    source_type="repository",
    repo_url="https://github.com/test/repo",
):
    proj = MagicMock()
    proj.id = project_id
    proj.name = "Test Project"
    proj.description = "A test project"
    proj.source_type = source_type
    proj.repository_url = repo_url
    proj.repository_type = "github"
    proj.default_branch = "main"
    proj.programming_languages = '["python"]'
    proj.owner_id = owner_id
    proj.is_active = is_active
    proj.created_at = datetime.now(timezone.utc)
    proj.updated_at = None
    proj.owner = MagicMock()
    proj.owner.id = owner_id
    proj.owner.email = f"{owner_id}@example.com"
    proj.owner.full_name = "Test User"
    proj.owner.avatar_url = None
    proj.owner.role = "member"
    return proj


def _scalar_result(obj):
    """Build a mock SQLAlchemy result that returns obj via scalars().first()."""
    result = MagicMock()
    scalars = MagicMock()
    scalars.first.return_value = obj
    result.scalars.return_value = scalars
    return result


def _scalars_all_result(objects):
    """Build a mock SQLAlchemy result that returns a list via scalars().all()."""
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = objects
    result.scalars.return_value = scalars
    return result


def _mock_db_for_create():
    """Build a db mock suitable for create_project (add, commit, refresh)."""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    async def fake_refresh(obj):
        obj.id = "new-proj-001"

    db.refresh = AsyncMock(side_effect=fake_refresh)
    return db


# ===================================================================
# create_project
# ===================================================================

class TestCreateProject:

    @pytest.mark.asyncio
    async def test_create_repository_project(self):
        """Create a repository-type project."""
        db = _mock_db_for_create()
        user = _make_user()

        project_in = ProjectCreate(
            name="My Repo Project",
            source_type="repository",
            repository_url="https://github.com/org/repo",
            repository_type="github",
            description="Test repo project",
            default_branch="main",
            programming_languages=["python"],
        )

        result = await create_project(db=db, project_in=project_in, current_user=user)

        db.add.assert_called_once()
        db.commit.assert_called_once()
        # The returned object should have been refreshed
        assert result.id == "new-proj-001"

    @pytest.mark.asyncio
    async def test_create_zip_project_ignores_repo_url(self):
        """ZIP-type projects should not store a repository_url."""
        db = _mock_db_for_create()
        user = _make_user()

        project_in = ProjectCreate(
            name="My Zip Project",
            source_type="zip",
            repository_url="https://github.com/org/repo",  # should be ignored
        )

        result = await create_project(db=db, project_in=project_in, current_user=user)

        db.add.assert_called_once()
        # Inspect the object passed to db.add
        added_obj = db.add.call_args[0][0]
        assert added_obj.repository_url is None
        assert added_obj.source_type == "zip"


# ===================================================================
# read_projects
# ===================================================================

class TestReadProjects:

    @pytest.mark.asyncio
    async def test_list_projects_returns_active_only(self):
        """By default, only active (non-deleted) projects are returned."""
        db = AsyncMock()
        proj1 = _make_project(project_id="p1", is_active=True)
        db.execute.return_value = _scalars_all_result([proj1])

        user = _make_user()
        result = await read_projects(db=db, current_user=user)

        assert len(result) == 1
        assert result[0].id == "p1"

    @pytest.mark.asyncio
    async def test_list_projects_includes_deleted(self):
        """When include_deleted=True, all projects are returned."""
        db = AsyncMock()
        proj1 = _make_project(project_id="p1", is_active=True)
        proj2 = _make_project(project_id="p2", is_active=False)
        db.execute.return_value = _scalars_all_result([proj1, proj2])

        user = _make_user()
        result = await read_projects(
            include_deleted=True, db=db, current_user=user
        )

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_projects_empty(self):
        """Returns empty list when user has no projects."""
        db = AsyncMock()
        db.execute.return_value = _scalars_all_result([])

        user = _make_user()
        result = await read_projects(db=db, current_user=user)

        assert result == []


# ===================================================================
# read_project
# ===================================================================

class TestReadProject:

    @pytest.mark.asyncio
    async def test_read_project_success(self):
        """Returns project when it exists and belongs to current user."""
        proj = _make_project()
        db = AsyncMock()
        db.execute.return_value = _scalar_result(proj)

        user = _make_user()
        result = await read_project(id="proj-001", db=db, current_user=user)

        assert result.id == "proj-001"

    @pytest.mark.asyncio
    async def test_read_project_not_found(self):
        """Raises 404 when project does not exist."""
        db = AsyncMock()
        db.execute.return_value = _scalar_result(None)

        user = _make_user()
        with pytest.raises(HTTPException) as exc_info:
            await read_project(id="nonexistent", db=db, current_user=user)
        assert exc_info.value.status_code == 404
        assert "项目不存在" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_read_project_wrong_owner_forbidden(self):
        """Raises 403 when project belongs to another user."""
        proj = _make_project(owner_id=OTHER_USER_ID)
        db = AsyncMock()
        db.execute.return_value = _scalar_result(proj)

        user = _make_user()
        with pytest.raises(HTTPException) as exc_info:
            await read_project(id="proj-001", db=db, current_user=user)
        assert exc_info.value.status_code == 403


# ===================================================================
# update_project
# ===================================================================

class TestUpdateProject:

    @pytest.mark.asyncio
    async def test_update_project_name(self):
        """Successfully update a project's name."""
        proj = _make_project()
        db = AsyncMock()
        db.execute.return_value = _scalar_result(proj)

        user = _make_user()
        update = ProjectUpdate(name="Updated Name")
        result = await update_project(
            id="proj-001", project_in=update, db=db, current_user=user
        )

        assert proj.name == "Updated Name"
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_project_not_found(self):
        """Raises 404 when project does not exist."""
        db = AsyncMock()
        db.execute.return_value = _scalar_result(None)

        user = _make_user()
        update = ProjectUpdate(name="New Name")
        with pytest.raises(HTTPException) as exc_info:
            await update_project(
                id="nonexistent", project_in=update, db=db, current_user=user
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_project_wrong_owner_forbidden(self):
        """Raises 403 when updating another user's project."""
        proj = _make_project(owner_id=OTHER_USER_ID)
        db = AsyncMock()
        db.execute.return_value = _scalar_result(proj)

        user = _make_user()
        update = ProjectUpdate(name="Hacked")
        with pytest.raises(HTTPException) as exc_info:
            await update_project(
                id="proj-001", project_in=update, db=db, current_user=user
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_update_project_programming_languages_serializes(self):
        """Programming languages list is serialized to JSON on update."""
        proj = _make_project()
        db = AsyncMock()
        db.execute.return_value = _scalar_result(proj)

        user = _make_user()
        update = ProjectUpdate(programming_languages=["python", "javascript"])
        await update_project(
            id="proj-001", project_in=update, db=db, current_user=user
        )

        assert proj.programming_languages == json.dumps(["python", "javascript"])


# ===================================================================
# delete_project (soft delete)
# ===================================================================

class TestDeleteProject:

    @pytest.mark.asyncio
    async def test_soft_delete_success(self):
        """Soft-deletes a project by setting is_active=False."""
        proj = _make_project(is_active=True)
        db = AsyncMock()
        db.execute.return_value = _scalar_result(proj)

        user = _make_user()
        result = await delete_project(id="proj-001", db=db, current_user=user)

        assert proj.is_active is False
        assert result["message"] == "项目已删除"
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_soft_delete_not_found(self):
        """Raises 404 when project does not exist."""
        db = AsyncMock()
        db.execute.return_value = _scalar_result(None)

        user = _make_user()
        with pytest.raises(HTTPException) as exc_info:
            await delete_project(id="nonexistent", db=db, current_user=user)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_soft_delete_wrong_owner_forbidden(self):
        """Raises 403 when deleting another user's project."""
        proj = _make_project(owner_id=OTHER_USER_ID)
        db = AsyncMock()
        db.execute.return_value = _scalar_result(proj)

        user = _make_user()
        with pytest.raises(HTTPException) as exc_info:
            await delete_project(id="proj-001", db=db, current_user=user)
        assert exc_info.value.status_code == 403


# ===================================================================
# restore_project
# ===================================================================

class TestRestoreProject:

    @pytest.mark.asyncio
    async def test_restore_success(self):
        """Restores a soft-deleted project."""
        proj = _make_project(is_active=False)
        db = AsyncMock()
        db.execute.return_value = _scalar_result(proj)

        user = _make_user()
        result = await restore_project(id="proj-001", db=db, current_user=user)

        assert proj.is_active is True
        assert result["message"] == "项目已恢复"

    @pytest.mark.asyncio
    async def test_restore_not_found(self):
        """Raises 404 when project does not exist."""
        db = AsyncMock()
        db.execute.return_value = _scalar_result(None)

        user = _make_user()
        with pytest.raises(HTTPException) as exc_info:
            await restore_project(id="nonexistent", db=db, current_user=user)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_restore_wrong_owner_forbidden(self):
        """Raises 403 when restoring another user's project."""
        proj = _make_project(owner_id=OTHER_USER_ID)
        db = AsyncMock()
        db.execute.return_value = _scalar_result(proj)

        user = _make_user()
        with pytest.raises(HTTPException) as exc_info:
            await restore_project(id="proj-001", db=db, current_user=user)
        assert exc_info.value.status_code == 403


# ===================================================================
# permanently_delete_project
# ===================================================================

class TestPermanentlyDeleteProject:

    @pytest.mark.asyncio
    async def test_permanent_delete_success(self):
        """Permanently deletes a repository project."""
        proj = _make_project()
        db = AsyncMock()
        db.execute.return_value = _scalar_result(proj)

        user = _make_user()
        result = await permanently_delete_project(
            id="proj-001", db=db, current_user=user
        )

        assert result["message"] == "项目已永久删除"
        db.delete.assert_called_once_with(proj)
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_permanent_delete_zip_cleans_files(self):
        """ZIP projects have their zip files cleaned up on permanent delete."""
        proj = _make_project(source_type="zip")
        db = AsyncMock()
        db.execute.return_value = _scalar_result(proj)

        user = _make_user()
        with patch("app.api.v1.endpoints.projects.delete_project_zip", new_callable=AsyncMock) as mock_del_zip:
            result = await permanently_delete_project(
                id="proj-001", db=db, current_user=user
            )

        mock_del_zip.assert_called_once_with("proj-001")
        assert result["message"] == "项目已永久删除"

    @pytest.mark.asyncio
    async def test_permanent_delete_not_found(self):
        """Raises 404 when project does not exist."""
        db = AsyncMock()
        db.execute.return_value = _scalar_result(None)

        user = _make_user()
        with pytest.raises(HTTPException) as exc_info:
            await permanently_delete_project(
                id="nonexistent", db=db, current_user=user
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_permanent_delete_wrong_owner_forbidden(self):
        """Raises 403 when permanently deleting another user's project."""
        proj = _make_project(owner_id=OTHER_USER_ID)
        db = AsyncMock()
        db.execute.return_value = _scalar_result(proj)

        user = _make_user()
        with pytest.raises(HTTPException) as exc_info:
            await permanently_delete_project(
                id="proj-001", db=db, current_user=user
            )
        assert exc_info.value.status_code == 403
