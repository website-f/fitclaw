from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.projects.models import Project
from app.modules.projects.schemas import DeployResponse, ProjectUpsert

logger = logging.getLogger(__name__)


class ProjectService:
    @staticmethod
    def upsert(db: Session, user_id: str, payload: ProjectUpsert) -> Project:
        existing = db.execute(
            select(Project).where(Project.user_id == user_id, Project.slug == payload.slug)
        ).scalar_one_or_none()
        if existing is None:
            row = Project(
                user_id=user_id,
                slug=payload.slug,
                name=payload.name,
                description=payload.description,
                keywords=list(payload.keywords),
                repo_url=payload.repo_url,
                default_branch=payload.default_branch,
                branches=list(payload.branches) if payload.branches else [payload.default_branch],
                agent_name=payload.agent_name,
                local_path=payload.local_path,
                vps_path=payload.vps_path,
                deploy_command=payload.deploy_command,
            )
            db.add(row)
        else:
            existing.name = payload.name
            existing.description = payload.description
            existing.keywords = list(payload.keywords)
            existing.repo_url = payload.repo_url
            existing.default_branch = payload.default_branch
            existing.branches = list(payload.branches) if payload.branches else existing.branches
            existing.agent_name = payload.agent_name
            existing.local_path = payload.local_path
            existing.vps_path = payload.vps_path
            existing.deploy_command = payload.deploy_command
            row = existing
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def list(db: Session, user_id: str) -> list[Project]:
        return list(
            db.execute(
                select(Project)
                .where(Project.user_id == user_id)
                .order_by(Project.slug.asc())
            )
            .scalars()
            .all()
        )

    @staticmethod
    def get_by_slug(db: Session, user_id: str, slug: str) -> Project | None:
        return db.execute(
            select(Project).where(Project.user_id == user_id, Project.slug == slug)
        ).scalar_one_or_none()

    @staticmethod
    def delete(db: Session, user_id: str, slug: str) -> bool:
        row = ProjectService.get_by_slug(db, user_id, slug)
        if row is None:
            return False
        db.delete(row)
        db.commit()
        return True

    @staticmethod
    def match_by_text(db: Session, user_id: str, text: str) -> list[Project]:
        """Return projects whose slug, name, or keywords appear as substrings of `text`.

        Cheap and predictable: lowercase substring match. If two projects share
        keywords, both are returned and the caller asks the user to disambiguate.
        """
        if not text:
            return []
        text_lower = text.lower()
        candidates = ProjectService.list(db, user_id)
        hits: list[Project] = []
        for project in candidates:
            haystack = [project.slug.lower(), project.name.lower()]
            haystack.extend((kw or "").lower() for kw in (project.keywords or []))
            for needle in haystack:
                if needle and needle in text_lower:
                    hits.append(project)
                    break
        return hits

    @staticmethod
    def run_deploy(db: Session, user_id: str, slug: str, branch: str | None) -> DeployResponse:
        """Execute project.deploy_command on the host this server runs on.

        SECURITY: deploy_command is executed via /bin/sh — owner of the project
        registry (i.e. you) is fully trusted to set it. Don't expose project
        upsert to untrusted users without a sandbox.
        """
        project = ProjectService.get_by_slug(db, user_id, slug)
        if project is None:
            raise ValueError(f"project '{slug}' not found")
        if not project.deploy_command:
            raise ValueError(f"project '{slug}' has no deploy_command configured")

        cmd = project.deploy_command
        env_extras = {
            "PROJECT_SLUG": project.slug,
            "PROJECT_BRANCH": branch or project.default_branch,
            "VPS_PATH": project.vps_path or "",
        }
        cwd: str | None = project.vps_path
        if cwd and not os.path.isdir(cwd):
            logger.warning("vps_path %s does not exist on this container; falling back to /tmp", cwd)
            cwd = None
        logger.info("deploy %s branch=%s cwd=%s", slug, branch, cwd)
        started = datetime.now(timezone.utc)
        try:
            result = subprocess.run(
                ["/bin/sh", "-c", cmd],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=600,
                env={**_safe_env(), **env_extras},
            )
            return DeployResponse(
                project_slug=slug,
                branch=branch,
                started_at=started,
                finished_at=datetime.now(timezone.utc),
                exit_code=result.returncode,
                stdout=result.stdout[-4000:],  # tail
                stderr=result.stderr[-2000:],
            )
        except subprocess.TimeoutExpired:
            return DeployResponse(
                project_slug=slug,
                branch=branch,
                started_at=started,
                finished_at=datetime.now(timezone.utc),
                exit_code=-1,
                stdout="",
                stderr="deploy timed out after 600s",
            )


def _safe_env() -> dict[str, str]:
    """Pass through PATH and a small allowlist; drop our own secrets."""
    import os

    allow = {
        "PATH",
        "HOME",
        "LANG",
        "LC_ALL",
        "TERM",
        "SHELL",
        "USER",
    }
    return {k: v for k, v in os.environ.items() if k in allow or k.startswith("DOCKER_")}
