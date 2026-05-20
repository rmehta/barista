"""Image-build task. Renders the per-spec Dockerfile, kicks docker-manager,
streams the log into the Bench Build row."""

from __future__ import annotations

import time

import frappe

from ..exceptions import DockerManagerError
from ._base import BaristaTask


class BuildBenchImage(BaristaTask):
    kind = "Update"   # bench rebuilds are recorded as "Update" actions

    def run(self) -> None:
        build_name = self.action.target
        build = frappe.get_doc("Bench Build", build_name)
        spec = frappe.get_doc("Bench Spec", build.spec)

        dockerfile = self._render_dockerfile(spec)
        tag = self._image_tag(spec, build_name)

        build.dockerfile = dockerfile
        build.mark_running()

        started = self.dm.start_build(tag=tag, dockerfile=dockerfile)
        build_id = started["build_id"]
        offset = 0
        while True:
            chunk = self.dm.build_log(build_id, since=offset)
            if chunk.get("data"):
                build.append_log(chunk["data"])
                offset = chunk["offset"]
            status = chunk.get("status")
            if status == "success":
                build.mark_finished(success=True, image_tag=tag)
                self._update_spec(spec, tag)
                return
            if status in ("failure", "cancelled"):
                build.mark_finished(success=False, error=chunk.get("error"))
                raise DockerManagerError(f"build {build_id} {status}")
            time.sleep(2)

    # ---- helpers ----

    def _render_dockerfile(self, spec) -> str:
        lines = [
            f"FROM {spec.base_image}",
            "USER frappe",
            "WORKDIR /home/frappe",
            f"RUN bench init --skip-redis-config-generation "
            f"--frappe-branch={spec.frappe_branch} bench",
            "WORKDIR /home/frappe/bench",
        ]
        for app in spec.apps or []:
            if app.app_name == "frappe":
                continue
            branch_flag = f"--branch {app.branch}" if app.branch else ""
            repo = self._repo_for(app)
            lines.append(f"RUN bench get-app {branch_flag} {repo}")
        return "\n".join(lines) + "\n"

    def _repo_for(self, spec_app) -> str:
        if not spec_app.source:
            return spec_app.app_name
        return frappe.db.get_value("Bench App", spec_app.source,
                                    "repository_url") or spec_app.app_name

    def _image_tag(self, spec, build_name: str) -> str:
        short = build_name[:8]
        return f"barista/bench-{spec.name}:{short}"

    def _update_spec(self, spec, tag: str) -> None:
        spec.latest_image = tag
        spec.build_status = "Built"
        spec.save(ignore_permissions=True)
