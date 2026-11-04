"""Universal Workflow Discovery Engine (multi-paradigm route and entrypoint detection)."""

from collections import defaultdict
from pathlib import Path
import re
from typing import Dict, List, Set
import uuid

from app.characterization.contracts.workflows import (
    EntryPointDefinition,
    WorkflowDefinition,
    WorkflowInventory,
)


class UniversalWorkflowDiscoveryEngine:
    """Discovers application workflows, entrypoints, and routes without framework bias."""

    ROUTE_PATTERNS = [
        # Python decorators: @app.get('/path'), @router.route('/path')
        (re.compile(r"@(?:app|router|bp|api)\.(get|post|put|delete|patch|route)\s*\(\s*['\"]([^'\"]+)['\"]", re.IGNORECASE), "PYTHON_ROUTE"),
        # JS/TS router: app.get('/path'), router.post('/path')
        (re.compile(r"(?:app|router|server|http|r)\.(get|post|put|delete|patch)\s*\(\s*['\"]([^'\"]+)['\"]", re.IGNORECASE), "EXPRESS_ROUTE"),
        # Go HTTP handles: r.HandleFunc('/path', ...), r.GET('/path')
        (re.compile(r"(?:r|router|http|e|app)\.(?:HandleFunc|GET|POST|PUT|DELETE|PATCH)\s*\(\s*['\"]([^'\"]+)['\"]", re.IGNORECASE), "GO_ROUTE"),
        # Rails / Ruby routes: get '/path', resources :users
        (re.compile(r"(?:get|post|put|patch|delete)\s+['\":]([a-zA-Z0-9_/-]+)", re.IGNORECASE), "RAILS_ROUTE"),
        # HTML Forms: <form action="/submit" method="post">
        (re.compile(r"<form\s+[^>]*action=['\"]([^'\"]+)['\"][^>]*>", re.IGNORECASE), "HTML_FORM"),
    ]

    CRITICAL_KEYWORDS: Set[str] = {
        "auth", "login", "register", "password", "token", "secret",
        "pay", "payment", "checkout", "billing", "invoice", "charge",
        "order", "book", "rent", "reserve", "cart",
        "delete", "remove", "update", "create", "mutate",
    }

    def discover(self, workspace_path: Path) -> WorkflowInventory:
        """Scan repository files to discover entrypoints and synthesize workflow domains."""
        discovered_entrypoints: List[EntryPointDefinition] = []
        domain_groups: Dict[str, List[EntryPointDefinition]] = defaultdict(list)
        all_domains: Set[str] = set()

        if not workspace_path.exists():
            return WorkflowInventory()

        for file_path in sorted(workspace_path.rglob("*")):
            if not file_path.is_file():
                continue

            rel_parts = file_path.relative_to(workspace_path).parts
            if any(part in {".git", "node_modules", ".venv", "dist", "build"} for part in rel_parts):
                continue

            # Only scan text/source files
            if file_path.suffix.lower() not in {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rb", ".php", ".html", ".htm"}:
                continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            rel_str = file_path.relative_to(workspace_path).as_posix()

            for pattern, ep_type in self.ROUTE_PATTERNS:
                for match in pattern.finditer(content):
                    line_no = content[:match.start()].count("\n") + 1
                    groups = match.groups()

                    if ep_type == "HTML_FORM":
                        path_val = groups[0]
                        method_val = "POST"
                    elif len(groups) == 2:
                        method_val = groups[0].upper()
                        path_val = groups[1]
                    else:
                        method_val = "GET"
                        path_val = groups[0]

                    clean_path = "/" + path_val.lstrip("/")
                    # Extract domain prefix (e.g. /api/cars/1 -> cars, /auth/login -> auth)
                    segments = [s for s in clean_path.split("/") if s and s not in {"api", "v1", "v2"}]
                    domain = segments[0] if segments else "root"
                    all_domains.add(domain)

                    ep = EntryPointDefinition(
                        entrypoint_id=f"ep_{uuid.uuid4().hex[:8]}",
                        entrypoint_type=ep_type,
                        path=clean_path,
                        method=method_val,
                        source_file=rel_str,
                        line_number=line_no,
                        signature=match.group(0)[:80],
                    )
                    discovered_entrypoints.append(ep)
                    domain_groups[domain].append(ep)

        # If no routes found but HTML files exist (static web project), extract static page workflows
        if not discovered_entrypoints:
            html_files = sorted(list(workspace_path.glob("*.html")))
            for hf in html_files:
                rel = hf.relative_to(workspace_path).as_posix()
                domain = hf.stem or "root"
                all_domains.add(domain)
                ep = EntryPointDefinition(
                    entrypoint_id=f"ep_{uuid.uuid4().hex[:8]}",
                    entrypoint_type="WEB_ROUTE",
                    path=f"/{rel}",
                    method="GET",
                    source_file=rel,
                    line_number=1,
                    signature=f"GET /{rel}",
                )
                discovered_entrypoints.append(ep)
                domain_groups[domain].append(ep)

        # Synthesize WorkflowDefinition items from domain clusters
        workflows: List[WorkflowDefinition] = []
        critical_count = 0

        for domain, eps in sorted(domain_groups.items()):
            wf_id = f"wf_{domain.replace('-', '_')}_{uuid.uuid4().hex[:6]}"
            is_critical = any(
                any(kw in ep.path.lower() or kw in domain.lower() for kw in self.CRITICAL_KEYWORDS)
                for ep in eps
            )
            if is_critical:
                critical_count += 1

            workflows.append(
                WorkflowDefinition(
                    workflow_id=wf_id,
                    name=f"{domain.capitalize()} Workflow",
                    domain=domain,
                    description=f"Synthesized domain workflow encompassing {len(eps)} entrypoints under '{domain}'.",
                    entrypoints=eps,
                    is_critical=is_critical,
                    declared_side_effects=["DATA_PERSISTENCE" if is_critical else "HTTP_RESPONSE"],
                )
            )

        return WorkflowInventory(
            total_workflows=len(workflows),
            critical_workflows_count=critical_count,
            workflows=workflows,
            entrypoints=discovered_entrypoints,
            domains_discovered=sorted(list(all_domains)),
        )

