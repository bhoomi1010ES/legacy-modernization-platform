"""Deliberately configured draft PR adapter. Never pushes/merges or deploys implicitly."""

import logging
import re
from urllib.parse import quote
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class GitHubProvider:
    async def create(self, *, branch: str, commit: str, title: str, body: str) -> dict:
        try:
            repository = settings.PHASE7_GITHUB_REPOSITORY
            token = settings.PHASE7_GITHUB_TOKEN
            base = settings.PHASE7_PR_BASE_BRANCH
            if (
                not token
                or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
                or settings.PHASE7_GITHUB_API_URL != "https://api.github.com"
                or not re.fullmatch(r"[A-Za-z0-9_./-]+", base)
            ):
                return {
                    "status": "MANUAL_REQUIRED",
                    "reason": "GitHub credentials/repository/base/provider support are not deliberately configured",
                }
            api = settings.PHASE7_GITHUB_API_URL
            headers = {
                "Authorization": "Bearer " + token,
                "Accept": "application/vnd.github+json",
            }
            async with httpx.AsyncClient(
                timeout=20, follow_redirects=False, headers=headers
            ) as client:
                remote = await client.get(
                    f"{api}/repos/{repository}/git/ref/heads/{quote(branch, safe='')}"
                )
                if (
                    remote.status_code != 200
                    or remote.json().get("object", {}).get("sha") != commit
                ):
                    return {
                        "status": "MANUAL_REQUIRED",
                        "reason": "Push the exact candidate branch through an approved credential workflow; remote commit is absent or differs",
                    }
                existing = await client.get(
                    f"{api}/repos/{repository}/pulls",
                    params={
                        "state": "open",
                        "head": repository.split("/")[0] + ":" + branch,
                        "base": base,
                    },
                )
                if existing.status_code != 200:
                    return {
                        "status": "MANUAL_REQUIRED",
                        "reason": "Cannot safely resolve existing PR identity",
                    }
                matches = [
                    item
                    for item in existing.json()
                    if item.get("head", {}).get("sha") == commit
                    and item.get("head", {}).get("ref") == branch
                ]
                if matches:
                    result = matches[0]
                else:
                    response = await client.post(
                        f"{api}/repos/{repository}/pulls",
                        json={
                            "title": title,
                            "body": body,
                            "head": branch,
                            "base": base,
                            "draft": True,
                        },
                    )
                    if response.status_code != 201:
                        return {
                            "status": "MANUAL_REQUIRED",
                            "reason": f"GitHub did not create a PR (HTTP {response.status_code}); no success claimed",
                        }
                    result = response.json()
                url = result.get("html_url", "")
                if (
                    not url.startswith(f"https://github.com/{repository}/pull/")
                    or result.get("head", {}).get("sha") != commit
                    or result.get("head", {}).get("ref") != branch
                ):
                    return {
                        "status": "UNKNOWN",
                        "reason": "Provider PR identity did not match the approved candidate",
                    }
                return {
                    "status": "CREATED",
                    "url": url,
                    "number": result.get("number"),
                    "provider": "github",
                    "commit": commit,
                    "branch": branch,
                    "draft": result.get("draft"),
                }
        except Exception:
            # Provider exceptions can contain request metadata; never log the token/response.
            logger.exception(
                "GitHubProvider.create failed; external outcome unknown; no automatic retry"
            )
            return {
                "status": "UNKNOWN",
                "reason": "Provider request failed; inspect the remote before retrying. No success claimed.",
            }


def configured_provider():
    try:
        return GitHubProvider() if settings.PHASE7_PR_PROVIDER == "github" else None
    except Exception:
        logger.exception("git_provider.configured_provider failed")
        raise
