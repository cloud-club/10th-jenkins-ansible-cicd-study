"""Write deployment metadata from docker image inspect and Jenkins environment variables."""

import json
import os
import re
from pathlib import Path

image = json.loads(Path(".artifacts/image-inspect.json").read_text())[0]
repository = os.environ["IMAGE_REPOSITORY"]
image_ref = next(
    ref for ref in image["RepoDigests"]
    if ref.startswith(repository + "@sha256:")
)
if not re.fullmatch(re.escape(repository) + r"@sha256:[0-9a-f]{64}", image_ref):
    raise ValueError("Invalid image digest")
Path(".artifacts/deploy-vars.json").write_text(json.dumps({
    "image_repository": repository,
    "image_ref": image_ref,
    "app_version": os.environ["APP_VERSION"],
    "release_id": os.environ["RELEASE_ID"],
    "git_revision": os.environ["GIT_REVISION"],
}, indent=2))
print("Deploy image:", image_ref)
